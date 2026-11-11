# 01 — Streaming speech-to-text for Live Notes

Research date: 2026-11-11. Author: speech/audio research lead.

## How to read this report (evidence quality)

Direct fetching of vendor sites (soniox.com, deepgram.com, assemblyai.com, elevenlabs.io, speechmatics.com, gladia.io, huggingface.co) was blocked by this research session's network policy. Everything below therefore comes from web-search summaries of those pages plus third-party trackers. Nothing was tested on audio. Each claim carries one of these tags:

- **[V]** — stated on the vendor's own site or docs (as returned by search). A vendor claim, not an independent measurement.
- **[3P]** — third-party source (benchmark, tracker, blog).
- **[U]** — unverified: sources conflict, the source is weak, or I could not find it. Do not build on these without checking.
- **[J]** — my engineering judgement, not a sourced fact.

All prices are list / pay-as-you-go prices as seen in November 2026 unless a different date is given. This market moves monthly (three of the candidate models below were released in the last ten weeks), so re-check prices before committing.

---

## 1. Recommendation

**Primary: Soniox real-time (`stt-rt-v6`, or `stt-rt-v5` if v6 proves unstable), EU-region project, browser connects directly over WebSocket with a temporary API key minted by our backend.** After the lecture, re-transcribe the locally recorded audio file with a batch model and swap the transcript in.

**Fallback / runner-up: AssemblyAI Universal-3.6 Pro Realtime** on the EU streaming endpoint.

**Do not use for the live path:** OpenAI `gpt-live-transcribe`, Google Gemini 3.5 Transcribe Live, Mistral Voxtral Realtime. None returns word-level timestamps in streaming mode, which we need to sync notes to audio.

**On-device / in-browser STT: not for v1's live path.** Use KB-Whisper (Swedish) as a benchmark baseline and as a candidate for the post-lecture batch pass.

Why Soniox first:

| Requirement | Soniox | Evidence |
|---|---|---|
| Word timestamps while streaming | Every token carries `start_ms` / `end_ms`, `is_final`, `confidence`; on by default | [V] |
| Swedish + English + switching mid-sentence | Swedish is a supported language; one model does language ID and mid-sentence switching; `language_hints` biases toward expected languages | [V] |
| Slide vocabulary | `context` object with `general` key-values and a `terms` list, up to 8,000 tokens (~10,000 characters) | [V] |
| 2-hour sessions | 300-minute hard cap per WebSocket session | [V] |
| Browser-direct | Temporary API key (1–3600 s validity, needed only to open the socket, optional single-use and max session duration); Web SDK with `client.realtime.record()` | [V] |
| EU / GDPR | EU region with in-region storage and processing, no US fallback; streaming audio processed in memory and not retained; not used for training; self-serve DPA; SOC 2 Type 2, ISO 27001 | [V] |
| Price | ~$0.12 per audio hour real-time, ~$0.10 async, with diarization, language ID, timestamps and context included | [V] |

It is 2–8x cheaper than every alternative that meets the requirements, and it is the only one where nothing we need is a paid add-on.

Why it is not a certain choice: the Swedish accuracy evidence is entirely vendor-published, v6 was released on 2026-11-03 (eight days before this report), the EU region is "enabled by request" rather than self-serve, and Soniox is a small vendor. So the recommendation is conditional on a one-week bake-off on real Swedish and English lecture-hall recordings (section 9), and the client must sit behind a provider abstraction so we can switch.

---

## 2. Comparison table — hosted streaming STT

Prices are per audio hour, streaming, pay-as-you-go. "WS direct" means the browser can open the WebSocket to the vendor itself using a short-lived credential minted by our server, so no audio proxy is needed.

