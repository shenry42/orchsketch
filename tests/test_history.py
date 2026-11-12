from orchsketch.history import MAX_STEPS, History


def test_undo_redo_and_branching():
    h = History("s0")
    h.push("s1", "one")
    h.push("s2", "two")
    assert h.undo_label() == "two" and h.undo() == "s1" and h.undo() == "s0" and h.undo() is None
    assert h.redo_label() == "one" and h.redo() == "s1"
    h.push("s3", "three")  # drops the redo branch
    assert not h.can_redo() and h.current == "s3" and h.undo() == "s1"


def test_identical_states_are_not_steps_and_size_is_capped():
    h = History("a")
    h.push("a", "nothing")
    assert not h.can_undo()
    for i in range(MAX_STEPS + 20):
        h.push(i, f"step {i}")
    assert len(h.steps) == MAX_STEPS and h.current == MAX_STEPS + 19
