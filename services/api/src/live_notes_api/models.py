"""Pydantic mirror of packages/protocol/src/index.ts (protocol v0).

JSON conventions: snake_case keys, every field always present (nullable, never optional).
Always serialise with `dump()` / `dump_json()` so aliases (DiagramEdge.from) are applied.
"""

from __future__ import annotations

import json
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

BlockKind = Literal[
    "h1", "h2", "bullet", "definition", "formula", "example", "question", "callout", "diagram"
]
InsertKind = Literal[
    "h1", "h2", "bullet", "definition", "formula", "example", "question", "callout"
]
BlockStatus = Literal["tentative", "stable", "frozen", "user_locked"]
Depth = Literal[0, 1, 2]
Actor = Literal["agent_fast", "agent_slow", "agent_final", "user"]
UpdateReason = Literal[
    "new_detail",
    "teacher_correction",
    "clarification",
    "merge_duplicate",
    "fix_transcription",
    "user_edit",
]
DeleteReason = Literal["superseded", "duplicate", "teacher_retracted", "user_edit"]
AnnotationStyle = Literal["highlight", "circle", "underline"]
RegionKind = Literal["text", "figure", "part"]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


def dump(m: BaseModel) -> dict[str, Any]:
    return m.model_dump(mode="json", by_alias=True)


def dump_json(m: BaseModel) -> str:
    """Compact JSON, same shape as the golden fixtures."""
    return json.dumps(dump(m), separators=(",", ":"), ensure_ascii=False)


# --- document ---------------------------------------------------------------------------------


class DiagramNode(Model):
    id: str
    label: str


class DiagramEdge(Model):
    from_: str = Field(alias="from")
    to: str
    label: str | None


class DiagramSpec(Model):
    layout: Literal["LR", "TB"]
    nodes: list[DiagramNode]
    edges: list[DiagramEdge]


class Block(Model):
    id: str
    kind: BlockKind
    depth: Depth
    text: str
    status: BlockStatus
    src: list[str]
    slide: int | None
    rev: int
    diagram: DiagramSpec | None


class Rect(Model):
    x: float
    y: float
    w: float
    h: float


class SlideAnnotation(Model):
    id: str
    slide: int
    style: AnnotationStyle
    rects: list[Rect]
    region: str | None
    quote: str | None
    note: str | None


class ClosedSection(Model):
    heading_id: str
    summary: str


class NotesDocument(Model):
    blocks: list[Block] = Field(default_factory=list)
    annotations: list[SlideAnnotation] = Field(default_factory=list)
    current_slide: int | None = None
    sections: list[ClosedSection] = Field(default_factory=list)


# --- ops --------------------------------------------------------------------------------------


class OpEnvelope(Model):
    seq: int
    session_id: str
    tick_id: str
    actor: Actor
    t_emit_ms: int
    src_t0_ms: int | None
    src_t1_ms: int | None


class BlockInsertPayload(Model):
    id: str
    after: str | None
    kind: InsertKind
    depth: Depth
    text: str
    src: list[str]
    slide: int | None


class BlockUpdatePayload(Model):
    id: str
    text: str
    reason: UpdateReason
    src: list[str]


class BlockDeletePayload(Model):
    id: str
    reason: DeleteReason


class BlockMovePayload(Model):
    id: str
    after: str | None
    depth: Depth


class BlockStatusPayload(Model):
    ids: list[str]
    status: BlockStatus


class DiagramUpsertPayload(Model):
    id: str
    after: str | None
    title: str
    spec: DiagramSpec
    src: list[str]
    slide: int | None


class SlideAnnotationRemovePayload(Model):
    id: str


class SlideSetPayload(Model):
    slide: int
    source: Literal["user", "agent"]


class BlockInsertOp(OpEnvelope):
    type: Literal["block.insert"]
    payload: BlockInsertPayload


class BlockUpdateOp(OpEnvelope):
    type: Literal["block.update"]
    payload: BlockUpdatePayload