| Provider / model | Streaming price per hour | Latency (as reported) | Swedish + English, code-switching | Word timestamps (streaming) | Vocabulary boosting | Diarization (streaming) | Session limit | Browser connection | EU / retention |
|---|---|---|---|---|---|---|---|---|---|
| **Soniox** `stt-rt-v6` (released 2026-11-03) | **$0.12** [V]; context tokens extra (~$0.03 per session at max size) [J] | 266 ms median time to final segment on Pipecat benchmark [V]; vendor claims sub-200 ms [V] | Swedish supported; mid-sentence switching in one model; language hints [V] | Yes, per token, always on [V] | Context: 8,000 tokens of terms + general info [V] | Included [V] | 300 min hard cap [V] | WS direct, temporary key, Web SDK [V] | EU region by request; no retention for streaming; DPA self-serve [V] |
| **AssemblyAI** Universal-3.6 Pro Realtime (released ~2026-09-29 [3P]) | **$0.45**, billed on session duration [V] | "Sub-300 ms" [V] | 32 languages incl. Swedish with native code-switching [V] | Yes [V] | 100 keyterms, 50 chars each, included, updatable mid-stream [V] | +$0.12/hr [V] | 3 hours [V] | WS direct, temporary token [V] | EU endpoint `streaming.eu.assemblyai.com` [V]; retention terms [U] |
| **Deepgram** Nova-3 | **$0.46** monolingual, **$0.55** multilingual [V, snapshot possibly stale]; keyterms +$0.08/hr; diarization +$0.12/hr [V] | Targets sub-300 ms [V]; 247 ms on Pipecat benchmark [3P] | Dedicated Swedish streaming model (improved 2026-08-27) [V]. New 55-language `language=multi` model with `language_hint` since 2026-10-23 [V]; Swedish in that set and Swedish code-switching [U] | Yes, per word with confidence [V] | Keyterm prompting, up to 500 tokens, updatable mid-stream [V] | Paid add-on [V] | Not found [U] | WS direct, JWT from `/v1/auth/grant` (30 s default TTL) [3P] | `api.eu.deepgram.com`, no cross-region fallback [V]; full in-region guarantee also needs `mip_opt_out=true` [3P] |
| **ElevenLabs** Scribe v3 Live (supersedes Scribe v2 Realtime) | **$0.22** [3P]; another tracker shows $0.39 for v2 Realtime on 2026-10-18 [U]; keyterms +$0.05–0.08/hr [3P] | ~150 ms median [V] | 90+ languages; `multilang_mode` tracks switches mid-sentence [V]; Swedish not named explicitly for v3 [U] | Yes, opt-in, delivered with committed transcripts [V] | 50 keyterms per session, or a "keyterm library" of 10,000+ terms [V, sizes conflict] | Yes (`diarize=true`) [V] | Not found [U] | WS direct, single-use token (15 min expiry) [V]. Official SDKs do not yet support multilingual mode, keyterm library or turn prediction; raw WebSocket needed [V] | US by default; EU residency and zero-retention are Enterprise-only [3P] |
| **Speechmatics** Realtime Enhanced | **$0.43** (cut 2026-07-06) [3P]; one tracker says $0.80 [U]. Standard $0.24 [3P] | ~0.32 s [3P, mid-2026] | Swedish supported [U — language list not retrieved; long-standing in my knowledge]. Code-switching needs the Melia 1 model, whose real-time availability is contradictory across sources ($0.40/hr if available) [U] | Yes [U — not retrieved; long-standing feature] | `additional_vocab`, ~1,000 words, start-up delay up to 15 s with large lists [V/3P] | Yes [U] | "No session time limit" [V] | WS direct, temporary JWT (`wss://eu.rt.speechmatics.com/v2?jwt=`) [V] | EU, US, AU regions; UK company; on-prem available [V] |
| **Gladia** Solaria-1 real-time | **€0.68** (pricing page dated 2026-11-03) [V] | Partials <103 ms, finals ~270 ms [V] | Code-switching across 100+ languages [V]; Swedish quality [U] | Not confirmed [U] | Custom vocabulary [3P] | [U] | 3 hours [3P] | Backend calls `POST /v2/live`, gets a session-specific WS URL, client connects directly [V] | French company, EU region default; zero retention Enterprise-only (pages conflict) [V/U] |
| **OpenAI** `gpt-live-transcribe` | **$1.02** ($0.017/min) [V] | Tunable [V] | Multiple language hints [V] | **No** — no word timestamps, speaker labels or confidence [V] | Keywords + free-form context [V] | No [V] | [U] | Ephemeral client secret, WebRTC or WS [V] | [U] |
| **Google** Gemini 3.5 Transcribe Live | ~$0.54 ($0.009/min) [3P, U] | — | — | **No** — utterance-level only [V] | — | — | **10 minutes** [V] | — | — |
| **Google** Cloud STT v2 Chirp 3 | **$0.96** ($0.016/min) [3P] | — | 85+ languages; Swedish locale [U] | Supported in batch; streaming support disputed [U] | Model adaptation [V] | Disputed [U] | ~5 min per stream, reconnect logic needed [3P, U] | Needs Google auth; proxy realistically required [J] | Regional endpoints exist [U] |
| **Azure** Speech real-time | **$1.00**, +$0.30 for continuous language ID, +$0.30 diarization (Oct 2026 US list) [3P] | — | Swedish supported [U] | Yes [U — long-standing] | Phrase lists [U] | Paid add-on [3P] | — | Token-based SDK auth [U] | Sweden Central region availability for Speech [U] |
| **Mistral** Voxtral Mini Transcribe Realtime 3 (Oct 2026) | **$0.48** ($0.008/min) [3P] | Final <500 ms [3P] | 35–40+ languages; Swedish [U] | **No** in realtime [3P] | — | — | — | — | French company [J] |
| **Berget AI** Klang Pianissimo (Swedish Parakeet fine-tune, hosted in Sweden) | **€0.21** (€3.50 per 1,000 min) [V] | — | Swedish-focused; English and code-switching [U] | [U] | [U] | [U] | [U] | OpenAI-protocol WebSocket [V]; browser token model [U] | Processed in Sweden [V] |

