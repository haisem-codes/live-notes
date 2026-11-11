"""The note-taking model interface and two offline implementations. No network calls here."""

from __future__ import annotations

import re
from collections import deque
from collections.abc import Callable, Iterable
from typing import Any, Protocol

from .context import TickContext
from .tools import ToolCall, parse_tool_call
from .trigger import CORRECTION_CUES


class NoteModel(Protocol):
    async def run_tick(self, context: TickContext) -> list[ToolCall]: ...


def call(name: str, **args: Any) -> ToolCall:
    """Build a parsed tool call (tests and scripted scenarios)."""
    return parse_tool_call(name, args)


class ScriptedModel:
    """Returns queued tool calls, one list per tick; an empty list once the queue runs out.
    An entry may also be a callable `(context) -> list[ToolCall]` or an Exception to raise."""

    def __init__(self, ticks: Iterable[Any] = ()) -> None:
        self.queue: deque[Any] = deque(ticks)
        self.contexts: list[TickContext] = []

    def push(self, calls: Any) -> None:
        self.queue.append(calls)

    async def run_tick(self, context: TickContext) -> list[ToolCall]:
        self.contexts.append(context)
        if not self.queue:
            return []
        item = self.queue.popleft()
        if isinstance(item, Exception):
            raise item
        if callable(item):
            return list(item(context))
        return list(item)


class HeuristicModel:
    """No LLM. Each new segment becomes a short bullet; a slide change starts a heading; a
    correction cue rewrites the previous bullet instead of adding a new one."""

    def __init__(self, max_words: int = 14, cues: tuple[str, ...] = CORRECTION_CUES) -> None:
        self.max_words = max_words
        self._cue = re.compile(r"\b(?:" + "|".join(cues) + r")\b", re.IGNORECASE)

    def _shorten(self, text: str) -> str:
        words = text.strip().split()
        return " ".join(words[: self.max_words]).rstrip(",;:- ")

    def _after_cue(self, text: str) -> str:
        last = None
        for m in self._cue.finditer(text):
            last = m
        rest = text[last.end() :] if last else text
        rest = rest.strip(" ,.;:-")
        return rest if len(rest.split()) >= 2 else text

    async def run_tick(self, context: TickContext) -> list[ToolCall]:
        calls: list[ToolCall] = []
        last: str | None = None
        for b in reversed(context.document.blocks):
            if b.kind == "bullet":
                last = b.id
                break
        slide = context.current_slide
        if context.slide_changed and slide is not None:
            page = next((p for p in context.manifest.slides if p.index == slide), None)
            title = f"Slide {slide}"
            if page:
                for r in page.regions:
                    if r.kind == "text" and r.label.strip():
                        title = self._shorten(r.label.splitlines()[0])
                        break
            calls.append(
                call(
                    "insert_block",
                    after="end",
                    kind="h2",
                    depth=0,
                    text=title,
                    src=[],
                    slide=slide,
                    ref="h",
                )
            )
        for i, seg in enumerate(context.new_segments):
            if not seg.text.strip():
                continue
            if self._cue.search(seg.text) and last is not None:
                calls.append(
                    call(
                        "update_block",
                        id=last,
                        text=self._shorten(self._after_cue(seg.text)),
                        reason="teacher_correction",
                        src=[seg.id],
                    )
                )
                continue
            ref = f"n{i}"
            calls.append(
                call(
                    "insert_block",
                    after="end",
                    kind="bullet",
                    depth=1,
                    text=self._shorten(seg.text),
                    src=[seg.id],
                    slide=slide,
                    ref=ref,
                )
            )
            last = ref
        return calls


ModelFactory = Callable[[], NoteModel]


def make_model(name: str) -> NoteModel:
    if name == "heuristic":
        return HeuristicModel()
    raise ValueError(f"unknown model {name!r} (available: heuristic)")
