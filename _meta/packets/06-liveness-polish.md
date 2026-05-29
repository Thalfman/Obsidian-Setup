---
type: reference
---
# Packet 06 — Liveness polish

**Bucket:** sync.py · **Wave:** B (after 05) · **Depends on:** 04 ·
**Exclusive:** owns `scripts/sync.py` + `tests/` for its turn.

Read `_meta/packets/README.md` header first. Rebase on 05 before starting.

## Problem
`status: active` is derived purely from the session file's mtime within
`active_minutes`. A stalled session (left open, no longer doing work) still reads
"active", which is misleading on the board.

## Change
1. Add a `last_synced` timestamp (UTC) to each session note's frontmatter, set at
   render time, so the board can show data freshness.
2. Refine liveness: keep mtime-based `active`, but add an `idle` tier — `active`
   if mtime within `active_minutes`; `idle` if within `active_minutes * 4`;
   `done` otherwise. Make the multiplier a config key `idle_factor` (default 4).
3. Update `render_session_note()` and the schema doc in `_meta/Console Spec.md`?
   No — Console Spec is dispatcher-owned. Note the schema delta in your output
   instead.

## Tests
- A session with a fresh mtime → `active`; mid-range → `idle`; old → `done`.
  (Inject mtime by setting the file's mtime in the test, or by parameterizing the
  status helper so it takes `now` and `mtime` directly — prefer extracting a pure
  `liveness(now, mtime, active_minutes, idle_factor)` helper and testing that.)
- `last_synced` line is present and parseable.

## Verification
```
python -m pytest tests/ -q
```

## Acceptance
- Three-tier liveness, pure-function tested.
- `last_synced` present on every generated note.
- `pytest tests/` green.

## Do NOT touch
README, Console Spec (report deltas), Dashboards (the `.base` may later add an
`idle` filter — that's packet 01's call, not yours), css, data folders.