Also seen but not evaluated: Deepgram Flux (turn-detection model for voice agents, not suited to continuous lecture speech [J]); Speechmatics Linden 1 ($0.15–0.30/hr, voice-agent model, one language per stream [V/3P]); Meta "Muse Voice Transcribe" reported top of Artificial Analysis streaming leaderboard at 3.1% WER [3P, U]; Smallest.ai Pulse; Cartesia.

### Independent accuracy and latency benchmarks (English, voice-agent audio — not lectures, not Swedish)

- Coval leaderboard, 28 Sep – 28 Oct 2026: AssemblyAI Universal-3.6 Pro 2.2% WER, Speechmatics Linden 1 3.9%, ElevenLabs Scribe v2 Realtime 4.3%, Soniox RT v5 4.8%, Deepgram Nova-3 5.2% [3P].
- Pipecat/Daily open benchmark (semantic WER): Soniox v6 0.74%, AssemblyAI U-3.6 Pro 0.89%, Speechmatics Linden 1 1.05%, Deepgram Nova-3 1.62% [V pages quoting 3P benchmark].
- Artificial Analysis AA-WER Streaming (June 2026): Scribe v2 Realtime 3.65%, Soniox v5 ~4.5%, Speechmatics Realtime Enhanced 8.05% [3P, now stale].

Reading: the top five are within a few points of each other on clean English, and the order changes with each release. These numbers do not predict Swedish far-field lecture performance.

### Swedish evidence

- Soniox comparison pages: Swedish WER 8.2% for Soniox vs 11.2% Speechmatics, 13.1% ElevenLabs, 13.6% Deepgram, 28.4% AssemblyAI ("2025 study, 60 languages, YouTube audio") [V — vendor-published, predates current models of every vendor]. A different Soniox page shows 1.25% / 1.4% / 1.71% / 3.16% for the same four; the two tables are not comparable.
- ElevenLabs Swedish page: Scribe v1 3.1–3.4% on FLEURS, 5.5% on Common Voice; Whisper large-v3 9.6% on FLEURS in the same table [V].
- KB-Whisper-large (National Library of Sweden): 5.4 FLEURS / 4.1 Common Voice / 5.2 NST, against 7.8 / 9.5 / 11.3 for OpenAI whisper-large-v3 — a 47% average reduction [V model card via 3P].
- NVIDIA Parakeet-TDT-0.6B-v3: 15.08% Swedish on FLEURS [V model card via 3P].
- **I found no independent 2026 benchmark of commercial streaming APIs on Swedish, and none on Swedish lectures or Swedish/English code-switching.** This is the largest evidence gap.

### Far-field evidence

No source compares commercial APIs on lecture-hall audio. The Far-Field ASR leaderboard (Hugging Face + Treble, launched 2026-06-24) reports mean WER of 4.4% near-field rising to 41.3% in its static low-SNR far-field condition, across all submitted models [3P]. Microphone distance will move our accuracy more than vendor choice will [J]. AssemblyAI sells a "Voice Focus" add-on (+$0.10/hr) [V]; its effect on lecture audio is unknown [U].

---

## 3. Notes on the serious candidates

### Soniox (primary)

- Pricing is token-based: real-time $2.00 per 1M input audio tokens and $4.00 per 1M input/output text tokens; 1 hour of audio ≈ 30,000 audio tokens and ≈ 15,000 output text tokens, which gives $0.06 + $0.06 = $0.12/hr. Async is $1.50 and $3.50, giving ~$0.10/hr [V].
- A comparison page lists v6 at $0.18/hr real-time; that row appears to be the translation comparison [U]. The pricing page and speech-to-text page both say $0.12 [V].
- The same model serves real-time and async "with the same accuracy and features" [V]. So a Soniox async re-pass mainly fixes gaps and applies the full vocabulary, not raw accuracy.
- Keepalive needed every 20 s when no audio is flowing; billed for full stream duration [V].
- Audio input: raw PCM (must state sample rate and channels) or auto-detected containers (aac, aiff, amr, asf, flac, mp3, ogg, wav, webm) [V].
- Rate limits: 100 requests/minute, 10 concurrent real-time requests by default [V] — must be raised before a classroom-scale pilot.
- To verify in the prototype: whether tokens are sub-word pieces that we must merge into words [U]; whether context can be changed mid-session [U]; whether context tokens are billed once per session [U]; how fast buffered audio can be replayed after a reconnect [U]; where the company and its sub-processors are located for the DPA [U].

