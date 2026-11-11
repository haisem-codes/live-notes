# 03 - Agent architecture, model choice and realtime stack for Live Notes

Research date: 2026-11-11. Author: AI/backend architecture research (agent-produced).

## 0. How to read this report

**Verification legend**

- **[V]** verified today against a first-party page fetched directly (Anthropic pricing page, Google Cloud Vertex AI / Agent Platform pricing page, tldraw agent template README on GitHub), or against the `claude-api` reference bundled with Claude Code (cached 2026-11-03).
- **[S]** taken from web-search summaries of third-party or first-party pages that could not be opened directly from this sandbox. Treat as probably right, re-check before budgeting.
- **[U]** unverified: my own estimate, prior knowledge, or a claim with conflicting sources.

**Access limitation.** The sandbox could not open `openai.com`, `developers.openai.com`, `ai.google.dev`, `artificialanalysis.ai`, `arxiv.org`, `developers.cloudflare.com`, `livekit.io`, `convex.dev`, `supabase.com` or `tldraw.dev` directly. Consequently every OpenAI price, every latency benchmark, and every hosting price below is [S] or [U]. Google model prices are [V] because the Vertex AI page on `cloud.google.com` was reachable; the Gemini Developer API (`ai.google.dev`) usually matches it but was not checked.

**Cost numbers are estimates** built from stated token assumptions (section 5.3), not from measured runs. No pipeline was executed for this report.

---

## 1. Executive summary

1. **Loop shape.** Run a single-flight, event-driven "tick" loop per lecture: fire when a finalized transcript segment ends and at least ~50 new words are waiting, or 25-30 s have passed, or the slide changed, or a correction cue was heard. Expect 120-200 ticks per lecture hour. Add a slow lane (section close, every 5-8 min) and a final consolidation pass.
2. **Edit interface.** The model never regenerates the document. It emits small tool calls (insert / update / delete / move block, upsert diagram, annotate slide) against short, server-assigned block IDs. The server validates every op, sequences it into an append-only, timestamped op log, and that log is the product: live view, reconnect, replay and evaluation all read from it.
3. **Context.** Rebuild a ~12K-token prompt on every tick in stability order: tools and rules (global cache), slide digest and glossary (per-session cache), notes document, rolling summary, recent transcript, new chunk. Each tick is a stateless single request, which is what makes the session survive restarts.
4. **Models.** Claude Haiku 5.5 for the fast lane, Claude Sonnet 5.5 for section tidy-up and diagrams, Claude Opus 5.5 for post-lecture consolidation. Estimated LLM cost: about **$0.93 per lecture hour** for that configuration, **$0.23** for an all-Haiku live loop with a batched Sonnet clean-up, **$1.10** for a Sonnet live loop. Streaming STT will likely cost as much as or more than the LLM in the lean configuration.
5. **Speech-native realtime models** (OpenAI Realtime, Gemini Live) are the wrong tool here: one-way audio, no need for speech output or turn-taking, context that grows with audio tokens, session caps, and no word timestamps for replay. Keep STT + text LLM.
6. **Stack.** Python FastAPI WebSocket service with one asyncio "session actor" per lecture, Postgres as the source of truth (transcript segments + op log), object storage for audio and PDFs, managed auth. Vite + React web app first; a thin native wrapper for phones second, because web microphone capture stops on screen lock on iOS.
7. **Evaluation.** Build the replay harness before tuning prompts: cached STT event streams from public lectures replayed on a virtual clock, automatic churn/latency metrics from the op log, nugget-based coverage and claim-based correctness judged by a stronger model, and a suite of 2-5 minute micro-scenarios as the regression gate.

---

## 2. Q1 - Agent loop design for continuous input

### 2.1 What comparable systems do

| System | What happens live | Where the LLM runs | Source quality |
|---|---|---|---|
| Granola | Live transcript plus the user's own typed notes. No AI-written notes during the meeting. | After the meeting ("Enhance notes"): transcript + user notes turned into structured notes with quotes. User notes act as the signal for what matters. | [S] product pages and third-party write-ups; no first-party engineering post found |
| Notion AI meeting notes | Transcript builds live in the block. | Summary, action items and citations generated when recording stops; uses transcript + manual notes. | [S] third-party reviews |
| Google Meet "Take notes for me" | Notes visible during the call through the pencil icon; "Summary so far" for late joiners. | Runs during the call; full doc after. Update cadence is not documented anywhere I could find. | [S] |
| Otter | Live transcript; "Live Summary" for catching up. | Cadence undocumented; main summary after the meeting. | [S] |
| Cluely | Screen OCR + streaming STT + LLM suggestions in an overlay. | Claims a ~300 ms pipeline budget in its own blog; independent users report 5-10 s. | [S], first-party figure is marketing |
| Micro (Mastra blog, 2026-06-02) | Transcript treated as an event stream with a rolling local buffer; compact running summary of open issues for calls over an hour. | Agent is not invoked on every partial; small prompts; fast sub-agent model with tight output-token caps; sub-3-second answers. | [S] |
| tldraw agent starter kit | Not transcript-driven, but the closest public design for "model edits a shared artifact through streamed actions". | Each action is a tool call with a `_type` field first; the client applies each action as it finishes streaming; actions are sanitized (shape ID must exist / be unique) before being applied; coordinates are offset and rounded before the model sees them; a turn is capped at 20 follow-up requests. | [V] GitHub README |

Published research on the incremental pattern:

- **Progressive note-taking** (arXiv 2510.06677, customer support): prompt with the previous bullets and ask only for new ones; a relevance classifier drops redundant bullets; human edits are preserved across updates. [S]
- **Two patented rolling patterns**: (a) resend the full transcript at each checkpoint and replace the summary, (b) send a transcript chunk plus the existing summary. The filing notes that (b) grows in cost as the running summary lengthens. [S]
- **Agenda-aware streaming summarization** (Springer, 2025): segment by agenda item and update the summary per segment. The lecture analogue of the agenda is the slide deck. [S]

**Takeaways.** The most successful note products deliberately avoid AI-written notes during the session (Granola, Notion) and do the heavy work afterwards. Live Notes is doing the harder thing, so the design has to treat stability as a first-class requirement, not a polish item. The systems that are live keep prompts small, do not call the model on partials, and keep a rolling summary for long sessions.

### 2.2 Triggering strategies compared

| Strategy | Strengths | Weaknesses | Role in the design |
|---|---|---|---|
| Fixed time window (every N s) | Simple, predictable cost | Cuts sentences in half; wasted calls during silence; worst-case latency equals the window | Only as the maximum-wait backstop |
| Sentence / pause boundary (STT final segments, endpointing) | Chunks are complete thoughts, so fewer half-formed notes that need revising | Lecturers can talk for a minute without a clean pause; rate is uneven | Primary trigger, with a minimum-words gate |
| Topic shift / slide change | Right moment for structural decisions: new heading, close and freeze the previous section, diagram | Far too sparse for content capture; detection can be wrong | Triggers the slow lane and an immediate fast tick |
| Token-count threshold | Direct cost control | Blind to meaning | Used as the minimum gate (do not call for 5 words) and as the catch-up batch size after a reconnect |

### 2.3 Recommended cadence

**Fast lane** (small fast model, one request per tick):

```
fire a tick when no tick is in flight AND any of:
  A. a final STT segment just ended AND >= ~50 new words are unprocessed
  B. >= 25-30 s since the last tick AND any new final words exist
  C. slide-change event (manual flip or detector)
  D. correction cue in the new text ("sorry", "I meant", "correction", "that should be",
     "let me rephrase", "actually no") -> fire immediately, flag the tick as a revision tick
min spacing between tick starts: ~8 s
never consume STT partials (interim hypotheses); only finals
```

- Single-flight: while a tick is running, new text accumulates and the next tick fires as soon as the current one commits. This is what bounds cost and prevents interleaved writes.
- "Nothing to add" is a normal outcome. The model ends its turn without tool calls.
- Expected rate: about 180 ticks per hour at a speaking rate of ~150 words per minute. [U]

