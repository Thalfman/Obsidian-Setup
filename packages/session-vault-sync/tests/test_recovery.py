"""Crash recovery and safety regressions using synthetic temporary files only."""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from session_vault_sync import sync


OLD_NOTE = '---\ntype: session\nstatus: "idle"\n---\nold body\n\n## Notes\n\n'
NEW_NOTE = '---\ntype: session\nstatus: "done"\n---\nnew body\n\n## Notes\n\n'


def _state(vault):
    path = vault / "_meta" / "sync-state.json"
    return sync.PersistentState(path, sync.load_state(path))


def _source(root, name="a"):
    path = root / "projects" / "synthetic" / f"{name}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "sessionId": name,
        "cwd": "/synthetic/demo",
        "timestamp": "2026-01-01T00:00:00Z",
        "type": "user",
    }) + "\n", encoding="utf-8")
    return path


def _archive_path(vault, source):
    digest = hashlib.sha256(str(source.absolute()).encode()).hexdigest()
    return vault / "Archive" / "demo" / f"{digest}.jsonl.gz"


def test_late_collision_does_not_orphan_earlier_notes(tmp_path, capsys):
    source_root, vault = tmp_path / "source", tmp_path / "vault"
    _source(source_root, "a")
    second = _source(source_root, "b")
    digest = hashlib.sha256(second.relative_to(source_root).as_posix().encode()).hexdigest()
    collision = vault / "Sessions" / f"2026-01-01-demo-{digest}.md"
    collision.parent.mkdir(parents=True)
    collision.write_text("unmanaged synthetic content", encoding="utf-8")
    argv = ["--claude-dir", str(source_root), "--vault", str(vault)]

    assert sync.main(argv) == 2
    assert "unmanaged note" in capsys.readouterr().err
    assert collision.read_text(encoding="utf-8") == "unmanaged synthetic content"
    persisted = sync.load_state(vault / "_meta" / "sync-state.json")
    assert len(persisted) == 1

    collision.unlink()
    assert sync.main(argv) == 0
    assert len(list((vault / "Sessions").glob("*.md"))) == 2
    assert len(list((vault / "Projects").glob("*.md"))) == 1
    assert all(not entry.get("pending") for entry in sync.load_state(vault / "_meta" / "sync-state.json").values())


@pytest.mark.parametrize("existing", [False, True], ids=["create", "update"])
def test_note_recovers_when_replacement_fails(tmp_path, monkeypatch, existing):
    vault = tmp_path / "vault"
    target = vault / "Sessions" / "synthetic.md"
    if existing:
        sync.write_note(target, OLD_NOTE, False, _state(vault), "session:a", 1)
        target.write_text(target.read_text(encoding="utf-8") + "human annotation\n", encoding="utf-8")
    before = target.read_bytes() if existing else None
    real_write = sync.atomic_write

    def fail_target(path, text):
        if path == target:
            raise OSError("synthetic replacement failure")
        return real_write(path, text)

    monkeypatch.setattr(sync, "atomic_write", fail_target)
    with pytest.raises(OSError, match="synthetic replacement failure"):
        sync.write_note(target, NEW_NOTE, False, _state(vault), "session:a", 2)
    pending = _state(vault)
    assert pending["session:a"]["pending"] is True
    if existing:
        assert target.read_bytes() == before
    else:
        assert not target.exists()

    monkeypatch.setattr(sync, "atomic_write", real_write)
    assert sync.write_note(target, NEW_NOTE, False, pending, "session:a", 2) == ("update" if existing else "create")
    assert "new body" in target.read_text(encoding="utf-8")
    if existing:
        assert target.read_text(encoding="utf-8").endswith("human annotation\n")
    assert not _state(vault)["session:a"].get("pending")


