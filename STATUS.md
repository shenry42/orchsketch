# OrchSketch — Status

> Read this first in every build chat, together with SPEC.md.
> The chat that finishes a milestone updates this file before it ends.

## Current state
- **Version:** v0.2
- **Last milestone completed:** 2 — Data and checker
- **Next milestone:** 3 — First orchestration (SPEC.md §10)
- **Repo:** https://github.com/shenry42/orchsketch
- **Last updated:** 2026-11-11

## Milestones
- [x] 1 — v0.1 Read and label (+ packaging spike, audio test with Ableton open)
- [x] 2 — v0.2 Data and checker (range + low-interval tables cross-checked)
- [ ] 3 — v0.3 First orchestration (safe mode, grid, playback, per-part export)
- [ ] 4 — v0.4 Control (A/B/C alternatives, lock, swap, undo, global sliders, presets)
- [ ] 5 — v0.5 Motion (patterns, bass, melody, moderate mode, per-section sliders)
- [ ] 6 — v1.0 Finish (projects, full export, .exe, full test-set pass, Ableton check)

## Test results (latest run)
- Automated tests: 207 passed / 0 failed (Windows, Python 3.12.10, `scripts\run_tests.bat`)
- Chord labels on 12-file test set: 12/12 correct, every chord as the best guess (not just among alternatives).
  Also stable under 60 random re-voicings per chord (spread, doubled, bass in octaves 1–3).
- Checker errors in generated output: — (no generator yet). Checker on hand-made examples: 14/14 cases as expected, 2 clean orchestrations clean (`scripts\checker_report.bat`).
- Ear-test ratings: see tests/ratings.csv (avg score: —) (no orchestrations yet)
- Milestone 1 manual checks (Sam, 2026-11-11):
  - Packaged `.exe` played FluidSynth through WASAPI shared mode **while Ableton was playing on ASIO** (Focusrite): pass.
  - Ableton round trip (own clip → OrchSketch → export → drag into Arrangement): starts on the bar line, same length, same notes: pass.
  - App: load, labels, correction, confirm all: pass (after the click fix below).

## Known issues
- Checker: melodic checks (leaps, parallels) follow each part's top note, so the generator must give every divisi line its own part (which also matches per-line export). Parallels are checked only at chord changes, not inside rhythm patterns.
- Checker: low-interval limits cover simple intervals only. Compound intervals (9ths, 10ths...) have no limit; revisit if wide low voicings sound muddy.
- `src/orchsketch/data/` (JSON) must be bundled into the `.exe` in Milestone 6 (PyInstaller `--add-data`); the loaders read it from next to the package.
- Chords over a non-chord bass show the Roman numeral as numeral + "/bass" (e.g. *Bb/C · VII/C*). Provisional notation; revisit if it reads badly.
- Diminished 7ths are named from the bass note (symmetrical chord): B–D–F–G# with B lowest reads *Bdim7 · ii°7*, not *vii°65*. The alternatives and typed correction cover it.
- Corrections only last while the app is open. Saving them is part of projects (Milestone 6).
- Melody and bass files: the reader exists and is tested, but there are no UI slots yet. They are first used in Milestone 5.
- Sam's real Ableton export isn't in the automated tests yet (the round trip was checked by hand). Add one Ableton-exported `.mid` to `tests/data/ableton/` when convenient.
- `Documents\OrchSketch` is both the Git repo and where the app writes `Exports\`, `Projects\` and `logs\` (git-ignored). Consider moving the repo to its own folder before v1.0.

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
- **App data folder:** errors are logged to `Documents\OrchSketch\logs\error_log.txt`.

## Notes for the next chat
- Milestone 3: build the generator on `instruments.instruments()`, `rules.rules()` and `checker.check(parts, chords, key, mode)`; get chords with `checker.chords_from_session(session)`. Discard any candidate whose report has errors or a `generator_must_pass` warning. Mark doublings with `Part.doubles` / `Part.group`, and give each divisi line its own `Part`.
- `tests/checker_examples.py` has two clean full orchestrations (test 1, test 4) that are good references for safe-mode voicing.
- SPEC.md edits for Sam to make in the main doc are listed in the Milestone 2 chat summary (ranges table, low-interval rule, severities, defining tones).
- Windows workflow: edit in the cloud workspace, pack a uniquely named `.tgz` into `_sync\`, unpack it in the linked folder, and copy over the files (deletes aren't allowed there, so `tar` can't overwrite; `cp` can). Ask Sam to run `scripts\run_tests.bat` and read `test_results.txt`.
- UI tests must never open a real popup or dialog (they block offscreen). Route them through replaceable methods like `MainWindow.show_menu`.
