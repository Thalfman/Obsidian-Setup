"""Adversarial regression tests use only synthetic files in pytest tmp_path."""
import builtins
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from session_vault_sync import sync
from test_sync import _make_fake_claude


def cli(vault, source, *args):
    return subprocess.run([sys.executable, '-m', 'session_vault_sync', '--vault', str(vault),
                           '--claude-dir', str(source), *args], text=True, capture_output=True)


def link(src, dest, directory=False):
    try:
        dest.symlink_to(src, target_is_directory=directory)
    except OSError:
        pytest.skip('symlink creation is unavailable')


@pytest.mark.parametrize('text', ['allow: null', 'allow: broad', 'allow: [""]', 'deny: false',
    'archive: "false"', 'active_minutes: -1', 'idle_factor: 0', 'retention_days: true',
    'unknown: 1', 'name_map: {x: 4}', 'since: 2026-01-01', '[a,b]', 'allow: ['])
def test_invalid_config_fails_closed(tmp_path, text):
    source = _make_fake_claude(tmp_path / 'source', '/synthetic/project', 'session')
    config = tmp_path / 'config.yaml'; config.write_text(text)
    vault = tmp_path / 'vault'
    result = cli(vault, source, '--config', str(config))
    assert result.returncode == 2, result.stderr
    assert not vault.exists()


def test_missing_explicit_config_fails_closed(tmp_path):
    assert sync.main(['--config', str(tmp_path / 'missing')]) == 2


def test_missing_yaml_does_not_ignore_config(tmp_path, monkeypatch):
    config = tmp_path / 'config.yaml'; config.write_text('allow: [specific]')
    original = builtins.__import__
    def no_yaml(name, *args, **kwargs):
        if name == 'yaml':
            raise ImportError('synthetic missing PyYAML')
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', no_yaml)
    with pytest.raises(ImportError):
        sync.load_config(config)


def test_explicit_vault_required_without_reading_default_history(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sync, 'build_history_index', lambda _: pytest.fail('history read'))
    assert sync.main([]) == 2
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('relation', ['equal', 'inside', 'parent'])
def test_source_vault_overlap_rejected(tmp_path, relation):
    source = tmp_path / 'source'; source.mkdir()
    vault = source if relation == 'equal' else source / 'vault' if relation == 'inside' else tmp_path
    result = cli(vault, source)
    assert result.returncode == 2
    assert 'overlap' in result.stderr
    assert not (vault / '_meta').exists()


