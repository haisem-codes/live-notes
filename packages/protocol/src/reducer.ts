/**
 * Reference reducer for the Live Notes op log. Pure, deterministic and total: an op that cannot
 * apply is a no-op. Semantics are specified in the comment block in ./index.ts.
 */
import type { Block, NotesDocument, Op, SlideAnnotation } from './index';

const emptyDocument = (): NotesDocument => ({
  blocks: [],
  annotations: [],
  current_slide: null,
  sections: [],
});

function mergeSrc(existing: readonly string[], added: readonly string[]): string[] {
  const out = [...existing];
  for (const id of added) if (!out.includes(id)) out.push(id);
  return out;
}

/** Returns a new block list with `block` placed directly after `after` (null = first, unknown = end). */
function placeAfter(blocks: readonly Block[], block: Block, after: string | null): Block[] {
  const out = [...blocks];
  if (after === null) {
    out.unshift(block);
    return out;
  }
  const i = out.findIndex((b) => b.id === after);
  if (i < 0) out.push(block);
  else out.splice(i + 1, 0, block);
  return out;
}

function clone<T>(v: T): T {
  return structuredClone(v);
}

function apply(doc: NotesDocument, op: Op): NotesDocument {
  switch (op.type) {
    case 'block.insert': {
      const p = op.payload;
      if (doc.blocks.some((b) => b.id === p.id)) return doc;
      const block: Block = {
        id: p.id,
        kind: p.kind,
        depth: p.depth,
        text: p.text,
        status: 'tentative',
        src: mergeSrc([], p.src),
        slide: p.slide,
        rev: 1,
        diagram: null,
      };
      return { ...doc, blocks: placeAfter(doc.blocks, block, p.after) };
    }
    case 'block.update': {
      const p = op.payload;
      if (!doc.blocks.some((b) => b.id === p.id)) return doc;
      return {
        ...doc,
        blocks: doc.blocks.map((b) =>
          b.id === p.id ? { ...b, text: p.text, rev: b.rev + 1, src: mergeSrc(b.src, p.src) } : b,
        ),
      };
    }
    case 'block.delete': {
      const p = op.payload;
      if (!doc.blocks.some((b) => b.id === p.id)) return doc;
      return { ...doc, blocks: doc.blocks.filter((b) => b.id !== p.id) };
    }
    case 'block.move': {
      const p = op.payload;
      const block = doc.blocks.find((b) => b.id === p.id);
      if (!block) return doc;
      if (p.after === p.id) return doc;
      if (p.after !== null && !doc.blocks.some((b) => b.id === p.after)) return doc;
      const rest = doc.blocks.filter((b) => b.id !== p.id);
      return { ...doc, blocks: placeAfter(rest, { ...block, depth: p.depth }, p.after) };
    }
    case 'block.status': {
      const p = op.payload;
      const ids = new Set(p.ids);
      if (!doc.blocks.some((b) => ids.has(b.id))) return doc;
      return {
        ...doc,
        blocks: doc.blocks.map((b) => (ids.has(b.id) ? { ...b, status: p.status } : b)),
      };
    }
    case 'diagram.upsert': {
      const p = op.payload;
      const existing = doc.blocks.find((b) => b.id === p.id);
      if (existing) {
        return {
          ...doc,
          blocks: doc.blocks.map((b) =>
            b.id === p.id
              ? { ...b, text: p.title, diagram: clone(p.spec), rev: b.rev + 1, src: mergeSrc(b.src, p.src) }
              : b,
          ),
        };
      }
      const block: Block = {
        id: p.id,
        kind: 'diagram',
        depth: 0,
        text: p.title,
        status: 'tentative',
        src: mergeSrc([], p.src),
        slide: p.slide,
        rev: 1,
        diagram: clone(p.spec),
      };
      return { ...doc, blocks: placeAfter(doc.blocks, block, p.after) };
    }
    case 'slide.annotate': {
      const p = op.payload;
      const ann: SlideAnnotation = clone(p);
      const i = doc.annotations.findIndex((a) => a.id === p.id);
      const annotations = [...doc.annotations];
      if (i >= 0) annotations[i] = ann;
      else annotations.push(ann);
      return { ...doc, annotations };
    }
    case 'slide.annotation.remove': {
      const p = op.payload;
      if (!doc.annotations.some((a) => a.id === p.id)) return doc;
      return { ...doc, annotations: doc.annotations.filter((a) => a.id !== p.id) };
    }
    case 'slide.set':
      return { ...doc, current_slide: op.payload.slide };
    case 'section.close':
      return {
        ...doc,
        sections: [
          ...doc.sections,
          { heading_id: op.payload.heading_id, summary: op.payload.summary },
        ],
      };
    default:
      return doc;
  }
}

/** Apply one op. Never throws and never mutates `doc` or `op`; malformed ops are no-ops. */
export function applyOp(doc: NotesDocument, op: Op): NotesDocument {
  try {
    return apply(doc, op);
  } catch {
    return doc;
  }
}

/**
 * Fold ops in ascending seq. When `t_ms` is given only ops with t_emit_ms <= t_ms are applied.
 * The input array is not mutated or required to be sorted.
 */
export function foldOps(ops: readonly Op[], t_ms?: number): NotesDocument {
  const sorted = ops.every((o, i) => i === 0 || (ops[i - 1] as Op).seq <= o.seq)
    ? ops
    : [...ops].sort((a, b) => a.seq - b.seq);
  let doc = emptyDocument();
  for (const op of sorted) {
    if (t_ms !== undefined && op.t_emit_ms > t_ms) continue;
    doc = applyOp(doc, op);
  }
  return doc;
}

/** True when applying `op` to `doc` changes nothing (the op was a no-op). Used by fixture checks. */
export function isNoOp(doc: NotesDocument, op: Op): boolean {
  return applyOp(doc, op) === doc;
}
