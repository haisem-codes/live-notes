"""Tool definitions given to the note-taking model (Anthropic Messages API tool format) and the
typed Python models for a parsed tool call.

Strict mode: every property is required and `additionalProperties` is false, so optional
arguments are expressed as nullable. The model never supplies block IDs for new blocks (only a
local `ref` alias) and never supplies coordinates.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from .models import AnnotationStyle, Depth, InsertKind

UpdateToolReason = Literal[
    "new_detail", "teacher_correction", "clarification", "merge_duplicate", "fix_transcription"
]
DeleteToolReason = Literal["superseded", "duplicate", "teacher_retracted"]
KINDS = ["h1", "h2", "bullet", "definition", "formula", "example", "question", "callout"]

_SRC = {
    "type": "array",
    "items": {"type": "string"},
    "description": 'Transcript segment IDs that justify this, e.g. ["s412"]',
}
_AFTER_DESC = (
    "Block ID exactly as shown in the notes, a `ref` from an earlier call in this response, "
    '"start" (first) or "end" (last).'
)
_NULLABLE_STR = {"type": ["string", "null"]}


def _tool(name: str, description: str, properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "strict": True,
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": list(properties),
            "properties": properties,
        },
    }


TOOLS: list[dict[str, Any]] = [
    _tool(
        "insert_block",
        "Add ONE new note block. The server assigns its ID. Use for each new point the teacher "
        "makes. Keep text keyword-dense, at most 40 words.",
        {
            "after": {"type": "string", "description": _AFTER_DESC},
            "kind": {"type": "string", "enum": KINDS},
            "depth": {"type": "integer", "enum": [0, 1, 2]},
            "text": {"type": "string", "description": "Inline markdown, LaTeX in $...$."},
            "src": _SRC,
            "slide": {"type": ["integer", "null"], "description": "1-based slide number or null."},
            "ref": {
                **_NULLABLE_STR,
                "description": "Optional local alias (e.g. 'h') later calls in this response "
                "may use as a block ID. Null if not needed.",
            },
        },
    ),
    _tool(
        "update_block",
        "Replace the text of ONE existing note block. Use when the teacher corrects or "
        "clarifies something already noted, or to add a detail to a recent block. Do not use to "
        "rephrase a block whose meaning has not changed.",
        {
            "id": {"type": "string", "description": "Block ID as shown in the notes, e.g. b17."},
            "text": {"type": "string", "description": "Full new text. Keyword-dense, <= 40 words."},
            "reason": {
                "type": "string",
                "enum": [
                    "new_detail",
                    "teacher_correction",
                    "clarification",
                    "merge_duplicate",
                    "fix_transcription",
                ],
            },
            "src": _SRC,
        },
    ),
    _tool(
        "delete_block",
        "Remove ONE note block that was wrong, retracted or duplicated.",
        {
            "id": {"type": "string", "description": "Block ID as shown in the notes."},
            "reason": {"type": "string", "enum": ["superseded", "duplicate", "teacher_retracted"]},
        },
    ),
    _tool(
        "move_block",
        "Move ONE block to sit directly after another block and set its indent. The fast lane may "
        "only move blocks inside the current (unclosed) section.",
        {
            "id": {"type": "string"},
            "after": {"type": "string", "description": _AFTER_DESC},
            "depth": {"type": "integer", "enum": [0, 1, 2]},
        },
    ),
    _tool(
        "upsert_diagram",
        "Create or replace a diagram as a small graph (max 12 nodes, 20 edges). To change an "
        "existing diagram pass its block ID in `id`; to create one pass `id` null and `after`.",
        {
            "id": {**_NULLABLE_STR, "description": "Existing diagram block ID, or null to create."},
            "after": {
                **_NULLABLE_STR,
                "description": _AFTER_DESC + " Only used when creating. Null = end.",
            },
            "title": {"type": "string"},
            "spec": {
                "type": "object",
                "additionalProperties": False,
                "required": ["layout", "nodes", "edges"],
                "properties": {
                    "layout": {"type": "string", "enum": ["LR", "TB"]},
                    "nodes": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["id", "label"],
                            "properties": {"id": {"type": "string"}, "label": {"type": "string"}},
                        },
                    },
                    "edges": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["from", "to", "label"],
                            "properties": {
                                "from": {"type": "string"},
                                "to": {"type": "string"},
                                "label": _NULLABLE_STR,
                            },
                        },
                    },
                },
            },
            "src": _SRC,
            "slide": {"type": ["integer", "null"]},
        },
    ),
    _tool(
        "annotate_slide",
        "Mark part of a slide. Name a region ID from the slide's region list, or quote text that "
        "appears on the slide. Never give coordinates. Unresolvable targets are dropped.",
        {
            "slide": {"type": "integer", "description": "1-based slide number."},
            "target": {
                "anyOf": [
                    {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["region"],
                        "properties": {"region": {"type": "string", "description": "e.g. r4"}},
                    },
                    {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["quote"],
                        "properties": {
                            "quote": {"type": "string", "description": "Text on slide."}
                        },
                    },
                ]
            },
            "style": {"type": "string", "enum": ["highlight", "circle", "underline"]},
            "note": {**_NULLABLE_STR, "description": "Block ID (or ref) of the linked note."},
        },
    ),
    _tool(
        "set_slide",
        "Report which slide the teacher is on. Only used when the student is not flipping slides "
        "manually; low-confidence reports are ignored.",
        {
            "slide": {"type": "integer"},
            "confidence": {"type": "string", "enum": ["low", "high"]},
        },
    ),
    _tool(
        "close_section",
        "Signal that the teacher finished a topic. `heading_id` is the h1/h2 block that opened it.",
        {
            "heading_id": {"type": "string"},
            "summary": {"type": "string", "description": "At most 30 words."},
        },
    ),
]

TOOL_NAMES = [t["name"] for t in TOOLS]


# --- typed calls ------------------------------------------------------------------------------


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InsertBlockArgs(_Args):
    after: str
    kind: InsertKind
    depth: Depth
    text: str
    src: list[str]
    slide: int | None = None
    ref: str | None = None


class UpdateBlockArgs(_Args):
    id: str
    text: str
    reason: UpdateToolReason
    src: list[str]


class DeleteBlockArgs(_Args):
    id: str
    reason: DeleteToolReason


class MoveBlockArgs(_Args):
    id: str
    after: str
    depth: Depth


class DiagramNodeArgs(_Args):
    id: str
    label: str


class DiagramEdgeArgs(_Args):
    from_: str = Field(alias="from")
    to: str
    label: str | None = None


class DiagramSpecArgs(_Args):
    layout: Literal["LR", "TB"]
    nodes: list[DiagramNodeArgs]
    edges: list[DiagramEdgeArgs]


class UpsertDiagramArgs(_Args):
    id: str | None = None
    after: str | None = None
    title: str
    spec: DiagramSpecArgs
    src: list[str]
    slide: int | None = None


class RegionTarget(_Args):
    region: str


class QuoteTarget(_Args):
    quote: str


class AnnotateSlideArgs(_Args):
    slide: int
    target: RegionTarget | QuoteTarget
    style: AnnotationStyle
    note: str | None = None


class SetSlideArgs(_Args):
    slide: int
    confidence: Literal["low", "high"]


class CloseSectionArgs(_Args):
    heading_id: str
    summary: str


class _Call(BaseModel):
    model_config = ConfigDict(extra="forbid")
    call_id: str | None = None


class InsertBlockCall(_Call):
    name: Literal["insert_block"] = "insert_block"
    input: InsertBlockArgs


class UpdateBlockCall(_Call):
    name: Literal["update_block"] = "update_block"
    input: UpdateBlockArgs


class DeleteBlockCall(_Call):
    name: Literal["delete_block"] = "delete_block"
    input: DeleteBlockArgs


class MoveBlockCall(_Call):
    name: Literal["move_block"] = "move_block"
    input: MoveBlockArgs


class UpsertDiagramCall(_Call):
    name: Literal["upsert_diagram"] = "upsert_diagram"
    input: UpsertDiagramArgs


class AnnotateSlideCall(_Call):
    name: Literal["annotate_slide"] = "annotate_slide"
    input: AnnotateSlideArgs


class SetSlideCall(_Call):
    name: Literal["set_slide"] = "set_slide"
    input: SetSlideArgs


class CloseSectionCall(_Call):
    name: Literal["close_section"] = "close_section"
    input: CloseSectionArgs


class InvalidToolCall(_Call):
    """A call the model made that does not parse (unknown tool or bad arguments)."""

    name: str
    input: Any
    error: str


ValidToolCall = Annotated[
    InsertBlockCall
    | UpdateBlockCall
    | DeleteBlockCall
    | MoveBlockCall
    | UpsertDiagramCall
    | AnnotateSlideCall
    | SetSlideCall
    | CloseSectionCall,
    Field(discriminator="name"),
]
ToolCall = (
    InsertBlockCall
    | UpdateBlockCall
    | DeleteBlockCall
    | MoveBlockCall
    | UpsertDiagramCall
    | AnnotateSlideCall
    | SetSlideCall
    | CloseSectionCall
    | InvalidToolCall
)
_adapter: TypeAdapter[Any] = TypeAdapter(ValidToolCall)


def parse_tool_call(name: str, args: Any, call_id: str | None = None) -> ToolCall:
    """Parse one raw tool_use block. Never raises: bad calls become InvalidToolCall."""
    try:
        if name not in TOOL_NAMES:
            raise ValueError(f"unknown tool {name!r}")
        return _adapter.validate_python({"name": name, "input": args, "call_id": call_id})
    except (ValidationError, ValueError) as e:
        return InvalidToolCall(name=name, input=args, error=str(e)[:300], call_id=call_id)
