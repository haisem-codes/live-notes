import json

from conftest import TINY

from live_notes_api.model import HeuristicModel
from live_notes_api.models import dump_json, parse_op
from live_notes_api.reducer import fold
from live_notes_api.replay import main, replay_session
from live_notes_api.store import DirectorySessionStore


async def test_replay_tiny_session(tmp_path):
    before = sorted(p.name for p in TINY.iterdir())
    out = tmp_path / "out"
    summary = await replay_session(TINY, out, HeuristicModel())
    assert sorted(p.name for p in TINY.iterdir()) == before  # input untouched

    ops = [parse_op(line) for line in (out / "ops.jsonl").read_text().splitlines()]
    assert [o.seq for o in ops] == list(range(1, len(ops) + 1))
    user = [o for o in ops if o.actor == "user"]
    assert [(o.t_emit_ms, o.payload.slide) for o in user] == [(0, 1), (36000, 2)]
    agent = [o for o in ops if o.actor != "user"]
    assert summary.ops_accepted == len(agent) > 0
    assert summary.ticks >= 3 and not summary.rejected_by_reason

    doc = fold(ops)
    texts = [b.text for b in doc.blocks]
    assert texts[0] == "Gradient descent"  # heading from slide 1's first text region
    assert any(b.kind == "h2" and b.text == "Learning rate" for b in doc.blocks)
    # the correction rewrote the bullet instead of adding one
    assert any(t.startswith("that the step goes against the gradient") for t in texts)
    assert not any("learning rate eta" in t for t in texts)  # s2's bullet was rewritten
    assert not any("Sorry" in t for t in texts)
    assert all(o.t_emit_ms >= p.t_emit_ms for p, o in zip(ops, ops[1:], strict=False))

    # a valid stored session: transcript copied, state present, reloadable
    store = DirectorySessionStore(out)
    assert len(store._segments) == 6
    assert (out / "session.json").exists() and (out / "state.json").exists()
    assert fold(store._ops) == doc


async def test_replay_is_deterministic(tmp_path):
    await replay_session(TINY, tmp_path / "a", HeuristicModel())
    await replay_session(TINY, tmp_path / "b", HeuristicModel())
    assert (tmp_path / "a" / "ops.jsonl").read_text() == (tmp_path / "b" / "ops.jsonl").read_text()


def test_replay_cli_prints_summary(tmp_path, capsys):
    out = tmp_path / "cli"
    assert main([str(TINY), "--model", "heuristic", "--out", str(out)]) == 0
    text = capsys.readouterr().out
    assert "ticks:" in text and "ops accepted:" in text and "ops rejected: 0" in text
    assert "block.insert:" in text
    first = json.loads((out / "ops.jsonl").read_text().splitlines()[0])
    assert first["type"] == "slide.set" and first["actor"] == "user"
    assert dump_json(parse_op(json.dumps(first))) == json.dumps(first, separators=(",", ":"))
