import { applyOp, foldOps, type NotesDocument, type Op } from '@live-notes/protocol';
import { describe, expect, it } from 'vitest';
import { loadSession } from '../src/lib/session';
import { diskFetcher } from './helpers';

const session = await loadSession('/s/', diskFetcher);
const { manifest, segments, ops } = session;
const segById = new Map(segments.map((s) => [s.id, s]));

const srcOf = (op: Op): string[] | null =>
  op.type === 'block.insert' || op.type === 'block.update' || op.type === 'diagram.upsert' ? op.payload.src : null;

describe('demo session: manifest, transcript, slides', () => {
  it('has the shape the protocol describes', () => {
    expect(manifest.audio).toBeNull();
    expect(manifest.duration_ms).toBeGreaterThan(140_000);
    expect(manifest.duration_ms).toBeLessThan(170_000);
    expect(manifest.slides.map((s) => s.index)).toEqual([1, 2, 3]);
    for (const s of manifest.slides) {
      expect([s.width, s.height]).toEqual([1280, 720]);
      expect(s.image_url).toMatch(/^slides\/slide-\d\.svg$/);
    }
  });

  it('transcript ids and times are consistent', () => {
    expect(segments.length).toBeGreaterThanOrEqual(24);
    segments.forEach((s, i) => {
      expect(s.id).toBe(`s${i + 1}`);
      expect(s.t1_ms).toBeGreaterThan(s.t0_ms);
      expect(s.t1_ms).toBeLessThanOrEqual(manifest.duration_ms);
      if (i > 0) expect(s.t0_ms).toBeGreaterThanOrEqual(segments[i - 1]!.t1_ms);
      expect(s.words.map((w) => w.w).join(' ')).toBe(s.text);
      expect(s.words[0]!.t0_ms).toBe(s.t0_ms);
      expect(s.words.at(-1)!.t1_ms).toBe(s.t1_ms);
      s.words.forEach((w, k) => {
        expect(w.t1_ms).toBeGreaterThanOrEqual(w.t0_ms);
        if (k > 0) expect(w.t0_ms).toBeGreaterThanOrEqual(s.words[k - 1]!.t1_ms);
      });
    });
  });

  it('region ids are unique per slide and rects are normalised', () => {
    for (const page of manifest.slides) {
      const ids = page.regions.map((r) => r.id);
      expect(new Set(ids).size).toBe(ids.length);
      for (const r of page.regions) {
        const { x, y, w, h } = r.rect;
        expect(x).toBeGreaterThanOrEqual(0);
        expect(y).toBeGreaterThanOrEqual(0);
        expect(x + w).toBeLessThanOrEqual(1.0001);
        expect(y + h).toBeLessThanOrEqual(1.0001);
      }
    }
  });
});

