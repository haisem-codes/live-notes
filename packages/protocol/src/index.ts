/**
 * Live Notes protocol v0 — the contract between the web app, the API service and the eval harness.
 *
 * The Python mirror lives in services/api (Pydantic models). Both sides must pass the golden
 * fixture in fixtures/protocol/. Change this file, the mirror and the fixtures together.
 *
 * JSON conventions: snake_case keys, every field always present (nullable instead of optional),
 * times in integer milliseconds of audio position unless named otherwise.
 */

// ---------------------------------------------------------------------------------------------
// Notes document
// ---------------------------------------------------------------------------------------------

export type BlockKind =
  | 'h1'
  | 'h2'
  | 'bullet'
  | 'definition'
  | 'formula'
  | 'example'
  | 'question'
  | 'callout'
  | 'diagram';

/** tentative: fast lane may edit freely. stable: settled. frozen: section closed. user_locked: student edited it. */
export type BlockStatus = 'tentative' | 'stable' | 'frozen' | 'user_locked';

export interface DiagramNode {
  id: string;
  label: string;
}

export interface DiagramEdge {
  from: string;
  to: string;
  label: string | null;
}

/** A constrained graph. Laid out and drawn deterministically by the client. */
export interface DiagramSpec {
  layout: 'LR' | 'TB';
  nodes: DiagramNode[];
  edges: DiagramEdge[];
}

export interface Block {
  /** Short, server-assigned, never reused: "b17" for notes, "d3" for diagrams. */
  id: string;
  kind: BlockKind;
  /** Indent level. Diagram blocks are always depth 0. */
  depth: 0 | 1 | 2;
  /** Inline markdown; LaTeX in $...$. For diagram blocks this is the title. */
  text: string;
  status: BlockStatus;
  /** Transcript segment IDs this block was derived from, in first-cited order, no duplicates. */
  src: string[];
  /** 1-based slide number the block relates to, or null. */
  slide: number | null;
  /** Content revision: 1 on insert, +1 on every block.update or diagram.upsert of an existing block. */
  rev: number;
  /** Present only for kind "diagram"; null otherwise. */
  diagram: DiagramSpec | null;
}

/** Rectangle in slide-page coordinates normalised to 0..1 (origin top-left). */
export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

export type AnnotationStyle = 'highlight' | 'circle' | 'underline';

export interface SlideAnnotation {
  id: string;
  slide: number;
  style: AnnotationStyle;
  /** Resolved geometry. The model never produces this; the server resolves it from region or quote. */
  rects: Rect[];
  /** Region ID from the slide's region map, if the target was a region. */
  region: string | null;
  /** Exact slide text, if the target was a quote. */
  quote: string | null;
  /** Block ID of the note this annotation belongs to, if any. */
  note: string | null;
}

export interface ClosedSection {
  heading_id: string;
  summary: string;
}

/** The folded state at one moment. */
export interface NotesDocument {
  /** In display order; deleted blocks are absent. */
  blocks: Block[];
  /** In first-created order. */
  annotations: SlideAnnotation[];
  current_slide: number | null;
  sections: ClosedSection[];
}

// ---------------------------------------------------------------------------------------------
// Operations
// ---------------------------------------------------------------------------------------------

export type Actor = 'agent_fast' | 'agent_slow' | 'agent_final' | 'user';

export type UpdateReason =
  | 'new_detail'
  | 'teacher_correction'
  | 'clarification'
  | 'merge_duplicate'
  | 'fix_transcription'
  | 'user_edit';

export type DeleteReason = 'superseded' | 'duplicate' | 'teacher_retracted' | 'user_edit';

export interface OpEnvelope {
  /** Total order per session, starting at 1, assigned by the server. */
  seq: number;
  session_id: string;
  /** All ops from one model response (or one user action) share a tick_id. */
  tick_id: string;
  actor: Actor;
  /** Audio position when the op was committed. Replay shows the op from this time on. */
  t_emit_ms: number;
  /** Audio span of the transcript segments the op cites; null when it cites none. */
  src_t0_ms: number | null;
  src_t1_ms: number | null;
}

export interface BlockInsertPayload {
  id: string;
  /** Insert after this block; null inserts at the start. */
  after: string | null;
  kind: Exclude<BlockKind, 'diagram'>;
  depth: 0 | 1 | 2;
  text: string;
  src: string[];
  slide: number | null;
}

export interface BlockUpdatePayload {
  id: string;
  text: string;
  reason: UpdateReason;
  src: string[];
}

export interface BlockDeletePayload {
  id: string;
  reason: DeleteReason;
}

export interface BlockMovePayload {
  id: string;
  after: string | null;
  depth: 0 | 1 | 2;
}

export interface BlockStatusPayload {
  ids: string[];
  status: BlockStatus;
}

export interface DiagramUpsertPayload {
  id: string;
  /** Used only when the diagram block does not exist yet. */
  after: string | null;
  title: string;
  spec: DiagramSpec;
  src: string[];
  slide: number | null;
}

export type SlideAnnotatePayload = SlideAnnotation;

export interface SlideAnnotationRemovePayload {
  id: string;
}

