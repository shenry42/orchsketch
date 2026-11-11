# Changelog

All notable changes to OrchSketch. Versions follow the milestones in SPEC.md §10.

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
