---
type: reference
---
# Packet 07 — Launch wiring (GUI, human-assisted)

**Bucket:** GUI · **Wave:** D · **Depends on:** plugins installed (GUI Setup
Guide done) · **Exclusive:** human-assisted; an agent can draft `hotkeys.json`
but cannot install plugins or click in-app.

Read `_meta/packets/README.md` header first.

## Goal
From a `Projects/` hub or a `Sessions` board row, open a terminal at that repo's
path and start/resume Claude — without leaving Obsidian.

## Why this is mostly GUI
Open in Terminal and polyipseity Terminal store their config in
`.obsidian/plugins/<id>/data.json`, which is git-ignored (holds absolute local
paths). So the wiring lives in app settings, not tracked files.

## Steps (human, in Obsidian)
1. Open in Terminal → settings → confirm terminal app (`wt.exe` or `powershell`)
   and enable **Open in Claude Code**.
2. From a `Projects/<repo>.md` hub, the `path:` field is the working dir. Use the
   command palette **Open in Claude Code** while that note is active, or configure
   the plugin to use the note's `path` property if supported by the installed
   version (verify in its settings; if unsupported, document the manual path step).
3. polyipseity Terminal: create a profile whose startup command is `claude` so the
   docked terminal can resume with `claude -r`.

## Agent-doable slice
Draft `.obsidian/hotkeys.json` binding (a) Open in Claude Code and (b) Terminal:
open integrated terminal, to ergonomic chords. These ids only resolve once plugins
are installed, so the agent writes the file and the human verifies bindings appear.

## Acceptance
- One action from a hub/row opens a terminal at the repo path and runs `claude`.
- Hotkeys appear bound in Settings → Hotkeys after plugins are installed.

## Do NOT touch
`scripts/`, `tests/`, `Dashboards/*.base`, data folders. (`hotkeys.json` is the
only tracked file in scope.)
