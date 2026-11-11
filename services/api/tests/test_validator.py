import pytest
from helpers import Env, call, ins, upd

from live_notes_api.tools import parse_tool_call
from live_notes_api.validator import ValidatorConfig


@pytest.fixture
def env(manifest):
    return Env(manifest)


def test_ids_seq_and_envelope_assigned_by_server(env):
    r = env.tick([ins("first", src=["s1", "s3"]), ins("second", src=["s2"])], t=5000)
    assert not r.rejections
    assert [o.payload.id for o in r.ops] == ["b1", "b2"]
    assert [o.seq for o in r.ops] == [1, 2]
    o = r.ops[0]
    assert (o.tick_id, o.actor, o.t_emit_ms, o.session_id) == ("t1", "agent_fast", 5000, "x")
    # span of cited segments: s1 [1000, 1900], s3 [3000, 3900]
    assert (o.src_t0_ms, o.src_t1_ms) == (1000, 3900)
    r2 = env.tick([ins("third")], t=30000)
    assert r2.ops[0].payload.id == "b3" and r2.ops[0].seq == 3


def test_ids_never_reused_after_rejection(env):
    env.tick([ins("a")])
    r = env.tick([ins(""), ins("b")])
    assert env.codes(r) == ["empty_text"]
    assert r.ops[0].payload.id == "b2"


def test_unknown_segment_ids_dropped_from_src(env):
    r = env.tick([ins("a", src=["s1", "s999", "s1"])])
    assert r.ops[0].payload.src == ["s1"]
    r = env.tick([ins("b", src=["s999"])])
    assert r.ops[0].payload.src == [] and r.ops[0].src_t0_ms is None


def test_refs_resolve_within_tick_only(env):
    r = env.tick(
        [
            ins("heading", kind="h2", depth=0, ref="h"),
            ins("child", after="h", ref="c"),
            upd("c", "child revised"),
            ins("again", ref="h"),  # duplicate ref
        ]
    )
    assert env.codes(r) == ["duplicate_ref"]
    assert [o.type for o in r.ops] == ["block.insert", "block.insert", "block.update"]
    assert r.ops[1].payload.after == "b1" and r.ops[2].payload.id == "b2"
    r2 = env.tick([upd("c", "x", "teacher_correction")], t=2000)
    assert env.codes(r2) == ["unknown_id"]  # refs do not survive the tick


def test_insert_positions_and_unknown_after(env):
    env.tick([ins("a"), ins("b")])
    r = env.tick([ins("front", after="start"), ins("mid", after="b1"), ins("bad", after="b77")])
    assert env.codes(r) == ["unknown_id"]
    assert [b.text for b in env.doc.blocks] == ["front", "a", "mid", "b"]


def test_text_caps_and_kinds(env):
    r = env.tick([ins("x" * 401), ins("h" * 121, kind="h2", depth=0), ins("   ")])
    assert env.codes(r) == ["text_too_long", "text_too_long", "empty_text"]


def test_invalid_and_unknown_tool_calls_rejected(env):
    bad = parse_tool_call("insert_block", {"after": "end"})
    unknown = parse_tool_call("drop_table", {})
    r = env.tick([bad, unknown, ins("ok")])
    assert env.codes(r) == ["invalid_arguments", "invalid_arguments"]
    assert len(r.ops) == 1


def test_update_unknown_id_and_no_change(env):
    env.tick([ins("a")])
    r = env.tick([upd("b9", "x"), upd("b1", "a")])
    assert env.codes(r) == ["unknown_id", "no_change"]


def test_user_locked_never_changed_by_agents(env):
    env.tick([ins("a"), ins("b")])
    env.set_status(["b1", "b2"], "user_locked")
    for actor in ("agent_fast", "agent_slow"):
        r = env.tick(
            [
                upd("b1", "z", "teacher_correction"),
                call("delete_block", id="b1", reason="duplicate"),
                call("move_block", id="b1", after="b2", depth=1),
            ],
            actor=actor,
        )
        assert env.codes(r) == ["user_locked"] * 3 and not r.ops


def test_frozen_update_reasons(env):
    env.tick([ins("a")])
    env.set_status(["b1"], "frozen")
    r = env.tick([upd("b1", "x1", "new_detail"), upd("b1", "x2", "merge_duplicate")], t=100000)
    assert env.codes(r) == ["frozen_block", "frozen_block"]
    for i, reason in enumerate(["teacher_correction", "clarification", "fix_transcription"]):
        r = env.tick([upd("b1", f"ok{i}", reason)], t=200000 + i * 50000)
        assert not r.rejections, reason


