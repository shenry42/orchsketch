"""Open FluidSynth for audition: WASAPI shared mode, audio driver only (no MIDI input driver).

Shared by the app's player and scripts/sound_check.py. See STATUS.md: FluidSynth must never open a
MIDI input driver, so it can't take MIDI ports away from Ableton.
"""
from __future__ import annotations

from pathlib import Path

from . import fluid_env

SAMPLE_RATE = 48000.0
GAIN = 0.4


class SynthError(RuntimeError):
    """Audio couldn't start. The message is shown to the user."""


def open_synth(soundfont: Path | str | None = None):
    """Return (synth, soundfont_id). Raises SynthError with a readable message."""
    try:
        fluid_env.prepare()
        import fluidsynth  # noqa: PLC0415  (needs the DLL folder first)
    except (FileNotFoundError, ImportError, OSError) as exc:
        raise SynthError(f"FluidSynth couldn't load ({exc}). Run scripts\\setup.bat.") from None
    sf = Path(soundfont) if soundfont else fluid_env.find_soundfont()
    fs = fluidsynth.Synth(gain=GAIN, samplerate=SAMPLE_RATE)
    fs.setting("audio.driver", "wasapi")
    fs.setting("audio.wasapi.exclusive-mode", 0)  # shared mode: coexists with Ableton on ASIO
    fs.setting("synth.polyphony", 512)
    fs.audio_driver = fluidsynth.new_fluid_audio_driver(fs.settings, fs.synth)
    if not fs.audio_driver:
        fs.delete()
        raise SynthError("FluidSynth couldn't open the Windows audio output (WASAPI shared mode).")
    sfid = fs.sfload(str(sf))
    if sfid == -1:
        fs.delete()
        raise SynthError(f"The SoundFont failed to load: {sf}")
    return fs, sfid
