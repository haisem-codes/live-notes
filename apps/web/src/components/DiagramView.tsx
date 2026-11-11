import type { Block } from '@live-notes/protocol';
import { diagramProgress, layoutDiagram } from '../lib/diagram';
import type { BlockMeta } from '../lib/view';

const INK = '#27323b';

function drawn(p: number) {
  return {
    pathLength: 1,
    strokeDasharray: '1 1',
    strokeDashoffset: 1 - p,
    opacity: p <= 0.001 ? 0 : 1,
  } as const;
}

export function DiagramView({ block, meta, t }: { block: Block; meta: BlockMeta; t: number }) {
  if (!block.diagram) return null;
  const drawing = layoutDiagram(block.id, block.diagram);
  const start = meta.updatedAt ?? meta.insertedAt;
  const prog = diagramProgress(t - start, drawing.nodes.length, drawing.edges.length);
  return (
    <svg
      className="diagram"
      viewBox={`0 0 ${drawing.width} ${drawing.height}`}
      style={{ maxWidth: drawing.width }}
      role="img"
      aria-label={block.text}
    >
      {drawing.edges.map((e, i) => (
        <g key={e.key}>
          <path d={e.d} fill="none" stroke={INK} strokeWidth={2.2} strokeLinecap="butt" strokeLinejoin="round" {...drawn(prog.edges[i]!)} />
          {e.label ? (
            <text
              x={e.labelX}
              y={e.labelY + 5}
              textAnchor="middle"
              className="diagram__edge-label"
              opacity={prog.edges[i]! > 0.5 ? 1 : 0}
            >
              {e.label}
            </text>
          ) : null}
        </g>
      ))}
      {drawing.nodes.map((n, i) => (
        <g key={n.id}>
          <rect x={n.x} y={n.y} width={n.w} height={n.h} rx={6} fill="#fffdf4" fillOpacity={prog.nodes[i]!} />
          <path d={n.d} fill="none" stroke={INK} strokeWidth={2.3} strokeLinecap="butt" {...drawn(prog.nodes[i]!)} />
          <text
            x={n.x + n.w / 2}
            y={n.y + n.h / 2 + 5}
            textAnchor="middle"
            className="diagram__label"
            opacity={Math.max(0, (prog.nodes[i]! - 0.4) / 0.6)}
          >
            {n.label}
          </text>
        </g>
      ))}
    </svg>
  );
}
