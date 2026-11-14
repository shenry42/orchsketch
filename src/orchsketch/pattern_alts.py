"""Pattern alternatives (SPEC §14, milestone 7): patterns 1, 2 and 3 on top of each harmony alternative.

The choice is two steps: pick the harmony (A/B/C) first, then the patterns (1/2/3) on top of it.

    Pattern 1  exactly the patterns, note modes and accents you set (with every new option at its default:
               v1.1's result).
    2 and 3    for every section, the parts that play a pattern get another pattern from the same family
               (8ths, 16ths or pulse; data/patterns) and/or another accent grouping, the same for every part of
               the section that had the same pattern. A few seeded candidates are rendered and the one with the
               fewest parallels inside the patterns wins. Your note modes are kept.

Only render settings change (Settings.part_variants), so every pitch at a chord change stays exactly the
harmony alternative's and switching patterns never re-runs the voicing search. Locked parts keep their pattern
when the patterns are regenerated, and Regenerate steers away from the last 8 results, as for the harmony.
No UI code.
"""
from __future__ import annotations

import random
from dataclasses import replace

from . import patterns as pat
from .generator import REGEN_MEMORY, Orchestration, rerender
from .instruments import instruments as builtin_instruments

PATTERN_ALTS = (1, 2, 3)
TRIES = 4  # candidates rendered per pattern alternative


def base_settings(orch: Orchestration):
    """The harmony alternative's own settings (pattern 1)."""
    return replace(orch.settings, part_variants=())


def pattern_number(orch: Orchestration) -> int:
    return orch.meta.get("pattern_alt", 1)


def alt_name(orch: Orchestration) -> str:
    """'A' for pattern 1, 'A2' / 'A3' for the others (tabs, export file names)."""
    k = pattern_number(orch)
    return orch.approach if k == 1 else f"{orch.approach}{k}"


def groups(orch: Orchestration, insts=None) -> dict[tuple[str, str, str], list[str]]:
    """(section, pattern, accent) of pattern 1 -> the sounding parts that play it (Sustain left out)."""
    insts = insts or builtin_instruments()
    st = base_settings(orch)
    out: dict[tuple[str, str, str], list[str]] = {}
    for ln in orch.sounding_lines:
        if ln.id in orch.figures:
            continue
        sec = insts[ln.instrument].section
        pt = st.pattern_for(ln.id, sec, ln.instrument)
        if not pat.allowed(pt, sec == "choir") or pt == pat.SUSTAIN:
            continue
        out.setdefault((sec, pt, st.accent_for(ln.id, sec)), []).append(ln.id)
    return out


def _options(section: str, pattern: str, accent: str) -> list[tuple[str, str]]:
    """Every (pattern, accent) in the pattern's family the section can play, except pattern 1's own."""
    lib = pat.library()
    out = []
    for p in pat.family(pattern):
        if not pat.allowed(p, section == "choir"):
            continue
        accents = pat.ACCENTS if lib[p].kind == "grid" else (pat.PATTERN_ACCENTS,)
        out += [(p, a) for a in accents if (p, a) != (pattern, accent)]
    return out


def choices(orch: Orchestration, k: int, variation: int = 0, keep: dict | None = None, insts=None,
            attempt: int = 0) -> tuple:
    """One candidate set of Settings.part_variants for pattern k (2 or 3). keep: line id -> (pattern, accent)
    for locked parts."""
    keep = keep or {}
    out = {}
    for (sec, pt, acc), ids in sorted(groups(orch, insts).items()):
        opts = _options(sec, pt, acc)
        if not opts:
            continue
        rng = random.Random(f"patterns:{orch.seed}:{orch.approach}:{variation}:{attempt}:{sec}:{pt}:{acc}")
        rng.shuffle(opts)
        pick = opts[(k - 2) % len(opts)]  # 2 and 3 take different options of the same shuffle
        for lid in ids:
            out[lid] = pick
    out.update({lid: v for lid, v in keep.items() if lid in {ln.id for ln in orch.lines}})
    return tuple(sorted(out.items()))


