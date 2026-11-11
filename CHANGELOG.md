# Changelog

All notable changes to OrchSketch. Versions follow the milestones in SPEC.md §10.

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
