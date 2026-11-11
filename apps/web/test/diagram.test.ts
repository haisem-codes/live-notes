import { describe, expect, it } from 'vitest';
import { diagramProgress, layoutDiagram } from '../src/lib/diagram';
import { loadSession } from '../src/lib/session';
import { viewAt } from '../src/lib/view';
import { diskFetcher } from './helpers';

const { ops } = await loadSession('/s/', diskFetcher);

describe('diagram layout', () => {
  const spec = viewAt(ops, 100_000).doc.blocks.find((b) => b.id === 'd1')!.diagram!;
  it('is deterministic for the same id and spec (no jitter between frames)', () => {
    const a = layoutDiagram('d1', spec);
    const b = layoutDiagram('d1', structuredClone(spec));
    expect(b).toEqual(a);
    expect(a.nodes).toHaveLength(spec.nodes.length);
    expect(a.edges).toHaveLength(spec.edges.length);
    expect(a.nodes.every((n) => n.d.length > 10 && n.w > 0)).toBe(true);
  });
  it('seeds by element id', () => {
    expect(layoutDiagram('d1', spec).nodes[0]!.d).not.toBe(layoutDiagram('dX', spec).nodes[0]!.d);
  });
  it('revised spec lays out differently', () => {
    const revised = viewAt(ops, 150_000).doc.blocks.find((b) => b.id === 'd1')!.diagram!;
    expect(layoutDiagram('d1', revised).nodes).toHaveLength(4);
    expect(layoutDiagram('d1', revised).height).toBeGreaterThan(layoutDiagram('d1', spec).height);
  });
});

describe('diagramProgress', () => {
  it('draws nodes before edges and finishes', () => {
    const p0 = diagramProgress(0, 3, 3);
    expect(p0.nodes).toEqual([0, 0, 0]);
    expect(p0.edges).toEqual([0, 0, 0]);
    const mid = diagramProgress(600, 3, 3);
    expect(mid.nodes[0]).toBe(1);
    expect(mid.edges.every((e) => e === 0)).toBe(true);
    const end = diagramProgress(diagramProgress(0, 3, 3).total, 3, 3);
    expect([...end.nodes, ...end.edges].every((x) => x === 1)).toBe(true);
  });
});
