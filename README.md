# Obsidian Mission Control

A keyboard-driven Obsidian vault that acts as a live operator console for Claude
Code: one window over every session across every repo, a terminal docked inside
the vault, and one-command launch/resume into any project.

This repo is **public and apparatus-only**. It contains the *system* (skeleton,
templates, dashboards, CSS, the sync script) and never the data. All session
content is generated locally into git-ignored folders and stays on disk.

**The board starts empty and only shows sessions you start from this vault.**
You run `claude` from a terminal inside the vault; Claude Code records it under
`~/.claude`; the sync script copies just those sessions in. Existing work in your
other repos never appears, because `sync-config.yaml` scopes the sync to this
vault's path and to sessions starting after a setup timestamp. See "Sync script"
below.

## What's tracked vs local

| Tracked (public) | Local only (git-ignored) |
| --- | --- |
| `Dashboards/*.base`, `Home.md` | `Sessions/`, `Projects/`, `Archive/` |
| `Templates/`, `scripts/sync.py` | `_meta/sync-config.yaml`, `_meta/sync-state.json` |
| `.obsidian/*.json`, `snippets/console.css` | `.obsidian/plugins/`, `.obsidian/themes/` |
| `_meta/sync-config.example.yaml`, `_meta/Console Spec.md` | `.obsidian/workspace*`, `cache` |

The `.base` dashboards are query files with zero data; they build the repo and
session lists at render time, so no project name or job number is ever written
into a tracked file.

## Setup (Windows)

1. **Open the vault.** Obsidian -> Open folder as vault -> this folder.
2. **Theme.** Settings -> Appearance -> install **Minimal**. The `console`
   snippet (Settings -> Appearance -> CSS snippets) and the orange accent are
   already declared in `.obsidian/appearance.json`.
3. **Enable Bases** (core): Settings -> Core plugins -> Bases.
4. **Community plugins** (declared in `community-plugins.json`; install each):
   - `templater-obsidian` (Templater) — note templates
   - `terminal` (polyipseity) — docked terminal inside the vault
   - `open-in-terminal` (Feng6611) — launch `claude` in a repo
   - `obsidian-shellcommands` (Shell commands) — the "Sync now" button
5. **polyipseity Terminal deps** (Windows): install Python 3.9+ then
   `pip3 install psutil==5.9.5 pywinctl==0.0.50 typing_extensions==4.7.1`.
   In the plugin's profile settings, set the Python executable and hit **Check**.
6. **Open in Terminal:** set the terminal app to `wt.exe` or `powershell`, and
   enable the **Open in Claude Code** command.
7. **Shell commands:** add a command `python scripts/sync.py` named "Sync now",
   working dir = vault root; optionally bind a hotkey.

## Daily use

- **See sessions:** open `Dashboards/Sessions` (active + recent).
- **Refresh:** run *Shell commands: Sync now*, or schedule it (below).
- **Jump in:** from a `Projects/` hub or `Sessions` row, *Open in Claude Code*
  (or `claude -r` in the docked terminal).

## Sync script

```
python scripts/sync.py [--dry-run] [--since YYYY-MM-DD] [--archive]
                       [--config PATH] [--vault PATH] [--minutes N]
```

Read-only over `~/.claude`. Writes one note per session to `Sessions/`, one hub
per repo to `Projects/`, optional gzipped transcripts to `Archive/`. Idempotent
(only changed sessions rewrite; the `## Notes` section is always preserved).
stdlib only; `pyyaml` optional but recommended here (it's what reads the scoping
config).

### Scope it to this vault, starting empty (recommended)

Copy `_meta/sync-config.example.yaml` to `_meta/sync-config.yaml` (git-ignored),
then set two keys so only sessions you start from this vault, from now on, appear:

- `allow:` the vault's absolute path, e.g. `'C:\Users\thalf\Desktop\Obsidian'`.
  Only sessions whose working directory matches show up.
- `since:` the current UTC moment, so existing and setup sessions stay hidden.
  Get it with `(Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm")`.

Install pyyaml so the config is honored: `pip install pyyaml`. Then
`python scripts/sync.py` produces zero notes until your next session here.

### Schedule it (near-live console)

Task Scheduler, every 15 minutes while you work:

```
schtasks /Create /SC MINUTE /MO 15 /TN "MC Session Sync" ^
  /TR "python \"%USERPROFILE%\Desktop\Obsidian\scripts\sync.py\" --archive"
```

## Data boundary

The remote is public. The boundary is `.gitignore` plus the script writing only
into ignored folders. Before pushing, `git status` should show no files under
`Sessions/`, `Projects/`, `Archive/`, or `sync-config.yaml`. A pre-commit guard
blocking those paths is recommended.
