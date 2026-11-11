# Live Notes — master plan

Status: v1, 2026-11-11. Working title only: "Live Notes" is already used by a near-identical free product (live-notes-ai.com), so the name must change before launch (candidates: Slidepen, Understudy, Chalkline — none trademark-checked).

This plan synthesises four research reports in `docs/research/`. Vendor sites could not be opened directly during research, so prices are from search extracts and nothing has been tested on real audio. Every number here is an assumption until Phase 0 measures it.

## 1. Problem and product

Students cannot listen, understand and write at the same time. Live Notes listens to the lecture and does the writing:

1. Before class the student optionally uploads the teacher's slides.
2. During class they press record. The AI follows the live transcript and writes concise, keyword-dense notes, draws diagrams, and highlights and annotates the slides — live, and it goes back to revise earlier notes when the teacher corrects or clarifies.
3. After class, audio, slides and notes replay in sync like a video, with seeking. Click any note to hear the moment it came from.
4. Later: quizzes, flashcards, course-level memory across lectures.

**Positioning.** "The AI that annotates your lecturer's slides while they talk — and replays it all in sync before the exam."

## 2. What the research changed

| Question | Finding | Consequence |
|---|---|---|
| Is the gap real? | Narrow but real. Live AI notes, slides beside a transcript, and audio-synced replay each ship separately (Notability, Goodnotes, Genio, StudyFetch). Nobody found has AI that annotates the uploaded slides live, revises its notes, and replays the annotations in sync. | It is a feature gap an incumbent could close in one release. Speed and the annotated, replayable slide deck are the moat, not "live" by itself. |
| What is Clicky? | Farza Majeed's cursor companion (now HeyClicky). The model emits inline `[POINT:x,y:label]` tags in screenshot pixels and a cursor flies there. | Good for a pointer, too imprecise for circles and highlights. We reference pre-parsed slide element IDs instead of pixels. |
| Speech-to-text | Soniox real-time is the provisional pick: Swedish with mid-sentence language switching, per-token timestamps, slide vocabulary as context, 300-minute sessions, about $0.12/h live. AssemblyAI is the fallback at about $0.70/h. OpenAI and Gemini live transcription return no word timestamps while streaming and are out. | Provider abstraction from day one. A bake-off on real Swedish and English lecture audio comes before commitment, because no independent far-field Swedish benchmark exists for any vendor. |
| Drawing | tldraw is proprietary and needs a paid licence in production. tldraw and Excalidraw are editors, not seekable players. | We own a thin React SVG renderer (rough.js + perfect-freehand, both MIT) whose animation progress is a function of the playhead. |
| Slide pointing | Vision models miss silently when asked for coordinates. | The model never emits coordinates. Each slide is pre-processed into a region map; at runtime the model names a region ID or quotes text on the slide, and the server resolves geometry. Unresolvable targets are dropped. |
| Speech-native models | OpenAI Realtime and Gemini Live are built for two-way dialogue, cap session length, and give no timestamps. | Keep streaming STT plus a text model. |
| Phones | Web microphone capture stops when an iPhone or iPad locks its screen. | Laptop web app first. Native wrapper with background recording in a later phase. |
| Legal | KI guidance allows audio recording for own use; a KTH staff FAQ says students may not record without permission. | Start with KI students. Permission attestation, personal-use lock and transcript-only mode are MVP features, not later polish. |

## 3. Architecture

The central decision: **the timestamped operation log is the product.** The model never regenerates the document. It emits small tool calls against stable block IDs; the server validates and sequences them into an append-only log. The live view, reconnects, replay and evaluation are all folds over that log: `document(t) = fold(ops where t_emit_ms <= t)`.

```
BEFORE   slides.pdf -> slide prep job -> page images, text boxes, region map, glossary

DURING   browser: mic -> streaming STT (direct, temporary key) -> final segments
                  mic -> local Opus recording (audio of record) -> resumable upload
                  notes view + slide overlay + transcript ticker  <- ops
              |  WebSocket: final segments up, ops down, resume by last_seq
         server: session actor per lecture
                  trigger policy (single-flight) -> fast lane (small model, ~180 ticks/h)
                                                 -> slow lane (section tidy, diagrams, ~10/h)
                  op validator + sequencer -> Postgres (segments, ops, snapshots)

AFTER    batch re-transcription of the recorded audio (fills wifi gaps)
         consolidation pass -> more ops in the same log
         replay player: audio clock is master, state = fold(ops <= t)
         eval harness reads the same log
```

