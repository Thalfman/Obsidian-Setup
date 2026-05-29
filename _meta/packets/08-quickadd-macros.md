---
type: reference
---
# Packet 08 — QuickAdd launcher macros (GUI)

**Bucket:** GUI · **Wave:** D · **Depends on:** plugins installed · **Exclusive:**
GUI only — config lives in git-ignored `data.json`, nothing tracked to edit.

Read `_meta/packets/README.md` header first.

## Goal
One keystroke to (a) "Sync now" and (b) "New session here": create a session note
from the Templater template and optionally fire the terminal launch.

## Why GUI only
QuickAdd macros and Shell commands store their definitions in
`.obsidian/plugins/*/data.json` (git-ignored). There is no tracked file to author;
this is configuration inside Obsidian. The agent's role is to document the exact
macro recipe; the human builds it.

## Recipe (human, in Obsidian)
1. **Sync now** (Shell commands): command `python scripts/sync.py`, working dir =
   vault root, name "Sync now", bind a hotkey. (Already in the GUI Setup Guide.)
2. **New session** (QuickAdd → Macro):
   - Template choice: `Templates/Session.md` → new note in `Sessions/`.
   - Then a step that runs the Open-in-Claude-Code command (chain via QuickAdd's
     "run command" step) so creating the note also launches the session.
3. Add both to the command palette and bind hotkeys.

## Acceptance
- A single hotkey creates a session note and launches `claude`.
- "Sync now" refreshes the board on demand.

## Do NOT touch
Nothing tracked. Do not attempt to commit `data.json` (it is and must stay
git-ignored). Report the recipe; the human executes.