def _score(o: Orchestration) -> int:
    return len(o.report.by_check("pattern_parallels")) + len(o.report.by_check("parallels"))


def pattern_alternative(orch: Orchestration, k: int, variation: int = 0, *, keep: dict | None = None,
                        previous: tuple = (), rules=None, instruments=None) -> Orchestration:
    """Harmony alternative `orch` with pattern k (1, 2 or 3). Pattern 1 is orch's own settings.
    previous: earlier choices to steer away from (Regenerate)."""
    if k not in PATTERN_ALTS:
        raise ValueError("pattern alternatives are 1, 2 and 3")
    base = base_settings(orch)
    if k == 1:
        if not orch.settings.part_variants and pattern_number(orch) == 1:
            return orch  # orchestrations are never changed in place (undo relies on it)
        o = rerender(orch, base, rules, instruments)
        o.meta = {kk: v for kk, v in o.meta.items() if not kk.startswith("pattern_")}
        return o
    best = None
    seen = set()
    for attempt in range(TRIES * 3):
        ch = choices(orch, k, variation, keep, instruments, attempt)
        if ch in seen or ch in previous:
            continue
        seen.add(ch)
        o = rerender(orch, replace(base, part_variants=ch), rules, instruments)
        if best is None or _score(o) < _score(best):
            best = o
        if len(seen) >= TRIES:
            break
    if best is None:  # nothing new: every choice was used before
        best = rerender(orch, replace(base, part_variants=choices(orch, k, variation, keep, instruments)),
                        rules, instruments)
    best.meta = dict(best.meta, pattern_alt=k, pattern_variation=variation,
                     pattern_previous=tuple(previous)[:REGEN_MEMORY])
    return best


def regenerate_patterns(current: Orchestration, harmony: Orchestration, locked_ids=frozenset(), *,
                        rules=None, instruments=None) -> Orchestration:
    """New choices for the current pattern alternative (2 or 3), locked parts kept, away from the current
    choice and the 7 before it."""
    k = pattern_number(current)
    if k == 1:
        raise ValueError("pattern 1 is your own settings; regenerate patterns 2 or 3")
    vs = dict(current.settings.part_variants)
    keep = {lid: vs.get(lid, (None, None)) for lid in locked_ids if lid in vs}
    previous = ((current.settings.part_variants,) + tuple(current.meta.get("pattern_previous", ())))[:REGEN_MEMORY]
    return pattern_alternative(harmony, k, current.meta.get("pattern_variation", 0) + 1, keep=keep,
                               previous=previous, rules=rules, instruments=instruments)


def reapply(palt: Orchestration, harmony: Orchestration, rules=None, instruments=None) -> Orchestration:
    """The same pattern choices on an edited harmony alternative (after a lock, swap or regenerate)."""
    o = rerender(harmony, replace(base_settings(harmony), part_variants=palt.settings.part_variants), rules,
                 instruments)
    o.meta = dict(o.meta, **{k: v for k, v in palt.meta.items() if k.startswith("pattern_")})
    return o


def refresh(palt: Orchestration, harmony: Orchestration, locked_ids=frozenset(), rules=None,
            instruments=None) -> Orchestration:
    """Pattern k worked out again for a harmony alternative whose pattern settings changed (same variation;
    locked parts keep their choices)."""
    vs = dict(palt.settings.part_variants)
    keep = {lid: vs[lid] for lid in locked_ids if lid in vs}
    return pattern_alternative(harmony, pattern_number(palt), palt.meta.get("pattern_variation", 0), keep=keep,
                               previous=tuple(palt.meta.get("pattern_previous", ())), rules=rules,
                               instruments=instruments)