### AssemblyAI Universal-3.6 Pro Realtime (fallback)

- Strongest independent English result (Coval) and self-serve EU endpoint. Swedish is one of 32 streaming languages with native code-switching, at a flat $0.45/hr regardless of language [V].
- Keyterms can be replaced mid-session with an `UpdateConfiguration` message [V]. This fits our product well: we can push the current slide's terms as the lecturer advances.
- Billing is by WebSocket open time, not speech [V].
- Temporary tokens are not single-use within their validity window; `max_session_duration_seconds` caps a session [V].
- Swedish quality is unproven: the only Swedish number is the 28.4% WER on a competitor's page for an older model [V-competitor]. AssemblyAI says benchmark figures for 3.6 were not yet published [V].

### Deepgram Nova-3

- Most mature streaming infrastructure and a dedicated Swedish streaming model. The cost with keyterms is ~$0.54/hr monolingual or ~$0.63/hr multilingual.
- The catch is language mode. Monolingual `sv` will handle English terms inside Swedish speech only as well as keyterms allow, and a fully English lecture needs `en`. The new 55-language multilingual model (2026-10-23) may solve this, but a Deepgram SDK pull request reported `language_hint` returning HTTP 400 in production on launch day, and I could not confirm Swedish is in the 55 [3P, U].

### ElevenLabs Scribe v3 Live

- Attractive on paper: low price, mid-sentence multilingual mode, very large keyterm library, live diarization.
- Concerns for our use: word timestamps arrive only with committed transcripts, and for continuous speech the docs recommend committing every 20–30 s (auto-commit at ~36 s was documented for v2) [V]. For a lecturer who rarely pauses, final word timings could lag well behind partial text [J]. EU residency and zero retention need an Enterprise contract [3P]. SDKs lag the API [V].
- Scribe v3 batch ($0.20/hr, up to 1,000 keyterms, word timestamps) is a strong candidate for the post-lecture pass [3P/V].

### Speechmatics

- Long track record, EU region, no session limit, on-prem option. Without Melia in real-time, a session is one language (or a fixed bilingual pack; no Swedish–English pack was found) [3P, U]. Worth including in the bake-off because of its reputation on noisy audio [J].

---

## 4. On-device and local options

Verdict: none is suitable as the v1 live engine for students' own laptops and phones in a browser. Reasons are below.

| Option | Streaming? | Swedish | Word timestamps | Feasibility for a 2-hour lecture |
|---|---|---|---|---|
| **whisper.cpp / faster-whisper** with large-v3-turbo or KB-Whisper | Not natively. Whisper works on 30 s windows; streaming wrappers (WhisperLiveKit, SimulStreaming) re-encode a sliding window on each update [3P] | KB-Whisper is distributed in GGML, ONNX and CTranslate2 formats [V] | Yes (cross-attention / alignment) [J] | Needs a native app, not a browser tab. Reported speed ranges from ~2x real-time on M2 CPU-only (different runtime) to 17x on an M5 Air with Metal [3P, inconsistent]. No measured battery data found. Windows laptops with integrated graphics and 8 GB RAM are the risk [J]. |
| **WhisperKit** (Argmax, Apple only) | Yes (`AudioStreamTranscriber`), with word timestamps and VAD [V/3P] | Community CoreML conversions of KB-Whisper exist [3P] | Yes | Native iOS/macOS app only. Battery reports range from "<4% per hour" to "25–35% per hour" with no methodology [3P, U]. |
| **NVIDIA Parakeet-TDT-0.6B-v3** | No — not cache-aware; sherpa-onnx and parakeet.cpp do offline only [3P] | Yes (25 European languages), but 15.08% FLEURS WER, far behind KB-Whisper [V] | Yes [U] | Good fast offline pass; not a live engine. |
| **NVIDIA Canary-1B-v2** | Chunked only, with large accuracy loss (12.45 vs 7.15 average WER in one paper) [3P] | 25 languages; Swedish number not found [U] | Via NeMo Forced Aligner [3P] | Server-side batch only [J]. |
| **NVIDIA Nemotron 3.5 ASR Streaming 0.6B** | Yes — true cache-aware streaming, 80 ms–1.12 s chunks [3P] | sv-SE among 40 locales [3P] | Not confirmed [U] | Most interesting open model for a self-hosted live path later; open weights (OpenMDW-1.1) [3P]; Swedish quality unknown [U]. |
| **Moonshine v2 streaming** | Yes | English plus 7 other languages; Swedish not confirmed [U] | [U] | English-only fallback at best. |
| **transformers.js + WebGPU in the browser** | No real streaming; the real-time demo re-transcribes a 30 s window [3P] | Whisper multilingual only; large-v3-turbo is a 1.6–2.9 GB download and may exceed browser memory [3P] | Yes for Whisper [J] | Not viable for 2 hours live across student hardware; WebGPU is not universal and falls back to slow WASM [3P]. |
| **Apple SpeechAnalyzer** (iOS/macOS 26) | Yes, long-form, on-device [3P] | Swedish support not confirmed [U] | [U] | Only relevant if we build a native Apple app. |

