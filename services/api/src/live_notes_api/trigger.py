"""Tick trigger policy. Pure: no sleeping, no wall clock. Every method that needs the time takes
`now_ms` (audio/session milliseconds) from the caller.

Fire when no tick is in flight AND any of
  A  >= words_threshold unprocessed words (evaluated when a final segment has just ended)
  B  >= max_gap_ms since the last tick start and any unprocessed words
  C  a slide change is pending
  D  a correction cue is in the new text -> immediately, flagged as a revision tick
with >= min_spacing_ms between tick starts (D is exempt). `flush` (session end) fires like D but
is not flagged as a revision.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

CORRECTION_CUES: tuple[str, ...] = (
    "sorry",
    "i meant",
    "correction",
    "that should be",
    "let me rephrase",
    "actually,? no",
)


@dataclass(frozen=True)
class TriggerConfig:
    words_threshold: int = 50
    max_gap_ms: int = 25_000
    min_spacing_ms: int = 8_000
    cues: tuple[str, ...] = CORRECTION_CUES

    def cue_regex(self) -> re.Pattern[str]:
        return re.compile(r"\b(?:" + "|".join(self.cues) + r")\b", re.IGNORECASE)


@dataclass(frozen=True)
class Decision:
    reason: str  # "A" | "B" | "C" | "D" | "flush"
    revision: bool


@dataclass(frozen=True)
class Pending:
    """What a started tick consumed; handed back to `abort_tick` if the tick fails."""

    words: int
    slide: bool
    cue: bool
    flush: bool
    first_ms: int | None


class TriggerPolicy:
    def __init__(self, config: TriggerConfig | None = None) -> None:
        self.cfg = config or TriggerConfig()
        self._cue = self.cfg.cue_regex()
        self.words = 0
        self.slide_pending = False
        self.cue_pending = False
        self.flush_pending = False
        self.in_flight = False
        self.last_start_ms: int | None = None
        self.first_pending_ms: int | None = None

    # -- inputs

    def add_segment(self, text: str, now_ms: int) -> None:
        n = len(text.split())
        if n == 0:
            return
        if self.words == 0:
            self.first_pending_ms = now_ms
        self.words += n
        if self._cue.search(text):
            self.cue_pending = True

    def slide_changed(self) -> None:
        self.slide_pending = True

    def request_flush(self) -> None:
        self.flush_pending = True

    # -- decision

    def decide(self, now_ms: int) -> Decision | None:
        if self.in_flight:
            return None
        has_work = self.words > 0 or self.slide_pending
        if self.cue_pending and self.words > 0:
            return Decision("D", True)
        if self.flush_pending and has_work:
            return Decision("flush", False)
        if self.last_start_ms is not None and now_ms - self.last_start_ms < self.cfg.min_spacing_ms:
            return None
        if self.slide_pending:
            return Decision("C", False)
        if self.words >= self.cfg.words_threshold:
            return Decision("A", False)
        if self.words > 0:
            ref = self.last_start_ms if self.last_start_ms is not None else self.first_pending_ms
            if ref is not None and now_ms - ref >= self.cfg.max_gap_ms:
                return Decision("B", False)
        return None

    # -- lifecycle

    def start_tick(self, now_ms: int) -> Pending:
        taken = Pending(
            self.words,
            self.slide_pending,
            self.cue_pending,
            self.flush_pending,
            self.first_pending_ms,
        )
        self.words = 0
        self.slide_pending = False
        self.cue_pending = False
        self.flush_pending = False
        self.first_pending_ms = None
        self.in_flight = True
        self.last_start_ms = now_ms
        return taken

    def end_tick(self) -> None:
        self.in_flight = False

    def abort_tick(self, taken: Pending) -> None:
        """The tick did not commit: put its inputs back. Spacing still counts from its start."""
        self.in_flight = False
        if self.words == 0:
            self.first_pending_ms = taken.first_ms
        self.words += taken.words
        self.slide_pending = self.slide_pending or taken.slide
        self.cue_pending = self.cue_pending or taken.cue
        self.flush_pending = self.flush_pending or taken.flush
