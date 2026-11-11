import type { Block, NotesDocument } from '@live-notes/protocol';
import { useEffect, useMemo, useRef } from 'react';
import { DELETE_FADE_MS } from '../lib/progress';
import { type View, displayBlocks, newestBlockId } from '../lib/view';
import { BlockView } from './BlockView';

interface Props {
  view: View;
  t: number;
  selectedId: string | null;
  onSelect: (block: Block) => void;
}

function summaries(doc: NotesDocument, closedAt: Record<string, number>, t: number): Map<string, string> {
  const m = new Map<string, string>();
  for (const s of doc.sections) if ((closedAt[s.heading_id] ?? Infinity) <= t) m.set(s.heading_id, s.summary);
  return m;
}

export function NotesSheet({ view, t, selectedId, onSelect }: Props) {
  const items = useMemo(() => displayBlocks(view, t, DELETE_FADE_MS), [view, t]);
  const closed = useMemo(() => summaries(view.doc, view.sectionClosedAt, t), [view, t]);
  const scroller = useRef<HTMLDivElement>(null);
  const newest = newestBlockId(view);
  const lastNewest = useRef<string | null>(null);

  useEffect(() => {
    if (newest === lastNewest.current) return;
    lastNewest.current = newest;
    const root = scroller.current;
    if (!root) return;
    if (newest === null) {
      root.scrollTop = 0;
      return;
    }
    const el = root.querySelector<HTMLElement>(`[data-block="${newest}"]`);
    if (!el) return;
    const top = el.offsetTop;
    const bottom = top + el.offsetHeight;
    if (bottom > root.scrollTop + root.clientHeight - 24) root.scrollTop = bottom - root.clientHeight + 48;
    else if (top < root.scrollTop) root.scrollTop = Math.max(0, top - 24);
  }, [newest]);

  return (
    <section className="sheet" aria-label="Notes">
      <div className="sheet__scroll" ref={scroller}>
        <div className="sheet__paper">
          {items.length === 0 ? (
            <p className="sheet__empty">Notes appear here a few seconds after the lecturer says something worth keeping.</p>
          ) : null}
          {items.map(({ block, ghostOf }) => {
            const meta = view.blockMeta[block.id];
            if (!meta) return null;
            return (
              <BlockView
                key={block.id}
                block={block}
                meta={meta}
                ghost={ghostOf}
                t={t}
                selected={selectedId === block.id}
                closedSummary={ghostOf ? null : (closed.get(block.id) ?? null)}
                onSelect={onSelect}
              />
            );
          })}
        </div>
      </div>
    </section>
  );
}
