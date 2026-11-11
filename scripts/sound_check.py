"""Milestone 3 sound check: plays every audition sound so Sam can judge the GeneralUser GS patches.

Numbered items:
  1-22  each instrument with its current GM program: comfortable low, middle and high note, then an
        A minor chord in its middle register
  23-26 alternatives (slow strings, solo string patches, "oohs" choir, and the full ensemble)
At the end you type the numbers that sounded wrong; they are saved to sound_check_results.txt.
"""
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from orchsketch.instruments import instruments  # noqa: E402
from orchsketch.playback.synth import open_synth  # noqa: E402
from orchsketch.theory import note_name  # noqa: E402

VEL = 90
lines = []


def say(msg=""):
    print(msg, flush=True)
    lines.append(msg)


def a_minor_chord(lo, hi):
    """A-C-E (closed) placed around the middle of [lo, hi]; returns pitches inside the range."""
    mid = (lo + hi) // 2
    a = mid - ((mid - 9) % 12)  # A at or below the middle
    for base in (a, a - 12, a + 12):
        ch = [base, base + 3, base + 7]
        if lo <= ch[0] and ch[-1] <= hi:
            return ch
    return [p for p in (a, a + 3, a + 7) if lo <= p <= hi] or [mid]


def hit(fs, chan, pitches, secs):
    for p in pitches:
        fs.noteon(chan, p, VEL)
    time.sleep(secs)
    for p in pitches:
        fs.noteoff(chan, p)


def main() -> int:
    say(f"OrchSketch sound check  {datetime.now():%Y-%m-%d %H:%M}")
    say("Listen for: wrong instrument, wrong octave, clicks, very loud/quiet compared to the others.\n")
    fs, sfid = open_synth()
    insts = list(instruments().values())
    for n, inst in enumerate(insts, 1):
        fs.program_select(0, sfid, 0, inst.gm_program)
        lo, hi = inst.comfortable
        mid = (lo + hi) // 2
        chord = a_minor_chord(lo, hi)
        say(f"#{n:2}  {inst.name:16} program {inst.gm_program:3}   notes "
            f"{note_name(lo)} {note_name(mid)} {note_name(hi)}, chord "
            f"{' '.join(note_name(p) for p in chord)} (Ableton names)")
        for p in (lo, mid, hi):
            hit(fs, 0, [p], 0.6)
        hit(fs, 0, chord, 1.6)
        time.sleep(0.4)

    say("\nAlternatives (compare with the items above):")
    strings_chord = [33, 45, 57, 64, 72]  # A1 A2 A3 E4 C5, low to high
    n = len(insts) + 1
    say(f"#{n:2}  strings: first the current Fast Strings (48), then Slow Strings (49)")
    for prog in (48, 49):
        fs.program_select(0, sfid, 0, prog)
        hit(fs, 0, strings_chord, 2.5)
        time.sleep(0.5)
    n += 1
    say(f"#{n:2}  strings, solo patches: Double Bass 43, Cello 42, Viola 41, Violin 40")
    for ch, prog in enumerate((43, 42, 41, 40, 40)):
        fs.program_select(ch, sfid, 0, prog)
    for ch, p in enumerate(strings_chord):
        fs.noteon(ch, p, VEL)
    time.sleep(2.5)
    for ch, p in enumerate(strings_chord):
        fs.noteoff(ch, p)
    time.sleep(0.4)
    n += 1
    choir = [45, 57, 64, 72]
    say(f"#{n:2}  choir: first the current Concert Choir (52), then Voice Oohs (53)")
    for prog in (52, 53):
        fs.program_select(0, sfid, 0, prog)
        hit(fs, 0, choir, 2.5)
        time.sleep(0.5)
    n += 1
    say(f"#{n:2}  full ensemble, A minor, every instrument on its current program")
    used = {}
    for inst in insts:
        if inst.gm_program not in used and len(used) < 15:
            ch = len(used) + (1 if len(used) >= 9 else 0)  # skip channel 10 (drums)
            used[inst.gm_program] = ch
            fs.program_select(ch, sfid, 0, inst.gm_program)
    notes = []
    for inst in insts:
        ch = used.get(inst.gm_program)
        if ch is not None:
            for p in a_minor_chord(*inst.comfortable)[:2]:
                notes.append((ch, p))
    for ch, p in notes:
        fs.noteon(ch, p, 70)
    time.sleep(3.5)
    for ch, p in notes:
        fs.noteoff(ch, p)
    time.sleep(1.0)
    fs.delete()
    return n


if __name__ == "__main__":
    out = ROOT / "sound_check_results.txt"
    try:
        last = main()
        say(f"\nDone. Type the numbers (1-{last}) that sounded wrong or bad, each with a word or two,")
        say("e.g.  9 too quiet, 23 better, 25 better   - or just press Enter if everything was fine.")
        try:
            answer = input("> ").strip()
        except EOFError:
            answer = ""
        say(f"ANSWER: {answer or '(all fine)'}")
    except Exception:  # noqa: BLE001
        say("FAILED:\n" + traceback.format_exc())
        try:
            input("\nPress Enter to close.")
        except EOFError:
            pass
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
