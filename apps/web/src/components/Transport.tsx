import type { Op } from '@live-notes/protocol';
import { useMemo } from 'react';
import { formatTime } from '../lib/progress';

export const SPEEDS = [1, 2, 4] as const;

type Cat = 'correction' | 'note' | 'diagram' | 'annotation' | 'slide' | 'tidy';

function category(op: Op): Cat {
  switch (op.type) {
    case 'block.update':
      return op.payload.reason === 'teacher_correction' ? 'correction' : 'note';
    case 'block.insert':
      return 'note';
    case 'diagram.upsert':
      return 'diagram';
    case 'slide.annotate':
    case 'slide.annotation.remove':
      return 'annotation';
    case 'slide.set':
      return 'slide';
    default:
      return 'tidy';
  }
}

const PRIORITY: Cat[] = ['correction', 'diagram', 'note', 'annotation', 'slide', 'tidy'];
const CAT_LABEL: Record<Cat, string> = {
  correction: 'teacher correction',
  note: 'note',
  diagram: 'diagram',
  annotation: 'slide annotation',
  slide: 'slide change',
  tidy: 'tidy-up',
};

interface Marker {
  t: number;
  cat: Cat;
  title: string;
}

function markers(ops: readonly Op[]): Marker[] {
  const byT = new Map<number, Op[]>();
  for (const op of ops) byT.set(op.t_emit_ms, [...(byT.get(op.t_emit_ms) ?? []), op]);
  return [...byT.entries()].map(([t, list]) => {
    const cats = new Set(list.map(category));
    const cat = PRIORITY.find((c) => cats.has(c)) ?? 'tidy';
    return { t, cat, title: `${formatTime(t)} · ${[...cats].map((c) => CAT_LABEL[c]).join(', ')}` };
  });
}

interface Props {
  t: number;
  duration: number;
  playing: boolean;
  rate: number;
  ops: readonly Op[];
  onToggle: () => void;
  onSeek: (ms: number) => void;
  onRate: (r: number) => void;
}

export function Transport({ t, duration, playing, rate, ops, onToggle, onSeek, onRate }: Props) {
  const marks = useMemo(() => markers(ops), [ops]);
  const pct = duration > 0 ? (t / duration) * 100 : 0;
  return (
    <footer className="transport">
      <button className="btn btn--play" onClick={onToggle} aria-label={playing ? 'Pause' : 'Play'} title="Space">
        {playing ? (
          <svg viewBox="0 0 24 24" width="22" height="22"><rect x="6" y="5" width="4.5" height="14" rx="1" /><rect x="13.5" y="5" width="4.5" height="14" rx="1" /></svg>
        ) : (
          <svg viewBox="0 0 24 24" width="22" height="22"><path d="M8 5.5v13a1 1 0 0 0 1.5.86l10.5-6.5a1 1 0 0 0 0-1.72L9.5 4.64A1 1 0 0 0 8 5.5Z" /></svg>
        )}
      </button>
      <div className="transport__time" aria-live="off">
        <span>{formatTime(t)}</span>
        <span className="transport__sep">/</span>
        <span>{formatTime(duration)}</span>
      </div>
      <div className="scrub">
        <div className="scrub__track">
          <div className="scrub__fill" style={{ width: `${pct}%` }} />
          {marks.map((m) => (
            <span
              key={m.t}
              className={`mark mark--${m.cat}`}
              style={{ left: `${(m.t / duration) * 100}%` }}
              title={m.title}
            />
          ))}
        </div>
        <input
          className="scrub__input"
          type="range"
          min={0}
          max={duration}
          step={50}
          value={Math.min(t, duration)}
          aria-label="Playhead"
          tabIndex={-1}
          onChange={(e) => onSeek(Number(e.target.value))}
          onKeyDown={(e) => {
            if (e.key.startsWith('Arrow') || e.key === ' ') e.preventDefault();
          }}
        />
      </div>
      <div className="speed" role="group" aria-label="Playback speed">
        {SPEEDS.map((s) => (
          <button key={s} className={`btn btn--speed${rate === s ? ' is-on' : ''}`} onClick={() => onRate(s)}>
            {s}x
          </button>
        ))}
      </div>
    </footer>
  );
}
