import { foldOps } from '@live-notes/protocol';
import { describe, expect, it } from 'vitest';
import { loadSession } from '../src/lib/session';
import { applyToView, appliedCount, displayBlocks, emptyView, viewAt } from '../src/lib/view';
import { diskFetcher } from './helpers';

const session = await loadSession('/s/', diskFetcher);
const { ops } = session;
const END = session.manifest.duration_ms;

describe('state-at-time selector', () => {
  it('document equals the reference fold at every second', () => {
    for (let t = -1000; t <= END + 1000; t += 1000) {
      expect(viewAt(ops, t).doc).toEqual(foldOps(ops, t));
    }
  });

  it('stepping op by op gives the same view as a direct fold at the same time', () => {
    // walk the playhead forward in 250 ms steps, applying ops as they become due
    let stepped = emptyView();
    let applied = 0;
    for (let t = 0; t <= END; t += 250) {
      const n = appliedCount(ops, t);
      while (applied < n) stepped = applyToView(stepped, ops[applied++]!);
      if (t % 5000 === 0) expect(stepped).toEqual(viewAt(ops, t));
    }
    expect(stepped).toEqual(viewAt(ops, END));
  });

  it('seeking backwards restores exactly the earlier view', () => {
    const early = viewAt(ops, 40_000);
    viewAt(ops, 140_000);
    expect(viewAt(ops, 40_000)).toEqual(early);
  });

  it('records timing facts for the renderer', () => {
    const v = viewAt(ops, 50_000);
    expect(v.blockMeta['b6']).toMatchObject({ insertedAt: 38000, updatedAt: 47200, reason: 'teacher_correction' });
    expect(v.blockMeta['b6']?.prevText).toContain('+');
    expect(v.annotationAddedAt['a3']).toBe(38000);
  });

  it('keeps a ghost for deleted blocks only until it has faded', () => {
    const v = viewAt(ops, 152_600);
    expect(v.doc.blocks.find((b) => b.id === 'b24')).toBeUndefined();
    expect(displayBlocks(v, 152_600, 600).some((d) => d.block.id === 'b24' && d.ghostOf)).toBe(true);
    expect(displayBlocks(v, 153_200, 600).some((d) => d.block.id === 'b24')).toBe(false);
  });

  it('ghost sits where the block was', () => {
    const v = viewAt(ops, 152_600);
    const ids = displayBlocks(v, 152_600, 600).map((d) => d.block.id);
    expect(ids.indexOf('b24')).toBe(ids.indexOf('b23') + 1);
  });
});
