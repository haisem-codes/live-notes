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
  const paper = useRef<HTMLDivElement>(null);

  // Deterministic: the scroll position depends only on which block is newest (and the layout), never on
  // the path the playhead took. Re-applied when the layout settles (fonts, resize).
  useEffect(() => {
    const apply = () => {
      const root = scroller.current;
      if (!root) return;
      if (newest === null) {
        root.scrollTop = 0;
        return;
      }
      const el = root.querySelector<HTMLElement>(`[data-block="${newest}"]`);
      if (!el) return;
      const bottom = el.offsetTop + el.offsetHeight;
      root.scrollTop = Math.max(0, bottom - root.clientHeight + 56);
    };
    apply();
    const ro = new ResizeObserver(apply);
    if (paper.current) ro.observe(paper.current);
    if (scroller.current) ro.observe(scroller.current);
    return () => ro.disconnect();
  }, [newest]);

  return (
    <section className="sheet" aria-label="Notes">
      <div className="sheet__scroll" ref={scroller}>
        <div className="sheet__paper" ref={paper}>
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
