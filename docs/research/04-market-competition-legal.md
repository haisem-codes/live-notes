# 04 — Market, competition, legal and go-to-market research

Date: 2026-11-11. Scope: "Live Notes" (working title) — AI that follows a live lecture and writes self-revising notes, diagrams and highlights onto the lecturer's slides, with synced audio + slides + notes replay.

## 0. How to read this report

**Verification limits — read first.**

- This session could run web searches but could **not open vendor websites directly** (the sandbox network policy blocked everything except github.com). So "check real pricing pages" was only possible indirectly: prices below come from search-engine extracts of vendor pages, App Store listings and price-tracking aggregators, mostly dated June–November 2026. Treat every price as **"search-verified, not page-verified"** and re-check before quoting it externally.
- Tags used: **[V]** = confirmed by a primary source I could read or by several consistent sources; **[S]** = single or secondary source; **[U]** = unverified (my inference, memory, or a vendor's own marketing claim).
- Nothing here is legal advice. The legal section tells you what to ask a lawyer and what to build defensively.
- "Nobody ships X" claims are based on roughly 45 searches. That is absence of evidence, not proof. App Store listings were not inspected directly.

## 1. Bottom line

1. **The gap is real but narrow, and it is a feature gap, not a market gap.** Every component exists somewhere: live incremental AI notes (Notability Pro, StudyFetch, Notigo), slides beside a live transcript (Clearly, Genio, LearnlyAI), audio-synced replay (Notability, Goodnotes, Genio, Otter). I found **no product that has the AI itself annotate the uploaded slides in real time during an in-room lecture, revise its earlier notes, and replay those annotations in sync with audio.** Notability's own help pages say slide/PDF content is only folded in *after* recording stops. The owners of the canvas (Notability, Goodnotes, Genio) could ship this in one release cycle.
2. **"Live" is probably not the thing students pay for. The annotated slide deck is.** Students already revise from slides; the sellable artifact is "the slides, with what the lecturer actually said written on them, replayable". Live matters most to three groups: non-native listeners, students with ADHD/dyslexia/hearing accommodations, and students in dense slide-driven courses. Lead with the artifact, use live as the demo.
3. **Unit economics is the number-one risk.** At $0.5–1.5 per lecture hour a flat student subscription loses money: a normal student has 35–55 lecture hours a month [U] and the market price anchor is $5–12 a month. The product needs to reach roughly $0.25 per live hour, and to meter live hours, before pricing works.
4. **Sharpest beachhead:** slide-heavy programmes in Stockholm where recording for personal use is explicitly tolerated — start with Karolinska Institutet (medicine/biomedicine), plus English-taught international master's courses at KTH with lecturer permission.
5. **The current name collides.** A free product called "Live Notes" at live-notes-ai.com has almost the same pitch, plus livenotes.online and "Living Notes: AI Live Notebook" on the App Store.

## 2. Clicky — what it is and what transfers

### Facts

| Item | Finding | Confidence |
|---|---|---|
| Builder | Farza Majeed (previously founder of buildspace) | [V] |
| What it is | "An AI teacher that lives as a buddy next to your cursor": sees your screen, talks to you, and points at UI elements. Farza's launch post said he used it to learn DaVinci Resolve | [V] |
| Launch | Announced on X in early April 2026 (repo README carries an update dated 27 April 2026) | [V] |
| Company | Now "HeyClicky", Y Combinator Spring 2026 batch, San Francisco | [V] |
| Funding | About $500K (the standard YC deal) reported by funding aggregators; Crunchbase hides the amount; one aggregator also lists Founders Inc and Pioneer Fund | [S] |
| Open source | github.com/farzaa/clicky, MIT, about 8.0k stars and 1.6k forks. Since 27 April 2026 new development is private; the current app is only at heyclicky.com | [V] |
| Platform | macOS (needs 14.2+ for the open-source build); Windows via waitlist; community Windows ports exist | [V] |
| Price | Free download. A directory lists a free tier with unlimited talk and dictation plus 1,000 agent messages a month; no paid tier found | [S] |
| Traction | Launch demo views reported as about 3 million by one source and 15 million in another newsletter headline; no user or download count published; one directory estimates about 305K monthly site visits | [S]/[U] |
| Direction | Product Hunt "Clicky 2.0 — Talk to AI and launch agents from your Mac": moving from "teacher that points" toward voice + background agents | [S] |

### How it works (from the repo README) [V]

- Menu-bar Swift app with two windows: a control panel and a **transparent full-screen overlay** that draws the cursor buddy.
- Push-to-talk (Control + Option) streams microphone audio over a websocket to **AssemblyAI** for transcription.
- On the hotkey it takes a screenshot with ScreenCaptureKit and sends transcript + screenshot to **Claude** with streaming responses.
- Claude's reply is spoken through **ElevenLabs** text-to-speech.
- **Pointing is done with inline tags in the model's text output**: `[POINT:x,y:label:screenN]`. The app parses the tag out of the stream and animates the pointer to that coordinate on that monitor.
- A Cloudflare Worker proxies the three APIs so keys are not shipped in the binary.

### What is transferable

1. **Inline action tags in a streaming response.** This is the cheapest possible way to make a model "draw": let it emit `[HIGHLIGHT:…]`, `[NOTE:…]`, `[REVISE:note_id]` inside its normal stream and render them as they arrive. No agent framework needed.
2. **We can do better than pixel coordinates.** Clicky has to guess x,y from a screenshot. We get the slides in advance, so we can pre-parse every slide into addressable elements (text blocks, figures, bounding boxes) and have the model reference **element IDs**. That removes the main failure mode of Clicky-style pointing.
3. **Overlay, don't replace.** Clicky annotates the app the user already uses. Our equivalent is annotating the lecturer's own slides instead of producing a separate notes document.
4. **The product is its own advert.** A pointer moving on screen is understandable in a 15-second clip. Our equivalent is a split screen: lecturer talking on the left, the slide being annotated on the right. Build the product so that this clip can be exported.
5. **Open source as launch fuel** (8k stars in weeks), then close development once there is pull. Worth considering for the renderer or replay format, not the whole product.

### What is not transferable

- **Pull versus push.** Clicky answers when asked, so it pays per question and the user has already told it what matters. We run continuously for 45–90 minutes, pay per hour, and must decide unprompted what is worth writing. Cost and error tolerance are both worse for us.
- **Distribution.** Clicky rode Farza's existing audience (buildspace is reported at 125,000+ builders [S]). A student founder in Stockholm does not have that.
- Voice output and screen capture are irrelevant in a lecture hall.

## 3. Competitors (late 2026)

### 3.1 Table

"Live" = what happens while the lecturer is speaking. "On-slide AI" = the AI itself writes, highlights or draws on the slide. "Synced replay" = audio replays in step with notes or slides.

| Product | Live | Uses slides | On-slide AI | Synced replay | Price (see section 0) | Platform | Traction / funding |
|---|---|---|---|---|---|---|---|
| **Turbo AI** (ex-TurboLearn) | Records in app; notes, flashcards, quizzes produced after. Real-time notes not confirmed [U] | Slides/PDFs accepted as a separate source | No | Not found [U] | App Store: $9.99/week, $14.99–19.99/month, $69.99–119.99/year; no public web pricing page [S] | Web, iOS, Android | 5M users and 20K signups/day (TechCrunch, Oct 2025); about $13M lifetime revenue; $750K raised; team of about 10 [V]. "10M users" in one later source [U] |
| **Coconote** (Quizlet) | Records; notes in under a minute after. Live transcript not confirmed [U] | PDFs as input | No | Not found [U] | $59/year (aggregator, June 2026); App Store purchases $9.99–189.99 [S] | iOS, Android, web | Acquired by Quizlet, announced 5 Feb 2026 [V]; about 25.6K App Store ratings at 4.7 [S]; pre-acquisition MRR of $200–300K claimed by growth blogs [U] |
| **Genio Notes** (ex-Glean, ex-Sonocent) | Records audio; the *student* types time-stamped notes and labels. Live captions on institutional plans only | **Yes** — import slides/PDFs, aligned to audio | No (student annotates by hand; AI Outline after) | **Yes** — core feature | From £12/month or £144/year individual; institutions by quote [V] | Web, iOS, Android | Claims 160,000+ students at 1,000+ institutions [U]; rebranded June 2025; sold mainly through disability services |
| **Jamworks** | Live subtitles; one-tap highlight button | AI tutor answers about slides | No | Partial [U] | £14.99/month student; institutions by quote [V] | Web, mobile | Claims 100+ universities [U] |
| **Otter** | **Live transcript** | Auto-captures slides only from Zoom/Meet/Teams calls, not in a room | No | Yes (audio ↔ transcript) | Pro $16.99/month or $8.33/month annual; 50% student offer announced 26 Aug 2026 (was 20% for .edu) [S] | Web, iOS, Android | Defending a consolidated privacy class action (section 5) |
| **Notability** (Ginger Labs) | **Real-time Smart Notes** generated from the transcript while recording (Pro) | Yes, as the note canvas | **No** — vendor help says the note is updated with ink/text/PDF content only when recording ends [V] | **Yes** — ink ↔ audio | Free; Plus about $20/year; Pro about $99/year (one source says $79.99) [S] | iOS, Mac, web, Android | Long-established; **the closest incumbent** |
| **Goodnotes** | Audio recording and transcription; live meeting summaries on a higher tier | Yes, as canvas | No | Yes — ink ↔ audio (free tier capped at 20 minutes) | Essential $11.99/year, Pro $35.99/year, AI Pass $9.99/month (vendor llms.txt) [S] | iOS, Android, Windows, web | Very large installed base [U] |
| **StudyFetch** | **Live Lecture Assistant**: transcribes and builds notes as the lecture runs; you can ask questions mid-lecture (Premium) | Uploaded as study material | No | Not found [U] | Premium $11.99/month ($7.99 annual) [S] | Web, iOS, Android | 6–7M users claimed [U]; $11.5M Series A June 2025 [S] |
| **Notigo** | **Notes roughly every 30 seconds** from laptop mic, editable live, split by topic | No | No | No — says it deletes the recording after processing [S] | About $5/month; free tier 15 notes [S] | Laptop/web only | Small [U] |
| **"Live Notes"** (live-notes-ai.com) | Transcript + summary appended about every minute; "expands hard material" | Not found | No | Not found | **Free, no paid tier** (own claim) [S] | Web [U] | Unknown. **Name collision** |
| **Clearly / Lecture Mate** (Gravity Tech) | **Live transcript beside your slides**, live translation, AI tutor | **Yes** — PDF side by side | No | Not found [U] | $5.99/week, $9.99/month, $49.99/year [S] | iPad-first | Aimed at international students |
| **LearnlyAI** (UK) | Live translated transcript; write on lecture PDFs with Pencil, AI notes alongside (own claim) | Yes | No [U] | Not found | Not found | iPad-focused | Product Hunt launch Feb 2026 [S] |
| **NoteAlong** (Oct 2026) | In-class or recorded | Inserts slides where discussed **only when a browser tab is shared**; off for in-room lectures [S] | No | Not found | Not found | Web | New [U] |
| **Knowt** | Records; notes, flashcards, games after | PowerPoint as input | No | No [U] | Ultra $12.99/month billed yearly ($149.99) or $24.99 monthly [S] | Web, mobile | Large US high-school/AP base [U] |
| **Quizlet** | Via Coconote (kept as a separate brand so far) | — | No | No | Quizlet Plus price not found [U] | All | Incumbent distribution |
| **Mindgrasp** | Live recording on Scholar (5 h/month) and Premium (10 h/month); output after | Uploads | No | No [U] | $9.99 / $12.99 / $14.99 per month [S] | Web, iOS | Note the **hour caps** — they meter audio |
| **Gemini Notebook** (ex-NotebookLM) | Mobile audio recorder (Sept 2026, about 1 hour, English first) saved as a source | Slides as sources | No | No | Free; US students get a year of Google AI Pro ($19.99/month after) [V/S] | Web, iOS, Android | Google. Strongest free post-class option |
| **Microsoft OneNote / Copilot Notebooks** | Record + transcribe with ink sync; "multimodal capture" builds AI pages after (iOS, Android; Windows slipped to about end Oct 2026) | Via OneNote | No | Yes (ink ↔ audio in OneNote) | Included with education licences in part; some features need a paid Copilot licence [S] | All | **KTH gives students Copilot Chat (Jan 2026) and uses Teams Premium as its official digital note-taking support** [V] |
| **ChatGPT** | Record mode: Mac desktop, paid plans; summary after. Study mode is free | Upload | No | No | Plus $20/month | All | Default tool for most students |
| **Notion AI Meeting Notes** | Live transcription, summary after | No | No | No | Business plan about $20/user/month; free student Plus plan has AI as trial only [S] | Desktop | Not aimed at lectures |
| **Granola** | Live transcript + your notes "enhanced" after | No | No | No | Not confirmed [U] | Mac, Windows, iOS | $125M Series C at $1.5B (Mar 2026); pivoting to enterprise [V] |
| **Jamie** | Bot-free meeting notes, works in person | No | No | No | Free 10 notes/month with 30-minute cap; paid from about €25/month [S] | Desktop, mobile | Meetings, not students |
| **Plaud** (hardware) | Records; everything after | No | No | Audio ↔ transcript | Devices $159–189; free 300 min/month; Pro $99.99/year (1,200 min/month) [S] | Device + app | Unit sales not found |
| **Feynman AI** | Several unrelated apps share the name; all post-class | Uploads | No | No | $2.99–5.99/week, $20–60/year [S] | iOS | Low-cost clones |
| **Apple Notes / Samsung Notes** | Record + transcript + summary, free on recent devices | Side by side at best | No | Partial | Free | OS-level | Raises the floor for "free" |
| **Memmo** (Stockholm, ex-Bright) | No lecture recording found | Uploads; digital textbooks | No | No | Free tier + Pro (price not found) | Web, app | Claims 25,000+ students; Pearson partnership May 2026 [S]. Local player for attention, possible partner |

Also noted: an unconfirmed report that Anthropic is building a meeting recorder into Claude Desktop ("Project Parka") [U]; Bluedot and HoverNotes capture slides from video calls or recorded video, not from a room.

### 3.2 Is the gap open?

| Capability | Who has it | Verdict |
|---|---|---|
| Notes appear during the lecture | Notability Pro, StudyFetch, Notigo, live-notes-ai.com | **Shipped.** Not a differentiator on its own |
| Slides and live transcript together | Clearly, Genio, LearnlyAI | **Shipped**, side by side |
| Audio-synced replay | Notability, Goodnotes, Genio, Otter, OneNote | **Shipped**, but synced to *the student's own* ink or transcript |
| AI writes/highlights/draws **on the slide** during an in-room lecture | Nobody found | **Open** |
| Notes visibly **revise** when the lecturer corrects or extends | Nobody found | **Open** (nobody markets it) |
| Replay where **AI annotations build up on the slides in time with audio** | Nobody found | **Open** |
| AI-drawn diagrams during a lecture | Only question-driven whiteboard tutors (ahaboard, BoardyBoo) | **Open** for lectures |

**Point of view.** The combination is unshipped, but be honest about why. It is expensive per hour, hard to get right, and it is unproven that students want it *live*. The moat is thin: Notability already generates live notes and already owns the slide canvas and audio sync, so joining the two is an obvious next step for them. Plan as if a large incumbent ships "AI annotations on your PDF" within 12 months. What they are less likely to do well: course-level memory across lectures, bilingual Swedish/English lectures, and a replay format built around the slide rather than around handwriting.

## 4. Customer segment, willingness to pay, pricing

### 4.1 Who

Criteria for a first segment: slides are the canonical study material and are published before class; lectures are dense and fast; not every lecture is officially recorded; recording for personal use is permitted; students are reachable by one person.

| Segment | Fit | Why / why not |
|---|---|---|
| **KI medicine and biomedicine students** | **Best first** | Slide-heavy, high volume of facts, heavy flashcard culture. KI's own student AI guidance says audio-recording lectures for personal use is allowed, sharing is not [S]. Caveat: lectures with patient cases need a pause button |
| **International master's students at KTH (English-taught, non-native listeners)** | **Best second** | Comprehension problem is acute; they pay tuition, so stakes are high; Clearly's positioning confirms this pain. Caveat: KTH's staff FAQ says students may not record (section 5), so go lecturer by lecturer |
| Students with approved support (ADHD, dyslexia, hearing) | Strong need, slow channel | Already entitled to record. Reach them as individuals first; institutional purchase later |
| KTH/SU first- and second-year programme students in Swedish | Medium | Largest volume, but Swedish speech recognition and blackboard-heavy maths lectures lower quality |
| Law, humanities | Weak | Few slides, discussion-based; SU's English department bans recording outright [S] |

Countries: use Stockholm to learn (founder access, about 330,500 full-time-equivalent students nationally in 2025, about 46,700 international [S]). Build English-first. The proven paying markets are the US (Turbo, Coconote, StudyFetch) and the UK (Genio and Jamworks, largely paid by government disability funding). The US needs consent UX for all-party-consent states before any push.

### 4.2 What they pay for today

- Default: ChatGPT (free or $20/month); usage is near universal (95% of UK undergraduates use generative AI — HEPI 2026 [S]; about 80% at Gothenburg University [S]). No figure found for the share who pay [U].
- Free and institution-provided is rising: Copilot Chat for KTH students, Gemini Notebook, a year of Google AI Pro for US students, OS-level transcription.
- Dedicated study/lecture tools cluster at **$5–15 a month or $50–120 a year**: Notigo about $5/month, Coconote $59/year, Clearly $49.99/year, StudyFetch $11.99/month, Notability Pro about $99/year, Knowt about $150/year, Turbo up to $119.99/year (and $9.99/week for exam-week buyers).
- Institutions pay more per head: Genio £144/year, Jamworks about £180/year.

Realistic self-pay willingness: **€5–10 a month**, with an exam-period spike. Expect low single-digit percent conversion from free to paid [U]. Weekly and term passes fit student cash flow better than annual plans.

### 4.3 The cost problem

Assumptions [U]: a full-time student has 35–55 lecture hours a month; a €9 plan nets about €7 after 25% Swedish VAT and card fees (worse through app stores).

| Live hours used per month | Cost at $0.25/h | Cost at $0.50/h | Cost at $1.00/h | Cost at $1.50/h |
|---|---|---|---|---|
| 10 | $2.50 | $5 | $10 | $15 |
| 15 | $3.75 | $7.50 | $15 | $22.50 |
| 40 | $10 | $20 | $40 | $60 |

Against about €7 net revenue, the plan only has a healthy margin at **about $0.25 per hour and about 15 included hours**. At $0.5–1.5 per hour, "unlimited" is impossible and even 15 hours is break-even or worse. For reference, streaming speech-to-text alone is quoted at about $0.12–0.45 per hour (Soniox, AssemblyAI, Deepgram, ElevenLabs) [S], so the model calls are where the cost must come down.

### 4.4 Pricing recommendation

Two modes, priced differently:

- **Live mode** (expensive): notes on slides in real time.
- **After-class mode** (cheap, batch): same annotated-slide replay, delivered a few minutes after the lecture ends.

| Tier | Price | Includes | Rationale |
|---|---|---|---|
| **Free** | 0 | First lecture fully live at any length; then **2 live hours a month** + 6 after-class hours; replay of everything already made stays free | One real lecture is the "aha". Caps the monthly cost of a free user at a few dollars |
| **Student** | **99 SEK / about €9 a month**, or a **term pass at about 399 SEK / €36 for 5 months** | **15 live hours a month** + generous after-class hours; quizzes and flashcards | Sits at the market anchor. Works only once cost is near $0.25/h |
| **Student Plus** | **189 SEK / about €17 a month** | 40 live hours | For students who want every lecture live |
| **Top-up** | 49 SEK per 5 live hours | — | Exam-week behaviour; protects margin |
| **Supported / institutional** (later) | €120–150 per student per year | Unmetered within fair use, transcript-only mode, admin controls | Benchmarked on Genio and Jamworks |

Do not launch "unlimited". Do not price below Notigo's $5 to win; win on the artifact. FX conversions are approximate [U].

## 5. Legal and policy

### 5.1 Sweden — recording a lecture

| Question | Finding | Confidence |
|---|---|---|
| Is recording for private use a copyright infringement? | Generally no. A lecture is a protected oral work, but the private-copying rule (12 § upphovsrättslagen) lets a student record for private use, comparable to taking notes. Legal commentary (SvJT 2009), the university teachers' union SULF and several universities say this | [V] |
| Can it be shared? | No. Passing the recording to classmates or posting it online infringes the lecturer's copyright | [V] |
| Can the lecturer or university forbid it? | Yes in practice: a lecturer can make "no recording" a condition of attending, and universities can set house rules. Commentators disagree on enforceability | [S] |
| Is it a crime? | Secret recording of a conversation you take part in is generally not a crime in Sweden; unlawful-eavesdropping rules target conversations you are not party to | [U] — confirm with a lawyer |
| Who owns the slides? | The lecturer, by long-standing Swedish practice (teachers keep copyright in teaching material). A student uploading slides for private study is private copying; redistribution is not | [S] |

University positions found:

| University | Position | Source confidence |
|---|---|---|
| **KI** | Audio recording of lectures for own use is allowed; do not pass it on. Separate premises guidelines require consent for filming/recording in general, with students recording lectures named as an exception | [S] |
| **SU** | No general ban; ask the lecturer first; private use only. The English department forbids recording even for personal study. Recording lectures for personal use is offered as an alternative to peer note-taking support | [S] |
| **KTH** | Staff FAQ on distance/hybrid teaching answers "May students record my lectures?" with **no**. Exception: students granted note-taking support may record and photograph the board, using **Microsoft Teams Premium** (records, transcribes, summarises); no onward sharing. A 2012 KTH instruction on sound recording in teaching also exists | [V] for the pages; current general rule for campus lectures [U] |
| **SLU** | Do not record or upload lectures without explicit consent of the lecturer and all participants | [S] |
| Kristianstad (example) | Uses a Teams tool that turns speech into text **without saving audio**; transcripts deleted after 60 days; no sharing of material or summaries | [S] |
| UK examples | Glasgow: lecturer consent needed; recordings and transcripts must not be uploaded to AI tools. UCL 2026/27 reportedly excludes automated transcription by default | [V] Glasgow, [U] UCL |

Takeaway: **"allowed for personal use" is the legal default, "ask first" is the institutional norm, and AI tools are starting to be named explicitly in policies.** KTH is the awkward case for a KTH-based founder.

### 5.2 GDPR

- **The household exemption protects the student, not us.** Recital 18 says the regulation still applies to companies that provide the means for personal processing [V]. We are at least a processor, and a controller for anything we do for our own purposes (analytics, improvement).
- **The lecturer's voice and anything they say about themselves or others is personal data.** It becomes special-category biometric data only if used to identify a person, so **do not build voiceprints or speaker identification** (Fireflies was sued in Illinois in Dec 2025 over voiceprints [S]).
- Legal basis: contract with the student for their own data; legitimate interest for the incidental processing of the lecturer's voice, backed by a written balancing test. Informing each lecturer individually is impractical, so publish a clear page for lecturers and give the student a notice to show or send.
- **US AI providers:** the EU–US Data Privacy Framework is valid today. The General Court dismissed the Latombe challenge on 3 Sept 2025; an appeal (C-703/25 P) is pending at the Court of Justice and I found no ruling [S]. Use providers certified under the framework, sign data-processing agreements with standard contractual clauses as fallback, choose EU regions and zero-retention options where offered, and keep storage in the EU.
- A data protection impact assessment is advisable: new technology, third-party audio, possible sensitive content (patient cases, students with protected identity — KTH's own instruction mentions the latter [S]).
- No guidance from the Swedish authority IMY on AI note-takers was found [U].
- **EU AI Act:** this is not a high-risk education use (it does not grade or admit students). Emotion recognition in education is prohibited, so never infer attention or mood. Transparency duties for AI-generated content apply; exact dates not re-checked [U].

### 5.3 United States

- Federal law and most states need one party's consent; about a dozen states (including California) need everyone's [S]. Whether an open lecture is a "confidential" communication is unsettled, and university policy usually requires instructor permission regardless.
- **Disability law is the wedge:** Section 504 regulations (34 CFR 104.44(b)) bar colleges from banning recorders where a disabled student needs one [S]. Disability offices approve recording as an accommodation, usually with a personal-use agreement, and buy tools such as Genio and Jamworks.
- **Litigation signal:** *In re Otter.AI Privacy Litigation* (N.D. Cal., 5:25-cv-06911), consolidated from suits filed Aug–Sept 2025, alleges Otter recorded people without consent and trained on the recordings, and attacks Otter's "make sure you have the necessary permissions" disclaimer. No ruling found; reported as pending in mid-2026 [S]. Lesson: a terms-of-service disclaimer alone is weak cover, and training on user audio is what plaintiffs go after.

### 5.4 How competitors handle it

| Approach | Who |
|---|---|
| Push responsibility to the user in terms and help text | Otter, Notion, most consumer study apps |
| Put the consent duty on the institution | Microsoft |
| Do not keep audio | Notigo (deletes after processing), Kristianstad's Teams set-up |
| Sell through disability services with personal-use agreements and faculty FAQ pages | Genio, Jamworks |
| Offer an official alternative so students need not record | Universities' own lecture capture; KTH via Teams Premium for supported students |

### 5.5 MVP versus later

**Must be in the MVP**

1. **Permission step before the first recording and a light reminder per recording:** "I'm allowed to record this lecture for my own study", plus a one-tap message to the lecturer in Swedish and English and a public page for lecturers explaining what the app does and how to object.
2. **Personal-use lock:** no public links, no sharing of audio, slides or transcript with other users.
3. **Transcript-only mode** (audio discarded once transcribed) and a visible **pause** button. This is what makes a "yes" easy for a cautious lecturer.
4. **No training on user content**, stated plainly; provider settings to match.
5. Privacy policy, terms (18+ only), list of sub-processors, data-processing agreements, EU storage, deletion on request, and a contact route for lecturers to have a recording removed.
6. No speaker identification, no attention or emotion inference.
7. A written balancing test and a short impact assessment on file.

**Later**

- Institutional contracts, single sign-on, accessibility audit, US security questionnaires.
- Sharing features (needs a rights model: share AI notes only, never raw audio or slides, lecturer opt-in).
- On-device or EU-only speech recognition; per-state consent flows for the US; lecturer-side opt-in programme.

## 6. Go-to-market for a solo founder

### 6.1 What worked for others

| Channel | Evidence | Usable now? |
|---|---|---|
| **Student creators on TikTok/Instagram** | Turbo AI recruited students over TikTok to run fresh accounts; organic content brought the first 300K users and $500K revenue; creator pay is now reported as its largest cost [S]. Coconote: about 259M views across 7 accounts, 5 run by student creators, using lecture-hall footage [S, growth blogs] | Yes at small scale; our split-screen demo suits it. Do not try to outspend them |
| **Disability services and government funding** | Genio, Jamworks (UK DSA), institutional licences | Not for the first 100: long sales cycles. Reach individual students instead |
| **Student discounts** | Otter went from 20% to 50% off for students (Aug 2026) | Later |
| **Free tier from a platform** | Google AI Pro free for students; Copilot via universities | Not available to us; it sets the floor |
| **Founder audience + launch video + open source** | Clicky | Partly: build in public, publish the replay format |

### 6.2 Three credible routes to 100 active users in Stockholm

Define "active" as recording at least two lectures a week for two weeks running.

1. **Course-by-course seeding, starting with your own courses.** Pick 3–5 large, slide-heavy courses for the next study period (starts mid-January [U]). Get the lecturer's explicit yes. Post one finished annotated-slide replay in the course's group chat and Canvas discussion; let people install to get the next one themselves. Target 20–30 actives per course. This is the fastest route and tests the lecturer-permission risk at the same time.
2. **Programme chapters and unions.** KTH sektioner and their study committees, Medicinska Föreningen at KI, SU's unions, SSE's student association. Offer a free term for a whole programme year in exchange for a feedback session; run a lunch talk with a live demo; put a QR code in the chapter room. Study representatives care about lecture quality and can vouch for you.
3. **International master's students and students with support needs.** Programme WhatsApp/WeChat/Facebook groups, THS International, ESN. Message: "follow the lecture in your second language". In parallel, reach students who are already told to record lectures as support, through student-run ADHD and dyslexia communities and by asking the support offices (Funka at KTH, Studentstöd at SU) for a conversation, not a contract.

Supporting moves: short Swedish and English demo clips; apply to KTH Innovation for credibility and legal help [U].

## 7. Riskiest assumptions and cheap experiments (2–4 weeks)

| # | Assumption | Why it might be false | Experiment | Pass signal |
|---|---|---|---|---|
| 1 | **Cost can reach about $0.25 per live hour** without hurting quality | Continuous model calls on a growing transcript are expensive | Record 10 real lectures; replay them offline through the pipeline with event-driven updates, a small model for increments, a larger one for consolidation, cached slide context; log cost per hour | ≤ $0.30/h with blind-rated quality equal to the expensive version |
| 2 | **Live beats "ready two minutes after class"** | Students listen or drift; they may never look at the screen | 15–20 students, same lectures: half get live view, half get the after-class version. Ask the "very disappointed if gone" question; log in-lecture glances and next-day replays | Live group clearly ahead; if not, ship after-class first and keep live as premium |
| 3 | **On-slide notes beat a normal notes document** | The gap may be something nobody wants | Blind preference test: annotated-slide replay versus Turbo AI and Notability output for the same lecture, 15 students | ≥ 70% prefer ours for exam revision |
| 4 | **Quality holds in a real hall** | Laptop mic at row 10, accents, Swedish/English switching, maths | From the same 10 recordings: word error rate per vendor, share of notes attached to the right slide, factual errors per lecture graded by a strong student | ≥ 90% correct slide attachment; ≤ 2 material errors per lecture |
| 5 | **Lecturers say yes** | KTH's stated position is no; AI tools are being named in bans | Email 30 lecturers across KTH, SU, KI asking permission, half offered transcript-only mode | ≥ 60% yes overall; note the lift from transcript-only |
| 6 | **Slides are available before class** | Many lecturers post after, or use the blackboard | Ask 30 students to check their current courses | ≥ 60% of lectures have slides at least an hour before; otherwise build a no-slides mode first |
| 7 | **Students pay €9** | Free alternatives are good and growing | Landing page with three price points and a real pre-order for a term pass | ≥ 5% of visitors from course groups start checkout |

Not testable in a month, but plan for it: an incumbent (Notability, Goodnotes, Google, Microsoft) shipping on-slide AI notes; seasonality and summer churn.

## 8. Positioning and names

**Positioning (one sentence):** *Upload the slides and press record — it writes what your lecturer actually says onto each slide as they say it, and lets you replay the whole lecture slide by slide before the exam.*

**Names.** "Live Notes" should be dropped: descriptive (hard to protect) and already used by a near-identical free product. Candidates below were checked only with one web search each; **no trademark registers (PRV, EUIPO, USPTO) and no domain availability were checked.**

| Name | Idea | Superficial check |
|---|---|---|
| **Slidepen** | The pen that writes on your slides | No lecture or study app with this name surfaced |
| **Understudy** | The one who learns the part alongside you | No AI study app surfaced; a common English word, so conflicts in other classes are likely [U] |
| **Chalkline** | The line between what was said and what was shown | No study app surfaced; likely used in unrelated industries [U] |

Avoid: anything with "Margin" (MarginNote is an established study app), "Scribbl" (existing meeting-notes product), "Notey", "Clearly".

## 9. Sources

Clicky
- https://github.com/farzaa/clicky (read directly)
- https://x.com/FarzaTV/status/2041314633978659092
- https://www.ycombinator.com/companies/heyclicky
- https://www.ycombinator.com/launches/QNN-this-is-heyclicky-an-ai-buddy-that-lives-next-to-your-computer-cursor
- https://www.crunchbase.com/organization/heyclicky
- https://recentfunding.com/companies/heyclicky/
- https://www.producthunt.com/products/clicky-2-0
- https://www.toolify.ai/tool/heyclicky
- https://www.neatprompts.com/p/heyclicky-15m-views-arguing-against-itself
- https://www.xda-developers.com/someone-built-tiny-ai-that-lives-next-to-your-cursor-the-most-useful-thing-ive-tried-this-year/

Competitors
- Turbo AI: https://techcrunch.com/2025/10/23/20-year-old-dropouts-built-ai-notetaker-turbo-ai-to-5-million-users · https://sacra.com/research/turbo-ai · https://letsdatascience.com/news/founders-scale-ai-study-app-to-13m-revenue-41e281e9 · https://www.inc.com/diana-bocco/student-founders-entrepreneurs-ai-startup-venture-capital-funding/91380311 · https://dailynorthwestern.com/2025/10/27/campus/turbocharged-by-initial-success-nu-students-leave-evanston-behind-to-pursue-ai-note-taking-startup-full-time/
- Coconote / Quizlet: https://pulse2.com/quizlet-acquires-coconote-and-adds-new-ai-study-experience · https://thejournal.com/articles/2026/02/13/quizlet-adds-ai-powered-tools-for-active-practice-notetaking.aspx · https://toolradar.com/tools/coconote/pricing · https://makerstack.co/reviews/coconote-review/ · https://growwithplutus.com/blog/coconote-tiktok-strategy · https://www.socialgrowthengineers.com/259m-views-200k-mrr-coconote-ais-shared-playbook-for-tiktok-reels
- Genio: https://genio.co/pricing/individuals · https://genio.co/pricing/institutions · https://genio.co/notes/ai-outline · https://genio.co/about · https://genio.co/blog/goodbye-glean-hello-genio · https://genio.co/blog/genio-vs-caption.ed-vs-jamworks-which-note-taking-tool-is-best-for-students
- Jamworks: https://www.jamworks.com/pricing
- Otter: https://otter.ai/education · https://otter.ai/blog/back-to-school-half-the-price-otter-ai-offers-students-50-off-to-turn-lectures-into-study-guides-quizzes-and-exam-prep · https://sonix.ai/resources/otter-ai-pricing/
- Notability: https://support.gingerlabs.com/hc/en-us/articles/9595133824410-Smart-Notes-Pro · https://support.gingerlabs.com/hc/en-us/articles/9598555904794-Smart-Notes-Web-App · https://blog.notability.com/post/how-we-built-live-transcription · https://toolradar.com/tools/notability/pricing
- Goodnotes: https://goodnotes.com/pricing · https://goodnotes.com/llms.txt · https://www.goodnotes.com/blog/ai-note-taking-apps
- StudyFetch: https://www.studyfetch.com/section/live-ai-note-taker-for-lectures · https://tldv.io/blog/studyfetch-review/
- Notigo: https://notigo.ai/solutions/students · https://www.bluedothq.com/blog/ai-note-takers-for-students-and-lectures
- Live Notes (name collision): https://live-notes-ai.com/ · https://www.livenotes.online/ · https://apps.apple.com/us/app/living-notes-ai-live-notebook/id6757954180
- Clearly / Lecture Mate: https://clearlynotes.com/ · https://apps.apple.com/us/app/-/id6746672252
- LearnlyAI: https://learnlyai.co.uk/
- NoteAlong: https://notealong.com/ai-lecture-note-taker
- Knowt: https://knowt.com/ai-lecture-note-taker · https://toolradar.com/tools/knowt
- Mindgrasp: https://mindgrasp.ai/pricing · https://toolradar.com/tools/mindgrasp/pricing
- Gemini Notebook: https://blog.google/innovation-and-ai/products/gemini-notebook/new-study-tools-september-2026/ · https://workspaceupdates.googleblog.com/2026/09/new-back-to-school-features-and-learning-tools-available-in-Gemini-Notebook.html
- Microsoft: https://mc.merill.net/message/MC1275566 · https://mc.merill.net/message/MC1450130 · https://www.kth.se/student/nyheter/copilot-chat-for-kth-studenter-ett-stod-i-studierna-1.1449050
- ChatGPT: https://techcrunch.com/2025/07/29/openai-launches-study-mode-in-chatgpt
- Notion: https://www.notion.com/pricing?country=US
- Granola: https://thenextweb.com/news/granola-series-c-meeting-ai-enterprise-context
- Jamie: https://toolradar.com/tools/jamie/pricing
- Plaud: https://www.plaud.ai/products/plaud-ai-annual-pro-plan-yearly · https://www.omi.me/blogs/ai-note-takers/plaud-pricing
- Memmo: https://www.memmo.org/en/about
- Anthropic meeting recorder (unconfirmed): https://www.reworked.co/digital-workplace/anthropic-explores-meeting-recorder-that-assigns-tasks-to-claude-agents/
- Speech-to-text prices: https://soniox.com/compare/stt/pricing · https://assemblyai.com/blog/speech-to-text-api-pricing

Legal and policy
- KTH: https://intra.kth.se/utbildning/e-larande/faqs/vanliga-juridiska-fragor-1.1171613 · https://www.kth.se/student/stod/studier/funktionsnedsattning/stod-du-kan-fa/digitalt-anteckningsstod-1.1271086 · https://intra.kth.se/polopoly_fs/1.662095!/ljudupptagning_mm.pdf
- SU: https://www.su.se/barn-och-ungdomsvetenskapliga-institutionen/utbildning/under-utbildningen/upphovsr%C3%A4tt-g%C3%A4llande-f%C3%B6rel%C3%A4sningar-och-seminarier-1.516989 · https://www.su.se/enheter/engelska-institutionen/utbildning/under-utbildningen · https://www.su.se/utbildning/studera-vid-universitetet/studera-med-funktionsnedsattning/stodformer-och-anpassningar
- KI: https://kib.ki.se/ai-for-studenter/ai-och-larande · https://ki.se/en/about/guidelines-on-photographing-filming-and-sound-recording-on-the-karolinska-institutet-premises · https://staff.ki.se/copyright
- SLU: https://www.slu.se/studentwebb/stod-och-service/studiestod/ai-stod-till-dig-som-student/
- Kristianstad: https://www.hkr.se/student/hjalp-och-stod/funktionsnedsattning/anteckningsstod/digitalt-anteckningsstod-i-teams/
- Swedish copyright commentary: https://svjt.se/svjt/2009/717 · https://sulf.se/jobb-lon-och-villkor/upphovsratt/upphovsratt-en-oversikt/ · https://universitetslararen.se/2008/11/30/inspelning-av-forelasning-far-inte-laggas-ut-pa-natet/ · https://www.medarbetarwebben.lu.se/sites/medarbetarwebben.lu.se/files/2020-11/regler-ljudupptagning-fotografering-filmning-undervisningssituationer.pdf
- UK: https://www.gla.ac.uk/myglasgow/policy/recording-teaching/guide/ · https://notibo.net/blog/lecture-recording-policies
- GDPR: https://gdpr-law.eu/recitals/recital-18-not-applicable-to-personal-or-household-activities/ · https://gdprhub.eu/Article_2_GDPR
- Data Privacy Framework: https://www.wilmerhale.com/insights/blogs/wilmerhale-privacy-and-cybersecurity-law/20251201-european-court-of-justice-to-review-challenge-to-eu-us-data-privacy-framework · https://streamlex.eu/resources/dpf-developments-tracker/
- US: https://www.ccny.cuny.edu/sites/default/files/AccessAbility%20Center%20Recording%20Policy%20(1).pdf · https://www.npr.org/2025/08/15/g-s1-83087/otter-ai-transcription-class-action-lawsuit · https://www.fisherphillips.com/en/insights/insights/new-lawsuit-highlights-concerns-about-ai-notetakers

Market data
- https://www.hepi.ac.uk/wp-content/uploads/2026/03/HEPI-Report-199-Gen-AI-Survey-2026.pdf
- https://www.gu.se/sites/default/files/2025-10/Report%20-%20Exploring%20the%20use%20of%20genAI%20applications%20in%20higher%20education%2020250516.pdf
- UKÄ annual report 2026 (student numbers): https://www.uka.se/
- https://statista.com/statistics/533107/sweden-biggest-universities-by-number-of-students

## 10. Not verified — check before relying on it

- Every price in section 3 (no vendor page could be opened).
- Whether Turbo AI and Coconote show anything live, and whether either has slide-synced replay.
- Clicky's launch view count, user numbers and exact funding.
- KTH's current general rule for students recording campus lectures (found: a staff FAQ on distance/hybrid teaching and a 2012 instruction).
- Swedish criminal-law position on recording a lecture you attend; AI Act transparency dates; any IMY guidance.
- Lecture hours per student per month, free-to-paid conversion rates, FX conversions.
- Trademark and domain availability for all name candidates.
