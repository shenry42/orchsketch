# Orchestral Composition Assistant — v1 Build Spec

Nov 12, 2026 · @Sam · updated after v1.1 (Phase 2 plan added, §14)

V1 is a standalone Windows app. It takes a block-chord MIDI file, labels the harmony, and generates 3 orchestrations for strings, brass, woodwinds and choir that stay in range and are rule-checked. You audition them with a light SoundFont and export them as MIDI to drag into Ableton. It is for personal use only. Accuracy beats novelty in v1.

## 1. Purpose and decisions

**V1 success criterion:** Load a real block-chord MIDI file (4 to 16 bars). The app labels every chord correctly, or offers the right label among its alternatives. It then produces 3 orchestrations that make musical sense. They have no notes outside comfortable range unless flagged, and no rule-checker errors. They can be auditioned in-app and exported as MIDI that drops into Ableton at the right position and pitch.

| Decision | V1 choice | Replaces in original overview |
| --- | --- | --- |
| Platform | Windows only, Sam's existing PC | — |
| Form | Standalone desktop app, packaged as a folder app (`OrchSketch.exe`, zipped for download). No VST3, no Max for Live | C++/JUCE VST3 |
| Input | MIDI file dragged or opened into the app | Clip capture or import |
| Output | MIDI files: one per instrument, one multi-track file, or both. Drag into Ableton or save to a folder | MIDI export |
| Ableton integration | None beyond drag-and-drop. Does not create tracks. Arrangement view use | Live track creation |
| Use case | Sketching from a chord progression | Composition and full arrangement |
| Style | Epic cinematic, modern orchestra leaning slightly hybrid | Traditional plus experimental |
| Intelligence | Deterministic music theory and orchestration rules only | Hybrid with AI |
| AI | Deferred in v1. Phase 2 adds an optional AI line writer (Claude API, online, button only); see §14 | Phase 4 |
| Network | Fully offline in v1. From Phase 2 only the optional AI line writer goes online | — |
| Builder | Claude writes all code. Sam tests, mostly inside the app | — |
| Backups | GitHub repo plus source zip per version, version numbers, changelog | Version control |
| Working name | OrchSketch (rename anytime) | — |

## 2. Workflow and input

A session is one straight run. Nothing round-trips through Ableton until export.

1. Export the chord clip from Ableton (right-click clip > Export MIDI Clip). Optionally export the melody and bass clips too.
2. Drag the chord file into the app. Optionally drop melody and bass files into their own slots.
3. Set key and mode (major or minor) and tempo.
4. Review chord labels. Fix any by picking an alternative or typing a chord.
5. Pick an ensemble preset and adjust sliders.
6. Generate. Compare 3 alternatives. Lock parts you like and regenerate the rest. Swap voicings per chord or per bar.
7. Audition with the built-in SoundFont: loop, tempo, mute and solo.
8. Export: drag parts into Ableton or save to a folder. Save the project to reopen later.

**Input rules (v1)**

- Format: Standard MIDI File, type 0 or 1. Ableton clip exports are the reference case.
- Chords file: one clip, block chords only, quantized to the grid, 4/4 time, up to 16 bars.
- Harmonic rhythm varies. A chord change is detected wherever the set of sounding pitches changes on a grid position. The smallest grid is an 8th note. Note starts and ends within a 1/32-note tolerance count as the same chord, so slight overlaps or early releases never split a chord in two.
- Melody and bass: separate optional files, monophonic. They must start at the same point as the chords file.
- Key: entered by you, never auto-detected in v1. Modes: major and natural/harmonic minor. Modal tagging comes later.
- No key changes, no tempo changes, no other time signatures.
- Tempo: entered by you (default 140 BPM). It affects playback and export only.
- Rejected with a clear message: overlapping non-block notes that cannot be grouped into chords, files longer than 16 bars, and time signatures other than 4/4.

## 3. Chord analysis

Each chord segment gets a best-guess label plus up to 3 ranked alternatives. You confirm or correct them, and generation only ever uses the confirmed label.

