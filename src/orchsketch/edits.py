"""Control over results (SPEC §5d): lock and regenerate, regenerate one part or one chord, per-chord swap.

Every function takes an Orchestration and returns a new one (the old one is never changed), so undo/redo
can simply keep the old objects. No UI code.

    regenerate(orch, locked_ids)          new variation of every unlocked part (locked parts stay exactly)
    regenerate_part(orch, line_id)        one part gets its own new line; everything else stays
    regenerate_chord(orch, i, locked_ids) one chord gets a new voicing that fits between its neighbours
    swap(target, source, chords, ...)     use another alternative's voicing for some chords (or a bar)

After a swap the checker re-runs on the whole result, and any leap the swap made bigger (at least
`rules.swap_leap_min` semitones, i.e. more than a perfect 5th) is flagged on the neighbouring chords.
Your own edits are kept even when they break a rule: the cells turn red and the checker says why.
"""
from __future__ import annotations

import random
from dataclasses import replace

from .checker import check
from .generator import (
    APPROACH, CHOIR_IDS, KEEP_LINE_BY_ID, SAME_AS_BEFORE_COST, SECTION_PRIORITY, GenerationError, Orchestration,
    _Cand, _Fixed, _finish, _must_fix, _parallel, _Setup, _Solver, _ties, approach_lines, generate, swap_leaps,
)
from .instruments import instruments as builtin_instruments
from .midi_io import BAR, position_text
from .rules import rules as builtin_rules


def _ctx(rules, insts):
    return rules or builtin_rules(), insts or builtin_instruments()


def next_variation(orch: Orchestration) -> int:
    return orch.meta.get("variation", 0) + 1


# ---------------------------------------------------------------- regenerate (all unlocked)
def regenerate(orch: Orchestration, locked_ids=frozenset(), *, variation: int | None = None,
               rules=None, instruments=None) -> Orchestration:
    """A new variation of every unlocked part, pushed away from the current result. Locked parts keep
    their notes exactly; the rest is orchestrated around them."""
    rules, insts = _ctx(rules, instruments)
    variation = next_variation(orch) if variation is None else variation
    return generate(orch.chords, orch.key, seed=orch.seed, approach=orch.approach, settings=orch.settings,
                    locked=orch, locked_ids=frozenset(locked_ids), variation=variation, avoid=orch,
                    rules=rules, instruments=insts)


# ---------------------------------------------------------------- helpers
def _copy(orch: Orchestration):
    cells = {k: list(v) for k, v in orch.cells.items()}
    labels = {k: list(v) for k, v in orch.meta["labels"].items()}
    voices = [dict(v) for v in orch.meta["voices"]]
    return cells, labels, voices


def _rebuild(orch: Orchestration, cells, labels, voices, *, sources=None, origin=None, rules=None, insts=None,
             **meta_changes) -> Orchestration:
    """A new orchestration from edited cells. Without `sources`, every chord counts as this alternative's
    own again (swaps are baked in); `origin` is the unswapped orchestration a swap started from."""
    meta = dict(orch.meta, labels=labels, voices=voices, **meta_changes)
    meta["sources"] = list(sources) if sources is not None else [orch.approach] * len(orch.chords)
    meta["origin"] = origin if any(s != orch.approach for s in meta["sources"]) else None
    meta.pop("base", None)
    new = _finish(orch.approach, orch.key, orch.seed, orch.chords, orch.lines, cells, meta, orch.settings,
                  rules, insts, reason=orch.reason)
    new.report.issues.extend(swap_leaps(new, rules, insts))
    return new


def _baseline_messages(orch: Orchestration, chord: int) -> set[str]:
    return {i.message for i in orch.report.issues if i.chord == chord}


