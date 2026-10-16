# session-vault-sync

Turn local Claude Code sessions into Markdown session notes and project hubs,
with optional compressed transcript archives. Intended for a private Obsidian
vault, but the output is ordinary Markdown with YAML frontmatter.

This is an early, standalone extraction from
[Thalfman/Obsidian-Setup](https://github.com/Thalfman/Obsidian-Setup). It is not an
official Anthropic or Obsidian product. The commands below install this local
source checkout; they do not assume a published PyPI release.

## Requirements

- Python 3.10 or later
- Local Claude Code data, normally in `~/.claude`
- A separate private output directory you choose explicitly

PyYAML is the only runtime dependency. Parsing and summary generation happen
locally, without a cloud model or runtime network requests. Package installation
may download dependencies.

## Install from a local checkout

From the directory containing `pyproject.toml`:

```sh
python -m venv .venv
# macOS / Linux
. .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install .
session-vault-sync --help
```

## First run

Start with a preview against a private vault outside your Claude data directory:

```sh
session-vault-sync --vault /path/to/private-vault --dry-run
```

Review the destination and your vault's Git, backup, plugin, and cloud-sync
settings, then remove `--dry-run` to write notes:

```sh
session-vault-sync --vault /path/to/private-vault
```

The input directory defaults to `~/.claude`. To use a different input:

```sh
session-vault-sync --claude-dir /path/to/claude-data --vault /path/to/private-vault
```

A destination is required: pass `--vault`, or set `vault_dir` in an explicitly
selected config file. The tool does not choose an output directory from its
installation path. Input and output must remain separate.

## What it produces

- `Sessions/`: one generated Markdown note per session, containing project,
  timestamps, status, first-prompt summary, path, branch, model, message count,
  tool names, and token-usage totals where present in the source records
- `Projects/`: project hubs showing local project paths and session counts
- `_meta/sync-state.json`: local state used to avoid unnecessary note rewrites
- `Archive/`: compressed raw JSONL transcripts, only when explicitly enabled
- `_meta/archive-state.json`: records identifying archives managed by this tool

Session identity includes its source-relative path. Generated filenames use
hashes to distinguish sessions and projects that would otherwise collide, and
project hubs distinguish project paths with the same display name. Existing
unmanaged notes are not overwritten. This extraction may use different names
from the original in-vault script; back up your vault and preview before migrating.

The generated region above `## Notes` is managed by the tool. Put personal edits
below that marker; that tail is preserved when a managed note is updated. Changes
to generated content or freshness status can cause an update even when no new
messages arrived. Repeated runs with unchanged effective content skip note writes.

Freshness comes from the transcript file's modification time, not a live process
check: sessions are `active` inside the configured active window, `idle` through
that window multiplied by `idle_factor`, then `done`. These labels do not prove
that a Claude process is running or finished. Token totals are source-record
usage sums, not a billing estimate.

## Configuration

A configuration file is loaded **only** when passed with `--config`. It is a YAML
mapping. Paths in that file are relative to the config file's parent directory,
and `~` expands to your home directory. Relative command-line paths are relative
to the current working directory. CLI values take precedence where provided. Unknown keys and invalid value types
are rejected. Quote a configured `since` date (for example, `since: "2026-10-01"`)
to keep YAML from interpreting it as a date object.

Example `sync-config.yaml`:

```yaml
claude_dir: ~/.claude
vault_dir: ./private-vault
active_minutes: 30
idle_factor: 4
archive: false
retention_days: 30
since: null
name_map:
  example-repo: Example Project
allow: []
deny:
  - .claude-mem
  - observer-sessions
```

Run it with:

```sh
session-vault-sync --config /path/to/sync-config.yaml --dry-run
```

`allow` and `deny` match substrings in the session's recorded working-directory
path; deny matches take priority. `name_map` maps a project directory's basename
to a display name. These filters are conveniences, not a security boundary or
redaction system. Review your input and generated output before sharing either.

Use `--since` to include only sessions whose recorded start is on or after a date
or ISO datetime, and `--minutes` to change the active window:

```sh
session-vault-sync --vault /path/to/private-vault --since 2026-10-01 --minutes 15
```

The configuration keys `since` and `active_minutes` provide the corresponding
defaults. See `session-vault-sync --help` for the full command-line interface.

## Archives and retention

Raw transcript archiving is opt-in:

```sh
session-vault-sync --vault /path/to/private-vault --archive --dry-run
session-vault-sync --vault /path/to/private-vault --archive
```

Setting `archive: true` in an explicit config file also opts in for runs using
that file. Raw transcripts can contain secrets and private code. Gzip archives
are not encrypted. Keep them out of shared or published vaults.

Pruning is a separate, explicit action. It is **not** performed during a normal
sync or merely because `retention_days` is configured:

```sh
session-vault-sync --config /path/to/sync-config.yaml --prune-archive --dry-run
session-vault-sync --config /path/to/sync-config.yaml --prune-archive
```

Pruning deletes only eligible, tool-managed archives whose file modification time
is older than `retention_days` (default: 30). Their current SHA-256 must match the
archive manifest. Untracked
and modified archives are skipped; symlink paths are rejected. Archives from
older scripts are not automatically adopted for deletion. A retention value of
zero disables pruning. Deletions are permanent: retain backups and preview first.
Source Claude files are never pruned.

## Privacy and operational limits

Even without raw archives, notes can expose prompt excerpts, local paths, project
names, branch names, timestamps, and session identifiers. Summaries are not
secret-redacted. The tool makes no runtime network requests, but your vault's
sync services, backups, plugins, or Git workflow may upload its output.

The repository's `.gitignore` applies only inside this checkout. For a Git-managed
vault, consider equivalent rules in **that vault**:

```gitignore
/Sessions/
/Projects/
/Archive/
/_meta/
```

Ignore rules do not affect already tracked files, forced staging, backups, or
cloud sync. Review staged changes and access controls; do not treat `.gitignore`
as a confidentiality guarantee. See [SECURITY.md](SECURITY.md) for the threat
model and private vulnerability reporting contact.

Use trusted local input and output directories. Filesystem path checks do not
protect against a malicious process changing files concurrently. Avoid overlapping
sync runs, and make a backup before first use on an existing vault. A lock in
`_meta/session-vault-sync.lock` prevents overlapping writes. If a run is interrupted
and leaves a stale lock, verify that no sync process is still running before
manually removing that lock. Claude Code's transcript format can change; missing fields or unsupported records may produce
partial metadata. This tool does not install Obsidian plugins, create a dashboard,
start Claude sessions, or schedule background jobs.

## Development

From a local checkout, install the package and development tools:

```sh
python -m venv .venv
. .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -e '.[dev]'
python -m pytest
python -m build
python -m twine check dist/*
```

Tests use temporary directories and synthetic transcripts; they do not require
real Claude history or credentials. The GitHub Actions workflow runs tests and
checks built distributions. The commands above build local wheel and source
distributions only; they do not publish to PyPI or any repository.

For a clean-install smoke test, create another virtual environment, install the
wheel from `dist/`, and run `session-vault-sync --help`. A real sync should always
use explicit private input/output paths and start with `--dry-run`.

## License and provenance

MIT, copyright 2026 Thomas Halfman. See [LICENSE](LICENSE).
The original sync utility came from
[Thalfman/Obsidian-Setup](https://github.com/Thalfman/Obsidian-Setup); this package
extracts and hardens it for explicit, standalone use.
