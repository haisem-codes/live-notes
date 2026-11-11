import type { Block, SlideAnnotation } from '@live-notes/protocol';
import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from 'react';
import { NotesSheet } from './components/NotesSheet';
import { SlideView } from './components/SlideView';
import { Ticker } from './components/Ticker';
import { Transport } from './components/Transport';
import { AudioElementClock, type PlayerClock, VirtualClock } from './lib/clock';
import { formatTime } from './lib/progress';
import { type LoadedSession, blockSourceStart, loadSession, resolveAsset } from './lib/session';
import { appliedCount, viewAt } from './lib/view';

const DEFAULT_SESSION = 'demo-gradient-descent';
const SEEK_STEP_MS = 5000;

interface UrlParams {
  session: string;
  t: number | null;
  paused: boolean;
  speed: number;
}

function readParams(): UrlParams {
  const q = new URLSearchParams(window.location.search);
  const t = q.get('t');
  const speed = Number(q.get('speed') ?? 1);
  return {
    session: q.get('session') ?? DEFAULT_SESSION,
    t: t !== null && Number.isFinite(Number(t)) ? Number(t) : null,
    paused: q.get('paused') === '1' || q.get('paused') === 'true',
    speed: [1, 2, 4].includes(speed) ? speed : 1,
  };
}

function makeClock(session: LoadedSession): PlayerClock {
  const audio = session.manifest.audio;
  if (audio) {
    const el = new Audio(resolveAsset(session.baseUrl, audio.url));
    el.preload = 'auto';
    return new AudioElementClock(el);
  }
  return new VirtualClock(session.manifest.duration_ms);
}

export function App() {
  const params = useMemo(readParams, []);
  const [state, setState] = useState<{ status: 'loading' } | { status: 'error'; message: string } | { status: 'ready'; session: LoadedSession }>({
    status: 'loading',
  });
  useEffect(() => {
    loadSession(`/sessions/${encodeURIComponent(params.session)}/`)
      .then((session) => setState({ status: 'ready', session }))
      .catch((e: unknown) => setState({ status: 'error', message: e instanceof Error ? e.message : String(e) }));
  }, [params.session]);

  if (state.status === 'loading') return <div className="boot">Loading session…</div>;
  if (state.status === 'error') return <div className="boot boot--error">Could not load the session: {state.message}</div>;
  return <Replay session={state.session} params={params} />;
}

declare global {
  interface Window {
    __replay?: {
      seek(ms: number): void;
      play(): void;
      pause(): void;
      time(): number;
      duration: number;
    };
  }
}

