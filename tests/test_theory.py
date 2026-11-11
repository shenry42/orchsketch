import pytest

from orchsketch.theory import Key, note_name, parse_note_name


def test_middle_c_names():
    assert note_name(60, "scientific") == "C4"
    assert note_name(60, "ableton") == "C3"


def test_tuba_example_from_spec():
    # SPEC §4: tuba never above C4 (scientific) = C3 in Ableton
    assert note_name(60, "ableton") == "C3"
    assert note_name(65, "scientific") == "F4" and note_name(65, "ableton") == "F3"


@pytest.mark.parametrize("name,pc", [("C", 0), ("C#", 1), ("Db", 1), ("Bb", 10), ("B#", 0), ("Cb", 11), ("E♭", 3)])
def test_parse_note_name(name, pc):
    assert parse_note_name(name) == pc


def test_key_spelling():
    assert Key("Eb", "major").spelled_scale() == ["Eb", "F", "G", "Ab", "Bb", "C", "D"]
    assert Key("A", "minor").pc_name(8) == "G#"  # leading tone
    assert Key("C", "minor").pc_name(8) == "Ab"
    assert Key("G", "major").pc_name(6) == "F#"
    assert Key("C", "major").pc_name(8) == "Ab"  # neutral key: bVI is Ab
    assert Key("D", "minor").pc_name(1) == "C#"
    assert Key("F#", "minor").pc_name(5) == "E#"


def test_minor_scale_includes_raised_seventh():
    assert Key("E", "minor").scale_pcs() == {4, 6, 7, 9, 11, 0, 2, 3}


def test_bad_mode():
    with pytest.raises(ValueError):
        Key("C", "dorian")