class BlockDeleteOp(OpEnvelope):
    type: Literal["block.delete"]
    payload: BlockDeletePayload


class BlockMoveOp(OpEnvelope):
    type: Literal["block.move"]
    payload: BlockMovePayload


class BlockStatusOp(OpEnvelope):
    type: Literal["block.status"]
    payload: BlockStatusPayload


class DiagramUpsertOp(OpEnvelope):
    type: Literal["diagram.upsert"]
    payload: DiagramUpsertPayload


class SlideAnnotateOp(OpEnvelope):
    type: Literal["slide.annotate"]
    payload: SlideAnnotation


class SlideAnnotationRemoveOp(OpEnvelope):
    type: Literal["slide.annotation.remove"]
    payload: SlideAnnotationRemovePayload


class SlideSetOp(OpEnvelope):
    type: Literal["slide.set"]
    payload: SlideSetPayload


class SectionCloseOp(OpEnvelope):
    type: Literal["section.close"]
    payload: ClosedSection


Op = Annotated[
    BlockInsertOp
    | BlockUpdateOp
    | BlockDeleteOp
    | BlockMoveOp
    | BlockStatusOp
    | DiagramUpsertOp
    | SlideAnnotateOp
    | SlideAnnotationRemoveOp
    | SlideSetOp
    | SectionCloseOp,
    Field(discriminator="type"),
]
OpAdapter: TypeAdapter[Any] = TypeAdapter(Op)


def parse_op(data: str | bytes | dict[str, Any]) -> Any:
    if isinstance(data, dict):
        return OpAdapter.validate_python(data)
    return OpAdapter.validate_json(data)


# --- transcript and session -------------------------------------------------------------------


class TranscriptWord(Model):
    w: str
    t0_ms: int
    t1_ms: int


class TranscriptSegmentIn(Model):
    """A segment as sent by the client: no id yet."""

    t0_ms: int
    t1_ms: int
    text: str
    lang: str | None
    words: list[TranscriptWord]


class TranscriptSegment(Model):
    id: str
    t0_ms: int
    t1_ms: int
    text: str
    lang: str | None
    words: list[TranscriptWord]


class SlideRegion(Model):
    id: str
    kind: RegionKind
    label: str
    rect: Rect


class SlidePage(Model):
    index: int
    image_url: str
    width: int
    height: int
    regions: list[SlideRegion]


class AudioRef(Model):
    url: str
    mime: str


class SessionManifest(Model):
    id: str
    title: str
    duration_ms: int
    audio: AudioRef | None
    slides: list[SlidePage]


# --- websocket --------------------------------------------------------------------------------


class ResumeMsg(Model):
    type: Literal["resume"]
    last_seq: int


class TranscriptFinalIn(Model):
    type: Literal["transcript.final"]
    segment: TranscriptSegmentIn


class SlideSetIn(Model):
    type: Literal["slide.set"]
    slide: int
    t_ms: int


class SessionEndIn(Model):
    type: Literal["session.end"]
    t_ms: int


ClientMessage = Annotated[
    ResumeMsg | TranscriptFinalIn | SlideSetIn | SessionEndIn, Field(discriminator="type")
]
ClientMessageAdapter: TypeAdapter[Any] = TypeAdapter(ClientMessage)


class OpMsg(Model):
    type: Literal["op"] = "op"
    op: Op


class TranscriptFinalOut(Model):
    type: Literal["transcript.final"] = "transcript.final"
    segment: TranscriptSegment


class LiveMsg(Model):
    type: Literal["live"] = "live"
    last_seq: int


class StatusMsg(Model):
    type: Literal["status"] = "status"
    state: Literal["listening", "catching_up", "ended", "server_restarting"]


class ErrorMsg(Model):
    type: Literal["error"] = "error"
    code: str
    message: str


ServerMessage = OpMsg | TranscriptFinalOut | LiveMsg | StatusMsg | ErrorMsg