- **Chord vocabulary (v1):** major, minor, diminished, augmented, sus2, sus4, power chord (root and 5th), 6, m6, 7, maj7, m7, m7b5, dim7, add9, and 9/m9. Anything else is labeled "unrecognized" and must be set by hand.
- **Bass note:** the lowest sounding note. If it is not the root, the chord is shown as a slash chord (C/E).
- **Scoring:** template matching against pitch classes, weighted by the bass note, the key you entered, and note duration. Ties are listed as alternatives, for example Am7 vs C6 or a power chord with no 3rd.
- **Display:** chord symbol and Roman numeral together, e.g. *Am7 · i7* and *C/E · III6*. Borrowed and chromatic chords show their Roman numeral with an accidental (bVI, iv in major).
- **Pedal tones:** if the lowest note holds across several chord changes, it is marked as a pedal. The upper chords are labeled over it.
- **Correction:** click a chord, pick an alternative or type a symbol. Corrections are saved in the project.
- **Melody and bass files** (when present) are read for pitch and rhythm only. They do not change chord labels in v1.

## 4. Instruments and ranges

There are 22 instrument parts in v1, all exported at concert (sounding) pitch. In safe mode the generator writes only inside **comfortable** range. Moderate mode may reach **playable** range, but every such note is flagged yellow. Nothing is ever written outside playable range.

**Pitch naming:** this spec uses scientific pitch, where C4 = middle C = MIDI 60. Ableton calls middle C "C3", so subtract 1 from every octave below to get Ableton names. The app displays Ableton names by default, with a setting to switch. Example: a tuba should never go above C4 here, which Ableton shows as C3.

| Section | Instrument | Playable (sounding) | Comfortable (sounding) | Default count |
| --- | --- | --- | --- | --- |
| Woodwinds | Piccolo | D5–C8 | A5–A7 | 1 |
| Woodwinds | Flute | C4–C7 | E4–A6 | 2 |
| Woodwinds | Oboe | Bb3–A6 | D4–D6 | 2 |
| Woodwinds | English horn | E3–C6 | G3–G5 | 1 |
| Woodwinds | Clarinet (Bb) | D3–Bb6 | E3–C6 | 2 |
| Woodwinds | Bass clarinet | Bb1–F5 | D2–F4 | 1 |
| Woodwinds | Bassoon | Bb1–E5 | C2–Bb4 | 2 |
| Woodwinds | Contrabassoon | Bb0–F3 | D1–C3 | 1 |
| Brass | French horn | B1–F5 | F2–D5 | 4 |
| Brass | Trumpet (Bb) | E3–D6 | G3–G5 | 3 |
| Brass | Tenor trombone | E2–F5 | G2–Bb4 | 2 |
| Brass | Bass trombone | Bb0–Bb4 | C2–F4 | 1 |
| Brass | Tuba | D1–F4 | F1–C4 | 1 |
| Strings | Violins I | G3–A7 | G3–A6 | section |
| Strings | Violins II | G3–A7 | G3–E6 | section |
| Strings | Violas | C3–E6 | C3–G5 | section |
| Strings | Cellos | C2–A5 | C2–A4 | section |
| Strings | Double basses | E1–G4 | E1–D3 | section |
| Choir | Soprano | C4–C6 | E4–G5 | section |
| Choir | Alto | F3–F5 | A3–C5 | section |
| Choir | Tenor | C3–A4 | D3–F4 | section |
| Choir | Bass | E2–E4 | G2–C4 | section |

**Status of this table:** these are draft values from standard orchestration ranges. Milestone 2 cross-checks each one against an orchestration reference (Adler, *The Study of Orchestration*) before the generator relies on it, and any changes are logged.

**Parts and splitting**

- Every instrument can be solo, a2/a3 (several players on one line), or divisi.
- Max divisi: Violins I, Violins II, Violas and Cellos up to 3 lines each. Basses 2. Horns up to 4 lines, trumpets 3, tenor trombones 2.
- Choir can be SATB, or split into men (T, B) and women (S, A) sections, or SSAATTBB.
- Counts are defaults, editable per project. Presets set them.
- Each instrument record (JSON) holds: id, name, section, both ranges, MIDI program number for audition, maximum divisi, timbre notes per register (e.g. *horn: F3–F4 heroic*), and a role list (bass, harmony, melody, pad).

## 5. Generation rules

Generation works in three steps: assign roles, build candidate voicings that pass the hard rules, then rank them by soft rules and the sliders. The 3 alternatives each take a different approach so they never come out as near-copies. A is low and warm: dense low-mid register, led by horns and low strings. B is wide and full: the widest span, all sections, octave doublings. C is high and bright: led by upper strings, woodwinds and trumpets, with a lighter bass. The same inputs, settings and seed always give the same output.

**Pipeline**