function Replay({ session, params }: { session: LoadedSession; params: UrlParams }) {
  const { manifest, segments, ops, baseUrl } = session;
  const [clock] = useState<PlayerClock>(() => makeClock(session));
  const [, rerender] = useReducer((x: number) => x + 1, 0);
  const [viewSlide, setViewSlide] = useState<number | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [peek, setPeek] = useState<{ ann: SlideAnnotation; toast: string } | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => {
    const off = clock.subscribe(rerender);
    if (params.t !== null) clock.seek(params.t);
    clock.setRate(params.speed);
    if (!params.paused) clock.play();
    window.__replay = {
      seek: (ms) => clock.seek(ms),
      play: () => clock.play(),
      pause: () => clock.pause(),
      time: () => clock.now(),
      duration: manifest.duration_ms,
    };
    return off;
  }, [clock, params, manifest.duration_ms]);

  const t = clock.now();
  const n = appliedCount(ops, t);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const view = useMemo(() => viewAt(ops, t), [ops, n]);

  const currentSlide = view.doc.current_slide;
  useEffect(() => setViewSlide(null), [currentSlide]);

  const toggle = useCallback(() => (clock.isPlaying() ? clock.pause() : clock.play()), [clock]);
  const seekBy = useCallback((delta: number) => clock.seek(clock.now() + delta), [clock]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (target && (target.tagName === 'TEXTAREA' || (target.tagName === 'INPUT' && (target as HTMLInputElement).type === 'text'))) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === ' ' || e.code === 'Space') {
        e.preventDefault();
        if (e.type === 'keydown' && !e.repeat) toggle();
      } else if (e.type === 'keydown' && e.key === 'ArrowRight') {
        e.preventDefault();
        seekBy(SEEK_STEP_MS);
      } else if (e.type === 'keydown' && e.key === 'ArrowLeft') {
        e.preventDefault();
        seekBy(-SEEK_STEP_MS);
      }
    };
    window.addEventListener('keydown', onKey);
    window.addEventListener('keyup', onKey);
    return () => {
      window.removeEventListener('keydown', onKey);
      window.removeEventListener('keyup', onKey);
    };
  }, [toggle, seekBy]);

  const onSelectBlock = useCallback(
    (block: Block) => {
      const start = blockSourceStart(block.src, segments);
      if (start !== null) clock.seek(start);
      // The annotation that belongs to this note, from the whole log (it may not exist yet at `start`).
      let ann: SlideAnnotation | null = null;
      for (const op of ops) if (op.type === 'slide.annotate' && op.payload.note === block.id) ann = op.payload;
      setSelectedId(block.id);
      const label = start !== null ? `Jumped to ${formatTime(start)}` : 'No source moment for this note';
      setToast(ann ? `${label} · marked on slide ${ann.slide}` : label);
      setPeek(ann ? { ann, toast: label } : null);
      clearTimeout(timer.current);
      timer.current = setTimeout(() => {
        setSelectedId(null);
        setPeek(null);
        setToast(null);
      }, 2800);
    },
    [clock, ops, segments],
  );
  useEffect(() => () => clearTimeout(timer.current), []);

  const shownSlide = peek?.ann.slide ?? viewSlide ?? currentSlide ?? 1;
  const page = manifest.slides.find((s) => s.index === shownSlide) ?? manifest.slides[0];

  return (
    <div className="app">
      <header className="topbar">
        <span className="brand">
          <span className="brand__mark" aria-hidden="true" />
          Live Notes
        </span>
        <span className="topbar__title">{manifest.title}</span>
        <span className="chip chip--quiet">Replay</span>
      </header>
      <main className="stage">
        <section className="pane" aria-label="Slides and transcript">
          <div className="slide-wrap">
            <SlideView page={page} baseUrl={baseUrl} view={view} t={t} peek={peek?.ann ?? null} />
            {toast ? <div className="toast" role="status">{toast}</div> : null}
            {viewSlide !== null && viewSlide !== currentSlide ? (
              <button className="chip chip--action" onClick={() => setViewSlide(null)}>
                Back to the lecturer’s slide ({currentSlide ?? 1})
              </button>
            ) : null}
          </div>
          <Ticker segments={segments} t={t} />
          <nav className="thumbs" aria-label="Slides">
            {manifest.slides.map((s) => (
              <button
                key={s.index}
                className={`thumb${s.index === shownSlide ? ' is-shown' : ''}${s.index === currentSlide ? ' is-current' : ''}`}
                onClick={() => setViewSlide(s.index)}
                aria-label={`Show slide ${s.index}`}
                aria-current={s.index === shownSlide}
              >
                <img src={`${baseUrl}${s.image_url}`} alt="" draggable={false} />
                <span className="thumb__no">{s.index}</span>
              </button>
            ))}
          </nav>
        </section>
        <NotesSheet view={view} t={t} selectedId={selectedId} onSelect={onSelectBlock} />
      </main>
      <Transport
        t={t}
        duration={manifest.duration_ms}
        playing={clock.isPlaying()}
        rate={clock.rate()}
        ops={ops}
        onToggle={toggle}
        onSeek={(ms) => clock.seek(ms)}
        onRate={(r) => clock.setRate(r)}
      />
    </div>
  );
}
