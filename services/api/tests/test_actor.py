import asyncio

import pytest
from conftest import seg_in, words

from live_notes_api.actor import ActorConfig, SessionActor, SessionEnded
from live_notes_api.model import HeuristicModel, ScriptedModel, call
from live_notes_api.models import dump
from live_notes_api.reducer import fold
from live_notes_api.store import MemorySessionRepository


def ins(text, after="end", kind="bullet", depth=1, src=(), ref=None):
    return call(
        "insert_block",
        after=after,
        kind=kind,
        depth=depth,
        text=text,
        src=list(src),
        slide=None,
        ref=ref,
    )


def upd(id, text, reason, src=()):
    return call("update_block", id=id, text=text, reason=reason, src=list(src))


def script():
    return [
        # t1 (slide change)
        [ins("Gradient descent", kind="h1", depth=0, ref="h")],
        # t2 (50+ words)
        [ins("minimise loss", after="b1", src=["s1"]), upd("b99", "x", "new_detail")],
        # t3 (correction cue): one accepted correction, a second update inside the dwell window
        [
            upd("b2", "minimise loss L(theta)", "teacher_correction", ["s2"]),
            upd("b2", "again", "new_detail"),
        ],
        # t4: dwell still applies; one unknown segment id is dropped
        [upd("b2", "too soon", "new_detail"), ins("lr", after="b2", src=["s3", "s999"])],
        # t5 (flush at the end)
        [ins("wrap up", src=["s4"])],
    ]


async def run(manifest, store, *, restart_after=None, repo=None):
    """Drive one scenario on a virtual clock; optionally restart the actor after a tick id."""
    now = {"t": 0}
    model = ScriptedModel(script())
    make = lambda: SessionActor(store, model, lambda: now["t"])  # noqa: E731
    actor = await make().start()
    restarted = []

    async def maybe_restart():
        nonlocal actor
        done = {r.tick_id for r in actor.ticks}
        st = await store.state()
        if (
            restart_after
            and restart_after in st.committed_tick_ids
            and restart_after not in restarted
        ):
            restarted.append(restart_after)
            actor = await make().start()
            await actor.poll()  # a fresh runtime polls straight away
        return done

    now["t"] = 0
    await actor.set_slide(1, 0)  # C -> t1
    await maybe_restart()
    now["t"] = 5_000
    await actor.add_segment(seg_in(0, 5_000, words(60)))  # A, but < 8 s since t1
    assert (await store.state()).cursor == 0
    now["t"] = 9_000
    await actor.poll()  # -> t2
    await maybe_restart()
    now["t"] = 12_000
    await actor.add_segment(
        seg_in(9_000, 12_000, "sorry I meant minimise the loss L of theta")
    )  # D -> t3
    await maybe_restart()
    now["t"] = 15_000
    await actor.add_segment(seg_in(12_000, 15_000, words(60, "x")))
    await actor.poll()  # spacing 8 s from t3 (12 s) not yet: pending
    now["t"] = 20_000
    await actor.poll()  # -> t4
    await maybe_restart()
    now["t"] = 25_000
    await actor.add_segment(seg_in(20_000, 25_000, "a few last words"))  # not enough for a tick
    now["t"] = 26_000
    await actor.end(26_000)  # flush -> t5
    return actor


@pytest.fixture
async def baseline(manifest):
    store = await MemorySessionRepository().create(manifest)
    actor = await run(manifest, store)
    return store, actor