**Slow lane** (stronger model, ~8-12 times per hour): fires when a section closes (slide change sustained for ~20 s, or a topic shift the fast lane signalled, or 8 minutes at most). It tidies the just-closed section, merges duplicates, decides whether a diagram is worth drawing, marks the section frozen, and rewrites the rolling summary.

**Final lane**: one consolidation pass after the lecture (section 5).

### 2.4 Latency budget

What "live" has to mean for a note-taker is different from a voice agent. A human note-taker trails the speaker by a sentence or two. The live transcript ticker supplies the sub-second "it is listening" signal; the notes only need to be a sentence or two behind.

| Stage | Target | Notes |
|---|---|---|
| Speech to visible transcript text | < 1 s | Streaming STT partials rendered in a transcript strip, not in the notes |
| Utterance end to final segment | 0.3-1.0 s | STT endpointing [U] |
| Trigger wait | 0-25 s, typically 5-15 s | The dominant term, by design |
| LLM time to first op | 1-2 s target | Requires thinking off or minimal on the fast lane; see 5.2 |
| Op streamed, validated, committed, pushed | < 300 ms | In-process |
| **Spoken point to note on screen** | **p50 10-15 s, p95 <= 30-40 s** | |
| **Spoken correction to revised note** | **<= 15 s** | Trigger D bypasses the gate |

Lag of this size is acceptable; flicker is not. If a trade has to be made, lengthen the trigger gate before allowing the model to rewrite recent blocks more often.

---

## 3. Q2 - Document-editing interface and working context

### 3.1 Three options

| Option | Stability of earlier notes | Cost and latency per update | Streaming UX | Verdict |
|---|---|---|---|---|
| Full regeneration of the notes each tick | Poor: wording drifts everywhere, block identity is lost, user edits get overwritten | Output grows with the document: 4-6K output tokens per tick late in a lecture, 20-40 s at ~150 tokens/s, roughly 30x the output cost | Whole document re-renders | Reject for the live loop |
| Tool calls emitting patch ops against stable block IDs | Strong: untouched blocks are untouched by construction | Output is proportional to the change (typically 50-300 tokens) | Each tool call is a discrete unit that can be applied the moment it completes | **Recommended** |
| Streamed structured output (one JSON object or NDJSON of ops) | Same as tool calls if the ops are the same | Same | Needs incremental JSON parsing; "do nothing" is an empty array | Acceptable fallback; equivalent content, slightly worse ergonomics |

Supporting evidence: code-editing research finds full rewrite is only the cheapest format for short bodies, and adaptive patch formats cut latency and cost by over 30% on long edits (arXiv 2604.27296) [S]. Search/replace anchors fail when the anchor text is not unique or not found [S], which is why ops here address blocks by ID rather than by quoted text. A document-agent issue thread shows the identity problem concretely: a whole-document replace gives every block a new ID and orphans anything anchored to it; diffing at block granularity keeps IDs of unchanged blocks byte-identical [S]. Tiptap's AI Toolkit ships the same shape (read a node range, apply a patch, a per-node hash to avoid overwriting user changes) [S].

Why tool calls over structured output on Claude specifically [V, claude-api reference]:

- `strict: true` on each tool guarantees schema-valid arguments.
- Parallel tool use is on by default, so one response can carry several ops as separate `tool_use` blocks.
- `eager_input_streaming: true` on each tool streams the arguments as they are generated, so a long `text` field can be shown while it is being written. With it on, the API no longer validates the input for you: validate each parsed input against the schema before applying it.
- Forced `tool_choice` (`any` / named tool) is accepted on Haiku 5.5 but returns a 400 on Sonnet 5.5 and Opus 5.5. Use `tool_choice: auto` everywhere so the same loop code works on all three, and let "no tool call" mean "nothing to add".

### 3.2 Document model

A flat, ordered list of blocks with a depth field. Flat-with-depth is easier for a model to address than a nested tree, and it maps directly onto block editors such as BlockNote or Tiptap [U].

```
Block {
  id:      "b17"            # short, server-assigned, never reused
  kind:    h1 | h2 | bullet | definition | formula | example | question | callout | diagram
  depth:   0..2
  text:    inline markdown, LaTeX in $...$, <= ~40 words for non-heading kinds
  status:  tentative | stable | frozen | user_locked
  src:     [seg_id, ...]    # transcript segments this block was derived from
  slide:   int | null
  rev:     int
}
```

Short sequential IDs matter: they cost one or two tokens each and are far less likely to be mis-copied than UUIDs [U]. The tldraw kit does the equivalent by simplifying shape data and sanitizing IDs before applying actions [V].

### 3.3 Tool / operation schema exposed to the model

Eight tools, kept identical on every tick so the tool block stays cacheable. All use `strict: true` and `additionalProperties: false`.

| Tool | Arguments | Server rules |
|---|---|---|
| `insert_block` | `after` (block ID or `"end"`), `kind`, `depth`, `text`, `src` (segment IDs), `slide` (optional), `ref` (optional local alias usable by later ops in the same response) | Server assigns the real ID. Rejected if `after` is unknown. New blocks start `tentative`. |
| `update_block` | `id`, `text`, `reason` (`new_detail` / `teacher_correction` / `clarification` / `merge_duplicate` / `fix_transcription`), `src` | Replaces the text of one block. On `frozen` blocks only `teacher_correction`, `clarification` and `fix_transcription` are allowed. Never allowed on `user_locked`. |
| `delete_block` | `id`, `reason` (`superseded` / `duplicate` / `teacher_retracted`) | Same permission rules. Soft delete in the log. |
| `move_block` | `id`, `after`, `depth` | Allowed only inside the active section in the fast lane; anywhere non-locked in the slow lane. |
| `upsert_diagram` | `id` (existing diagram block) or `after`, `title`, `spec` | `spec` is a constrained graph: `{layout: "LR"|"TB", nodes: [{id, label}], edges: [{from, to, label?}]}`. Rendered deterministically on the client. Validated: edge endpoints must exist, size caps. |
| `annotate_slide` | `slide`, `target` = `{region: "r4"}` or `{quote: "exact phrase on the slide"}`, `style` (`highlight` / `circle` / `underline`), `note` (optional block ID to link) | The model never emits coordinates. The server resolves a region ID from the pre-computed region map, or resolves the quote against the PDF text layer. Unresolvable targets are dropped and logged. |
| `set_slide` | `slide`, `confidence` (`low` / `high`) | Only used when the student is not flipping manually (section 6.3). |
| `close_section` | `heading_id`, `summary` (<= 30 words) | Signals a topic boundary; queues the slow lane. |

Example definition (Anthropic Messages API tool format):

```json
{
  "name": "update_block",
  "description": "Replace the text of ONE existing note block. Use when the teacher corrects or clarifies something already noted, or to add a detail to a recent block. Do not use to rephrase a block whose meaning has not changed.",
  "strict": true,
  "eager_input_streaming": true,
  "input_schema": {
    "type": "object",
    "additionalProperties": false,
    "required": ["id", "text", "reason", "src"],
    "properties": {
      "id":     {"type": "string", "description": "Block ID exactly as shown in the notes, e.g. b17"},
      "text":   {"type": "string", "description": "Full new text of the block. Keyword-dense, <= 40 words."},
      "reason": {"type": "string", "enum": ["new_detail", "teacher_correction", "clarification", "merge_duplicate", "fix_transcription"]},
      "src":    {"type": "array", "items": {"type": "string"}, "description": "Transcript segment IDs that justify this change, e.g. [\"s412\"]"}
    }
  }
}
```

A diagram as a graph spec rather than free-form Mermaid text is a deliberate choice: a schema-validated node/edge list cannot fail to parse, can be laid out with any engine, and an update is a small re-send of the spec. Mermaid source is a reasonable alternative if it is parsed server-side and rejected on error. I found no measured error rate for model-written Mermaid, so the relative reliability is [U].

**What the server stores** (the envelope the model never sees):