Where local models do help:

1. **KB-Whisper-large as the Swedish reference.** Run it server-side in the bake-off, and consider it for the batch pass on Swedish lectures. Hosted in Sweden by Berget AI at roughly €0.12/hr (€1.98 per 1,000 min) [3P, U].
2. **A later native app** could use WhisperKit or Nemotron streaming for an offline mode.
3. KB-Whisper is tuned for Swedish; its behaviour on English lectures and code-switching is not documented [U].

---

## 5. Browser audio capture

Recommendation: capture once, feed two consumers.

```
getUserMedia (mono)
   ├─ AudioWorklet → resample to 16 kHz → Int16 PCM frames (20–100 ms) → STT WebSocket
   │                                    └→ ring buffer (last N minutes) for reconnect replay
   └─ MediaRecorder (Opus) → 5–10 s chunks → OPFS/IndexedDB → resumable upload to our storage
```

**PCM via AudioWorklet for the STT stream, not MediaRecorder chunks.** [J, supported by 3P reports]

- Raw PCM has no container state. After a reconnect we can resume from any sample. A WebM stream needs its header again and vendors' decoders can stall on unsplit clusters [3P].
- The worklet's sample counter is our master clock. Every transcript timestamp, note and slide event is stored as an offset on that clock.
- `AudioContext` sample rate varies by browser; read the actual rate and resample [3P].
- Cost: 16 kHz 16-bit mono is 256 kbit/s, about 115 MB per hour upstream. Fine on campus wifi; on mobile data consider sending Opus instead (Soniox auto-detects webm/ogg [V]).

**getUserMedia constraints:** request mono, `echoCancellation: false`. Test `noiseSuppression` and `autoGainControl` both ways in the bake-off; browser noise suppression can damage far-field speech for ASR, while gain control may help a quiet distant voice [J].

**Mobile web caveat:** iOS Safari stops microphone capture when the screen locks or the web app is backgrounded (WebKit bugs 241400, 236509 and others, still open or unclear) [3P]. Whether the Screen Wake Lock API is enough is unverified [U]. Treat laptop browsers as the v1 target; phones need a native app or a "keep the screen on" mode [J].

### Stored format for synced playback

- **Opus, mono, 24–32 kbit/s.** 32 kbit/s is 14.4 MB per hour, so a 2-hour lecture is ~29 MB [J — arithmetic; the bitrate range is standard practice for speech, not sourced here].
- Chrome and Firefox record `audio/webm;codecs=opus`. Safari defaults to `audio/mp4` (AAC) and can record WebM/Opus from 18.4 (March 2025) if asked [3P]. Always check `MediaRecorder.isTypeSupported` and store the real MIME type.
- MediaRecorder WebM files lack a duration and seek index, so they do not seek properly [3P]. Remux on the server after upload (`ffmpeg -c copy`), or transcode to a single seekable Opus-in-WebM/Ogg or AAC/M4A file for playback on all browsers [J].
- Keep the full-quality upload as the source for the batch transcription pass.

---

## 6. Flaky lecture-hall wifi

Design rule: **the local recording is the source of truth; the live transcript is best-effort.** [J]

