from helpers import Env, call, ins

from live_notes_api.context import build_context, fmt_time, render_notes
from live_notes_api.models import TranscriptSegment


def seg(i, t0, t1, text):
    return TranscriptSegment(id=f"s{i}", t0_ms=t0, t1_ms=t1, text=text, lang=None, words=[])


def test_note_line_format(manifest):
    env = Env(manifest)
    env.tick(
        [
            ins("Gradient descent", kind="h2", depth=0),
            ins("update rule", depth=1),
            ins("eta = learning rate", kind="definition", depth=2),
            call(
                "upsert_diagram",
                id=None,
                after=None,
                title="Loop",
                src=[],
                slide=None,
                spec={"layout": "LR", "nodes": [{"id": "n", "label": "N"}], "edges": []},
            ),
        ]
    )
    env.set_status(["b1"], "frozen")
    assert render_notes(env.doc).splitlines() == [
        "[b1|h2|frozen] Gradient descent",
        "[b2|bullet.1|tentative] update rule",
        "[b3|def.2|tentative] eta = learning rate",
        "[d1|diagram|tentative] Loop (1 nodes, 0 edges)",
    ]
    assert render_notes(Env(manifest).doc) == "(empty)"


def test_time_format():
    assert fmt_time(31_070) == "00:31"
    assert fmt_time(1_867_000) == "31:07"
    assert fmt_time(3_725_000) == "1:02:05"


def test_context_order_and_content(manifest):
    env = Env(manifest)
    env.tick([ins("a", kind="h1", depth=0), call("set_slide", slide=1, confidence="high")])
    processed = [seg(1, 0, 5_000, "old, outside window"), seg(2, 200_000, 205_000, "recent one")]
    new = [seg(3, 1_867_000, 1_872_000, "brand new"), seg(4, 1_872_000, 1_880_000, "newer")]
    processed[0].t1_ms = 5_000
    ctx = build_context(
        tick_id="t3",
        now_ms=1_880_000,
        revision=True,
        slide_changed=True,
        doc=env.doc,
        manifest=manifest,
        processed=processed + [seg(5, 1_800_000, 1_850_000, "in window")],
        new=new,
    )
    blocks = ctx.user_blocks()
    heads = [b.split("\n", 1)[0] for b in blocks]
    assert heads == [
        "SLIDES",
        "NOTES",
        "SUMMARY",
        "CURRENT SLIDE",
        "RECENT TRANSCRIPT (already processed)",
    ]
    assert "slide 1: Gradient descent | regions r1:text,r2:text,r3:figure" in blocks[0]
    assert "slide 2:" in blocks[0]
    assert "[b1|h1|tentative] a" in blocks[1]
    assert "r2 [text] Update rule:  theta <- theta - eta * grad" in blocks[3]
    assert "[s5 30:00] in window" in blocks[4]
    assert "old, outside window" not in blocks[4] and "recent one" not in blocks[4]
    assert "[s3 31:07] brand new" in blocks[4] and "[s4 31:12] newer" in blocks[4]
    assert "REVISION TICK" in blocks[4]
    assert ctx.system and len(ctx.system) < 400 and len(ctx.tools) == 8


def test_context_is_deterministic(manifest):
    kw = dict(
        tick_id="t1",
        now_ms=0,
        revision=False,
        slide_changed=False,
        doc=Env(manifest).doc,
        manifest=manifest,
        processed=[],
        new=[],
    )
    a, b = build_context(**kw), build_context(**kw)
    assert a.user_blocks() == b.user_blocks() and a.user_blocks()[2] == "SUMMARY\n(none yet)"
