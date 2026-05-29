"""Tests for scripts/sync.py — the session indexer.

Pure-stdlib unit tests plus one end-to-end run against a synthetic ~/.claude.
No network, no real Claude history touched. Run: pytest tests/
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import sync  # noqa: E402


# --------------------------------------------------------------------------- #
# scalar / formatting helpers
# --------------------------------------------------------------------------- #
def test_slugify_basic():
    assert sync.slugify("Make-Ready Poles") == "make-ready-poles"
    assert sync.slugify("a/b\\c") == "a-b-c"
    assert sync.slugify("") == "session"  # fallback


def test_yq_quotes_and_escapes_windows_paths():
    # backslashes must be doubled so YAML stays valid for C:\Users\...
    assert sync.yq("a\\b") == '"a\\\\b"'
    assert sync.yq('he said "hi"') == '"he said \\"hi\\""'
    assert sync.yq(True) == "true"
    assert sync.yq(3) == "3"


def test_yaml_list():
    assert sync.yaml_list([]) == "[]"
    assert sync.yaml_list(["Bash", "Read"]) == '["Bash", "Read"]'


def test_sanitize_summary_collapses_and_truncates():
    assert sync.sanitize_summary("  a\n\tb   c ") == "a b c"
    out = sync.sanitize_summary("x" * 200, limit=10)
    assert len(out) == 10 and out.endswith("…")


def test_parse_ts_normalizes_to_utc_minutes():
    assert sync.parse_ts("2026-06-01T10:00:00.000Z") == "2026-06-01T10:00"
    # +02:00 local -> 08:00 UTC
    assert sync.parse_ts("2026-06-01T10:00:00+02:00") == "2026-06-01T08:00"
    assert sync.parse_ts(None) is None
    assert sync.parse_ts("not-a-date") is None


# --------------------------------------------------------------------------- #
# scoping — the rule that keeps existing repos out of the board
# --------------------------------------------------------------------------- #
def test_included_deny_takes_precedence():
    assert sync.included("C:\\x\\.claude-mem\\y", [], [".claude-mem"]) is False


def test_included_allow_is_an_allowlist():
    allow = ["Desktop\\Obsidian"]
    assert sync.included("C:\\Users\\me\\Desktop\\Obsidian", allow, []) is True
    assert sync.included("C:\\Users\\me\\Desktop\\OtherRepo", allow, []) is False


def test_included_empty_allow_includes_everything():
    assert sync.included("C:\\anything", [], []) is True


# --------------------------------------------------------------------------- #
# managed-block preservation + idempotency
# --------------------------------------------------------------------------- #
def test_split_preserved():
    text = "---\nfm\n---\nbody\n## Notes\nmine\n"
    assert sync.split_preserved(text) == "## Notes\nmine\n"
    assert sync.split_preserved("no marker here") is None


def test_write_note_idempotent_and_preserves_user_notes(tmp_path):
    target = tmp_path / "Sessions" / "n.md"
    content = "---\ntype: session\n---\nbody\n\n## Notes\n\n"
    state: dict = {}

    a1 = sync.write_note(target, content, dry=False, state=state, key="k", source_mtime=1.0)
    assert a1 == "create"

    # user adds notes below the marker
    edited = target.read_text(encoding="utf-8") + "my private note\n"
    target.write_text(edited, encoding="utf-8")

    # same source -> skipped, and the user's note must survive
    a2 = sync.write_note(target, content, dry=False, state=state, key="k", source_mtime=1.0)
    assert a2 == "skip"
    assert "my private note" in target.read_text(encoding="utf-8")

    # source changed (new mtime) -> update, still preserving the note
    a3 = sync.write_note(target, content, dry=False, state=state, key="k", source_mtime=2.0)
    assert a3 == "update"
    assert "my private note" in target.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# end-to-end against a synthetic ~/.claude
# --------------------------------------------------------------------------- #
def _make_fake_claude(root: Path, vault_path: str, uuid: str) -> Path:
    proj = root / "projects" / "C--fake-hash"
    proj.mkdir(parents=True)
    records = [
        {"type": "user", "sessionId": uuid, "cwd": vault_path, "gitBranch": "main",
         "version": "2.1.156", "timestamp": "2026-06-01T10:00:00.000Z",
         "message": {"role": "user", "content": "hi"}},
        {"type": "assistant", "sessionId": uuid, "timestamp": "2026-06-01T10:01:00.000Z",
         "message": {"role": "assistant", "model": "claude-opus-4-8",
                     "content": [{"type": "tool_use", "name": "Bash"}]}},
    ]
    (proj / f"{uuid}.jsonl").write_text(
        "\n".join(json.dumps(r) for r in records), encoding="utf-8")
    hist = {"sessionId": uuid, "display": "do a thing",
            "project": vault_path, "timestamp": 1780000000000}
    (root / "history.jsonl").write_text(json.dumps(hist) + "\n", encoding="utf-8")
    return root


def _empty_config(tmp_path: Path) -> Path:
    """A config with no scoping, so tests don't inherit the repo's real
    sync-config.yaml (which is path- and date-scoped to the live vault)."""
    cfg = tmp_path / "empty.yaml"
    cfg.write_text("allow: []\ndeny: []\nsince: null\n", encoding="utf-8")
    return cfg


def _run(vault: Path, claude_dir: Path, *extra: str):
    cmd = [sys.executable, str(SCRIPTS / "sync.py"),
           "--vault", str(vault), "--claude-dir", str(claude_dir), *extra]
    return subprocess.run(cmd, capture_output=True, text=True, check=True)


def test_end_to_end_indexes_one_session(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    claude = _make_fake_claude(tmp_path / "claude", str(vault), "abcd1234-0000-0000-0000-000000000000")

    try:
        import yaml  # noqa: F401
    except ImportError:
        pytest.skip("pyyaml not installed; cannot neutralize repo config in subprocess")
    _run(vault, claude, "--config", str(_empty_config(tmp_path)), "--since", "2026-01-01")

    sessions = list((vault / "Sessions").glob("*.md"))
    projects = list((vault / "Projects").glob("*.md"))
    assert len(sessions) == 1
    assert len(projects) == 1

    fm = sessions[0].read_text(encoding="utf-8")
    assert 'session_id: "abcd1234-0000-0000-0000-000000000000"' in fm
    assert "message_count: 2" in fm
    assert 'tools: ["Bash"]' in fm
    assert 'summary: "do a thing"' in fm
    assert 'model: "claude-opus-4-8"' in fm
    assert "## Notes" in fm


def test_since_floor_excludes_older_sessions(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    claude = _make_fake_claude(tmp_path / "claude", str(vault), "abcd1234-0000-0000-0000-000000000000")

    try:
        import yaml  # noqa: F401
    except ImportError:
        pytest.skip("pyyaml not installed; cannot neutralize repo config in subprocess")
    # session starts 2026-06-01; a 2027 floor must exclude it -> empty board
    _run(vault, claude, "--config", str(_empty_config(tmp_path)), "--since", "2027-01-01")
    assert list((vault / "Sessions").glob("*.md")) == []


def test_allow_scope_excludes_other_paths(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    # session cwd is some OTHER repo, not the vault
    claude = _make_fake_claude(tmp_path / "claude", "C:\\some\\other\\repo",
                               "abcd1234-0000-0000-0000-000000000000")

    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("allow:\n  - 'Desktop\\\\Obsidian'\n", encoding="utf-8")
    try:
        import yaml  # noqa: F401
    except ImportError:
        pytest.skip("pyyaml not installed; allow-scoping is config-driven")

    _run(vault, claude, "--config", str(cfg))
    assert list((vault / "Sessions").glob("*.md")) == []


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