export interface SlideSetPayload {
  slide: number;
  source: 'user' | 'agent';
}

export type SectionClosePayload = ClosedSection;

export type Op = OpEnvelope &
  (
    | { type: 'block.insert'; payload: BlockInsertPayload }
    | { type: 'block.update'; payload: BlockUpdatePayload }
    | { type: 'block.delete'; payload: BlockDeletePayload }
    | { type: 'block.move'; payload: BlockMovePayload }
    | { type: 'block.status'; payload: BlockStatusPayload }
    | { type: 'diagram.upsert'; payload: DiagramUpsertPayload }
    | { type: 'slide.annotate'; payload: SlideAnnotatePayload }
    | { type: 'slide.annotation.remove'; payload: SlideAnnotationRemovePayload }
    | { type: 'slide.set'; payload: SlideSetPayload }
    | { type: 'section.close'; payload: SectionClosePayload }
  );

export type OpType = Op['type'];

/**
 * Reducer semantics. The fold must be pure, deterministic and total: an op that cannot apply is a
 * no-op, never an error. Ops are applied in ascending seq. document(t) folds ops with t_emit_ms <= t.
 *
 * block.insert            New block {status: "tentative", rev: 1, diagram: null}. Placed directly after
 *                         `after`; null places it first; an unknown `after` appends at the end.
 *                         No-op if the id already exists.
 * block.update            Sets text, rev += 1, src = existing src followed by new IDs not already present.
 *                         No-op on an unknown id.
 * block.delete            Removes the block. No-op on an unknown id.
 * block.move              Removes the block and re-inserts it directly after `after` (null = first) with
 *                         the new depth. rev is unchanged. No-op if the id or a non-null `after` is unknown,
 *                         or if after == id.
 * block.status            Sets status on each listed block that exists.
 * diagram.upsert          Existing id: sets text = title and diagram = spec, rev += 1, src merged as in
 *                         block.update; position, status and slide are unchanged.
 *                         New id: inserts {kind: "diagram", depth: 0, text: title, diagram: spec,
 *                         status: "tentative", rev: 1} with the placement rule of block.insert.
 * slide.annotate          Upserts by id: replaces in place if it exists, else appends.
 * slide.annotation.remove Removes by id. No-op on an unknown id.
 * slide.set               current_slide = slide.
 * section.close           Appends {heading_id, summary} to sections.
 */
export const EMPTY_DOCUMENT: NotesDocument = {
  blocks: [],
  annotations: [],
  current_slide: null,
  sections: [],
};

// ---------------------------------------------------------------------------------------------
// Transcript
// ---------------------------------------------------------------------------------------------

export interface TranscriptWord {
  w: string;
  t0_ms: number;
  t1_ms: number;
}

/** A finalized stretch of speech. Interim hypotheses are never stored. */
export interface TranscriptSegment {
  /** "s1", "s2", ... in order of t0_ms. */
  id: string;
  t0_ms: number;
  t1_ms: number;
  text: string;
  /** BCP-47 language tag if the provider reports one. */
  lang: string | null;
  /** Empty when the provider gave no word timings. */
  words: TranscriptWord[];
}

// ---------------------------------------------------------------------------------------------
// Session manifest and slides
// ---------------------------------------------------------------------------------------------

export type RegionKind = 'text' | 'figure' | 'part';

export interface SlideRegion {
  /** "r1", "r2", ... unique within the slide. */
  id: string;
  kind: RegionKind;
  /** The text itself for text regions; a short description for figures and parts. */
  label: string;
  rect: Rect;
}

export interface SlidePage {
  /** 1-based. */
  index: number;
  /** Relative to the session directory, or absolute. */
  image_url: string;
  width: number;
  height: number;
  regions: SlideRegion[];
}

export interface SessionManifest {
  id: string;
  title: string;
  duration_ms: number;
  /** null means no recording: the replay player runs on a virtual clock. */
  audio: { url: string; mime: string } | null;
  slides: SlidePage[];
}

/**
 * A stored session is a directory:
 *   session.json      SessionManifest
 *   transcript.jsonl  one TranscriptSegment per line
 *   ops.jsonl         one Op per line, ascending seq
 *   slides/           page images referenced by image_url
 */

// ---------------------------------------------------------------------------------------------
// WebSocket messages (/ws/sessions/{id})
// ---------------------------------------------------------------------------------------------

export type ClientMessage =
  /** First message on every connection. The server replays ops with seq > last_seq, then goes live. */
  | { type: 'resume'; last_seq: number }
  /** A finalized segment from the browser-side speech provider. The server assigns the id. */
  | { type: 'transcript.final'; segment: Omit<TranscriptSegment, 'id'> }
  /** The student flipped the slide. */
  | { type: 'slide.set'; slide: number; t_ms: number }
  | { type: 'session.end'; t_ms: number };

export type ServerMessage =
  | { type: 'op'; op: Op }
  | { type: 'transcript.final'; segment: TranscriptSegment }
  /** Sent once the backlog after a resume has been replayed. */
  | { type: 'live'; last_seq: number }
  | { type: 'status'; state: 'listening' | 'catching_up' | 'ended' | 'server_restarting' }
  | { type: 'error'; code: string; message: string };
