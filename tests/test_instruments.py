import json

import pytest

from orchsketch.instruments import (INSTRUMENT_DIR, ROLES, SECTIONS, DataError, instruments,
                                    load_instruments, parse_instrument)
from orchsketch.theory import parse_pitch

# SPEC §4 table with the changes Sam approved in Milestone 2 (see STATUS.md). Sounding, scientific.
APPROVED = {
    "piccolo": ("D5", "C8", "A5", "A7", 1),
    "flute": ("C4", "C7", "E4", "A6", 2),
    "oboe": ("Bb3", "A6", "D4", "D6", 2),
    "english_horn": ("E3", "A5", "G3", "G5", 1),
    "clarinet": ("D3", "Bb6", "E3", "C6", 2),
    "bass_clarinet": ("Bb1", "F5", "D2", "F4", 1),
    "bassoon": ("Bb1", "E5", "C2", "Bb4", 2),
    "contrabassoon": ("Bb0", "C4", "D1", "C3", 1),
    "horn": ("B1", "F5", "F2", "D5", 4),
    "trumpet": ("E3", "C6", "G3", "G5", 3),
    "tenor_trombone": ("E2", "F5", "G2", "Bb4", 2),
    "bass_trombone": ("Bb0", "F5", "C2", "F4", 1),
    "tuba": ("D1", "F4", "F1", "C4", 1),
    "violins_1": ("G3", "E7", "G3", "A6", "section"),
    "violins_2": ("G3", "E7", "G3", "E6", "section"),
    "violas": ("C3", "E6", "C3", "G5", "section"),
    "cellos": ("C2", "A5", "C2", "A4", "section"),
    "basses": ("E1", "G4", "E1", "D3", "section"),
    "choir_soprano": ("C4", "A5", "E4", "G5", "section"),
    "choir_alto": ("F3", "F5", "A3", "C5", "section"),
    "choir_tenor": ("C3", "A4", "D3", "F4", "section"),
    "choir_bass": ("E2", "C4", "G2", "C4", "section"),
}
MAX_DIVISI = {"violins_1": 3, "violins_2": 3, "violas": 3, "cellos": 3, "basses": 2,
              "horn": 4, "trumpet": 3, "tenor_trombone": 2}


def test_all_22_parts_in_score_order():
    insts = instruments()
    assert list(insts) == list(APPROVED)
    sections = [i.section for i in insts.values()]
    assert sections == sorted(sections, key=SECTIONS.index)


@pytest.mark.parametrize("iid", list(APPROVED))
def test_ranges_match_approved_table(iid):
    p_lo, p_hi, c_lo, c_hi, count = APPROVED[iid]
    inst = instruments()[iid]
    assert inst.playable == (parse_pitch(p_lo), parse_pitch(p_hi))
    assert inst.comfortable == (parse_pitch(c_lo), parse_pitch(c_hi))
    assert inst.default_count == count


@pytest.mark.parametrize("iid", list(APPROVED))
def test_record_fields(iid):
    inst = instruments()[iid]
    assert inst.playable[0] <= inst.comfortable[0] <= inst.comfortable[1] <= inst.playable[1]
    assert inst.roles and set(inst.roles) <= set(ROLES)
    assert 0 <= inst.gm_program <= 127
    assert inst.registers, "every instrument has timbre notes per register"
    for r in inst.registers:
        assert inst.playable[0] <= r.low <= r.high <= inst.playable[1]
    assert inst.max_divisi == MAX_DIVISI.get(iid, inst.max_divisi)


def test_spec_examples():
    insts = instruments()
    assert insts["tuba"].playable[1] == parse_pitch("F4")  # SPEC §7: tuba above F4 fails
    assert "heroic" in " ".join(insts["horn"].register_notes(parse_pitch("C4")))
    assert insts["bass_clarinet"].audition_note and insts["contrabassoon"].audition_note
    assert insts["tuba"].range_text("playable", "ableton") == "D0–F3"


def _write(tmp_path, rec):
    (tmp_path / f"{rec['id']}.json").write_text(json.dumps(rec), encoding="utf-8")


def _good():
    return json.loads((INSTRUMENT_DIR / "flute.json").read_text("utf-8"))


@pytest.mark.parametrize("change,msg", [
    ({"comfortable": ["B3", "A6"]}, "inside the playable"),
    ({"playable": ["C7", "C4"]}, "low note is above"),
    ({"playable": ["H4", "C7"]}, "not a pitch name"),
    ({"section": "percussion"}, "section must be"),
    ({"roles": ["lead"]}, "roles must be"),
    ({"gm_program": 128}, "gm_program"),
    ({"default_count": 0}, "default_count"),
    ({"colour": "silver"}, "unknown field"),
])
def test_bad_records_are_rejected(change, msg):
    raw = _good() | change
    with pytest.raises(DataError, match=msg):
        parse_instrument(raw)


def test_loader_checks_file_names(tmp_path):
    raw = _good()
    _write(tmp_path, raw)
    assert list(load_instruments(tmp_path)) == ["flute"]
    (tmp_path / "piccolo.json").write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(DataError, match="doesn't match the file name"):
        load_instruments(tmp_path)


def test_loader_reports_bad_json(tmp_path):
    (tmp_path / "flute.json").write_text("{nope", encoding="utf-8")
    with pytest.raises(DataError, match="flute.json: not valid JSON"):
        load_instruments(tmp_path)
