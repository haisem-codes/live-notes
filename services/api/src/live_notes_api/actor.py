"""SessionActor: owns one lecture. All durable state lives in the store; a new actor over the same
store continues the session with no duplicate or lost ops.

The clock returns audio/session milliseconds. `t_emit_ms` is max(clock(), the latest audio time
seen so far), so it never goes backwards.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .context import build_context
from .model import NoteModel
from .models import (
    Actor,
    LiveMsg,
    NotesDocument,
    OpMsg,
    StatusMsg,
    TranscriptFinalOut,
    TranscriptSegment,
    TranscriptSegmentIn,
)
from .reducer import apply_op_inplace, fold
from .store import SessionStore
from .trigger import TriggerConfig, TriggerPolicy
from .validator import Counters, Rejection, ValidatorConfig, user_slide_op, validate_tick

log = logging.getLogger(__name__)
Clock = Callable[[], int]


class SessionEnded(Exception):
    pass


@dataclass
class ActorConfig:
    trigger: TriggerConfig = field(default_factory=TriggerConfig)
    validator: ValidatorConfig = field(default_factory=ValidatorConfig)
    lane: Actor = "agent_fast"


@dataclass
class TickRecord:
    tick_id: str
    reason: str
    revision: bool
    t_ms: int
    n_ops: int
    rejections: list[Rejection]


class SessionActor:
    def __init__(
        self,
        store: SessionStore,
        model: NoteModel,
        clock: Clock,
        config: ActorConfig | None = None,
        *,
        autopoll: bool = True,
    ) -> None:
        self.store = store
        self.model = model
        self.clock = clock
        self.cfg = config or ActorConfig()
        self.autopoll = autopoll
        self.trigger = TriggerPolicy(self.cfg.trigger)
        self.ticks: list[TickRecord] = []
        self.errors: list[str] = []
        self.ended = False
        self._lock = asyncio.Lock()  # sequencing: seq assignment, commit, state mutation
        self._poll_lock = asyncio.Lock()  # single-flight ticks
        self._subs: set[asyncio.Queue[Any]] = set()
        self._fail_until = -1
        self._started = False

    # -- startup: rebuild everything from the store

    async def start(self) -> SessionActor:
        self.manifest = await self.store.manifest()
        self.segments: list[TranscriptSegment] = await self.store.segments()
        self.ops: list[Any] = await self.store.ops()
        st = await self.store.state()
        self.cursor = st.cursor
        self.ended = st.ended
        self.counters = Counters.from_dict(st.counters)
        self.tick_seq = int(st.counters.get("tick", 0))
        self.utick_seq = int(st.counters.get("utick", 0))
        self.doc: NotesDocument = fold(self.ops)
        self.last_update: dict[str, int] = {}
        seen: set[str] = set()
        for op in self.ops:
            t, pid = op.type, getattr(op.payload, "id", None)
            if t == "block.insert":
                seen.add(pid)
            elif t == "diagram.upsert":
                if pid in seen:
                    self.last_update[pid] = op.t_emit_ms
                seen.add(pid)
            elif t == "block.update":
                self.last_update[pid] = op.t_emit_ms
        self._seg_by_id = {s.id: s for s in self.segments}
        self._floor = max([o.t_emit_ms for o in self.ops] + [s.t1_ms for s in self.segments] + [0])
        for s in self.segments[self.cursor :]:
            self.trigger.add_segment(s.text, s.t1_ms)
        self.trigger.last_start_ms = st.meta.get("last_tick_start_ms")
        if st.meta.get("slide_pending"):
            self.trigger.slide_changed()
        self._started = True
        return self

    # -- read access

    @property
    def session_id(self) -> str:
        return self.manifest.id

    @property
    def last_seq(self) -> int:
        return self.ops[-1].seq if self.ops else 0

    def ops_after(self, seq: int) -> list[Any]:
        return [o for o in self.ops if o.seq > seq]

    def subscribe(self) -> asyncio.Queue[Any]:
        q: asyncio.Queue[Any] = asyncio.Queue()
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[Any]) -> None:
        self._subs.discard(q)

    def _publish(self, msg: Any) -> None:
        for q in list(self._subs):
            q.put_nowait(msg)

    def live_message(self) -> LiveMsg:
        return LiveMsg(last_seq=self.last_seq)

    def _now(self) -> int:
        return max(self.clock(), self._floor)

    def _state_counters(self) -> dict[str, int]:
        d = self.counters.to_dict()
        d["tick"] = self.tick_seq
        d["utick"] = self.utick_seq
        return d

    # -- inputs

    async def add_segment(self, seg_in: TranscriptSegmentIn) -> TranscriptSegment:
        async with self._lock:
            if self.ended:
                raise SessionEnded(self.session_id)
            seg = TranscriptSegment(id=f"s{len(self.segments) + 1}", **seg_in.model_dump())
            await self.store.append_segment(seg)
            self.segments.append(seg)
            self._seg_by_id[seg.id] = seg
            self._floor = max(self._floor, seg.t1_ms)
            self.trigger.add_segment(seg.text, self._now())
            self._publish(TranscriptFinalOut(segment=seg))
        if self.autopoll:
            await self.poll()
        return seg

    async def set_slide(self, slide: int, t_ms: int) -> None:
        async with self._lock:
            if self.ended:
                raise SessionEnded(self.session_id)
            if self.manifest.slides and all(p.index != slide for p in self.manifest.slides):
                raise ValueError(f"unknown slide {slide}")
            self.utick_seq += 1
            t = max(t_ms, self._floor)
            op = user_slide_op(
                session_id=self.session_id,
                tick_id=f"u{self.utick_seq}",
                t_emit_ms=t,
                slide=slide,
                seq=self.last_seq + 1,
            )
            self.trigger.slide_changed()
            try:
                await self._commit(op.tick_id, [op], self.cursor, [])
            except Exception:
                await self._resync_after_failure()
                raise
        if self.autopoll:
            await self.poll()

    async def end(self, t_ms: int | None = None) -> None:
        """Flush what is left with a final tick, then mark the session ended."""
        async with self._poll_lock:
            if t_ms is not None:
                self._floor = max(self._floor, t_ms)
            self.trigger.request_flush()
            await self._poll_core()
            async with self._lock:
                self.ended = True
                await self.store.mark_ended()
            self._publish(StatusMsg(state="ended"))

    # -- ticks

    async def poll(self) -> bool:
        """Run ticks while the trigger policy says to fire. Single-flight: returns False at once
        if another poll is already running. Returns True if at least one tick ran."""
        if self._poll_lock.locked() or self.ended:
            return False
        async with self._poll_lock:
            return await self._poll_core()

    async def _poll_core(self) -> bool:
        ran = False
        while True:
            now = self._now()
            if now < self._fail_until:
                break
            decision = self.trigger.decide(now)
            if decision is None:
                break
            ran = True
            if not await self._tick(decision.reason, decision.revision, now):
                break
        return ran

    async def _tick(self, reason: str, revision: bool, now: int) -> bool:
        taken = self.trigger.start_tick(now)
        n = len(self.segments)
        tick_id = f"t{self.tick_seq + 1}"
        ctx = build_context(
            tick_id=tick_id,
            now_ms=now,
            revision=revision,
            slide_changed=taken.slide,
            doc=self.doc.model_copy(deep=True),
            manifest=self.manifest,
            processed=self.segments[: self.cursor],
            new=self.segments[self.cursor : n],
        )
        try:
            calls = await self.model.run_tick(ctx)
            async with self._lock:
                result = validate_tick(
                    session_id=self.session_id,
                    tick_id=tick_id,
                    actor=self.cfg.lane,
                    t_emit_ms=self._now(),
                    calls=calls,
                    doc=self.doc,
                    counters=self.counters,
                    last_update_ms=self.last_update,
                    segments=self._seg_by_id,
                    manifest=self.manifest,
                    next_seq=self.last_seq + 1,
                    config=self.cfg.validator,
                )
                self.tick_seq += 1
                self.counters = result.counters
                await self._commit(
                    tick_id,
                    result.ops,
                    n,
                    result.rejections,
                    last_update=result.last_update_ms,
                )
        except Exception as e:  # the tick did not commit: put its inputs back, retry later
            log.exception("tick %s failed", tick_id)
            self.errors.append(f"{tick_id}: {e!r}")
            self.trigger.abort_tick(taken)
            self._fail_until = now + self.cfg.trigger.min_spacing_ms
            await self._resync_after_failure()
            return False
        self.trigger.end_tick()
        self.ticks.append(
            TickRecord(tick_id, reason, revision, now, len(result.ops), result.rejections)
        )
        return True

    async def _resync_after_failure(self) -> None:
        """Reload committed state so memory matches the store after a failed commit."""
        st = await self.store.state()
        self.cursor = st.cursor
        self.counters = Counters.from_dict(st.counters)
        self.tick_seq = int(st.counters.get("tick", 0))
        self.utick_seq = int(st.counters.get("utick", 0))

    async def _commit(
        self,
        tick_id: str,
        ops: list[Any],
        new_cursor: int,
        rejections: list[Rejection],
        *,
        last_update: dict[str, int] | None = None,
    ) -> None:
        await self.store.commit_tick(
            tick_id,
            ops,
            new_cursor,
            counters=self._state_counters(),
            meta={
                "slide_pending": self.trigger.slide_pending,
                "last_tick_start_ms": self.trigger.last_start_ms,
            },
            rejections=[r.to_dict() for r in rejections],
        )
        # Committed: now (and only now) update memory.
        self.cursor = new_cursor
        if last_update is not None:
            self.last_update = last_update
        for op in ops:
            apply_op_inplace(self.doc, op)
            self.ops.append(op)
            self._floor = max(self._floor, op.t_emit_ms)
        for op in ops:
            self._publish(OpMsg(op=op))
