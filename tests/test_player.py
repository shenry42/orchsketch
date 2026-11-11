"""Milestone 3 playback logic, without audio: channels, timing, loop, tempo, mute/solo, unisons."""
import pytest

from orchsketch.midi_io import PPQ, Note
from orchsketch.playback.player import DRUM_CHANNEL, Clock, Sequence, channel_map


class FakeBackend:
    def __init__(self):
        self.log = []
        self.programs = {}
        self.closed = False

    def program(self, ch, prog):
        self.programs[ch] = prog

    def noteon(self, ch, pitch, vel):
        self.log.append(("on", ch, pitch, vel))

    def noteoff(self, ch, pitch):
        self.log.append(("off", ch, pitch))

    def close(self):
        self.closed = True

    def held(self):
        h = set()
        for e in self.log:
            (h.add if e[0] == "on" else h.discard)((e[1], e[2]))
        return h


BAR = 4 * PPQ


def seq(parts=None, length=2 * BAR):
    be = FakeBackend()
    parts = parts or [
        ("vln", 48, [Note(67, 0, BAR, 80), Note(69, BAR, 2 * BAR, 80)]),
        ("vla", 48, [Note(60, 0, 2 * BAR, 80)]),
        ("hn", 60, [Note(60, 0, BAR, 80)]),
    ]
    sections = {"vln": "strings", "vla": "strings", "hn": "brass"}
    return Sequence(be, parts, length, sections), be


def test_channels_skip_drums_and_share_per_program():
    m = channel_map([73, 68, 69, 71, 70, 60, 56, 57, 58, 48, 52, 48])
    assert DRUM_CHANNEL not in m.values() and len(set(m.values())) == 11
    s, be = seq()
    assert be.programs == {0: 48, 1: 60}
    assert s.part_channel == {"vln": 0, "vla": 0, "hn": 1}


def test_events_in_time_and_off_before_on():
    s, be = seq()
    s.advance_to(1)
    assert sorted(be.log) == sorted([("on", 0, 67, 80), ("on", 0, 60, 80), ("on", 1, 60, 80)])
    be.log.clear()
    s.advance_to(BAR + 1)
    assert sorted(be.log[:2]) == [("off", 0, 67), ("off", 1, 60)] and be.log[2] == ("on", 0, 69, 80)
    s.advance_to(2 * BAR + 1)
    assert be.held() == set()


def test_mute_solo_and_section():
    s, be = seq()
    s.advance_to(1)
    s.set_mute("vla", True)
    assert ("off", 0, 60) in be.log and (0, 60) not in be.held()
    s.set_mute("vla", False)
    s.set_solo("hn", True)
    assert be.held() == {(1, 60)}
    s.set_solo("hn", False)
    s.seek(0)
    be.log.clear()
    s.set_section("strings", mute=True)
    s.advance_to(1)
    assert be.held() == {(1, 60)}
    s.set_section("strings", mute=False)
    s.set_section("brass", solo=True)
    assert s.audible("hn") and not s.audible("vln")


def test_unison_on_one_channel_is_reference_counted():
    parts = [("a", 48, [Note(60, 0, BAR, 80)]), ("b", 48, [Note(60, 0, 2 * BAR, 80)])]
    s, be = seq(parts)
    s.advance_to(1)
    assert be.log == [("on", 0, 60, 80)]  # one note-on for the unison
    s.advance_to(BAR + 1)
    assert be.held() == {(0, 60)}  # part a ending doesn't cut part b
    s.advance_to(2 * BAR + 1)
    assert be.held() == set()


def test_seek_silences_and_restarts():
    s, be = seq()
    s.advance_to(BAR + 1)
    s.seek(0)
    assert be.held() == set()
    s.advance_to(1)
    assert len(be.held()) == 3


def test_clock_tempo_change_keeps_position():
    t = [0.0]
    c = Clock(120, now=lambda: t[0])
    t[0] = 1.0  # 2 beats at 120 BPM
    assert c.tick() == pytest.approx(2 * PPQ)
    c.set_bpm(60)
    t[0] = 2.0  # one more beat at 60
    assert c.tick() == pytest.approx(3 * PPQ)
    c.reset(0)
    assert c.tick() == 0
