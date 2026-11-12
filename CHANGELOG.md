# Changelog

All notable changes to OrchSketch. Versions follow the milestones in SPEC.md §10.

## v0.5 — Motion (Milestone 5) — 2026-11-11

### Added
- **Rhythm patterns** (SPEC §5c, new `patterns.py`), applied after the voicings are chosen, so the pitches at
  every chord change stay the same:
  - The patterns are Sustain, 8th ostinato (accents on 1 and 3; the other notes at 80% velocity), 16th
    ostinato (accent on every beat), 16ths alternating (the part's note with the next chord tone below,
    always ending on its own note), Brass stabs (8th-note hits on 1 and the "and" of 2) and Half-time pulse
    (quarter-note hits on 1 and 3). Every pattern strikes at each chord change.
  - Patterns are set per section in the side panel, and per part from the right-click menu (*Pattern ▸*).
    A choir sings Sustain, 8ths, stabs or half-time.
  - Patterns apply at once, like Dynamics, without regenerating. The grid shows the pattern next to each
    part's name and a ♪ on cells with more than one note.
  - Safety net: each chord is re-checked against plain Sustain. Where a pattern would add a rule problem, it
    first loses its passing tones, then the parts named in the problem fall back to Sustain for that chord.
    Generated output still has 0 errors.
  - **Re-strike every bar** toggle: held Sustain notes re-strike at each bar line instead of tying.
- **Melody and bass slots** in the top bar. Open or drop a monophonic clip; × removes it.
  - **Bass file:** every bass-line part (cellos, basses, bassoon 2, contrabassoon, bass trombone, tuba)
    plays it with its own rhythm, in octaves. Cellos play it at the bass register; basses, tuba and
    contrabassoon an octave lower where their range allows, and a note below an instrument's range moves up
    an octave. The bass trombone takes the lower octave when it fits. The choir bass keeps singing the chord's
    bass note. The open 5th may rest where the file moves.
  - **Melody file:** played exactly as written by one instrument, picked by register for each alternative:
    A tries the horns first, B Violins I, C the flute, each with fallbacks. You can also pick the instrument
    yourself (*Melody: …*). It replaces that instrument's top line; the instrument's other players stay on
    harmony.
  - The harmony is voiced around the melody: it prefers to stay below it, and the search avoids parallels
    against it.
  - **Melody doubling:** Auto / Off / 8va / 8vb. Auto doubles at Density 4–5 (A an octave down, B and C an
    octave up). An octave-down doubling stays at G3 or above.
  - If a melody plan can't be voiced, the next one is tried: the same instrument without the doubling, then
    the next instrument.
- **Moderate mode** (the Character slider is unlocked):
  - Upper voices may take one colour tone per chord: a diatonic 9th, a sus 4th (never over a major 3rd) or
    an added 6th. It never sits a semitone from another voice, and there's none on diminished, augmented or
    half-diminished chords. About 45% of chords get one.
  - Parts may reach their playable range where no comfortable octave exists. Those notes are flagged yellow.
  - 8th and 16th ostinatos may end a chord on a diatonic passing tone toward the part's next note (only when
    it moves by a 3rd, and dropped wherever it would add parallels).
  - **Independent bass** (moderate only, no bass file): the bass moves by step toward the next chord's bass
    on chords of a half note or longer, with at most two passing notes. Every bass part plays it, the choir
    bass included.
- **Per-section sliders** (SPEC §6): the side panel's *Set* box picks All sections or one section.
  - Character, Forces, Density, Dynamics and Pattern can each differ per section; *All* moves every section.
  - Equal values everywhere give exactly the master-slider results.
  - Section Density thins only that section, keeping its most important line on each voice.
  - Velocity and the constant CC1 are now per part, from its section's Dynamics, and export writes each
    part's own CC1.
- **Presets** now carry patterns (per section or per instrument), Character and per-section slider values,
  and your saved presets keep them.
  - Full epic: strings on 8th ostinato, tenor and bass trombones and tuba on Half-time pulse.
  - Low and heavy: strings on 8ths, low brass on stabs.
  - The other presets stay on Sustain.
- The reason line names the melody instrument and its doubling, the bass file or independent bass, and the
  colour chords.
- Undo/redo covers every new control: slots, patterns (section and part), per-section sliders, Character,
  doubling, melody instrument, independent bass and re-strike.
- Tests:
  - `tests/test_motion.py`, plus a new `tests/data/v04_snapshot.json`. It holds every note (pitch, rhythm,
    velocity) of A, B and C at v0.4 for all 12 files × presets × Forces/Density samples, and the defaults
    must still match it exactly.
  - Sweeps: every pattern in every section and approach, moderate mode, mixed per-section sliders, and
    melody + bass on tests 1, 4 and 11 across seeds, every preset, A/B/C and Forces × Density.
  - Also: keep-as-is with melody and bass, a walking-bass stress file with passing tones, the independent
    bass, edits with files and patterns, and the new window controls.

