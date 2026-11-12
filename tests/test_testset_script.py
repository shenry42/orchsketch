"""Milestone 6: scripts/testset.py (the full test-set pass) builds a project the app reopens exactly."""
import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


def test_fifteen_runs_and_one_of_them_end_to_end(tmp_path):
    import testset
    runs = testset.runs()
    assert len(runs) == 15 and sum(f for _, f in runs) == 3  # 12 files, plus 1, 4 and 11 with melody and bass
    assert testset.main(["04_harmonic_minor_v_melody_bass"], folder=tmp_path, report=tmp_path / "r.txt")
    text = (tmp_path / "r.txt").read_text(encoding="utf-8")
    assert "AUTOMATIC CHECKS: 1/1 runs pass" in text and "reopens with the same notes" in text
    assert (tmp_path / "04_harmonic_minor_v_melody_bass.osk").exists()


def test_benchmark_runs_and_a_hand_set_chord(tmp_path):
    """--benchmark: Sam's 10 progressions (B01 also with its melody and bass files). B08's chords are outside the
    v1 chord list, come out unrecognized and are typed in by hand before Generate."""
    import testset
    assert len(testset.runs(testset.BENCHMARK_DATA)) == 11
    assert testset.main(["B08"], folder=tmp_path, report=tmp_path / "r.txt", data=testset.BENCHMARK_DATA)
    text = (tmp_path / "r.txt").read_text(encoding="utf-8")
    assert "second benchmark" in text and "Set by hand: chord 1 = Cm" in text
    assert "AUTOMATIC CHECKS: 1/1 runs pass" in text and (tmp_path / "B08.osk").exists()
