"""Rule data (SPEC §5a, §7): low-interval limits, spacing and leap limits, check severities.

Loaded from data/rules.json so the numbers can be changed without touching code.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .instruments import DATA_DIR, DataError
from .theory import parse_pitch

RULES_FILE = DATA_DIR / "rules.json"
ERROR, WARNING = "error", "warning"
SAFE, MODERATE = "safe", "moderate"
CHECK_IDS = (
    "playable_range", "comfortable_range", "defining_tone", "low_interval", "spacing",
    "choir_crossing", "choir_leap", "parallels", "choir_parallels", "doubled_outer", "melody_clash",
)


@dataclass(frozen=True)
class CheckDef:
    id: str
    severity: str
    safe_mode_severity: str
    generator_must_pass: bool
    label: str


@dataclass(frozen=True)
class Rules:
    low_interval_limits: dict[int, int]  # semitones (1-11) -> lowest allowed lower pitch (MIDI)
    interval_names: dict[int, str]
    spacing_max: int
    choir_max_leap: int
    melody_clash: frozenset[int]
    choir_order: tuple[str, ...]
    checks: dict[str, CheckDef]

    def severity(self, check: str, mode: str = MODERATE) -> str:
        c = self.checks[check]
        return c.safe_mode_severity if mode == SAFE else c.severity

    def low_limit(self, semitones: int) -> int | None:
        """Lowest allowed lower note for this interval, or None when it has no limit."""
        return self.low_interval_limits.get(semitones)


def parse_rules(raw: dict, name: str = "rules.json") -> Rules:
    try:
        lil = raw["low_interval_limits"]
        limits = {int(k): parse_pitch(v) for k, v in lil["lowest_allowed_lower_note"].items()}
        names = {int(k): v for k, v in lil.get("interval_names", {}).items()}
        checks = {}
        for cid, c in raw["checks"].items():
            sev = c["severity"]
            safe = c.get("safe_mode_severity", sev)
            if sev not in (ERROR, WARNING) or safe not in (ERROR, WARNING):
                raise DataError(f"{name}: check '{cid}' severity must be error or warning")
            checks[cid] = CheckDef(cid, sev, safe, bool(c.get("generator_must_pass", sev == ERROR)),
                                   c.get("label", cid))
        rules = Rules(
            low_interval_limits=limits,
            interval_names=names,
            spacing_max=int(raw["spacing_max_semitones"]),
            choir_max_leap=int(raw["choir_max_leap_semitones"]),
            melody_clash=frozenset(int(x) for x in raw["melody_clash_semitones"]),
            choir_order=tuple(raw["choir_order"]),
            checks=checks,
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, DataError):
            raise
        raise DataError(f"{name}: {type(exc).__name__}: {exc}") from None
    if bad := [k for k in limits if not 1 <= k <= 11]:
        raise DataError(f"{name}: low-interval limits are for 1-11 semitones, not {bad}")
    if missing := set(CHECK_IDS) - checks.keys():
        raise DataError(f"{name}: missing check(s) {', '.join(sorted(missing))}")
    return rules


def load_rules(path: Path | str | None = None) -> Rules:
    p = Path(path) if path else RULES_FILE
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DataError(f"{p.name}: not valid JSON ({exc})") from None
    return parse_rules(raw, p.name)


@lru_cache(maxsize=1)
def rules() -> Rules:
    """The built-in rules (cached)."""
    return load_rules()
