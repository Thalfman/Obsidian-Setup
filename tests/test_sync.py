"""Tests for scripts/sync.py — the session indexer.

Pure-stdlib unit tests plus one end-to-end run against a synthetic ~/.claude.
No network, no real Claude history touched. Run: pytest tests/
"""

from __future__ import annotations

import gzip
import json
import os
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
# token accounting (packet 04)
# --------------------------------------------------------------------------- #
def _write_session(tmp_path: Path, records: list) -> Path:
    p = tmp_path / "session.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")
    return p


def test_token_sum_defaults_missing_and_ignores_non_dict():
    full = {"input_tokens": 6, "output_tokens": 151,
            "cache_read_input_tokens": 0, "cache_creation_input_tokens": 48257}
    assert sync.token_sum(full) == 48414
    assert sync.token_sum({"input_tokens": 5}) == 5  # absent keys default to 0
    assert sync.token_sum({"input_tokens": 5, "output_tokens": None}) == 5  # None -> 0
    assert sync.token_sum(None) == 0
    assert sync.token_sum({}) == 0


def test_parse_session_sums_usage_across_assistant_records(tmp_path):
    records = [
        {"type": "user", "sessionId": "s1", "cwd": "C:\\x",
         "timestamp": "2026-06-01T10:00:00.000Z",
         "message": {"role": "user", "content": "hi"}},
        {"type": "assistant", "sessionId": "s1", "timestamp": "2026-06-01T10:01:00.000Z",
         "message": {"role": "assistant", "model": "claude-opus-4-8",
                     "usage": {"input_tokens": 10, "output_tokens": 20,
                               "cache_read_input_tokens": 5,
                               "cache_creation_input_tokens": 3}}},
        {"type": "assistant", "sessionId": "s1", "timestamp": "2026-06-01T10:02:00.000Z",
         "message": {"role": "assistant",
                     "usage": {"input_tokens": 100, "output_tokens": 200}}},  # cache keys absent
    ]
    s = sync.parse_session(_write_session(tmp_path, records))
    assert s is not None
    assert s["tokens"] == 338  # (10+20+5+3) + (100+200+0+0)


def test_parse_session_tokens_zero_when_no_usage(tmp_path):
    records = [
        {"type": "user", "sessionId": "s2", "cwd": "C:\\x",
         "timestamp": "2026-06-01T10:00:00.000Z",
         "message": {"role": "user", "content": "hi"}},
        {"type": "assistant", "sessionId": "s2", "timestamp": "2026-06-01T10:01:00.000Z",
         "message": {"role": "assistant",
                     "content": [{"type": "text", "text": "no usage here"}]}},
    ]
    s = sync.parse_session(_write_session(tmp_path, records))
    assert s is not None
    assert s["tokens"] == 0


# --------------------------------------------------------------------------- #
# liveness (packet 06)
# --------------------------------------------------------------------------- #
def test_liveness_three_tiers_and_boundaries():
    am, factor, now, minute = 30, 4, 1_000_000.0, 60
    assert sync.liveness(now, now - 5 * minute, am, factor) == "active"
    assert sync.liveness(now, now - am * minute, am, factor) == "active"  # boundary, inclusive
    assert sync.liveness(now, now - 90 * minute, am, factor) == "idle"  # within 30*4=120 min
    assert sync.liveness(now, now - am * factor * minute, am, factor) == "idle"  # boundary
    assert sync.liveness(now, now - 200 * minute, am, factor) == "done"  # beyond 120 min


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


def test_last_synced_change_alone_does_not_force_rewrite(tmp_path):
    target = tmp_path / "Sessions" / "n.md"
    state: dict = {}
    c1 = '---\ntype: session\nlast_synced: "2026-01-01T00:00"\n---\nbody\n\n## Notes\n\n'
    assert sync.write_note(target, c1, dry=False, state=state, key="k", source_mtime=1.0) == "create"
    # only last_synced differs, same source mtime -> still skip (idempotent)
    c2 = '---\ntype: session\nlast_synced: "2099-12-31T23:59"\n---\nbody\n\n## Notes\n\n'
    assert sync.write_note(target, c2, dry=False, state=state, key="k", source_mtime=1.0) == "skip"
    # a real content change (status flip) with the same mtime -> update
    c3 = '---\ntype: session\nstatus: done\nlast_synced: "2099-12-31T23:59"\n---\nbody\n\n## Notes\n\n'
    assert sync.write_note(target, c3, dry=False, state=state, key="k", source_mtime=1.0) == "update"


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
                     "usage": {"input_tokens": 100, "output_tokens": 50,
                               "cache_read_input_tokens": 200,
                               "cache_creation_input_tokens": 300},
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
    assert "tokens: 650" in fm  # 100 + 50 + 200 + 300, unquoted integer
    assert "## Notes" in fm

    # last_synced is stamped at render time and must be parseable (packet 06)
    synced = next(l for l in fm.splitlines() if l.startswith("last_synced:"))
    assert sync.parse_ts(synced.split(":", 1)[1].strip().strip('"')) is not None


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


