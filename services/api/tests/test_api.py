from conftest import words
from fastapi.testclient import TestClient

from live_notes_api.main import create_app
from live_notes_api.model import HeuristicModel
from live_notes_api.models import dump
from live_notes_api.store import MemorySessionRepository


def make_client():
    app = create_app(
        repo=MemorySessionRepository(),
        model_factory=HeuristicModel,
        clock_factory=lambda: lambda: 0,  # audio time then comes from the segments
        poll_interval=0.02,
    )
    return TestClient(app)


def seg_msg(t0, t1, text):
    return {
        "type": "transcript.final",
        "segment": {"t0_ms": t0, "t1_ms": t1, "text": text, "lang": "en", "words": []},
    }


def recv_until(ws, pred, limit=50):
    got = []
    for _ in range(limit):
        m = ws.receive_json()
        got.append(m)
        if pred(m):
            return got
    raise AssertionError(f"predicate never matched: {got}")


def test_healthz():
    with make_client() as c:
        assert c.get("/healthz").json() == {"status": "ok"}


def test_create_and_get_session(manifest):
    with make_client() as c:
        body = dump(manifest)
        r = c.post("/sessions", json=body)
        assert r.status_code == 201 and r.json() == body
        assert c.post("/sessions", json=body).status_code == 409
        bad = dict(body, id="../evil")
        assert c.post("/sessions", json=bad).status_code == 422
        assert c.post("/sessions", json={"id": "x"}).status_code == 422
        got = c.get(f"/sessions/{manifest.id}").json()
        assert got == {"manifest": body, "transcript": [], "ops": []}
        assert c.get("/sessions/missing").status_code == 404
        generated = c.post("/sessions", json=dict(body, id="")).json()["id"]
        assert generated.startswith("ls-")


def test_websocket_resume_replays_only_missing_ops_then_live(manifest):
    with make_client() as c:
        c.post("/sessions", json=dump(manifest))
        url = f"/ws/sessions/{manifest.id}"

        with c.websocket_connect(url) as ws:
            ws.send_json({"type": "resume", "last_seq": 0})
            assert ws.receive_json() == {"type": "live", "last_seq": 0}
            assert ws.receive_json() == {"type": "status", "state": "listening"}
            ws.send_json({"type": "slide.set", "slide": 1, "t_ms": 0})
            ws.send_json(seg_msg(0, 4000, words(60)))
            msgs = recv_until(ws, lambda m: m["type"] == "op" and m["op"]["actor"] == "agent_fast")
            seen = [m["op"]["seq"] for m in msgs if m["type"] == "op"]
            assert seen[0] == 1  # the user's slide.set was sequenced first
            ws.send_json(seg_msg(4000, 14000, words(60, "y")))
            more = recv_until(ws, lambda m: m["type"] == "op" and m["op"]["seq"] >= 4, limit=60)
            seen += [m["op"]["seq"] for m in more if m["type"] == "op"]
        assert seen == sorted(set(seen))  # strictly increasing, no duplicates while live

        everything = c.get(f"/sessions/{manifest.id}").json()["ops"]
        last = everything[-1]["seq"]
        assert [o["seq"] for o in everything] == list(range(1, last + 1))
        assert last == 4

        # reconnect knowing seq 2: receive exactly the rest, then `live`, nothing duplicated
        with c.websocket_connect(url) as ws:
            ws.send_json({"type": "resume", "last_seq": 2})
            replay = recv_until(ws, lambda m: m["type"] == "live")
            assert [m["type"] for m in replay[:-1]] == ["op"] * (last - 2)
            assert [m["op"]["seq"] for m in replay[:-1]] == list(range(3, last + 1))
            assert [m["op"] for m in replay[:-1]] == everything[2:]
            assert replay[-1] == {"type": "live", "last_seq": last}

        # up to date: no ops, straight to live
        with c.websocket_connect(url) as ws:
            ws.send_json({"type": "resume", "last_seq": last})
            assert ws.receive_json() == {"type": "live", "last_seq": last}


def test_websocket_end_and_errors(manifest):
    with make_client() as c:
        c.post("/sessions", json=dump(manifest))
        url = f"/ws/sessions/{manifest.id}"
        with c.websocket_connect(url) as ws:
            ws.send_json({"type": "resume", "last_seq": 0})
            recv_until(ws, lambda m: m["type"] == "status")
            ws.send_json({"type": "bogus"})
            assert ws.receive_json()["code"] == "bad_request"
            ws.send_json({"type": "slide.set", "slide": 99, "t_ms": 0})
            assert ws.receive_json()["code"] == "rejected"
            ws.send_json(seg_msg(0, 1000, "a short remark"))
            ws.send_json({"type": "session.end", "t_ms": 2000})
            msgs = recv_until(ws, lambda m: m["type"] == "status")
            assert msgs[-1] == {"type": "status", "state": "ended"}
            assert any(m["type"] == "op" for m in msgs)  # flushed by a final tick
            ws.send_json(seg_msg(2000, 3000, "too late"))
            assert ws.receive_json()["code"] == "rejected"


def test_websocket_requires_resume_first_and_known_session(manifest):
    with make_client() as c:
        c.post("/sessions", json=dump(manifest))
        with c.websocket_connect(f"/ws/sessions/{manifest.id}") as ws:
            ws.send_json({"type": "session.end", "t_ms": 0})
            assert ws.receive_json()["code"] == "bad_request"
        with c.websocket_connect("/ws/sessions/nope") as ws:
            assert ws.receive_json()["code"] == "not_found"
