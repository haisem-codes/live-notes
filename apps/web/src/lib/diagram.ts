/** Deterministic diagram layout (dagre) and hand-drawn paths (rough.js, seeded by element id). */
import dagre from '@dagrejs/dagre';
import type { DiagramSpec } from '@live-notes/protocol';
import rough from 'roughjs';
import { hashSeed } from './progress';

export interface DrawnNode {
  id: string;
  label: string;
  x: number;
  y: number;
  w: number;
  h: number;
  /** Outline as SVG path data (drawn in with a dash reveal). */
  d: string;
}

export interface DrawnEdge {
  key: string;
  label: string | null;
  d: string;
  labelX: number;
  labelY: number;
}

export interface DiagramDrawing {
  width: number;
  height: number;
  nodes: DrawnNode[];
  edges: DrawnEdge[];
}

const gen = rough.generator();
const PAD = 16;
const NODE_H = 46;

const round = (n: number) => Math.round(n * 10) / 10;

function pathData(drawable: ReturnType<typeof gen.line>): string {
  return gen
    .toPaths(drawable)
    .map((p) => p.d)
    .join(' ');
}

function arrowHead(
  from: { x: number; y: number },
  to: { x: number; y: number },
  seed: number,
): string {
  const ang = Math.atan2(to.y - from.y, to.x - from.x);
  const len = 13;
  const spread = 0.45;
  const a = { x: to.x - len * Math.cos(ang - spread), y: to.y - len * Math.sin(ang - spread) };
  const b = { x: to.x - len * Math.cos(ang + spread), y: to.y - len * Math.sin(ang + spread) };
  return [
    pathData(gen.line(a.x, a.y, to.x, to.y, { seed: seed + 1, roughness: 0.6, strokeWidth: 2.4 })),
    pathData(gen.line(b.x, b.y, to.x, to.y, { seed: seed + 2, roughness: 0.6, strokeWidth: 2.4 })),
  ].join(' ');
}

const cache = new Map<string, DiagramDrawing>();

export function layoutDiagram(id: string, spec: DiagramSpec): DiagramDrawing {
  const cacheKey = `${id}\u0000${JSON.stringify(spec)}`;
  const hit = cache.get(cacheKey);
  if (hit) return hit;

  const g = new dagre.graphlib.Graph({ multigraph: true });
  g.setGraph({
    rankdir: spec.layout,
    nodesep: 38,
    ranksep: spec.layout === 'LR' ? 64 : 44,
    marginx: PAD,
    marginy: PAD,
  });
  g.setDefaultEdgeLabel(() => ({}));
  for (const n of spec.nodes) {
    g.setNode(n.id, { width: Math.max(96, Math.ceil(n.label.length * 9.2) + 36), height: NODE_H });
  }
  spec.edges.forEach((e, i) => {
    const w = e.label ? e.label.length * 8 + 12 : 0;
    g.setEdge(e.from, e.to, e.label ? { label: e.label, width: w, height: 20, labelpos: 'c' } : {}, `e${i}`);
  });
  dagre.layout(g);

  const nodes: DrawnNode[] = spec.nodes.map((n) => {
    const p = g.node(n.id);
    const x = p.x - p.width / 2;
    const y = p.y - p.height / 2;
    const seed = hashSeed(`${id}/${n.id}`);
    const d = pathData(
      gen.rectangle(x, y, p.width, p.height, { seed, roughness: 1.1, strokeWidth: 2.4, bowing: 0.8 }),
    );
    return { id: n.id, label: n.label, x: round(x), y: round(y), w: round(p.width), h: round(p.height), d };
  });

  const edges: DrawnEdge[] = spec.edges.map((e, i) => {
    const info = g.edge(e.from, e.to, `e${i}`);
    const pts = (info.points ?? []) as { x: number; y: number }[];
    const seed = hashSeed(`${id}/${e.from}>${e.to}#${i}`);
    let d = '';
    if (pts.length >= 2) {
      const curve =
        pts.length === 2
          ? gen.line(pts[0]!.x, pts[0]!.y, pts[1]!.x, pts[1]!.y, { seed, roughness: 0.9, strokeWidth: 2.4 })
          : gen.curve(
              pts.map((p) => [p.x, p.y] as [number, number]),
              { seed, roughness: 0.9, strokeWidth: 2.4 },
            );
      d = `${pathData(curve)} ${arrowHead(pts[pts.length - 2]!, pts[pts.length - 1]!, seed)}`;
    }
    return { key: `${e.from}>${e.to}#${i}`, label: e.label, d, labelX: round(info.x ?? 0), labelY: round(info.y ?? 0) };
  });

  const graph = g.graph();
  const out: DiagramDrawing = {
    width: Math.ceil(graph.width ?? 200),
    height: Math.ceil(graph.height ?? 100),
    nodes,
    edges,
  };
  cache.set(cacheKey, out);
  return out;
}

export const NODE_DRAW_MS = 450;
export const NODE_STAGGER_MS = 260;
export const EDGE_DRAW_MS = 500;
export const EDGE_STAGGER_MS = 220;

/** Draw-in progress of every element, as a pure function of time since the upsert. */
export function diagramProgress(
  elapsed: number,
  nodeCount: number,
  edgeCount: number,
): { nodes: number[]; edges: number[]; total: number } {
  const clamp = (x: number) => (x < 0 ? 0 : x > 1 ? 1 : x);
  const nodes = Array.from({ length: nodeCount }, (_, i) => clamp((elapsed - i * NODE_STAGGER_MS) / NODE_DRAW_MS));
  const edgeStart = nodeCount * NODE_STAGGER_MS + 100;
  const edges = Array.from({ length: edgeCount }, (_, j) => clamp((elapsed - edgeStart - j * EDGE_STAGGER_MS) / EDGE_DRAW_MS));
  return { nodes, edges, total: edgeStart + edgeCount * EDGE_STAGGER_MS + EDGE_DRAW_MS };
}
