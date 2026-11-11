import { describe, expect, it } from 'vitest';
import { blockSourceStart, loadSession, parseJsonl, resolveAsset, segmentAt } from '../src/lib/session';
import { diskFetcher } from './helpers';

describe('parseJsonl', () => {
  it('skips blank lines and reports bad lines', () => {
    expect(parseJsonl<{ a: number }>('{"a":1}\n\n{"a":2}\n')).toEqual([{ a: 1 }, { a: 2 }]);
    expect(() => parseJsonl('{"a":1}\nnope')).toThrow(/line 2/);
  });
});

describe('loadSession', () => {
  it('loads the demo session', async () => {
    const s = await loadSession('/sessions/demo-gradient-descent', diskFetcher);
    expect(s.manifest.id).toBe('demo-gradient-descent');
    expect(s.manifest.audio).toBeNull();
    expect(s.manifest.slides).toHaveLength(3);
    expect(s.segments.length).toBeGreaterThanOrEqual(24);
    expect(s.ops.length).toBeGreaterThanOrEqual(45);
    expect(s.baseUrl).toBe('/sessions/demo-gradient-descent/');
  });
  it('rejects when a file is missing', async () => {
    await expect(loadSession('/x/', async () => ({ ok: false, status: 404, text: async () => '' }))).rejects.toThrow(/404/);
  });
});

describe('helpers', () => {
  it('resolves relative and absolute asset urls', () => {
    expect(resolveAsset('/s/x/', 'slides/a.svg')).toBe('/s/x/slides/a.svg');
    expect(resolveAsset('/s/x/', 'https://h/a.svg')).toBe('https://h/a.svg');
    expect(resolveAsset('/s/x/', '/abs.svg')).toBe('/abs.svg');
  });
  it('finds the segment under the playhead', async () => {
    const { segments } = await loadSession('/s/', diskFetcher);
    expect(segmentAt(segments, 0).segment).toBeNull();
    expect(segmentAt(segments, 3000)).toMatchObject({ live: true, segment: { id: 's1' } });
    expect(segmentAt(segments, 6000)).toMatchObject({ live: false, segment: { id: 's1' } });
    expect(blockSourceStart(['s9', 's10'], segments)).toBe(47500);
    expect(blockSourceStart(['nope'], segments)).toBeNull();
  });
});
