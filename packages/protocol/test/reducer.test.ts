import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { applyOp, foldOps, EMPTY_DOCUMENT, type NotesDocument, type Op } from '../src/index';

const fixture = (name: string) =>
  readFileSync(fileURLToPath(new URL(`../../../fixtures/protocol/${name}`, import.meta.url)), 'utf8');

const ops: Op[] = fixture('golden-ops.jsonl')
  .split('\n')
  .filter((l) => l.trim())
  .map((l) => JSON.parse(l) as Op);

const golden = JSON.parse(fixture('golden-documents.json')) as {
  cases: { t_ms: number; document: NotesDocument }[];
};

describe('golden fixtures', () => {
  it('loads 20 ops and some cases', () => {
    expect(ops).toHaveLength(20);
    expect(golden.cases.length).toBeGreaterThan(0);
  });
  for (const c of golden.cases) {
    it(`foldOps(ops, ${c.t_ms}) equals the golden document`, () => {
      expect(foldOps(ops, c.t_ms)).toEqual(c.document);
    });
  }
  it('foldOps without t_ms equals the last golden case', () => {
    const last = golden.cases[golden.cases.length - 1]!;
    expect(foldOps(ops)).toEqual(last.document);
  });
});

describe('purity', () => {
  it('is deterministic', () => {
    expect(foldOps(ops, 42000)).toEqual(foldOps(ops, 42000));
    expect(JSON.stringify(foldOps(ops))).toBe(JSON.stringify(foldOps(ops)));
  });

  it('does not mutate inputs', () => {
    const before = JSON.stringify(ops);
    const frozenOps = structuredClone(ops);
    const deepFreeze = (o: unknown): void => {
      if (o && typeof o === 'object') {
        Object.freeze(o);
        Object.values(o).forEach(deepFreeze);
      }
    };
    deepFreeze(frozenOps);
    expect(() => foldOps(frozenOps)).not.toThrow();
    expect(JSON.stringify(ops)).toBe(before);
    expect(JSON.stringify(frozenOps)).toBe(before);
  });

  it('applyOp does not mutate the document and EMPTY_DOCUMENT stays empty', () => {
    const doc = foldOps(ops, 20000);
    const snap = JSON.stringify(doc);
    for (const op of ops) applyOp(doc, op);
    expect(JSON.stringify(doc)).toBe(snap);
    foldOps(ops);
    expect(EMPTY_DOCUMENT).toEqual({ blocks: [], annotations: [], current_slide: null, sections: [] });
  });

  it('later mutation of op payloads does not leak into folded documents', () => {
    const local = structuredClone(ops);
    const doc = foldOps(local);
    const snap = JSON.stringify(doc);
    for (const op of local) {
      if (op.type === 'diagram.upsert') op.payload.spec.nodes.length = 0;
      if (op.type === 'slide.annotate') op.payload.rects.length = 0;
      if (op.type === 'block.insert') op.payload.src.push('zzz');
    }
    expect(JSON.stringify(doc)).toBe(snap);
  });

  it('stepping op by op equals direct fold', () => {
    let doc = foldOps([]);
    for (const op of ops) doc = applyOp(doc, op);
    expect(doc).toEqual(foldOps(ops));
  });

  it('sorts by seq and never throws on malformed ops', () => {
    expect(foldOps([...ops].reverse())).toEqual(foldOps(ops));
    const junk = { seq: 99, type: 'block.insert', payload: null, t_emit_ms: 0 } as unknown as Op;
    expect(() => applyOp(EMPTY_DOCUMENT, junk)).not.toThrow();
    expect(applyOp(EMPTY_DOCUMENT, junk)).toBe(EMPTY_DOCUMENT);
  });
});