```
Op {
  seq:         bigint          # total order per session, assigned by the server
  session_id:  uuid
  tick_id:     uuid            # all ops of one model response share it; unique-constrained for idempotency
  actor:       agent_fast | agent_slow | agent_final | user
  type:        block.insert | block.update | block.delete | block.move |
               diagram.upsert | slide.annotate | slide.annotation.remove | slide.set | section.close | section.freeze
  payload:     jsonb           # validated tool input with resolved IDs and resolved slide geometry
  t_emit_ms:   int             # audio position when the op was committed (replay = "as it happened")
  src_t0_ms / src_t1_ms: int   # audio span of the transcript segments cited in `src` (click a note -> hear it)
  wall_time:   timestamptz
  model:       text, usage: jsonb   # for cost and evaluation
}
```

Replay invariant: `document(t) = fold(ops where t_emit_ms <= t)`. Store a snapshot every ~200 ops so seeking does not refold from zero.

### 3.4 What keeps earlier notes stable

1. **Append bias in the prompt, enforced in the server.** The fast lane may freely edit only `tentative` blocks in the active section. Anything else needs an allowed `reason`. The server rejects the rest, so a prompt regression cannot cause document-wide churn.
2. **Freezing.** When a section closes, the slow lane tidies it once and marks its blocks `frozen`.
3. **Dwell time.** A block cannot be updated twice within ~20 s unless the reason is `teacher_correction`.
4. **User locks.** A block the student has edited becomes `user_locked`; the agent may add next to it but not change it. This is the same rule the progressive note-taking paper uses for human edits [S].
5. **One writer.** The server is the only sequencer. Student edits go through the same op log. No CRDT is needed while there is one human editor per session; revisit if shared editing is added.
6. **Rejected ops are dropped, not retried.** Each tick is one request. The next tick sees the true document. Only a `read_section` call (rare, long lectures only) costs a second round trip.
7. **Word-level diff on the client.** For `block.update` the client diffs old and new text and animates only the changed words.

### 3.5 Working context for a 2-hour lecture

Rebuilt from the database on every tick, in stability order:

```
[tools]                         8 tool definitions, byte-identical on every request
[system]                        role, note style guide, edit rules, 2-3 worked examples      ~2,500 tok  -> cache breakpoint 1 (global)
[user content block 1]          slide digest: per-slide title + 1-2 line summary + region IDs,
                                glossary of key terms                                         ~5,000 tok  -> cache breakpoint 2 (per session)
[user content block 2]          notes document, compact line format, frozen sections first   ~3,500 tok avg (see below)
[user content block 3]          rolling summary of everything older than the transcript window  ~500 tok
[user content block 4]          current slide: full text + region list                        ~400 tok
[user content block 5]          recent transcript (last ~90 s, already processed, for continuity)
                                + NEW segments since the last tick, each tagged [s412 31:07]   ~500 tok
```

Notes rendered for the model as one line per block:

```
[b12|h2|frozen] Gradient descent
[b13|bullet|frozen] update rule: theta <- theta - eta * grad L(theta)
[b14|bullet.1|stable] eta = learning rate; too large -> diverges
[b15|def|tentative] convex: any local min is the global min
```

Growth control: concise notes run at roughly 8-15% of transcript length [U], so one hour produces 1.5-2.5K tokens of notes plus ID overhead. For lectures up to about 75 minutes the whole document fits in ~6K tokens and is shown in full. Beyond that, the oldest frozen sections collapse to their heading plus a key-term line, and the model gets a `read_section(heading_id)` tool for the rare case where a correction reaches that far back. This keeps the prompt near 12-15K tokens for the entire two hours.

The rolling summary is rewritten by the slow lane only, so it changes ~10 times an hour instead of 180.

### 3.6 Prompt caching against a changing document

Mechanics that matter [V, claude-api reference and Anthropic pricing page]:

- Caching is a **prefix match**. Render order is `tools` -> `system` -> `messages`. A changed byte invalidates everything after it.
- Up to 4 breakpoints. Minimum cacheable prefix is 512 tokens on Haiku 5.5, Sonnet 5.5 and Opus 5.5.
- 5-minute TTL entries are refreshed for free by every read. With ticks every ~20 s the cache stays warm through the whole lecture; the 1-hour TTL (2x write price) buys nothing here. A 10-minute break costs one re-write of ~7.5K tokens, which is negligible.
- Cache reads: 0.1x input on Haiku 5.5, 0.05x on Sonnet 5.5 and Opus 5.5. Writes: 1.25x (5-minute).
- Caches are per model. The fast lane and slow lane do not share entries.
- Silent invalidators to keep out of the prefix: timestamps, session IDs, non-deterministic JSON key order, a tool list that varies per tick.
- Verify with `usage.cache_read_input_tokens` on every response and alert when it drops to zero.

**Design A - stateless rebuild (recommended).** The changing document sits after the two cached blocks. About 60% of each prompt (tools + rules + slide digest) is read from cache; the document and transcript are paid at full input price. On Haiku 5.5 that full-price part costs about $0.09 per lecture hour, so optimizing further is not worth any complexity. An optional third breakpoint after the frozen sections (which are append-mostly) recovers most of the rest.

**Design B - append-only log.** Each tick appends the new transcript chunk as a user turn and the model's tool calls as an assistant turn; the document is implicit in the history. Nearly the whole prompt is a cache read and only the delta is written. Every ~10 minutes the conversation is re-based onto a fresh document snapshot. This cuts a Sonnet-class live loop from about $2.17 to about $0.75 per hour (section 5.3). Costs: per-session conversation state that must survive restarts, and on the 5.5 models editing earlier turns invalidates replayed thinking blocks, so a re-base must start a new conversation rather than rewrite the old one [V].

Recommendation: Design A on Haiku 5.5. Move to Design B only if evaluation shows the fast lane needs a Sonnet-class model.

On OpenAI, caching is automatic for repeated prefixes with cached input at about 10% of the input price [S]; some sources also list a cache-write price on a 30-minute tier for the GPT-6 family [U]. On Gemini, cached input is 10% of input [V] with separate storage charges for explicit caches (rate not extracted) [U]. The same stability-ordered prompt works on all three.

---

## 4. Recommended architecture

```
                         BEFORE THE LECTURE
  slides.pdf --> [slide prep job] --> slide digest, glossary/keyterms, region map, page images
                       |                         |                |
                       v                         v                v
                  object storage             Postgres        STT keyterm list

                         DURING THE LECTURE
 +----------------------- client (web app) ------------------------+
 | mic -> AudioWorklet -> 16 kHz PCM frames (seq-numbered)         |
 |      -> local chunk recorder (OPFS/IndexedDB) = audio of record |
 | notes view (block reducer) | slide view + annotations | ticker  |
 +----------|--------------------------------------^---------------+
            | WebSocket: audio up, {resume,last_seq} |  ops + transcript down
            v                                        |
 +------------------ FastAPI service (session actor per lecture) ----------------+
 |                                                                               |
 |  audio ingest --> streaming STT provider (WebSocket) --> partials -> ticker   |
 |       |                                   |                                   |
 |       v                                   v finals (+word timestamps)         |
 |  audio chunks -> object storage     transcript_segments (Postgres)            |
 |                                           |                                   |
 |                                  +--------v---------+                         |
 |                                  | trigger policy   |  A boundary+50 words    |
 |                                  | (single-flight)  |  B 25-30 s  C slide  D cue
 |                                  +---+----------+---+                         |
 |                         fast lane    |          |   slow lane (section close) |
 |                     Claude Haiku 5.5 |          | Claude Sonnet 5.5           |
 |                  context builder ----+          +---- context builder         |
 |                  (rules | slides | notes | summary | transcript window)       |
 |                                  |  streamed tool calls                       |
 |                                  v                                            |
 |                   op validator / sequencer (permissions, ID + slide           |
 |                   geometry resolution, tick_id idempotency)                   |
 |                                  |                                            |
 |                 one transaction: append ops + advance transcript cursor       |
 +----------------------------------|--------------------------------------------+
                                    v
                    Postgres: sessions, transcript_segments, ops, snapshots, slides
                                    |
                         AFTER THE LECTURE
        [consolidation job: Claude Opus 5.5 over full transcript + slide digest + live notes]
              -> emits ops (actor = agent_final) into the same log
        [replay player] audio + fold(ops where t_emit_ms <= t) + slide annotations
        [eval harness]  reads the same op log
```

Properties this buys:

- **Restart safety.** The actor holds no state that is not in Postgres. A tick commits its ops and the transcript cursor in one transaction, keyed by `tick_id`. After a crash or deploy, any process takes the session lease, loads snapshot + ops, and continues from the cursor.
- **Reconnect safety.** The client sends `{resume, last_seq}`; the server replays ops after `last_seq`, then goes live. Ops are idempotent by `seq`.
- **Audio safety.** The client records locally and numbers its frames. After a wifi drop it re-sends what the server missed; the server de-duplicates by frame number, back-fills the gap through STT, and the agent runs a catch-up tick with a larger batch.
- **Replay and evaluation for free.** Both are folds over the op log.

---

## 5. Q3 - Model choice and cost

### 5.1 Price table (per million tokens, standard tier)

| Model | Input | Cached input | Output | Notes | Status |
|---|---|---|---|---|---|
| Claude Haiku 5.5 `claude-haiku-5-5` | $0.10 | $0.01 (5-min write $0.125) | $0.50 | For prompts up to 100K tokens. Above that the whole request is $0.50 / $0.05 / $2.50. 1M context. | [V] |
| Claude Sonnet 5.5 `claude-sonnet-5-5` | $2.00 | $0.10 (write $2.50) | $10.00 | 1M context | [V] |
| Claude Opus 5.5 `claude-opus-5-5` | $4.00 | $0.20 (write $5.00) | $20.00 | 1M context | [V] |
| Claude Fable 5.2 `claude-fable-5-2` | $8.00 | $0.20 | $40.00 | Top tier; not needed for this product | [V] |
| Claude Batch API | 50% off input and output | | | For consolidation and slide prep | [V] |
| GPT-6 Luna | $0.10 | $0.01 | $0.50 | OpenAI's cheapest current model per several trackers | [S] |
| GPT-6.1 Terra | $1.00 | $0.05 | $5.00 | Released 2026-10-26 per trackers; higher rates above 272K input tokens | [S] |
| GPT-6.1 Sol | $2.00 | $0.20 | $10.00 | Naming inconsistent across sources ("GPT-6 Sol" vs "GPT-6.1 Sol") | [U] |
| GPT-6 Astra | $10.00 | n/a | $50.00 | Flagship, released 2026-09-03 per one tracker | [S] |
| GPT-5.6 Luna / Terra / Sol | $0.20 / $2 / $5 | $0.02 / $0.20 / $0.50 | $1.20 / $12 / $30 | After the 2026-07-30 price cut; previous generation | [S] |
| Gemini 3.8 Flash | $0.75 | $0.075 | $3.75 | Introductory price through 2026-12-31; **$1.50 / $0.15 / $7.50 from 2027-01-01** | [V] |
| Gemini 3.5 Flash-Lite | $0.30 | $0.03 | $2.50 | | [V] |
| Gemini 3.1 Flash-Lite | $0.25 | $0.025 | $1.50 | Audio input $0.50 | [V] |
| Gemini 4 Argon | $2.00 | $0.10 | $10.00 | Promotional through 2026-11-30; **$4.00 / $0.20 / $20.00 from 2026-12-01** | [V] |
| Gemini 3.1 Pro Preview | $2.00 | $0.20 | $12.00 | $4 / $18 above 200K input tokens | [V] |
| Gemini 3.8 Live API | text $0.75, audio $3.00 | n/a | text $4.50, audio $12.00 | Audio billed at 25 tokens per second | [V] |
| Gemini 3.5 Transcribe Live | audio $3.50 | n/a | text $21.00 | Google's stated blended price: $0.008925 per audio minute | [V] |
| OpenAI realtime (gpt-realtime-2.x) | audio $32, text $4 | cached audio $0.40 | audio $64, text $16-24 | Model naming and text rates differ between sources | [S] |

Tokenizer note: Claude 4.7-and-later models, including all three 5.5 models, produce roughly 30% more tokens for the same text than earlier Claude models [V]. The estimates below use a Claude-sized transcript count for every vendor, which slightly overstates the non-Claude rows.

### 5.2 Latency, tool use, vision

**Latency.** The only figures found are Artificial Analysis snapshots relayed through search summaries [S]:

- Claude Haiku 5.5: about 170 output tokens/s at low effort and 137 at medium, with about 8 s and 13 s to the first answer token respectively. Those times include thinking.
- Gemini 3.8 Flash (high): about 285-305 tokens/s, 13-25 s to the first answer token depending on the page.
- The previous generation, Haiku 4.5 without reasoning, was reported at 0.56-1.0 s to first token.

The implication is firm even though the numbers are second-hand: on every current small model, **reasoning is what breaks the live latency budget**, not raw generation speed. No source measured Haiku 5.5 with thinking off, so the 1-2 s target in section 2.4 is [U] and is the first thing to measure. On Haiku 5.5, `thinking: {"type": "disabled"}` is accepted at effort `low`, `medium` and `high`; thinking is on by default and the default effort is `medium` [V]. Anthropic's latency guidance points time-sensitive applications at Haiku 5.5 with low effort [S]. Plan to test both thinking-off and low effort and choose on measured latency and note quality.

API constraints that shape the loop [V]:

| | Haiku 5.5 | Sonnet 5.5 | Opus 5.5 |
|---|---|---|---|
| Thinking off | `disabled` allowed at effort <= high | `disabled` is a 400; use `{"type": "between_tools"}` at effort <= high | Cannot be turned off; lower effort instead |
| Forced `tool_choice` | Accepted (skips thinking) | 400 | 400 |
| `temperature` / `top_p` / `top_k` | Non-default values 400 | Non-default values 400 | 400 |
| Refusal (`stop_reason: "refusal"`) | No server-side fallback: handle in code | Server-side `fallbacks` available | Server-side `fallbacks` available |
| Documented caveat | With thinking off, can skip a needed tool call when the request also asks for JSON output | | Default effort is `medium` |

**Tool-use reliability.** I found no current head-to-head benchmark of tool-call validity for Haiku 5.5, GPT-6 Luna and Gemini 3.8 Flash. Schema-constrained tool arguments exist on Anthropic (`strict: true`) [V] and on OpenAI and Google [U]; that removes malformed-JSON failures on all three. What remains is semantic reliability (right block ID, edit instead of duplicate), which only the evaluation harness in section 8 can measure. Design for it: validate everything, drop bad ops, measure the rejection rate.

**Vision (reading slides).** All three vendors take PDF pages or images directly [U for OpenAI and Google]. Claude accepts PDFs as `document` blocks, up to 600 pages and 32 MB per request [V]; each page costs roughly 1.5-3K tokens as text plus image [U]. In this design vision is used once per deck before the lecture, never in the live loop, so vision cost and latency are not live concerns. Use a Sonnet-class model for slide prep if the deck is figure-heavy; region maps for figures are where a weaker vision model will hurt.

### 5.3 Cost per lecture hour

**Assumptions** (all [U], chosen conservatively):

| Quantity | Value |
|---|---|
| Speech | 150 words/min -> 9,000 words/h -> ~15,000 transcript tokens/h (Claude tokenizer) |
| Fast-lane ticks | 180 per hour |
| Fast-lane prompt (Design A) | 12,400 tokens = 7,500 cached (rules 2,500 + slide digest 5,000) + 4,900 uncached (notes 3,500 avg, summary 500, slide 400, transcript 500) |
| Fast-lane output | 150 tokens per tick average, thinking off -> 27,000 tokens/h |
| Slow-lane calls | 10 per hour; 13,500 input tokens each, assumed uncached (gaps exceed the 5-minute TTL); 2,000 output tokens each including thinking |
| Consolidation | 27,000 input (15,000 transcript + 5,000 slide digest + 5,000 live notes + 2,000 rules), 12,000 output including thinking, per lecture hour |

**Fast lane, Design A, per hour**

