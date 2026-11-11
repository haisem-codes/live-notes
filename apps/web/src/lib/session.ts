import type { Op, SessionManifest, TranscriptSegment } from '@live-notes/protocol';

export interface LoadedSession {
  manifest: SessionManifest;
  segments: TranscriptSegment[];
  ops: Op[];
  /** Absolute-ish base URL of the session directory, with trailing slash. */
  baseUrl: string;
}

export function parseJsonl<T>(text: string): T[] {
  const rows: T[] = [];
  const lines = text.split('\n');
  lines.forEach((line, i) => {
    const l = line.trim();
    if (!l) return;
    try {
      rows.push(JSON.parse(l) as T);
    } catch {
      throw new Error(`invalid JSON on line ${i + 1}`);
    }
  });
  return rows;
}

export type Fetcher = (url: string) => Promise<{ ok: boolean; status: number; text(): Promise<string> }>;

export async function loadSession(baseUrl: string, fetcher: Fetcher = (u) => fetch(u)): Promise<LoadedSession> {
  const base = baseUrl.endsWith('/') ? baseUrl : `${baseUrl}/`;
  const get = async (name: string) => {
    const res = await fetcher(`${base}${name}`);
    if (!res.ok) throw new Error(`${name}: HTTP ${res.status}`);
    return res.text();
  };
  const [manifestText, transcriptText, opsText] = await Promise.all([
    get('session.json'),
    get('transcript.jsonl'),
    get('ops.jsonl'),
  ]);
  const manifest = JSON.parse(manifestText) as SessionManifest;
  const segments = parseJsonl<TranscriptSegment>(transcriptText);
  const ops = parseJsonl<Op>(opsText).sort((a, b) => a.seq - b.seq);
  return { manifest, segments, ops, baseUrl: base };
}

/** Resolve a slide image URL against the session directory. */
export function resolveAsset(baseUrl: string, url: string): string {
  if (/^([a-z]+:)?\/\//i.test(url) || url.startsWith('/')) return url;
  return `${baseUrl}${url}`;
}

/** The transcript segment the playhead is in; falls back to the most recent finished one. */
export function segmentAt(segments: readonly TranscriptSegment[], t: number): { segment: TranscriptSegment | null; live: boolean } {
  let last: TranscriptSegment | null = null;
  for (const s of segments) {
    if (t >= s.t0_ms && t < s.t1_ms) return { segment: s, live: true };
    if (s.t1_ms <= t) last = s;
  }
  return { segment: last, live: false };
}

/** Start time of the moment a block came from: its first cited segment. */
export function blockSourceStart(src: readonly string[], segments: readonly TranscriptSegment[]): number | null {
  for (const id of src) {
    const s = segments.find((x) => x.id === id);
    if (s) return s.t0_ms;
  }
  return null;
}
