"""Session persistence.

`SessionRepository` creates/opens sessions; `SessionStore` is one session's storage. Both are
async interfaces so a Postgres implementation (one transaction per commit_tick, unique key on
(session_id, tick_id), primary key (session_id, seq)) can replace the two implementations here.

Commit point: for the directory store, state.json is written last (temp file + rename). ops.jsonl
lines whose seq is greater than state.last_seq belong to an unfinished commit and are discarded
when the session is opened.
"""

from __future__ import annotations

import json
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .models import SessionManifest, TranscriptSegment, dump, dump_json, parse_op

SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class SessionExists(Exception):
    pass


class SessionNotFound(Exception):
    pass


class CommitConflict(Exception):
    """Ops do not continue the log (wrong seq) - the caller's view of the session is stale."""


@dataclass
class StoreState:
    last_seq: int = 0
    cursor: int = 0  # number of transcript segments already processed by committed ticks
    counters: dict[str, int] = field(default_factory=dict)
    committed_tick_ids: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)  # small flags owned by the actor
    ended: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "last_seq": self.last_seq,
            "cursor": self.cursor,
            "counters": self.counters,
            "committed_tick_ids": self.committed_tick_ids,
            "meta": self.meta,
            "ended": self.ended,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> StoreState:
        return cls(
            last_seq=d["last_seq"],
            cursor=d["cursor"],
            counters=dict(d["counters"]),
            committed_tick_ids=list(d["committed_tick_ids"]),
            meta=dict(d.get("meta", {})),
            ended=bool(d.get("ended", False)),
        )

    def copy(self) -> StoreState:
        return StoreState.from_dict(json.loads(json.dumps(self.to_dict())))


class SessionStore(ABC):
    @abstractmethod
    async def manifest(self) -> SessionManifest: ...

    @abstractmethod
    async def segments(self) -> list[TranscriptSegment]: ...

    @abstractmethod
    async def append_segment(self, seg: TranscriptSegment) -> bool:
        """Idempotent by segment id. Returns True if newly stored."""

    @abstractmethod
    async def ops(self, after_seq: int = 0) -> list[Any]: ...

    @abstractmethod
    async def state(self) -> StoreState: ...

    @abstractmethod
    async def commit_tick(
        self,
        tick_id: str,
        ops: list[Any],
        new_cursor: int,
        *,
        counters: dict[str, int] | None = None,
        meta: dict[str, Any] | None = None,
        rejections: list[dict[str, Any]] | None = None,
    ) -> bool:
        """Atomically append `ops`, set the transcript cursor, counters and meta, and record
        `tick_id`. Idempotent: if tick_id is already committed nothing changes and False is
        returned. Raises CommitConflict if ops do not continue the log."""

    @abstractmethod
    async def mark_ended(self) -> None: ...


class SessionRepository(ABC):
    @abstractmethod
    async def create(self, manifest: SessionManifest) -> SessionStore: ...

    @abstractmethod
    async def open(self, session_id: str) -> SessionStore: ...

    @abstractmethod
    async def exists(self, session_id: str) -> bool: ...


def _check_continuity(state: StoreState, ops: list[Any]) -> None:
    expected = state.last_seq + 1
    for op in ops:
        if op.seq != expected:
            raise CommitConflict(f"expected seq {expected}, got {op.seq}")
        expected += 1


# --- in memory --------------------------------------------------------------------------------


class MemorySessionStore(SessionStore):
    def __init__(self, manifest: SessionManifest) -> None:
        self._manifest = manifest
        self._segments: list[TranscriptSegment] = []
        self._ops: list[Any] = []
        self._state = StoreState()
        self.rejections: list[dict[str, Any]] = []

    async def manifest(self) -> SessionManifest:
        return self._manifest

    async def segments(self) -> list[TranscriptSegment]:
        return list(self._segments)

    async def append_segment(self, seg: TranscriptSegment) -> bool:
        if any(s.id == seg.id for s in self._segments):
            return False
        self._segments.append(seg)
        return True

    async def ops(self, after_seq: int = 0) -> list[Any]:
        return [o for o in self._ops if o.seq > after_seq]

    async def state(self) -> StoreState:
        return self._state.copy()

    async def commit_tick(
        self, tick_id, ops, new_cursor, *, counters=None, meta=None, rejections=None
    ) -> bool:
        if tick_id in self._state.committed_tick_ids:
            return False
        _check_continuity(self._state, ops)
        # Build the new state first so nothing is applied if something above raised.
        st = self._state.copy()
        st.committed_tick_ids.append(tick_id)
        st.cursor = new_cursor
        if ops:
            st.last_seq = ops[-1].seq
        if counters is not None:
            st.counters = dict(counters)
        if meta is not None:
            st.meta = dict(meta)
        self._ops.extend(ops)
        self._state = st
        if rejections:
            self.rejections.extend({"tick_id": tick_id, **r} for r in rejections)
        return True

    async def mark_ended(self) -> None:
        self._state.ended = True


class MemorySessionRepository(SessionRepository):
    def __init__(self) -> None:
        self._sessions: dict[str, MemorySessionStore] = {}

    async def create(self, manifest: SessionManifest) -> SessionStore:
        if manifest.id in self._sessions:
            raise SessionExists(manifest.id)
        self._sessions[manifest.id] = MemorySessionStore(manifest)
        return self._sessions[manifest.id]

    async def open(self, session_id: str) -> SessionStore:
        try:
            return self._sessions[session_id]
        except KeyError:
            raise SessionNotFound(session_id) from None

    async def exists(self, session_id: str) -> bool:
        return session_id in self._sessions


