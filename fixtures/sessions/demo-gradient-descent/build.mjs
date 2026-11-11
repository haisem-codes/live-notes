// Regenerates the demo session: node fixtures/sessions/demo-gradient-descent/build.mjs
// Writes session.json, transcript.jsonl, ops.jsonl and slides/*.svg next to this file.
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const OUT = dirname(fileURLToPath(import.meta.url));
const SESSION_ID = 'demo-gradient-descent';
const DURATION_MS = 154000;
const W = 1280;
const H = 720;

// ------------------------------------------------------------------------------------------
// Slides. Every element that matters is declared once with its pixel rect; the SVG and the
// normalised region map are both derived from the same declaration.
// ------------------------------------------------------------------------------------------

const INK = '#1f2a33';
const MUTED = '#5b6670';
const ACCENT = '#2f6f6a';
const WARM = '#c2571a';
const SANS = "'Helvetica Neue', Helvetica, Arial, sans-serif";
const SERIF = "Georgia, 'Times New Roman', serif";

const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;');
const r4 = (n) => Math.round(n * 10000) / 10000;
const norm = (p) => ({ x: r4(p.x / W), y: r4(p.y / H), w: r4(p.w / W), h: r4(p.h / H) });

/** Rough text width for the system sans stack (average glyph about half an em). */
const textW = (s, fs, k = 0.46) => Math.ceil(s.length * fs * k);

function textRegion(id, label, x, baseline, fs, k = 0.46, extra = 0) {
  const w = textW(label, fs, k) + extra;
  return { id, kind: 'text', label, rect: { x: x - 8, y: baseline - fs * 0.98, w: w + 16, h: fs * 1.3 } };
}

const bg = (extra = '') =>
  `<rect width="${W}" height="${H}" fill="#fdfcf8"/><rect width="22" height="${H}" fill="${ACCENT}"/>${extra}`;

function slide1() {
  const regions = [];
  let svg = bg();
  const title = 'Gradient descent';
  svg += `<text id="r1" x="96" y="210" font-family="${SANS}" font-size="76" font-weight="700" fill="${INK}">${title}</text>`;
  regions.push(textRegion('r1', title, 96, 210, 76, 0.52));
  const sub = 'How a model learns by walking downhill';
  svg += `<text id="r2" x="96" y="268" font-family="${SANS}" font-size="32" fill="${MUTED}">${sub}</text>`;
  regions.push(textRegion('r2', sub, 96, 268, 32, 0.5));
  svg += `<rect x="96" y="304" width="220" height="5" rx="2" fill="${WARM}"/>`;
  const bullets = [
    ['r3', 'Goal: minimise the loss L(θ)', 430],
    ['r4', 'Follow the slope downhill', 510],
    ['r5', 'Repeat until the slope is flat', 590],
  ];
  for (const [id, t, y] of bullets) {
    svg += `<circle cx="112" cy="${y - 13}" r="7" fill="${ACCENT}"/>`;
    svg += `<text id="${id}" x="146" y="${y}" font-family="${SANS}" font-size="38" fill="${INK}">${esc(t)}</text>`;
    regions.push(textRegion(id, t, 146, y, 38));
  }
  svg += `<text x="96" y="672" font-family="${SANS}" font-size="20" fill="${MUTED}">Optimisation · Lecture 4</text>`;
  return { svg, regions };
}

