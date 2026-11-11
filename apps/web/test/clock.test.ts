import { describe, expect, it } from 'vitest';
import { AudioElementClock, type AudioLike, type Scheduler, VirtualClock } from '../src/lib/clock';

function fakeScheduler() {
  let wall = 0;
  const queue = new Map<number, () => void>();
  let id = 0;
  const sched: Scheduler = {
    now: () => wall,
    request: (cb) => {
      queue.set(++id, cb);
      return id;
    },
    cancel: (i) => void queue.delete(i),
  };
  return {
    sched,
    advance(ms: number) {
      wall += ms;
      const cbs = [...queue.values()];
      queue.clear();
      cbs.forEach((cb) => cb());
    },
  };
}

describe('VirtualClock', () => {
  it('plays at real time, at 2x, pauses and seeks', () => {
    const f = fakeScheduler();
    const c = new VirtualClock(10_000, f.sched);
    expect(c.now()).toBe(0);
    c.play();
    f.advance(1000);
    expect(c.now()).toBe(1000);
    c.setRate(2);
    f.advance(1000);
    expect(c.now()).toBe(3000);
    c.pause();
    f.advance(5000);
    expect(c.now()).toBe(3000);
    c.seek(500);
    expect(c.now()).toBe(500);
    c.seek(-5);
    expect(c.now()).toBe(0);
    c.seek(99_999);
    expect(c.now()).toBe(10_000);
  });

  it('stops at the end and restarts from 0', () => {
    const f = fakeScheduler();
    const c = new VirtualClock(2000, f.sched);
    c.play();
    f.advance(2500);
    expect(c.now()).toBe(2000);
    expect(c.isPlaying()).toBe(false);
    c.play();
    expect(c.now()).toBe(0);
    expect(c.isPlaying()).toBe(true);
  });

  it('notifies subscribers on ticks and seeks', () => {
    const f = fakeScheduler();
    const c = new VirtualClock(10_000, f.sched);
    let n = 0;
    c.subscribe(() => n++);
    c.seek(100);
    c.play();
    f.advance(16);
    f.advance(16);
    expect(n).toBeGreaterThanOrEqual(4);
  });
});

describe('AudioElementClock', () => {
  it('reads time from the audio element, which stays master', () => {
    const listeners: Record<string, (() => void)[]> = {};
    const audio: AudioLike = {
      currentTime: 1.5,
      playbackRate: 1,
      paused: true,
      duration: 100,
      play() {
        this.paused = false;
      },
      pause() {
        this.paused = true;
      },
      addEventListener: (t, cb) => void (listeners[t] = [...(listeners[t] ?? []), cb]),
      removeEventListener: () => undefined,
    };
    const f = fakeScheduler();
    const c = new AudioElementClock(audio, f.sched);
    expect(c.now()).toBe(1500);
    c.seek(42_000);
    expect(audio.currentTime).toBe(42);
    c.setRate(2);
    expect(audio.playbackRate).toBe(2);
    c.play();
    expect(c.isPlaying()).toBe(true);
    audio.currentTime = 43;
    expect(c.now()).toBe(43_000);
  });
});
