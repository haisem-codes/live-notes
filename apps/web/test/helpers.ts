import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import type { Fetcher } from '../src/lib/session';

export const SESSION_DIR = fileURLToPath(new URL('../../../fixtures/sessions/demo-gradient-descent/', import.meta.url));

/** A fetcher that serves the session directory from disk. */
export const diskFetcher: Fetcher = async (url) => {
  const file = SESSION_DIR + url.split('/').pop();
  try {
    const body = readFileSync(file, 'utf8');
    return { ok: true, status: 200, text: async () => body };
  } catch {
    return { ok: false, status: 404, text: async () => '' };
  }
};