1. **Local first.** Write Opus chunks and the timeline of events to OPFS/IndexedDB as they are produced. A closed lid, tab crash or two-hour outage must not lose audio.
2. **Resumable upload.** Upload chunks in the background with retry; the server assembles them.
3. **STT reconnect.** On socket loss: fetch a new temporary key, open a new session, replay PCM from the ring buffer starting at the last finalized token's end time, then continue live. Add the session's start offset to every timestamp so all sessions share the master clock. Re-send the context/keyterms on each new session.
4. **Outage longer than the ring buffer** (suggest 2–5 minutes): stop trying to catch up, mark the interval as a gap, and resume live. The UI shows "transcript will be filled in after the lecture".
5. **AI notes during a gap:** the note-taking model simply receives no text; the gap is repaired by the batch pass and the notes for that interval are generated afterwards.
6. **Temporary key expiry** only affects opening a socket for Soniox, AssemblyAI and Deepgram; an open session continues [V/3P]. Keep keys short-lived and single-use where offered.
7. **Session caps:** Soniox 300 min, AssemblyAI 180 min — both above our 120-minute maximum, but handle a forced close the same way as a network drop.

Unverified: how fast each vendor accepts replayed audio (faster than real time) [U].

---

## 7. Post-lecture batch re-transcription

**Yes, do it for every lecture.** It costs $0.10–0.25 per hour and solves three problems: wifi gaps, live errors that the full slide vocabulary would have fixed, and student-question segments where diarization is more reliable offline. [J]

Rules that make it safe:

- Anchor notes, diagrams and slide annotations to **audio time**, never to live transcript token IDs. Then the transcript can be replaced without breaking sync.
- Keep the live transcript as a fallback until the batch result passes sanity checks (duration matches, no long empty stretches).
- An LLM clean-up pass using the slides may fix spellings of terms, but must not change timestamps.

Batch candidates (all return word-level timestamps unless noted):

| Batch model | Price per hour | Notes |
|---|---|---|
| Soniox async | ~$0.10 [V] | Same model as live, so same format and code path; gains come from full context and gap filling |
| Speechmatics Melia 1 | $0.12–0.13 [V] | Code-switching across 55+ languages; batch was GA first |
| KB-Whisper-large (self-hosted, or Berget AI ~€0.12) | compute / [3P, U] | Best published Swedish numbers; English and code-switching behaviour unknown |
| ElevenLabs Scribe v3 | $0.20 [3P] | Up to 1,000 keyterms (+$0.05/hr) |
| AssemblyAI Universal-3.5 Pro | $0.21 + $0.05 keyterms [3P] | 18 languages incl. Swedish |
| Google Gemini 3.5 Transcribe | ~$0.30 [3P, U] | Max 30 min per request with word timestamps [V] — needs chunking |
| OpenAI `gpt-transcribe` | $0.27 [3P] | **No word timestamps** [3P] — unusable alone |
| Groq whisper-large-v3-turbo | $0.04 [V] | Timestamp granularity and EU residency not confirmed [U] |

Default: Soniox async for simplicity. The bake-off should test whether KB-Whisper or Scribe v3 gives a clearly better Swedish transcript; if so, use that for Swedish lectures.

---

## 8. Cost per lecture hour

Primary setup (list prices, November 2026):

| Item | Per audio hour |
|---|---|
| Soniox real-time | $0.12 |
| Slide vocabulary as context (up to 8,000 text tokens at $4/1M, assumed billed once per session [U]) | ≤ $0.03 per session |
| Reconnect replays (assume 5% extra audio) [J] | ~$0.01 |
| Soniox async batch pass | $0.10 |
| **Total** | **≈ $0.23–0.26** |

- 90-minute lecture: about **$0.35–0.40**. 2-hour lecture: about **$0.50**.
- A student recording 10 hours a week for a 15-week term: about **$35–40 per term**.
- Fallback setup (AssemblyAI live $0.45 + batch $0.21–0.26): about **$0.66–0.71 per hour**, roughly $100–107 per term for the same student.
- Audio storage at 32 kbit/s is ~14 MB per hour and negligible.

Not included: the LLM that writes the notes (expected to dominate total cost), egress, and our own backend.

---

## 9. Bake-off before committing (one week)

1. Record 8–10 real lectures with a laptop mic and a phone on the desk, at front, middle and back rows: Swedish and English, across maths, CS and medicine, including lecturers who mix languages. Get consent from the lecturers.
2. Hand-correct reference transcripts for 10-minute excerpts of each.
3. Run live: Soniox v6 and v5, AssemblyAI U-3.6 Pro, Deepgram Nova-3 (`sv`, `en`, and `multi` with hints), ElevenLabs Scribe v3 Live, Speechmatics Enhanced. Run batch: Soniox async, Scribe v3, Melia 1, KB-Whisper-large.
4. Measure: WER per language; recall of slide terms with and without vocabulary boosting; word-timestamp error against forced alignment; delay to final text; behaviour at language switches; hallucinated text during silence or applause; behaviour through a forced 30-second network drop.
5. Decide primary and fallback on those numbers, not on this report's vendor claims.

---

