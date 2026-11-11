# Live Notes API

Phase 0 server core: final transcript segments in, validated, sequenced, append-only op log out.
No external API is called anywhere; the note-taking model is behind `NoteModel` with two offline
implementations (`ScriptedModel`, `HeuristicModel`).

```
uv sync                                   # install
uv run pytest -q                          # all tests, offline
uv run ruff check .                       # lint
uv run uvicorn live_notes_api.main:app --reload
curl localhost:8000/healthz               # {"status":"ok"}

# replay a stored session through the actor on a virtual clock
uv run python -m live_notes_api.replay tests/data/tiny --model heuristic --out /tmp/replayed
```

Environment: `LIVE_NOTES_DATA_DIR` (default `services/api/data`, git-ignored),
`LIVE_NOTES_MODEL` (default `heuristic`).

Modules: `models` (protocol mirror), `reducer`, `tools` (model tool schemas), `validator`
(tool calls -> ops), `store` (memory + directory), `trigger`, `context`, `model`, `actor`,
`main` (HTTP + WebSocket), `replay`.