function slide2() {
  const regions = [];
  let svg = bg();
  const title = 'The update rule';
  svg += `<text id="r1" x="96" y="150" font-family="${SANS}" font-size="60" font-weight="700" fill="${INK}">${title}</text>`;
  regions.push(textRegion('r1', title, 96, 150, 60, 0.52));
  // formula card
  const card = { x: 220, y: 210, w: 840, h: 170 };
  svg += `<rect id="r2" x="${card.x}" y="${card.y}" width="${card.w}" height="${card.h}" rx="18" fill="#f1efe6" stroke="${ACCENT}" stroke-width="3"/>`;
  svg += `<text x="640" y="322" text-anchor="middle" font-family="${SERIF}" font-style="italic" font-size="84" fill="${INK}">θ ← θ − η ∇L(θ)</text>`;
  regions.push({ id: 'r2', kind: 'text', label: 'θ ← θ − η ∇L(θ)', rect: card });
  const bullets = [
    ['r3', 'θ', 'the parameters we are tuning', 476],
    ['r4', 'η', 'learning rate: the size of each step', 548],
    ['r5', '∇L(θ)', 'gradient: points uphill', 620],
  ];
  for (const [id, sym, t, y] of bullets) {
    svg += `<text id="${id}" x="120" y="${y}" font-family="${SANS}" font-size="36" fill="${INK}"><tspan font-family="${SERIF}" font-style="italic" font-weight="700" fill="${ACCENT}">${sym}</tspan><tspan dx="22">${esc(t)}</tspan></text>`;
    regions.push(textRegion(id, `${sym}  ${t}`, 120, y, 36, 0.46, 40));
  }
  return { svg, regions };
}

// Loss curve geometry (pixels).
const cx = (u) => 480 + 340 * u;
const cy = (u) => 540 - 330 * u * u;

function slide3() {
  const regions = [];
  let svg = bg();
  const title = 'Rolling downhill';
  svg += `<text id="r1" x="96" y="130" font-family="${SANS}" font-size="60" font-weight="700" fill="${INK}">${title}</text>`;
  regions.push(textRegion('r1', title, 96, 130, 60, 0.52));

  // figure card, axes
  const fig = { x: 70, y: 170, w: 770, h: 500 };
  svg += `<rect id="r2" x="${fig.x}" y="${fig.y}" width="${fig.w}" height="${fig.h}" rx="18" fill="#f6f4ec" stroke="#d9d5c6" stroke-width="2"/>`;
  regions.push({ id: 'r2', kind: 'figure', label: 'Loss curve with a ball rolling toward the minimum', rect: fig });
  svg += `<g stroke="${MUTED}" stroke-width="2.5" fill="none"><path d="M140 200 V600 H820"/><path d="M132 212 L140 198 L148 212"/><path d="M806 592 L822 600 L806 608"/></g>`;
  svg += `<text x="160" y="214" font-family="${SERIF}" font-style="italic" font-size="26" fill="${MUTED}">L(θ)</text>`;
  svg += `<text x="800" y="640" font-family="${SERIF}" font-style="italic" font-size="26" fill="${MUTED}">θ</text>`;

  // curve
  const pts = [];
  for (let i = 0; i <= 40; i++) {
    const u = -1 + i / 20;
    pts.push(`${i === 0 ? 'M' : 'L'}${cx(u).toFixed(1)} ${cy(u).toFixed(1)}`);
  }
  svg += `<path id="r3" d="${pts.join(' ')}" fill="none" stroke="${ACCENT}" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/>`;
  regions.push({ id: 'r3', kind: 'part', label: 'Loss curve', rect: { x: 130, y: 200, w: 700, h: 350 } });

  // steps: arrows between successive ball positions
  const balls = [
    { x: 225, y: 318, r: 20 },
    { x: 320, y: 447, r: 14 },
    { x: 400, y: 510, r: 11 },
    { x: 447, y: 529, r: 8 },
  ];
  let arrows = '';
  for (let i = 0; i < balls.length - 1; i++) {
    const a = balls[i];
    const b = balls[i + 1];
    const mx = (a.x + b.x) / 2 + 22;
    const my = (a.y + b.y) / 2 - 38;
    arrows += `<path d="M${a.x + 16} ${a.y - 10} Q${mx} ${my} ${b.x - 4} ${b.y - b.r - 4}" fill="none" stroke="${WARM}" stroke-width="3.5" stroke-dasharray="9 7" stroke-linecap="round"/>`;
  }
  svg += `<g id="r6">${arrows}</g>`;
  regions.push({ id: 'r6', kind: 'part', label: 'Steps: large at first, then shrinking', rect: { x: 235, y: 300, w: 215, h: 225 } });
  for (let i = 1; i < balls.length; i++) {
    const b = balls[i];
    svg += `<circle cx="${b.x}" cy="${b.y}" r="${b.r}" fill="${WARM}" fill-opacity="0.35" stroke="${WARM}" stroke-width="2"/>`;
  }
  // start ball
  const b0 = balls[0];
  svg += `<g id="r4"><circle cx="${b0.x}" cy="${b0.y}" r="${b0.r}" fill="${WARM}" stroke="#8c3a0e" stroke-width="3"/><text x="${b0.x - 96}" y="${b0.y - 40}" font-family="${SANS}" font-size="22" fill="${WARM}" font-weight="700">start θ₀</text></g>`;
  regions.push({ id: 'r4', kind: 'part', label: 'Ball at the starting point', rect: { x: 125, y: 255, w: 135, h: 90 } });
  // minimum marker
  svg += `<g id="r5"><circle cx="480" cy="540" r="13" fill="none" stroke="${INK}" stroke-width="3.5"/><text x="480" y="580" text-anchor="middle" font-family="${SANS}" font-size="22" font-weight="700" fill="${INK}">minimum</text></g>`;
  regions.push({ id: 'r5', kind: 'part', label: 'Minimum of the loss', rect: { x: 420, y: 522, w: 120, h: 66 } });

  // right column
  const bullets = [
    ['r7', 'Big slope, big step', 300],
    ['r8', 'Flat slope, tiny step', 380],
    ['r9', 'Learning rate η: step scale', 460],
  ];
  for (const [id, t, y] of bullets) {
    svg += `<circle cx="872" cy="${y - 9}" r="6" fill="${ACCENT}"/>`;
    svg += `<text id="${id}" x="896" y="${y}" font-family="${SANS}" font-size="26" fill="${INK}">${esc(t)}</text>`;
    regions.push(textRegion(id, t, 896, y, 26));
  }
  return { svg, regions };
}

