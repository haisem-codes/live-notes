"""Test helper: drive validate_tick across several ticks, keeping state like the actor does."""

from __future__ import annotations

from live_notes_api.model import call
from live_notes_api.models import (
    BlockStatusOp,
    BlockStatusPayload,
    NotesDocument,
    TranscriptSegment,
)
from live_notes_api.reducer import apply_op_inplace, fold
from live_notes_api.validator import Counters, TickResult, ValidatorConfig, validate_tick

SEGS = {
    f"s{i}": TranscriptSegment(
        id=f"s{i}", t0_ms=i * 1000, t1_ms=i * 1000 + 900, text=f"seg {i}", lang=None, words=[]
    )
    for i in range(1, 8)
}


class Env:
    def __init__(self, manifest, actor="agent_fast", config=None):
        self.manifest = manifest
        self.actor = actor
        self.config = config or ValidatorConfig()
        self.doc = NotesDocument()
        self.counters = Counters()
        self.last_update: dict[str, int] = {}
        self.ops: list = []
        self.n = 0

    def tick(self, calls, t=1000, actor=None) -> TickResult:
        self.n += 1
        r = validate_tick(
            session_id="x",
            tick_id=f"t{self.n}",
            actor=actor or self.actor,
            t_emit_ms=t,
            calls=calls,
            doc=self.doc,
            counters=self.counters,
            last_update_ms=self.last_update,
            segments=SEGS,
            manifest=self.manifest,
            next_seq=len(self.ops) + 1,
            config=self.config,
        )
        # the validator's working document must equal the fold of everything committed
        folded = fold(self.ops + r.ops)
        assert folded == r.doc
        self.ops += r.ops
        self.doc, self.counters, self.last_update = r.doc, r.counters, r.last_update_ms
        return r

    def set_status(self, ids, status):
        op = BlockStatusOp(
            seq=len(self.ops) + 1,
            session_id="x",
            tick_id=f"s{len(self.ops)}",
            actor="user",
            t_emit_ms=0,
            src_t0_ms=None,
            src_t1_ms=None,
            type="block.status",
            payload=BlockStatusPayload(ids=list(ids), status=status),
        )
        self.ops.append(op)
        apply_op_inplace(self.doc, op)

    def codes(self, r: TickResult) -> list[str]:
        return [x.code for x in r.rejections]


def ins(text="note", after="end", kind="bullet", depth=1, src=("s1",), ref=None, slide=None):
    return call(
        "insert_block",
        after=after,
        kind=kind,
        depth=depth,
        text=text,
        src=list(src),
        slide=slide,
        ref=ref,
    )


def upd(id, text, reason="new_detail", src=("s2",)):
    return call("update_block", id=id, text=text, reason=reason, src=list(src))


__all__ = ["Env", "apply_op_inplace", "call", "ins", "upd"]
