import json

import pytest

from orchsketch.instruments import DataError
from orchsketch.rules import CHECK_IDS, ERROR, RULES_FILE, WARNING, load_rules, parse_rules, rules
from orchsketch.theory import parse_pitch

# Low-interval limits adopted in Milestone 2 (lowest allowed lower note, scientific pitch).
LIMITS = {1: "E3", 2: "Eb3", 3: "C3", 4: "Bb2", 5: "A2", 6: "Bb2", 7: "Bb1",
          8: "F2", 9: "F2", 10: "F2", 11: "F2"}


def test_low_interval_table():
    r = rules()
    assert r.low_interval_limits == {k: parse_pitch(v) for k, v in LIMITS.items()}
    assert r.low_limit(0) is None and r.low_limit(12) is None and r.low_limit(15) is None


def test_limits_cover_the_spec_wording():
    # SPEC §5a: "no 3rds or 2nds below about C3, nothing smaller than a 5th below about Bb1".
    r = rules()
    assert all(r.low_limit(i) >= parse_pitch("C3") for i in (1, 2, 3))
    assert all(r.low_limit(i) > parse_pitch("Bb1") for i in range(1, 7))
    assert r.low_limit(7) == parse_pitch("Bb1")


def test_severities_agreed_in_milestone_2():
    r = rules()
    assert set(r.checks) == set(CHECK_IDS)
    errors = {"playable_range", "defining_tone", "low_interval", "choir_crossing", "choir_leap",
              "choir_parallels"}
    for cid in CHECK_IDS:
        assert r.severity(cid, "moderate") == (ERROR if cid in errors else WARNING), cid
    assert r.severity("comfortable_range", "safe") == ERROR
    assert r.severity("spacing", "safe") == WARNING
    # Warnings the Milestone 3 generator must still never produce:
    assert r.checks["spacing"].generator_must_pass and r.checks["doubled_outer"].generator_must_pass
    assert not r.checks["parallels"].generator_must_pass


def test_other_limits():
    r = rules()
    assert r.spacing_max == 12 and r.choir_max_leap == 12
    assert r.melody_clash == {1}
    assert r.choir_order == ("choir_soprano", "choir_alto", "choir_tenor", "choir_bass")


def _raw():
    return json.loads(RULES_FILE.read_text(encoding="utf-8"))


def test_bad_rules_rejected(tmp_path):
    raw = _raw()
    raw["checks"]["spacing"]["severity"] = "fatal"
    with pytest.raises(DataError, match="severity"):
        parse_rules(raw)
    raw = _raw()
    del raw["checks"]["melody_clash"]
    with pytest.raises(DataError, match="missing check"):
        parse_rules(raw)
    raw = _raw()
    raw["low_interval_limits"]["lowest_allowed_lower_note"]["3"] = "X9"
    with pytest.raises(DataError):
        parse_rules(raw)
    p = tmp_path / "rules.json"
    p.write_text("[", encoding="utf-8")
    with pytest.raises(DataError, match="not valid JSON"):
        load_rules(p)