## 10. Open risks

1. **Far-field Swedish accuracy is unknown for every vendor.** No independent data exists; far-field conditions can multiply error rates several times over. Mitigation: bake-off, microphone-placement guidance in onboarding, input level meter, optional external mic.
2. **Vendor concentration and churn.** Soniox is small; v6 is days old; ElevenLabs replaced its realtime model within the year; OpenAI is removing `whisper-1` and the whole `gpt-4o-transcribe` family on 2027-02-26 (announced 2026-08-26) [3P]. Mitigation: provider-neutral transcript schema and client adapter; keep AssemblyAI integrated behind a flag.
3. **GDPR and recording consent.** We record a lecturer's and other students' voices. We need a lawful basis, a university-acceptable consent/notice flow, a DPA and EU processing with the STT vendor, and a retention policy. Soniox's EU region must be requested and confirmed before any pilot. This needs legal review; it is outside this report's scope.
4. **Mobile web recording is unreliable** on iOS when the screen locks. Phones probably need a native app.
5. **Timestamp continuity across reconnects and across the live→batch swap** is the hardest client engineering problem here; it must be designed and tested first.
6. **Vocabulary limits and behaviour:** how well 8,000 tokens of slide terms work in Swedish, and whether too many terms cause false insertions, is untested.
7. **Rate limits:** Soniox's default of 10 concurrent real-time sessions will block even a small pilot until raised.
8. **Price figures are unverified against live pages** for ElevenLabs, Speechmatics, Deepgram batch, Azure and Google; several sources conflict.

---

## 11. Sources

Soniox
- Pricing: https://soniox.com/pricing — comparison: https://soniox.com/compare/stt/pricing
- Temporary API keys: https://soniox.com/docs/guides/temporary-api-keys — https://soniox.com/docs/api-reference/auth/create_temporary_api_key
- Real-time limits: https://soniox.com/docs/stt/rt/limits-and-quotas — real-time transcription: https://soniox.com/docs/stt/rt/real-time-transcription
- Context: https://soniox.com/docs/stt/concepts/context — language hints: https://soniox.com/docs/stt/core-concepts/language-hints
- WebSocket API: https://soniox.com/docs/api-reference/stt/websocket-api — Web SDK: https://soniox.com/docs/sdk/web-SDK/stt/realtime-transcription
- Security and privacy: https://soniox.com/docs/security-and-privacy — EU: https://soniox.com/europe
- Swedish: https://soniox.com/speech-to-text/swedish — https://soniox.com/compare/soniox-vs-assemblyai/swedish
- Benchmarks: https://soniox.com/benchmarks — v6 coverage: https://www.marktechpost.com/2026/11/03/soniox-stt-v6-agent-text-input-echo-cancellation/
- Third-party v5/v6 test: https://github.com/TypeWhisper/typewhisper-benchmark/pull/17

AssemblyAI
- Streaming product page: https://www.assemblyai.com/products/streaming-speech-to-text
- Models: https://www.assemblyai.com/docs/getting-started/models
- Streaming WebSocket API (EU endpoint, 3-hour limit): https://www.assemblyai.com/docs/streaming/api-spec/streaming-websocket
- Temporary tokens: https://www.assemblyai.com/docs/api-reference/streaming/create-temporary-token
- Keyterms: https://www.assemblyai.com/docs/streaming/universal-3-pro/prompting
- Code-switching and pricing post: https://www.assemblyai.com/blog/real-time-transcription-code-switches-multilingual-speakers
- Pricing reference: https://www.assemblyai.com/pricing.md — tracker: https://www.usagepricing.com/blueprint/assemblyai

Deepgram
- Pricing: https://deepgram.com/pricing
- Models and languages: https://developers.deepgram.com/docs/models-languages-overview
- 55-language multilingual model: https://developers.deepgram.com/changelog/2026/10/23 — SDK PR noting launch issue: https://github.com/deepgram/deepgram-js-sdk/pull/583
- Swedish streaming update: https://developers.deepgram.com/changelog/2026/8/27 — Swedish launch: https://deepgram.com/learn/deepgram-expands-nova-3-with-german-dutch-swedish-and-danish-support
- Interim results and word timings: https://developers.deepgram.com/docs/interim-results — keep-alive: https://developers.deepgram.com/docs/audio-keep-alive
- EU endpoint: https://deepgram.com/blog/deepgram-eu-endpoint-now-generally-available — data: https://developers.deepgram.com/trust-security/your-data