```
uncached input : 180 x 4,900  =   882,000 tok
cached input   : 180 x 7,500  = 1,350,000 tok
output         : 180 x   150  =    27,000 tok

Haiku 5.5  : 0.882 x $0.10 + 1.35 x $0.01  + 0.027 x $0.50  = $0.088 + $0.014 + $0.014 = $0.115
Sonnet 5.5 : 0.882 x $2.00 + 1.35 x $0.10  + 0.027 x $10.00 = $1.764 + $0.135 + $0.270 = $2.17
GPT-6 Luna : same rates as Haiku 5.5                                                    = $0.115  [S prices]
Gemini 3.8 Flash (promo)   : 0.882 x $0.75 + 1.35 x $0.075 + 0.027 x $3.75             = $0.86
Gemini 3.8 Flash (2027)    : 0.882 x $1.50 + 1.35 x $0.15  + 0.027 x $7.50             = $1.73
Gemini 3.5 Flash-Lite      : 0.882 x $0.30 + 1.35 x $0.03  + 0.027 x $2.50             = $0.37
```

**Fast lane on Sonnet 5.5, Design B (append-only, cached), per hour**

```
context per tick averages ~15,500 tok (7,500 base + 3,500 notes snapshot + 0..9,000 growth between re-bases)
cache reads  : 180 x 15,500 = 2,790,000 tok x $0.10 = $0.28
cache writes : 180 x 300 delta + 6 re-bases x 3,500 + 7,500 initial = 82,500 tok x $2.50 = $0.21
output       : 27,000 tok x $10 = $0.27
total        = $0.75   (rounded from $0.76)
```

**Slow lane, per hour**

```
Sonnet 5.5 : 10 x (13,500 x $2.00/M + 2,000 x $10.00/M) = 10 x ($0.027 + $0.020)   = $0.47
Haiku 5.5  : 10 x (13,500 x $0.10/M + 2,000 x $0.50/M)  = 10 x ($0.00135 + $0.001) = $0.024
```

**Consolidation, per lecture hour**

```
Opus 5.5         : 27,000 x $4/M + 12,000 x $20/M = $0.108 + $0.240 = $0.35     (Batch API: $0.17)
Sonnet 5.5       : 27,000 x $2/M + 12,000 x $10/M = $0.054 + $0.120 = $0.17     (Batch API: $0.09)
GPT-6.1 Terra    : 27,000 x $1/M + 12,000 x $5/M  = $0.027 + $0.060 = $0.09     [S prices]
Gemini 4 Argon   : $0.17 through 2026-11-30, $0.35 from 2026-12-01
adding the raw PDF (40 pages x ~2,000 tok = 80,000 tok) adds $0.32 on Opus 5.5, $0.16 on Sonnet 5.5
```

**Three configurations**

| Configuration | Fast lane | Slow lane | Consolidation | **LLM cost per lecture hour** |
|---|---|---|---|---|
| **1. Lean** | Haiku 5.5 $0.115 | Haiku 5.5 $0.024 | Sonnet 5.5 via Batch $0.09 | **~$0.23** |
| **2. Recommended** | Haiku 5.5 $0.115 | Sonnet 5.5 $0.47 | Opus 5.5 $0.35 | **~$0.93** ($0.76 with batched consolidation) |
| **3. Premium live** | Sonnet 5.5, Design B $0.75 | folded into the fast lane | Opus 5.5 $0.35 | **~$1.10** |

Other one-off and adjacent costs:

- **Slide prep, once per deck** (40 slides, 83,000 input tokens including the PDF, 10,000 output): Sonnet 5.5 about $0.27 ($0.13 batched); Haiku 5.5 about $0.013. Keep each Haiku request under 100K prompt tokens or it is billed at five times the rate: split large decks into chunks of ~30 pages.
- **Sensitivity.** Doubling the tick rate to every 10 s roughly doubles the fast lane (Haiku: $0.23). Leaving thinking on at low effort adds perhaps 36-90K output tokens per hour (Haiku: +$0.02-0.05).
- **STT is outside this report's scope** but for scale: Google lists its live transcription at $0.0089 per audio minute, about $0.54 per hour [V]. In configuration 1 the LLM is the smaller line item.

### 5.4 Should a small model run the loop with a stronger one for diagrams and clean-up?

Yes. The reasoning:

- The fast lane's job is narrow: turn 50-100 new words into zero to three small ops against a document it can see. That is a small-model task, and the latency budget favours the fastest model with thinking off.
- The judgement-heavy work is infrequent: deciding the outline, merging duplicates, choosing whether something deserves a diagram, reconciling the whole lecture. Ten slow-lane calls and one consolidation call per hour concentrate the expensive tokens where they change the result.
- The claude-api guidance cautions that a multi-model cascade forfeits cache sharing and that a stronger model at lower effort should be measured first. Here the lanes have different prompts and different cadences, so there is little cache to share, and the measured alternative (Sonnet 5.5 in the fast lane) costs 7-19x more for the lane that runs 180 times an hour. It stays in the plan as configuration 3 in case evaluation shows Haiku cannot handle corrections reliably.

### 5.5 Is a speech-native realtime model viable instead of STT + text LLM?

Not as the primary pipeline. Reasons, in order of weight:

1. **The product needs a timestamped transcript anyway.** Replay sync, click-a-note-to-hear-it, search and evaluation all depend on word timestamps. A speech-native model that listens and writes notes does not produce them, so STT would still run.
2. **The interaction is one-way.** Realtime models are built and priced for low-latency spoken dialogue: turn detection, barge-in, speech output. A lecture uses none of it.
3. **Context and session limits.** Gemini Live: audio accumulates at 25 tokens per second (90,000 tokens per hour) against a 128K session context; audio-only sessions are capped at 15 minutes without context-window compression, and compression works by discarding or summarizing the oldest turns; a connection lasts around 10 minutes and needs session resumption [S, Google and Firebase docs]. OpenAI Realtime: session length is reported as about 30 minutes, and the API drops the oldest items when the context fills [S, the 30-minute figure is a user report]. A 2-hour lecture fights both.
4. **Cost.** OpenAI realtime audio input at $32 per million tokens and roughly 600 tokens per minute is about $1.15 per hour just to hear the lecture once, before the accumulated audio context is re-read on each response and before any output [S prices, my arithmetic]. Gemini Live audio input is about $0.27 per hour for one pass [V prices], which is competitive with STT, but item 3 still applies and how accumulated context is billed per turn is [U].
5. **Control.** With STT + text, the trigger policy, the context, the glossary boosting and the model are each independently testable and swappable. A speech-native session is one opaque box.

