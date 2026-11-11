from __future__ import annotations

import json
from pathlib import Path

import pytest

from live_notes_api.models import SessionManifest, TranscriptSegmentIn

ROOT = Path(__file__).resolve().parents[3]
GOLDEN_OPS = ROOT / "fixtures" / "protocol" / "golden-ops.jsonl"
GOLDEN_DOCS = ROOT / "fixtures" / "protocol" / "golden-documents.json"
TINY = Path(__file__).parent / "data" / "tiny"


@pytest.fixture
def manifest() -> SessionManifest:
    return SessionManifest.model_validate(json.loads((TINY / "session.json").read_text()))


def seg_in(t0: int, t1: int, text: str) -> TranscriptSegmentIn:
    return TranscriptSegmentIn(t0_ms=t0, t1_ms=t1, text=text, lang="en", words=[])


def words(n: int, prefix: str = "w") -> str:
    return " ".join(f"{prefix}{i}" for i in range(n))