const slideBuilders = [slide1, slide2, slide3];
const slides = slideBuilders.map((fn, i) => {
  const { svg, regions } = fn();
  const doc = `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">${svg}</svg>\n`;
  return {
    index: i + 1,
    doc,
    page: {
      index: i + 1,
      image_url: `slides/slide-${i + 1}.svg`,
      width: W,
      height: H,
      regions: regions.map((r) => ({ id: r.id, kind: r.kind, label: r.label, rect: norm(r.rect) })),
    },
  };
});
const region = (slide, id) => {
  const r = slides[slide - 1].page.regions.find((x) => x.id === id);
  if (!r) throw new Error(`no region ${slide}/${id}`);
  return r;
};

// ------------------------------------------------------------------------------------------
// Transcript: [t0_s, t1_s, text]
// ------------------------------------------------------------------------------------------

const script = [
  [0.8, 5.6, "Okay, welcome back. Today we're talking about gradient descent, which is how almost every model gets trained."],
  [6.2, 11.4, 'The idea is simple: we have a loss function, L of theta, that tells us how wrong the model is.'],
  [12.0, 17.2, 'Our goal is to make that loss as small as we can by adjusting the parameters, theta.'],
  [17.8, 22.6, 'And we do that by following the slope downhill, and repeating until the slope is flat.'],
  [24.0, 28.5, "So let's write down the update rule. This is the heart of it."],
  [29.0, 35.2, 'Theta gets replaced by theta plus eta times the gradient of L at theta.'],
  [36.0, 41.0, "Sorry, no. That's a minus. We want to go down the slope, so it's minus eta times the gradient."],
  [41.8, 46.5, "If you add it you'd climb uphill and the loss would grow. Minus is what makes it descent."],
  [47.5, 52.5, 'Eta is the learning rate. It controls how big a step we take each time.'],
  [53.0, 58.0, 'The gradient, nabla L, is just the vector of partial derivatives. It points uphill.'],
  [58.6, 62.6, "And theta is whatever we're tuning: weights, biases, everything."],
  [70.5, 75.5, "Now a picture. Here's the loss as a curve, with theta along the bottom."],
  [76.2, 82.0, 'Say we start with the ball way up on the left. The slope there is steep.'],
  [82.8, 88.6, 'So the gradient is large, and we take a big step to the right, downhill.'],
  [89.4, 94.8, 'As we get closer to the bottom the slope flattens, so the steps get smaller on their own.'],
  [95.6, 100.5, 'That flat spot at the bottom is the minimum, where the gradient is zero.'],
  [101.4, 107.0, 'Now what if eta is too big? You overshoot the minimum and bounce to the other side.'],
  [107.8, 113.8, 'Too big and it can even diverge. The loss gets bigger each step instead of smaller.'],
  [114.5, 120.0, 'Too small, and you crawl. It converges, but it takes forever.'],
  [120.8, 126.0, 'So choosing the learning rate is a real trade-off. Typical values are around point zero zero one.'],
  [127.0, 132.5, 'In practice we stop when the gradient is close to zero, or after a fixed number of steps.'],
  [133.5, 138.5, 'To sum up: compute the gradient, step against it, scaled by the learning rate, repeat.'],
  [139.2, 144.0, "Next time we'll look at stochastic gradient descent, where we estimate the gradient from a small batch."],
  [144.8, 148.8, "That's what makes this practical on huge data sets. Okay, any questions?"],
  [149.5, 152.5, 'No? Great. See you on Thursday.'],
];

