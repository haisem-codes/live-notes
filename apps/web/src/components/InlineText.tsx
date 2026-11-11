import katex from 'katex';
import { memo } from 'react';
import { progressAt, tintStrength } from '../lib/progress';
import { type DiffItem, atomLength, visibleLengths } from '../lib/text';

const mathCache = new Map<string, string>();
export function renderMath(tex: string, displayMode = false): string {
  const key = `${displayMode ? 'D' : 'I'}${tex}`;
  let html = mathCache.get(key);
  if (html === undefined) {
    html = katex.renderToString(tex, { throwOnError: false, displayMode, output: 'html' });
    mathCache.set(key, html);
  }
  return html;
}

interface Props {
  items: DiffItem[];
  /** Write-in progress for add/new items, 0..1. */
  writeP: number;
  /** ms since the update that produced the 'add'/'del' items, or null when there was none. */
  sinceUpdate: number | null;
  delFadeMs: number;
}

const HIDDEN = { visibility: 'hidden' } as const;

/** Renders diff items; unrevealed parts keep their layout space (visibility:hidden) so wrapping never jumps. */
function InlineTextImpl({ items, writeP, sinceUpdate, delFadeMs }: Props) {
  const shown = visibleLengths(items, writeP);
  const tint = sinceUpdate === null ? 0 : tintStrength(sinceUpdate);
  const delP = sinceUpdate === null ? 1 : progressAt(sinceUpdate, 0, delFadeMs);
  return (
    <>
      {items.map((it, i) => {
        const { atom, state } = it;
        const full = atomLength(atom);
        const v = shown[i]!;
        if (state === 'del') {
          if (delP >= 1) return null;
          return (
            <span key={i} className="tok tok--del" style={{ opacity: 1 - delP }}>
              {atom.sp ? ' ' : ''}
              {atom.kind === 'math' ? <span dangerouslySetInnerHTML={{ __html: renderMath(atom.text) }} /> : atom.text}
            </span>
          );
        }
        const tinted = state === 'add' && tint > 0.01;
        const style = tinted ? { backgroundColor: `rgba(255, 207, 64, ${(0.5 * tint).toFixed(3)})` } : undefined;
        const lead = atom.sp ? ' ' : '';
        const hideAll = v === 0;
        let body;
        if (atom.kind === 'math') {
          const ok = v >= full;
          body = <span style={ok ? undefined : HIDDEN} className="tok-math" dangerouslySetInnerHTML={{ __html: renderMath(atom.text) }} />;
        } else {
          const nChars = Math.max(0, v - (atom.sp ? 1 : 0));
          const head = atom.text.slice(0, nChars);
          const rest = atom.text.slice(nChars);
          body = (
            <>
              {head}
              {rest ? <span style={HIDDEN}>{rest}</span> : null}
            </>
          );
        }
        const inner = (
          <>
            {lead}
            {body}
          </>
        );
        const wrapStyle = { ...style, ...(hideAll ? HIDDEN : null) };
        switch (atom.kind) {
          case 'bold':
            return <strong key={i} style={wrapStyle}>{inner}</strong>;
          case 'italic':
            return <em key={i} style={wrapStyle}>{inner}</em>;
          case 'code':
            return <code key={i} style={wrapStyle}>{inner}</code>;
          default:
            return <span key={i} style={wrapStyle}>{inner}</span>;
        }
      })}
    </>
  );
}

export const InlineText = memo(InlineTextImpl);
