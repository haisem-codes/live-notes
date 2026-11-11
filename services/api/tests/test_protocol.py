import json

from conftest import GOLDEN_DOCS, GOLDEN_OPS

from live_notes_api.models import dump, dump_json, parse_op
from live_notes_api.reducer import apply_op, fold


def _ops():
    return [parse_op(line) for line in GOLDEN_OPS.read_text().splitlines() if line.strip()]


def test_golden_ops_round_trip_identically():
    lines = [line for line in GOLDEN_OPS.read_text().splitlines() if line.strip()]
    assert len(lines) == 20
    for line in lines:
        op = parse_op(line)
        assert json.loads(dump_json(op)) == json.loads(line)
        assert dump_json(op) == line  # byte-for-byte, including key order


def test_golden_fold_cases():
    cases = json.loads(GOLDEN_DOCS.read_text())["cases"]
    ops = _ops()
    assert cases
    for case in cases:
        assert dump(fold(ops, case["t_ms"])) == case["document"], case["t_ms"]


def test_fold_without_t_is_everything_and_apply_op_is_pure():
    ops = _ops()
    doc = fold(ops)
    assert dump(doc) == dump(fold(ops, 10**9))
    from live_notes_api.models import NotesDocument

    empty = NotesDocument()
    new = apply_op(empty, ops[0])
    assert empty.current_slide is None and new.current_slide == 1


def test_fold_ignores_input_order():
    ops = _ops()
    assert dump(fold(list(reversed(ops)))) == dump(fold(ops))