# ---------------------------------------------------------------- regenerate one part
def regenerate_part(orch: Orchestration, line_id: str, *, variation: int | None = None,
                    rules=None, instruments=None) -> Orchestration:
    """Give one part a new line of its own, keeping every other part exactly.

    The part keeps its rhythm (it sounds where it sounded) and takes chord tones in its comfortable
    range. It never adds a rule problem, never changes the chord's bass note, and is pushed away from its
    old notes. Afterwards it is an independent line (it no longer doubles another part).
    """
    rules, insts = _ctx(rules, instruments)
    variation = next_variation(orch) if variation is None else variation
    line = orch.line(line_id)
    if line_id in orch.figures:
        what = "melody" if line.role == "melody" else "bass line"
        raise GenerationError(f"{line.label} plays your {what} as written, so it can't be regenerated. "
                              "Lock it, or remove the file to orchestrate it freely.")
    inst = insts[line.instrument]
    old = orch.cells[line_id]
    spans = orch.chords
    if all(p is None for p in old):
        raise GenerationError(f"{line.label} rests throughout, so there is nothing to regenerate.")
    rng = random.Random(f"part:{orch.seed}:{variation}:{line_id}")
    cells, labels, voices = _copy(orch)
    others = [ln for ln in orch.lines if ln.id != line_id]
    is_choir = line_id in CHOIR_IDS

    # candidates per chord
    layers: list[list[tuple[int | None, float]]] = []
    for i, span in enumerate(spans):
        if old[i] is None:
            layers.append([(None, 0.0)])
            continue
        others_now = [cells[ln.id][i] for ln in others if cells[ln.id][i] is not None]
        low = min(others_now) if others_now else None
        pcs = span.label.pcs() | {span.label.bass}
        base = _baseline_messages(orch, i)
        opts = []
        for p in range(inst.comfortable[0], inst.comfortable[1] + 1):
            if p % 12 not in pcs:
                continue
            if (low is None or p < low) and p % 12 != span.label.bass:
                continue  # it would become the lowest note on a tone that isn't the bass
            if p != old[i]:
                cells[line_id][i] = p
                labels[line_id][i] = f"free:{line_id}"
                parts = _one_chord_parts(orch, cells, labels, i, insts)
                rep = check(parts, [span], orch.key, orch.mode, rules=rules, instruments=insts, inside=False)
                bad = [x for x in _must_fix(rep, rules) if x.message not in base and line_id in x.parts
                       or (not x.parts and x.message not in base)]
                if bad:
                    continue
            cost = 0.15 * abs(p - old[i]) + rng.random() * 0.25
            if p == old[i]:
                cost += SAME_AS_BEFORE_COST
            opts.append((p, cost))
        cells[line_id][i], labels[line_id][i] = old[i], orch.meta["labels"][line_id][i]
        layers.append(opts or [(old[i], SAME_AS_BEFORE_COST)])

    tie = _ties(spans)

    def trans(i, a, b):
        if a is None or b is None:
            return 0.0
        if tie[i - 1]:
            return 0.0 if a == b else 50.0
        d = abs(b - a)
        if is_choir and d > rules.choir_max_leap:
            return None
        cost = (0.5 + 0.25 * d + 0.5 * max(0, d - 5) + 4.0 * max(0, d - 12)) if d else 0.0
        for ln in others:
            x, y = cells[ln.id][i - 1], cells[ln.id][i]
            if x is None or y is None or not _parallel(a, b, x, y):
                continue
            if is_choir and ln.id in CHOIR_IDS:
                return None
            cost += 8.0
        return cost

    path = _path(layers, trans)
    if path is None:
        raise GenerationError(f"{line.label} can't get a new line here without breaking a choir rule.")
    for i, p in enumerate(path):
        cells[line_id][i] = p
        labels[line_id][i] = f"free:{line_id}" if p is not None else None
    if cells[line_id] == old:
        raise GenerationError(f"{line.label} has no other line that fits with the other parts.")
    free = set(orch.meta.get("free", set())) | {line_id}
    return _rebuild(orch, cells, labels, voices, rules=rules, insts=insts, free=free, variation=variation)


def _one_chord_parts(orch, cells, labels, i, insts):
    from .generator import build_parts, figure_notes
    span = orch.chords[i]
    figs = orch.figures
    notes = {lid: figure_notes(cells[lid][i], figs[lid][i], span, orch.velocity) for lid in figs if lid in cells}
    return build_parts(orch.lines, [span], {k: [v[i]] for k, v in cells.items()},
                       {k: [v[i]] for k, v in labels.items()}, orch.velocity, insts, tie=[], notes=notes or None)


def _path(layers, trans):
    """Viterbi over per-chord options [(value, cost)] with trans(i, a, b) -> cost or None."""
    best = [c for _, c in layers[0]]
    back = []
    for i in range(1, len(layers)):
        cur, ptr = [], []
        for b, cb in layers[i]:
            top, arg = None, -1
            for j, (a, _) in enumerate(layers[i - 1]):
                if best[j] is None:
                    continue
                t = trans(i, a, b)
                if t is None:
                    continue
                if top is None or best[j] + t < top:
                    top, arg = best[j] + t, j
            cur.append(None if top is None else top + cb)
            ptr.append(arg)
        best, back = cur, back + [ptr]
        if all(x is None for x in best):
            return None
    end = min((j for j in range(len(best)) if best[j] is not None), key=lambda j: best[j])
    idx = [end]
    for ptr in reversed(back):
        idx.append(ptr[idx[-1]])
    idx.reverse()
    return [layers[i][j][0] for i, j in enumerate(idx)]