describe('demo session: op log', () => {
  it('has a convincing amount of story', () => {
    expect(ops.length).toBeGreaterThanOrEqual(45);
    expect(ops.length).toBeLessThanOrEqual(60);
    const types = new Set(ops.map((o) => o.type));
    for (const t of ['block.insert', 'block.update', 'block.delete', 'block.move', 'block.status', 'diagram.upsert', 'slide.annotate', 'slide.annotation.remove', 'slide.set', 'section.close']) {
      expect(types.has(t as Op['type'])).toBe(true);
    }
    const styles = new Set(ops.flatMap((o) => (o.type === 'slide.annotate' ? [o.payload.style] : [])));
    expect([...styles].sort()).toEqual(['circle', 'highlight', 'underline']);
    expect(ops.some((o) => o.type === 'block.update' && o.payload.reason === 'teacher_correction')).toBe(true);
    expect(ops.filter((o) => o.type === 'diagram.upsert').length).toBeGreaterThanOrEqual(2);
  });

  it('envelopes are consistent', () => {
    let lastT = 0;
    ops.forEach((op, i) => {
      expect(op.seq).toBe(i + 1);
      expect(op.session_id).toBe(manifest.id);
      expect(op.t_emit_ms).toBeGreaterThanOrEqual(lastT);
      expect(op.t_emit_ms).toBeLessThanOrEqual(manifest.duration_ms);
      lastT = op.t_emit_ms;
      const src = srcOf(op);
      if (src && src.length) {
        const cited = src.map((id) => segById.get(id));
        expect(cited.every(Boolean), `op ${op.seq} cites unknown segment`).toBe(true);
        expect(op.src_t0_ms).toBe(Math.min(...cited.map((s) => s!.t0_ms)));
        expect(op.src_t1_ms).toBe(Math.max(...cited.map((s) => s!.t1_ms)));
      }
      if (op.src_t0_ms !== null || op.src_t1_ms !== null) {
        expect(op.src_t0_ms).not.toBeNull();
        expect(op.src_t1_ms!).toBeGreaterThan(op.src_t0_ms!);
        // an op can only cite speech that has already happened
        expect(op.src_t1_ms!).toBeLessThanOrEqual(op.t_emit_ms);
      }
    });
  });

  it('notes trail speech by roughly 8-15 s (new blocks, measured from the start of the source)', () => {
    const lags = ops
      .filter((o) => o.type === 'block.insert' && o.src_t0_ms !== null)
      .map((o) => o.t_emit_ms - o.src_t0_ms!);
    const sorted = [...lags].sort((a, b) => a - b);
    const median = sorted[Math.floor(sorted.length / 2)]!;
    expect(median).toBeGreaterThanOrEqual(8000);
    expect(median).toBeLessThanOrEqual(15_000);
    expect(Math.min(...lags)).toBeGreaterThanOrEqual(5000);
    expect(Math.max(...lags)).toBeLessThanOrEqual(20_000);
  });

  it('every referenced id exists when it is referenced, and no op is a no-op', () => {
    let doc: NotesDocument = foldOps([]);
    const everBlock = new Set<string>();
    const everAnn = new Set<string>();
    for (const op of ops) {
      const ids = new Set(doc.blocks.map((b) => b.id));
      const annIds = new Set(doc.annotations.map((a) => a.id));
      const need = (id: string | null, what: string) => {
        if (id !== null) expect(ids.has(id), `op ${op.seq} ${op.type}: ${what} ${id} must exist`).toBe(true);
      };
      for (const sid of srcOf(op) ?? []) {
        expect(segById.has(sid), `op ${op.seq}: segment ${sid}`).toBe(true);
        expect(segById.get(sid)!.t1_ms).toBeLessThanOrEqual(op.t_emit_ms);
      }
      switch (op.type) {
        case 'block.insert':
          expect(everBlock.has(op.payload.id), `op ${op.seq}: id reused`).toBe(false);
          need(op.payload.after, 'after');
          break;
        case 'diagram.upsert':
          if (!ids.has(op.payload.id)) {
            expect(everBlock.has(op.payload.id)).toBe(false);
            need(op.payload.after, 'after');
          }
          break;
        case 'block.update':
        case 'block.delete':
          need(op.payload.id, 'id');
          break;
        case 'block.move':
          need(op.payload.id, 'id');
          need(op.payload.after, 'after');
          expect(op.payload.after).not.toBe(op.payload.id);
          break;
        case 'block.status':
          op.payload.ids.forEach((id) => need(id, 'status id'));
          break;
        case 'section.close':
          need(op.payload.heading_id, 'heading');
          break;
        case 'slide.annotate': {
          const a = op.payload;
          const page = manifest.slides.find((s) => s.index === a.slide);
          expect(page, `op ${op.seq}: slide ${a.slide}`).toBeDefined();
          need(a.note, 'note');
          if (a.region !== null) {
            const region = page!.regions.find((r) => r.id === a.region);
            expect(region, `op ${op.seq}: region ${a.region} on slide ${a.slide}`).toBeDefined();
            expect(a.rects).toEqual([region!.rect]);
          }
          expect(a.rects.length).toBeGreaterThan(0);
          everAnn.add(a.id);
          break;
        }
        case 'slide.annotation.remove':
          expect(annIds.has(op.payload.id), `op ${op.seq}: annotation ${op.payload.id}`).toBe(true);
          break;
        case 'slide.set':
          expect(manifest.slides.some((s) => s.index === op.payload.slide)).toBe(true);
          break;
      }
      const next = applyOp(doc, op);
      expect(next, `op ${op.seq} ${op.type} was a no-op`).not.toBe(doc);
      doc = next;
      if (op.type === 'block.insert' || op.type === 'diagram.upsert') everBlock.add(op.payload.id);
    }
  });

  it('final document is tidy', () => {
    const doc = foldOps(ops);
    expect(doc.blocks.find((b) => b.id === 'b24')).toBeUndefined();
    expect(doc.blocks.find((b) => b.id === 'b6')?.text).toContain('-');
    expect(doc.blocks.find((b) => b.id === 'b6')?.rev).toBe(2);
    expect(doc.blocks.find((b) => b.id === 'd1')?.rev).toBe(2);
    expect(doc.annotations.find((a) => a.id === 'a5')).toBeUndefined();
    expect(doc.sections).toHaveLength(2);
    expect(doc.blocks.filter((b) => b.status === 'frozen').length).toBe(10);
    expect(doc.current_slide).toBe(3);
  });

  it('the formula is first written with the wrong sign, then corrected after the lecturer corrects themselves', () => {
    const wrong = foldOps(ops, 40_000).blocks.find((b) => b.id === 'b6')!;
    const fixed = foldOps(ops, 48_000).blocks.find((b) => b.id === 'b6')!;
    expect(wrong.text).toContain('+ \\eta');
    expect(fixed.text).toContain('- \\eta');
    const correction = segments.find((s) => /Sorry, no/.test(s.text))!;
    const update = ops.find((o) => o.type === 'block.update' && o.payload.reason === 'teacher_correction')!;
    expect(update.t_emit_ms - correction.t0_ms).toBeLessThan(15_000);
    expect(update.t_emit_ms).toBeGreaterThan(correction.t1_ms - 6000);
  });
});
