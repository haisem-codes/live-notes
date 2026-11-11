/** Player clock abstraction: virtual (rAF) when there is no audio, audio-element (audio is master) otherwise. */

export interface PlayerClock {
  /** Current playhead in ms. */
  now(): number;
  isPlaying(): boolean;
  rate(): number;
  play(): void;
  pause(): void;
  seek(ms: number): void;
  setRate(rate: number): void;
  /** Called on every tick while playing and after every seek / state change. */
  subscribe(cb: () => void): () => void;
  destroy(): void;
}

export interface Scheduler {
  now(): number;
  request(cb: () => void): number;
  cancel(id: number): void;
}

export const browserScheduler: Scheduler = {
  now: () => performance.now(),
  request: (cb) => requestAnimationFrame(() => cb()),
  cancel: (id) => cancelAnimationFrame(id),
};

class Emitter {
  private subs = new Set<() => void>();
  subscribe(cb: () => void): () => void {
    this.subs.add(cb);
    return () => this.subs.delete(cb);
  }
  emit(): void {
    this.subs.forEach((cb) => cb());
  }
  clear(): void {
    this.subs.clear();
  }
}

export class VirtualClock implements PlayerClock {
  private pos = 0;
  private playing = false;
  private speed = 1;
  private anchorWall = 0;
  private anchorPos = 0;
  private raf = 0;
  private em = new Emitter();

  constructor(
    private readonly duration: number,
    private readonly sched: Scheduler = browserScheduler,
  ) {}

  now(): number {
    if (!this.playing) return this.pos;
    return Math.min(this.duration, this.anchorPos + (this.sched.now() - this.anchorWall) * this.speed);
  }
  isPlaying(): boolean {
    return this.playing;
  }
  rate(): number {
    return this.speed;
  }
  play(): void {
    if (this.playing) return;
    if (this.pos >= this.duration) this.pos = 0;
    this.playing = true;
    this.anchorWall = this.sched.now();
    this.anchorPos = this.pos;
    this.loop();
    this.em.emit();
  }
  pause(): void {
    if (!this.playing) return;
    this.pos = this.now();
    this.playing = false;
    this.sched.cancel(this.raf);
    this.em.emit();
  }
  seek(ms: number): void {
    const target = Math.max(0, Math.min(this.duration, ms));
    this.pos = target;
    this.anchorPos = target;
    this.anchorWall = this.sched.now();
    this.em.emit();
  }
  setRate(rate: number): void {
    this.anchorPos = this.now();
    this.pos = this.anchorPos;
    this.anchorWall = this.sched.now();
    this.speed = rate;
    this.em.emit();
  }
  subscribe(cb: () => void): () => void {
    return this.em.subscribe(cb);
  }
  destroy(): void {
    this.sched.cancel(this.raf);
    this.playing = false;
    this.em.clear();
  }
  private loop = (): void => {
    this.raf = this.sched.request(() => {
      if (!this.playing) return;
      const t = this.now();
      if (t >= this.duration) {
        this.pos = this.duration;
        this.playing = false;
        this.em.emit();
        return;
      }
      this.em.emit();
      this.loop();
    });
  };
}

/** The subset of HTMLAudioElement the clock needs (also makes it testable without a DOM). */
export interface AudioLike {
  currentTime: number;
  playbackRate: number;
  paused: boolean;
  duration: number;
  play(): Promise<void> | void;
  pause(): void;
  addEventListener(type: string, cb: () => void): void;
  removeEventListener(type: string, cb: () => void): void;
}

export class AudioElementClock implements PlayerClock {
  private em = new Emitter();
  private raf = 0;
  private readonly onEvent = () => {
    this.em.emit();
    if (!this.audio.paused) this.loop();
  };

  constructor(
    private readonly audio: AudioLike,
    private readonly sched: Scheduler = browserScheduler,
  ) {
    for (const ev of ['play', 'pause', 'seeked', 'ratechange', 'ended']) audio.addEventListener(ev, this.onEvent);
  }
  now(): number {
    return Math.round(this.audio.currentTime * 1000);
  }
  isPlaying(): boolean {
    return !this.audio.paused;
  }
  rate(): number {
    return this.audio.playbackRate;
  }
  play(): void {
    void Promise.resolve(this.audio.play()).catch(() => this.em.emit());
  }
  pause(): void {
    this.audio.pause();
  }
  seek(ms: number): void {
    this.audio.currentTime = Math.max(0, ms) / 1000;
    this.em.emit();
  }
  setRate(rate: number): void {
    this.audio.playbackRate = rate;
  }
  subscribe(cb: () => void): () => void {
    return this.em.subscribe(cb);
  }
  destroy(): void {
    for (const ev of ['play', 'pause', 'seeked', 'ratechange', 'ended']) this.audio.removeEventListener(ev, this.onEvent);
    this.sched.cancel(this.raf);
    this.em.clear();
  }
  private loop(): void {
    this.sched.cancel(this.raf);
    this.raf = this.sched.request(() => {
      this.em.emit();
      if (!this.audio.paused) this.loop();
    });
  }
}
