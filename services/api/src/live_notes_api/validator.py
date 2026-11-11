"""Turns the tool calls of one tick into sequenced ops, or rejections with a reason.

The server is the only sequencer: IDs, seq, tick_id, actor, t_emit_ms and src spans are assigned
here, never by the model. Validation is sequential against a working copy of the document, so a
later call sees the effect of an earlier one. Rejected calls are dropped; the rest still apply.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .models import (
    Actor,
    Block,
    BlockDeleteOp,
    BlockDeletePayload,
    BlockInsertOp,
    BlockInsertPayload,
    BlockMoveOp,
    BlockMovePayload,
    BlockStatusOp,
    BlockStatusPayload,
    BlockUpdateOp,
    BlockUpdatePayload,
    ClosedSection,
    DiagramEdge,
    DiagramNode,
    DiagramSpec,
    DiagramUpsertOp,
    DiagramUpsertPayload,
    NotesDocument,
    Rect,
    SectionCloseOp,
    SessionManifest,
    SlideAnnotateOp,
    SlideAnnotation,
    SlidePage,
    SlideSetOp,
    SlideSetPayload,
    TranscriptSegment,
)
from .reducer import apply_op_inplace
from .tools import (
    AnnotateSlideCall,
    CloseSectionCall,
    DeleteBlockCall,
    InsertBlockCall,
    InvalidToolCall,
    MoveBlockCall,
    QuoteTarget,
    SetSlideCall,
    ToolCall,
    UpdateBlockCall,
    UpsertDiagramCall,
)

FROZEN_OK_REASONS = frozenset({"teacher_correction", "clarification", "fix_transcription"})
HEADINGS = {"h1": 1, "h2": 2}


@dataclass(frozen=True)
class ValidatorConfig:
    dwell_ms: int = 20_000
    max_chars_heading: int = 120
    max_chars_text: int = 400
    max_chars_summary: int = 300
    max_chars_title: int = 120
    max_chars_node_label: int = 60
    max_nodes: int = 12
    max_edges: int = 20


@dataclass
class Counters:
    b: int = 0
    d: int = 0
    a: int = 0

    def copy(self) -> Counters:
        return Counters(self.b, self.d, self.a)

    def to_dict(self) -> dict[str, int]:
        return {"b": self.b, "d": self.d, "a": self.a}

    @classmethod
    def from_dict(cls, d: Mapping[str, int]) -> Counters:
        return cls(int(d.get("b", 0)), int(d.get("d", 0)), int(d.get("a", 0)))


@dataclass(frozen=True)
class Rejection:
    index: int
    tool: str
    code: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {"index": self.index, "tool": self.tool, "code": self.code, "detail": self.detail}


@dataclass
class TickResult:
    ops: list[Any]
    rejections: list[Rejection]
    doc: NotesDocument
    counters: Counters
    last_update_ms: dict[str, int] = field(default_factory=dict)


class _Reject(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code)
        self.code = code
        self.detail = detail


# --- helpers ----------------------------------------------------------------------------------


def closed_block_ids(doc: NotesDocument) -> set[str]:
    """IDs of blocks inside closed sections. A section runs from its heading to the next h1/h2
    of the same or higher level."""
    out: set[str] = set()
    for sec in doc.sections:
        out.update(section_span(doc, sec.heading_id))
    return out


def section_span(doc: NotesDocument, heading_id: str) -> list[str]:
    idx = next((i for i, b in enumerate(doc.blocks) if b.id == heading_id), -1)
    if idx < 0:
        return []
    level = HEADINGS.get(doc.blocks[idx].kind, 99)
    ids = [doc.blocks[idx].id]
    for b in doc.blocks[idx + 1 :]:
        if HEADINGS.get(b.kind, 99) <= level:
            break
        ids.append(b.id)
    return ids


def _norm_map(text: str) -> tuple[str, list[int]]:
    """Lower-case, whitespace-collapsed, stripped text plus a map from each normalised character
    to its index in the original."""
    chars: list[str] = []
    idx: list[int] = []
    prev_space = True
    for i, ch in enumerate(text):
        if ch.isspace():
            if not prev_space:
                chars.append(" ")
                idx.append(i)
            prev_space = True
        else:
            chars.append(ch.lower())
            idx.append(i)
            prev_space = False
    while chars and chars[-1] == " ":
        chars.pop()
        idx.pop()
    return "".join(chars), idx


def normalise(text: str) -> str:
    return _norm_map(text)[0]


def resolve_quote(page: SlidePage, quote: str) -> tuple[Rect, str]:
    """Match a quote against text regions of one slide. Returns (rect, exact slide text).
    Raises _Reject for no match or an ambiguous match (never guesses)."""
    q = normalise(quote)
    if not q:
        raise _Reject("unresolved_target", "empty quote")
    hits: list[tuple[Rect, str]] = []
    for r in page.regions:
        if r.kind != "text":
            continue
        n, idx = _norm_map(r.label)
        pos = n.find(q)
        if pos >= 0:
            exact = r.label[idx[pos] : idx[pos + len(q) - 1] + 1]
            hits.append((r.rect, exact))
    if not hits:
        raise _Reject("unresolved_target", f"quote not found on slide {page.index}")
    if len(hits) > 1:
        raise _Reject("ambiguous_target", f"quote matches {len(hits)} regions")
    return hits[0]


def _dedupe(xs: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for x in xs:
        seen.setdefault(x, None)
    return list(seen)


# --- the validator ----------------------------------------------------------------------------


class _Tick:
    def __init__(
        self,
        *,
        session_id: str,
        tick_id: str,
        actor: Actor,
        t_emit_ms: int,
        doc: NotesDocument,
        counters: Counters,
        last_update_ms: Mapping[str, int],
        segments: Mapping[str, TranscriptSegment],
        manifest: SessionManifest,
        next_seq: int,
        config: ValidatorConfig,
    ) -> None:
        self.session_id = session_id
        self.tick_id = tick_id
        self.actor = actor
        self.t = t_emit_ms
        self.doc = doc.model_copy(deep=True)
        self.counters = counters.copy()
        self.last_update = dict(last_update_ms)
        self.segments = segments
        self.manifest = manifest
        self.seq = next_seq
        self.cfg = config
        self.refs: dict[str, str] = {}
        self.ops: list[Any] = []
        self.fast = actor == "agent_fast"

    # -- plumbing

    def block(self, ref_or_id: str) -> Block:
        bid = self.refs.get(ref_or_id, ref_or_id)
        for b in self.doc.blocks:
            if b.id == bid:
                return b
        raise _Reject("unknown_id", f"no block {ref_or_id!r}")

    def src(self, ids: list[str]) -> tuple[list[str], int | None, int | None]:
        known = [s for s in _dedupe(ids) if s in self.segments]
        if not known:
            return [], None, None
        return (
            known,
            min(self.segments[s].t0_ms for s in known),
            max(self.segments[s].t1_ms for s in known),
        )

    def emit(self, cls: Any, payload: Any, t0: int | None = None, t1: int | None = None) -> Any:
        op = cls(
            seq=self.seq,
            session_id=self.session_id,
            tick_id=self.tick_id,
            actor=self.actor,
            t_emit_ms=self.t,
            src_t0_ms=t0,
            src_t1_ms=t1,
            type=_TYPE[cls],
            payload=payload,
        )
        self.seq += 1
        apply_op_inplace(self.doc, op)
        self.ops.append(op)
        return op

    def after_id(self, after: str | None, *, default_end: bool = False) -> str | None:
        if after is None:
            after = "end" if default_end else "start"
        if after == "start":
            return None
        if after == "end":
            return self.doc.blocks[-1].id if self.doc.blocks else None
        return self.block(after).id

    def check_slide(self, slide: int | None) -> None:
        if slide is None or not self.manifest.slides:
            return
        if all(p.index != slide for p in self.manifest.slides):
            raise _Reject("unknown_slide", f"slide {slide} not in manifest")

    def check_text(self, text: str, kind: str) -> None:
        if not text.strip():
            raise _Reject("empty_text")
        cap = self.cfg.max_chars_heading if kind in HEADINGS else self.cfg.max_chars_text
        if len(text) > cap:
            raise _Reject("text_too_long", f"{len(text)} > {cap} chars")

    def check_editable(self, b: Block, *, reason: str | None, fast_only_frozen_block: bool) -> None:
        """Permission rules shared by update, delete and diagram edits."""
        if b.status == "user_locked":
            raise _Reject("user_locked", b.id)
        if b.status == "frozen":
            if reason is None:
                if fast_only_frozen_block and self.fast:
                    raise _Reject("frozen_block", b.id)
            elif reason not in FROZEN_OK_REASONS:
                raise _Reject("frozen_block", f"{b.id}: reason {reason} not allowed")

    def check_dwell(self, b: Block, reason: str | None) -> None:
        last = self.last_update.get(b.id)
        if (
            last is not None
            and reason != "teacher_correction"
            and self.t - last < self.cfg.dwell_ms
        ):
            raise _Reject("dwell", f"{b.id} updated {self.t - last} ms ago")

    # -- per tool

    def insert_block(self, c: InsertBlockCall) -> None:
        a = c.input
        if a.ref is not None and a.ref in self.refs:
            raise _Reject("duplicate_ref", a.ref)
        self.check_text(a.text, a.kind)
        self.check_slide(a.slide)
        after = self.after_id(a.after)
        src, t0, t1 = self.src(a.src)
        slide = a.slide if a.slide is not None else self.doc.current_slide
        self.counters.b += 1
        bid = f"b{self.counters.b}"
        self.emit(
            BlockInsertOp,
            BlockInsertPayload(
                id=bid, after=after, kind=a.kind, depth=a.depth, text=a.text, src=src, slide=slide
            ),
            t0,
            t1,
        )
        if a.ref is not None:
            self.refs[a.ref] = bid

    def update_block(self, c: UpdateBlockCall) -> None:
        a = c.input
        b = self.block(a.id)
        self.check_editable(b, reason=a.reason, fast_only_frozen_block=False)
        self.check_text(a.text, b.kind)
        if a.text == b.text:
            raise _Reject("no_change", b.id)
        self.check_dwell(b, a.reason)
        src, t0, t1 = self.src(a.src)
        self.emit(
            BlockUpdateOp,
            BlockUpdatePayload(id=b.id, text=a.text, reason=a.reason, src=src),
            t0,
            t1,
        )
        self.last_update[b.id] = self.t

    def delete_block(self, c: DeleteBlockCall) -> None:
        b = self.block(c.input.id)
        self.check_editable(b, reason=None, fast_only_frozen_block=True)
        self.emit(BlockDeleteOp, BlockDeletePayload(id=b.id, reason=c.input.reason))

    def move_block(self, c: MoveBlockCall) -> None:
        a = c.input
        b = self.block(a.id)
        self.check_editable(b, reason=None, fast_only_frozen_block=True)
        after = self.after_id(a.after)
        if after == b.id:
            raise _Reject("invalid_target", "cannot move a block after itself")
        if b.kind == "diagram" and a.depth != 0:
            raise _Reject("invalid_depth", "diagram blocks are depth 0")
        if self.fast:
            closed = closed_block_ids(self.doc)
            if b.id in closed or (after in closed if after is not None else bool(closed)):
                raise _Reject("outside_active_section", b.id)
        self.emit(BlockMoveOp, BlockMovePayload(id=b.id, after=after, depth=a.depth))

    def upsert_diagram(self, c: UpsertDiagramCall) -> None:
        a = c.input
        self.check_text(a.title, "h2")
        if not 1 <= len(a.spec.nodes) <= self.cfg.max_nodes:
            raise _Reject("diagram_too_large", f"{len(a.spec.nodes)} nodes")
        if len(a.spec.edges) > self.cfg.max_edges:
            raise _Reject("diagram_too_large", f"{len(a.spec.edges)} edges")
        ids = [n.id for n in a.spec.nodes]
        if len(set(ids)) != len(ids):
            raise _Reject("diagram_invalid", "duplicate node ids")
        for n in a.spec.nodes:
            if not n.id or not n.label.strip() or len(n.label) > self.cfg.max_chars_node_label:
                raise _Reject("diagram_invalid", f"bad node {n.id!r}")
        for e in a.spec.edges:
            if e.from_ not in ids or e.to not in ids:
                raise _Reject("diagram_invalid", f"edge {e.from_}->{e.to} has unknown endpoint")
        spec = DiagramSpec(
            layout=a.spec.layout,
            nodes=[DiagramNode(id=n.id, label=n.label) for n in a.spec.nodes],
            edges=[DiagramEdge(from_=e.from_, to=e.to, label=e.label) for e in a.spec.edges],
        )
        src, t0, t1 = self.src(a.src)
        if a.id is not None:
            b = self.block(a.id)
            if b.kind != "diagram":
                raise _Reject("not_a_diagram", b.id)
            self.check_editable(b, reason=None, fast_only_frozen_block=True)
            self.check_dwell(b, None)
            payload = DiagramUpsertPayload(
                id=b.id, after=None, title=a.title, spec=spec, src=src, slide=b.slide
            )
            self.emit(DiagramUpsertOp, payload, t0, t1)
            self.last_update[b.id] = self.t
            return
        self.check_slide(a.slide)
        after = self.after_id(a.after, default_end=True)
        self.counters.d += 1
        slide = a.slide if a.slide is not None else self.doc.current_slide
        self.emit(
            DiagramUpsertOp,
            DiagramUpsertPayload(
                id=f"d{self.counters.d}",
                after=after,
                title=a.title,
                spec=spec,
                src=src,
                slide=slide,
            ),
            t0,
            t1,
        )

    def annotate_slide(self, c: AnnotateSlideCall) -> None:
        a = c.input
        page = next((p for p in self.manifest.slides if p.index == a.slide), None)
        if page is None:
            raise _Reject("unknown_slide", f"slide {a.slide}")
        region: str | None = None
        quote: str | None = None
        if isinstance(a.target, QuoteTarget):
            rect, quote = resolve_quote(page, a.target.quote)
        else:
            reg = next((r for r in page.regions if r.id == a.target.region), None)
            if reg is None:
                raise _Reject(
                    "unresolved_target", f"no region {a.target.region!r} on slide {a.slide}"
                )
            rect, region = reg.rect, reg.id
        note_block = self.block(a.note) if a.note is not None else None
        t0 = t1 = None
        if note_block is not None:
            _, t0, t1 = self.src(note_block.src)
        self.counters.a += 1
        self.emit(
            SlideAnnotateOp,
            SlideAnnotation(
                id=f"a{self.counters.a}",
                slide=a.slide,
                style=a.style,
                rects=[rect.model_copy()],
                region=region,
                quote=quote,
                note=note_block.id if note_block else None,
            ),
            t0,
            t1,
        )

    def set_slide(self, c: SetSlideCall) -> None:
        a = c.input
        self.check_slide(a.slide)
        if a.confidence != "high":
            raise _Reject("low_confidence")
        if self.doc.current_slide == a.slide:
            raise _Reject("no_change")
        self.emit(SlideSetOp, SlideSetPayload(slide=a.slide, source="agent"))

    def close_section(self, c: CloseSectionCall) -> None:
        a = c.input
        h = self.block(a.heading_id)
        if h.kind not in HEADINGS:
            raise _Reject("not_a_heading", h.id)
        if any(s.heading_id == h.id for s in self.doc.sections):
            raise _Reject("already_closed", h.id)
        if not a.summary.strip():
            raise _Reject("empty_text")
        if len(a.summary) > self.cfg.max_chars_summary:
            raise _Reject("text_too_long", "summary")
        self.emit(SectionCloseOp, ClosedSection(heading_id=h.id, summary=a.summary))
        by_id = {b.id: b for b in self.doc.blocks}
        freeze = [i for i in section_span(self.doc, h.id) if by_id[i].status != "user_locked"]
        if freeze:
            self.emit(BlockStatusOp, BlockStatusPayload(ids=freeze, status="frozen"))

    def run(self, index: int, call: ToolCall) -> Rejection | None:
        mark = (
            len(self.ops),
            self.seq,
            self.counters.copy(),
            dict(self.refs),
            dict(self.last_update),
        )
        try:
            if isinstance(call, InvalidToolCall):
                raise _Reject("invalid_arguments", call.error)
            getattr(self, call.name)(call)
            return None
        except _Reject as r:
            # A handler may have emitted nothing before failing; keep state consistent anyway.
            assert len(self.ops) == mark[0], "handler emitted ops and then rejected"
            return Rejection(index, call.name, r.code, r.detail)


_TYPE: dict[Any, str] = {
    BlockInsertOp: "block.insert",
    BlockUpdateOp: "block.update",
    BlockDeleteOp: "block.delete",
    BlockMoveOp: "block.move",
    BlockStatusOp: "block.status",
    DiagramUpsertOp: "diagram.upsert",
    SlideAnnotateOp: "slide.annotate",
    SlideSetOp: "slide.set",
    SectionCloseOp: "section.close",
}


def validate_tick(
    *,
    session_id: str,
    tick_id: str,
    actor: Actor,
    t_emit_ms: int,
    calls: list[ToolCall],
    doc: NotesDocument,
    counters: Counters,
    last_update_ms: Mapping[str, int],
    segments: Mapping[str, TranscriptSegment],
    manifest: SessionManifest,
    next_seq: int,
    config: ValidatorConfig | None = None,
) -> TickResult:
    """Validate one tick's tool calls. `doc`, `counters` and `last_update_ms` are not mutated; the
    result carries their new values (valid only if the caller commits the ops)."""
    t = _Tick(
        session_id=session_id,
        tick_id=tick_id,
        actor=actor,
        t_emit_ms=t_emit_ms,
        doc=doc,
        counters=counters,
        last_update_ms=last_update_ms,
        segments=segments,
        manifest=manifest,
        next_seq=next_seq,
        config=config or ValidatorConfig(),
    )
    rejections = [r for i, c in enumerate(calls) if (r := t.run(i, c)) is not None]
    return TickResult(t.ops, rejections, t.doc, t.counters, t.last_update)


def user_slide_op(
    *, session_id: str, tick_id: str, t_emit_ms: int, slide: int, seq: int
) -> SlideSetOp:
    return SlideSetOp(
        seq=seq,
        session_id=session_id,
        tick_id=tick_id,
        actor="user",
        t_emit_ms=t_emit_ms,
        src_t0_ms=None,
        src_t1_ms=None,
        type="slide.set",
        payload=SlideSetPayload(slide=slide, source="user"),
    )
