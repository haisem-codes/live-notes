import type { Block } from '@live-notes/protocol';
import { memo } from 'react';
import { DELETE_FADE_MS, progressAt, writeDuration } from '../lib/progress';
import { atomLength, formulaSource, newItems, sameItems, tokenize, wordDiff } from '../lib/text';
import type { BlockMeta, Ghost } from '../lib/view';
import { DiagramView } from './DiagramView';
import { InlineText, renderMath } from './InlineText';

interface Props {
  block: Block;
  meta: BlockMeta;
  ghost: Ghost | null;
  t: number;
  selected: boolean;
  closedSummary: string | null;
  onSelect: (block: Block) => void;
}

const KIND_LABEL: Partial<Record<Block['kind'], string>> = {
  example: 'Example',
  callout: 'Note',
  question: 'Question',
  definition: 'Definition',
};

const UPDATE_ANIM_MS = 900;
const WATCH_MS = 5200;

function BlockViewImpl({ block, meta, ghost, t, selected, closedSummary, onSelect }: Props) {
  const fade = ghost ? 1 - progressAt(t, ghost.deletedAt, DELETE_FADE_MS) : 1;
  const sinceInsert = t - meta.insertedAt;
  const updatedAt = meta.updatedAt;
  const sinceUpdate = updatedAt !== null ? t - updatedAt : null;
  const updating = sinceUpdate !== null && sinceUpdate < WATCH_MS;
  const revised = block.kind === 'diagram' && updating;

  let body;
  if (block.kind === 'diagram') {
    body = (
      <>
        <div className="diagram-title">
          {block.text}
          {revised ? <span className="chip">revised</span> : null}
        </div>
        <DiagramView block={block} meta={meta} t={t} />
      </>
    );
  } else if (block.kind === 'formula') {
    const src = formulaSource(block.text);
    const insertP = progressAt(t, meta.insertedAt, writeDuration(src.length));
    const typed = Math.floor(insertP * src.length);
    if (updating && meta.prevText !== null && updatedAt !== null) {
      const p = progressAt(t, updatedAt, 700);
      body = (
        <div className="formula" style={{ background: tintBg(sinceUpdate!) }}>
          {p < 1 ? (
            <div className="formula__old" style={{ opacity: 1 - p }} dangerouslySetInnerHTML={{ __html: renderMath(formulaSource(meta.prevText), true) }} />
          ) : null}
          <div style={{ opacity: p }} dangerouslySetInnerHTML={{ __html: renderMath(src, true) }} />
        </div>
      );
    } else if (insertP < 1) {
      body = (
        <div className="formula formula--typing">
          <code>
            {src.slice(0, typed)}
            <span style={{ visibility: 'hidden' }}>{src.slice(typed)}</span>
          </code>
        </div>
      );
    } else {
      body = <div className="formula" dangerouslySetInnerHTML={{ __html: renderMath(src, true) }} />;
    }
  } else {
    const nextAtoms = tokenize(block.text);
    const label = KIND_LABEL[block.kind];
    if (updating && meta.prevText !== null && updatedAt !== null) {
      const items = wordDiff(tokenize(meta.prevText), nextAtoms);
      const addedChars = items.filter((i) => i.state === 'add').reduce((n, i) => n + atomLength(i.atom), 0);
      const writeP = progressAt(t, updatedAt, Math.min(UPDATE_ANIM_MS, writeDuration(addedChars)));
      body = (
        <>
          {label ? <span className="kind-label">{label}</span> : null}
          <InlineText items={items} writeP={writeP} sinceUpdate={sinceUpdate} delFadeMs={UPDATE_ANIM_MS} />
        </>
      );
    } else {
      const items = sinceInsert < 1600 ? newItems(nextAtoms) : sameItems(nextAtoms);
      const writeP = progressAt(t, meta.insertedAt, writeDuration(block.text.length));
      body = (
        <>
          {label ? <span className="kind-label">{label}</span> : null}
          <InlineText items={items} writeP={writeP} sinceUpdate={null} delFadeMs={0} />
        </>
      );
    }
  }

  return (
    <div
      className={`block block--${block.kind} depth-${block.depth} status-${block.status}${selected ? ' is-selected' : ''}${ghost ? ' is-ghost' : ''}`}
      data-block={block.id}
      data-status={block.status}
      style={{ opacity: fade }}
      onClick={() => onSelect(block)}
      title={`Jump to where this came from${block.src.length ? ` (${block.src.join(', ')})` : ''}`}
    >
      <div className="block__body">{body}</div>
      {closedSummary ? <div className="block__summary">Section closed. {closedSummary}</div> : null}
    </div>
  );
}

function tintBg(since: number): string {
  const s = Math.max(0, 1 - Math.max(0, since - 2500) / 2500);
  return `rgba(255, 207, 64, ${(0.38 * s).toFixed(3)})`;
}

export const BlockView = memo(BlockViewImpl);
