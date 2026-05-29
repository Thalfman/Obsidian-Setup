---
type: reference
---
# Packet 03 — Dev tooling + CI

**Bucket:** new files · **Wave:** A · **Depends on:** none · **Exclusive:** none
(all new files).

Read `_meta/packets/README.md` header first.

## Goal
Make the test suite trivially runnable and gate it in CI on the public repo.

## Change
1. `requirements-dev.txt` — pin `pytest` and `pyyaml` (the two dev deps;
   `sync.py` itself is stdlib-only at runtime).
2. `tests/conftest.py` — ensure `scripts/` is importable (it already is via the
   test's sys.path insert; consolidate that here so individual tests don't repeat
   it). Add a fixture that builds a synthetic `~/.claude` (factor out the
   `_make_fake_claude` helper if clean to do so).
3. `.github/workflows/test.yml` — on push and pull_request: checkout, setup
   Python 3.12, `pip install -r requirements-dev.txt`, `pytest tests/ -q`.
   The tests use synthetic dirs only, so CI never sees real `~/.claude` data —
   confirm no test reads the real home dir.

## Data-boundary note
CI runs on a public repo. The workflow must not echo or upload anything from a
real `~/.claude`. Tests already isolate via tmp dirs; keep it that way.

## Verification
```
pip install -r requirements-dev.txt
python -m pytest tests/ -q
```
Then push the branch and confirm the Action runs green (human-visible in GitHub).

## Acceptance
- `pip install -r requirements-dev.txt && pytest tests/` works from a clean venv.
- The workflow file is valid and the Action passes on push.

## Do NOT touch
`scripts/sync.py` logic (you may import it), `Dashboards/`, css, README, Console
Spec, data folders.