# --- directory --------------------------------------------------------------------------------


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _append_lines(path: Path, lines: list[str]) -> None:
    if not lines:
        return
    with open(path, "a", encoding="utf-8") as f:
        f.write("".join(line + "\n" for line in lines))
        f.flush()
        os.fsync(f.fileno())


class DirectorySessionStore(SessionStore):
    """Stored-session format of the protocol (session.json, transcript.jsonl, ops.jsonl) plus
    state.json (commit point) and rejections.jsonl (diagnostics)."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._manifest = SessionManifest.model_validate_json((root / "session.json").read_text())
        self._segments = self._read_segments()
        self._state = self._load_state()
        self._ops = self._load_ops()

    @classmethod
    def create_at(cls, root: Path, manifest: SessionManifest) -> DirectorySessionStore:
        root.mkdir(parents=True, exist_ok=True)
        _atomic_write(root / "session.json", json.dumps(dump(manifest), indent=1) + "\n")
        (root / "transcript.jsonl").touch()
        (root / "ops.jsonl").touch()
        store = cls(root)
        store._save_state(store._state)
        return store

    # -- loading and recovery

    def _read_segments(self) -> list[TranscriptSegment]:
        p = self.root / "transcript.jsonl"
        if not p.exists():
            return []
        out = []
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                out.append(TranscriptSegment.model_validate_json(line))
            except ValueError:
                break  # torn final line from a crash; segments are re-sent by the client
        return out

    def _read_ops(self) -> list[Any]:
        p = self.root / "ops.jsonl"
        if not p.exists():
            return []
        out = []
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    out.append(parse_op(line))
                except ValueError:
                    break
        return out

    def _load_state(self) -> StoreState:
        p = self.root / "state.json"
        if p.exists():
            return StoreState.from_dict(json.loads(p.read_text()))
        # A stored session without state (e.g. a fixture): derive what we can from the ops.
        ops = self._read_ops()
        st = StoreState(last_seq=ops[-1].seq if ops else 0)
        for op in ops:
            if op.tick_id not in st.committed_tick_ids:
                st.committed_tick_ids.append(op.tick_id)
        counters = {"b": 0, "d": 0, "a": 0}
        for op in ops:
            if op.type == "block.insert" or op.type == "diagram.upsert":
                m = re.fullmatch(r"([bd])(\d+)", op.payload.id)
                if m:
                    counters[m[1]] = max(counters[m[1]], int(m[2]))
            elif op.type == "slide.annotate":
                m = re.fullmatch(r"a(\d+)", op.payload.id)
                if m:
                    counters["a"] = max(counters["a"], int(m[1]))
        st.counters = counters
        return st

    def _load_ops(self) -> list[Any]:
        ops = self._read_ops()
        keep = [o for o in ops if o.seq <= self._state.last_seq]
        if len(keep) != len(ops) or not (self.root / "ops.jsonl").exists():
            # Drop lines from an unfinished commit (or a torn tail).
            _atomic_write(self.root / "ops.jsonl", "".join(dump_json(o) + "\n" for o in keep))
        return keep

    def _save_state(self, st: StoreState) -> None:
        _atomic_write(self.root / "state.json", json.dumps(st.to_dict(), indent=1) + "\n")

    # -- interface

    async def manifest(self) -> SessionManifest:
        return self._manifest

    async def segments(self) -> list[TranscriptSegment]:
        return list(self._segments)

    async def append_segment(self, seg: TranscriptSegment) -> bool:
        if any(s.id == seg.id for s in self._segments):
            return False
        _append_lines(self.root / "transcript.jsonl", [dump_json(seg)])
        self._segments.append(seg)
        return True

    async def ops(self, after_seq: int = 0) -> list[Any]:
        return [o for o in self._ops if o.seq > after_seq]

    async def state(self) -> StoreState:
        return self._state.copy()

    async def commit_tick(
        self, tick_id, ops, new_cursor, *, counters=None, meta=None, rejections=None
    ) -> bool:
        if tick_id in self._state.committed_tick_ids:
            return False
        _check_continuity(self._state, ops)
        st = self._state.copy()
        st.committed_tick_ids.append(tick_id)
        st.cursor = new_cursor
        if ops:
            st.last_seq = ops[-1].seq
        if counters is not None:
            st.counters = dict(counters)
        if meta is not None:
            st.meta = dict(meta)
        _append_lines(self.root / "ops.jsonl", [dump_json(o) for o in ops])
        if rejections:
            _append_lines(
                self.root / "rejections.jsonl",
                [json.dumps({"tick_id": tick_id, **r}) for r in rejections],
            )
        self._save_state(st)  # commit point
        self._ops.extend(ops)
        self._state = st
        return True

    async def mark_ended(self) -> None:
        st = self._state.copy()
        st.ended = True
        self._save_state(st)
        self._state = st


class DirectorySessionRepository(SessionRepository):
    def __init__(self, base: Path) -> None:
        self.base = base
        base.mkdir(parents=True, exist_ok=True)

    def _dir(self, session_id: str) -> Path:
        if not SESSION_ID_RE.match(session_id):
            raise SessionNotFound(session_id)
        return self.base / session_id

    async def create(self, manifest: SessionManifest) -> SessionStore:
        d = self._dir(manifest.id)
        if d.exists():
            raise SessionExists(manifest.id)
        return DirectorySessionStore.create_at(d, manifest)

    async def open(self, session_id: str) -> SessionStore:
        d = self._dir(session_id)
        if not (d / "session.json").exists():
            raise SessionNotFound(session_id)
        return DirectorySessionStore(d)

    async def exists(self, session_id: str) -> bool:
        try:
            return (self._dir(session_id) / "session.json").exists()
        except SessionNotFound:
            return False
