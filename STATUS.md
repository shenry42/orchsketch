# OrchSketch — Status

> Read this first in every build chat, together with SPEC.md.
> The chat that finishes a milestone updates this file before it ends.

## Current state
- **Version:** v0.3
- **Last milestone completed:** 3 — First orchestration
- **Next milestone:** 4 — Control (SPEC.md §10)
- **Repo:** https://github.com/shenry42/orchsketch
- **Last updated:** 2026-11-11

## Milestones
- [x] 1 — v0.1 Read and label (+ packaging spike, audio test with Ableton open)
- [x] 2 — v0.2 Data and checker (range + low-interval tables cross-checked)
- [x] 3 — v0.3 First orchestration (safe mode, grid, playback, per-part export)
- [ ] 4 — v0.4 Control (A/B/C alternatives, lock, swap, undo, global sliders, presets)
- [ ] 5 — v0.5 Motion (patterns, bass, melody, moderate mode, per-section sliders)
- [ ] 6 — v1.0 Finish (projects, full export, .exe, full test-set pass, Ableton check)

## Test results (latest run)
- Automated tests: 259 passed / 0 failed (Windows, Python 3.12.10, `scripts\run_tests.bat`, 100 s)
- Chord labels on 12-file test set: 12/12 correct, every chord as the best guess (not just among alternatives).
  Also stable under 60 random re-voicings per chord (spread, doubled, bass in octaves 1–3).
- Checker errors in generated output: **0**. All 12 test files × seeds 1–8 in full epic, plus every one of the 15
  section combinations: 276 runs, 0 errors, 0 warnings of any kind (not even parallels). Checker on hand-made examples: 14/14.
- Ear-test ratings: see tests/ratings.csv (avg score: —). Formal ear test is with all three alternatives (Milestone 4+).
- Milestone 3 manual checks (Sam, 2026-11-11):
  - Sound check (`scripts\sound_check.bat`, 22 instruments + string/choir alternatives): all fine, current GM programs kept.
  - App (test 1, A minor): confirm, generate (31 parts, checker clean), playback with loop/tempo/mute/solo, piano roll,
    section toggles, Export parts: pass. Drag into Ableton: optional now, formally checked in Milestone 6.
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
- Generator speed: up to ~2 s for 16 bars on the build machine; the generator tests take ~90 s of the test run. Fine for now; if
  Milestone 4's three alternatives make Generate feel slow, cache candidates per chord and share them between A/B/C.
- Approach A sometimes puts two upper voices in unison (e.g. horns 3 and 4) - allowed and needed for power chords in the choir, but
  scored as a small cost. Tenor trombone 2 and bassoon 1 only play when there is an open 5th (root-position chords with a perfect 5th)
  and rest otherwise.
- Tuba is in the low octave except on E chords (E1 is below its comfortable F1), where it plays E2 with the cellos.
- Out of scope, noted for later: A/B/C tabs, lock, regenerate one part/chord, swap, undo, top-voice option, keep-as-is, sliders,
  presets (Milestone 4); rhythm patterns, re-strike-every-bar toggle, melody/bass slots, moderate mode (Milestone 5); combined
  divisi file, full-score type-1 file, projects (Milestone 6).
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

## Notes for the next chat
- Milestone 4: add approaches B (wide and full) and C (high and bright) as new line tables + scoring targets next to `LINES_A` /
  `_vertical_cost` in `generator.py`, and tabs A/B/C in the window. `generate()` already takes `seed` and an `Ensemble`;
  presets will replace the section checkboxes. Lock/regenerate can reuse the per-chord candidate lists (`_candidates`) and
  Viterbi with locked lines fixed.
- The window's dialogs go through `MainWindow.notify` / `open_folder` / `show_menu` and the player through
  `player_factory`, so UI tests never open a popup or audio. Keep it that way.
- `tests/test_generator.py` sweeps every section combination; any new approach should pass the same sweep.
- Windows workflow: edit in the cloud workspace, pack a uniquely named `.tgz` into `_sync\`, unpack it in the linked folder, and
  copy over the files (deletes aren't allowed there, so `tar` can't overwrite; `cp` can). Ask Sam to run `scripts\run_tests.bat`
  and read `test_results.txt`. The linked folder must be `Documents\OrchSketch` (one chat was linked to an old
  Downloads copy by mistake; check `get_device_info` first).
- UI tests must never open a real popup or dialog (they block offscreen). Route them through replaceable methods like `MainWindow.show_menu`.
