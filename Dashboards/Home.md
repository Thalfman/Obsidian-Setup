---
type: dashboard
cssclasses:
  - console-home
---
> [!info] Mission Control — one window over every Claude Code session. Data is generated locally by `scripts/sync.py` and never leaves this machine.

## Boards
- [[Sessions]] — active and recent sessions across every repo
- [[Projects]] — repo launch hubs, newest activity first

## Launch
- Command palette -> **Open in Terminal: Open in Claude Code** to start `claude` in a repo.
- Or open the docked **Terminal** view (polyipseity) and run `claude -r` to resume.

## Sync
- Run **Shell commands: Sync now** (or `python scripts/sync.py`) to refresh the boards.
- Dry run: `python scripts/sync.py --dry-run`. Archive transcripts: `--archive`.

## Live sessions
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