### Changed
- Checker: a melody part no longer counts for the within-section spacing rule. A flute doubling the melody
  an octave above the other woodwinds is standard epic writing, and this rule is about a section's chord.
- Checker speed: the time slices are built in one sweep, so 16th patterns over 16 bars check quickly.
- Problems only between your own inputs (kept voicing, locked parts, melody and bass files) are shown, not
  discarded. Everything the generator adds is still clean.
- **Regenerate unlocked** avoids the current result and the 7 variations before it, not just the last one. On
  short progressions it used to bounce between two results (found by Sam).
- The test run takes about 10 minutes on Windows (was 3:44) because of the new sweeps (about 410 tests).
- `swap_leaps` moved into `generator.py` (`edits.py` re-exports it); `with_dynamics` now re-renders through
  the new `rerender()`.

## v0.4 — Control (Milestone 4) — 2026-11-11

### Added
- **Three alternatives** (tabs A / B / C, Ctrl+1/2/3), each with its own one-line reason. Generate builds all
  three from the seed in the background, so the window stays responsive (about 2 s for 16 bars).
  - A, low and warm: unchanged. It gives exactly the v0.3 notes at the default settings
    (`tests/data/a_v03_snapshot.json`).
  - B, wide and full: the widest span. Violins I in octaves on top, flutes and piccolo an octave up, horns in
    the middle, basses, tuba and contrabassoon an octave down, open 5ths in the low brass.
  - C, high and bright: higher upper voices led by violins, flutes, piccolo, oboes and trumpets 1–3, horns in
    the middle, and a light bass (no tuba, contrabassoon or open 5ths).
- **Lock and regenerate**:
  - An L button on every row; locks are per alternative.
  - *Regenerate unlocked* (Ctrl+R) makes a new variation that is pushed away from the current one. Locked
    parts keep their notes exactly, and Generate keeps them too.
  - Right-click a part for *Regenerate this part only*. It gets its own new line with the same rhythm and
    never changes the chord's bass note.
  - Click a chord header for *Regenerate this chord*.
- **Per-chord and per-bar swap**: from the chord header, *Use B's / C's voicing for this chord / this bar*,
  and *back to own*. The header shows the source ("Am · B"). The checker re-runs on the result, and leaps
  the swap made bigger (8+ semitones) are flagged as the new `swap_leap` warning on the neighbouring chords.
  Your edits are kept even when they break a rule: the cells turn red or orange, and the reason is in the
  tooltip and the details panel.
- **Undo/redo** (Ctrl+Z / Ctrl+Y, plus buttons) for every edit: corrections, the key, presets and parts,
  sliders, top voice, keep-as-is, seed, locks, swaps, Generate and every regeneration.
- **Top voice**: *smooth* (as before) or *follow input*, where the top voice takes your clip's top note in
  the nearest octave the approach allows, falling back to smooth where it can't.
- **Keep-as-is**: *Keep my voicing (strings)* keeps your input voicing exactly as written, spread over the
  string lines low to high (Basses / Cellos / Violas / Violins II / Violins I, divisi as needed, one file per
  line). Everything else is orchestrated around it, and model parts that double your bass are linked to it.
- **Global sliders**:
  - Character is shown locked at Safe until Milestone 5.
  - Forces: Solo (one player per instrument, solo strings auditioned with GM solo sounds), Section, or
    Divisi (Violins II, violas and cellos split).
  - Density 1–5: the most important lines per voice, each section kept without gaps, the choir all or
    nothing.
  - Dynamics pp–ff: velocity and CC1 30/50/65/80/100/120. It applies at once; Forces and Density take
    effect at the next Generate, and the button turns orange.
- **Presets** (`data/presets.json`), replacing the section checkboxes: Strings only, Strings + horns,
  Brass + choir, Full epic, Woodwinds + strings (soft), Low and heavy. *Parts…* turns single instruments on
  or off; *Save preset…* writes your own to `Documents\OrchSketch\Presets\`.
- Exports are named after the tab: `{clip}_{Part}_A/B/C.mid`.
- New modules: `edits.py` (lock/regenerate/swap, pure), `history.py` (undo), `presets.py`.
- Tests:
  - B and C on all 12 files × seeds 1–3 × all 15 section combinations, with zero issues.
  - Every preset × A/B/C, and Forces × Density samples.
  - Follow input and keep-as-is on every file.
  - Edits, undo, presets, and the new window features off-screen, including background Generate.
  - 322 tests in total.

### Changed
- Generator refactor: one master line list, and approaches as data (voices, octaves, targets, lead
  order). Doubling links are rebuilt from the notes: a line doubles another where it plays the same voice
  on the same pitch class.
- Checker: parts can carry per-chord links (`Part.doubles_at`), so a swapped chord no longer makes every
  doubling in the piece count as independent parallels.
- Speed: the voice-leading search uses lookup tables, a one-chord fast path builds the checker parts, and
  key name tables are cached. One alternative on 16 bars went from 1.9 s to about 0.6 s.
- The test run takes about 3 minutes (was 1:40) because of the larger sweeps.

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