ElevenLabs
- Scribe v3 / v3 Live: https://elevenlabs.io/blog/scribe-v3 — models: https://elevenlabs.io/docs/overview/models
- Realtime API: https://elevenlabs.io/docs/api-reference/speech-to-text/v-1-speech-to-text-realtime
- Client-side streaming and tokens: https://elevenlabs.io/docs/eleven-api/guides/how-to/speech-to-text/realtime/client-side-streaming
- Commit strategies: https://elevenlabs.io/docs/eleven-api/guides/how-to/speech-to-text/realtime/transcripts-and-commit-strategies
- Language options: https://elevenlabs.io/docs/eleven-api/guides/how-to/speech-to-text/realtime/language-options
- Pricing: https://elevenlabs.io/pricing/api — secondary: https://www.datastudios.org/post/elevenlabs-scribe-v3-live-speech-to-text-27-percent-fewer-errors-0-20-per-hour
- Swedish page: https://elevenlabs.io/speech-to-text/swedish

Speechmatics
- Pricing: https://www.speechmatics.com/pricing — tracker: https://www.usagepricing.com/blueprint/activity/speechmatics-2026-07-06-realtime-stt-price-cut
- Melia: https://www.speechmatics.com/company/articles-and-news/introducing-melia-multilingual-speech-to-text-model
- Models: https://docs.speechmatics.com/speech-to-text/models — realtime API: https://docs.speechmatics.com/api-ref/realtime-transcription-websocket — auth: https://docs.speechmatics.com/get-started/authentication

Gladia
- Pricing: https://www.gladia.io/pricing.md — live quickstart: https://docs.gladia.io/chapters/live-stt/quickstart — retention: https://docs.gladia.io/chapters/limits-and-specifications/data-retention

OpenAI, Google, Azure, Mistral
- gpt-live-transcribe: https://developers.openai.com/api/docs/models/gpt-live-transcribe — guide: https://developers.openai.com/api/docs/guides/realtime-transcription — pricing: https://developers.openai.com/api/docs/pricing
- Whisper / gpt-4o-transcribe shutdown: https://creuto.com/whisper-1-deprecation-gpt-transcribe-migration
- Gemini live transcription: https://ai.google.dev/gemini-api/docs/live-api/live-transcribe — model: https://ai.google.dev/gemini-api/docs/models/gemini-3.5-transcribe
- Chirp 3: https://docs.cloud.google.com/speech-to-text/docs/models/chirp-3
- Azure Speech pricing: https://azure.microsoft.com/en-us/pricing/details/speech/
- Voxtral: https://mistral.ai/news/voxtral-transcribe-2/ — Voxtral 3 summary: https://www.digitalapplied.com/blog/voxtral-3-transcription-tts-models-price-preview

Benchmarks
- Coval: https://www.coval.ai/blog/best-speech-to-text-providers-in-2026-independent-benchmarks-and-how-to-choose/
- Pipecat: https://www.pipecat.ai/benchmarks/speech-to-text
- Artificial Analysis streaming: https://artificialanalysis.ai/speech-to-text/streaming — launch article: https://artificialanalysis.ai/articles/new-streaming-speech-to-text-benchmark-aa-wer-streaming
- Far-field leaderboard coverage: https://getaibook.com/news/far-field-benchmark-shows-massive-gap-in-low-snr-speech-mode/

Swedish and local models
- KB-Whisper: https://huggingface.co/KBLab/kb-whisper-large — blog: https://kb-labb.github.io/posts/2025-03-07-welcome-KB-Whisper/
- Berget AI realtime Swedish: https://berget.ai/en/blog/realtime-transcription-launch
- Parakeet v3 / Canary v2 paper: https://arxiv.org/abs/2509.14128 — Parakeet streaming limitation: https://github.com/k2-fsa/sherpa-onnx/issues/2918
- Nemotron 3.5 ASR Streaming: https://deepinfra.com/nvidia/Nemotron-3.5-ASR-Streaming-Multilingual-0.6b — https://huggingface.co/cstr/nemotron-3.5-asr-streaming-GGUF
- WhisperLiveKit: https://github.com/QuentinFuxa/WhisperLiveKit — WhisperKit: https://github.com/argmaxinc/argmax-oss-swift
- On-device streaming overview: https://dev.to/voxrtio/on-device-streaming-asr-in-2026-five-approaches-and-when-to-pick-what-5h1n

Browser audio
- MediaRecorder and Safari WebM support: https://www.testmuai.com/learning-hub/mediarecorder-browser-support/
- WebM duration problem: https://blog.addpipe.com/duration-in-webm-videos-produced-by-chrome/
- iOS microphone on screen lock: https://bugs.webkit.org/show_bug.cgi?id=241400 — https://bugs.webkit.org/show_bug.cgi?id=236509