const segments = script.map(([a, b, text], i) => {
  const t0 = Math.round(a * 1000);
  const t1 = Math.round(b * 1000);
  const words = text.split(' ');
  const total = words.reduce((n, w) => n + w.length + 1, 0);
  let cursor = t0;
  const out = words.map((w, k) => {
    const share = ((w.length + 1) / total) * (t1 - t0);
    const w0 = cursor;
    cursor = k === words.length - 1 ? t1 : Math.round(cursor + share);
    return { w, t0_ms: w0, t1_ms: cursor };
  });
  return { id: `s${i + 1}`, t0_ms: t0, t1_ms: t1, text, lang: 'en', words: out };
});
const seg = (id) => {
  const s = segments.find((x) => x.id === id);
  if (!s) throw new Error(`no segment ${id}`);
  return s;
};

// ------------------------------------------------------------------------------------------
// Ops
// ------------------------------------------------------------------------------------------

const ops = [];
let tickN = 0;
let userN = 0;

/** One tick: all ops share tick_id, actor and t_emit_ms; src span comes from the cited segments. */
function tick(t, actor, cites, list) {
  const id = actor === 'user' ? `u${++userN}` : `t${++tickN}`;
  const spanOf = (ids) =>
    ids.length ? [Math.min(...ids.map((c) => seg(c).t0_ms)), Math.max(...ids.map((c) => seg(c).t1_ms))] : [null, null];
  const tickSpan = spanOf(cites);
  for (const [type, payload, own] of list) {
    // `own === null` forces a null span (housekeeping ops that cite nothing); ops with a `src`
    // list get exactly the span of that list; others (annotations) get the tick span.
    const [a, b] = own === null ? [null, null] : payload.src ? spanOf(payload.src) : tickSpan;
    ops.push({
      seq: ops.length + 1,
      session_id: SESSION_ID,
      tick_id: id,
      actor,
      t_emit_ms: t,
      src_t0_ms: a,
      src_t1_ms: b,
      type,
      payload,
    });
  }
}

const ins = (id, after, kind, depth, text, src, slide) => ['block.insert', { id, after, kind, depth, text, src, slide }];
const upd = (id, text, reason, src) => ['block.update', { id, text, reason, src }];
const ann = (id, slide, style, regionId, note) => [
  'slide.annotate',
  { id, slide, style, rects: [region(slide, regionId).rect], region: regionId, quote: null, note },
];
const none = (op) => [op[0], op[1], null];

// slide 1
tick(0, 'user', [], [['slide.set', { slide: 1, source: 'user' }]]);
tick(10400, 'agent_fast', ['s1'], [ins('b1', null, 'h1', 0, 'Gradient descent', ['s1'], 1)]);
tick(15200, 'agent_fast', ['s2'], [
  ins('b2', 'b1', 'bullet', 1, 'Loss $L(\\theta)$ = how wrong the model is', ['s2'], 1),
  ann('a1', 1, 'highlight', 'r3', 'b2'),
]);
tick(21200, 'agent_fast', ['s3'], [ins('b3', 'b2', 'bullet', 1, 'Goal: shrink the loss by tuning parameters $\\theta$', ['s3'], 1)]);
tick(25400, 'agent_fast', ['s4'], [
  ins('b4', 'b3', 'bullet', 1, 'Method: step downhill along the slope, repeat', ['s4'], 1),
  ann('a2', 1, 'underline', 'r4', 'b4'),
]);

