/** Pure helpers: every animation in the app is progress = f(playhead, op time). */

export const clamp01 = (x: number): number => (x < 0 ? 0 : x > 1 ? 1 : x);

/** 0 before `start`, 1 after `start + duration`, linear in between. */
export function progressAt(t: number, start: number, duration: number): number {
  if (duration <= 0) return t >= start ? 1 : 0;
  return clamp01((t - start) / duration);
}

export const easeOutCubic = (p: number): number => 1 - Math.pow(1 - clamp01(p), 3);
export const easeInOut = (p: number): number => {
  const x = clamp01(p);
  return x < 0.5 ? 2 * x * x : 1 - Math.pow(-2 * x + 2, 2) / 2;
};

/** How many of `total` characters are visible at progress `p`. */
export function revealCount(total: number, p: number): number {
  if (p >= 1) return total;
  if (p <= 0) return 0;
  return Math.min(total, Math.floor(p * total));
}

export const WRITE_MIN_MS = 800;
export const WRITE_MAX_MS = 1500;
/** Time to write in a text of `length` characters: 0.8 s for short, 1.5 s for long. */
export function writeDuration(length: number): number {
  return Math.min(WRITE_MAX_MS, Math.max(WRITE_MIN_MS, 600 + length * 12));
}

export const TINT_HOLD_MS = 2500;
export const TINT_FADE_MS = 2500;
/** Strength 1..0 of the "this word just changed" tint, `elapsed` ms after an update. */
export function tintStrength(elapsed: number): number {
  if (elapsed < 0) return 0;
  return 1 - progressAt(elapsed, TINT_HOLD_MS, TINT_FADE_MS);
}

export const DELETE_FADE_MS = 600;

export function formatTime(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

/** Stable 32-bit hash used to seed rough.js, so a shape looks identical in every frame. */
export function hashSeed(key: string): number {
  let h = 2166136261;
  for (let i = 0; i < key.length; i++) {
    h ^= key.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return (h >>> 0) % 2147483647 || 1;
}
