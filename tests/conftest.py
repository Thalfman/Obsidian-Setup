"""Shared pytest fixtures for the sync.py suite.

Consolidates the `scripts/` import path so individual test modules don't each
repeat the sys.path dance, and offers a `fake_claude` factory that builds a
synthetic, throwaway ~/.claude tree under pytest's tmp_path.

Data boundary: every fixture writes only into tmp_path. No fixture or test ever
reads the real home dir, so CI on the public repo never sees real Claude data.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Make `import sync` resolve for every test module. conftest is imported before
# test collection, so this runs before any `import sync` at module top level.
SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


@pytest.fixture
def fake_claude(tmp_path):
    """Return a factory that builds a synthetic ~/.claude tree.

    The factory mirrors the real layout (`projects/<hash>/<uuid>.jsonl` plus a
    top-level `history.jsonl`) and returns the root dir to pass as
    `--claude-dir`. Optionally attaches a `usage` block to the assistant record
    so token-summation paths can be exercised. Build more than one by passing a
    distinct `root` per call.
    """

    def make(vault_path: str,
             uuid: str = "abcd1234-0000-0000-0000-000000000000",
             *,
             usage: dict | None = None,
             root: Path | None = None) -> Path:
        root = root or (tmp_path / "claude")
        proj = root / "projects" / "C--fake-hash"
        proj.mkdir(parents=True, exist_ok=True)
        assistant = {
            "type": "assistant", "sessionId": uuid,
            "timestamp": "2026-06-01T10:01:00.000Z",
            "message": {"role": "assistant", "model": "claude-opus-4-8",
                        "content": [{"type": "tool_use", "name": "Bash"}]},
        }
        if usage is not None:
            assistant["message"]["usage"] = usage
        records = [
            {"type": "user", "sessionId": uuid, "cwd": vault_path,
             "gitBranch": "main", "version": "2.1.156",
             "timestamp": "2026-06-01T10:00:00.000Z",
             "message": {"role": "user", "content": "hi"}},
            assistant,
        ]
        (proj / f"{uuid}.jsonl").write_text(
            "\n".join(json.dumps(r) for r in records), encoding="utf-8")
        hist = {"sessionId": uuid, "display": "do a thing",
                "project": vault_path, "timestamp": 1780000000000}
        (root / "history.jsonl").write_text(
            json.dumps(hist) + "\n", encoding="utf-8")
        return root

    return make
