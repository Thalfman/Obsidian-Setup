---
type: dashboard
cssclasses:
  - console-home
---
<span class="label">setup</span>
# GUI Setup Guide

Everything an agent cannot do for you, in order. ~15 minutes. Do it once. Each
step has a "you'll know it worked when" check.

> [!warning] Data boundary
> This vault's GitHub remote is **public**. Never commit anything under
> `Sessions/`, `Projects/`, `Archive/`, or `_meta/sync-config.yaml`. A pre-commit
> hook blocks it, but enable the hook first (step 0).

---

<span class="label">step 0</span>
## Enable the safety hook
In a terminal at the vault root:
```
git config core.hooksPath .githooks
```
**Worked when:** staging a file under `Sessions/` and trying to commit is refused.

---

<span class="label">step 1</span>
## Open the vault
Obsidian → **Open folder as vault** → `C:\Users\thalf\Desktop\Obsidian`.
Trust the author prompt if shown (needed for community plugins).
**Worked when:** the file list shows `Dashboards`, `Templates`, `scripts`.

---

<span class="label">step 2</span>
## Theme + look
Settings → **Appearance** → Manage themes → search **Minimal** → Install → Use.
Then scroll to **CSS snippets**, refresh, and confirm **console** is toggled on.
The orange accent is already set.
**Worked when:** the UI is dark with an orange accent and tight spacing.

---

<span class="label">step 3</span>
## Enable Bases (core)
Settings → **Core plugins** → toggle **Bases** on.
**Worked when:** opening `Dashboards/Sessions` shows a table view (empty is fine),
not raw code.

---

<span class="label">step 4</span>
## Install community plugins
Settings → **Community plugins** → turn on community plugins → **Browse**, then
install AND enable each:

| Search for | Why |
| --- | --- |
| Templater | session/project note templates |
| Terminal | docked terminal inside the vault (polyipseity) |
| Open in Terminal | launch `claude` in a repo |
| Shell commands | the "Sync now" button |
| Style Settings | accent/density toggles *(after packet 02)* |

**Worked when:** all show **Enabled** with no error notices.

---

<span class="label">step 5</span>
## Terminal Python deps (Windows, for the docked Terminal)
In a terminal:
```
pip install psutil==5.9.5 pywinctl==0.0.50 typing_extensions==4.7.1
```
Then Settings → **Terminal** → profile settings → set the Python executable →
click **Check**.
**Worked when:** the Check reports Python OK, and *Terminal: Open terminal* opens
a working shell docked in the vault.

---

<span class="label">step 6</span>
## Wire launch + sync
- **Open in Terminal** settings: terminal app = `wt.exe` or `powershell`; enable
  **Open in Claude Code**.
- **Shell commands**: add command `python scripts/sync.py`, name it **Sync now**,
  working dir = vault root. Optionally bind a hotkey (Settings → Hotkeys).
**Worked when:** running *Sync now* prints a summary and the board refreshes.

---

<span class="label">step 7</span>
## Confirm "starts empty"
The board should be empty until you work here. If you set up days after the
scaffold, bump the floor so prior days don't show:
```
(Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm")
```
Put that value in `_meta/sync-config.yaml` under `since:` (UTC).
**Worked when:** *Sync now* yields `created=0` before your first session here.

---

<span class="label">daily</span>
## Then, day to day
1. [[Home]] → docked Terminal → `claude`.
2. Work.
3. *Sync now* → your session appears on [[Sessions]].

> [!note] Optional: near-live board
> Schedule the sync every 15 min — see **README.md → Schedule it**.
