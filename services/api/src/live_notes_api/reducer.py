"""Pure, deterministic, total reducer. Semantics: see the comment block in the protocol file."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .models import Block, ClosedSection, NotesDocument


def _index(doc: NotesDocument, block_id: str) -> int:
    for i, b in enumerate(doc.blocks):
        if b.id == block_id:
            return i
    return -1


def _place(doc: NotesDocument, block: Block, after: str | None) -> None:
    """Insert directly after `after` (None = first); unknown `after` appends."""
    if after is None:
        doc.blocks.insert(0, block)
        return
    i = _index(doc, after)
    if i < 0:
        doc.blocks.append(block)
    else:
        doc.blocks.insert(i + 1, block)


def _merge_src(existing: list[str], new: list[str]) -> list[str]:
    out = list(existing)
    for s in new:
        if s not in out:
            out.append(s)
    return out


def apply_op_inplace(doc: NotesDocument, op: Any) -> None:
    """Apply `op` to `doc`, mutating it. An op that cannot apply is a no-op."""
    p = op.payload
    t = op.type
    if t == "block.insert":
        if _index(doc, p.id) >= 0:
            return
        _place(
            doc,
            Block(
                id=p.id,
                kind=p.kind,
                depth=p.depth,
                text=p.text,
                status="tentative",
                src=list(p.src),
                slide=p.slide,
                rev=1,
                diagram=None,
            ),
            p.after,
        )
    elif t == "block.update":
        i = _index(doc, p.id)
        if i < 0:
            return
        b = doc.blocks[i]
        b.text = p.text
        b.rev += 1
        b.src = _merge_src(b.src, p.src)
    elif t == "block.delete":
        i = _index(doc, p.id)
        if i >= 0:
            del doc.blocks[i]
    elif t == "block.move":
        i = _index(doc, p.id)
        if i < 0 or p.after == p.id:
            return
        if p.after is not None and _index(doc, p.after) < 0:
            return
        b = doc.blocks.pop(i)
        b.depth = p.depth
        _place(doc, b, p.after)
    elif t == "block.status":
        wanted = set(p.ids)
        for b in doc.blocks:
            if b.id in wanted:
                b.status = p.status
    elif t == "diagram.upsert":
        i = _index(doc, p.id)
        if i >= 0:
            b = doc.blocks[i]
            b.text = p.title
            b.diagram = p.spec.model_copy(deep=True)
            b.rev += 1
            b.src = _merge_src(b.src, p.src)
        else:
            _place(
                doc,
                Block(
                    id=p.id,
                    kind="diagram",
                    depth=0,
                    text=p.title,
                    status="tentative",
                    src=list(p.src),
                    slide=p.slide,
                    rev=1,
                    diagram=p.spec.model_copy(deep=True),
                ),
                p.after,
            )
    elif t == "slide.annotate":
        ann = p.model_copy(deep=True)
        for i, a in enumerate(doc.annotations):
            if a.id == ann.id:
                doc.annotations[i] = ann
                return
        doc.annotations.append(ann)
    elif t == "slide.annotation.remove":
        doc.annotations = [a for a in doc.annotations if a.id != p.id]
    elif t == "slide.set":
        doc.current_slide = p.slide
    elif t == "section.close":
        doc.sections.append(ClosedSection(heading_id=p.heading_id, summary=p.summary))


def apply_op(doc: NotesDocument, op: Any) -> NotesDocument:
    """Pure variant: returns a new document and leaves `doc` untouched."""
    new = doc.model_copy(deep=True)
    apply_op_inplace(new, op)
    return new


def fold(ops: Iterable[Any], t_ms: int | None = None) -> NotesDocument:
    """document(t) = fold(ops where t_emit_ms <= t), applied in ascending seq."""
    chosen = [o for o in ops if t_ms is None or o.t_emit_ms <= t_ms]
    chosen.sort(key=lambda o: o.seq)
    doc = NotesDocument()
    for op in chosen:
        apply_op_inplace(doc, op)
    return doc