### Stack decisions

| Layer | Decision | Why | Revisit when |
|---|---|---|---|
| Web app | Vite + React + TypeScript, installable PWA | Authenticated realtime tool; server rendering adds little | Public share pages are needed |
| Notes surface | Block document rendered by our own reducer-driven React view; TipTap (MIT) when student editing lands | Replay needs a renderer that is a pure function of the log | — |
| Diagrams | Model emits a validated node/edge graph; dagre lays it out; rough.js draws it with playhead-driven animation | A schema-checked graph cannot fail to parse or overlap | Freeform sketches are demanded |
| Slides | Convert to PDF, rasterise server-side with PDFium, extract word boxes with PDF.js; regions labelled offline by a vision model | Avoids AGPL traps (MuPDF, DocLayout-YOLO) | — |
| Backend | Python FastAPI, one asyncio session actor per lecture, stateless ticks | The founder's home stack; stateless ticks make restarts safe | — |
| Data | Postgres as the single source of truth; S3-compatible object storage in the EU | One writer, no CRDT needed while one human edits | Shared editing |
| Live model | Claude Haiku 5.5 for the fast lane | Narrow task, 180 calls an hour, about $0.12/h | Evaluation shows it mishandles corrections: move to Sonnet 5.5 with an append-only cached conversation |
| Slow lane and consolidation | Claude Sonnet 5.5 (section tidy, diagrams); Opus 5.5 or batched Sonnet after class | Spend expensive tokens where judgement matters | Measured quality per dollar |
| STT | Soniox behind a provider interface; AssemblyAI as fallback; batch re-transcription after class | Cheapest option with Swedish and timestamps | Bake-off result |
| Audio path | Browser connects to the STT vendor directly with a temporary key and forwards final segments to our server | Smallest server, lowest latency | Transcript integrity or resume logic needs the server in the path |
| Hosting | One always-on container on an EU PaaS region | WebSockets need a long-lived process | Second instance: add Postgres LISTEN/NOTIFY |

### Note-stability rules (enforced by the server, not the prompt)

- New blocks start `tentative`; the fast lane may freely edit only tentative blocks in the active section.
- Closed sections are tidied once, then `frozen`; only a teacher correction, clarification or transcription fix may touch them.
- A block the student edited is `user_locked`; the agent may add beside it but never change it.
- A block cannot be updated twice within about 20 s unless the teacher corrected themselves.
- Rejected ops are dropped and logged, never retried.

Latency target: a spoken point appears as a note in 10–15 s (median), under 40 s at the 95th percentile; a spoken correction revises the note within 15 s. The transcript ticker gives the sub-second "it is listening" signal. Lag is acceptable; flicker is not.

## 4. Unit economics

| Configuration | STT | LLM | All-in per lecture hour |
|---|---|---|---|
| Lean: Haiku live, batched Sonnet clean-up | $0.12 live (+$0.10 batch re-transcription) | $0.23 | $0.35–0.48 |
| Recommended: Haiku live, Sonnet slow lane, Opus consolidation | $0.22 | $0.93 | about $1.15 |
| Premium live: Sonnet live loop | $0.22 | $1.10 | about $1.32 |

Market anchor is $5–12 a month. Proposed: free tier with the first lecture fully live then 2 live hours a month; Student at 99 SEK (about $9) with 15 live hours; Plus at 189 SEK with 40 hours; exam-week top-ups; no "unlimited". At the lean cost a fully used Student plan costs $5.30–7.20 to serve, so **launch on the lean configuration** and treat the recommended one as a quality upgrade to be justified by evaluation.

## 5. Roadmap

Each phase ends with a demo and a go/no-go check. Dates assume one founder plus coding agents.

