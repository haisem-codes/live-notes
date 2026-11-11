import type { TranscriptSegment } from '@live-notes/protocol';
import { segmentAt } from '../lib/session';

export function Ticker({ segments, t }: { segments: TranscriptSegment[]; t: number }) {
  const { segment, live } = segmentAt(segments, t);
  return (
    <div className={`ticker${live ? ' is-live' : ''}`} aria-live="off">
      <span className="ticker__dot" aria-hidden="true" />
      <span className="ticker__text">
        {segment === null ? (
          <span className="ticker__idle">Listening…</span>
        ) : live && segment.words.length ? (
          segment.words.map((w, i) => (
            <span key={i} className={t >= w.t0_ms ? 'w w--said' : 'w'}>
              {i ? ' ' : ''}
              {w.w}
            </span>
          ))
        ) : (
          <span className={live ? 'w w--said' : 'ticker__prev'}>{segment.text}</span>
        )}
      </span>
    </div>
  );
}
