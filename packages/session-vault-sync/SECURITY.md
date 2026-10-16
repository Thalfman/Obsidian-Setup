# Security and privacy

## Security maintainer

Thomas Halfman (@Thalfman) is the designated security maintainer, responsible
for vulnerability triage and security fixes.

## Reporting a vulnerability

Report security issues privately to **thalfman22@outlook.com**. Include the
package version, operating system, a description of the impact, and a minimal
reproduction using synthetic data. Please do not attach real transcripts,
credentials, or private project information. Avoid public issue reports until
there has been an opportunity to assess and address the issue.

This project is an early release. No response-time or long-term support
commitment is currently offered. Security fixes will target the latest release.

## What this tool reads and writes

The runtime reads Claude Code JSONL transcripts and history from a local input
directory. It writes generated Markdown and state into a separate, explicitly
selected vault. It does not require credentials and does not make runtime
network requests. Installing dependencies or running package-manager commands
may use the network.

Generated notes can contain first-prompt excerpts, local filesystem paths,
project names, branch names, model and tool names, timestamps, and session
identifiers. These are potentially sensitive even when raw archives are off.
The summary formatter shortens text; it does **not** redact secrets.

Raw archives are disabled by default. Enabling `--archive` or `archive: true`
copies complete transcripts to gzip files. Gzip is compression, not encryption.
Transcripts may contain prompts, code, tool outputs, personal data, and secrets.

## Filesystem boundaries

- Keep the input and output directories separate. Source Claude data is read-only.
- Use a private vault on a trusted local filesystem, with access limited to the
  intended users. Avoid untrusted or collaboratively writable source/output
  paths. The program is not a sandbox and does not defend against a malicious
  process racing filesystem checks.
- Do not rely on generated filenames or Markdown escaping to make untrusted
  transcript content safe to render in every plugin or application. Review
  content before exporting or rendering it with powerful third-party plugins.
- Automatic changes are limited to tool-managed output. Existing unmanaged
  notes are not an invitation to overwrite them. Preserve backups before
  adopting an existing vault or changing output conventions.
- Pruning is never automatic. Explicit `--prune-archive` can permanently delete
  managed archives older than the configured retention period. Only tracked
  archives whose current content matches the recorded SHA-256 are eligible;
  untracked or modified files are skipped and symlink paths are rejected. Keep
  backups and preview with `--dry-run`. Treat the archive manifest as trusted
  local state, not a tamper-proof security boundary.

## Git, backups, and syncing

A `.gitignore` rule is not a privacy guarantee. It does not remove files already
tracked by Git, prevent forced staging, control other repositories, or stop
Obsidian Sync, cloud drives, backup software, or plugins from uploading data.
Review your vault's sharing and sync settings. If you use Git, configure ignore
rules in that vault and inspect staged changes before committing. If a secret
has already been shared, revoke or rotate it through the issuing service;
adding an ignore rule does not undo disclosure.

The package does not configure encryption, backup retention, cloud-sync access,
or access controls for your vault. Those remain your responsibility.