def test_config_paths_relative_to_config_not_install_or_cwd(tmp_path):
    source = _make_fake_claude(tmp_path / 'source', '/synthetic/project', 'session')
    cfg = tmp_path / 'config.yaml'; cfg.write_text('claude_dir: source\nvault_dir: vault\n')
    result = subprocess.run([sys.executable, '-m', 'session_vault_sync', '--config', str(cfg)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert len(list((tmp_path / 'vault' / 'Sessions').glob('*.md'))) == 1


def test_project_and_session_injection_cannot_escape_or_create_markdown(tmp_path):
    source = _make_fake_claude(tmp_path / 'source', '/synthetic/project', 'session')
    file = next(source.glob('projects/*/*.jsonl'))
    records = [json.loads(line) for line in file.read_text().splitlines()]
    for record in records:
        record['sessionId'] = '../../evil\n## Notes\n![](https://invalid.example/x)'
        record['gitBranch'] = '`\n## Notes\n<img src="https://invalid.example/x">'
    file.write_text('\n'.join(json.dumps(rec) for rec in records))
    config = tmp_path / 'cfg.yaml'
    config.write_text('name_map:\n  project: "../../owned\\n## Notes\\n[[injected]]"\n')
    vault = tmp_path / 'vault'
    result = cli(vault, source, '--config', str(config), '--archive')
    assert result.returncode == 0, result.stderr
    assert not (tmp_path / 'owned').exists()
    for note in [*vault.glob('Sessions/*.md'), *vault.glob('Projects/*.md')]:
        text = note.read_text()
        fm = yaml.safe_load(text.split('---\n', 2)[1])
        assert fm['project'].startswith('../../owned')
        assert text.count('\n## Notes\n') == 1
        assert '<img' not in text.split('---\n', 2)[2] and '[[injected]]' not in text.split('---\n', 2)[2]


def test_duplicate_session_and_project_basenames_are_distinct(tmp_path):
    source = _make_fake_claude(tmp_path / 'source', '/a/same', 'duplicate-id')
    other = _make_fake_claude(tmp_path / 'other', '/b/same', 'duplicate-id')
    dest = source / 'projects' / 'another'; dest.mkdir()
    dest.joinpath('duplicate-id.jsonl').write_bytes(next(other.glob('projects/*/*.jsonl')).read_bytes())
    vault = tmp_path / 'vault'
    result = cli(vault, source, '--archive')
    assert result.returncode == 0, result.stderr
    assert len(list(vault.glob('Sessions/*.md'))) == 2
    assert len(list(vault.glob('Projects/*.md'))) == 2
    assert len(list(vault.glob('Archive/*/*.gz'))) == 2


@pytest.mark.parametrize('output', ['Sessions', 'Projects', 'Archive', '_meta'])
def test_symlink_output_directories_refused(tmp_path, output):
    source = _make_fake_claude(tmp_path / 'source', '/synthetic/project', 'session')
    vault = tmp_path / 'vault'; vault.mkdir()
    outside = tmp_path / 'outside'; outside.mkdir()
    link(outside, vault / output, True)
    assert cli(vault, source, '--archive').returncode == 2
    assert list(outside.iterdir()) == []


def test_source_file_symlink_refused(tmp_path):
    source = _make_fake_claude(tmp_path / 'source', '/synthetic/project', 'session')
    file = next(source.glob('projects/*/*.jsonl'))
    real = tmp_path / 'outside.jsonl'; file.rename(real)
    link(real, file)
    result = cli(tmp_path / 'vault', source)
    assert result.returncode == 2
    assert real.exists()


def test_source_and_histories_unchanged_with_archive_and_prune(tmp_path):
    source = _make_fake_claude(tmp_path / 'source', '/synthetic/project', 'session')
    before = {p.relative_to(source): (p.read_bytes(), p.stat().st_mtime_ns) for p in source.rglob('*') if p.is_file()}
    result = cli(tmp_path / 'vault', source, '--archive', '--prune-archive')
    assert result.returncode == 0, result.stderr
    after = {p.relative_to(source): (p.read_bytes(), p.stat().st_mtime_ns) for p in source.rglob('*') if p.is_file()}
    assert before == after


def test_dry_run_writes_nothing(tmp_path):
    source = _make_fake_claude(tmp_path / 'source', '/synthetic/project', 'session')
    vault = tmp_path / 'vault'
    result = cli(vault, source, '--dry-run', '--archive', '--prune-archive')
    assert result.returncode == 0, result.stderr
    assert not vault.exists()


def test_prune_keeps_untracked_and_modified_archives(tmp_path):
    source = tmp_path / 'source.jsonl'; source.write_text('synthetic')
    vault = tmp_path / 'vault'
    sync.archive_transcript(source, 'project', vault, False)
    archive = next(vault.glob('Archive/*/*.gz')); archive.write_bytes(b'user changed')
    untracked = archive.parent / 'untracked.jsonl.gz'; untracked.write_bytes(b'user file')
    for path in (archive, untracked): os.utime(path, (0, 0))
    assert sync.prune_archive(vault, 1, 1000000, False) == 0
    assert archive.read_bytes() == b'user changed' and untracked.exists()


def test_prune_rejects_archive_root_symlink(tmp_path):
    vault = tmp_path / 'vault'; vault.mkdir()
    outside = tmp_path / 'outside'; outside.mkdir()
    victim = outside / 'victim.jsonl.gz'; victim.write_bytes(b'keep')
    link(outside, vault / 'Archive', True)
    with pytest.raises(ValueError): sync.prune_archive(vault, 1, 1000000, False)
    assert victim.exists()


def test_unsafe_archive_manifest_rejected(tmp_path):
    vault = tmp_path / 'vault'; (vault / '_meta').mkdir(parents=True)
    (vault / '_meta' / 'archive-state.json').write_text('{"../../victim": {}}')
    with pytest.raises(ValueError): sync.prune_archive(vault, 1, 1000000, False)


def test_note_symlink_and_unmanaged_note_refused(tmp_path):
    outside = tmp_path / 'outside'; outside.write_text('do not touch')
    dest = tmp_path / 'note'; link(outside, dest)
    with pytest.raises(ValueError): sync.write_note(dest, 'body\n## Notes\n', False, {}, 'k')
    assert outside.read_text() == 'do not touch'
    dest.unlink(); dest.write_text('my note\n## Notes\n')
    with pytest.raises(ValueError): sync.write_note(dest, 'body\n## Notes\n', False, {}, 'k')


def test_deleted_generated_note_recreated(tmp_path):
    note = tmp_path / 'note.md'; state = {}; content = 'body\n## Notes\n'
    sync.write_note(note, content, False, state, 'k'); note.unlink()
    assert sync.write_note(note, content, False, state, 'k') == 'create'
    assert note.exists()


def test_yaml_controls_roundtrip():
    for text in ['line\nnext', '\x00\r\t"\\', '\u2028---\u2029', '!!python/object', 'emoji 😀', '\ud800']: 
        assert yaml.safe_load('value: ' + sync.yq(text))['value'] == text


def test_nonobject_records_and_malformed_fields_are_ignored(tmp_path):
    path = tmp_path / 'synthetic.jsonl'
    records = [None, [], 5, {'sessionId': {}, 'cwd': [], 'timestamp': '2026-01-01',
        'message': {'model': [], 'content': [{'type': 'tool_use', 'name': {}}],
                    'usage': {'output_tokens': float('nan')}}}]
    path.write_text('\n'.join(json.dumps(r) for r in records))
    parsed = sync.parse_session(path)
    assert parsed['session_id'] == 'synthetic'
    assert parsed['tokens'] == 0


def test_lock_prevents_other_writer(tmp_path):
    vault = tmp_path / 'vault'
    with sync.vault_lock(vault, False):
        with pytest.raises(ValueError):
            with sync.vault_lock(vault, False): pass
    assert not (vault / '_meta' / 'session-vault-sync.lock').exists()


def test_invalid_since_and_negative_minutes_fail_before_writes(tmp_path):
    source = tmp_path / 'source'; source.mkdir()
    vault = tmp_path / 'vault'
    for args in [('--since', 'nope'), ('--minutes', '-1')]:
        assert cli(vault, source, *args).returncode == 2
        assert not vault.exists()