# --------------------------------------------------------------------------- #
# archival + retention (packet 05)
# --------------------------------------------------------------------------- #
def test_archive_transcript_creates_gz_and_roundtrips(tmp_path):
    src = tmp_path / "uuid1234.jsonl"
    src.write_text('{"hello": "world"}\n', encoding="utf-8")
    vault = tmp_path / "vault"
    assert sync.archive_transcript(src, "myproj", vault, dry=False) is True
    dest = vault / "Archive" / "myproj" / "uuid1234.jsonl.gz"
    assert dest.exists()
    with gzip.open(dest, "rt", encoding="utf-8") as fh:
        assert fh.read() == '{"hello": "world"}\n'


def test_archive_transcript_noop_when_unchanged(tmp_path):
    src = tmp_path / "u.jsonl"
    src.write_text("x", encoding="utf-8")
    vault = tmp_path / "vault"
    assert sync.archive_transcript(src, "p", vault, dry=False) is True
    dest = vault / "Archive" / "p" / "u.jsonl.gz"
    # pin the archive newer than the source so the mtime guard sees it current
    os.utime(src, (100.0, 100.0))
    os.utime(dest, (200.0, 200.0))
    assert sync.archive_transcript(src, "p", vault, dry=False) is False


def test_archive_transcript_rearchives_when_source_newer(tmp_path):
    src = tmp_path / "u.jsonl"
    src.write_text("x", encoding="utf-8")
    vault = tmp_path / "vault"
    sync.archive_transcript(src, "p", vault, dry=False)
    dest = vault / "Archive" / "p" / "u.jsonl.gz"
    os.utime(dest, (200.0, 200.0))
    os.utime(src, (300.0, 300.0))  # source edited after the archive was written
    assert sync.archive_transcript(src, "p", vault, dry=False) is True


def test_archive_transcript_dry_run_writes_nothing(tmp_path):
    src = tmp_path / "u.jsonl"
    src.write_text("x", encoding="utf-8")
    vault = tmp_path / "vault"
    assert sync.archive_transcript(src, "p", vault, dry=True) is True
    assert not (vault / "Archive").exists()


def test_end_to_end_archive_writes_gz(tmp_path, fake_claude):
    vault = tmp_path / "vault"
    vault.mkdir()
    uuid = "abcd1234-0000-0000-0000-000000000000"
    claude = fake_claude(str(vault), uuid)
    try:
        import yaml  # noqa: F401
    except ImportError:
        pytest.skip("pyyaml not installed; cannot neutralize repo config in subprocess")
    _run(vault, claude, "--config", str(_empty_config(tmp_path)),
         "--since", "2026-01-01", "--archive")
    gz = list((vault / "Archive").glob("**/*.jsonl.gz"))
    assert len(gz) == 1
    assert gz[0].name == f"{uuid}.jsonl.gz"


def test_prune_archive_removes_old_keeps_recent(tmp_path):
    vault = tmp_path / "vault"
    arch = vault / "Archive" / "proj"
    arch.mkdir(parents=True)
    old = arch / "old.jsonl.gz"
    old.write_bytes(b"old")
    recent = arch / "recent.jsonl.gz"
    recent.write_bytes(b"new")
    now = 1_000_000_000.0
    day = 86400
    os.utime(old, (now - 40 * day, now - 40 * day))
    os.utime(recent, (now - 5 * day, now - 5 * day))
    pruned = sync.prune_archive(vault, retention_days=30, now=now, dry=False)
    assert pruned == 1
    assert not old.exists()
    assert recent.exists()


def test_prune_archive_dry_run_keeps_files(tmp_path):
    vault = tmp_path / "vault"
    arch = vault / "Archive" / "proj"
    arch.mkdir(parents=True)
    old = arch / "old.jsonl.gz"
    old.write_bytes(b"old")
    os.utime(old, (1_000_000_000.0 - 99 * 86400,) * 2)
    assert sync.prune_archive(vault, retention_days=30, now=1_000_000_000.0, dry=True) == 1
    assert old.exists()  # reported but not deleted


def test_prune_archive_disabled_when_retention_nonpositive(tmp_path):
    vault = tmp_path / "vault"
    arch = vault / "Archive" / "proj"
    arch.mkdir(parents=True)
    old = arch / "old.jsonl.gz"
    old.write_bytes(b"old")
    os.utime(old, (0.0, 0.0))  # ancient
    assert sync.prune_archive(vault, retention_days=0, now=1_000_000_000.0, dry=False) == 0
    assert old.exists()


def test_prune_archive_missing_dir_is_safe(tmp_path):
    vault = tmp_path / "vault"  # no Archive directory at all
    assert sync.prune_archive(vault, retention_days=30, now=1.0, dry=False) == 0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
