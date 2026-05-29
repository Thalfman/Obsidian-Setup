---
type: reference
---
# Fan-out dispatch index

Self-contained work packets for completing the full roadmap. Each packet is
designed to hand to one agent with no further design decisions. Read this header
first, then the packet.

## NON-NEGOTIABLE header (every agent, every packet)

1. **Data boundary.** The remote is PUBLIC. Never run an unscoped `sync.py`
   (always rely on the scoped `_meta/sync-config.yaml`). Never `git add` anything
   under `Sessions/`, `Projects/`, `Archive/`, or `_meta/sync-config.yaml` /
   `sync-state.json`. A pre-commit hook (`.githooks/pre-commit`, enabled via
   `git config core.hooksPath .githooks`) enforces this — do not bypass it with
   `--no-verify`.
2. **Green bar before done.** `python -m pytest tests/ -q` must pass. If your
   packet adds behavior to `sync.py`, it must also add tests.
3. **Branch.** Never commit to `main`. Work on `feat/console-mvp` (current) or an
   isolated worktree per the wave rules below.
4. **Scope discipline.** Touch only the files your packet lists. Respect each
   packet's "Do NOT touch" list. README.md and `_meta/Console Spec.md` are owned
   by the dispatcher only — propose edits in your packet's output, do not write them.
5. **Verify, don't assert.** Quote the actual command output that proves acceptance.

## Packets

| # | Packet | Bucket | Wave | Depends on | Primary files | Exclusive? |
|---|--------|--------|------|-----------|---------------|-----------|
| 04 | Token extraction | sync.py | A | — | `scripts/sync.py`, `tests/test_sync.py` | sync.py owner |
| 05 | Archival + retention | sync.py | B | 04 | `scripts/sync.py`, `tests/test_sync.py` | sync.py owner |
| 06 | Liveness polish | sync.py | B | 04 | `scripts/sync.py`, `tests/test_sync.py` | sync.py owner |
| 01 | Activity board | new file | C | 04 (for tokens) | `Dashboards/Activity.base` | none |
| 02 | Style Settings | css | A | — | `.obsidian/snippets/console.css` | css owner |
| 03 | Dev tooling + CI | new files | A | — | `requirements-dev.txt`, `tests/conftest.py`, `.github/workflows/test.yml` | none |
| 07 | Launch wiring | GUI | D | plugins installed | `.obsidian/hotkeys.json` + GUI | human-assisted |
| 08 | QuickAdd macros | GUI | D | plugins installed | GUI only (`data.json` git-ignored) | human-assisted |

## Wave plan (how to fan out)

- **Wave A — fully parallel, zero collisions:** packets **02, 03, 04**. Different
  files. Dispatch all three at once. (04 owns `scripts/sync.py` + `tests/`.)
- **Wave B — serialized on sync.py:** **05** then **06**, after 04 merges. These
  collide with 04 and each other on `scripts/sync.py`. One agent sequentially, OR
  isolated worktrees merged in order 04 → 05 → 06.
- **Wave C — after 04 lands:** **01** (Activity board). The `.base` file collides
  with nothing, but its token column is empty until 04 populates `tokens`.
- **Wave D — GUI, human or human-assisted:** **07, 08**, after the plugins from
  the GUI Setup Guide are installed. An agent can draft `hotkeys.json` but the
  commands only exist post-install, so acceptance is in-app.

Critical path: 04 → 05 → 06 (one file). Everything else parallelizes around it.

## Definition of done (whole roadmap)

`pytest tests/` green; Activity board renders; Style Settings toggles appear in
Obsidian; CI runs on push; launch + QuickAdd commands work in-app; no data file
ever tracked (`git ls-files` shows nothing under the boundary paths).
