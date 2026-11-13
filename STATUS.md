# OrchSketch — Status

> Read this first in every build chat, together with SPEC.md.
> The chat that finishes a milestone updates this file before it ends.

## Current state
- **Version:** v1.2
- **Last milestone completed:** 7 — Pattern engine (v1.2, Phase 2). Before it: 6 — Finish (v1.0) and the
  second benchmark (v1.1).
- **Next:** Phase 2, Milestone 8 — v1.3 Textures and shapes (SPEC §14).
- **Repo:** https://github.com/shenry42/orchsketch
- **Last updated:** 2026-11-13 (Milestone 7 done)

## Milestones
- [x] 1 — v0.1 Read and label (+ packaging spike, audio test with Ableton open)
- [x] 2 — v0.2 Data and checker (range + low-interval tables cross-checked)
- [x] 3 — v0.3 First orchestration (safe mode, grid, playback, per-part export)
- [x] 4 — v0.4 Control (A/B/C alternatives, lock, swap, undo, global sliders, presets)
- [x] 5 — v0.5 Motion (patterns, bass, melody, moderate mode, per-section sliders)
- [x] 6 — v1.0 Finish (projects, full export, .exe, full test-set pass, Ableton check)
- [x] v1.1 — Second benchmark (SPEC §8): Sam's 10 progressions

### Phase 2 — Composition (SPEC §14)
- [x] 7 — v1.2 Pattern engine (pattern data files, shape-preserving ostinato + note-mode control, accent groupings,
  pattern A/B/C, parallels inside patterns, Phase 2 ear-test set, speed cache)
- [ ] 8 — v1.3 Textures and shapes (intensity shapes, arpeggios, stabs, phrase-end fills, unison themes, pulse beds)
- [ ] 9 — v1.4 Expression (CC1/CC11 curves, swells, tremolo part, risers, velocity shaping + humanize)
- [ ] 10 — v1.5 Lines (imitation, runs, pickups, rips/falls, simple bass, countermelody engine, targeted placement)
- [ ] 11 — v1.6 Control (pedal instrument, role overrides, choir override, player counts, keep-as-is, SSAATTBB, repo move)
- [ ] 12 — v2.0 AI line writer (Claude API, button only, checker-validated)

