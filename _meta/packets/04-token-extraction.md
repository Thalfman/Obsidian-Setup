---
type: reference
---
# Packet 04 — Token extraction

**Bucket:** sync.py · **Wave:** A · **Depends on:** none · **Exclusive:** owns
`scripts/sync.py` and `tests/test_sync.py` for its wave.

Read `_meta/packets/README.md` header first.

## Problem
`scripts/sync.py` writes `tokens: 0` into every session note. The field exists in
the schema but is never populated, so Activity (packet 01) can't sum real usage.

## Investigate first (do not assume the shape)
Claude Code assistant records *may* carry usage under `message.usage`. Confirm
against a real transcript before coding:
```
python -c "import json,glob,os;[print(json.dumps(json.loads(l).get('message',{}).get('usage'))) for f in glob.glob(os.path.expanduser('~/.claude/projects/*/*.jsonl'))[:1] for l in open(f,encoding='utf-8') if '\"usage\"' in l][:5]"
```
Expected keys if present: `input_tokens`, `output_tokens`,
`cache_read_input_tokens`, `cache_creation_input_tokens`. If the key is absent or
named differently, adjust and note it in your output.

## Change
In `parse_session()`, accumulate a `tokens` total across assistant records:
`input_tokens + output_tokens + cache_read_input_tokens + cache_creation_input_tokens`,
defaulting any missing sub-key to 0. Add `tokens` to the returned dict. In
`render_session_note()`, emit `tokens: {s['tokens']}` (integer, unquoted) instead
of the current hardcoded `tokens: 0`. If no usage data exists in any record, emit
`tokens: 0` (graceful).

## Tests (add to tests/test_sync.py)
- Unit: a synthetic session with two assistant records carrying `usage` sums to
  the expected integer.
- Unit: a session with no `usage` anywhere yields `tokens: 0`.
- Extend the existing end-to-end test to assert the rendered `tokens:` line.

## Verification
```
python -m pytest tests/ -q          # all pass, including new token tests
```

## Acceptance
- `tokens` reflects real summed usage when present, `0` when absent.
- No change to any other frontmatter field.
- `pytest tests/` green.

## Do NOT touch
`Dashboards/*`, `console.css`, README, Console Spec, any data folder.
