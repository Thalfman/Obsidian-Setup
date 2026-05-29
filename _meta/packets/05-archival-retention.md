---
type: reference
---
# Packet 05 — Archival tests + retention

**Bucket:** sync.py · **Wave:** B (after 04 merges) · **Depends on:** 04 ·
**Exclusive:** owns `scripts/sync.py` + `tests/` for its turn in the wave.

Read `_meta/packets/README.md` header first. Rebase on 04 before starting.

## Problem
`archive_transcript()` exists and gzips raw transcripts into `Archive/`, but has
zero test coverage and no retention/prune logic. Claude Code prunes old sessions
over time; archival must reliably run before that, and old archives should be
prunable.

## Change
1. **Tests** for current `archive_transcript()`: archiving creates
   `Archive/<slug>/<uuid>.jsonl.gz`; re-archiving an unchanged source is a no-op
   (returns False); a newer source re-archives. Use the synthetic `~/.claude`
   pattern already in `tests/test_sync.py` with `--archive`.
2. **Retention prune** (opt-in): add a `--prune-archive` flag and a
   `retention_days` config key (already present in the example config). When set,
   delete `Archive/**/*.jsonl.gz` whose mtime is older than `retention_days`.
   Read-only on `~/.claude` still holds — prune only touches `Archive/`. Log how
   many were pruned. Add a test that an old gz is pruned and a recent one is kept.
3. Keep it idempotent and within the data boundary (Archive/ is git-ignored).

## Verification
```
python -m pytest tests/ -q
python scripts/sync.py --archive --dry-run      # reports planned archives, writes nothing
```

## Acceptance
- Archival has tests; retention prune works and is tested.
- Prune never touches `~/.claude` or anything outside `Archive/`.
- `pytest tests/` green.

## Do NOT touch
Token logic from 04 beyond rebasing; `Dashboards/*`, css, README, Console Spec.