## Test results (latest run)
- **Milestone 7 (v1.2):**
  - Automated tests: Claude's workspace 502 passed, 1 skipped in 14:41 (music21 not installed there), slow
    sweeps included. Windows `run_tests.bat` (Sam, 2026-11-13): 425 passed, 89 deselected (`slow`) in 7:27.
  - **v1.1 unchanged:** the A and v0.4 snapshots and every v1 sweep pass as before, and the new
    `tests/data/v11_patterns_snapshot.json` (450 runs made on tag v1.1: the six v1 patterns as master, per
    section and per instrument, Full epic and Low and heavy, moderate passing tones, re-strike, per-section
    dynamics, melody and bass files) gives exactly v1.1's notes. The v1 renderer is also compared note for
    note with a frozen copy of v1.1's `patterns.py`.
  - New sweeps, all with 0 errors and 0 `generator_must_pass` warnings, cells unchanged, every chord struck on
    the voiced note: the 9 new patterns rotated over the sections × the 3 note modes on all 12 files × A/B/C
    (`slow`; a sample runs in the quick suite), every accent grouping on 8ths/16ths/shaped patterns in Hybrid,
    tests 1, 4 and 11 with melody + bass + moderate + new patterns, pattern alternatives 2/3 and Regenerate
    patterns (locks kept, no cycling within 8).
  - `scripts\benchmark.bat` on Windows: 39/39 runs pass (Sam's 11 benchmark runs + the 28 Phase 2 projects in
    `Projects\Benchmark\Phase2\`): 0 generator errors, 0 must-pass warnings, nothing outside playable range,
    projects reopen exactly.
  - **Ear test** (Sam, 2026-11-13, `tests/ratings.csv` tests P1a…P6d, alternatives B1–B3 = harmony B with
    patterns 1/2/3; Sam rated on B because A's dense low register hides the rhythm). 84 scores, all 3–5, none
    "doesn't make musical sense". Means of pattern 1 (the setup as set) over P1–P6: a baseline 4.3,
    b 8ths rising + 3+3+2 (chord tones) **4.8**, c 16ths pendulum Hybrid 4.2, d 16ths rising Scale steps 4.3.
    Patterns 2: 4.5–4.7 for every setup; patterns 3: 4.2–4.5, but **d 3.5**. Sam's notes:
    - b is the most consistently liked; pattern 2 often the best of the three.
    - "Chaotic / elements clashing" comes almost only with Scale steps (d) and with Hybrid under a melody file
      (P5c, P5d, P1d, P6d, P2d pattern 3).
    - Test 11 + files (P4, 16 bars): rhythms hard to make out in every setup (3–4).
    - Patterns play quietly: Sam had to raise Dynamics to hear them.
    - P1a/P1a2/P1a3 and P6a/a2/a3 are the same music on harmony B (they differ only in the tab shown on A), so
      their spread (P1: 4/5/3, 3/4/5, 4/5/5) shows the ear test's noise is about ±1 point.
  - Speed (Claude's workspace, which is slower than Sam's PC): test 11 + files, moderate, Full epic, all three
    alternatives 10.6 s at v1.1 → 8.3 s now; Full epic without files 2.3 s (unchanged). One pattern
    alternative re-renders in 0.05–0.3 s. Sam's PC (`benchmark_report.txt`): 4-bar progressions 0.3–0.6 s,
    B01 + files (8 bars) 3.0–3.2 s, **test 11 + files (16 bars) 5.0–5.2 s** in every setup including the v1.1
    baseline, so the patterns add nothing, but this case is over SPEC §14's "about 4 s". Pattern alternative
    2/3: 0.08–0.09 s.
- Automated tests (v1.1): 0 failed. Claude's workspace: 461 passed, 1 skipped in 10:24 (music21 not installed
  there), slow sweeps included. `release.bat` runs all of them on Windows before tagging (`test_results.txt`).
- **Second benchmark (SPEC §8, v1.1): PASS.** Sam's 10 progressions (Ableton exports, 4 bars each, B01 8 bars
  with melody and bass files), `scripts\benchmark.bat` (Full epic, safe, seed 1):
  - Labels: 40/40 chords as Sam intended (Sam confirmed 2026-11-12). B08's four chords have 9ths, 11ths, 6ths
    and a #11, outside the v1 chord list: they come out unrecognized (correct per SPEC §3) and are typed in by
    hand as Cm, Abm, Cm, Db. One fix was needed: tritone chords (B02 D · bV, B04 Bb · bV), see Decisions.
  - `benchmark_report.txt` on Windows: 11/11 runs pass (0 generator errors, 0 must-pass warnings, nothing
    outside playable range, projects reopen exactly).
  - Ear test (`tests/ratings.csv`, tests B1–B10): all 11 runs × A/B/C 5/5.
  - B01 + files: about 80–120 warnings per alternative, all "melody clashes a minor 2nd" — Sam's melody uses
    D, G and A natural over F-minor chords (Sam: intended). Warnings only; rated 5/5.
- v1.0 test results follow.
- Automated tests (v1.0): 0 failed. Claude's workspace: 421 passed, 1 skipped in 7:20 (music21 not installed
  there). Windows `run_tests.bat` (skips the 66 `slow` sweeps): 367 passed, 66 deselected in 7:07. `release.bat` runs all of them.
- **V1 pass/fail (SPEC §7): PASS.**
  - Labels: 12/12 files, every chord the best guess.
  - No note outside playable range, and 0 checker errors in generated output (`testset_report.txt`: 15/15 runs).
  - Ear test (`tests/ratings.csv`): all 15 runs × A/B/C rated; final v1.0 scores 5/5 everywhere. In the first pass, test 11 with files got 1/5 (the tuba's octave jumps, now fixed), so only 1 progression was below par even before the fix, within SPEC's "more than 1" limit.
  - Exported MIDI lands at the right position and pitch in Ableton (Sam, 2026-11-12: pass).
- Full test-set pass (`scripts\test_set.bat`, default preset Full epic, safe, seed 1): 15/15 runs pass the
  automatic checks. That covers labels, playable range, generated errors and must-pass warnings (0), and an
  exact reopen of the saved project.
- Milestone 6 manual checks (Sam, 2026-11-12):
  - `run_tests.bat`, `test_set.bat`, `build_exe.bat`: pass. The self-check of the built app passed, audio included.
  - The packaged app played a project while Ableton was playing on ASIO, and saving then reopening a project
    restored it: pass.
  - Ableton drag test, at bar 5 in Arrangement view: a single part and the *All* handle (parts plus the
    full-score file) start on the bar line, are 4 bars long, show the same note names as the grid, and the
    full score opens as named tracks: pass.
- Chord labels on 12-file test set: 12/12 correct, every chord as the best guess (unchanged since Milestone 1).
- Checker errors in generated output: **0**.
  - Approach A gives exactly the v0.3 notes on all 216 Milestone 3 runs and still has 0 warnings of any kind.
  - **v0.4 notes unchanged:** with Milestone 5's defaults (Sustain, safe, no files, equal sections) every note
    (pitch, rhythm, velocity) of A, B and C equals v0.4 for 12 files × every preset line-up, plus Forces ×
    Density samples for A (`tests/data/v04_snapshot.json`).
  - B and C: all 12 files × seeds 1–3 × 15 section combinations, 0 errors and 0 warnings (as in v0.4).
  - New sweeps, all with 0 errors and 0 `generator_must_pass` warnings:
    - Every pattern in every section (rotated) and everywhere, for A/B/C on all 12 files. Patterns add no
      parallels.
    - Moderate mode on all 12 files × A/B/C, with and without 8ths, plus section combinations and moderate
      in one section only. Colour tones land on about 45% of chords.
    - Mixed per-section Forces/Density/Character.
    - Melody + bass on tests 1, 4 and 11: alone and together, seeds 1–2, every preset (with its patterns),
      Forces × Density with moderate and 8ths, and keep-as-is.
    - A walking bass file with passing tones (tests 1, 8 and 11) across every preset.
    - The independent bass on all 12 files.
    - Edits (lock, regenerate, chord, part, swap) with files and patterns.
- Speed: all three alternatives for 16 bars take about 2 s (melody, bass, moderate and patterns all on: about
  3 s), in the background.
- Ear-test ratings (tests/ratings.csv):
  - v1.0 full test set (Sam, 2026-11-12): all 12 progressions plus 1, 4 and 11 with melody and bass files,
    A/B/C 5/5. The first pass (1.0-rc1) had test 11 + files at 1/5 (tuba octave jumps, fixed). Test 12 got
    3/5 only because it is 7 bars long, which is by design, so Sam counts it as 5.
  - v0.4: test 1 A/B/C all 5/5.
  - v0.5: tests 1, 4 and 11 with melody + bass files, A/B/C all 4/5 (Sam: "everything is working; patterns
    fairly generic, room for improvement"). The formal pass over all test files is in Milestone 6.
- Milestone 5 manual checks (Sam, 2026-11-11): melody and bass slots, Generate A/B/C, brass section pattern
  live, part pattern menu, Character Moderate, independent bass, Export parts: all pass ("everything is
  working"). Sam found *Regenerate unlocked* bouncing between two results on short progressions; fixed (it now
  avoids the last 8 variations).
- Milestone 4 manual checks (Sam, 2026-11-11): tabs and reasons, lock + Regenerate unlocked, chord-header
  swap with Ctrl+Z/Ctrl+Y, Regenerate Horn 2 only, Dynamics live, Density → orange Generate, Low and heavy,
  keep-as-is + follow input, export names `_B.mid`: all pass ("Everything is working").
- Milestone 3 manual checks (Sam, 2026-11-11):
  - Sound check (`scripts\sound_check.bat`, 22 instruments + string/choir alternatives): all fine, current GM programs kept.
  - App (test 1, A minor): confirm, generate (31 parts, checker clean), playback with loop/tempo/mute/solo, piano roll,
    section toggles, Export parts: pass. Drag into Ableton: optional now, formally checked in Milestone 6.
- Milestone 1 manual checks (Sam, 2026-11-11):
  - Packaged `.exe` played FluidSynth through WASAPI shared mode **while Ableton was playing on ASIO** (Focusrite): pass.
  - Ableton round trip (own clip → OrchSketch → export → drag into Arrangement): starts on the bar line, same length, same notes: pass.
  - App: load, labels, correction, confirm all: pass (after the click fix below).

## Known issues
- Checker: melodic checks (leaps, parallels) follow each part's top note, so the generator must give every divisi line its own part (which also matches per-line export). Since v1.2 parallels inside chords are checked too (`pattern_parallels`, a warning; see Decisions).
- Checker: low-interval limits cover simple intervals only. Compound intervals (9ths, 10ths...) have no limit; revisit if wide low voicings sound muddy.
- Chords over a non-chord bass show the Roman numeral as numeral + "/bass" (e.g. *Bb/C · VII/C*). Provisional notation; revisit if it reads badly.
- Diminished 7ths are named from the bass note (symmetrical chord): B–D–F–G# with B lowest reads *Bdim7 · ii°7*, not *vii°65*. The alternatives and typed correction cover it.
- Undo history only lasts while the app is open; projects save everything else.
- Ensemble edits: per-project player counts (SPEC §4 "counts editable per project") are covered by the Forces
  slider and Parts… on/off (both saved in the project). Exact counts per instrument aren't built (later).
- Generator speed: all three alternatives for 16 bars take about 2–3 s in the background. The test run is
  about 10 minutes on Windows (was 3:44), most of it the generator sweeps. If it gets slower, cache
  candidates per chord and share them between A/B/C, or move the heaviest sweeps behind a pytest marker.
- Allowed parallel warnings (never errors), all expected:
  - Follow input copies parallel 5ths or octaves between your clip's top and bass, and each one is
    reported once per pair of doubling parts.
  - Keep-as-is: model parts doubling your kept notes by pitch class aren't linked to them (only to your
    bass), so their parallels show.
  - C on test 12 (power chords) at Forces Solo or Density 3–4.
  - Melody against the bass: parallel octaves where your melody lands on chord roots while the bass moves by
    root (the bass voice sits in one octave, E2–Eb3, so its direction is often forced). With a bass file they
    come from your two files.
- Your own edits can break rules: a swap can give the choir a leap of more than an octave, and a kept
  voicing can have its own rule problems. The cells turn red, and generated output itself never has
  errors. Keep-as-is notes outside the strings' playable range (below E1) are kept and flagged red.
- Swaps link parts per chord (`Part.doubles_at`). Regenerating anything (all, a part, a chord) bakes swaps in: the alternative's
  "origin" is reset and swap_leap flags go away.
- "Regenerate this part" makes the part an independent line. A later *Regenerate unlocked* puts it back into its doubling role
  unless it is locked.
- Approach A sometimes puts two upper voices in unison (e.g. horns 3 and 4) - allowed and needed for power chords in the choir, but
  scored as a small cost. Tenor trombone 2 and bassoon 1 only play when there is an open 5th (root-position chords with a perfect 5th)
  and rest otherwise.
- Tuba is in the low octave except on E chords (E1 is below its comfortable F1), where it plays E2 with the cellos.
- Patterns (Sam, v0.5): "fairly generic, room for improvement". Milestone 7 added shapes, note modes, accent
  groupings and pattern alternatives; more textures (arpeggios, stabs, fills, pads under ostinatos,
  interlocking 16ths) are Milestone 8.
- Patterns are checked chord by chord; a pattern falls back to Sustain for a part at a chord where it would
  break a rule (16ths alternating does this on about 18% of chords). A Hybrid/Scale steps part first falls
  back to chord tones. Parallels inside patterns are reported (`pattern_parallels`, warnings) but not avoided
  by the safety net; pattern alternatives 2/3 pick, of 4 candidates, the one with the fewest.
- v1.1's 16ths alternating now shows some `pattern_parallels` warnings that were always there (Sam's call:
  report as warnings; the notes stay v1.1's).
- Low parts on shaped patterns in Hybrid/Scale steps (e.g. tuba on 8ths 3+3+2 lift) often fall back to chord
  tones or Sustain because steps in the low register break the low-interval limits. Expected; a per-role
  pattern choice could come with role overrides (Milestone 11).
- **Speed:** 16 bars with melody and bass files take about 5 s on Sam's PC (the v1.1 harmony search; v1.2 made
  it about 20% faster, patterns add nothing). Over SPEC §14's "about 4 s". The next step that would fix it is
  running A, B and C in parallel processes (about 2.5x; needs `multiprocessing.freeze_support()` in the
  packaged app) or sharing candidate checks between A/B/C.
- **Ear-test follow-ups for Milestone 8/9** (Sam, v1.2): patterns are too quiet to hear (unaccented notes at
  80% of mf; velocity shaping is Milestone 9); approach A's dense low register hides the rhythm; Scale steps
  and Hybrid under a melody can sound chaotic/clashing (a tighter clash rule or a default of Chord tones for
  parts near the melody's register); test 11 + files is a busy texture where patterns blur.
- Pattern alternatives only vary sections that play a pattern. With Sustain everywhere, patterns 2 and 3 are
  greyed out.
- Parts that play your melody or bass file keep the file's rhythm; section patterns don't apply to them.
- A melody plan that can't be voiced falls back quietly (same instrument without doubling, then the next
  instrument); the reason line says what was used. Example: approach A with an octave-up flute doubling
  over the low A woodwinds needed the melody spacing exemption (see Decisions).
- Problems only between your own inputs (kept voicing, locked parts, melody, bass file) are shown, not
  discarded, e.g. your kept voicing and your melody both on the leading tone (a doubled-outer warning).
- Bass-file mode: lines that can't play the file in any octave rest; the choir bass keeps the chord's bass
  only if singing the line would need a leap over an octave.
- *Generate* with unchanged settings and seed gives the same result by design; use *Regenerate unlocked*
  or another seed for new variations.
- Out of scope, noted for later:
  - Per-part role overrides beyond the melody instrument (SPEC §5 step 1: "you can override them"), and
    roles in presets. Sam chose melody-instrument only for Milestone 5.
  - Not yet built: keep-as-is in other sections (only strings for now) and the SSAATTBB choir layout.
  - Sam's v1.0 requests: choosing which instrument plays a pedal tone (test 9); an "override" to keep a melody
    in the choir when the rest of the choir can't sing around it. Hard choir rules are never broken by
    generated parts (SPEC §5a), so this needs a spec decision, e.g. letting the choir bass rest there.
- Ableton exports are now in the automated tests: the 10 benchmark files in `tests/data/benchmark/` are
  Sam's own clip exports (96 PPQ, type 0). The round trip into Ableton was checked by hand (v1.0).
- Benchmark files: Sam's originals sit in `benchmark/` (local, git-ignored); the copies the tests use are in
  `tests/data/benchmark/` as `Bnn.mid`, `Bnn.melody.mid`, `Bnn.bass.mid` plus `Bnn.expected.json` ("test":
  "Bn", "intended", per chord label/roman, or "unrecognized" + "correct_to"). New benchmark progressions:
  add them there, `tests/test_benchmark.py::test_ten_progressions_present` lists the expected names.
- Grid and piano-roll note names still use the key's spelling, so in B04 (E minor) the Bb · bV chord's
  notes show as A#. Phase 2: spell a chord's notes like its symbol.
- Chromatic roots other than the tritone keep the key's spelling table, which can disagree with the Roman
  numeral in sharp keys (D major: an Eb chord shows as *D# · bII*). Not in the benchmark; Phase 2 with the
  note-name item above.
- **Phase 2 ideas from the benchmark:** a larger chord vocabulary (m11, add11, m6/9, 6/9#11 — all of B08);
  the B01 melody against its chords suggests an optional check or hint when a melody file sits outside the
  key or chords (today: clash warnings only).
- `Documents\OrchSketch` is both the Git repo and where the app writes `Exports\`, `Projects\` and `logs\` (git-ignored). Still worth moving the repo to its own folder (e.g. `Documents\OrchSketch-dev`); the app's folders stay where they are.
- Bass file: basses, tuba and contrabassoon rest on file notes they can't reach an octave down (v1.0, Sam's
  choice), so in a low line (test 11 reaches C2) they drop out on a few notes; cellos, bass trombone and
  bassoon carry them.
- A melody in a choir voice in Safe mode often can't be voiced (the choir bass's comfortable range starts at
  G2); the message points to Character: Moderate, which works on tests 1, 4 and 11.
- Combined divisi files merge unisons between lines, so a combined file can have fewer notes than its lines
  together. Full-score tracks are all on MIDI channel 1, like the per-part files.
- The packaged app is a folder (`build\exe\dist\OrchSketch\`, zipped to `releases\OrchSketch-v1.0-win64.zip`,
  git-ignored), not one file: it opens in 1–2 s instead of 5–10 s (Sam's choice). Not code-signed: Windows
  SmartScreen may ask once.

## Decisions made during the build
<!-- Anything decided in a build chat that SPEC.md doesn't cover. Copy major ones into SPEC.md. -->
- **Range cross-check (Milestone 2, approved by Sam):** no copy of Adler was available, so each SPEC §4 value was checked against the Vienna Symphonic Library Academy instrument pages (main source), Andrew Hugill's *The Orchestra: A User's Manual*, and other published range references. Changed playable tops: English horn A5, contrabassoon C4, trumpet C6, bass trombone F5, violins I/II E7, choir soprano A5, choir bass C4. Everything else matched or SPEC was more conservative; comfortable ranges unchanged. The values are locked by `tests/test_instruments.py`.
- **Low-interval limits (Milestone 2, Claude's call as Sam deferred):** one limit per interval instead of SPEC's two-line rule, from the standard low-interval-limit chart (Berklee arranging; Sweetwater; US Navy harmony manual): lower note at least m2 E3, M2 Eb3, m3 C3, M3 Bb2, P4 A2, tritone Bb2, P5 Bb1, 6ths/7ths F2. Checked between adjacent distinct sounding pitches of the whole texture.
- **Severities (Milestone 2):** SPEC §7 table, except choir parallels = error, and in safe mode outside-comfortable = error. Spacing and doubled leading tone/7th stay warnings in the report, but the generator must never produce them (`generator_must_pass` in `rules.json`).
- **Defining tones:** every template tone, except the 5th of maj, m, 7, maj7, m7, add9, 9, m9 (as the labeller allows). So 6/m6 need the 6th, add9/9/m9 the 9th, sus the 2nd/4th, and dim/aug/m7b5/dim7/power the 5th. A slash bass outside the chord (Bb/C) must sound too.
- **Checker conventions:** "independent lines" = parts not linked by `Part.doubles` (followed through chains) or a shared `Part.group` (e.g. low-brass power chords); choir parallels are errors even between linked parts. "Outer voice" = highest/lowest sounding pitch of the whole texture at the chord start; a leading tone (only when it's in the chord) or chord 7th there is "doubled" when another, unlinked part plays the same pitch class. Spacing: within one section, gaps over an octave are allowed above the section's lowest note or above a part with role `bass`. Melody clash = exactly 1 semitone, overlapping in time.
- **Instrument data choices:** choir parts are separate instruments (`choir_soprano`...) named "Choir soprano" etc. so they don't clash with double basses; ids for strings are plural (`violins_1`, `basses`). Max divisi for winds = their default player count. Audition programs (GM, 0-based): string sections 48 (String Ensemble 1), choir 52 (Choir Aahs), bass clarinet 71 (clarinet), contrabassoon 70 (bassoon); recheck with GeneralUser GS in Milestone 3.
- **How builds happen (resolves SPEC §12 ".exe" item):** Claude edits files in `Documents\OrchSketch` through the linked folder. Claude's shell there is a Linux sandbox with no internet, and GitHub isn't linked to Claude. So every Windows step is a one-click script Sam runs: `setup.bat`, `run_tests.bat`, `run_app.bat`, `build_spike.bat`, `release.bat` (the last pushes with Sam's own Git login). Claude reads the logs these scripts write.
- **Minor key** = one setting that accepts both natural and harmonic minor chords (v and V, VII and vii°).
- **Test 8 and test 11 progressions** were written by Claude (see `tests/make_test_set.py`); Sam agreed to check them.
- **Grid snapping:** a note start more than 1/32 away from an 8th position is **rejected** with a message, not moved. Note ends snap to the nearest 8th (halves round up), so early releases never leave gaps.
- **Plain re-export** = the grid-snapped input notes as a type-0 MIDI file, 480 PPQ, 4/4, the tempo set in the app, starting at bar 1.
- **Labelling score:** template match minus missing/extra tones, plus bass role (root > 3rd > 5th > 7th > added tones), key fit and a small simplicity prior. Within a segment every pitch sounds for its full length, so SPEC's "duration weighting" has no effect in v1. The 5th may be omitted only in chords that have a 3rd and aren't 6/m6. A pedal favours "upper chord over the pedal".
- **Roman numeral conventions:** an added 6th is written *add6* (IIIadd6) so it isn't read as an inversion figure. Power and sus chords take the case of the diatonic triad on their root (*i5*, *VI5*, *IVsus2*). Inversions use 6/64 and 65/43/42.
- **FluidSynth opens its audio driver only, never a MIDI input driver**, so it can't take MIDI ports away from Ableton. WASAPI shared mode, default Windows output.
- **Versions:** FluidSynth 2.6.2 (official Windows x64 build), GeneralUser GS from its GitHub repo, PySide6 6.12, mido 1.3.3. The exact set is in `requirements.lock.txt`.
- **Release history fix (Milestone 3, approved by Sam):** `release.bat` was run before the docs were final and reused the
  previous `build\commit_msg.txt`, so the Milestone 3 code commit 52b60d3 is labelled "v0.2: Milestone 2". A follow-up docs
  commit was added and the v0.3 tag moved onto it (main's history not rewritten). `release.bat` now uses
  `build\commit_msg.txt` only if it starts with `vX.Y:` for the current version, and deletes it after committing.
- **App data folder:** errors are logged to `Documents\OrchSketch\logs\error_log.txt`.

- **Milestone 3 generator design:** abstract voices B (bass), L5 (open 5th above a root-position bass), h1–h4 (upper voices);
  each line in `generator.LINES_A` carries one voice, and per voice the first active line in priority strings > brass >
  woodwinds > choir is the primary, the rest `doubles` it. Bass and L5 lines share `group="low"`. The bass voice sits in
  E2–Eb3 (one octave, so octave doublings never switch direction); upper voices C3–F5, adjacent ones at most an octave apart.
  The leading tone / chord 7th may be in only one line family. Candidates are scored, checked one by one with the real checker
  (`check()` on a single chord), then a Viterbi search picks the path. Hard rules in the search: choir leaps ≤ an octave, no
  choir parallels. Parallels elsewhere cost 8 each (they are warnings, not `generator_must_pass`).
- **Milestone 3 defaults (approved by Sam):** fixed "full epic" line-up with section on/off toggles; one alternative built as
  approach A (low and warm); dynamics mf (velocity 80, CC1 80); forces = sections, divisi only to cover chord tones
  (Violins I a/b), horns as 4 lines; drag-out built now, Ableton drag test in Milestone 6.
- **Piccolo** rests in approach A (low and warm); trumpet 3 is not used yet. Approach C (high and bright) should use them.
- **Playback:** parts share a MIDI channel per GM program (11 programs in use, drum channel skipped); mute/solo filter notes per
  part; unisons on one channel are reference-counted. Generating again or changing a chord/key clears the result and stops playback.
- **SoundFont (SPEC §12 resolved):** GeneralUser GS v2.0.3 (official repo, Feb 2026), GeneralUser GS License v2.0: free use for own
  music, private or commercial, and in software projects; only caveat (sample provenance) concerns commercial software. Sam's
  sound check: all programs fine; Fast Strings 48 and Concert Choir 52 kept over Slow Strings 49 / Voice Oohs 53.
- **Export names:** `{clip file name}_{Part}_A.mid` until projects exist (Milestone 6); part codes are `Line.export`
  (Fl1, Hn1, Vln1-a, Cb, ChS...).

- **Milestone 4 decisions (Sam):** keep-as-is spreads the input over string lines, one note per line (not one polyphonic part).
  User edits that break a rule are kept and flagged red, with Ctrl+Z to undo. Forces and Density wait for Generate (the button
  turns orange); Dynamics applies at once. Locks are per alternative.
- **Milestone 4 decisions (Claude's calls):**
  - *Generate* keeps each tab's locked parts. *Regenerate unlocked* works on the current tab only, uses a
    new variation (seed "seed.variation") and is pushed away from the current notes.
  - A swap keeps locked parts. *Use own voicing* restores the unswapped original.
  - Swap leap flag: a leap of 8 or more semitones (more than a perfect 5th) that is bigger than before the
    swap (`swap_leap` in rules.json, `min_semitones`).
  - Follow input matches the clip's top note's pitch class, in the octave nearest to it inside the
    approach's window.
  - Low and heavy = violas, cellos, basses, tenor and bass trombones, tuba, contrabassoon, men's choir (T, B).
  - Forces Solo uses one player per instrument, with solo-string GM sounds 40–43 for audition. Divisi
    splits Violins II, violas and cellos (cellos b take the open 5th).
  - Density keeps the k most important lines per voice in the approach's lead order (k = 1, 2, 3, 5,
    all). The choir plays as a whole, and each section is kept without gaps.
  - A line written an octave up needs a same-section partner within an octave below, or it drops down.
  - Ensembles with fewer than three upper voices spread their upper lines over three voices.
- **Approach parameters** (generator.py `A`, `B`, `C`):
  - Upper-voice windows: A C3–F5, B C3–G5, C G3–C6.
  - Targets: centre, span, bass range; B adds a minimum span of 17, C a top pull.
  - Parallel cost: A 8 (as in Milestone 3), B and C 16.
  - Each approach has its own octave and rest table and lead order.

- **Milestone 5 decisions (Sam):** built-in presets carry patterns (Full epic: strings 8ths, tenor/bass
  trombones and tuba half-time; Low and heavy: strings 8ths, low brass stabs; the rest Sustain). Roles:
  only the melody instrument is choosable; full role overrides later. Melody doubling Auto + manual. Parts
  playing the bass file keep the file's rhythm.
- **Milestone 5 decisions (Claude's calls):**
  - *Patterns* (`patterns.py`): every pattern strikes at the chord start. Unaccented 8ths/16ths are at 80%
    velocity (8ths accented on beats 1 and 3, 16ths on every beat). Stabs are an 8th long, half-time hits a
    quarter. 16ths alternating uses the next chord tone at least a minor 3rd below (else above) and always
    ends on the part's own note. Choirs sing Sustain, 8ths, stabs or half-time only.
  - *Pattern priority:* part override > preset instrument pattern > section > master. Picking a section
    pattern clears that section's instrument and part patterns.
  - *Pattern safety net* (`generator._render`): per chord, compared with plain Sustain. A new problem →
    drop the passing tones → the named parts sustain → every patterned part sustains. A passing tone is
    also dropped where it adds parallels at the chord change.
  - *Moderate:*
    - Colour tones: a diatonic 9th, a 4th (not over a major 3rd) or a 6th, never on dim/aug/m7b5/dim7. At
      most one per chord, in one upper voice whose lines are all in moderate sections, never a semitone from
      another voice. `COLOUR_COST` 1.3 gives about 45% of chords.
    - Playable range only as a fallback when no comfortable octave exists (+0.5 cost per note, flagged
      yellow).
    - Passing tones only when a part moves by a 3rd, on the last 8th of the chord.
    - The checker runs in moderate mode when any section is moderate; safe sections still stay comfortable
      and on chord tones.
  - *Per-section sliders:* `Ensemble.section_forces/section_density` and `Settings.section_*` override the
    master. Section Density: lines kept as for the highest k, then a section with a lower k keeps its own k
    most important lines per voice (equal values = the old rule exactly). The UI sends no overrides when all
    sections are equal.
  - *Bass file:*
    - The line is moved by octaves so it best fits the bass window (E2–Eb3). Each bass line uses the first
      of its octaves that fits at least 2/3 of the notes, and notes outside its range move by an octave.
    - The bass trombone takes the lower octave first (SPEC).
    - The bass voice is pinned to the file's note at each chord start (a silent start is filled with the
      chord's bass note), and the open 5th may rest (cost 0.6).
    - The choir bass sings the line too (see Known issues).
    - Bassoon 2 and contrabassoon double it as well (they're on the bass voice).
  - *Melody:*
    - Host lists per approach are `generator.MELODY_HOSTS` (A horn, Violins I, clarinet…; B Violins I,
      horn, flute…; C flute, Violins I, trumpet…), at pitch first, then an octave down/up.
    - The melody replaces the host's top harmony line; a choir host needs no leaps over an octave; with
      keep-as-is the strings can't host.
    - Doubling hosts are `DOUBLE_HOSTS`; an octave-down doubling stays at G3 or above.
    - Up to 4 plans are tried (host ± doubling, next host).
    - Harmony above the melody's lowest note in a chord costs 0.3 per semitone, and the search counts
      parallels of every model line against the melody.
  - *Independent bass:* active only when every bass-voice section is moderate and there's no bass file. It
    places the chord's bass nearest the previous note in E2–Eb3; on chords of a half note or more, the last
    one or two diatonic steps toward the next bass (quarters on chords of a bar or more, else 8ths). If a
    chord can't be voiced with them, that chord holds the bass.
  - *Checker:* a part with role `melody` is left out of the within-section spacing rule (SPEC §5a), so a
    melody doubled high in the flutes over the other woodwinds is possible.
  - *Ownership:* the final gate treats issues only among fixed parts (kept voicing, locks, melody, bass
    file) as the user's (shown); everything else must be clean.
  - *Regenerate unlocked* avoids the current result and the 7 before it (`meta["previous"]`,
    `REGEN_MEMORY` 8), not just the last one (Sam saw it bounce between two).
  - Per-part CC1 = the part's section Dynamics (`Orchestration.cc1_for`); export writes it.
  - Melody export code `{Inst}-mel`, doubling `{Inst}-mel8va` / `-mel8vb`; line ids `mel` and `mel-8`.

- **Milestone 6 decisions (Sam):** packaged app as a folder build, not a single `.exe`. `slow` marker on the
  six biggest sweeps (run_tests.bat skips them, release.bat runs everything). Ear-test projects use the default
  preset (Full epic), safe, seed 1. Bass-file low lines rest instead of jumping. Note names on the piano roll.
- **Milestone 6 decisions (Claude's calls):**
  - *Project format:* one JSON object `{"format": "orchsketch-project", "format_version": 1, "app_version",
    "saved", "project": {...}}`. The project body mirrors the window's `EditState`. Alternatives are stored
    as the `Orchestration` objects themselves (tagged dataclasses, `project._CLASSES`), so a reopened
    alternative compares equal to the saved one. A new type in an orchestration must be added to
    `_CLASSES` (the encoder refuses unknown types). Saving writes a `.tmp` file first, then renames it.
  - *Unsaved changes:* the history step that was last saved is remembered, so undoing back to it counts as
    saved; a tempo change also counts. The save prompt appears only when there is an orchestration or a
    project file to lose (a freshly opened clip doesn't ask).
  - *Project name* = the `.osk` file's name, else the chord clip's. Export names use it.
  - *Export choice* (Parts / Full / Both, default Both) and *Combined divisi* (off) are app settings, not
    per project.
  - *Combined divisi files* exist for every instrument with two or more sounding lines (divisi, a2 winds,
    horns 1–4, a melody host with its harmony line), named `{Code}-all`. CC1 is the highest of its lines.
  - *Full score:* track 1 holds the name, 4/4 and tempo; then one track per sounding part in score order,
    named by the part's label.
  - *Test-set projects* are saved by the real window (driven off-screen), so they are exactly what the app saves.
- **v1.1 decisions (Claude's calls, Sam agreed):**
  - *Tritone chords:* a chord whose root is a tritone above the tonic reads #IV or bV, the root spelled to
    match (`analysis/chords.py`, `_chromatic_root`): fewest accidentals in the chord's own tones wins, a tie
    keeps the key's usual spelling (C major F# · #IV, C minor Gb · bV). A chord tone in the bass is spelled
    with the chord (Bb/D · bV6). Every other root is unchanged; generator output is unchanged.
  - *Benchmark out-of-vocabulary chords* stay in the benchmark as "unrecognized" + typed correction, which
    also covers the hand-correction path end to end.
  - *Roman numerals in minor* stay natural-minor degrees (III, VII), as in test 1; Sam writes bIII/bVII.
  - Slash labels follow the lowest note of the clip (B01 Ebadd9/G, B02 A/C#, B04 F/A, B07 Eb/Bb), as SPEC §3.
- **Line ending note:** `.bat` files must be CRLF (the build/test scripts check it).

- **Milestone 7 decisions (Sam):** Hybrid and Scale steps are allowed in Safe mode (the in-between notes are
  checked like any note: range, rules, clashes). Parallels inside patterns are reported as warnings, so v1.1's
  output stays identical. The Phase 2 plan was committed on its own first (`scripts\commit_docs.bat`). The
  ear-test set includes B10 besides B01. Pattern tabs are 1/2/3, exported as `_A2.mid`, `_A3.mid`.
- **Milestone 7 decisions (Claude's calls):**
  - *Pattern files* (`data/patterns/*.json`, one per pattern) and *accent groupings* (`data/accents.json`):
    format in `patterns.py`'s docstring. Positions are 16ths in the bar. A pattern's first note must be the
    anchor (the voiced pitch); `end_on_anchor` makes the chord's last note the anchor again, so chord-change
    rules see exactly the voicing (all new shaped patterns use it).
  - *Contour steps*: Chord tones = next chord tone (`min_step` semitones away at least; 16ths alternating
    uses 3, which is v1's rule); Scale steps = next note of the chord's scale; Hybrid = scale, but notes on a
    beat or an accent snap to the nearest chord tone (a tie goes the contour's way). A step that is out of
    range is mirrored, an octave shift too, else the anchor plays.
  - *Chord scale*: the key's natural scale with the chord's tones put in; a chord tone outside it replaces the
    neighbour it alters, by the key's spelling (sharp → the note below, flat → the note above).
  - *Accent groupings* restart every bar; on an 8th pattern, groups starting on an off-16th are skipped.
    "Short" groupings play off-accent notes at half length. Hits patterns (stabs, half-time, gallop, 3+3+2
    pulse) keep their own accents.
  - *Safety net levels* per part and chord: 3 note mode + passing tones, 2 note mode, 1 chord tones,
    0 Sustain (v1's 2/1/0 are 3/2/0). The loop runs until clean (v1 stopped after 4 rounds; every v1.1 case
    was clean by then, so output is unchanged). A Hybrid/Scale part whose scale notes clash a minor 2nd with
    the melody uses chord tones at that chord.
  - *Checker* `pattern_parallels`: consecutive common attacks of two parts inside one chord; once per pair and
    chord; parts on the same pitch classes at every common attack are one doubled line. Choir pairs report
    `choir_parallels` (error). The solver's candidate checks and the rendering's window checks run with
    `inside=False`, so the search and v1.1's output are unchanged.
  - *Pattern alternatives* (`pattern_alts.py`): per (section, pattern, accent) group of pattern 1, a seeded
    shuffle of the family's other (pattern, accent) options; pattern 2 takes option 1, pattern 3 option 2;
    4 candidates (attempts) rendered, fewest `parallels` + `pattern_parallels` wins. Note modes are never
    varied. Families: 8ths (8ths, 8ths rising, octave pulse, 3+3+2 lift, gallop), 16ths (16ths, alternating,
    rising, pendulum, broken, falling), pulse (stabs, half-time, 3+3+2 pulse), sustain (none).
  - *Window*: `self.alts` stay the harmony alternatives (pattern 1); `self.palts[tab]` holds patterns 2/3,
    built when first shown; `self.orch` is what is shown/played/exported, `self.harmony` what harmony edits
    use. A harmony edit re-applies the pattern choices (`pa.reapply`); a change to Pattern/Note mode/Accents/
    Dynamics works patterns 2/3 out again with the same variation, locked parts keeping their choices
    (`pa.refresh`). Pattern tab switches aren't undo steps (like harmony tab switches). The side panel now
    scrolls.
  - *Speed*: `_check_cached` remembers the rendering's window checks by content (40 000 entries, then
    cleared); `_Fixed` caches its per-chord lookups (`forget()` after the independent bass changes a
    figure); the melody-clash check skips melody notes with no note a semitone away.

## Notes for the next chat
- v1.2 (Milestone 7) is done. **Next: Milestone 8, v1.3 Textures and shapes** (SPEC §14). The research behind
  Phase 2 is the Claude Doc *OrchSketch Phase 2 — Ranked Feature Research*:
  https://claude.ai/artifact/3FppXiZGQNhVj13gn5DwZX
  - Milestone 8's arpeggios, stabs/anticipations and phrase-end fills are new pattern files and, where needed,
    new `kind`s in `patterns.py` (sustain/grid/hits today). Keep the rule that a pattern strikes its anchor
    at the chord start; anticipations (an 8th early) break it on purpose, so they need their own check path.
  - Intensity shapes change density/forces/pattern/dynamics per bar: density and forces are generation
    settings (not render-only), so shapes touch the solver, not only `_render`.
  - Guardrails: `tests/data/v11_patterns_snapshot.json` + the A and v0.4 snapshots must keep passing with
    every new option at its default; re-run `scripts\benchmark.bat` (now with the Phase 2 set and times) and
    log ratings.
  - Housekeeping (Milestone 11): move the repo out of `Documents\OrchSketch`.
- **Patterns** (v1.2): `patterns.py` (library, groupings, `make_mapper`, `render`), data in `data/patterns/` and
  `data/accents.json`, generator `_render` (levels, safety net), `pattern_alts.py` (pattern alternatives),
  checker `check_parallels_inside`. New Settings fields: `note_mode`, `section_note_modes`, `accent`,
  `section_accents`, `part_variants` (all render-only, in `RENDER_ONLY`).
- **Projects:** `project.py` + `MainWindow.to_project()` / `open_project()`. Any new window state that should
  persist needs a field in `EditState` and `project.Project` (same name); old files fill in its default.
- **Packaged app:** `scripts\build_exe.bat` (PyInstaller folder build; entry `scripts/orchsketch_main.py`).
  Data is found next to the package (`_internal\orchsketch\data`), FluidSynth and the SoundFont via
  `playback/fluid_env.py` (`_MEIPASS`). Check a build with `OrchSketch.exe --self-check`.
- **Test time:** `run_tests.bat` (not slow) is about 6 min on Windows; the full run is about 11 min. New big
  sweeps should get `@pytest.mark.slow`.
- **Data model:**
  - Each `Orchestration` has `cells` (pitch per line per chord) plus `meta`: "labels" (voice label per
    line per chord, used for the doubling links), "voices" (abstract voicing), "sources" (approach per
    chord), "origin" (the unswapped original), "fixed", "model", "free", "settings", "variation", and since
    Milestone 5 "figures" (rhythm of melody/bass-file lines per chord, relative to the cell pitch),
    "extras" (bass_pin, mel_lo, l5_optional for re-solving a chord), "info" (melody/bass text) and
    "previous" (earlier variations' cells, for Regenerate).
  - Rendering: `_finish` → `_render` (patterns, figures, per-section velocity, re-strike, safety net) →
    `build_parts(notes=...)` → full check. Render-only settings (`RENDER_ONLY`) change via `rerender()`.
  - Edits never change an orchestration in place; undo relies on that.
- **Test conventions:** `tests/test_generator.py` sweeps A (snapshot), B and C over every section
  combination, every preset and Forces × Density samples, so any new approach or option should pass the
  same sweeps. If A is ever changed on purpose, rerun `tests/make_a_snapshot.py` and say so in the changelog.
- The window's dialogs go through `MainWindow.notify` / `open_folder` / `show_menu` / `ask_text`, and the
  player goes through `player_factory`, so UI tests never open a popup or audio. Keep it that way. Tests
  set `run_async = False`, and `wait_for_generation()` waits for a background Generate.
- `tests/test_generator.py` sweeps every section combination; any new approach should pass the same sweep.
  `tests/test_motion.py` holds the Milestone 5 sweeps; if the defaults are ever changed on purpose, rerun
  `tests/make_v04_snapshot.py` (and `make_a_snapshot.py` for A) and say so in the changelog.
- Windows workflow: edit in the cloud workspace, pack a uniquely named `.tgz` into `_sync\`, unpack it in the linked folder, and
  copy over the files (deletes aren't allowed there, so `tar` can't overwrite; `cp` can). Ask Sam to run `scripts\run_tests.bat`
  and read `test_results.txt`. The linked folder must be `Documents\OrchSketch`. The Milestone 4 chat was linked to
  `Downloads\DocumentsDevOrchSketch` (an old copy) again and asked for `Documents\OrchSketch` with `device_request_folder_access`;
  check `get_device_info` first. Claude's workspace can run the whole suite (pip install mido pytest PySide6==6.12.*;
  QT_QPA_PLATFORM=offscreen), so iterate there and only sync when it's green.
- UI tests must never open a real popup or dialog (they block offscreen). Route them through replaceable methods like `MainWindow.show_menu`.
