/** Geometry and progress for slide annotations. Pure; rough.js and perfect-freehand supply the strokes. */
import type { Rect, SlideAnnotation } from '@live-notes/protocol';
import { getStroke } from 'perfect-freehand';
import rough from 'roughjs';
import { hashSeed } from './progress';

export const SLIDE_W = 1280;
export const SLIDE_H = 720;

export const DRAW_MS: Record<SlideAnnotation['style'], number> = {
  highlight: 750,
  underline: 600,
  circle: 950,
};

const gen = rough.generator();
const round = (n: number) => Math.round(n * 10) / 10;

const toPx = (r: Rect) => ({ x: r.x * SLIDE_W, y: r.y * SLIDE_H, w: r.w * SLIDE_W, h: r.h * SLIDE_H });

function outlineToPath(points: number[][]): string {
  if (points.length < 4) return '';
  const first = points[0]!;
  let d = `M${round(first[0]!)} ${round(first[1]!)} Q`;
  for (let i = 0; i < points.length; i++) {
    const [x0, y0] = points[i]!;
    const [x1, y1] = points[(i + 1) % points.length]!;
    d += `${round(x0!)} ${round(y0!)} ${round((x0! + x1!) / 2)} ${round((y0! + y1!) / 2)} `;
  }
  return d + 'Z';
}

/** Marker stroke across a rect, drawn from the left up to `p` (0..1). */
export function highlightPath(rect: Rect, p: number, seedKey: string): string {
  if (p <= 0) return '';
  const { x, y, w, h } = toPx(rect);
  if (h > 70) {
    // Large targets (figures, cards): a soft wipe instead of a marker stroke.
    const pw = (w + 12) * p;
    const r = Math.min(12, pw / 2, (h + 12) / 2);
    const x0 = x - 6;
    const y0 = y - 6;
    const hh = h + 12;
    return `M${round(x0 + r)} ${round(y0)} H${round(x0 + pw - r)} Q${round(x0 + pw)} ${round(y0)} ${round(x0 + pw)} ${round(y0 + r)} V${round(y0 + hh - r)} Q${round(x0 + pw)} ${round(y0 + hh)} ${round(x0 + pw - r)} ${round(y0 + hh)} H${round(x0 + r)} Q${round(x0)} ${round(y0 + hh)} ${round(x0)} ${round(y0 + hh - r)} V${round(y0 + r)} Q${round(x0)} ${round(y0)} ${round(x0 + r)} ${round(y0)} Z`;
  }
  const seed = hashSeed(seedKey);
  const n = Math.max(6, Math.ceil(w / 28));
  const all: number[][] = [];
  for (let i = 0; i <= n; i++) {
    const k = i / n;
    const wobble = (((seed >> (i % 16)) & 3) - 1.5) * 0.9;
    all.push([x - 4 + k * (w + 8), y + h / 2 + wobble, 0.5]);
  }
  const f = p * n;
  const whole = Math.floor(f);
  const pts = all.slice(0, Math.min(n, whole) + 1);
  if (whole < n) {
    const a = all[whole]!;
    const b = all[whole + 1]!;
    const r = f - whole;
    if (r > 0) pts.push([a[0]! + (b[0]! - a[0]!) * r, a[1]! + (b[1]! - a[1]!) * r, 0.5]);
  }
  if (pts.length < 2) pts.push([pts[0]![0]! + 0.1, pts[0]![1]!, 0.5]);
  const outline = getStroke(pts, {
    size: Math.max(12, h * 0.92),
    thinning: 0,
    smoothing: 0.7,
    streamline: 0.3,
    simulatePressure: false,
    start: { cap: true },
    end: { cap: true },
    last: true,
  });
  return outlineToPath(outline);
}

const cacheRough = new Map<string, string>();

/** Rough hand-drawn path data (stroked with pathLength=1 and a dash reveal by the caller). */
export function roughPath(ann: SlideAnnotation, rect: Rect, index: number): string {
  const key = `${ann.id}/${ann.style}/${index}/${rect.x}/${rect.y}/${rect.w}/${rect.h}`;
  const hit = cacheRough.get(key);
  if (hit) return hit;
  const { x, y, w, h } = toPx(rect);
  const seed = hashSeed(`${ann.id}#${index}`);
  let drawable;
  if (ann.style === 'underline') {
    drawable = gen.line(x - 2, y + h + 4, x + w + 4, y + h + 2, { seed, roughness: 1.6, strokeWidth: 5, bowing: 1.4 });
  } else {
    const rx = w * 0.56 + 14;
    const ry = Math.max(h * 0.62 + 10, 26);
    drawable = gen.ellipse(x + w / 2, y + h / 2, rx * 2, ry * 2, {
      seed,
      roughness: 1.4,
      strokeWidth: 4.5,
      curveFitting: 0.92,
    });
  }
  const d = gen
    .toPaths(drawable)
    .map((p) => p.d)
    .join(' ');
  cacheRough.set(key, d);
  return d;
}

export const ANNOTATION_COLORS = {
  highlight: '#ffd23f',
  underline: '#2b62d9',
  circle: '#d8402c',
} as const;
