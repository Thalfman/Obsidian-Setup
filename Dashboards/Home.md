---
type: dashboard
cssclasses:
  - console-home
---
<span class="label">mission control</span>
# Console

> [!info] One window over your Claude Code sessions. Data is generated locally by `scripts/sync.py` and never leaves this machine. The board starts empty and fills only with sessions you start from this vault.

---

<span class="label">launch</span>
## Start or resume a session
- Open the docked **Terminal** (ribbon or command palette → *Terminal: Open terminal*), then:
  - `claude` — new session in this vault
  - `claude -c` — continue the last session
  - `claude -r` — pick a session to resume
- Or command palette → **Open in Claude Code** to launch in a chosen repo.

---

<span class="label">live now</span>
## Active sessions
```base
filters:
  and:
    - 'note.type == "session"'
    - 'status == "active"'
views:
  - type: table
    name: Active now
    order:
      - note.project
      - note.start
      - note.message_count
      - note.summary
    sort:
      - property: note.start
        direction: DESC
    limit: 25
```

---

<span class="label">boards</span>
## Drill in
- [[Sessions]] — active and recent, across this vault
- [[Projects]] — launch hubs, newest activity first
- [[Activity]] — effort and token rollup *(added by packet 01)*

---

<span class="label">sync</span>
## Refresh the board
- Command palette → **Sync now** (Shell commands), or run `python scripts/sync.py`.
- The board is not live; it reflects the last sync. Schedule it from the README for near-live updates.

---

<span class="label">setup</span>
## First time here?
Follow **[[GUI Setup Guide]]** — install the theme and plugins, then come back. Until plugins are installed, the embedded board above renders as plain code.
