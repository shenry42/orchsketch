"""Small helpers to write throwaway MIDI files in tests."""
import mido


def write_mid(path, notes, ppq=480, timesig=(4, 4), mtype=1):
    """notes: (pitch, start_tick, end_tick[, velocity]) at the given ppq."""
    mid = mido.MidiFile(type=mtype, ticks_per_beat=ppq)
    tr = mido.MidiTrack()
    tr.append(mido.MetaMessage("time_signature", numerator=timesig[0], denominator=timesig[1], time=0))
    ev = []
    for n in notes:
        p, s, e = n[:3]
        v = n[3] if len(n) > 3 else 100
        ev.append((s, 1, mido.Message("note_on", note=p, velocity=v)))
        ev.append((e, 0, mido.Message("note_off", note=p, velocity=0)))
    ev.sort(key=lambda x: (x[0], x[1]))
    now = 0
    for t, _, m in ev:
        tr.append(m.copy(time=t - now))
        now = t
    mid.tracks.append(tr)
    mid.save(str(path))
    return path


def block(chords, ppq=480):
    """chords: list of (pitches, beats) -> notes list."""
    out, t = [], 0
    for pitches, beats in chords:
        for p in pitches:
            out.append((p, int(t * ppq), int((t + beats) * ppq)))
        t += beats
    return out
