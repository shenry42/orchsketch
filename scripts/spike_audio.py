"""Milestone 1 throwaway spike: a packaged .exe that plays FluidSynth through WASAPI
shared mode, so it can sound while Ableton holds its ASIO driver. Writes
spike_audio_log.txt next to the .exe. Not part of the app."""
import sys
import time
import traceback
from pathlib import Path

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orchsketch.playback import fluid_env  # noqa: E402

lines = []


def say(msg: str):
    print(msg, flush=True)
    lines.append(msg)


def play(fs, sfid, program, pitches, name):
    fs.program_select(0, sfid, 0, program)
    say(f"Playing {name} for 2 seconds...")
    for p in pitches:
        fs.noteon(0, p, 100)
    time.sleep(2.0)
    for p in pitches:
        fs.noteoff(0, p)
    time.sleep(1.0)


def main() -> int:
    ok = False
    try:
        say(f"OrchSketch audio spike · Python {sys.version.split()[0]} · frozen={getattr(sys, 'frozen', False)}")
        say(f"FluidSynth DLL folder: {fluid_env.prepare()}")
        import fluidsynth
        sf = fluid_env.find_soundfont()
        say(f"SoundFont: {sf}")
        fs = fluidsynth.Synth(gain=0.5, samplerate=48000.0)
        fs.setting("audio.driver", "wasapi")
        fs.setting("audio.wasapi.exclusive-mode", 0)  # shared mode: coexists with Ableton
        # Audio driver only. Synth.start() would also open a Windows MIDI input port,
        # which could fight Ableton for MIDI devices, so it is not used.
        fs.audio_driver = fluidsynth.new_fluid_audio_driver(fs.settings, fs.synth)
        if not fs.audio_driver:
            raise RuntimeError("FluidSynth could not open the WASAPI audio output")
        say("Audio driver: WASAPI (shared mode), default Windows output device")
        sfid = fs.sfload(str(sf))
        if sfid == -1:
            raise RuntimeError("SoundFont failed to load")
        play(fs, sfid, 48, [60], "one note: middle C (Ableton C3), strings")
        play(fs, sfid, 60, [57, 60, 64], "an A minor chord, French horn")
        fs.delete()
        ok = True
        say("DONE. If you heard a string note and then a horn chord, audio works.")
    except Exception:  # noqa: BLE001
        say("FAILED:\n" + traceback.format_exc())
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
    (base / "spike_audio_log.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        input("\nPress Enter to close this window.")
    except EOFError:
        pass
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