# ---------------------------------------------------------------- regenerate one chord
def regenerate_chord(orch: Orchestration, index: int, locked_ids=frozenset(), *, variation: int | None = None,
                     rules=None, instruments=None) -> Orchestration:
    """A new voicing for one chord that fits between its neighbours. Locked parts, parts regenerated on
    their own and the kept input voicing stay as they are; the other parts get the new voicing."""
    rules, insts = _ctx(rules, instruments)
    variation = next_variation(orch) if variation is None else variation
    spans = orch.chords
    ap = APPROACH[orch.approach]
    model_ids = set(orch.meta.get("model", []))
    fixed_ids = {ln.id for ln in orch.lines if ln.id not in model_ids or ln.id in locked_ids
                 or ln.id in orch.meta.get("free", set())}
    model = [ln for ln in approach_lines(ap, orch.settings.ensemble, insts, exclude=fixed_ids,
                                         keep=orch.settings.keep is not None) if ln.id in model_ids]
    if not model:
        raise GenerationError("Every part of this chord is locked or kept, so there is nothing to regenerate.")
    fixed_lines = [ln for ln in orch.lines if ln.id in fixed_ids]
    cells, labels, voices = _copy(orch)
    figs = orch.figures
    fixed = _Fixed(fixed_lines, {ln.id: cells[ln.id] for ln in fixed_lines},
                   {ln.id: [None if x is None else (x if ln.id in figs else f"lock:{x}") for x in labels[ln.id]]
                    for ln in fixed_lines},
                   {ln.id: list(figs[ln.id]) for ln in fixed_lines if ln.id in figs})
    setup = _Setup(model, insts, ap, need_bass=False, settings=orch.settings)
    solver = _Solver(setup, spans, orch.key, orch.seed, rules, insts, orch.settings, fixed, variation,
                     avoid={ln.id: cells[ln.id] for ln in model}, extras=orch.meta.get("extras"))
    current = tuple((ln.id, cells[ln.id][index]) for ln in model)
    cands = solver.valid(index, exclude_keys={current})
    if not cands:
        raise GenerationError(f"The chord at {position_text(spans[index].start)} has no other voicing that "
                              "passes the rules with the locked parts.")

    def column(i):
        if not voices[i]:
            return None
        return _Cand(tuple(sorted(voices[i].items())), tuple((ln.id, cells[ln.id][i]) for ln in model), 0.0)

    prev = column(index - 1) if index > 0 else None
    nxt = column(index + 1) if index + 1 < len(spans) else None
    best, best_cost = None, None
    for c in cands:
        cost = c.cost
        if prev is not None:
            t = solver.transition(prev, c, index)
            if t is None:
                continue
            cost += t
        if nxt is not None:
            t = solver.transition(c, nxt, index + 1)
            if t is None:
                continue
            cost += t
        if best_cost is None or cost < best_cost:
            best, best_cost = c, cost
    if best is None:
        raise GenerationError(f"No other voicing of the chord at {position_text(spans[index].start)} connects "
                              "to its neighbours without breaking a choir rule.")
    for ln in model:
        cells[ln.id][index] = best.p(ln.id)
        labels[ln.id][index] = ln.voices[0] if best.p(ln.id) is not None else None
    voices[index] = dict(best.voices)
    return _rebuild(orch, cells, labels, voices, rules=rules, insts=insts, variation=variation)


# ---------------------------------------------------------------- swap
def bar_chords(orch: Orchestration, index: int) -> list[int]:
    """Indices of every chord that starts in the same bar as chord `index`."""
    bar = orch.chords[index].start // BAR
    return [i for i, c in enumerate(orch.chords) if c.start // BAR == bar]


def origin(orch: Orchestration) -> Orchestration:
    """The alternative as it was before any swap (itself when nothing is swapped)."""
    return orch.meta.get("origin") or orch


def swap(target: Orchestration, source: Orchestration, chords: list[int], locked_ids=frozenset(), *,
         rules=None, instruments=None) -> Orchestration:
    """Use the source alternative's voicing for these chords in the target (locked parts stay).
    With the target's own letter as source (`unswap`), the chords go back to the target's own voicing."""
    rules, insts = _ctx(rules, instruments)
    if source.approach == target.approach:
        source = origin(target)
    if [c.start for c in target.chords] != [c.start for c in source.chords]:
        raise ValueError("the two alternatives are for different chords")
    cells, labels, voices = _copy(target)
    src_labels = source.meta["labels"]
    sources = list(target.sources)
    for i in chords:
        for ln in target.lines:
            if ln.id in locked_ids:
                continue
            if ln.id in source.cells:
                cells[ln.id][i] = source.cells[ln.id][i]
                labels[ln.id][i] = src_labels[ln.id][i]
            else:
                cells[ln.id][i], labels[ln.id][i] = None, None
        voices[i] = dict(source.meta["voices"][i])
        sources[i] = source.sources[i]
    return _rebuild(target, cells, labels, voices, sources=sources, origin=origin(target), rules=rules,
                    insts=insts)


def unswap(orch: Orchestration, chords: list[int], locked_ids=frozenset(), *, rules=None,
           instruments=None) -> Orchestration:
    """Put these chords back to the alternative's own voicing."""
    return swap(orch, origin(orch), chords, locked_ids, rules=rules, instruments=instruments)
