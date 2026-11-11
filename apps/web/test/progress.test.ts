import { describe, expect, it } from 'vitest';
import {
  DELETE_FADE_MS,
  WRITE_MAX_MS,
  WRITE_MIN_MS,
  clamp01,
  easeInOut,
  formatTime,
  hashSeed,
  progressAt,
  revealCount,
  tintStrength,
  writeDuration,
} from '../src/lib/progress';

describe('progress helpers', () => {
  it('clamps', () => {
    expect(clamp01(-3)).toBe(0);
    expect(clamp01(0.4)).toBe(0.4);
    expect(clamp01(9)).toBe(1);
  });

  it('progressAt is 0 before, 1 after, linear between', () => {
    expect(progressAt(999, 1000, 500)).toBe(0);
    expect(progressAt(1000, 1000, 500)).toBe(0);
    expect(progressAt(1250, 1000, 500)).toBe(0.5);
    expect(progressAt(1500, 1000, 500)).toBe(1);
    expect(progressAt(9e9, 1000, 500)).toBe(1);
    expect(progressAt(0, 1000, 0)).toBe(0);
    expect(progressAt(1000, 1000, 0)).toBe(1);
  });

  it('is a pure function of time: seek order does not matter', () => {
    const times = [0, 4000, 1100, 1250, 800, 1500, 1249];
    const forward = times.map((t) => progressAt(t, 1000, 500));
    const again = [...times].reverse().map((t) => progressAt(t, 1000, 500)).reverse();
    expect(again).toEqual(forward);
  });

  it('easeInOut is monotonic with fixed endpoints', () => {
    expect(easeInOut(0)).toBe(0);
    expect(easeInOut(1)).toBe(1);
    let prev = 0;
    for (let i = 1; i <= 20; i++) {
      const v = easeInOut(i / 20);
      expect(v).toBeGreaterThanOrEqual(prev);
      prev = v;
    }
  });

  it('revealCount reveals characters in proportion', () => {
    expect(revealCount(10, 0)).toBe(0);
    expect(revealCount(10, 0.5)).toBe(5);
    expect(revealCount(10, 0.999)).toBe(9);
    expect(revealCount(10, 1)).toBe(10);
    expect(revealCount(0, 0.5)).toBe(0);
  });

  it('writeDuration stays within 0.8 and 1.5 s', () => {
    expect(writeDuration(0)).toBe(WRITE_MIN_MS);
    expect(writeDuration(40)).toBeGreaterThanOrEqual(WRITE_MIN_MS);
    expect(writeDuration(10_000)).toBe(WRITE_MAX_MS);
    expect(DELETE_FADE_MS).toBe(600);
  });

  it('tint holds, then fades to zero within five seconds', () => {
    expect(tintStrength(-1)).toBe(0);
    expect(tintStrength(0)).toBe(1);
    expect(tintStrength(2500)).toBe(1);
    expect(tintStrength(3750)).toBeCloseTo(0.5);
    expect(tintStrength(5000)).toBe(0);
  });

  it('formats times and hashes stably', () => {
    expect(formatTime(0)).toBe('0:00');
    expect(formatTime(65_400)).toBe('1:05');
    expect(hashSeed('a1/n2')).toBe(hashSeed('a1/n2'));
    expect(hashSeed('a1/n2')).not.toBe(hashSeed('a1/n3'));
    expect(hashSeed('x')).toBeGreaterThan(0);
  });
});
