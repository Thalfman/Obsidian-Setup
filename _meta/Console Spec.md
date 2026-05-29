---
type: reference
---
# Mission Control — Console Spec

Living spec for this vault. Approved plan, condensed to what was built.

## Purpose
Live operator console for running many Claude Code sessions at once: see every
session across every repo, launch/resume into any project, and keep a terminal
in the window. Distinct from the private CommandCenter vault, which holds durable
knowledge and post-hoc logs. This vault is present-tense and apparatus-only;
link out to CommandCenter via a session/hub `cc_link` for durable notes.

## Data boundary (load-bearing)
Remote is **public**. Enforcement = `.gitignore` + sync.py writing only into
ignored folders (`Sessions/`, `Projects/`, `Archive/`, `_meta/sync-config.yaml`,
`_meta/sync-state.json`). Dashboards are zero-data `.base` query files. All
parsing/summaries are local; no cloud model ever sees transcript content.

## Components
- **sync.py** — read-only indexer/archiver over `~/.claude`. The spine: the
  cross-repo board exists only because this runs.
- **Bases dashboards** — `Sessions.base` (active + recent), `Projects.base`
  (launch hubs), plus an embedded "live sessions" block in `Home.md`.
- **Terminal plugins** — polyipseity `terminal` (docked) + `open-in-terminal`
  (launch `claude` in a repo). `obsidian-shellcommands` runs the sync button.
- **Templater** — `Session.md`, `Project.md` for manual notes.
- **console.css** — Swiss/Bauhaus dark, single signal-orange accent (#FF5A1F),
  monospace IDs/dates; theme-agnostic over Minimal.

## Frontmatter
Session: type, project, session_id, path, start, end, message_count, tools,
status, summary, branch, cc_version, model, tokens, source.
Project: type, project, path, status, last_session, session_count,
key_commands, cc_link.
Body convention: everything below `## Notes` is human-owned and never rewritten.

## Verified (this session, early 2026)
- Bases: core since Obsidian 1.9; view sort = `[{property, direction: ASC|DESC}]`;
  `order` = columns; refs `file.x`, `note.x`/bare, `formula.x`.
- Plugin ids/versions: templater-obsidian 2.20.5, terminal 3.25.0,
  open-in-terminal 0.9.1, obsidian-shellcommands 0.23.0.
- Claude Code storage: `~/.claude/projects/<hash>/<uuid>.jsonl`,
  `~/.claude/history.jsonl` (epoch-ms `timestamp`, `display`, `sessionId`).
  Session records carry cwd, gitBranch, version, timestamp (ISO), type.

## Status / roadmap
- [x] Phase 0 boundary + skeleton + theme/CSS
- [x] Phase 1 templates
- [x] Phase 2 sync.py + dashboards
- [ ] Phase 3 launch wiring from board rows + liveness polish
- [ ] Phase 4 QuickAdd launcher macro + hotkeys
- [ ] Phase 5 archival schedule + Activity.base + Style Settings

## Open questions
- Auto-link session notes to a CommandCenter hub (`cc_link`), or stay decoupled?
- Sync cadence: 15 min scheduled vs manual-only.