def test_frozen_not_deletable_or_movable_by_fast_lane(env):
    env.tick([ins("a"), ins("b")])
    env.set_status(["b1"], "frozen")
    r = env.tick(
        [
            call("delete_block", id="b1", reason="duplicate"),
            call("move_block", id="b1", after="b2", depth=1),
        ]
    )
    assert env.codes(r) == ["frozen_block", "frozen_block"]
    r = env.tick([call("delete_block", id="b1", reason="duplicate")], actor="agent_slow")
    assert not r.rejections and [b.id for b in env.doc.blocks] == ["b2"]


def test_dwell_time(env):
    env.tick([ins("a")], t=0)
    assert not env.tick([upd("b1", "v1")], t=1000).rejections
    r = env.tick([upd("b1", "v2")], t=15000)  # 14 s later
    assert env.codes(r) == ["dwell"]
    assert not env.tick([upd("b1", "v2c", "teacher_correction")], t=15000).rejections
    assert not env.tick([upd("b1", "v3")], t=35001).rejections  # >= 20 s after the last update


def test_dwell_two_updates_in_one_tick(env):
    env.tick([ins("a")], t=0)
    r = env.tick([upd("b1", "v1"), upd("b1", "v2")], t=1000)
    assert env.codes(r) == ["dwell"]


def test_move_rules_active_section(env):
    env.tick(
        [
            ins("H1", kind="h2", depth=0),
            ins("a"),
            ins("b"),
            ins("H2", kind="h2", depth=0),
            ins("c"),
            ins("d"),
        ]
    )
    # close the first section (b1..b3) -> frozen, outside the active section
    r = env.tick([call("close_section", heading_id="b1", summary="first part")])
    assert not r.rejections
    assert [o.type for o in r.ops] == ["section.close", "block.status"]
    assert r.ops[1].payload.ids == ["b1", "b2", "b3"]
    # fast lane: moves inside the active section ok, into/out of the closed one not
    ok = env.tick([call("move_block", id="b6", after="b5", depth=2)])
    assert not ok.rejections
    bad = env.tick(
        [
            call("move_block", id="b5", after="b2", depth=1),  # target inside closed section
            call("move_block", id="b2", after="b6", depth=1),  # source is closed (and frozen)
            call("move_block", id="b5", after="start", depth=1),  # before the closed section
            call("move_block", id="b5", after="b5", depth=1),
        ]
    )
    assert env.codes(bad) == [
        "outside_active_section",
        "frozen_block",
        "outside_active_section",
        "invalid_target",
    ]
    # slow lane may move anywhere that is not locked/frozen
    env.set_status(["b1", "b2", "b3"], "stable")
    assert not env.tick(
        [call("move_block", id="b5", after="b2", depth=1)], actor="agent_slow"
    ).rejections


def test_close_section_rules(env):
    env.tick([ins("H", kind="h1", depth=0), ins("a")])
    r = env.tick([call("close_section", heading_id="b2", summary="s")])
    assert env.codes(r) == ["not_a_heading"]
    assert not env.tick([call("close_section", heading_id="b1", summary="s")]).rejections
    assert env.codes(env.tick([call("close_section", heading_id="b1", summary="s")])) == [
        "already_closed"
    ]
    assert env.codes(env.tick([call("close_section", heading_id="zz", summary="s")])) == [
        "unknown_id"
    ]
    assert env.doc.sections[0].heading_id == "b1"
    assert {b.status for b in env.doc.blocks} == {"frozen"}


def _diagram(nodes=("n1", "n2"), edges=(("n1", "n2"),), **kw):
    return call(
        "upsert_diagram",
        id=kw.get("id"),
        after=kw.get("after"),
        title=kw.get("title", "Loop"),
        spec={
            "layout": "LR",
            "nodes": [{"id": n, "label": n.upper()} for n in nodes],
            "edges": [{"from": a, "to": b, "label": None} for a, b in edges],
        },
        src=["s1"],
        slide=None,
    )


def test_diagram_validation(env):
    ok = env.tick([_diagram()])
    assert not ok.rejections and ok.ops[0].payload.id == "d1"
    many = [f"n{i}" for i in range(13)]
    r = env.tick(
        [
            _diagram(nodes=("n1", "n1")),
            _diagram(edges=(("n1", "zz"),)),
            _diagram(nodes=many, edges=()),
            _diagram(nodes=("n1", "n2"), edges=[("n1", "n2")] * 21),
            _diagram(nodes=()),
        ]
    )
    assert env.codes(r) == [
        "diagram_invalid",
        "diagram_invalid",
        "diagram_too_large",
        "diagram_too_large",
        "diagram_too_large",
    ]
    assert not env.tick(
        [_diagram(nodes=[f"n{i}" for i in range(12)], edges=[("n0", "n1")] * 20)], t=99999
    ).rejections