// slide 2
tick(28500, 'user', [], [['slide.set', { slide: 2, source: 'user' }]]);
tick(33200, 'agent_fast', ['s5'], [ins('b5', 'b4', 'h2', 0, 'Update rule', ['s5'], 2)]);
tick(38000, 'agent_fast', ['s6'], [
  ins('b6', 'b5', 'formula', 1, '$\\theta \\leftarrow \\theta + \\eta \\nabla L(\\theta)$', ['s6'], 2),
  ann('a3', 2, 'highlight', 'r2', 'b6'),
]);
tick(47200, 'agent_fast', ['s7', 's8'], [
  upd('b6', '$\\theta \\leftarrow \\theta - \\eta \\nabla L(\\theta)$', 'teacher_correction', ['s7']),
  ins('b8', 'b6', 'callout', 1, 'Watch the sign: plus climbs uphill, minus descends', ['s8'], 2),
]);
tick(56500, 'agent_fast', ['s9'], [
  ins('b7', 'b8', 'definition', 1, '**Learning rate** $\\eta$: how big a step we take each time', ['s9'], 2),
  ann('a4', 2, 'circle', 'r4', 'b7'),
]);
tick(63400, 'agent_fast', ['s10'], [
  ins('b9', 'b7', 'bullet', 1, 'Gradient $\\nabla L$ = vector of partial derivatives, points uphill', ['s10'], 2),
  ann('a5', 2, 'highlight', 'r5', 'b9'),
]);
tick(69000, 'agent_fast', ['s11'], [
  ins('b10', 'b9', 'bullet', 1, '$\\theta$ = all tunable parameters (weights, biases)', ['s11'], 2),
  ann('a6', 2, 'highlight', 'r3', 'b10'),
  none(['slide.annotation.remove', { id: 'a5' }]),
]);