async def test_end_to_end_scripted(baseline):
    store, actor = baseline
    ops = await store.ops()
    assert [o.seq for o in ops] == list(range(1, len(ops) + 1))
    assert [t.tick_id for t in actor.ticks] == ["t1", "t2", "t3", "t4", "t5"]
    assert [t.reason for t in actor.ticks] == ["C", "A", "D", "A", "flush"]
    assert actor.ticks[2].revision and not actor.ticks[1].revision
    assert [o.type for o in ops] == [
        "slide.set",
        "block.insert",
        "block.insert",
        "block.update",
        "block.insert",
        "block.insert",
    ]
    assert ops[0].actor == "user" and ops[0].tick_id == "u1"
    assert all(o.actor == "agent_fast" for o in ops[1:])
    # rejections recorded per tick, with reasons
    assert [[r.code for r in t.rejections] for t in actor.ticks] == [
        [],
        ["unknown_id"],
        ["dwell"],
        ["dwell"],
        [],
    ]
    # teacher-correction update accepted; src merged; unknown segment dropped
    b2 = next(b for b in actor.doc.blocks if b.id == "b2")
    assert b2.text == "minimise loss L(theta)" and b2.rev == 2 and b2.src == ["s1", "s2"]
    assert next(b for b in actor.doc.blocks if b.id == "b3").src == ["s3"]
    # folding the produced ops equals the live document, and the cursor covers all segments
    assert actor.doc == fold(ops)
    st = await store.state()
    assert st.cursor == 4 and st.ended and st.counters["b"] == 4
    assert actor.ended
    # the model saw tagged new segments only once each
    seen = [s.id for c in actor.model.contexts for s in c.new_segments]
    assert seen == ["s1", "s2", "s3", "s4"]
    with pytest.raises(SessionEnded):
        await actor.add_segment(seg_in(0, 1, "late"))


@pytest.mark.parametrize("restart_after", ["u1", "t1", "t2", "t3", "t4"])
async def test_restart_mid_session_gives_identical_log(manifest, baseline, restart_after):
    store0, _ = baseline
    store = await MemorySessionRepository().create(manifest)
    actor = await run(manifest, store, restart_after=restart_after)
    a, b = await store0.ops(), await store.ops()
    assert [dump(o) for o in a] == [dump(o) for o in b]
    assert actor.doc == fold(b)
    assert (await store0.state()).counters == (await store.state()).counters


async def test_restart_with_directory_store(tmp_path, manifest):
    from live_notes_api.store import DirectorySessionRepository

    store0 = await MemorySessionRepository().create(manifest)
    await run(manifest, store0)
    store = await DirectorySessionRepository(tmp_path).create(manifest)
    await run(manifest, store, restart_after="t2")
    reopened = await DirectorySessionRepository(tmp_path).open(manifest.id)
    assert [dump(o) for o in await reopened.ops()] == [dump(o) for o in await store0.ops()]
    assert [s.id for s in await reopened.segments()] == ["s1", "s2", "s3", "s4"]


async def test_pending_input_survives_restart(manifest):
    """Segments stored but not yet ticked are picked up by the new actor."""
    store = await MemorySessionRepository().create(manifest)
    now = {"t": 0}
    a1 = await SessionActor(store, ScriptedModel(), lambda: now["t"]).start()
    await a1.add_segment(seg_in(0, 1000, words(10)))
    await a1.set_slide(2, 1000)  # C fires immediately -> t1 consumes both
    assert (await store.state()).cursor == 1
    await a1.add_segment(seg_in(1000, 2000, words(10)))
    model = ScriptedModel([[ins("kept", src=["s2"])]])
    a2 = await SessionActor(store, model, lambda: now["t"]).start()
    now["t"] = 30_000
    await a2.poll()  # B: >= 25 s after the first pending text
    assert [s.id for s in model.contexts[0].new_segments] == ["s2"]
    assert a2.doc.blocks[0].text == "kept"


async def test_failed_tick_is_not_committed_and_is_rerun_with_same_id(manifest):
    store = await MemorySessionRepository().create(manifest)
    now = {"t": 0}
    model = ScriptedModel([RuntimeError("provider down"), [ins("ok", src=["s1"])]])
    actor = await SessionActor(store, model, lambda: now["t"]).start()
    await actor.add_segment(seg_in(0, 100, words(60)))  # A -> fails
    assert actor.errors and (await store.state()).cursor == 0 and await store.ops() == []
    now["t"] = 5_000
    assert not await actor.poll()  # backoff: not before min spacing
    now["t"] = 9_000
    assert await actor.poll()
    st = await store.state()
    assert st.committed_tick_ids == ["t1"] and st.cursor == 1 and len(await store.ops()) == 1


