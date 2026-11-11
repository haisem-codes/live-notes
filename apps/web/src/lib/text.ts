/** Inline markdown atoms, word-level diff and character-level reveal. All pure. */

export type AtomKind = 'text' | 'bold' | 'italic' | 'code' | 'math';

export interface Atom {
  kind: AtomKind;
  /** Inner text: no delimiters. */
  text: string;
  /** Whitespace precedes this atom. */
  sp: boolean;
}

const ATOM_RE = /(\$[^$]+\$)|(\*\*[^*]+\*\*)|(\*[^*\s][^*]*\*)|(`[^`]+`)|([^\s$*`]+|\S)/g;

export function tokenize(src: string): Atom[] {
  const atoms: Atom[] = [];
  for (const m of src.matchAll(ATOM_RE)) {
    const idx = m.index ?? 0;
    const sp = idx > 0 && /\s/.test(src[idx - 1] ?? '');
    if (m[1]) atoms.push({ kind: 'math', text: m[1].slice(1, -1), sp });
    else if (m[2]) atoms.push({ kind: 'bold', text: m[2].slice(2, -2), sp });
    else if (m[3]) atoms.push({ kind: 'italic', text: m[3].slice(1, -1), sp });
    else if (m[4]) atoms.push({ kind: 'code', text: m[4].slice(1, -1), sp });
    else atoms.push({ kind: 'text', text: m[5] ?? '', sp });
  }
  return atoms;
}

/** Characters an atom contributes to the reveal (leading space counts as one). */
export const atomLength = (a: Atom): number => a.text.length + (a.sp ? 1 : 0);

export type DiffState = 'same' | 'add' | 'del' | 'new';

export interface DiffItem {
  atom: Atom;
  state: DiffState;
}

const key = (a: Atom) => `${a.kind}\u0000${a.text}`;

/** Word-level diff: atoms kept, added in `next`, or deleted from `prev`. Deletions precede additions. */
export function wordDiff(prev: Atom[], next: Atom[]): DiffItem[] {
  const n = prev.length;
  const m = next.length;
  const lcs: number[][] = Array.from({ length: n + 1 }, () => new Array<number>(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      lcs[i]![j] =
        key(prev[i]!) === key(next[j]!)
          ? lcs[i + 1]![j + 1]! + 1
          : Math.max(lcs[i + 1]![j]!, lcs[i]![j + 1]!);
    }
  }
  const out: DiffItem[] = [];
  let i = 0;
  let j = 0;
  while (i < n || j < m) {
    if (i < n && j < m && key(prev[i]!) === key(next[j]!)) {
      out.push({ atom: next[j]!, state: 'same' });
      i++;
      j++;
    } else if (i < n && (j >= m || lcs[i + 1]![j]! >= lcs[i]![j + 1]!)) {
      out.push({ atom: prev[i]!, state: 'del' });
      i++;
    } else {
      out.push({ atom: next[j]!, state: 'add' });
      j++;
    }
  }
  return out;
}

/** Plain diff items for a freshly inserted text: everything is written in. */
export const newItems = (atoms: Atom[]): DiffItem[] => atoms.map((atom) => ({ atom, state: 'new' as const }));
/** Diff items for text shown without any animation. */
export const sameItems = (atoms: Atom[]): DiffItem[] => atoms.map((atom) => ({ atom, state: 'same' as const }));

/**
 * Visible length of every item at write-in progress `p`. Items in state same/del are always fully
 * visible (del fading is handled by the caller); add/new items are revealed in order, sharing `p`.
 */
export function visibleLengths(items: DiffItem[], p: number): number[] {
  const written = items.filter((it) => it.state === 'add' || it.state === 'new');
  const total = written.reduce((s, it) => s + atomLength(it.atom), 0);
  let left = p >= 1 ? total : Math.max(0, Math.min(total, Math.floor(p * total)));
  return items.map((it) => {
    const len = atomLength(it.atom);
    if (it.state === 'same' || it.state === 'del') return len;
    const shown = Math.min(len, left);
    left -= shown;
    return shown;
  });
}

/** Strip `$` delimiters of a formula block's text. */
export function formulaSource(text: string): string {
  const t = text.trim();
  if (t.startsWith('$$') && t.endsWith('$$') && t.length > 4) return t.slice(2, -2).trim();
  if (t.startsWith('$') && t.endsWith('$') && t.length > 2) return t.slice(1, -1).trim();
  return t;
}