// slide 3
tick(70000, 'user', [], [['slide.set', { slide: 3, source: 'user' }]]);
tick(78500, 'agent_slow', [], [
  none(['section.close', { heading_id: 'b1', summary: 'Gradient descent minimises a loss by repeatedly stepping downhill' }]),
  none(['block.status', { ids: ['b1', 'b2', 'b3', 'b4'], status: 'frozen' }]),
]);
tick(83600, 'agent_fast', ['s12', 's13'], [
  ins('b11', 'b10', 'h2', 0, 'Loss as a landscape', ['s12'], 3),
  ins('b12', 'b11', 'example', 1, 'Start high on the left: slope is steep, first step is large', ['s13'], 3),
  ann('a7', 3, 'circle', 'r4', 'b12'),
]);
tick(95600, 'agent_fast', ['s14', 's15'], [
  ins('b13', 'b12', 'bullet', 1, 'Steep slope → large gradient → big step downhill', ['s14'], 3),
  ins('b14', 'b13', 'bullet', 1, 'Near the bottom the slope flattens, so steps shrink by themselves', ['s15'], 3),
  ann('a8', 3, 'highlight', 'r6', 'b13'),
]);
tick(99500, 'agent_slow', ['s14', 's15'], [
  [
    'diagram.upsert',
    {
      id: 'd1',
      after: 'b14',
      title: 'One training step, repeated',
      spec: {
        layout: 'LR',
        nodes: [
          { id: 'n1', label: 'Compute gradient' },
          { id: 'n2', label: 'Step against it (× η)' },
          { id: 'n3', label: 'Update θ' },
        ],
        edges: [
          { from: 'n1', to: 'n2', label: null },
          { from: 'n2', to: 'n3', label: null },
          { from: 'n3', to: 'n1', label: 'repeat' },
        ],
      },
      src: ['s14', 's15'],
      slide: 3,
    },
  ],
  none(['block.move', { id: 'b10', after: 'b8', depth: 1 }]),
]);
tick(109000, 'agent_fast', ['s16', 's17'], [
  ins('b15', 'b14', 'definition', 1, '**Minimum**: gradient is zero, the loss stops falling', ['s16'], 3),
  ins('b16', 'b15', 'bullet', 1, '$\\eta$ too large: overshoots the minimum and bounces across', ['s17'], 3),
  ann('a9', 3, 'circle', 'r5', 'b15'),
  ann('a10', 3, 'highlight', 'r9', 'b16'),
]);
tick(118000, 'agent_slow', [], [
  none(['section.close', { heading_id: 'b5', summary: 'The update rule: step against the gradient, scaled by the learning rate' }]),
  none(['block.status', { ids: ['b5', 'b6', 'b8', 'b10', 'b7', 'b9'], status: 'frozen' }]),
]);
tick(121500, 'agent_fast', ['s18', 's19'], [
  ins('b17', 'b16', 'bullet', 1, 'Too large can diverge: the loss grows every step', ['s18'], 3),
  ins('b18', 'b17', 'bullet', 1, 'Too small: very slow', ['s19'], 3),
]);
tick(130000, 'agent_fast', ['s20'], [
  upd('b18', 'Too small: still converges, but needs a huge number of steps', 'clarification', ['s20']),
  ins('b19', 'b18', 'callout', 1, 'Choosing $\\eta$ is a trade-off; typical values around 0.001', ['s20'], 3),
]);
tick(139500, 'agent_fast', ['s21', 's22'], [
  ins('b20', 'b19', 'bullet', 1, 'Stop when the gradient is about 0, or after a fixed number of steps', ['s21'], 3),
  ins('b21', 'b20', 'bullet', 1, 'Recipe: compute gradient, step against it scaled by $\\eta$, repeat', ['s22'], 3),
]);
tick(141000, 'agent_slow', ['s21', 's22'], [
  [
    'diagram.upsert',
    {
      id: 'd1',
      after: null,
      title: 'Gradient descent loop with stopping test',
      spec: {
        layout: 'TB',
        nodes: [
          { id: 'n1', label: 'Compute gradient' },
          { id: 'n2', label: 'Step: θ ← θ − η∇L' },
          { id: 'n4', label: 'Gradient ≈ 0?' },
          { id: 'n5', label: 'Stop' },
        ],
        edges: [
          { from: 'n1', to: 'n2', label: null },
          { from: 'n2', to: 'n4', label: null },
          { from: 'n4', to: 'n1', label: 'no' },
          { from: 'n4', to: 'n5', label: 'yes' },
        ],
      },
      src: ['s21', 's22'],
      slide: 3,
    },
  ],
]);
tick(147500, 'agent_fast', ['s22', 's23'], [
  ins('b22', 'd1', 'h2', 0, 'Next: stochastic gradient descent', ['s23'], 3),
  ins('b23', 'b22', 'bullet', 1, 'SGD estimates the gradient from a small batch', ['s23'], 3),
  ins('b24', 'b23', 'bullet', 1, 'Stop when gradient is about 0', ['s22'], 3),
]);
tick(152500, 'agent_slow', [], [
  none(['block.delete', { id: 'b24', reason: 'duplicate' }]),
]);

// ------------------------------------------------------------------------------------------
// Write
// ------------------------------------------------------------------------------------------

const manifest = {
  id: SESSION_ID,
  title: 'Gradient descent: a scripted mini-lecture',
  duration_ms: DURATION_MS,
  audio: null,
  slides: slides.map((s) => s.page),
};

mkdirSync(join(OUT, 'slides'), { recursive: true });
for (const s of slides) writeFileSync(join(OUT, 'slides', `slide-${s.index}.svg`), s.doc);
writeFileSync(join(OUT, 'session.json'), JSON.stringify(manifest, null, 2) + '\n');
const jsonl = (rows) => rows.map((r) => JSON.stringify(r)).join('\n') + '\n';
writeFileSync(join(OUT, 'transcript.jsonl'), jsonl(segments));
writeFileSync(join(OUT, 'ops.jsonl'), jsonl(ops));
console.log(`wrote ${slides.length} slides, ${segments.length} segments, ${ops.length} ops`);