def describe(orch: Orchestration, insts=None) -> str:
    """'strings 16ths pendulum (3+3+2), brass half-time pulse': what plays a pattern, by section."""
    insts = insts or builtin_instruments()
    st = orch.settings
    lib = pat.library()
    seen: dict[str, list[str]] = {}
    for ln in orch.sounding_lines:
        if ln.id in orch.figures:
            continue
        sec = insts[ln.instrument].section
        pt = st.pattern_for(ln.id, sec, ln.instrument)
        if not pat.allowed(pt, sec == "choir") or pt == pat.SUSTAIN:
            continue
        acc = st.accent_for(ln.id, sec)
        mode = st.note_mode_for(sec)
        bits = [lib[pt].name[0].lower() + lib[pt].name[1:] if not lib[pt].name[:2].isdigit() else lib[pt].name]
        if acc != pat.PATTERN_ACCENTS and lib[pt].kind == "grid":
            bits.append(acc)
        if mode != pat.CHORD_TONES and not lib[pt].flat:
            bits.append(pat.NOTE_MODE_NAMES[mode].lower())
        text = bits[0] + (f" ({', '.join(bits[1:])})" if len(bits) > 1 else "")
        seen.setdefault(sec, [])
        if text not in seen[sec]:
            seen[sec].append(text)
    out = "; ".join(f"{sec}: {' / '.join(v)}" for sec, v in seen.items())
    # v1.3: shapes, fills and rhythm options (render settings that change what you hear)
    from . import shapes as shp
    from .generator import FILL_NAMES, FILL_NONE
    secs = sorted({insts[ln.instrument].section for ln in orch.sounding_lines})
    extra = []
    for name, get, names, none in (("shape", st.shape_for, shp.SHAPE_NAMES, shp.STEADY),
                                   ("fill", st.fill_for, FILL_NAMES, FILL_NONE)):
        vals = {sec: get(sec) for sec in secs}
        if set(vals.values()) - {none}:
            if len(set(vals.values())) == 1:
                extra.append(f"{name} {names[next(iter(vals.values()))].lower()}")
            else:
                extra.append(f"{name} " + ", ".join(f"{sec} {names[v].lower()}" for sec, v in vals.items() if v != none))
    if any(st.fill_for(sec) != FILL_NONE for sec in secs) or any(
            shp.library()[st.shape_for(sec)].span == "phrase" for sec in secs):
        extra.append(f"{st.phrase}-bar phrases")
    extra += [t for on, t in ((st.pattern_emphasis, "pattern emphasis"), (st.clear_low, "clear low register"),
                              (st.change_accents, "accented chord changes")) if on]
    # v1.4: expression
    from . import expression as ex
    sw = {sec: st.swell_for(sec) for sec in secs}
    if set(sw.values()) - {ex.SWELL_OFF}:
        extra.append("swells " + ", ".join(f"{sec} {ex.SWELL_NAMES[v].lower()}" for sec, v in sw.items()
                                           if v != ex.SWELL_OFF) if len(set(sw.values())) > 1
                     else "swells " + ex.SWELL_NAMES[next(iter(sw.values()))].lower())
    ex_meta = orch.meta.get("expression") or {}
    extra += [t for on, t in ((st.curves, "CC curves"), (st.phrase_arcs, "phrase arcs"),
                              (st.beat_accents, "beat accents"), (st.balance, "balanced sections"),
                              (st.long_doubling, "long notes only in the high doubling"),
                              (st.humanize != ex.HUMANIZE_OFF, f"humanize {st.humanize}"),
                              (bool(ex_meta.get("trem")), "tremolo part")) if on]
    if st.riser:
        rise = ex_meta.get("rise") or {}
        layers = max((v[3] for v in rise.values()), default=0)
        extra.append((f"{st.riser}-bar {'Shepard ' if layers > 1 else ''}riser in the {st.riser_section}") if rise
                     else "no riser (it didn't fit)")
    if extra:
        out = (out + "; " if out else "") + ", ".join(extra)
    return out