1. **Roles.** Each active part gets one role for the passage: bass, low harmony, mid harmony, high harmony, melody, or pad. The preset sets the defaults. In v1 the only override is which instrument plays the melody; full per-part role overrides and roles in presets come later.
2. **Bass line.** If you supply a bass file, every part on the bass line doubles it in octaves, with the file's own rhythm: cellos at the bass register; basses, tuba and contrabassoon an octave lower where their range allows; bass trombone on the lower octave when it fits; bassoon 2 too. Basses, tuba and contrabassoon, doubling an octave below, rest on the notes they can't reach there, so they keep the line's shape. Other bass lines move such a note by an octave. A part that can't play the line in any octave rests. The choir bass sings the line as well, unless that would need a leap over an octave (then it keeps the chord's bass note). Without a bass file the bass parts follow the chord's bass note (the root, or the slash bass). A per-project toggle switches to an independent line that moves by step toward the next chord's bass: at most two diatonic passing notes, on chords of a half note or longer. This toggle is moderate mode only: it needs Character at Moderate for the sections playing the bass, and no bass file.
3. **Melody.** If you supply a melody file, it goes to one instrument chosen by register, with its own order per alternative: A tries the horns first, B Violins I, C the flute, each with fallbacks (at pitch first, then an octave away). You can also pick the instrument. The melody replaces that instrument's top line; its other players stay on harmony. With keep-as-is the melody stays out of the strings. Melody notes are fixed, and the harmony is voiced around them (kept below the melody where it can be). Octave doubling: Auto, Off, Octave up or Octave down. Auto doubles at Density 4–5 (A an octave down, B and C up); an octave-down doubling stays at G3 or above. If a melody plan can't be voiced, the next one is tried: the same instrument without the doubling, then the next instrument. A melody given to a choir voice counts as a choir voice for the choir rules. In Safe mode the rest of the choir may not fit around it, usually because the choir bass can't go low enough; the app then says so and suggests Character: Moderate, another instrument or Melody: auto.
4. **Voicing.** For each chord, candidate pitch sets are built inside each part's range. They are ranked by voice leading from the previous chord, spacing, doubling and slider weights.
5. **Pattern.** The chosen rhythm pattern is applied per part (section 5c).
6. **Check.** The rule checker runs (section 7). Any hard-rule failure discards the candidate. It is never shown and then flagged.

**5a. Hard rules (never broken, any mode)**

- No note outside playable range. In safe mode, no note outside comfortable range.
- Every chord's defining tones are present somewhere in the texture: root, 3rd (except power and sus chords), 7th when labeled. The 5th may be omitted.
- Low-interval limits, checked across the whole sounding texture rather than per section: no 3rds or 2nds between adjacent harmony voices below about C3, and no intervals smaller than a 5th below about Bb1. (The limits table goes in the rules data and is cross-checked in Milestone 2.)
- Spacing: within a section, adjacent upper voices are at most an octave apart. Wider gaps are allowed only between bass and tenor. A melody part is exempt: it is a line of its own, not part of the section's chord (so a melody doubled high in the flutes over the other woodwinds is allowed).
- Choir: no voice crossing, and each voice moves by at most an octave between chords.
- Never double the leading tone or the chord 7th in an exposed outer voice.

**5b. Soft rules (scored; slider-weighted)**

- Smooth voice leading: common tones held, other voices move by the smallest step. Contrary motion against the bass is preferred.
- Top voice: either (a) **smooth**, moving by the smallest step, or (b) **follow input**, matching your clip's top note. You choose per generation.
- Parallel 5ths and octaves are allowed when they come from doubling or a low-brass power-chord texture, both normal in epic writing. They are penalised between independent inner lines and banned within the choir.
- Epic traits: open 5ths and octaves in the low register, horns in their F3–F4 heroic zone for harmony, strings carrying the widest span, and the melody doubled at the octave as density rises.
- **Safe mode:** only the labeled chord tones are used.
- **Moderate mode:** 9ths, sus2/sus4 colour and added 6ths are allowed in upper voices, plus passing tones in patterns. Details:
  - At most one colour tone per chord, in one upper voice: a diatonic 9th, a 4th (never over a major 3rd) or a 6th. It never sits a semitone from another voice, and there is none on diminished, augmented or half-diminished chords. About 45% of chords get one.
  - Notes may reach playable range only where no comfortable octave exists (flagged yellow).
  - Passing tones only on the last 8th of a chord in 8th and 16th ostinatos, only where the part moves by a 3rd, and dropped wherever they would add parallels.

**5c. Rhythm patterns (v1)**

| Pattern | Typical parts | Behaviour |
| --- | --- | --- |
| Sustain | Any | Notes held for the chord's length |
| 8th ostinato | Strings, low brass | Repeated 8ths on chord tones, accented on beats 1 and 3 |
| 16th string ostinato | Violins, violas, cellos | Repeated 16ths, accented on every beat |
| 16ths alternating | Violins, violas, cellos | 16ths alternating the part's note with the next chord tone below, always ending on the part's own note |
| Brass stabs | Brass, low strings | Short hits (an 8th long) on chosen beats, default 1 and the "and" of 2 |
| Half-time pulse | Low brass, low strings, choir | Hits (a quarter long) on beats 1 and 3 |

- **Sustain behaviour:** a note common to two consecutive identical chords is held through, as one tied note. At every chord change all parts re-strike. A toggle re-strikes every bar instead.
- Patterns are assigned per section and can be changed per part. Presets can also set them per instrument (e.g. low brass). Priority: part, then instrument, then section.
- Every pattern strikes at each chord change. Unaccented notes play at 80% velocity.
- Choirs sing only Sustain, 8th ostinato, stabs or half-time pulse.
- Parts playing the melody or bass file keep the file's rhythm.
- Where a pattern would break a rule at a chord, that part falls back to Sustain for that chord, so generated output still has no rule errors.

**5d. Control over results**

- 3 alternatives per generation.
- **Lock** any part, then regenerate the rest around it.
- **Regenerate** one part only, all parts, or one chord only. Regenerating steers away from the last 8 results, so it doesn't cycle between two. Undo/redo (Ctrl+Z / Ctrl+Y) covers every edit: corrections, locks, swaps, slider changes and regenerations.
- **Choose per chord or per bar:** for any chord, pick a different alternative's voicing just for that chord. After a swap, the checker re-runs on the neighbouring chords and flags any leaps the swap caused.
- **Keep as-is option:** your input voicing is kept exactly as written and assigned to one part (default: strings), with the rest orchestrated around it.
- **One-line reason** for each alternative, e.g. *"Wide strings, horns on 3rds and 7ths, low brass in open 5ths."*

## 6. Controls, interface and playback

Four sliders, set per section (woodwinds, brass, strings, choir) with a global master that moves all four, plus ensemble presets. The side panel's "Set" box picks All sections or one section; the pattern picker sits in the same panel. Dynamics and Pattern apply at once; Character, Forces and Density take effect at the next Generate. With every section set the same, results equal the master slider's. The main screen is a grid of instruments by chords.

**Sliders**

| Slider | Left end | Right end | What it changes |
| --- | --- | --- | --- |
| Character | Safe | Moderate | Chord tones only, moving toward added 9ths/sus/6ths, passing tones and independent bass. A wild setting is reserved for later. |
| Forces | Solo | Section / divisi | Solo instruments, then full sections, then divisi splits |
| Density | Sparse | Full | How many of the preset's parts play, and how many doublings |
| Dynamics | pp | ff | Velocity (pp 30, p 50, mp 65, mf 80, f 100, ff 120), plus one constant CC1 value per part at its section's level, because most library sustain patches use CC1 for loudness |

**Presets (v1):** Strings only · Strings + horns · Brass + choir · Full epic · Woodwinds + strings (soft) · Low and heavy (low strings, low brass, contrabassoon, men's choir). Presets set active parts, counts, patterns (per section or per instrument) and slider starting points, master and per section. You can save your own presets. Built-in patterns: Full epic has strings on 8th ostinato and tenor/bass trombones and tuba on half-time pulse; Low and heavy has strings on 8ths and low brass on stabs; the other presets sustain.

**Main screen, top to bottom**

1. **Top bar:** file slots (chords, melody, bass), key, mode, tempo, preset, the Generate button, and alternative tabs A / B / C.
2. **Chord strip:** one cell per chord showing symbol, Roman numeral and length. Click it to correct.
3. **Grid:** one row per active part, one column per chord. Each cell shows the part's notes (Ableton names). Yellow means outside comfortable range, red means a rule error (should never appear). Each row has lock, mute, solo and a drag handle for export.
4. **Side panel:** per-section sliders and pattern pickers.
5. **Piano-roll preview:** opens under the grid for the selected part and shows its full line, with each note's name (Ableton or scientific, as set).
6. **Bottom:** the transport (play, stop, loop, tempo), the checker summary with warnings, and the one-line reason for the current alternative.

The interface uses a dark theme.

**Playback**

- FluidSynth plays a General MIDI SoundFont, so it is light on CPU and RAM. The candidate SoundFont is GeneralUser GS (about 30 MB). It is checked in Milestone 3, and any GM SoundFont can be swapped in through settings.
- GM has no bass clarinet or contrabassoon, so the audition sound uses clarinet and bassoon for these. Exported notes are unaffected.
- Playback supports loop on or off, a tempo field, and mute and solo per part and per section. Audio uses WASAPI shared mode so it still plays while Ableton holds the ASIO driver. This is tested in Milestone 1.

## 7. Export, projects and validation

Export writes standard MIDI files at concert pitch, starting at bar 1 with no lead-in, so a file dropped at a bar line in Ableton lines up exactly. Dynamics in v1 are velocity plus one constant CC1 value per part.

**Export**

- **Export choice:** per-part files, the full score file, or both (default both). It also sets what the "All" drag handle gives.
- **Per-part files:** one track per file, named `{ProjectName}_{Part}_{Alt}.mid`, e.g. `NightRise_Hn1_A.mid` … `NightRise_Hn4_A.mid`.
- **Full score file:** type 1 MIDI with one named track per part, `{ProjectName}_Full_{Alt}.mid`.
- **Drag-out:** drag a row handle (or the "All" handle) straight into Ableton's Arrangement view.
- **Save to folder:** export everything to `Documents\OrchSketch\Exports\{ProjectName}\`.
- Divisi exports as one file per divisi line (e.g. `Vln1-a`, `Vln1-b`). The optional combined files hold all of an instrument's lines on one track for every instrument playing on several lines (divisi, a2 winds, horns 1–4), named `{ProjectName}_{Code}-all_{Alt}.mid`, e.g. `NightRise_Hn-all_A.mid`. Unisons between its lines are merged so no two notes overlap on one pitch.
- Tempo and time signature are written into each file. The constant CC1 value is written at the start of each part. Keyswitches and CC1/CC11 curves are left out in v1, and the export is designed so they can be added later.

**Projects**

- Saved as a JSON `.osk` file in `Documents\OrchSketch\Projects\`. It holds the input files (embedded copies), key, tempo, chord corrections, settings, locks, chosen alternatives, the generated notes themselves, and the generation seed.
- Reopening a project restores the saved notes exactly, even after app updates change the generator. The seed is only used when you choose to regenerate.
- The project name is the `.osk` file's name (the chord clip's name until first saved) and is used in export file names. Undo history isn't saved; it lasts while the app is open.

**Rule checker** runs after every generation and on demand. Results are listed per part and per chord, and clicking a warning highlights the cell. Problems that come only from your own inputs (kept voicing, locked parts, melody and bass files) are shown on the cells, not discarded; everything the generator adds must pass.

| Check | Severity |
| --- | --- |
| Note outside playable range | Error (blocks generation) |
| Note outside comfortable range | Warning |
| Chord's defining tone missing | Error |
| Low-interval limit broken | Error |
| Spacing over an octave between adjacent upper voices | Warning |
| Choir voice crossing or leap over an octave | Error |
| Parallel 5ths/8ves between independent lines | Warning |
| Doubled leading tone or 7th in an outer voice | Warning |
| Melody note clashes with a harmony note a minor 2nd away in the same register | Warning |

**V1 pass/fail**

- **Fail:** any chord mislabeled on the test set without the correct label among its alternatives.
- **Fail:** any note outside playable range. For example, a tuba above F4 (Ableton F3) is an automatic fail.
- **Fail:** any checker error in generated output.
- **Fail:** any alternative that you judge "doesn't make musical sense" on more than 1 of the test progressions. This is your ear test. Each judgment is logged in tests/ratings.csv (test #, alternative, 1–5 score, reason, app version), so later versions can be checked for regressions.
- **Fail:** exported MIDI that lands at the wrong pitch or position in Ableton.
- **Pass:** none of the above across the full test set, with all three alternatives judged usable as sketches.

## 8. Test set

V1 is judged first on 12 textbook progressions that Claude generates as MIDI, each with a file of expected labels. Your own 5–10 progressions come in as a second benchmark only after v1 passes these.

| # | Key | Progression (expected labels) | Tests |
| --- | --- | --- | --- |
| 1 | A minor | Am – F – C – G (i–VI–III–VII) | Epic staple, 1 chord/bar |
| 2 | C major | C – G – Am – F (I–V–vi–IV) | Basic major |
| 3 | D minor | Dm – Gm – Am – Dm (i–iv–v–i) | Natural minor |
| 4 | E minor | Em – C – Am – B (i–VI–iv–V) | Harmonic-minor V, leading tone |
| 5 | F major | Gm7 – C7 – Fmaj7 (ii7–V7–Imaj7) | 7th chords |
| 6 | G major | G – D/F# – Em – C/E (I–V6–vi–IV6) | Inversions and slash chords |
| 7 | D major | Dsus4 – D – Gsus2 – G | Sus chords |
| 8 | C minor | Cm Ab \| Bb Cm, 8 bars mixed | 2 chords/bar, varying rhythm |
| 9 | C minor | Cm – Ab/C – Bb/C – Cm | Pedal tone |
| 10 | C major | C – Fm – Ab – G (I–iv–bVI–V) | Borrowed chords |
| 11 | A minor | 16 bars incl. E7 and Dm/F | Max length, V7, varied rhythm |
| 12 | A minor | A5 – F5 – C5 – G5, then Am7 vs C6, Bm7b5 | Power chords, ambiguous labels |

Each test is run with melody and bass files absent and present (tests 1, 4 and 11 get melody and bass files).

## 9. Tech stack and architecture

The app is built in Python 3.12 with a Qt (PySide6) interface and packaged as a Windows folder app (`OrchSketch.exe` plus its files, zipped as one download; it starts in 1–2 s, where a single-file `.exe` takes 5–10 s). Analysis, generation and checking are pure-Python modules with no UI code. They are covered by automated tests that run without the app open.

| Module | Job | Library |
| --- | --- | --- |
| midi\_io | Read and write MIDI files | mido |
| analysis | Chord segmentation, labeling, alternatives, Roman numerals | Own code (music21 used only to cross-check in tests) |
| instruments | Range and role data | JSON files |
| rules | Hard and soft rule definitions, low-interval limits | JSON plus Python |
| generator | Roles, voicings, ranking, alternatives, locking | Own code |
| patterns | Rhythm templates | Own code |
| checker | Validation report | Own code |
| playback | Audition | FluidSynth via pyfluidsynth |
| export | Per-part and full files, drag-out | mido, Qt drag |
| project | Save and load `.osk` | JSON |
| ui | Grid, sliders, transport | PySide6 |

- Tests run with pytest. Every milestone must pass the existing tests before it is tagged.
- The biggest generator sweeps carry a `slow` marker: `run_tests.bat` skips them for a quicker run, and `release.bat` runs everything before tagging.
- Generation is seeded, so results can be reproduced and bugs can be reported exactly.

## 10. Milestones (v1)

Each milestone ends with a working build, a version tag, a changelog entry, a GitHub push and a source zip. Ableton testing happens only at milestones 1 and 6. Everything else is tested inside the app.

1. **v0.1 — Read and label.** Load MIDI, segment chords, labels plus alternatives, correction, and plain re-export. Build the 12 test files. One drag test into Ableton to confirm position and pitch. Also a throwaway packaged .exe with FluidSynth playing one note, and an audio test with Ableton open.
2. **v0.2 — Data and checker.** Instrument and rules JSON, range table cross-checked, rule checker running on hand-made examples.
3. **v0.3 — First orchestration.** Safe-mode voicings, the grid, playback with the SoundFont, per-part export.
4. **v0.4 — Control.** 3 alternatives (A/B/C approaches), lock and regenerate, per-chord swap with neighbour re-check, undo/redo, top-voice option, keep-as-is, global sliders, presets.
5. **v0.5 — Motion.** Rhythm patterns, bass doubling and the independent toggle, melody assignment, moderate mode, per-section sliders.
6. **v1.0 — Finish.** Projects, full export options, packaged app (folder build), full test-set pass, and the Ableton check.

## 11. Out of scope for v1

The following are left out: the AI assistant; keyswitches and CC1/CC11 curves (the constant CC1 per part is in); harp, piano, timpani and percussion; key changes, other time signatures and tempo changes; arpeggiated or broken input; automatic key detection and modal labeling; the half-time toggle; wild mode; VST3 and Max for Live; training on reference datasets (OpenScore, IMSLP, etc., which move to Phase 2 for tuning); and notation export.

**Later phases (unchanged order):** 2 Composition (planned in §14: patterns, textures, CC curves, lines, control items, AI line writer) · 3 Arrangement (entrances and exits, timeline) · 4 AI assistant (online allowed) · 5 Expansion (harp, piano, timpani, percussion engine).

## 12. Open items

- ~~**Building the `.exe`**~~ resolved: `scripts\build_exe.bat`, a one-click build Sam runs (v1.0).
- ~~**SoundFont**~~ resolved: GeneralUser GS v2.0.3, licence and sound confirmed in Milestone 3.
- ~~**Range and low-interval tables**~~ resolved: cross-checked in Milestone 2 (sources and changes in STATUS.md).
- **Your progressions:** collect 5–10 for the second benchmark after the v1.0 test-set pass.
- **App name:** OrchSketch is a placeholder.

## 13. Handoff to build chats

Each milestone is built in its own fresh chat, starting from three files: `SPEC.md` (this doc exported as Markdown), `STATUS.md` and the latest code.

1. Export this doc as Markdown and save it as `SPEC.md` in the repo root, next to `STATUS.md`.
2. Open a new chat per milestone. Attach `SPEC.md`, `STATUS.md` and the repo link or latest source zip.
3. Kickoff message: *"Build Milestone N per SPEC.md. STATUS.md has the current state. Update STATUS.md and CHANGELOG.md when done."* Phase 2 milestones (7–12) are defined in §14.
4. The milestone ends with an updated `STATUS.md`, which becomes the next chat's starting point.
5. If the spec changes, edit this doc and re-export `SPEC.md`. Never patch the copy in a chat.

## 14. Phase 2 — Composition (v1.2 to v2.0)

Decided 2026-11-12 after a research and brainstorm round (Claude Doc *OrchSketch Phase 2 — Ranked Feature Research*: https://claude.ai/artifact/3FppXiZGQNhVj13gn5DwZX, which holds the 44 ranked ideas, sources and reasoning). Phase 2 targets the hand work Sam still does after export: rewriting rhythms/patterns and adding lines (countermelodies, runs, bass). The exported MIDI ends up as the final, polished part, so it must sound finished, not just correct.

**Guardrails (all Phase 2 milestones)**

- A/B/C plus the sliders stay the main way to work. New features are new options, not a new workflow.
- Generation stays fast: all three alternatives for 16 bars, patterns and lines included, in about 4 s or less (now 2–3 s). Profile each new generator.
- Defaults reproduce v1.1: with every new option at its default, the A and v0.4 snapshots and every existing sweep pass unchanged. Generated output keeps 0 checker errors and 0 must-pass warnings.
- Re-run `scripts\benchmark.bat` after generator changes and log ear-test scores in `tests/ratings.csv`.
- Still deterministic and seeded. The one exception is the optional AI line writer (milestone 12), which runs only on a button press.

**Decisions**

| Topic | Decision |
| --- | --- |
| Ostinato note mode | A three-position control per section: **Chord tones** (default; every note is a chord-tone slot, always consonant) · **Hybrid** (strong-beat notes snap to chord tones, notes in between follow the scale) · **Scale steps** (the whole contour moves by scale steps from the nearest chord tone; most melodic). |
| A/B/C for patterns and lines | Two steps. Sam picks the harmony A/B/C first, then patterns and lines get their own A/B/C on top of it (lock/regenerate work as now). |
| Countermelody target | The melody file; with no melody file, the chord top voice. |
| Counter vs top voice | Separate registers: the counter sits an octave or more from the line it counters, or in another section. Thin (rest or re-octave) a top-voice note only where they would still collide. |
| Counter instrument | Chosen by melody register: a high melody puts the counter in horns, then cellos; a low melody puts it in violins, then flute. Sam can pick the instrument (milestone 10 placement). |
| Checker on runs, pickups, rips, falls, trills | Endpoints only: notes stay in range and in the scale (or the target chord's scale on the last beat before a hit), and the run lands on a chord tone on the beat. Parallels and clash checks are skipped for the notes in between. |
| Articulations | Sam rarely switches articulations: one patch per exported file. Tremolo goes out as its own part. No shorts/longs split. Keyswitches are low priority (optional, later). |
| Builds | Preset intensity shapes and phrase-end fills only; no drawn curves, no inferred fills. |
| AI | Pulled forward into Phase 2 for writing lines only. Online via the Claude API (Anthropic Python SDK + Sam's API key); per-use cost is fine. Runs only when Sam presses its button; its output is validated by the checker and retried; rules-only stays the offline default. |
| Choir melody override | When the choir carries the melody and can't voice around it, the choir bass rests; its notes are covered by cellos/basses, switched on automatically if they are off. Upper choir voices carry melody and harmony. |
| Bass | Simple is enough: sustained roots, repeated 1/4 or 1/8 roots, octave variants. Synth wobble is done in Ableton. |

**Not in Phase 2 (Sam's call):** display spelling, larger chord vocabulary and the melody-outside-key hint; input limits (16 bars, 4/4, key changes, 1/8 grid); drum or rhythm-clip import; better audition sounds or live MIDI into Ableton; a hybrid synth section (later phase); drawn intensity curves; tutti hits/braams as a separate texture; motif development and fix-my-line; AI for ranking, text instructions or taste learning.

**Milestones.** Each one ends like v1: working build, tag, changelog, push, source zip, updated STATUS.md. Numbers in brackets are ranks in the research doc.

7. **v1.2 — Pattern engine.**
   - Patterns, accent groupings and shapes stored as data (JSON) so new ones need no engine code [2]. The six v1 patterns move into this format and render exactly as before.
   - Shape-preserving ostinato engine: a pattern is a contour + rhythm; at each chord change it keeps its shape and remaps its notes using the section's note mode (Chord tones / Hybrid / Scale steps) [1].
   - Accent groupings (velocity and note-length) such as 3+3+2, 3+3+3+3+2+2, 4+4+3+3+2, per section [3].
   - Pattern A/B/C (the second step of the two-step choice).
   - Checker: parallels checked inside patterns, not only at chord changes [5].
   - Phase 2 ear-test set added to the benchmark before building [4]; voicing-candidate cache and profiling [15].
8. **v1.3 — Textures and shapes.**
   - Intensity shape presets per bar: steady, build, swell, drop, build-and-hit, 4-bar phrase, breakdown (strip to 1–2 parts, then return) [6, 32]. Shapes drive density, forces, pattern and dynamics over the clip.
   - Arpeggio/broken-chord patterns: up, down, up-down, root–5th–octave–10th, rolling, range-aware [7].
   - Hits and stabs: syncopated stab rhythms, downbeat hits with rests around them, anticipations (an 8th early) [8].
   - Phrase-end fills on the last beat(s) of every 4 or 8 bars: 16th fill, drop-out before the downbeat, pickup into the next phrase [9].
   - Unison/octave theme mode: melody (or chord top voice) doubled in octaves across horns, low brass, cellos and choir instead of voiced [10].
   - Pulse-bed builder: a preset that adds a layer every 4 bars [11].
   - If time allows: pattern families per approach [23], pads under ostinatos [24], accents on chord changes [25], interlocking two-section 16ths [27], reference preset packs [31].
9. **v1.4 — Expression.**
   - CC1 and CC11 curves per part: swell per chord, crescendo/diminuendo over a phrase, following the intensity shape; winds and brass get one CC11 arc per phrase [12]. Replaces the constant CC1 when switched on.
   - Swells into the next chord or downbeat [13]; tremolo exported as its own part (e.g. "Vln I trem") [14]; risers over 1–4 bars into a hit, with an optional Shepard-style layered version [21].
   - Velocity shaping (phrase arcs, beat accents) and seeded humanize of timing and velocity [26].
10. **v1.5 — Lines.**
   - Imitation/echo: a melody fragment a beat or bar later in another instrument, fitted to the chords [17].
   - Runs into phrase starts, landing accented on the downbeat (octave runs in flutes/clarinets, string runs in violins) [18]; chord-change pickups of 2–4 notes [20]; decorating sustains (trills, ripples) [28]; brass rips and falls written as notes [29].
   - Simple bass patterns, and the fix for basses/tuba/contrabassoon resting on notes they can't reach [19].
   - Countermelody engine with four styles: answers in the gaps, contrary motion, rhythmic counterline, imitation. Counterpoint rules: prefer contrary and oblique motion, no parallel 5ths/octaves against its target, dissonances approached and left by step [16].
   - Targeted placement: select bars + an instrument and generate a line only there, with its own A/B/C [22].
11. **v1.6 — Control.** Pedal-tone instrument choice [33]; per-part role overrides and roles in presets [34]; choir melody override [35]; exact player counts [36]; keep-as-is outside the strings [37]; SSAATTBB layout [40]; move the repo to its own folder, e.g. `Documents\OrchSketch-dev` [42].
12. **v2.0 — AI line writer.** A button that asks the Claude API for a counter, run or melody line over the current harmony, validates it with the checker (including the line rules from milestone 10), retries on failure and offers the results as A/B/C. Key stored locally, never in the repo or project files. Without network or key the button explains why and nothing else changes [38].

**Parked (ranked low; pick up later if wanted):** cross-rhythm triplet layer [30]; chopped chords and orchestral CC11 pumping [39]; root-note bass export for synths [41]; a local AI music model [43]; keyswitches per library [44].