def test_diagram_update_existing(env):
    env.tick([ins("a"), _diagram()], t=0)
    r = env.tick([_diagram(id="d1", title="v2")], t=30000)
    assert not r.rejections and env.doc.blocks[-1].rev == 2 and env.doc.blocks[-1].text == "v2"
    r = env.tick([_diagram(id="d1", title="v3"), _diagram(id="b1"), _diagram(id="d9")], t=31000)
    assert env.codes(r) == ["dwell", "not_a_diagram", "unknown_id"]
    env.set_status(["d1"], "frozen")
    assert env.codes(env.tick([_diagram(id="d1", title="v4")], t=90000)) == ["frozen_block"]
    assert not env.tick([_diagram(id="d1", title="v4")], t=90000, actor="agent_slow").rejections


def test_annotate_region_and_quote(env):
    env.tick([ins("rule")])
    r = env.tick(
        [
            call("annotate_slide", slide=1, target={"region": "r2"}, style="highlight", note="b1"),
            call(
                "annotate_slide",
                slide=1,
                target={"quote": "  THETA <- theta"},
                style="underline",
                note=None,
            ),
            call(
                "annotate_slide",
                slide=1,
                target={"quote": "update rule:  theta"},
                style="circle",
                note=None,
            ),
        ]
    )
    assert not r.rejections
    a1, a2, a3 = (o.payload for o in r.ops)
    assert (a1.id, a1.region, a1.quote, a1.note) == ("a1", "r2", None, "b1")
    assert a1.rects[0].x == 0.1 and a1.rects[0].y == 0.3
    assert a2.region is None and a2.quote == "theta <- theta" and a2.rects == a1.rects
    assert a3.quote == "Update rule:  theta"  # exact slide text, original whitespace
    assert r.ops[0].src_t0_ms == 1000  # span borrowed from the linked note's segments


def test_annotate_rejections_never_guess(env):
    env.tick([ins("rule")])

    def ann(slide, target, note=None):
        return call("annotate_slide", slide=slide, target=target, style="highlight", note=note)

    r = env.tick(
        [
            ann(1, {"region": "r9"}),
            ann(2, {"region": "r2"}),  # r2 exists only on slide 1
            ann(1, {"quote": "not on the slide"}),
            ann(1, {"quote": "loss curve"}),  # figure regions are not text
            ann(1, {"quote": "   "}),
            ann(7, {"region": "r1"}),
            ann(1, {"region": "r1"}, note="b9"),
            ann(1, {"quote": "e"}),  # ambiguous: matches r1 and r2
        ]
    )
    assert env.codes(r) == [
        "unresolved_target",
        "unresolved_target",
        "unresolved_target",
        "unresolved_target",
        "unresolved_target",
        "unknown_slide",
        "unknown_id",
        "ambiguous_target",
    ]
    assert not r.ops and env.counters.a == 0


def test_set_slide(env):
    r = env.tick(
        [
            call("set_slide", slide=2, confidence="low"),
            call("set_slide", slide=9, confidence="high"),
            call("set_slide", slide=2, confidence="high"),
            call("set_slide", slide=2, confidence="high"),
        ]
    )
    assert env.codes(r) == ["low_confidence", "unknown_slide", "no_change"]
    assert r.ops[0].payload.source == "agent" and env.doc.current_slide == 2


def test_insert_defaults_slide_to_current_and_checks_manifest(env):
    env.tick([call("set_slide", slide=2, confidence="high")])
    r = env.tick([ins("a"), ins("b", slide=1), ins("c", slide=5)])
    assert env.codes(r) == ["unknown_slide"]
    assert [o.payload.slide for o in r.ops] == [2, 1]


def test_rejected_calls_dropped_rest_still_apply(env):
    r = env.tick([ins("a"), upd("nope", "x"), ins("b"), upd("b2", "b!")])
    assert env.codes(r) == ["unknown_id"]
    assert [o.type for o in r.ops] == ["block.insert", "block.insert", "block.update"]
    assert env.doc.blocks[1].text == "b!"


def test_custom_dwell_config(manifest):
    e = Env(manifest, config=ValidatorConfig(dwell_ms=0))
    e.tick([ins("a")])
    assert not e.tick([upd("b1", "x")], t=1).rejections
    assert not e.tick([upd("b1", "y")], t=2).rejections