def test_note_recovers_after_output_but_before_completion_state(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    target = vault / "Sessions" / "synthetic.md"
    state_path = vault / "_meta" / "sync-state.json"
    real_write = sync.atomic_write
    state_writes = 0

    def fail_completion(path, text):
        nonlocal state_writes
        if path == state_path:
            state_writes += 1
            if state_writes == 2:
                raise OSError("synthetic completion failure")
        return real_write(path, text)

    monkeypatch.setattr(sync, "atomic_write", fail_completion)
    with pytest.raises(OSError, match="synthetic completion failure"):
        sync.write_note(target, NEW_NOTE, False, _state(vault), "session:a", 2)
    assert target.read_text(encoding="utf-8") == NEW_NOTE
    assert sync.load_state(state_path)["session:a"]["pending"] is True

    target.write_text(NEW_NOTE + "annotation after interruption\n", encoding="utf-8")
    monkeypatch.setattr(sync, "atomic_write", real_write)
    sync.write_note(target, NEW_NOTE, False, _state(vault), "session:a", 2)
    assert target.read_text(encoding="utf-8").endswith("annotation after interruption\n")
    assert not sync.load_state(state_path)["session:a"].get("pending")


@pytest.mark.parametrize("existing", [False, True], ids=["create", "update"])
def test_archive_recovers_when_replacement_fails(tmp_path, monkeypatch, existing):
    source = _source(tmp_path / "source")
    vault = tmp_path / "vault"
    dest = _archive_path(vault, source)
    if existing:
        assert sync.archive_transcript(source, "demo", vault, False)
        before = dest.read_bytes()
        source.write_text(source.read_text(encoding="utf-8") + '{"synthetic":"updated"}\n', encoding="utf-8")
    real_replace = sync.os.replace

    def fail_archive(src, dst):
        if Path(dst) == dest:
            raise OSError("synthetic archive replacement failure")
        return real_replace(src, dst)

    monkeypatch.setattr(sync.os, "replace", fail_archive)
    with pytest.raises(OSError, match="synthetic archive replacement failure"):
        sync.archive_transcript(source, "demo", vault, False)
    manifest = sync.load_state(vault / "_meta" / "archive-state.json")
    entry = next(iter(manifest.values()))
    if existing:
        assert dest.read_bytes() == before
        assert entry["previous_sha256"] == hashlib.sha256(before).hexdigest()
    else:
        assert not dest.exists()

    monkeypatch.setattr(sync.os, "replace", real_replace)
    assert sync.archive_transcript(source, "demo", vault, False)
    assert gzip.decompress(dest.read_bytes()) == source.read_bytes()
    entry = next(iter(sync.load_state(vault / "_meta" / "archive-state.json").values()))
    assert entry["sha256"] == sync.file_digest(dest)
    assert "previous_sha256" not in entry
    assert not list(dest.parent.glob(".session-sync-*"))


def test_archive_recovers_after_replacement_before_manifest_completion(tmp_path, monkeypatch):
    source = _source(tmp_path / "source")
    vault = tmp_path / "vault"
    dest = _archive_path(vault, source)
    manifest_path = vault / "_meta" / "archive-state.json"
    real_write = sync.atomic_write
    manifest_writes = 0

    def fail_completion(path, text):
        nonlocal manifest_writes
        if path == manifest_path:
            manifest_writes += 1
            if manifest_writes == 2:
                raise OSError("synthetic archive completion failure")
        return real_write(path, text)

    monkeypatch.setattr(sync, "atomic_write", fail_completion)
    with pytest.raises(OSError, match="synthetic archive completion failure"):
        sync.archive_transcript(source, "demo", vault, False)
    assert gzip.decompress(dest.read_bytes()) == source.read_bytes()
    monkeypatch.setattr(sync, "atomic_write", real_write)
    assert sync.archive_transcript(source, "demo", vault, False) is False
    entry = next(iter(sync.load_state(manifest_path).values()))
    assert entry["sha256"] == sync.file_digest(dest)
    assert "previous_sha256" not in entry


@pytest.mark.parametrize("value", [
    "emoji \U0001f600",
    "astral \U00010437 music \U0001d11e",
    "Unicode \u00e9\u4e2d\u2028line\u2029paragraph",
    'quotes " slash \\ newline\n\tcontrol\x01',
])
def test_yaml_escaped_scalars_round_trip_unicode(value):
    assert yaml.safe_load(sync.yq(value)) == value


@pytest.mark.parametrize("from_config", [False, True], ids=["cli", "config"])
def test_empty_since_is_rejected_without_writes(tmp_path, capsys, from_config):
    source_root, vault = tmp_path / "source", tmp_path / "vault"
    _source(source_root)
    argv = ["--claude-dir", str(source_root), "--vault", str(vault)]
    if from_config:
        config = tmp_path / "config.yaml"
        config.write_text('since: ""\n', encoding="utf-8")
        argv += ["--config", str(config)]
    else:
        argv += ["--since", ""]
    assert sync.main(argv) == 2
    assert "since must be" in capsys.readouterr().err
    assert not vault.exists()


def test_reparse_attribute_is_rejected_without_junction_api(tmp_path, monkeypatch):
    target = tmp_path / "synthetic-junction"
    target.mkdir()
    original_lstat = Path.lstat
    reparse_flag = 0x400
    monkeypatch.setattr(sync.stat, "FILE_ATTRIBUTE_REPARSE_POINT", reparse_flag, raising=False)
    monkeypatch.setattr(Path, "is_junction", lambda self: False, raising=False)

    def synthetic_lstat(self, *args, **kwargs):
        result = original_lstat(self, *args, **kwargs)
        if self == target:
            return SimpleNamespace(st_file_attributes=reparse_flag, st_mode=result.st_mode)
        return result

    monkeypatch.setattr(Path, "lstat", synthetic_lstat)
    with pytest.raises(ValueError, match="symlink/junction"):
        sync.check_path(target / "not-created.md")


def test_config_filename_expands_home_without_reading_real_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    config = tmp_path / "synthetic.yaml"
    config.write_text('active_minutes: 7\n', encoding="utf-8")
    assert sync.load_config(Path("~/synthetic.yaml"))["active_minutes"] == 7


@pytest.mark.parametrize("value", [10**400, float("inf"), float("nan"), -1, True])
def test_invalid_usage_numbers_do_not_overflow(value):
    assert sync.token_sum({"input_tokens": value, "output_tokens": 7}) == 7


def test_huge_history_timestamp_does_not_abort_valid_records(tmp_path):
    source_root = tmp_path / "source"
    source_root.mkdir()
    records = [
        {"sessionId": "bad", "display": "ignore this", "timestamp": 10**400},
        {"sessionId": "good", "display": "synthetic first prompt", "timestamp": 1234},
    ]
    (source_root / "history.jsonl").write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")
    assert sync.build_history_index(source_root) == {"good": "synthetic first prompt"}


@pytest.mark.parametrize("value", ["0001-01-01T00:00:00+01:00", "9999-12-31T23:59:59-01:00"])
def test_timestamp_utc_overflow_is_ignored(value):
    assert sync.parse_ts(value) is None
