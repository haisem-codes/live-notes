import json
import shutil

import pytest
from conftest import TINY
from helpers import Env, ins

from live_notes_api.models import TranscriptSegment
from live_notes_api.store import (
    CommitConflict,
    DirectorySessionRepository,
    MemorySessionRepository,
    SessionExists,
    SessionNotFound,
)


def make_ops(manifest, n=2):
    env = Env(manifest)
    r = env.tick([ins(f"note {i}") for i in range(n)])
    return r.ops


@pytest.fixture(params=["memory", "directory"])
def repo(request, tmp_path):
    return (
        MemorySessionRepository()
        if request.param == "memory"
        else DirectorySessionRepository(tmp_path)
    )


async def test_commit_is_idempotent(repo, manifest):
    store = await repo.create(manifest)
    ops = make_ops(manifest)
    assert await store.commit_tick("t1", ops, 3, counters={"b": 2}, meta={"slide_pending": False})
    assert not await store.commit_tick("t1", ops, 3, counters={"b": 2})
    assert not await store.commit_tick("t1", [], 9)
    st = await store.state()
    assert (st.last_seq, st.cursor, st.counters, st.committed_tick_ids) == (2, 3, {"b": 2}, ["t1"])
    assert [o.seq for o in await store.ops()] == [1, 2]
    assert [o.seq for o in await store.ops(after_seq=1)] == [2]


async def test_empty_tick_advances_cursor_and_is_recorded(repo, manifest):
    store = await repo.create(manifest)
    assert await store.commit_tick("t1", [], 4)
    st = await store.state()
    assert st.cursor == 4 and st.last_seq == 0 and st.committed_tick_ids == ["t1"]


async def test_commit_rejects_gaps_and_changes_nothing(repo, manifest):
    store = await repo.create(manifest)
    ops = make_ops(manifest)
    with pytest.raises(CommitConflict):
        await store.commit_tick("t1", ops[1:], 5)
    with pytest.raises(CommitConflict):
        await store.commit_tick("t1", [ops[0], ops[0]], 5)
    st = await store.state()
    assert st.cursor == 0 and st.committed_tick_ids == [] and await store.ops() == []
    assert await store.commit_tick("t1", ops, 1)  # the tick id was not burned


async def test_segments_idempotent(repo, manifest):
    store = await repo.create(manifest)
    seg = TranscriptSegment(id="s1", t0_ms=0, t1_ms=10, text="hi", lang=None, words=[])
    assert await store.append_segment(seg)
    assert not await store.append_segment(seg)
    assert len(await store.segments()) == 1


async def test_create_twice_and_missing(repo, manifest):
    await repo.create(manifest)
    with pytest.raises(SessionExists):
        await repo.create(manifest)
    with pytest.raises(SessionNotFound):
        await repo.open("nope")
    assert await repo.exists(manifest.id) and not await repo.exists("nope")


async def test_directory_reopen_and_format(tmp_path, manifest):
    repo = DirectorySessionRepository(tmp_path)
    store = await repo.create(manifest)
    ops = make_ops(manifest)
    await store.append_segment(
        TranscriptSegment(id="s1", t0_ms=0, t1_ms=10, text="hi", lang="en", words=[])
    )
    await store.commit_tick(
        "t1", ops, 1, counters={"b": 2, "d": 0, "a": 0}, rejections=[{"code": "x"}]
    )
    d = tmp_path / manifest.id
    assert sorted(p.name for p in d.iterdir()) == [
        "ops.jsonl",
        "rejections.jsonl",
        "session.json",
        "state.json",
        "transcript.jsonl",
    ]
    assert len((d / "ops.jsonl").read_text().splitlines()) == 2
    again = await DirectorySessionRepository(tmp_path).open(manifest.id)
    assert [o.seq for o in await again.ops()] == [1, 2]
    assert (await again.state()).cursor == 1
    assert not await again.commit_tick("t1", ops, 1)


async def test_directory_crash_between_ops_and_state_is_rolled_back(tmp_path, manifest):
    repo = DirectorySessionRepository(tmp_path)
    store = await repo.create(manifest)
    ops = make_ops(manifest, 4)
    await store.commit_tick("t1", ops[:2], 1, counters={"b": 2})
    # simulate a crash after ops were appended but before state.json was replaced
    with open(tmp_path / manifest.id / "ops.jsonl", "a") as f:
        from live_notes_api.models import dump_json

        f.write(dump_json(ops[2]) + "\n")
        f.write('{"seq": 4, "torn')
    reopened = await DirectorySessionRepository(tmp_path).open(manifest.id)
    assert [o.seq for o in await reopened.ops()] == [1, 2]
    # the unfinished tick can be committed again, cleanly
    assert await reopened.commit_tick("t2", ops[2:], 2, counters={"b": 4})
    lines = (tmp_path / manifest.id / "ops.jsonl").read_text().splitlines()
    assert [json.loads(line)["seq"] for line in lines] == [1, 2, 3, 4]


async def test_directory_opens_stored_fixture_without_state(tmp_path, manifest):
    dst = tmp_path / "tiny"
    shutil.copytree(TINY, dst)
    store = await DirectorySessionRepository(tmp_path).open("tiny")
    st = await store.state()
    assert st.last_seq == 2 and st.committed_tick_ids == ["u1", "u2"] and st.cursor == 0
    assert len(await store.segments()) == 6


async def test_session_id_traversal_rejected(tmp_path):
    repo = DirectorySessionRepository(tmp_path)
    with pytest.raises(SessionNotFound):
        await repo.open("../etc")
    assert not await repo.exists("../etc")
