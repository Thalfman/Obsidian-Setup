---
type: reference
---
# Build Plan — MVP completion

The agent-executable work is **done and verified** (see "Completed" below). What
remains is **GUI-only setup** no agent can perform: installing the theme and
plugins inside the Obsidian desktop app. This file is the handoff.

Scope: "just finish MVP" — terminal in the vault + a board that starts empty and
only shows sessions you start here. Phases 3-5 (launch wiring, QuickAdd, archival
schedule, Activity board) are deferred and intentionally NOT in this plan.

## Resolved decisions
- **cc_link to CommandCenter:** decoupled. No linking in MVP. The field exists in
  the template but stays empty.
- **Sync cadence:** manual "Sync now" button is the default. The Task Scheduler
  entry is an optional human step, not required.

## Completed (agent-executable, verified this session)
- [x] Scoped sync: `allow` (vault path) + `since` (UTC floor). Board starts empty.
- [x] `--claude-dir` flag added for testability.
- [x] Idempotency fix: only the machine-owned region (above `## Notes`) is hashed,
      so user edits below the marker never trigger a rewrite. Verified:
      create → edit notes → skip → source change → update, note preserved.
- [x] Test suite `tests/test_sync.py` — 13 tests, all pass (`pytest tests/`).
- [x] Pre-commit data-boundary guard `.githooks/pre-commit`. Verified it blocks a
      staged `Sessions/` file and leaves HEAD unchanged.
- [x] `git config core.hooksPath .githooks` set in this repo.

Verification commands (re-runnable):
```
python -m pytest tests/ -q          # expect: 13 passed
python scripts/sync.py              # expect: created=0 until you work here
```

## Remaining: human GUI setup (no agent can do this)
Do these once, in order, inside Obsidian. Source of truth is README.md "Setup".

1. **Open vault:** Obsidian → Open folder as vault → `C:\Users\thalf\Desktop\Obsidian`.
2. **Theme:** Settings → Appearance → Manage → install **Minimal**. The accent and
   the `console` CSS snippet are already declared; just confirm both are enabled.
3. **Core plugin:** Settings → Core plugins → enable **Bases**.
4. **Community plugins** (Settings → Community plugins → Browse, install + enable):
   `templater-obsidian`, `terminal`, `open-in-terminal`, `obsidian-shellcommands`.
5. **polyipseity Terminal deps (Windows):** in a terminal run
   `pip install psutil==5.9.5 pywinctl==0.0.50 typing_extensions==4.7.1`,
   then in the plugin's profile settings set the Python executable and hit **Check**.
6. **Open in Terminal:** set terminal app to `wt.exe` or `powershell`; enable the
   **Open in Claude Code** command.
7. **Shell command:** add `python scripts/sync.py` named "Sync now", working dir =
   vault root; optionally bind a hotkey.

Done-criteria for the whole MVP: you can open a docked terminal in the vault, run
`claude`, run "Sync now", and see exactly that one session appear on the
`Dashboards/Sessions` board.

## Acceptance per remaining step
- After step 4: `community-plugins.json` plugins all show enabled, no load errors.
- After step 5: the polyipseity "Check" button reports Python OK.
- After step 7: running "Sync now" with no vault sessions yet leaves the board empty;
  after one `claude` session here, it shows exactly one row.
