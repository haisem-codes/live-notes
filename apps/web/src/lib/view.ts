/**
 * The "state at time T" selector. A View is the folded NotesDocument plus the timing facts the
 * renderer needs (when each block appeared / changed / disappeared). It is a pure function of the
 * op log and the playhead: stepping op by op and folding directly give the same View.
 */
import { applyOp, type Block, type NotesDocument, type Op, type UpdateReason } from '@live-notes/protocol';

export interface BlockMeta {
  insertedAt: number;
  /** t_emit of the latest block.update / diagram.upsert of an existing block. */
  updatedAt: number | null;
  /** Text before the latest update (null for diagrams and never-updated blocks). */
  prevText: string | null;
  reason: UpdateReason | null;
}

export interface Ghost {
  block: Block;
  deletedAt: number;
  /** The block that preceded it when it was deleted (null = it was first). */
  afterId: string | null;
}

export interface View {
  doc: NotesDocument;
  blockMeta: Record<string, BlockMeta>;
  ghosts: Ghost[];
  annotationAddedAt: Record<string, number>;
  slideSetAt: number | null;
  /** heading_id -> t_emit of the section.close. */
  sectionClosedAt: Record<string, number>;
  /** Number of ops applied. */
  applied: number;
}

export const emptyView = (): View => ({
  doc: { blocks: [], annotations: [], current_slide: null, sections: [] },
  blockMeta: {},
  ghosts: [],
  annotationAddedAt: {},
  slideSetAt: null,
  sectionClosedAt: {},
  applied: 0,
});

export function applyToView(view: View, op: Op): View {
  const doc = applyOp(view.doc, op);
  const next: View = { ...view, doc, applied: view.applied + 1 };
  const t = op.t_emit_ms;
  switch (op.type) {
    case 'block.insert':
      if (doc !== view.doc) {
        next.blockMeta = {
          ...view.blockMeta,
          [op.payload.id]: { insertedAt: t, updatedAt: null, prevText: null, reason: null },
        };
      }
      break;
    case 'diagram.upsert': {
      const meta = view.blockMeta[op.payload.id];
      next.blockMeta = {
        ...view.blockMeta,
        [op.payload.id]: meta
          ? { ...meta, updatedAt: t, prevText: null, reason: null }
          : { insertedAt: t, updatedAt: null, prevText: null, reason: null },
      };
      break;
    }
    case 'block.update': {
      const before = view.doc.blocks.find((b) => b.id === op.payload.id);
      const meta = view.blockMeta[op.payload.id];
      if (before && meta) {
        next.blockMeta = {
          ...view.blockMeta,
          [op.payload.id]: { ...meta, updatedAt: t, prevText: before.text, reason: op.payload.reason },
        };
      }
      break;
    }
    case 'block.delete': {
      const idx = view.doc.blocks.findIndex((b) => b.id === op.payload.id);
      if (idx >= 0) {
        next.ghosts = [
          ...view.ghosts,
          { block: view.doc.blocks[idx]!, deletedAt: t, afterId: idx > 0 ? view.doc.blocks[idx - 1]!.id : null },
        ];
      }
      break;
    }
    case 'slide.annotate':
      next.annotationAddedAt = { ...view.annotationAddedAt, [op.payload.id]: t };
      break;
    case 'slide.set':
      next.slideSetAt = t;
      break;
    case 'section.close':
      next.sectionClosedAt = { ...view.sectionClosedAt, [op.payload.heading_id]: t };
      break;
    default:
      break;
  }
  return next;
}

/** Index of the first op with t_emit_ms > t (so ops[0..n) are applied). Ops must be time-ordered. */
export function appliedCount(ops: readonly Op[], t: number): number {
  let lo = 0;
  let hi = ops.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (ops[mid]!.t_emit_ms <= t) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}

/** Direct fold. `ops` must be in ascending seq (and therefore non-decreasing t_emit_ms). */
export function viewAt(ops: readonly Op[], t: number): View {
  const n = appliedCount(ops, t);
  let v = emptyView();
  for (let i = 0; i < n; i++) v = applyToView(v, ops[i]!);
  return v;
}

/** Blocks in display order including fading ghosts of deleted blocks still visible at `t`. */
export interface DisplayBlock {
  block: Block;
  ghostOf: Ghost | null;
}

export function displayBlocks(view: View, t: number, fadeMs: number): DisplayBlock[] {
  const live = view.ghosts.filter((g) => t - g.deletedAt < fadeMs);
  const byAfter = new Map<string | null, Ghost[]>();
  for (const g of live) {
    const known = g.afterId === null || view.doc.blocks.some((b) => b.id === g.afterId) || live.some((o) => o.block.id === g.afterId);
    const k = known ? g.afterId : '\u0000end';
    byAfter.set(k, [...(byAfter.get(k) ?? []), g]);
  }
  const out: DisplayBlock[] = [];
  const emit = (afterId: string | null) => {
    for (const g of byAfter.get(afterId) ?? []) {
      out.push({ block: g.block, ghostOf: g });
      emit(g.block.id);
    }
  };
  emit(null);
  for (const b of view.doc.blocks) {
    out.push({ block: b, ghostOf: null });
    emit(b.id);
  }
  for (const g of byAfter.get('\u0000end') ?? []) out.push({ block: g.block, ghostOf: g });
  return out;
}

/** Newest block (by insertion time) visible at the playhead, for auto-scroll. */
export function newestBlockId(view: View): string | null {
  let best: string | null = null;
  let bestT = -1;
  for (const b of view.doc.blocks) {
    const at = view.blockMeta[b.id]?.updatedAt ?? view.blockMeta[b.id]?.insertedAt ?? -1;
    if (at >= bestT) {
      bestT = at;
      best = b.id;
    }
  }
  return best;
}
