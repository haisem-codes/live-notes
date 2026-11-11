import { describe, expect, it } from 'vitest';
import { formulaSource, newItems, sameItems, tokenize, visibleLengths, wordDiff, atomLength } from '../src/lib/text';

const states = (a: string, b: string) =>
  wordDiff(tokenize(a), tokenize(b)).map((i) => `${i.state}:${i.atom.text}`);

describe('tokenize', () => {
  it('splits words, math, bold, and tracks spaces', () => {
    const atoms = tokenize('**Learning rate** $\\eta$: how big, ok');
    expect(atoms.map((a) => [a.kind, a.text, a.sp])).toEqual([
      ['bold', 'Learning rate', false],
      ['math', '\\eta', true],
      ['text', ':', false],
      ['text', 'how', true],
      ['text', 'big,', true],
      ['text', 'ok', true],
    ]);
  });
  it('keeps math with spaces atomic', () => {
    expect(tokenize('$a + b$').map((a) => a.kind)).toEqual(['math']);
  });
});

describe('wordDiff', () => {
  it('marks only the changed words', () => {
    expect(states('Too small: very slow', 'Too small: still converges')).toEqual([
      'same:Too',
      'same:small:',
      'del:very',
      'del:slow',
      'add:still',
      'add:converges',
    ]);
  });
  it('detects a sign change in a formula atom', () => {
    const d = wordDiff(tokenize('$\\theta + \\eta$'), tokenize('$\\theta - \\eta$'));
    expect(d.map((i) => i.state)).toEqual(['del', 'add']);
  });
  it('identical texts have no changes', () => {
    expect(wordDiff(tokenize('a b c'), tokenize('a b c')).every((i) => i.state === 'same')).toBe(true);
  });
  it('pure insertion and deletion', () => {
    expect(states('', 'a b')).toEqual(['add:a', 'add:b']);
    expect(states('a b', '')).toEqual(['del:a', 'del:b']);
  });
});

describe('visibleLengths', () => {
  const items = newItems(tokenize('hello brave world'));
  const total = items.reduce((n, i) => n + atomLength(i.atom), 0);
  it('reveals in order and completes at p=1', () => {
    expect(visibleLengths(items, 0)).toEqual([0, 0, 0]);
    expect(visibleLengths(items, 1)).toEqual(items.map((i) => atomLength(i.atom)));
    const half = visibleLengths(items, 0.5);
    expect(half.reduce((a, b) => a + b, 0)).toBe(Math.floor(total / 2));
    expect(half[2]).toBe(0);
  });
  it('is monotonic in p', () => {
    let prev = 0;
    for (let i = 0; i <= 40; i++) {
      const sum = visibleLengths(items, i / 40).reduce((a, b) => a + b, 0);
      expect(sum).toBeGreaterThanOrEqual(prev);
      prev = sum;
    }
  });
  it('only added words are animated in an update', () => {
    const d = wordDiff(tokenize('one two three'), tokenize('one 2 three'));
    const v = visibleLengths(d, 0);
    expect(d.map((i, k) => [i.state, v[k]])).toEqual([
      ['same', 3],
      ['del', 4],
      ['add', 0],
      ['same', 6],
    ]);
  });
  it('same items are always fully visible', () => {
    const s = sameItems(tokenize('a b'));
    expect(visibleLengths(s, 0)).toEqual([1, 2]);
  });
});

describe('formulaSource', () => {
  it('strips delimiters', () => {
    expect(formulaSource('$x^2$')).toBe('x^2');
    expect(formulaSource('$$x^2$$')).toBe('x^2');
    expect(formulaSource('x^2')).toBe('x^2');
  });
});
