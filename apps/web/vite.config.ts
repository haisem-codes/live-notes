import { cpSync, existsSync, readFileSync, statSync } from 'node:fs';
import { extname, join, normalize, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import react from '@vitejs/plugin-react';
import type { Plugin } from 'vite';
import { defineConfig } from 'vitest/config';

const SESSIONS_DIR = resolve(fileURLToPath(new URL('../../fixtures/sessions', import.meta.url)));

const MIME: Record<string, string> = {
  '.json': 'application/json',
  '.jsonl': 'application/x-ndjson',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.mp3': 'audio/mpeg',
  '.webm': 'audio/webm',
};

/** Serves fixtures/sessions at /sessions/* in dev and preview, and copies it into dist on build. */
function sessionFixtures(): Plugin {
  const serve = (url: string | undefined) => {
    if (!url?.startsWith('/sessions/')) return null;
    const rel = normalize(decodeURIComponent(url.slice('/sessions/'.length).split('?')[0] ?? ''));
    const file = join(SESSIONS_DIR, rel);
    if (!file.startsWith(SESSIONS_DIR) || !existsSync(file) || !statSync(file).isFile()) return null;
    return { body: readFileSync(file), type: MIME[extname(file)] ?? 'application/octet-stream' };
  };
  const middleware = (
    req: { url?: string | undefined },
    res: { setHeader(k: string, v: string): void; end(b: Buffer): void },
    next: () => void,
  ) => {
    const hit = serve(req.url);
    if (!hit) return next();
    res.setHeader('Content-Type', hit.type);
    res.setHeader('Cache-Control', 'no-cache');
    res.end(hit.body);
  };
  return {
    name: 'session-fixtures',
    configureServer(server) {
      server.middlewares.use(middleware);
    },
    configurePreviewServer(server) {
      server.middlewares.use(middleware);
    },
    closeBundle() {
      cpSync(SESSIONS_DIR, resolve('dist/sessions'), { recursive: true, filter: (src) => !src.endsWith('.mjs') });
    },
  };
}

export default defineConfig({
  plugins: [react(), sessionFixtures()],
  server: { port: 5173, strictPort: false },
  test: { include: ['test/**/*.test.ts'], environment: 'node' },
});