async def test_frozen_block_correction_flow(manifest):
    store = await MemorySessionRepository().create(manifest)
    now = {"t": 0}
    model = ScriptedModel(
        [
            [
                ins("Topic", kind="h2", depth=0, ref="h"),
                ins("fact", ref="f"),
                call("close_section", heading_id="h", summary="topic done"),
            ],
            [
                upd("b2", "fact v2", "new_detail"),
                upd("b2", "fact corrected", "teacher_correction", ["s2"]),
            ],
        ]
    )
    actor = await SessionActor(store, model, lambda: now["t"]).start()
    await actor.add_segment(seg_in(0, 100, "sorry"))  # D -> t1 ... heading refs resolve in-tick
    now["t"] = 1000
    await actor.add_segment(seg_in(500, 1000, "correction the fact differs"))  # D -> t2
    ops = await store.ops()
    assert [o.type for o in ops] == [
        "block.insert",
        "block.insert",
        "section.close",
        "block.status",
        "block.update",
    ]
    assert actor.ticks[1].rejections[0].code == "frozen_block"
    assert actor.doc.blocks[1].text == "fact corrected" and actor.doc.blocks[1].status == "frozen"


async def test_subscribers_get_ops_and_segments(manifest):
    store = await MemorySessionRepository().create(manifest)
    now = {"t": 0}
    actor = await SessionActor(store, HeuristicModel(), lambda: now["t"]).start()
    q = actor.subscribe()
    await actor.add_segment(seg_in(0, 1000, "sorry " + words(5)))
    msgs = []
    while not q.empty():
        msgs.append(q.get_nowait())
    assert [m.type for m in msgs] == ["transcript.final", "op"]
    actor.unsubscribe(q)


async def test_heuristic_model_end_to_end(manifest):
    store = await MemorySessionRepository().create(manifest)
    now = {"t": 0}
    actor = await SessionActor(store, HeuristicModel(), lambda: now["t"], ActorConfig()).start()
    await actor.set_slide(1, 0)
    now["t"] = 4000
    await actor.add_segment(
        seg_in(0, 4000, "Gradient descent minimises a loss function step by step")
    )
    now["t"] = 30_000
    await actor.poll()
    now["t"] = 31_000
    await actor.add_segment(
        seg_in(30_000, 31_000, "Sorry, I meant it follows the negative gradient")
    )
    texts = [(b.kind, b.text) for b in actor.doc.blocks]
    assert texts[0] == ("h2", "Gradient descent")
    assert texts[1][0] == "bullet" and texts[1][1] == "it follows the negative gradient"
    assert len([t for t in texts if t[0] == "bullet"]) == 1  # corrected, not duplicated
    assert actor.doc == fold(await store.ops())


async def test_concurrent_polls_are_single_flight(manifest):
    store = await MemorySessionRepository().create(manifest)
    now = {"t": 0}
    gate = asyncio.Event()
    started = []

    async def slow(ctx):
        started.append(ctx.tick_id)
        await gate.wait()
        return [ins("x", src=["s1"])]

    class Slow:
        async def run_tick(self, ctx):
            return await slow(ctx)

    actor = await SessionActor(store, Slow(), lambda: now["t"], autopoll=False).start()
    await actor.add_segment(seg_in(0, 100, words(60)))
    p1 = asyncio.create_task(actor.poll())
    await asyncio.sleep(0)
    await actor.add_segment(seg_in(100, 200, "sorry meant"))  # arrives mid-tick
    assert await actor.poll() is False  # second poll returns at once
    gate.set()
    await p1
    assert started == ["t1", "t2"]  # the D text accumulated and ran right after t1 committed
