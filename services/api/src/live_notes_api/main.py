"""FastAPI app: health, session creation/inspection and the session WebSocket."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import time
import uuid
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from .actor import ActorConfig, Clock, SessionActor, SessionEnded
from .model import ModelFactory, make_model
from .models import (
    ClientMessageAdapter,
    ErrorMsg,
    OpMsg,
    SessionManifest,
    StatusMsg,
    dump,
)
from .store import (
    SESSION_ID_RE,
    DirectorySessionRepository,
    SessionExists,
    SessionNotFound,
    SessionRepository,
)

log = logging.getLogger(__name__)
DEFAULT_DATA_DIR = Path(__file__).resolve().parents[2] / "data"


class Runtime:
    """One live session: its actor plus the background task that polls the trigger policy."""

    def __init__(self, actor: SessionActor, poll_interval: float) -> None:
        self.actor = actor
        self.poll_interval = poll_interval
        self.kick = asyncio.Event()
        self.task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        while True:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self.kick.wait(), self.poll_interval)
            self.kick.clear()
            try:
                await self.actor.poll()
            except Exception:  # pragma: no cover - the actor already logs tick failures
                log.exception("poll failed")

    async def stop(self) -> None:
        self.task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self.task


def create_app(
    *,
    repo: SessionRepository | None = None,
    model_factory: ModelFactory | None = None,
    clock_factory: Callable[[], Clock] | None = None,
    poll_interval: float = 1.0,
    actor_config: ActorConfig | None = None,
) -> FastAPI:
    data_dir = Path(os.environ.get("LIVE_NOTES_DATA_DIR", str(DEFAULT_DATA_DIR)))
    repo = repo or DirectorySessionRepository(data_dir)
    model_factory = model_factory or (
        lambda: make_model(os.environ.get("LIVE_NOTES_MODEL", "heuristic"))
    )
    runtimes: dict[str, Runtime] = {}

    def default_clock() -> Clock:
        t0 = time.monotonic()
        return lambda: int((time.monotonic() - t0) * 1000)

    async def get_runtime(session_id: str) -> Runtime:
        if session_id in runtimes:
            return runtimes[session_id]
        store = await repo.open(session_id)  # raises SessionNotFound
        actor = SessionActor(
            store,
            model_factory(),
            (clock_factory or default_clock)(),
            actor_config,
            autopoll=False,  # the runtime's background task polls; WS handlers never wait on a tick
        )
        await actor.start()
        runtimes[session_id] = Runtime(actor, poll_interval)
        return runtimes[session_id]

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        for rt in runtimes.values():
            await rt.stop()

    app = FastAPI(title="Live Notes API", lifespan=lifespan)
    app.state.runtimes = runtimes

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/sessions", status_code=201)
    async def create_session(manifest: SessionManifest) -> dict[str, Any]:
        if manifest.id == "":
            manifest = manifest.model_copy(update={"id": f"ls-{uuid.uuid4().hex[:12]}"})
        if not SESSION_ID_RE.match(manifest.id):
            raise HTTPException(422, "session id must match [A-Za-z0-9_-]{1,64}")
        try:
            await repo.create(manifest)
        except SessionExists:
            raise HTTPException(409, "session exists") from None
        return dump(manifest)

    @app.get("/sessions/{session_id}")
    async def get_session(session_id: str) -> dict[str, Any]:
        try:
            store = await repo.open(session_id)
        except SessionNotFound:
            raise HTTPException(404, "no such session") from None
        rt = runtimes.get(session_id)
        ops = rt.actor.ops if rt else await store.ops()
        return {
            "manifest": dump(await store.manifest()),
            "transcript": [dump(s) for s in await store.segments()],
            "ops": [dump(o) for o in ops],
        }

    @app.websocket("/ws/sessions/{session_id}")
    async def ws_session(ws: WebSocket, session_id: str) -> None:
        await ws.accept()
        try:
            rt = await get_runtime(session_id)
        except SessionNotFound:
            await ws.send_json(dump(ErrorMsg(code="not_found", message="no such session")))
            await ws.close(code=4404)
            return
        actor = rt.actor
        try:
            first = await ws.receive_json()
            msg = ClientMessageAdapter.validate_python(first)
            if msg.type != "resume":
                raise ValueError("first message must be resume")
        except (ValidationError, ValueError, KeyError):
            await ws.send_json(dump(ErrorMsg(code="bad_request", message="expected resume")))
            await ws.close(code=4400)
            return
        except WebSocketDisconnect:
            return

        # Subscribe and snapshot the backlog in the same event-loop turn: no gap, no duplicate.
        queue = actor.subscribe()
        try:
            sent = msg.last_seq
            for op in actor.ops_after(msg.last_seq):
                await ws.send_json(dump(OpMsg(op=op)))
                sent = op.seq
            await ws.send_json(dump(actor.live_message()))
            await ws.send_json(dump(StatusMsg(state="ended" if actor.ended else "listening")))

            async def sender() -> None:
                nonlocal sent
                while True:
                    out = await queue.get()
                    if isinstance(out, OpMsg):
                        if out.op.seq <= sent:
                            continue
                        sent = out.op.seq
                    await ws.send_json(dump(out))

            async def receiver() -> None:
                while True:
                    try:
                        m = ClientMessageAdapter.validate_python(await ws.receive_json())
                    except ValidationError as e:
                        await ws.send_json(dump(ErrorMsg(code="bad_request", message=str(e)[:200])))
                        continue
                    try:
                        if m.type == "transcript.final":
                            await actor.add_segment(m.segment)
                        elif m.type == "slide.set":
                            await actor.set_slide(m.slide, m.t_ms)
                        elif m.type == "session.end":
                            await actor.end(m.t_ms)
                        else:  # a second resume
                            await ws.send_json(
                                dump(ErrorMsg(code="bad_request", message="already resumed"))
                            )
                    except (SessionEnded, ValueError) as e:
                        await ws.send_json(dump(ErrorMsg(code="rejected", message=str(e))))
                    rt.kick.set()

            tasks = [asyncio.create_task(sender()), asyncio.create_task(receiver())]
            try:
                await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            finally:
                for t in tasks:
                    t.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
        except WebSocketDisconnect:
            pass
        finally:
            actor.unsubscribe(queue)

    return app


app = create_app()
