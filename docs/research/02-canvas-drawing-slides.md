# 02 — Canvas, AI drawing, slide annotation and replay

Research date: 2026-11-11. Scope: the rendering/drawing layer of Live Notes (web first, React/TypeScript; tablets later).

## 0. How to read this report

### Verification legend

| Tag | Meaning |
| --- | --- |
| **[V]** | Verified this session against a primary source: the project's own repository files (LICENSE, docs source, source code) fetched from `raw.githubusercontent.com`, or the npm registry metadata. |
| **[S]** | Secondary: comes from a web-search result summary. The underlying page could not be opened from this sandbox, so wording and numbers may be off. |
| **[U]** | Unverified: from prior knowledge, not checked this session. Treat as a hypothesis to confirm in a spike. |

### Research limits (important)

- The sandbox network only allowed `raw.githubusercontent.com` and the npm registry. **`tldraw.dev` (including `/pricing`), vendor pricing pages, docs sites, arXiv and blogs could not be opened directly.** Everything about those is either [S] or [U].
- Consequence: **the tldraw commercial price is not verified.** The licence terms themselves are verified from the repository.
- Research was cut short by a usage limit; sections 4 (notes surface) and 5 (replay) lean more on [U] than sections 1–3.

---

## 1. Executive summary

**Recommended stack (one concrete choice):**

| Layer | Choice | Licence |
| --- | --- | --- |
| Ink/diagram renderer (note diagrams and slide overlay) | Our own thin **SVG renderer in React**, using **rough.js** for hand-drawn shapes and **perfect-freehand** for pen/highlighter strokes | MIT, MIT [V] |
| Shape model the LLM writes | Our own small **shape DSL delivered as tool calls**, with model-chosen stable IDs; modelled on Excalidraw's element/skeleton vocabulary so it converts to Excalidraw | — |
| Graph-like diagrams | Model emits nodes + edges without coordinates; we lay out with **dagre** (MIT) [V]; **elkjs** as an upgrade (EPL-2.0 OR GPL-3.0 — weak copyleft, check with counsel) [V] |
| Notes surface | **Block document, not an infinite canvas**: **TipTap 3 / ProseMirror** with stable block IDs (`@tiptap/extension-unique-id`) and a custom "diagram" block that hosts the SVG renderer | MIT [V] |
| Slides | Convert everything to **PDF** server-side (**Gotenberg**/LibreOffice for PPTX), rasterise pages with **PDFium**, extract words + boxes with **PDF.js**, display image + our SVG overlay in normalised slide coordinates | MIT, BSD-style [U], Apache-2.0 [V] |
| Slide grounding | **Pre-computed region map per slide; the model only picks region IDs or quotes text at runtime** (hybrid of options (c) and (a)); vision pointing is a pre-processing and fallback tool, never the live path |
| Replay | **Append-only timestamped op log + periodic snapshots**, audio clock as master, every animation a pure function of the playhead | — |
| Collaboration | None in v1 (server-authoritative single log, two actors: AI and student). Add **Yjs** (MIT) for text only if multi-user arrives | MIT [V] |

**Why not tldraw or Excalidraw as the foundation:** both are *editors*. Live Notes mostly needs a deterministic *player* — "draw scene state at time T, with strokes partially drawn" — on two surfaces (a note block and a slide overlay). Neither library offers time-seekable stroke animation; we would be fighting the editor to get it. tldraw additionally needs a paid licence key in production. Excalidraw stays valuable as (1) the vocabulary the model already knows and (2) an optional MIT "open this diagram in a full editor" escape hatch.

**The strongest evidence for this design** is the official Excalidraw MCP server, which made the same choice: it does *not* mount the Excalidraw editor; it parses partial streaming JSON and renders pure SVG with CSS draw-on animations [V].

---

## 2. What "Clicky" is and how it points

Clicky is an open-source (MIT) macOS menu-bar "AI teacher that lives as a buddy next to your cursor", by Farza. It sees the screen, talks, and flies a blue triangle cursor to the thing it is talking about. The open repo is frozen as of April 2026; newer work continues closed-source as "HeyClicky" for Mac and Windows [V — `farzaa/clicky` README, LICENSE, AGENTS.md].

How it works technically [V — `AGENTS.md`, `CompanionManager.swift`, `ElementLocationDetector.swift`]:

1. **Push-to-talk** → streaming speech-to-text (AssemblyAI) → transcript + **screenshots of every display** go to Claude (Sonnet 4.6 default) through a Cloudflare Worker proxy; reply is streamed and spoken with ElevenLabs.
2. **Pointing protocol is a text tag, not a tool call.** The system prompt tells the model to append, at the very end of its spoken answer, `[POINT:x,y:label]` (or `[POINT:x,y:label:screenN]`, or `[POINT:none]`). `x,y` are integer pixels in the *screenshot's* coordinate space, origin top-left; the screenshot images are labelled with their pixel dimensions. A regex strips the tag before text-to-speech.
3. **Coordinate mapping:** clamp to the screenshot size → scale screenshot pixels to display points → flip Y (AppKit is bottom-left origin) → add the monitor's global offset.
4. **Rendering:** one transparent, click-through, full-screen overlay window per display; the cursor flies along a **bezier arc** to the target and shows a short label bubble.
5. **A second, more accurate locator exists in the repo:** `ElementLocationDetector` calls Claude's *Computer Use* tool, after resizing the screenshot to one of three small resolutions (1024×768, 1280×800, 1366×768) chosen to match the display's aspect ratio. The author's code comment claims the computer-use tool "activates Claude's specialized pixel-counting training, which is significantly more accurate than regular vision API coordinate extraction", and that aspect-ratio distortion hurts X accuracy. This is the developer's claim, not a measured benchmark.

**Lessons for Live Notes:**

- Clicky points at *one* thing with a *cursor*, where a 20–40 px miss is harmless. Live Notes circles and highlights, where the same miss is visibly wrong. Clicky's raw-coordinate approach is therefore not enough for us on its own.
- Worth copying: the overlay is a separate transparent layer in its own coordinate space; the pointer animates along an arc with a label; the model is told the exact pixel dimensions of what it sees; a sentinel for "nothing to point at".
- A Clicky-style **pointer/laser** ("look here") is a cheap, forgiving first annotation type for slides, and a good fallback when confidence in a region is low.

---

## 3. Canvas foundation

### 3.1 Licensing facts