Where these models do fit: as the transcription engine (OpenAI's realtime transcription mode, Gemini 3.5 Transcribe Live), if the STT research prefers them. One further option worth a cheap experiment later: a Gemini text model accepts audio input directly, so a slow-lane call could be given the raw audio of a section to catch what STT garbled. That is [U] and not needed for v1.

---

## 6. Q4 - Pre-lecture slide processing and slide tracking

### 6.1 Extraction pipeline (runs once per deck, asynchronous, batchable)

| Step | Tool | Output |
|---|---|---|
| 1. Native text + geometry | PyMuPDF (reads the PDF text layer with word boxes; fast; returns nothing for scanned pages) | Per-page words with bounding boxes, image and drawing rectangles, page PNGs |
| 2. Layout regions | Cluster step-1 geometry into regions (title, bullet group, figure, equation, table). For image-only or scanned decks, fall back to a layout/OCR parser: Docling (MIT-licensed, strong on structure and tables), Marker or MinerU. Marker's weights need a paid licence above a revenue threshold. | Region map: `{slide, region_id, kind, bbox (0-1 normalized), text}` |
| 3. Semantic pass | One vision-capable model call per ~30 pages with the page images and the region list | Per-slide title, 1-2 line summary, what each figure shows, key terms, and corrections to region labels |
| 4. Glossary | Deduplicate key terms across slides, add expansions for acronyms | Keyterm list for STT boosting and for the notes prompt |
| 5. Retrieval index | Embed each slide's text + summary; keep a BM25 index of slide words | Used by the slide tracker |

Parser comparisons above are from 2026 third-party benchmarks and vendor posts [S]; none of them measured figure bounding boxes on slides, so step 2 needs its own small test on real decks.

Design rule: **the live loop never sees a slide image and never emits a coordinate.** It sees region IDs and text; the server turns `region: "r4"` or `quote: "..."` into geometry. Phrase highlights resolve against the step-1 word boxes, which is exact. Figure circles depend on step 2 being right, which is the weaker link.

How this keeps the live loop cheap: the digest (~120 tokens per slide) is a cached prefix; only the current slide's full text is added per tick.

STT boosting: pass the glossary as the STT provider's keyterm / custom-vocabulary input at stream start. Provider-specific limits and effectiveness are for the STT report [U].

### 6.2 Detecting the current slide from the transcript

What the literature says [S]:

- **MaViLS** (Interspeech 2024, arXiv 2409.16765): benchmark for aligning lecture video to slides using speech-transcript, OCR and visual features. A jump penalty that discourages frequent slide switches improves accuracy on average but hurts on lectures with many switches.
- **"Attend to what I say"** (ICDAR 2025, arXiv 2601.10244): matches transcript lines to OCR'd slide regions by embedding similarity or by asking a language model which region is relevant; in its user study about half of participants found highlighting useful, especially when joining midway. Check the paper before quoting figures.
- Older work aligns speech to slide word order with a sequential hidden Markov model.

A transcript-only tracker in the same spirit:

```
every time a final segment arrives:
  window  = last 30-45 s of transcript
  score_i = 0.5 * BM25(window, slide_i) + 0.5 * cosine(embed(window), embed(slide_i))
  prior   = stay: high | next slide: medium | +2..+3 or -1: low | arbitrary jump: very low
  decode with Viterbi over (score x prior); switch only if the new slide wins by a margin
  for two consecutive windows (hysteresis)
explicit cues override: "next slide", "go back to", "as this graph shows", a slide title read aloud
```

The cheapest additional signal is the notes model itself: it already has the slide digest in context and can call `set_slide` with a confidence, at no extra request.

Where it will fail: slides that share vocabulary, long stretches where the teacher talks off-slide, backward jumps, and demos. Expect it to be right most of the time and wrong at exactly the moments that matter for annotation.

### 6.3 Recommendation: manual flip is authoritative, auto-follow is assistive

- If the student moves the slide, that is ground truth; log it as a `slide.set` op by `actor = user` and pause auto-follow.
- If the student is not touching the slides, auto-follow with the tracker, and show a non-blocking "teacher seems to be on slide 14" chip when the tracker disagrees with what is on screen.
- Record tracker output alongside manual flips. Every lecture then yields labelled data for tuning the tracker.
- Annotations attach to the slide the op names, not to whatever is on screen, so a wrong follow never misplaces a highlight.
- v1 can ship with manual flip plus the model's `set_slide` hint, and add the retrieval tracker once the harness can score it.

---

## 7. Q5 - Realtime backend and app stack

### 7.1 Options for the long-lived per-lecture session

| Option | Fit for "ingest audio, run loop, fan out ops" | Restart / reconnect story | Solo-founder fit | Cost at small scale |
|---|---|---|---|---|
| **Python FastAPI + WebSocket, session actor per lecture** | Direct fit. One asyncio task group per session: client socket, STT socket, tick loop. Every AI SDK is first-class in Python. | You build it: state in Postgres, lease per session, resume by `last_seq`. Straightforward because ticks are stateless. | Best: the founder's home stack; coding agents are strong at it. | One small always-on instance, roughly $5-25/month [U] |
| TypeScript (Node or Bun, Hono) | Same shape. Advantage: op schema types shared with the client. | Same as above. | Good, but a second language for the backend. Type sharing can be had from Python by generating TypeScript types from the Pydantic models' JSON Schema. | Same |
| Cloudflare Durable Objects / PartyKit | Architecturally the cleanest: one object per lecture is the session actor, with built-in SQLite storage and WebSocket handling. | Good. Objects restart on deploy, so the same resume logic is still needed. Hibernation does not help while an outbound STT socket is open, but duration cost is tiny (128 MB for an hour is about 460 GB-s, well under a cent at the quoted ~$12.50 per million GB-s) [S/U]. | JavaScript/TypeScript runtime with CPU and memory limits; a new platform and language for the founder. | Very low [S] |
| Convex | Excellent for the fan-out half: ops as rows, clients subscribe reactively. Not a place to hold an audio/STT stream; long-running work must live in a separate worker. | Fan-out and reconnect are handled for you. | TypeScript functions; adds a second backend alongside the Python worker. | Free tier, then about $25 per developer per month [S] |
| Supabase (Postgres + Auth + Storage + Realtime) | Not a compute host for the loop. Very good data plane: auth, Postgres, object storage, optional Broadcast for fan-out. | Database-level durability; Realtime reconnects itself. | Good as a companion to FastAPI. | Free tier, then about $25/month [S] |
| LiveKit Agents | Python agent framework on WebRTC. Strong capture transport and worker lifecycle. Built for two-way voice agents; this product uses a fraction of it. | Good for media; the notes op log is still yours to build. | Familiar to a voice-AI engineer, but heavy for one-way ingest. | LiveKit Cloud meters agent session minutes at about $0.01/min beyond plan allowances, i.e. about $0.60 per lecture hour, plus participant minutes [S]. That is more than the whole lean LLM budget. Self-hosting avoids it. |

A point specific to this product: WebRTC trades completeness for latency. For transcription and for the audio of record, a reliable ordered stream with local buffering is the better trade. That, plus cost, is why LiveKit is not the v1 recommendation.

### 7.2 Recommended stack

| Layer | Choice | Why |
|---|---|---|
| Realtime service | FastAPI (ASGI, uvicorn), one WebSocket per client, one session actor per lecture | Home stack; stateless ticks make durability simple |
| LLM access | Vendor SDKs directly in the hot loop (Anthropic first), behind a thin internal interface | The loop depends on cache breakpoints, streamed tool-call events and usage fields; an abstraction layer makes those harder to control. LangChain remains fine for offline jobs. [U opinion] |
| Database | Postgres: `sessions`, `transcript_segments`, `ops`, `snapshots`, `slides`, `slide_regions` | One source of truth; op log is append-only |
| Auth | Managed (Supabase Auth or similar); JWT verified in FastAPI; WebSocket authenticated by a short-lived token in the first message | No auth code to maintain |
| Object storage | S3-compatible (Supabase Storage or Cloudflare R2) for audio chunks, PDFs, page images | Audio is small: Opus at 24-32 kbps mono is about 11-14 MB per hour |
| Jobs | Slide prep and consolidation as background tasks (a Postgres-backed queue is enough); Anthropic Batch API for both | Halves the cost of the two heaviest calls |
| Hosting | One always-on container on a PaaS (Fly.io, Render or Railway), single region near users | WebSockets need a long-lived process; serverless functions do not fit |
| Web app | Vite + React SPA, installable as a PWA | The app is an authenticated realtime tool; server rendering adds little. Next.js is reasonable if public share/replay pages and the marketing site should live in the same project. |
| Notes editor | A block editor with stable block IDs and a block-level API (BlockNote or Tiptap), driven by a reducer over ops | Agent ops and user edits map one-to-one onto editor operations [U on current APIs] |
| Observability | Log every tick: prompt hash, usage, latency, ops proposed / accepted / rejected | Granola found it necessary to build its own tracing tools for exactly this class of product [S] |

### 7.3 The hard operational cases

**Server restart or deploy mid-lecture**

- On SIGTERM: stop accepting sessions, finish or abandon the in-flight tick (the transaction makes abandonment safe), send `server_restarting`, close.
- The client reconnects to the new process with `{resume, last_seq, last_audio_frame}`.
- The new process takes the session lease (a row with owner and expiry, or a Postgres advisory lock), loads the latest snapshot plus later ops, reopens the STT stream with the correct time offset, and resumes from the transcript cursor.
- A tick that was cut off is simply re-run: its `tick_id` never committed.

**Bad wifi**

- The client always records locally in chunks and numbers audio frames. That local recording is the audio of record.
- On reconnect it re-sends frames the server has not acknowledged; the server de-duplicates by frame number.
- Gaps longer than a few seconds are back-filled: the late audio goes through STT (streaming if short, batch if long), the transcript segments get their true timestamps, and a catch-up tick processes them in one larger batch.
- The UI shows "catching up" rather than pretending to be live.
- Ops down are small; if WebSockets are blocked on a campus network, fall back to server-sent events for ops and chunked HTTPS uploads for audio.

**Operation log persistence**

- `ops` is append-only with `(session_id, seq)` as the key and a unique constraint on `(session_id, tick_id, index)`.
- Ops and the transcript cursor commit together.
- Snapshots every ~200 ops and at lecture end.
- Fan-out is in-process while there is one instance. When there are two, add Postgres LISTEN/NOTIFY or Redis pub/sub; do not add it earlier.

**Audio storage**

- Upload client chunks resumably during the lecture; finalize to one Opus file per session afterwards.
- Keep the per-chunk start offsets so `t_emit_ms` and `src_t0_ms` map onto the final file.
- Decide retention and consent rules early; recording a lecture is a policy and legal question in many institutions (not researched here).

**Capacity.** A session is one client socket, one STT socket and a request every ~20 s. It is I/O-bound; one small instance should carry dozens of concurrent lectures [U]. Per-session rate against the LLM API is about 3 requests per minute.

### 7.4 Web vs desktop vs mobile, and microphone capture

| Platform | Mic capture in a lecture hall | Screen lock / backgrounding | Verdict |
|---|---|---|---|
| Laptop, web app | Works in all major browsers. Built-in laptop mics are mediocre from mid-hall; allow choosing an external or Bluetooth mic. | Capture continues while the tab is open and the laptop is awake; sleep or lid close ends it. | **Primary v1 target.** It is also where a student wants notes and slides side by side. |
| iPhone / iPad, web or home-screen web app | Works in the foreground. `getUserMedia` must be called directly in the tap handler or Safari refuses it. | Capture is muted when the screen locks or the app is backgrounded. This is long-standing WebKit behaviour reported in WebKit bug 226620 and Apple developer forum threads [S]. The Screen Wake Lock API can keep the screen on while the page is visible; sources conflict on its iOS support history, so treat it as [U] and test on current devices. It does not survive switching apps and it drains the battery. | Usable only as "phone propped up, screen on, app in front". Not a reliable recorder. |
| Android, web | Works in the foreground. | Background and screen-off behaviour without a native foreground service is not dependable [U]. | Same caveat. |
| Native wrapper (Capacitor around the same React app, or React Native) | Native recording with the audio background mode keeps capturing with the screen locked [S for iOS]. | Solved by the platform's background-audio entitlement. | **Phase 2.** The phone can also act as a remote microphone near the lecturer, paired to the laptop session. |
| Desktop app (Tauri or Electron) | Same microphone as the web app. Its real advantage is capturing system audio for online lectures, which is how Granola avoids meeting bots [S]. | Can keep running in the background. | Not needed for in-person lectures. Revisit if recorded/online lectures become a target. |

Recommendation: ship the web app for laptops first; make the PWA honest on phones (wake lock where available, a visible "keep this screen on" state, local chunk recording so nothing is lost when capture is interrupted); then add the native wrapper with background recording.

---

## 8. Q6 - Evaluation

### 8.1 Replay harness

1. **Corpus.** 20-30 public lectures with slide PDFs across subjects (maths-heavy, biology, humanities, CS). MIT OpenCourseWare publishes many courses with lecture video, slides and transcripts under a Creative Commons licence [U on exact licence terms per course]. Research sets to draw from: M3AV (about 367 hours of academic talks with slides and speech, ACL 2024), SlideSpeech, LPM, VT-SSum (segmentation and summarization from VideoLectures.NET), and MaViLS for slide-timing ground truth [S]. Check each licence before storing derived data.
2. **Fixtures.** Run each recording through the production streaming STT once and store the full event stream (partials and finals with timestamps). Also store the slide prep output. Fixtures are regenerated only when STT or slide prep changes.
3. **Simulator.** Replay the event stream into the real trigger policy and tick loop on a virtual clock. LLM latency is measured for real and added to virtual time, so single-flight behaviour and op timestamps are faithful. Output: an op log identical in form to production.
4. **Repeatability.** Sampling parameters cannot be pinned on the current Claude models, so run each configuration 3 times and report mean and spread.

### 8.2 Metrics computed from the op log (no judge needed)

| Metric | Definition | Why |
|---|---|---|
| Churn ratio | Tokens removed or replaced by `update`/`delete` divided by tokens ever inserted | Headline stability number |
| Survival rate | Share of live-inserted tokens still present at lecture end, before consolidation | Did live effort produce lasting notes |
| Flicker count | Blocks updated two or more times within 60 s | What the student perceives as instability |
| Frozen-edit rate | Updates to frozen blocks per hour, by `reason` | Should be low and dominated by corrections |
| Freshness | `t_emit_ms` minus the end of the cited transcript span: p50, p95 | The latency budget, measured |
| Correction latency | Same, for ops with `reason = teacher_correction` | |
| Op rejection rate | Rejected ops divided by proposed ops, by rule | Tool-use reliability of the model in this task |
| No-op rate | Ticks with zero ops | Too low means over-writing; too high means missed content |
| Compression | Notes tokens divided by transcript tokens | Concision; target band 8-15% [U] |
| Cost | Dollars per lecture hour from logged usage | Replaces the estimates in section 5.3 with measurements |

### 8.3 Judge-based metrics

- **Coverage (recall).** For each lecture, a strong model extracts a list of key points ("nuggets") from the full transcript and slides; a human corrects it for a gold subset of ~5 lectures. The judge marks each nugget as present, partial or missing in the notes.
- **Correctness (precision).** Split the notes into atomic claims; the judge checks each against the transcript and slides and labels it supported, unsupported or contradicted. Report the unsupported and contradicted rates separately.
- **Correction handling.** Splice scripted corrections into transcripts ("sorry, that exponent is minus three, not minus two") and assert that the final notes contain the corrected value and not the original, and that an `update_block` (not a new block) made the change.
- **Concision and keyword density.** Rubric score for redundancy, plus the share of glossary terms that appear.
- **Structure.** Rubric score for the outline; separately, agreement between section boundaries and slide-change timestamps.
- **Slide grounding.** Precision and recall of annotations against a small hand-labelled set; slide-tracker accuracy against ground-truth timings.
- **Diagrams.** Validity is guaranteed by the schema; the judge rates whether each diagram matches what was said.

Judge practice:

- Use a stronger model than the generator (Opus 5.5, or a different vendor to reduce shared bias).
- Prefer pairwise comparison between two pipeline versions, with order swapped, over absolute scores.
- Anchor every rubric level with an example.
- Calibrate on ~50 human-labelled items and track judge-human agreement; re-check when the judge model changes.
- Judge mid-lecture snapshots (15, 30, 45 minutes) as well as the final document, because the product is experienced live.
- Batch the judging through the Batch API.

### 8.4 Regression suite

| Tier | Contents | When it runs | Cost |
|---|---|---|---|
| 1. Deterministic | Op reducer, validator and permission rules; replay determinism (same ops -> same document); resume and de-duplication logic | Every commit | None |
| 2. Micro-scenarios | 30-50 clips of 2-5 minutes, each with assertions: self-correction, digression, student question, backward slide jump, joke with no content, formula-dense passage, enumerated list, garbled STT, long silence, rapid slide flipping | Every prompt, model or trigger change | Roughly a cent per scenario on Haiku [U] |
| 3. Full lectures | 5 full lectures, op-log metrics plus judge metrics, compared pairwise with the previous release | Nightly or before release | A few dollars [U] |
| 4. Production telemetry | The section 8.2 metrics on real sessions, plus student signals: edits to agent blocks, deletions, locks | Continuous | None |

Tier 2 is the gate. A change that improves coverage but raises churn or flicker should fail it.

---

## 9. Open risks

| # | Risk | Why it matters | Mitigation / first experiment |
|---|---|---|---|
| 1 | **Fast-lane latency with reasoning models** | Current small models think by default; the only published figures show 8+ s to first answer token with thinking on. The thinking-off figure is unmeasured. | Measure Haiku 5.5 with thinking off vs low effort on the real prompt in week one. Fallbacks: Sonnet 5.5 with `between_tools`, or GPT-6 Luna / Gemini Flash-Lite. |
| 2 | **Revision quality and churn on a small model** | Revising the right block when the teacher corrects themselves is the product's distinguishing feature and the hardest behaviour. Haiku 5.5 with thinking off is documented to sometimes skip a needed tool call. | Server-enforced edit permissions; correction-cue trigger; tier-2 scenarios; configuration 3 as the escape hatch. |
| 3 | **Capture reliability** | iOS web capture stops on screen lock; lecture-hall wifi is poor; distant microphones degrade STT, and wrong transcripts produce wrong notes. | Local chunk recording, resumable upload, catch-up ticks, glossary boosting, native wrapper in phase 2. |
| 4 | **Slide grounding** | Figure regions from PDF geometry and transcript-only slide tracking are both error-prone; a circle on the wrong figure is worse than none. | Model never emits coordinates; manual flip is authoritative; drop unresolved targets; measure before enabling auto-follow by default. |
| 5 | **Unverified and moving prices** | OpenAI prices are from secondary sources. Gemini 3.8 Flash doubles on 2027-01-01 and Gemini 4 Argon doubles on 2026-12-01. Haiku 5.5 is five times dearer above 100K-token prompts. | Keep the model interface thin; log real usage; re-run section 5.3 with measured tokens. |
| 6 | **Refusals without fallback on Haiku 5.5** | A safety-classifier refusal returns HTTP 200 with `stop_reason: "refusal"`; on Haiku there is no server-side fallback. Lecture content in medicine, chemistry or security could trigger it. | Check `stop_reason` on every response; retry that tick on Sonnet 5.5. |
| 7 | **Token assumptions** | Every cost figure rests on 150 words/min, 180 ticks/h and a ~12K prompt. | The harness reports actual tokens per lecture hour. |
| 8 | **Consent and retention** | Recording lectures can require permission; audio and transcripts are personal data. | Not researched here; needs a decision before launch. |

---

## 10. Sources

Fetched directly today [V]:

- Anthropic pricing: https://platform.claude.com/docs/en/about-claude/pricing
- Google Cloud Vertex AI / Agent Platform generative AI pricing: https://cloud.google.com/vertex-ai/generative-ai/pricing
- tldraw agent template README: https://github.com/tldraw/tldraw/blob/main/templates/agent/README.md
- `claude-api` reference bundled with Claude Code (models, thinking and effort rules, prompt caching, tool use), cached 2026-11-03

Found through web search, not opened directly [S]:

Comparable systems
- Granola, "AI meeting transcription: how it works": https://www.granola.ai/blog/ai-meeting-transcription-how-it-works-and-which-tools-lead-in-2026
- "How does Granola AI work?": https://zackproser.com/blog/how-does-granola-ai-work
- ZenML case study on Granola's tracing tools: https://zenml.io/llmops-database/building-custom-tracing-tools-and-development-infrastructure-for-ai-powered-meeting-notes
- Sacra note on Granola: https://sacra.com/chat/h/bb316bee-0809-4c7d-a859-4095ed2142a1/
- Notion AI meeting notes review: https://tldv.io/blog/notion-ai-meeting-notes-review/ and https://fireflies.ai/blog/notion-ai-meeting-notes
- Google, "Take notes for me": https://blog.google/products-and-platforms/products/workspace/take-notes-for-me/ and https://workspaceupdates.googleblog.com/2026/08/take-notes-with-me-for-in-person-meetings-is-now-available.html
- Otter: https://otter.ai/blog/otter-surpasses-1-billion-meetings-transcribed-and-launches-otterpilot-tm-the-smart-ai-meeting-assistant-to-eliminate-note-taking-and-automate-meeting-summaries
- Cluely blog (first-party latency budget): https://cluely-blog-demo.pages.dev/blog/how-realtime-ai-works
- Mastra, "Building low-latency agents that help humans respond on live calls": https://mastra.ai/blog/building-low-latency-agents
- tldraw agent starter kit docs: https://tldraw.dev/starter-kits/agent

Incremental summarization and edit formats
- Incremental summarization via progressive note-taking: https://arxiv.org/pdf/2510.06677
- Dynamic agenda-aware real-time meeting summarization: https://link.springer.com/article/10.1007/s44443-025-00304-y
- LLM-powered meeting recap system (design and evaluation): https://arxiv.org/html/2307.15793v3
- "To Diff or Not to Diff?" (edit output formats): https://arxiv.org/pdf/2604.27296
- Edit format selection overview: https://agentpatterns.ai/tool-engineering/llm-edit-format-selection/
- Block-identity issue and fix in a document agent: https://github.com/arfct/vapor/issues/59 and https://github.com/arfct/vapor/pull/114
- Tiptap AI Toolkit tools and changelog: https://tiptap.dev/docs/content-ai/capabilities/ai-toolkit/tools and https://tiptap.dev/docs/resources/changelog/pro-ai-toolkit

Models, prices, latency
- OpenAI price cut announcement (GPT-5.6): https://community.openai.com/t/announcing-a-major-price-drop-for-5-6-terra-and-luna-and-fast-mode-for-5-6-sol/1388484
- OpenAI pricing trackers (GPT-6 family): https://www.cloudzero.com/blog/openai-pricing/ , https://www.morphllm.com/openai-api-pricing , https://developer.puter.com/tutorials/openai-api-pricing/ , https://www.requesty.ai/blog/gpt-6-1-terra-pricing-api
- OpenAI official pricing page (not reachable from this sandbox): https://openai.com/api/pricing/
- OpenAI realtime pricing analyses: https://www.forasoft.com/blog/article/openai-realtime-api-pricing , https://callsphere.ai/blog/vw2c-openai-realtime-cost-per-minute-math-2026
- OpenAI realtime developer notes and transcription guide: https://developers.openai.com/blog/realtime-api , https://developers.openai.com/api/docs/guides/realtime-transcription
- Gemini Live session management: https://ai.google.dev/gemini-api/docs/live-session and https://firebase.google.com/docs/ai-logic/live-api/limits-and-specs
- Artificial Analysis, Claude Haiku 5.5: https://artificialanalysis.ai/models/claude-haiku-5-5-low and https://artificialanalysis.ai/models/claude-haiku-5-5-medium/providers
- Artificial Analysis, Gemini 3.8 Flash: https://artificialanalysis.ai/models/gemini-3-8-flash
- Anthropic latency guidance: https://platform.claude.com/docs/en/test-and-evaluate/strengthen-guardrails/reduce-latency
- Haiku 5.5 overviews: https://www.deeplearning.ai/the-batch/claude-fills-out-its-model-family , https://www.eesel.ai/blog/claude-haiku-5-5-review

Slides
- MaViLS benchmark: https://arxiv.org/pdf/2409.16765
- "Attend to what I say: highlighting relevant content on slides": https://arxiv.org/abs/2601.10244v1
- PDF parser comparisons: https://themenonlab.blog/blog/best-open-source-pdf-to-markdown-tools-2026 , https://needl.ai/technical-notes/benchmarking-pdf-extraction-tools , https://www.file2markdown.ai/blog/pymupdf4llm-vs-docling

Stack and platforms
- Cloudflare Durable Objects pricing: https://developers.cloudflare.com/durable-objects/platform/pricing
- LiveKit pricing and billing: https://livekit.com/pricing and https://docs.livekit.io/deploy/admin/billing.md
- Convex vs Supabase comparisons: https://www.bytebase.com/blog/convex-vs-supabase/ and https://convex.dev/compare/supabase/
- WebKit bug 226620 (capture in home-screen web apps): https://bugs.webkit.org/show_bug.cgi?id=226620
- Apple developer forum threads on background microphone capture: https://developer.apple.com/forums/thread/689182 and https://developer.apple.com/forums/thread/762582
- iOS PWA limitations guide: https://www.magicbell.com/blog/pwa-ios-limitations-safari-support-complete-guide

Evaluation
- M3AV dataset: https://aclanthology.org/2024.acl-long.489/
- VT-SSum: https://arxiv.org/abs/2106.05606

Not researched or left unverified because of the access limits and search budget: Fly.io / Render / Railway / R2 list prices, Convex and Supabase function time limits, OpenAI prompt-caching specifics for the GPT-6 family, current iOS Wake Lock behaviour, Android background capture, per-vendor STT keyterm limits, and any head-to-head tool-calling benchmark for the small models.
