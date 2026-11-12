# OrchSketch — Status

> Read this first in every build chat, together with SPEC.md.
> The chat that finishes a milestone updates this file before it ends.

## Current state
- **Version:** v0.4
- **Last milestone completed:** 4 — Control
- **Next milestone:** 5 — Motion (SPEC.md §10)
- **Repo:** https://github.com/shenry42/orchsketch
- **Last updated:** 2026-11-11 (Milestone 4)

## Milestones
- [x] 1 — v0.1 Read and label (+ packaging spike, audio test with Ableton open)
- [x] 2 — v0.2 Data and checker (range + low-interval tables cross-checked)
- [x] 3 — v0.3 First orchestration (safe mode, grid, playback, per-part export)
- [x] 4 — v0.4 Control (A/B/C alternatives, lock, swap, undo, global sliders, presets)
- [ ] 5 — v0.5 Motion (patterns, bass, melody, moderate mode, per-section sliders)
- [ ] 6 — v1.0 Finish (projects, full export, .exe, full test-set pass, Ableton check)

## Test results (latest run)
- Automated tests: 322 passed / 0 failed (Claude's Linux workspace, about 3 min; Windows run via `release.bat`).
- Chord labels on 12-file test set: 12/12 correct, every chord as the best guess (unchanged since Milestone 1).
- Checker errors in generated output: **0**.
  - Approach A gives exactly the v0.3 notes on all 216 Milestone 3 runs (12 files × seeds 1–3 plus all 15
    section combinations) and still has 0 warnings of any kind.
  - B and C: the same 432 runs, with 0 errors and 0 warnings.
  - Every preset × A/B/C × 12 files, Forces × Density samples, follow input and keep-as-is: 0 errors and 0
    `generator_must_pass` warnings (some allowed parallel warnings; see Known issues).
- Speed: all three alternatives for 16 bars take about 1.8 s in Claude's workspace (one took 1.9 s before
  Milestone 4) and run in the background.
- Ear-test ratings (tests/ratings.csv): test 1 A/B/C all 5/5 (Sam, v0.4: "a little basic/generic for now,
  room to grow"). The formal pass over all test files is in Milestone 6.
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
- Checker: melodic checks (leaps, parallels) follow each part's top note, so the generator must give every divisi line its own part (which also matches per-line export). Parallels are checked only at chord changes, not inside rhythm patterns.
- Checker: low-interval limits cover simple intervals only. Compound intervals (9ths, 10ths...) have no limit; revisit if wide low voicings sound muddy.
- `src/orchsketch/data/` (JSON) must be bundled into the `.exe` in Milestone 6 (PyInstaller `--add-data`); the loaders read it from next to the package.
- Chords over a non-chord bass show the Roman numeral as numeral + "/bass" (e.g. *Bb/C · VII/C*). Provisional notation; revisit if it reads badly.
- Diminished 7ths are named from the bass note (symmetrical chord): B–D–F–G# with B lowest reads *Bdim7 · ii°7*, not *vii°65*. The alternatives and typed correction cover it.
- Corrections only last while the app is open. Saving them is part of projects (Milestone 6).
- Melody and bass files: the reader exists and is tested, but there are no UI slots yet. They are first used in Milestone 5.
- Ensemble edits: per-project player counts (SPEC §4 "counts editable per project") are covered by the Forces slider and Parts…
  on/off for now; exact counts per instrument come with projects.
- Generator speed: all three alternatives for 16 bars take about 1.8 s in the background. The test run is about 3 minutes, most
  of it the generator sweeps. If it gets slower, cache candidates per chord and share them between A/B/C.
- Allowed parallel warnings (never errors), all expected:
  - Follow input copies parallel 5ths or octaves between your clip's top and bass, and each one is
    reported once per pair of doubling parts.
  - Keep-as-is: model parts doubling your kept notes by pitch class aren't linked to them (only to your
    bass), so their parallels show.
  - C on test 12 (power chords) at Forces Solo or Density 3–4.
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
- Out of scope, noted for later:
  - Milestone 5: rhythm patterns, the re-strike-every-bar toggle, melody/bass slots, moderate mode (the
    Character slider is shown locked at Safe), per-section sliders, per-part role overrides, and roles and
    patterns in presets.
  - Milestone 6: the combined divisi file, the full-score type-1 file, projects (they also save locks,
    swaps and corrections; undo history only lasts while the app is open).
  - Not yet built: keep-as-is in other sections (only strings for now) and the SSAATTBB choir layout.
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

## Notes for the next chat
- Milestone 5:
  - **Patterns:** they go after the path search (SPEC §5 step 5). The checker already follows each part's
    top note and checks parallels at chord changes only.
  - **Moderate mode:** it needs `_candidates` to allow 9ths, sus and 6ths in upper voices, and `generate()`
    to accept mode="moderate". The Character slider is already in the window, disabled.
  - **Per-section sliders:** they can feed `Ensemble` per section. Density and Forces are applied in
    `approach_lines()` / `ensemble_lines()`.
  - **Melody and bass slots:** a melody line can be added as a fixed part (`_Fixed`, the way keep-as-is
    and locks work).
- **Data model:**
  - Each `Orchestration` has `cells` (pitch per line per chord) plus `meta`: "labels" (voice label per
    line per chord, used for the doubling links), "voices" (abstract voicing), "sources" (approach per
    chord), "origin" (the unswapped original), "fixed", "model", "free", "settings" and "variation".
  - Edits never change an orchestration in place; undo relies on that.
- **Test conventions:** `tests/test_generator.py` sweeps A (snapshot), B and C over every section
  combination, every preset and Forces × Density samples, so any new approach or option should pass the
  same sweeps. If A is ever changed on purpose, rerun `tests/make_a_snapshot.py` and say so in the changelog.
- The window's dialogs go through `MainWindow.notify` / `open_folder` / `show_menu` / `ask_text`, and the
  player goes through `player_factory`, so UI tests never open a popup or audio. Keep it that way. Tests
  set `run_async = False`, and `wait_for_generation()` waits for a background Generate.
- `tests/test_generator.py` sweeps every section combination; any new approach should pass the same sweep.
- Windows workflow: edit in the cloud workspace, pack a uniquely named `.tgz` into `_sync\`, unpack it in the linked folder, and
  copy over the files (deletes aren't allowed there, so `tar` can't overwrite; `cp` can). Ask Sam to run `scripts\run_tests.bat`
  and read `test_results.txt`. The linked folder must be `Documents\OrchSketch`. The Milestone 4 chat was linked to
  `Downloads\DocumentsDevOrchSketch` (an old copy) again and asked for `Documents\OrchSketch` with `device_request_folder_access`;
  check `get_device_info` first. Claude's workspace can run the whole suite (pip install mido pytest PySide6==6.12.*;
  QT_QPA_PLATFORM=offscreen), so iterate there and only sync when it's green.
- UI tests must never open a real popup or dialog (they block offscreen). Route them through replaceable methods like `MainWindow.show_menu`.