| Library | Latest (npm, date) | Licence | Cost for a commercial startup |
| --- | --- | --- | --- |
| **tldraw SDK** | 5.6.0 (2026-10-28) [V] | Proprietary "tldraw license" [V] | **Production use requires a licence key** [V]. Trial: free, 100 days, one per company, no watermark [V]. Commercial: annual, no watermark, price via sales [V]. Hobby: non-commercial only, watermark stays [V]. **Price: third-party sites report about $6,000/year (≈$500/month) with startup discounts on application; the official page reportedly shows no figure — [S], unverified.** |
| `@tldraw/sync`, `@tldraw/mermaid` | 5.6.0 [V] | Same tldraw licence [V] | Covered by the same key requirement |
| tldraw starter kits (agent, workflow, …) | — | MIT for the kit code [V — repo README] | The kits still depend on the SDK, so the key requirement applies |
| **Excalidraw** (`@excalidraw/excalidraw`) | 0.18.1 (2026-04-20); master actively changing through 2026-10-31 [V] | MIT [V] | Free |
| Konva / react-konva | 10.9.1 / 19.3.2 [V] | MIT [V] | Free |
| Fabric.js | 7.4.0 (2026-05-18) [V] | MIT [V] | Free |
| PixiJS | 8.22.0 (2026-10-01) [V] | MIT [V] | Free |
| rough.js | 4.6.6 (2023-11-20 — stable, rarely released) [V] | MIT [V] | Free |
| perfect-freehand | 1.2.3 (2026-02-01) [V] | MIT [V] | Free |
| rough-notation | 0.5.1 (2020-10-30 — dormant) [V] | MIT [V] | Free |
| Plain SVG | — | Web platform | Free |
| Newer/other: Leafer UI 2.3.4, Drawnix/Plait, xyflow 12 | [V] | MIT [V] | Free |
| Newer/other: BlockSuite (AFFiNE edgeless), Penpot | [V] | MPL-2.0 [V] | Free, file-level copyleft |

**tldraw licence detail [V — `LICENSE.md` and `apps/docs/content/sdk-features/license-key.mdx` on `main`]:**

- Default terms permit development only: you agree "Not to use the Software in Production Environments" and "Not to disable, change, or interfere with the Software's License Key enforcement".
- In production (HTTPS, non-localhost, `NODE_ENV=production`) without a valid key, the SDK logs errors and **stops rendering the editor after five seconds**.
- Keys are validated client-side, are domain-bound, and can be public. Annual licences have a 30-day grace period; trials have none.
- Trial/hobby/unlicensed builds ping tldraw with licence ID, SDK version and page URL; commercial keys send nothing by default.
- Stale text warning: the agent template's own README still says commercial use is allowed if the watermark is kept. That contradicts `LICENSE.md` and the docs and looks like leftover pre-4.0 wording. Follow `LICENSE.md`.

### 3.2 Capability comparison

| | Agent-facing API (create/update/delete by ID) | Stroke-drawing animation | Thousands of elements | Collaboration | Tablet |
| --- | --- | --- | --- | --- | --- |
| **tldraw** | Excellent. `editor.createShapes / updateShapes / deleteShapes`, record store with IDs [U]. Official **agent starter kit**: each action is a tool call, applied as it finishes streaming; model-friendly simplified shape formats; ID and coordinate sanitising [V]. | None built in for progressive drawing [U]. You would write custom shapes that take a `progress` prop. | Good; DOM/SVG with culling; 5.0 moved overlays to a single canvas [S]. | Best of the group: `@tldraw/sync` (same licence) [V]; record-level sync on Cloudflare Durable Objects [U]. | Good touch/pen support [U]. |
| **Excalidraw** | Good. `excalidrawAPI.updateScene({elements, captureUpdate})`; `convertToExcalidrawElements` "skeleton" API auto-sizes labels and binds arrows by ID [V]. Elements carry `id`, `version`, `versionNonce`, `isDeleted`, `seed` [V]. | None in the editor. The official MCP app and `excalidraw-animate` (MIT) both animate the **exported SVG**, not the editor [V]. | Canvas 2D; fine for typical boards, slows on very large scenes [U]. | Not in the npm package; you build it (the hosted app uses a relay + version reconciliation, not a CRDT) [U]. | Works; UI is desktop-first [U]. |
| **Konva / react-konva** | Good scene graph, nodes by id/name; you define the model. | You write it: `dash` + `dashOffset` tween, or progressive point arrays [U]. | Good with layer and cache tuning [U]. | None. | Touch events supported [U]. |
| **Fabric.js** | Good object model + JSON serialisation; built for user manipulation (handles, selection) [U]. | You write it. | Moderate [U]. | None. | OK [U]. |
| **PixiJS** | Low-level display list; you build everything. | You write it; no native hand-drawn look. | Best raw throughput (WebGL/WebGPU) [U]. | None. | Good [U]. |
| **Plain SVG + rough.js + perfect-freehand** | Whatever we define; a keyed React list of elements *is* the API. | **Trivial and seekable**: `pathLength="1"` + `stroke-dashoffset = 1 − progress`, driven from the playhead. | Fine to low thousands of nodes per surface; we never have more per slide or diagram. Mitigate by rasterising settled layers [U]. | None; we own the log (section 7). | Excellent; resolution-independent, native pointer events. |

### 3.3 Assessment

- **tldraw** is the best *editor* SDK and has the best agent tooling. It is the right pick if the product were "an AI that works on a whiteboard with you". It is the wrong pick for a player-first product: licence cost and vendor dependency for the core surface, no seekable draw animation, and its page/camera model does not match "many small diagrams inside a document + overlays on slides".
- **Excalidraw** is free and its hand-drawn look is exactly the target aesthetic. But mounting one editor instance per diagram block and per slide is heavy, and replay would mean re-driving `updateScene` with no partial-stroke state.
- **Konva/Fabric/Pixi** solve throughput and interactive manipulation — problems we do not have at this scale — and give nothing for the hand-drawn look.
- **SVG + rough.js + perfect-freehand** is the smallest thing that satisfies every hard requirement: hand-made look, animation as a function of time, identical code for live and replay, identical code for note diagrams and slide overlays, crisp on tablets.

Cost of the recommendation: we own roughly a dozen shape renderers, hit-testing if students edit AI drawings, and text measurement. That is weeks, not months, and it is the product's core.

---

## 4. How LLMs draw well today

### 4.1 What the two reference implementations do

**tldraw agent starter kit** [V — `templates/agent/README.md`, `apps/docs/content/starter-kits/agent.mdx`]:

- Every action is a **tool call**; the browser applies each action when it has *finished* streaming, then returns results plus a fresh canvas view. Loop ends when the model replies without tool calls; max 20 follow-ups per turn.
- The model sees **both** a screenshot and structured shape data, in three levels of detail: `FocusedShape` (full props; also the output format), `BlurryShape` (bounds, id, type, text), `PeripheralShapeCluster` (off-screen groups).
- **Sanitising is a first-class step**: `ensureShapeIdExists`, `ensureShapeIdIsUnique`, type coercion — because "an incoming action might contain invalid data" from hallucination or because the canvas changed.
- **Coordinates are made model-friendly**: offset relative to the chat's start position, rounded before sending and restored afterwards; shape IDs are converted to short "simple IDs".
- Schema trick: a leading `_type` field so the discriminator streams first.
- Works with Anthropic, OpenAI and Google models.

**Official Excalidraw MCP app** (`excalidraw/excalidraw-mcp`, MIT, hosted at `mcp.excalidraw.com`) [V — README, `CLAUDE.md`, `package.json`]:

- Two tools: `read_me` (a cheat sheet: element format, palettes, coordinate tips, examples) and `create_view` (a JSON string of **standard Excalidraw elements**).
- The widget **parses partial JSON while it streams** and renders with `exportToSvg` + **morphdom** DOM diffing — "No Excalidraw React canvas component — pure SVG rendering". Animations (stroke draw-on, fade-in) are plain CSS.
- They **tried and rejected** the skeleton API (`convertToExcalidrawElements`) because it needs font metrics at conversion time and is a non-standard format. Trade-off they accept: the model must compute label positions by hand (`x = shape.x + (shape.width − text.width)/2`).
- A **checkpoint system** lets the model reference prior state by ID instead of resending all elements; deleting a container also deletes bound text.
- After the final render a 512 px PNG screenshot is fed back so the model can iterate.
- Camera hints (`cameraUpdate` elements, nudged to 4:3) steer the viewport.

### 4.2 Output format comparison

| Format | Reliability | Looks | Latency / tokens | Incremental edits by stable ID | Hand-drawn progressive animation |
| --- | --- | --- | --- | --- | --- |
| **Mermaid / D2 / Graphviz** | High for graphs: no coordinates to get wrong; a layout engine guarantees no overlaps. Syntax errors do occur [S — MermaidSeqBench reports "significant capability gaps" between models; no error-rate numbers found]. | Tidy but generic; limited to supported diagram types. | Very compact. | Poor: an edit re-runs layout and everything can move; no per-node persistence unless IDs are mapped. | Indirect: convert to shapes first (`@excalidraw/mermaid-to-excalidraw` 3.6.0, MIT; `@tldraw/mermaid`, tldraw licence) [V]. |
| **Raw SVG from the model** | Medium. Valid markup is easy; good composition is not ("syntactically valid … semantically incorrect") [S — Math-Vision Diagrams 2026]. | Can be the most expressive (illustrations, curves). | Verbose; slow to stream. | Weak unless you force `id` attributes and patch by ID. | Possible with `stroke-dashoffset`, but fills and text need special handling. |
| **Excalidraw element JSON** | Good; models know the format. Label centring and arrow endpoints are manual in the standard format [V]. | The target aesthetic. | Verbose (many required fields) unless you accept a reduced subset. | Good: every element has an `id`. | Proven: the MCP app does it [V]. |
| **Tool-call shape DSL (ours)** | Best: schema-validated (`strict` tools), small vocabulary, sanitised before apply. | Whatever our renderer does — hand-drawn by construction. | Compact; each op is usable as soon as it closes in the stream. | Native: `add` / `update` / `remove` keyed by model-chosen IDs. | Native: the renderer owns stroke geometry and timing. |

### 4.3 Recommendation

Use a **tool-call shape DSL with three tiers**, cheapest first:

1. **Annotation marks** (highlight, underline, circle, box, bracket, arrow, margin note, pointer) — anchored to a region or text, **no coordinates at all**. This covers almost everything drawn on slides.
2. **Graph diagrams** — `nodes` + `edges` + direction, **no coordinates**; we run dagre/ELK and emit shapes with derived stable IDs (`g1.n.mito`). Edits re-run layout but animate nodes to their new positions.
3. **Freeform shapes** — rect/ellipse/diamond/line/arrow/text/sketch-path on a small local grid (0–1000 wide) inside one diagram block. Text auto-fits its container; arrows bind to shape IDs, not coordinates. Used only when tiers 1–2 cannot express the idea.

Rules that fall out of the evidence above:

