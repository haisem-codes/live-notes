# Live Notes

AI that listens to a lecture and writes notes, draws diagrams and annotates the slides live, then replays audio, slides and notes in sync. Read `docs/PLAN.md` first; the research behind it is in `docs/research/`.

## Layout

```
packages/protocol   The contract: block, op, transcript and session types (TypeScript). Source of truth.
apps/web            Vite + React app: reducer, notes renderer, slide overlay, replay player.
services/api        FastAPI service: session actor, op validator and sequencer, providers.
evals               Replay harness, scenarios and metrics.
fixtures/sessions   Recorded or scripted sessions (session.json, transcript.jsonl, ops.jsonl, slides/).
docs                Plan, research, decisions.
```

## Commands

```
pnpm install                      # JS workspace
pnpm --filter web dev             # web app
pnpm --filter web test            # web tests
pnpm -r typecheck                 # all TypeScript
cd services/api && uv run pytest  # backend tests
cd services/api && uv run uvicorn live_notes_api.main:app --reload
```

## Invariants

- The append-only op log is the product. `document(t) = fold(ops where t_emit_ms <= t)`. Never mutate or reorder committed ops.
- The reducer is pure and deterministic. The same ops always give the same document, in TypeScript and in Python.
- The model never emits coordinates. It names a slide region ID or quotes slide text; the server resolves geometry and drops what it cannot resolve.
- The server is the only sequencer. Student edits go through the same log with `actor: "user"`.
- Edit permissions (tentative / stable / frozen / user_locked) are enforced in the validator, never only in a prompt.
- `packages/protocol` changes are contract changes: update the Python mirror in `services/api` and the shared fixtures in the same commit.
- Model and speech providers sit behind interfaces with fake implementations; tests never call a paid API.

## Conventions

- This repository is public. No secrets, keys, real lecture recordings or student data in it, ever.
- Every change ships with tests. Fixtures under `fixtures/sessions` must load in both the web tests and the backend tests.
- Licences: MIT/Apache/BSD dependencies only. Known traps: tldraw (proprietary), MuPDF and DocLayout-YOLO (AGPL), BlockNote `xl-*` packages (GPL), elkjs (EPL).
- Claude API code follows current model IDs: `claude-haiku-5-5` for the fast lane, `claude-sonnet-5-5` for the slow lane, `claude-opus-5-5` for consolidation. Check `stop_reason` for `refusal` on every response.
