import type { SlideAnnotation, SlidePage } from '@live-notes/protocol';
import {
  ANNOTATION_COLORS,
  DRAW_MS,
  SLIDE_H,
  SLIDE_W,
  highlightPath,
  roughPath,
} from '../lib/annotations';
import { clamp01, easeInOut, progressAt } from '../lib/progress';
import { resolveAsset } from '../lib/session';
import type { View } from '../lib/view';

interface Props {
  page: SlidePage | undefined;
  baseUrl: string;
  view: View;
  t: number;
  /** Annotation to show at full strength regardless of the playhead (note click). */
  peek: SlideAnnotation | null;
}

function Shape({ ann, p, ring }: { ann: SlideAnnotation; p: number; ring?: boolean }) {
  return (
    <g data-annotation={ann.id} data-style={ann.style}>
      {ann.rects.map((rect, i) => {
        const pi = easeInOut(clamp01(p * ann.rects.length - i));
        if (pi <= 0) return null;
        if (ann.style === 'highlight') {
          return (
            <path
              key={i}
              d={highlightPath(rect, pi, `${ann.id}#${i}`)}
              fill={ANNOTATION_COLORS.highlight}
              fillOpacity={0.55}
              style={{ mixBlendMode: 'multiply' }}
            />
          );
        }
        return (
          <path
            key={i}
            d={roughPath(ann, rect, i)}
            fill="none"
            stroke={ANNOTATION_COLORS[ann.style]}
            strokeWidth={ann.style === 'underline' ? 5 : 4.5}
            strokeLinecap="butt"
            strokeLinejoin="round"
            pathLength={1}
            strokeDasharray="1 1"
            strokeDashoffset={1 - pi}
          />
        );
      })}
      {ring
        ? ann.rects.map((r, i) => (
            <rect
              key={`ring${i}`}
              className="peek-ring"
              x={r.x * SLIDE_W - 10}
              y={r.y * SLIDE_H - 10}
              width={r.w * SLIDE_W + 20}
              height={r.h * SLIDE_H + 20}
              rx={14}
              fill="none"
              stroke="#2f6f6a"
              strokeWidth={3}
              strokeDasharray="10 8"
            />
          ))
        : null}
    </g>
  );
}

export function SlideView({ page, baseUrl, view, t, peek }: Props) {
  const slideNo = page?.index ?? 1;
  const anns = view.doc.annotations.filter((a) => a.slide === slideNo && a.id !== peek?.id);
  return (
    <div className="slide" data-slide={slideNo}>
      {page ? <img className="slide__img" src={resolveAsset(baseUrl, page.image_url)} alt={`Slide ${page.index}`} draggable={false} /> : null}
      <svg className="slide__overlay" viewBox={`0 0 ${SLIDE_W} ${SLIDE_H}`} preserveAspectRatio="none" aria-hidden="true">
        {anns.map((a) => (
          <Shape key={a.id} ann={a} p={progressAt(t, view.annotationAddedAt[a.id] ?? 0, DRAW_MS[a.style])} />
        ))}
        {peek && peek.slide === slideNo ? <Shape ann={peek} p={1} ring /> : null}
      </svg>
    </div>
  );
}