- **IDs are chosen by the model and are short and semantic** (`cell`, `cell.nucleus`). The server rejects or renames duplicates and reports the outcome in the tool result.
- **Never make the model compute what code can compute**: label centring, arrow endpoints, text wrapping, stroke timing, z-order.
- **Stream tool inputs** and apply each op when its JSON object closes. On the Claude API this is `eager_input_streaming: true` on the tool, with our own validation because eager streaming skips server-side validation [U — per Anthropic's bundled `claude-api` skill reference, cached 2026-11-03].
- **Do not rely on forced tool choice.** The same reference says `tool_choice: any/tool` returns HTTP 400 on the newest Claude models; use `auto` + `strict: true` + prompt steering [U — same source].
- **Give the model a compact scene digest**, not the full log: IDs, type, text, bounding box for the diagram being edited (tldraw's "blurry/focused" split).
- **Validate geometry in code** before applying: overlaps, text overflow, off-canvas; auto-fix or bounce the op back with a reason.

### 4.4 Getting the "being drawn by hand" effect from structured shapes

| Element | Technique |
| --- | --- |
| Outline shapes (rect, ellipse, diamond, line, arrow) | rough.js generator with a **fixed `seed` per element** so the wobble is identical on every render [U]. Emit each sub-path with `pathLength="1"`, `stroke-dasharray="1"`, `stroke-dashoffset = 1 − progress`. Arrowheads appear in the last 15%. |
| Hachure / fill | Draw after the outline; reveal hachure lines sequentially with the same dash trick, or wipe with a `clipPath`. |
| Pen and highlighter strokes | perfect-freehand returns a filled **outline polygon**, so dash-offset does not apply. Animate by feeding it a growing **prefix of the input points** (simulate pressure tapering). Highlighter = wide, flat stroke with `mix-blend-mode: multiply`. |
| Annotation marks on slides | Same primitives; rough-notation (MIT, dormant since 2020) is the visual reference for underline/box/circle/highlight/bracket. Do not use the library itself: its animation is CSS-timed, so it cannot be scrubbed. |
| Handwritten text | v1: handwriting web font + **left-to-right reveal** per line (clip-path) with a moving pen cursor; cheap and legible. Later: true stroke-by-stroke writing needs a **single-stroke font** (Hershey-style) or per-glyph mask paths [S — CSS-Tricks/Codrops/SVGator write-ups]. |
| Timing | Duration = path length ÷ pen speed, clamped (e.g. 150–1200 ms); elements in one op batch are staggered. Timing is **derived by the renderer**, never emitted by the model. |
| Revisions | An `update` animates as strike-or-fade-out of the old geometry and draw-in of the new; a `remove` as a quick scribble-erase or fade. |

**The one non-negotiable rule:** animation progress is computed from the playhead (`progress = clamp((T − t_start) / dur, 0, 1)`), not from CSS/WAAPI timers. That single decision is what makes replay seeking and pausing free. (`excalidraw-animate` [V] and the MCP app [V] both use timer-driven animation, which is why neither is directly reusable for a scrubbable replay.)

---

## 5. Slide rendering and grounding

### 5.1 Getting slides into a renderable form

| Input | Path | Notes |
| --- | --- | --- |
| PDF | Use as is. | The canonical internal format. |
| PPTX | **Gotenberg** (MIT [V]) wrapping **LibreOffice headless** → PDF. | Free and self-hosted [S]. Known risk class: missing fonts → substitution and reflow, SmartArt/charts/effects differences [U]. Bundle common fonts; show the converted result for confirmation; keep a commercial converter as fallback (Aspose.Slides, ConvertAPI, CloudConvert — prices not verified). |
| Google Slides | Drive API export to PDF [U]. | Needs OAuth scope; size limits apply [U]. |
| Keynote | Ask for a PDF export, or use a cloud conversion API [U]. | LibreOffice's Keynote import is limited [U]. |

Animated builds and embedded video are lost in all paths. Out of scope for v1.

### 5.2 Rendering and text extraction

| Option | Licence | Verdict |
| --- | --- | --- |
| **PDF.js** (`pdfjs-dist` 6.5.438) | Apache-2.0 [V] | Use for **text extraction with coordinates** (`getTextContent()` returns text runs with a transform matrix; PDF origin is bottom-left, so flip Y; items are *runs*, not words — split on whitespace and apportion width) [S]. Also the client-side renderer if we want vector-sharp zoom. |
| react-pdf 11 | MIT [V] | Thin React wrapper over PDF.js; fine for a viewer, unnecessary if we show pre-rendered images. |
| **PDFium** (server) | BSD-style/Apache [U]; `@hyzyla/pdfium` wrapper is MIT [V] | Use for **server-side rasterisation**: fast, Chrome-grade fidelity [U]. Also has a text API with character boxes [U]. |
| MuPDF / `mupdf` npm 1.28.6 | **AGPL-3.0-or-later** or commercial from Artifex (quote only) [V/S] | Technically excellent, but AGPL in a SaaS product means open-sourcing or paying. **Avoid unless licensed.** |
| EmbedPDF | Mixed licences in one repo (Apache-2.0 for parts) [V] | Read the licence notice before adopting. |

**Recommended pipeline:** on upload, the server (1) converts to PDF, (2) rasterises each page to WebP at 2× display size, (3) extracts words with boxes, (4) builds the region map (5.4), (5) stores everything keyed by `slide index`. The client shows the image with an absolutely positioned SVG overlay whose `viewBox` is the **normalised slide space (0–1000 × 0–1000·h/w)**. Images + overlay make live view, replay and tablets identical, and remove PDF.js from the hot path.

### 5.3 How should the model refer to a place on a slide?

| Option | Accuracy | Runtime cost | Failure mode |
| --- | --- | --- | --- |
| **(a) Text anchors** — extracted words/spans with boxes; model quotes text or names a span ID | Exact for born-digital text. Zero for text baked into images unless OCR is added. | None: no image needed at runtime; any fast text model can do it. | Quote not found / ambiguous (repeated phrase). Detectable in code → fall back. |
| **(b) Vision coordinates** — model returns pixels/boxes | Good and improving, not exact (below). Weakest on small targets and dense figures. | An image per call, a stronger model, higher latency. | **Silent**: a confident circle around the wrong thing. Not detectable in code. |
| **(c) Pre-labelled region map** (layout detection / Set-of-Mark) — model picks IDs | As good as the pre-processing; can be reviewed, cached and corrected offline. | None at runtime beyond a short text list of regions. | Region missing or too coarse. Detectable ("no such ID") → fall back. |

**What is known about current pointing accuracy:**

- **Claude:** from Opus 4.7 / Sonnet 5 onward, images up to 2576 px on the long edge are supported and "coordinates returned by the model map 1:1 to actual image pixels"; earlier models were limited to 1568 px and needed scale-factor maths [U — Anthropic migration notes in the bundled `claude-api` skill reference; not a public benchmark].
- **Gemini:** boxes are `[ymin, xmin, ymax, xmax]` and points `[y, x]`, integers normalised to 0–1000; reordering the fields reportedly degrades results [S].
- **PointArena / Point-Bench (2025):** the pointing-specialised open model Molmo-72B scored highest, with Gemini 2.5 Pro comparable; models trained with explicit pointing supervision consistently beat those without; chain-of-thought prompting *reduced* pointing accuracy [S — arXiv 2505.09990 abstract-level summary; per-model percentages not retrieved].
- **ScreenSpot-Pro (GUI grounding, small targets on high-res screens):** aggregator sites list frontier models around 70–90% in 2026 (e.g. Claude Opus 4.8 ≈ 88%, GPT-5.4 ≈ 85%, Gemini 3.1 Pro ≈ 84%, Gemini 3 Pro ≈ 73%) versus ~1–2% for 2024-era generalist models [S — **aggregators disagree with each other; treat as indicative only**].
- **Set-of-Mark** (Microsoft, 2023; code MIT [V]): overlaying numbered marks on regions and asking for a number markedly improves grounding; one 2026 paper reports SoM adding 57 points for a model that was near zero with raw coordinates [S].
- None of these benchmarks is about **lecture slides**. Slide figures (anatomy diagrams, plots, circuit schematics) are closer to "dense figure parts" than to UI buttons. **There is no published number we can rely on for our case — we must measure it ourselves.**

Reading of the evidence: even ~85–90% point accuracy means roughly one wrong annotation in eight on hard targets. For a product whose value is "the AI circles the right thing", silent errors at that rate are unacceptable in the live path, and the latency of an image-in call per annotation is too.

### 5.4 Recommendation: region map + text anchors, vision only offline and as fallback

**Pre-processing (once per deck, before or at the start of the lecture, not latency-critical):**

1. **Text regions from the PDF text layer** (exact): words → lines → blocks (title, bullets, captions), each with an ID and box. `s7.t3` = slide 7, text block 3; words addressable as `s7.t3.w5` or by quote.
2. **Figure regions from PDF structure**: image XObjects and clusters of vector drawing operations give exact figure boxes without any model [U — needs a spike].
3. **Layout detector for image-only slides** (scans, screenshots, slides exported as pictures) plus OCR. Candidates and licences [V]: **PP-DocLayout / PaddleX** (Apache-2.0), **Docling** (MIT; model weights have their own terms — check), **Surya** (repo now Apache-2.0; check model weights), **MinerU** (Apache-2.0 with additional terms — read them). **Avoid DocLayout-YOLO: AGPL-3.0** [V].
4. **Vision-model pass for sub-figure parts**: send each figure crop at high resolution to a strong vision model and ask for named parts with boxes ("left ventricle", "x-axis", "the red curve", "step 3 arrow"). Verify by drawing the proposed boxes as numbered marks (Set-of-Mark) on the crop and asking the model to confirm or correct. Store as `s7.f1.p4` with a short description.
5. Output per slide: a compact text table — `id | kind | text or description | box` — that fits in the prompt and is cacheable for the whole lecture.

**Runtime (latency-critical):** the model receives the current slide's region table as text and emits anchors only:

- `{ "region": "s7.t3" }` — a whole block
- `{ "quote": "oxidative phosphorylation", "in": "s7" }` — a phrase; code resolves it to word boxes, fuzzy-matching and disambiguating by proximity to the last anchor
- `{ "region": "s7.f1.p4" }` — a named part of a figure
- `{ "region": "s7.f1", "sub": [x0, y0, x1, y1] }` — a sub-box in 0–1000 *of that region* (small search space, small error)
- `{ "margin": "right", "near": "s7.t3" }` — free space next to something; code finds the empty area

**Fallback when no region fits:** an asynchronous "locate" call to a vision model on the figure crop (optionally with a zoom-and-refine second step). Until it returns, show a soft pointer or a margin note, not a precise mark. Add the new region to the map so it is reused.

Why this is the right trade:

- Text — the majority of what lecturers refer to — is grounded **exactly and for free**.
- Every failure is **detectable in code** (unknown ID, quote not found), so we can degrade gracefully instead of drawing something wrong.
- The live model can be a **small, fast, text-only** call; the expensive vision work is done once and cached.
- The region table doubles as the model's "memory" of the slide and as the replay index ("jump to when this figure was discussed").

---

## 6. Notes surface

### 6.1 Options

| Option | For | Against |
| --- | --- | --- |
| **Rich-text block editor with embedded diagram blocks** | Notes are mostly text; structure (headings, bullets, definitions) is what makes them useful afterwards. Stable block IDs map directly to "AI patches block X". The student can type normally. Reflows on tablets. Exportable to Markdown/PDF. | Diagrams live in boxes; no free spatial arrangement. |
| **Infinite canvas** | Feels like a whiteboard; free placement; one renderer for everything. | The model must do 2-D layout of *text* (overlaps, overflow) — the hardest thing to get reliably right. Poor reading/reviewing/search/export. Student typing is awkward. Revising an early note means moving everything below it. |
| **Hybrid: document flow + ink layer** | Document for structure; a transparent ink layer over the page for arrows between blocks, margin doodles, emphasis marks anchored to block IDs. | Ink must re-anchor when text reflows (solved by anchoring to block/quote, same mechanism as slides). |

**Recommendation: the hybrid, built document-first.** v1 = block document + diagram blocks. v1.5 = the ink layer over the document, reusing the slide-overlay renderer and the same anchor types (`{block: "b12"}`, `{quote: …, in: "b12"}`). This gives the hand-made feel without making the model responsible for page layout.

### 6.2 Editor choice

| Editor | Licence | Notes |
| --- | --- | --- |
| **TipTap 3** (`@tiptap/core` 3.33.1) | MIT [V]; `extension-unique-id` and `extension-collaboration` also MIT [V] | Mature, headless, ProseMirror underneath (transactions/steps available). React node views host the diagram block. Paid platform (cloud, AI Toolkit — custom pricing; Start plan reportedly $49/month) is optional and not needed [S]. |
| **BlockNote** (`@blocknote/core` 0.57.0) | Core MPL-2.0 — usable in closed-source products; changes to BlockNote's own files must be published [V] | Block IDs and a block-level API out of the box; fastest route to a Notion-like editor. **Trap:** `@blocknote/xl-*` packages (AI, exports, etc.) are **GPL-3.0 or paid commercial** (Business subscription, reportedly $390/month [S]) [V]. Pre-1.0. |
| **Lexical** 0.53.0 | MIT [V] | Solid, lower-level; smaller ecosystem for our needs; pre-1.0. |

**Pick TipTap 3**: MIT throughout for what we use, stable, and it does not push us towards a paid AI add-on. BlockNote core is an acceptable faster start as long as nobody installs an `xl-*` package.

### 6.3 How the AI, the student and replay share the document

- **Canonical state is our own block tree** (`id, type, text/marks, attrs, children`), produced by folding the op log (section 7). The editor is a *view* bound to it. Replay mode does not need the editor at all — it renders the block tree read-only.
- **AI ops are block-level**: `add_block`, `update_block`, `remove_block`, `move_block`. Small in-place changes may use `{find, replace}` inside one block.
- **Student edits are logged as block-level ops too** (debounced: one `update_block` per pause in typing), with `actor: "user"`. Keystroke-level fidelity is not needed for replay and would bloat the log.
- **Ownership rule:** once a student has edited a block, the AI may not rewrite it; it may only append a new block or attach a suggestion. Without this rule the AI and the student will fight.
- **Revision calm:** cap how often the AI may revise already-visible content, and animate revisions gently. Notes that keep rewriting themselves while being read are a product risk, not just a technical one.
- **"Being written" animation for text:** streamed characters with a handwriting font and a pen cursor. Because progress is derived from the op timestamp and text length, it replays identically.

---

## 7. Replay: one append-only, timestamped operation log

### 7.1 Model

```
Event = {
  seq:    number        // strictly increasing, assigned by the server
  t:      number        // ms on the AUDIO timeline when the op became visible live
  tRef?:  number        // ms on the audio timeline of the speech it refers to (transcript segment)
  actor:  "ai" | "user" | "system"
  surface:"notes" | `diagram:${blockId}` | `slide:${index}` | "session"
  op:     NoteOp | DrawOp | SessionOp     // see section 8
}
```

- **State is a pure fold**: `state(T) = reduce(apply, events where t ≤ T)`. Deletes are tombstones; updates carry only changed props.
- **Session ops** record what the viewer saw: `slide_change`, `scroll_to`, `focus_block`.
- **Snapshots are keyframes**: every N seconds or M events, store the full folded state. `seek(T)` = nearest snapshot at or before T + apply the events up to T. This is the same shape as **rrweb**: a full snapshot followed by incremental events, periodic re-snapshots (`checkoutEveryNms` / `checkoutEveryNth`), and seeking by applying everything before the target synchronously, then playing on [S].
- **Animation is not stored.** Each visible element has `t_start` (its event's time) and a duration derived from geometry. At playhead `T` the renderer computes progress. Seeking into the middle of a stroke shows a half-drawn stroke with no extra machinery.
- **Audio is the master clock**: a `requestAnimationFrame` loop reads `audio.currentTime` and renders `state(T)`. Never run a separate timer. Playback speed and pause then work for free.
- **`tRef` makes replay better than live.** Live, an annotation appears a second or more after the words that caused it. In replay we can schedule it at `tRef` (minus a small lead), so the circle lands exactly as the lecturer says the word.
- **Storage:** NDJSON chunks (e.g. per minute) + a snapshot index. A one-hour lecture is on the order of thousands of events — megabytes at most.
- **Live transport = the same events** over WebSocket/SSE. The live client and the replay client share one reducer and one renderer; "live" is just "replay at the head of the log".

### 7.2 How the editor libraries relate to this

| System | What it gives | Limit for our purpose |
| --- | --- | --- |
| rrweb 2.2.2 (MIT) [V] | Proven snapshot + incremental + seek design; could record the real DOM. | Records DOM mutations, not semantic ops: large, brittle against UI changes, CSS-timed animations do not scrub. Use the *pattern*, not the tool. |
| tldraw | Record store emitting per-change diffs (added/updated/removed); snapshots; sync [U]. | A diff log is replayable, but partial-stroke state and audio sync are still ours to build; licence applies. |
| Excalidraw | Element versions + tombstones; `onChange`; scene JSON [V]. | No time-travel player; third-party animators are timer-based [V]. |
| ProseMirror/TipTap | Transactions/steps are an op log for text [U]. | Too fine-grained and editor-version-coupled for long-term replay; log block-level ops instead. |
| CRDTs — Yjs 13.6 (MIT), Loro 1.17 (MIT), Automerge 3.5 (MIT) [V] | Merge concurrent edits; Loro and Automerge advertise history/time-travel [U]. | Solve multi-writer merging, which v1 does not have. A CRDT history is not a wall-clock timeline. Adopt later for collaborative text, alongside (not instead of) the event log. |

---

## 8. Sketch of the drawing-operation schema given to the model

Design goals: tiny vocabulary; model-chosen stable IDs; anchors instead of coordinates wherever possible; every op independently applicable as soon as it finishes streaming; nothing about timing or styling details the renderer can decide.

```ts
// ---------- shared ----------
type Id = string;                       // short, semantic, model-chosen: "krebs", "krebs.n.atp"
type Ink = "pen" | "accent" | "warn" | "muted";          // palette tokens, not hex colours
type Ref = string;                      // transcript segment id this op is about ("seg_412") -> server maps to tRef

// ---------- anchors: how to say WHERE without coordinates ----------
type Anchor =
  | { region: Id }                                        // "s7.t3" | "s7.f1.p4" | "b12" (a note block)
  | { quote: string; in: Id; nth?: number }               // phrase inside a slide/region/block
  | { region: Id; sub: [number, number, number, number] } // 0..1000 box INSIDE that region
  | { margin: "left" | "right" | "top" | "bottom"; near: Id };

// ---------- tool 1: notes ----------
type NoteOp =
  | { op: "add_block"; id: Id; after: Id | "start" | "end";
      kind: "h1" | "h2" | "bullet" | "para" | "definition" | "formula" | "callout" | "diagram";
      text?: string; indent?: 0 | 1 | 2; ref?: Ref }
  | { op: "update_block"; id: Id; text?: string; find?: string; replace?: string; ref?: Ref }
  | { op: "remove_block"; id: Id }
  | { op: "move_block"; id: Id; after: Id };

// ---------- tool 2: annotate (slides, and later the note page) ----------
type MarkOp =
  | { op: "mark"; id: Id; at: Anchor;
      kind: "highlight" | "underline" | "circle" | "box" | "bracket" | "strike" | "pointer";
      ink?: Ink; ref?: Ref }
  | { op: "arrow"; id: Id; from: Anchor; to: Anchor; label?: string; ink?: Ink; ref?: Ref }
  | { op: "note";  id: Id; at: Anchor; text: string; ink?: Ink; ref?: Ref }   // margin/handwritten note
  | { op: "update"; id: Id; at?: Anchor; text?: string; kind?: string; ink?: Ink }
  | { op: "remove"; id: Id };

// ---------- tool 3: diagram (inside one diagram block) ----------
// 3a. graph tier: no coordinates, we lay it out
type GraphNode = { id: Id; text: string; shape?: "box" | "round" | "diamond" | "plain" };
type GraphEdge = { from: Id; to: Id; text?: string; dashed?: boolean };
type GraphOp =
  | { op: "graph"; id: Id; dir: "LR" | "TB"; nodes: GraphNode[]; edges: GraphEdge[] }
  | { op: "graph_add"; graph: Id; nodes?: GraphNode[]; edges?: GraphEdge[] }
  | { op: "graph_update"; graph: Id; node: Id; text?: string; shape?: string; emphasis?: boolean }
  | { op: "graph_remove"; graph: Id; node?: Id; edge?: [Id, Id] };

// 3b. freeform tier: local grid, x and w in 0..1000, y grows downward
type ShapeOp =
  | { op: "add"; id: Id; shape: "rect" | "ellipse" | "diamond"; box: [x: number, y: number, w: number, h: number];
      text?: string; fill?: "none" | "hatch" | "solid"; ink?: Ink }
  | { op: "add"; id: Id; shape: "text"; at: [number, number]; text: string; size?: "s" | "m" | "l"; ink?: Ink }
  | { op: "add"; id: Id; shape: "arrow" | "line"; from: Id | [number, number]; to: Id | [number, number];
      text?: string; curve?: boolean; ink?: Ink }                  // binding to shape ids preferred
  | { op: "add"; id: Id; shape: "sketch"; box: [number, number, number, number];
      path: string; ink?: Ink }                                    // SVG path `d` in a 0..100 local box, strokes only
  | { op: "update"; id: Id; box?: [number, number, number, number]; text?: string; ink?: Ink; fill?: string }
  | { op: "remove"; id: Id };

// ---------- tool call envelopes ----------
// notes({ ops: NoteOp[] })
// annotate({ slide: number, ops: MarkOp[] })            // or { page: "notes" } later
// diagram({ block: Id, ops: (GraphOp | ShapeOp)[] })
```

Server-side contract around these tools:

- **Stamp `seq`, `t`, `tRef`, `actor`** — the model never emits time.
- **Sanitise before applying** (the tldraw kit's lesson): unknown ID → reject with a message listing near matches; duplicate ID → rename and report; out-of-range numbers → clamp; quote not found → fuzzy match, else reject; text overflow → auto-shrink or grow the container.
- **Tool results are terse and corrective**: `ok` or `rejected: s7.f1.p9 not found; figure parts are p1..p6`.
- **Protect student-owned content**: ops targeting user-edited blocks are rejected with a reason.
- **Context given to the model each turn**: recent transcript, the current slide's region table, a digest of the note outline (IDs + first words), and — only when editing a diagram — that diagram's shape digest. Stable parts first so prompt caching works.

---

## 9. Open risks

| # | Risk | Why it matters | Mitigation / next step |
| --- | --- | --- | --- |
| 1 | **Wrong marks on figures** | Text is exact; sub-figure parts depend on an offline vision pass with no slide-specific benchmark. A wrong circle destroys trust. | Build a 100–200-slide evaluation set across subjects before committing; measure region recall and part-box accuracy; ship text-only annotations + soft pointer first; add figure-part marks behind a confidence threshold. |
| 2 | **Live latency and pacing** | Ops arrive after the speech they refer to; drawing animations add more delay; bursts look frantic. | Small fast text model on the live path; no images at runtime; animation budget per op; queue with coalescing; `tRef` re-timing in replay. Needs an end-to-end latency prototype. |
| 3 | **Freeform drawing quality** | Models still produce overlaps, overflow and awkward composition when given raw coordinates. | Prefer anchors and auto-layout tiers; geometry validator; optional render-and-critique pass for non-urgent diagrams; keep the freeform tier small. |
| 4 | **PPTX/Keynote conversion fidelity** | Font substitution moves text → region boxes still match the *converted* PDF, but slides may look wrong to the student. | Font bundle; preview step; commercial converter fallback; accept PDF as the recommended upload. |
| 5 | **Owning the renderer** | Hit-testing, selection, text measurement, undo for student edits of AI drawings are real work. | Scope v1 to view + delete/hide for AI drawings and pen-only student ink; keep the DSL convertible to Excalidraw (MIT) for "edit in full editor". |
| 6 | **Handwritten-text animation** | True stroke-writing needs single-stroke fonts and costs performance; fake reveals can look cheap. | Start with font + reveal + pen cursor; test legibility with students; evaluate single-stroke fonts later. |
| 7 | **Revision churn and AI-vs-student conflicts** | Notes that rewrite themselves are distracting; overwriting student edits is unforgivable. | Ownership rule, revision rate limit, visible but gentle change animations, per-block "pin". |
| 8 | **Licence traps** | MuPDF (AGPL), DocLayout-YOLO (AGPL), BlockNote `xl-*` (GPL/commercial), elkjs (EPL/GPL), tldraw (key required), GSAP (custom "no charge" licence [V] — read before use), model weights with separate terms. | Dependency licence check in CI; this report's tables as the starting allowlist. |
| 9 | **tldraw price unknown** | Only matters if the team overrides the recommendation and adopts tldraw. | Get a written quote, including startup terms, domain rules and what happens at expiry (the editor stops rendering). |
| 10 | **Tablet performance** | Large SVG overlays + blend modes on iPad Safari; pencil latency for student ink. | Rasterise settled layers; test on a mid-range iPad early; consider a canvas layer for live student ink only. |
| 11 | **SVG scale ceiling** | A very dense session on one surface could reach thousands of animated nodes. | Per-slide/per-block surfaces keep counts low; virtualise off-screen surfaces; canvas fallback for settled content. |

---

## 10. Suggested spikes (in order)

1. **Renderer spike (3–4 days):** SVG + rough.js + perfect-freehand; ten primitives; playhead-driven progress; scrub bar. Proves the look and the seek model.
2. **Slide grounding spike (1 week):** PDF → words/boxes + figure regions + vision part-labelling on 100 real slides; measure accuracy; produce the region-table format.
3. **Live loop spike (1 week):** transcript stream → fast model → streamed tool calls → sanitiser → event log → renderer; measure speech-to-ink latency.
4. **Notes spike (3–4 days):** TipTap with block IDs, AI block ops, student typing, ownership rule, diagram block hosting the renderer.
5. **Replay spike (2–3 days):** log + snapshots + audio-clock playback with `tRef` re-timing.

---

## 11. Sources

Primary sources opened this session ([V]):

- tldraw licence: https://raw.githubusercontent.com/tldraw/tldraw/main/LICENSE.md
- tldraw licence-key docs source: https://raw.githubusercontent.com/tldraw/tldraw/main/apps/docs/content/sdk-features/license-key.mdx
- tldraw licence overview docs source: https://raw.githubusercontent.com/tldraw/tldraw/main/apps/docs/content/community/license.mdx
- tldraw AI docs source: https://raw.githubusercontent.com/tldraw/tldraw/main/apps/docs/content/docs/ai.mdx
- tldraw agent starter kit: https://raw.githubusercontent.com/tldraw/tldraw/main/templates/agent/README.md and https://raw.githubusercontent.com/tldraw/tldraw/main/apps/docs/content/starter-kits/agent.mdx
- tldraw README (starter kits MIT; production needs a key): https://raw.githubusercontent.com/tldraw/tldraw/main/README.md
- Excalidraw licence: https://raw.githubusercontent.com/excalidraw/excalidraw/master/LICENSE
- Excalidraw API (`updateScene`, `captureUpdate`): https://raw.githubusercontent.com/excalidraw/excalidraw/master/dev-docs/docs/@excalidraw/excalidraw/api/props/excalidraw-api.mdx
- Excalidraw skeleton API: https://raw.githubusercontent.com/excalidraw/excalidraw/master/dev-docs/docs/@excalidraw/excalidraw/api/excalidraw-element-skeleton.mdx
- Excalidraw changelog (unreleased `exportScene` change, 2026-10): https://raw.githubusercontent.com/excalidraw/excalidraw/master/packages/excalidraw/CHANGELOG.md
- Excalidraw MCP app: https://raw.githubusercontent.com/excalidraw/excalidraw-mcp/main/README.md , https://raw.githubusercontent.com/excalidraw/excalidraw-mcp/main/CLAUDE.md , https://raw.githubusercontent.com/excalidraw/excalidraw-mcp/main/src/global.css
- excalidraw-animate: https://raw.githubusercontent.com/dai-shi/excalidraw-animate/main/README.md
- Clicky: https://raw.githubusercontent.com/farzaa/clicky/main/README.md , https://raw.githubusercontent.com/farzaa/clicky/main/AGENTS.md , https://raw.githubusercontent.com/farzaa/clicky/main/LICENSE , https://raw.githubusercontent.com/farzaa/clicky/main/leanring-buddy/CompanionManager.swift , https://raw.githubusercontent.com/farzaa/clicky/main/leanring-buddy/ElementLocationDetector.swift
- BlockNote licence: https://raw.githubusercontent.com/TypeCellOS/BlockNote/main/LICENSE.txt
- LICENSE files (same URL pattern, `raw.githubusercontent.com/<repo>/<branch>/LICENSE`) for: konvajs/konva, fabricjs/fabric.js, pixijs/pixijs, rough-stuff/rough, rough-stuff/rough-notation, steveruizok/perfect-freehand, mozilla/pdf.js, wojtekmaj/react-pdf, ArtifexSoftware/mupdf.js, embedpdf/embed-pdf-viewer, gotenberg/gotenberg, ueberdosis/tiptap, facebook/lexical, yjs/yjs, loro-dev/loro, rrweb-io/rrweb, mermaid-js/mermaid, terrastruct/d2, excalidraw/mermaid-to-excalidraw, kieler/elkjs, opendatalab/DocLayout-YOLO, datalab-to/surya, docling-project/docling, PaddlePaddle/PaddleX, opendatalab/MinerU, microsoft/SoM, microsoft/OmniParser, allenai/molmo, xyflow/xyflow, leaferjs/leafer-ui, plait-board/drawnix, toeverything/blocksuite, penpot/penpot
- npm registry metadata (version, publish date, licence), `https://registry.npmjs.org/<package>`: tldraw, @tldraw/sync, @tldraw/mermaid, @excalidraw/excalidraw, @excalidraw/mermaid-to-excalidraw, konva, react-konva, fabric, pixi.js, roughjs, perfect-freehand, rough-notation, excalidraw-animate, pdfjs-dist, react-pdf, mupdf, @hyzyla/pdfium, @embedpdf/core, @tiptap/core, @tiptap/extension-unique-id, @tiptap/extension-collaboration, @blocknote/core, @blocknote/xl-ai, lexical, yjs, loro-crdt, @automerge/automerge, rrweb, mermaid, @terrastruct/d2, elkjs, @dagrejs/dagre, gsap, motion

Secondary sources (search summaries only, pages not opened — [S]):

- tldraw pricing and licence pages: https://tldraw.dev/pricing , https://tldraw.dev/legal/tldraw-license , https://tldraw.dev/sdk-features/license-key , https://tldraw.dev/blog/tldraw-sdk-5-0
- tldraw $6,000/year reports: https://biggo.com/news/202509190115_tldraw_SDK_4.0_Licensing_Debate , https://appdevelopermagazine.com/tldraw-sdk-4.0-release-new-starter-kits-and-licensing-model/ , https://instapods.com/apps/excalidraw/vs/tldraw/
- Clicky write-up: https://isaac-flath.kit.com/posts/point-and-talk-how-clicky-s-ai-interface-works
- PointArena / Point-Bench: https://arxiv.org/abs/2505.09990
- ScreenSpot-Pro aggregators: https://benchlm.ai/benchmarks/screenspot-pro , https://llm-stats.com/benchmarks/screenspot-pro
- GUI grounding papers (Set-of-Mark gain, baselines): https://arxiv.org/pdf/2604.15376 , https://arxiv.org/html/2602.16855v1 , https://arxiv.org/pdf/2511.13087
- Set-of-Mark: https://arxiv.org/pdf/2310.11441v2.pdf
- Gemini box/point format: https://ai.google.dev/gemini-api/docs/robotics-spatial , https://simedw.com/2025/07/10/gemini-bounding-boxes/
- Diagram-generation benchmarks: https://arxiv.org/abs/2511.14967 (MermaidSeqBench), https://arxiv.org/pdf/2608.08964 (Math-Vision Diagrams)
- Layout detection: https://arxiv.org/pdf/2503.17213 (PP-DocLayout), https://arxiv.org/pdf/2410.12628 (DocLayout-YOLO)
- MuPDF licensing: https://mupdf.com/r/Licensing
- Gotenberg / LibreOffice conversion: https://blog.elest.io/gotenberg-free-open-source-pdf-document-conversion-api/
- Editors: https://tiptap.dev/pricing , https://tiptap.dev/product/ai-toolkit , https://www.blocknotejs.org/pricing , https://www.blocknotejs.org/legal/blocknote-xl-commercial-license
- rrweb guide (checkout / seeking): https://github.com/rrweb-io/rrweb/blob/main/guide.md
- Handwriting / draw-on animation technique: https://jakearchibald.com/2013/animated-line-drawing-svg/ , https://tympanus.net/codrops/2023/01/31/bringing-letters-to-life-coding-a-kinetic-svg-typography-animation/ , https://www.stefanjudis.com/blog/pathlength-makes-makes-svg-path-animations-easier-to-manage

Other: Claude model capabilities (image resolution limits, 1:1 pixel coordinates, eager tool-input streaming, forced tool choice removal) are taken from Anthropic's `claude-api` skill reference bundled with the research tool (cached 2026-11-03), not from a public page opened this session — treated as [U].

## 12. Not verified — confirm before relying on it

- tldraw commercial price and startup terms (only third-party reports of ~$6,000/year).
- All vendor prices: Tiptap plans, BlockNote Business, Artifex MuPDF, Aspose, ConvertAPI, CloudConvert.
- Per-model pointing accuracy numbers (ScreenSpot-Pro figures come from aggregators that disagree; PointArena percentages not retrieved). No benchmark exists for lecture slides.
- Performance ceilings for every canvas library (no benchmarks run or found).
- tldraw and Excalidraw internals stated from memory: tldraw store diff/history API and sync architecture; Excalidraw collaboration model; absence of built-in stroke animation in both editors.
- PDFium licence and text API; LibreOffice Keynote import quality; Google Drive export limits.
- rough.js `seed` determinism and PDF.js word-splitting approach (well known, not re-checked).
- Model-weight licences for Docling, Surya and MinerU (only the repository licences were checked).
