"""Replay a stored session through a SessionActor on a virtual clock and write a new stored
session. Seed of the evaluation harness.

    uv run python -m live_notes_api.replay <session_dir> --model heuristic --out <dir>
"""

from __future__ import annotations

import argparse
import asyncio
import shutil
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .actor import ActorConfig, SessionActor
from .model import NoteModel, make_model
from .models import SessionManifest, TranscriptSegment, TranscriptSegmentIn, parse_op
from .store import DirectorySessionStore

POLL_STEP_MS = 1000


@dataclass
class ReplaySummary:
    session_id: str
    ticks: int = 0
    ops_by_type: Counter[str] = field(default_factory=Counter)
    rejected_by_reason: Counter[str] = field(default_factory=Counter)

    @property
    def ops_accepted(self) -> int:
        return sum(self.ops_by_type.values())

    @property
    def ops_rejected(self) -> int:
        return sum(self.rejected_by_reason.values())

    def format(self) -> str:
        lines = [
            f"session {self.session_id}",
            f"ticks: {self.ticks}",
            f"ops accepted: {self.ops_accepted}",
            *(f"  {t}: {n}" for t, n in sorted(self.ops_by_type.items())),
            f"ops rejected: {self.ops_rejected}",
            *(f"  {r}: {n}" for r, n in sorted(self.rejected_by_reason.items())),
        ]
        return "\n".join(lines)


def _read_input(
    src: Path,
) -> tuple[SessionManifest, list[TranscriptSegment], list[tuple[int, int]]]:
    manifest = SessionManifest.model_validate_json((src / "session.json").read_text())
    segs = [
        TranscriptSegment.model_validate_json(line)
        for line in (src / "transcript.jsonl").read_text().splitlines()
        if line.strip()
    ]
    slides: list[tuple[int, int]] = []  # (t_ms, slide)
    ops_path = src / "ops.jsonl"
    if ops_path.exists():
        for line in ops_path.read_text().splitlines():
            if not line.strip():
                continue
            op = parse_op(line)
            if op.type == "slide.set" and op.actor == "user":
                slides.append((op.t_emit_ms, op.payload.slide))
    return manifest, segs, slides


async def replay_session(
    src: Path,
    out: Path,
    model: NoteModel,
    config: ActorConfig | None = None,
) -> ReplaySummary:
    manifest, segs, slides = _read_input(src)
    if out.exists() and any(out.iterdir()):
        raise FileExistsError(f"output directory {out} is not empty")
    store = DirectorySessionStore.create_at(out, manifest)
    if (src / "slides").is_dir():
        shutil.copytree(src / "slides", out / "slides", dirs_exist_ok=True)

    now = {"t": 0}
    actor = SessionActor(store, model, lambda: now["t"], config, autopoll=False)
    await actor.start()

    # (time, order, kind, payload); slide flips sort before a segment that ends at the same time.
    events: list[tuple[int, int, str, object]] = [(t, 0, "slide", s) for t, s in slides]
    events += [(s.t1_ms, 1, "seg", s) for s in segs]
    events.sort(key=lambda e: (e[0], e[1]))

    async def advance_to(t: int) -> None:
        while now["t"] + POLL_STEP_MS < t:
            now["t"] += POLL_STEP_MS
            await actor.poll()
        now["t"] = max(now["t"], t)

    for t, _, kind, payload in events:
        await advance_to(t)
        if kind == "slide":
            await actor.set_slide(int(payload), t)  # type: ignore[arg-type]
        else:
            seg = payload  # type: ignore[assignment]
            await actor.add_segment(
                TranscriptSegmentIn(
                    t0_ms=seg.t0_ms, t1_ms=seg.t1_ms, text=seg.text, lang=seg.lang, words=seg.words
                )
            )
        await actor.poll()
    end_t = max(manifest.duration_ms, now["t"])
    await advance_to(end_t)
    await actor.end(end_t)

    summary = ReplaySummary(manifest.id, ticks=len(actor.ticks))
    for op in actor.ops:
        if op.actor != "user":
            summary.ops_by_type[op.type] += 1
    for tr in actor.ticks:
        for r in tr.rejections:
            summary.rejected_by_reason[r.code] += 1
    if actor.errors:
        print("tick errors:", *actor.errors, sep="\n  ", file=sys.stderr)
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="live_notes_api.replay", description=__doc__)
    ap.add_argument("session_dir", type=Path)
    ap.add_argument("--model", default="heuristic")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    summary = asyncio.run(replay_session(args.session_dir, args.out, make_model(args.model)))
    print(summary.format())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