| Phase | Weeks | Builds | Exit criteria |
|---|---|---|---|
| **0. De-risk** | 1–2 | Protocol and op log; reducer; replay player on a scripted fixture; backend skeleton with fake STT and fake model; replay/eval harness. In parallel: STT bake-off on real KI/KTH-style Swedish and English recordings; Haiku latency measured on the real prompt; five student interviews; landing page with waitlist | Scripted lecture replays with seeking. Best STT vendor chosen on measured error rate. Fast-lane time to first op under 2 s, or the fallback model chosen. |
| **1. Walking skeleton** | 3–4 | Record in the browser, live transcript, live text notes with revisions, local Opus recording and upload, replay with audio | The founder takes notes in a real lecture with it and prefers the result to their own notes. |
| **2. Slides** | 5–6 | PDF upload, slide prep job, region map, text-anchored highlights, manual slide flip, slides in replay | 90% of highlights land on the right text in a 100-slide test set. |
| **3. Diagrams and quality** | 7–8 | Animated graph diagrams, slow lane, consolidation pass, figure-part annotations, regression suite in CI | Coverage, correctness and churn scores beat the Phase 1 baseline on the test lectures. |
| **4. Private alpha** | 9–10 | Auth, permission attestation, transcript-only mode, EU storage, cost metering, 10–20 KI students | 40% of alpha users record a second lecture within a week; measured cost per hour at or under $0.50. |
| **5. Beta** | 11+ | Payments, quizzes and flashcards, course memory, native wrapper with background recording, student editing | Paying users; retention through an exam period. |

### Cheapest experiments first (weeks 1–2, before more code than Phase 0)

1. **Is live worth it?** Show five students a replay made after class versus the live view. If "two minutes after class" satisfies them, the product becomes cheaper and simpler.
2. **STT bake-off.** Three vendors, five real recordings from mid-hall on a laptop mic, Swedish and English.
3. **Fake-door pricing.** Landing page with the 99 SEK plan and a waitlist.
4. **Permission.** Ask three KI lecturers for permission using the template; count yeses.

## 6. Team

The founder is product owner and makes the calls in section 8. Work is split across agent roles defined in `.claude/agents/`:

| Role | Owns |
|---|---|
| Orchestrator (main session) | Plan, protocol contract, task breakdown, integration, commits |
| `backend-engineer` | FastAPI service, session actor, op validator and sequencer, persistence |
| `frontend-engineer` | React app, reducer, renderer, slide overlay, replay player |
| `ai-eval-engineer` | Prompts, tool schemas, trigger policy, replay harness, metrics, regression suite |
| `qa-reviewer` | Independent review of each change, tests, security and privacy checks |
| `researcher` | Vendor checks, benchmarks, legal and market questions |

Working rules: the protocol in `packages/protocol` is the contract and changes only through the orchestrator; every change ships with tests; implementers do not review their own work.

## 7. Risks

| # | Risk | Mitigation |
|---|---|---|
| 1 | Unit economics: cost per live hour versus what students pay | Lean configuration, metered hours, measure real tokens in Phase 0 |
| 2 | Live adds little over notes just after class; an incumbent fast-follows | Experiment 1 in week 1; lead with the annotated replayable deck |
| 3 | Far-field Swedish transcription is poor in real halls | Bake-off, slide vocabulary as context, external mic option, batch re-transcription |
| 4 | Small model revises the wrong block or churns | Server-enforced edit rules, correction-cue trigger, scenario tests, Sonnet escape hatch |
| 5 | A mark lands on the wrong part of a figure | Text anchors first; region IDs only; drop unresolved targets; own 100–200 slide test set |
| 6 | Lecturer and university permission; GDPR for a lecturer's voice | Attestation, ask-your-lecturer template, transcript-only mode, EU storage, no training on user content, written legitimate-interest test before alpha |
| 7 | Vendor churn (Soniox is small; prices move) | Provider interfaces for STT and the model; log real usage |

## 8. Decisions for the founder

1. **Name** before any public page.
2. **Repository visibility**: this repo is public; product code and prompts probably should not be.
3. **API accounts**: the product needs its own Anthropic API key and an STT key. A Claude or ChatGPT subscription drives the coding agents but cannot power the product's own model calls.
4. **Beachhead**: KI medicine students first, as recommended, or the founder's own programme where access is easier.
5. **Budget** for the bake-off and alpha (order of $50–100 in API spend).
