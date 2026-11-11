"""Builds the model's working context for one tick, in stability order (most stable first, so a
provider can place cache breakpoints): rules, slide digest + region IDs, notes document, rolling
summary, current slide, recent transcript, NEW segments. Pure."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import Block, NotesDocument, SessionManifest, SlidePage, TranscriptSegment
from .tools import TOOLS

# Placeholder only: the real system prompt is owned by another engineer.
SYSTEM_RULES = (
    "You take live lecture notes by calling tools. Add short keyword-dense blocks for new points, "
    "revise a block only when the teacher corrects or clarifies it, and do nothing when there is "
    "nothing to add. Never invent block IDs or coordinates."
)

RECENT_WINDOW_MS = 90_000
KIND_ABBREV = {"definition": "def"}


def fmt_time(ms: int) -> str:
    s = max(ms, 0) // 1000
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"


def fmt_segment(seg: TranscriptSegment) -> str:
    return f"[{seg.id} {fmt_time(seg.t0_ms)}] {seg.text}"


def fmt_block(b: Block) -> str:
    kind = KIND_ABBREV.get(b.kind, b.kind)
    if b.depth and b.kind not in ("h1", "h2", "diagram"):
        kind = f"{kind}.{b.depth}"
    text = b.text
    if b.kind == "diagram" and b.diagram:
        text = f"{b.text} ({len(b.diagram.nodes)} nodes, {len(b.diagram.edges)} edges)"
    return f"[{b.id}|{kind}|{b.status}] {text}"


def render_notes(doc: NotesDocument) -> str:
    return "\n".join(fmt_block(b) for b in doc.blocks) or "(empty)"


def _first_text(page: SlidePage) -> str:
    for r in page.regions:
        if r.kind == "text" and r.label.strip():
            return r.label.strip().splitlines()[0][:80]
    return ""


def render_slide_digest(manifest: SessionManifest) -> str:
    if not manifest.slides:
        return "(no slides)"
    lines = []
    for p in manifest.slides:
        ids = ",".join(f"{r.id}:{r.kind}" for r in p.regions)
        lines.append(f"slide {p.index}: {_first_text(p) or '(no text)'} | regions {ids}")
    return "\n".join(lines)


def render_current_slide(manifest: SessionManifest, slide: int | None) -> str:
    if slide is None:
        return "(no current slide)"
    page = next((p for p in manifest.slides if p.index == slide), None)
    if page is None:
        return f"slide {slide} (not in manifest)"
    lines = [f"slide {page.index}"]
    for r in page.regions:
        lines.append(f"  {r.id} [{r.kind}] {r.label}")
    return "\n".join(lines)


def render_rolling_summary(doc: NotesDocument) -> str:
    if not doc.sections:
        return "(none yet)"
    return "\n".join(f"- {s.heading_id}: {s.summary}" for s in doc.sections)


@dataclass
class TickContext:
    tick_id: str
    now_ms: int
    revision: bool
    slide_changed: bool
    current_slide: int | None
    # structured access for models that do not use text (the fake ones)
    document: NotesDocument
    new_segments: list[TranscriptSegment]
    manifest: SessionManifest
    # rendered, stability-ordered text blocks
    system: str
    slide_digest: str
    notes: str
    summary: str
    current_slide_text: str
    recent_transcript: str
    new_transcript: str
    tools: list[dict[str, Any]] = field(default_factory=lambda: TOOLS)

    def user_blocks(self) -> list[str]:
        """The user message content blocks, most stable first."""
        flag = (
            "REVISION TICK: the teacher appears to be correcting something.\n"
            if self.revision
            else ""
        )
        return [
            f"SLIDES\n{self.slide_digest}",
            f"NOTES\n{self.notes}",
            f"SUMMARY\n{self.summary}",
            f"CURRENT SLIDE\n{self.current_slide_text}",
            f"RECENT TRANSCRIPT (already processed)\n{self.recent_transcript}\n\n"
            f"{flag}NEW TRANSCRIPT\n{self.new_transcript}",
        ]


def build_context(
    *,
    tick_id: str,
    now_ms: int,
    revision: bool,
    slide_changed: bool,
    doc: NotesDocument,
    manifest: SessionManifest,
    processed: list[TranscriptSegment],
    new: list[TranscriptSegment],
) -> TickContext:
    horizon = (new[0].t0_ms if new else now_ms) - RECENT_WINDOW_MS
    recent = [s for s in processed if s.t1_ms >= horizon]
    return TickContext(
        tick_id=tick_id,
        now_ms=now_ms,
        revision=revision,
        slide_changed=slide_changed,
        current_slide=doc.current_slide,
        document=doc,
        new_segments=list(new),
        manifest=manifest,
        system=SYSTEM_RULES,
        slide_digest=render_slide_digest(manifest),
        notes=render_notes(doc),
        summary=render_rolling_summary(doc),
        current_slide_text=render_current_slide(manifest, doc.current_slide),
        recent_transcript="\n".join(fmt_segment(s) for s in recent) or "(none)",
        new_transcript="\n".join(fmt_segment(s) for s in new) or "(none)",
    )
