"""Undo/redo (SPEC §5d): a stack of snapshots of everything you can edit.

The window takes a snapshot (any immutable object) *after* each edit and pushes it with a short label
("Lock Horn 1", "Swap chord 3 from B"). Undo returns the previous snapshot, redo the next one. Pushing after
an undo throws the redo branch away, as in every editor. Orchestrations are never changed in place, so a
snapshot can share them with the live state at no cost. No UI code.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

MAX_STEPS = 200


@dataclass(frozen=True)
class Step:
    label: str
    state: Any


class History:
    def __init__(self, initial: Any = None, label: str = "Start"):
        self.steps: list[Step] = []
        self.pos = -1
        if initial is not None:
            self.reset(initial, label)

    def reset(self, state: Any, label: str = "Start"):
        """Start a new history (e.g. a new file was opened)."""
        self.steps = [Step(label, state)]
        self.pos = 0

    def push(self, state: Any, label: str):
        if self.pos < 0:
            self.reset(state, label)
            return
        if state == self.steps[self.pos].state:
            return  # nothing changed
        del self.steps[self.pos + 1:]
        self.steps.append(Step(label, state))
        if len(self.steps) > MAX_STEPS:
            del self.steps[0]
        self.pos = len(self.steps) - 1

    @property
    def current(self) -> Any:
        return self.steps[self.pos].state if self.pos >= 0 else None

    def can_undo(self) -> bool:
        return self.pos > 0

    def can_redo(self) -> bool:
        return 0 <= self.pos < len(self.steps) - 1

    def undo_label(self) -> str | None:
        return self.steps[self.pos].label if self.can_undo() else None

    def redo_label(self) -> str | None:
        return self.steps[self.pos + 1].label if self.can_redo() else None

    def undo(self) -> Any:
        if not self.can_undo():
            return None
        self.pos -= 1
        return self.steps[self.pos].state

    def redo(self) -> Any:
        if not self.can_redo():
            return None
        self.pos += 1
        return self.steps[self.pos].state
