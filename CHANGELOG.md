# Changelog

All notable changes to OrchSketch. Versions follow the milestones in SPEC.md §10.

## v0.3 — First orchestration (Milestone 3) — 2026-11-11

### Added
- **Generator** (`generator.py`, no UI code): orchestrates the confirmed chords in safe mode (labelled chord
  tones only, comfortable range only) as approach A, "low and warm": a close mid-register chord in four upper
  voices (strings with Violins I divisi, horns, upper woodwinds and choir doubling at the unison), the bass in
  octaves (cellos, basses, bassoon, contrabassoon, bass trombone, tuba, choir bass) and open 5ths in low brass and
  bassoon under root-position chords. Every candidate voicing is checked by the rule checker on its own, then a
  seeded voice-leading search picks one per chord (common tones held, small steps, smooth top voice, contrary
  motion, parallels avoided; choir leaps over an octave and choir parallels never allowed). The final result is
  checked again and is only returned with no errors and no `generator_must_pass` warnings. Same chords, key,
  sections and seed always give the same result.
- Notes sustain for the chord's length; a note common to two consecutive identical chords is tied through.
- Section toggles (woodwinds, brass, strings, choir) and a seed field until presets and sliders arrive (Milestone 4).
  Dynamics fixed at mf: velocity 80 and CC1 80.
- **Grid**: one row per part, one column per chord (width follows the chord's length), notes in Ableton or
  scientific names, "~" for a note held from the previous identical chord, yellow = outside comfortable range,
  red = rule error. Each row has mute, solo and a drag handle. Checker summary and the one-line reason underneath.
- **Piano-roll preview** of the selected part, with a playhead.
- **Playback** (`playback/player.py`): FluidSynth + GeneralUser GS through WASAPI shared mode, play/stop, loop,
  live tempo, mute and solo per part and per section. Parts share one MIDI channel per GM program.
- **Per-part export** (`export.py`): one type-0 file per part line (divisi lines separate), concert pitch,
  480 PPQ, 4/4, tempo, CC1 80 at the start, bar 1 with no lead-in, the clip's full length. Named
  `{Project}_{Part}_A.mid` in `Documents\OrchSketch\Exports\{Project}\`. "Export parts" saves them all;
  dragging a row handle or "All" drags the files out (into Ableton).
- `scripts\sound_check.bat`: plays every audition sound for a quick ear check.
- Tests: the generator on all 12 test files (several seeds, all 15 section combinations), export round trip,
  playback logic with a silent backend, and the new window features off-screen.

### Changed
- Setup now also saves the GeneralUser GS licence (`vendor\soundfonts\LICENSE.txt`).
- File menu: "Export MIDI" is now "Re-export input clip" (Ctrl+Shift+E); Ctrl+E exports the parts.

## v0.2 — Data and checker (Milestone 2) — 2026-11-11

### Added
- **Instrument data** (`src/orchsketch/data/instruments/*.json`, loader `instruments.py`): the 22 SPEC §4 parts
  with playable and comfortable ranges (sounding pitch), default count, maximum divisi, GM program for audition,
  role list and timbre notes per register. Files are validated on load (comfortable inside playable, known
  section/roles, file name = id) with messages that name the file and field.
- **Rules data** (`src/orchsketch/data/rules.json`, loader `rules.py`): per-interval low-interval limits,
  spacing and choir-leap limits, melody-clash interval, and the severity of every check (plus which ones the
  generator must always pass).
- **Rule checker** (`checker.py`): runs on plain note lists, no UI. Checks playable and comfortable range,
  defining chord tones, low-interval limits across the whole texture, spacing within a section, choir crossing,
  choir leaps, parallel 5ths/8ves (between independent lines; always within the choir), doubled leading tone or
  7th in an outer voice, and melody minor-2nd clashes. Results list each problem by part, chord and position.
  Parts can be marked as doubling another part or as sharing a group, so intended doublings aren't flagged.
- `theory.parse_pitch` ("Bb1" -> 34).
- **Hand-made examples** (`tests/checker_examples.py`): one case per check, a clean C -> G texture and choir, and
  two clean full orchestrations (test 1 and test 4).
- `scripts/checker_report.bat`: runs the checker on the examples and writes `checker_report.txt`.

### Changed (approved by Sam, range cross-check)
- Playable tops: English horn C6 -> A5, contrabassoon F3 -> C4, trumpet D6 -> C6, bass trombone Bb4 -> F5,
  violins I and II A7 -> E7, choir soprano C6 -> A5, choir bass E4 -> C4.
- Low-interval limits: SPEC's two-line rule is replaced by one limit per interval (m2 E3, M2 Eb3, m3 C3, M3 Bb2,
  P4 A2, tritone Bb2, P5 Bb1, 6ths and 7ths F2).
- Severities: choir parallels are errors; in safe mode a note outside comfortable range is an error.

## v0.1 — Read and label (Milestone 1) — 2026-11-11

### Added
- **MIDI input** (`midi_io`): Standard MIDI type 0/1 at any PPQ, normalised to 480 PPQ. Notes snap to the
  8th-note grid within a 1/32-note tolerance (slight overlaps and early releases never split a chord).
  Clear rejection messages for: off-grid starts, time signatures other than 4/4, clips over 16 bars,
  type 2 / SMPTE files, empty or unreadable files. Monophonic melody/bass reader (rejects two notes at once,
  trims legato overlaps).
- **Chord segmentation**: a new chord wherever the set of sounding pitches changes on the 8th grid; the same
  chord struck again stays one segment; gaps become rests; held lowest notes across 2+ changes are marked as pedals.
- **Chord labelling**: full v1 vocabulary (maj, m, dim, aug, sus2, sus4, 5, 6, m6, 7, maj7, m7, m7b5, dim7, add9,
  9, m9) by template matching weighted by bass note and key; slash chords; upper structures over a pedal;
  best guess plus up to 3 ranked alternatives; "not recognized" when nothing fits exactly.
- **Roman numerals** with inversion figures (6, 64, 65, 43, 42), quality marks (°, +, ø) and accidentals for
  borrowed/chromatic chords (bVI, iv in major). Minor keys accept natural and harmonic-minor chords.
- **Corrections**: pick an alternative or type a chord symbol (common aliases accepted); confirm one or all;
  revert. Key changes keep corrections. Only confirmed labels are exposed to the generator.
- **Plain re-export**: the grid-snapped input as a type-0 MIDI file at 480 PPQ starting at bar 1, with tempo and 4/4.
- **Minimal window** (PySide6, dark theme): open or drop a file, key/mode/tempo, chord strip with
  symbol · Roman numeral · length · pedal mark, chord details with notes in Ableton or scientific names,
  Confirm all, Export MIDI. Unexpected errors are logged to `Documents\OrchSketch\logs\error_log.txt`.
- **Test set**: 12 generated progressions (SPEC §8) with hand-written expected labels, plus melody and bass
  files for tests 1, 4 and 11 (`tests/make_test_set.py`).
- **Automated tests** (pytest): MIDI reading and writing, segmentation, labels, symbols, session, the 12-file test set,
  a seeded randomised re-voicing check, a music21 root cross-check, and an off-screen UI smoke test.
- **Audio spike**: `OrchSketchAudioSpike.exe` (PyInstaller, FluidSynth 2.6.2 + GeneralUser GS inside) plays
  through WASAPI shared mode.
- **Scripts**: `setup.bat`, `run_app.bat`, `run_tests.bat`, `build_spike.bat`, `release.bat`, `check_prereqs.bat`.
