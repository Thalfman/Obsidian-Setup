"""Mission Control session sync.

Read-only indexer + archiver. Parses Claude Code transcripts under ~/.claude
and writes one markdown note per session and one launch hub per repo into the
vault, where Obsidian Bases renders them as a live console.

Safety contract:
  * Everything under claude_dir is opened READ-ONLY. Never written, moved,
    or deleted.
  * All output lands in /Sessions, /Projects, /Archive, /_meta — every one of
    which is git-ignored, so this data never reaches the public remote.
  * All parsing and summarization is local. No network. No cloud model.
  * Idempotent: a note is rewritten only when its source changed, and only the
    region above the `## Notes` marker is touched.

Usage:
  python scripts/sync.py [--dry-run] [--since YYYY-MM-DD] [--archive]
                         [--config PATH] [--vault PATH] [--minutes N]

stdlib only. pyyaml is optional (used for the config file if present).
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path


def atomic_write(path: Path, text: str) -> None:
    """Write text to path atomically: temp file in the same dir, then os.replace.

    Guards against partial/interleaved files if a scheduled run overlaps a
    manual one.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)

NOTES_MARKER = "## Notes"

DEFAULTS = {
    "claude_dir": "~/.claude",
    # "." = the repo root (the folder containing scripts/). Relative paths are
    # resolved against the repo root; absolute paths are used as-is.
    "vault_dir": ".",
    "active_minutes": 30,
    "archive": False,
    "retention_days": 30,
    "name_map": {},
    "allow": [],
    "deny": [".claude-mem", "observer-sessions"],
    # Only index sessions that START on/after this ISO date or datetime
    # (e.g. "2026-05-30" or "2026-05-30T09:00"). None = no floor.
    "since": None,
}


# --------------------------------------------------------------------------- #
# config
# --------------------------------------------------------------------------- #
def load_config(explicit: Path | None, script_dir: Path) -> dict:
    cfg = dict(DEFAULTS)
    path = explicit or (script_dir.parent / "_meta" / "sync-config.yaml")
    if not path.exists():
        return cfg
    try:
        import yaml  # type: ignore
    except ImportError:
        print(f"note: {path.name} found but pyyaml not installed; using defaults "
              f"(pip install pyyaml to enable the config file).", file=sys.stderr)
        return cfg
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    cfg.update({k: v for k, v in data.items() if v is not None})
    return cfg


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def slugify(text: str) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return text or "session"


def yq(value) -> str:
    """YAML-quote a scalar."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    s = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{s}"'


def yaml_list(items) -> str:
    return "[" + ", ".join(yq(i) for i in items) + "]"


def sanitize_summary(text: str, limit: int = 140) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


def iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def parse_ts(value):
    """Return an ISO 'YYYY-MM-DDTHH:mm' string from an ISO record timestamp."""
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M")
    except ValueError:
        return None


def split_preserved(text: str) -> str | None:
    """Return the `## Notes ...` tail of an existing note, or None."""
    idx = text.find("\n" + NOTES_MARKER)
    if idx == -1:
        return None
    return text[idx + 1 :]


# --------------------------------------------------------------------------- #
# history index (first prompt per session, for local summaries)
# --------------------------------------------------------------------------- #
def build_history_index(claude_dir: Path) -> dict[str, str]:
    hist = claude_dir / "history.jsonl"
    earliest: dict[str, tuple[int, str]] = {}
    if not hist.exists():
        return {}
    for rec in iter_jsonl(hist):
        sid = rec.get("sessionId")
        disp = rec.get("display")
        ts = rec.get("timestamp")
        if not sid or not disp or not isinstance(ts, (int, float)):
            continue
        if sid not in earliest or ts < earliest[sid][0]:
            earliest[sid] = (int(ts), disp)
    return {sid: disp for sid, (_, disp) in earliest.items()}


# --------------------------------------------------------------------------- #
# session parsing
# --------------------------------------------------------------------------- #
def parse_session(path: Path) -> dict | None:
    sid = path.stem
    cwd = ""
    branch = ""
    version = ""
    model = ""
    timestamps: list[str] = []
    tools: set[str] = set()
    msg_count = 0

    for rec in iter_jsonl(path):
        if rec.get("sessionId"):
            sid = rec["sessionId"]
        if not cwd and rec.get("cwd"):
            cwd = rec["cwd"]
        if not branch and rec.get("gitBranch"):
            branch = rec["gitBranch"]
        if not version and rec.get("version"):
            version = rec["version"]

        ts = parse_ts(rec.get("timestamp"))
        if ts:
            timestamps.append(ts)

        rtype = rec.get("type")
        if rtype in ("user", "assistant") and not rec.get("isSidechain") and not rec.get("isMeta"):
            msg_count += 1
        msg = rec.get("message")
        if isinstance(msg, dict):
            if not model and msg.get("model"):
                model = msg["model"]
            content = msg.get("content")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        name = block.get("name")
                        if name:
                            tools.add(name)

    if not timestamps:
        return None
    timestamps.sort()
    return {
        "session_id": sid,
        "path": cwd,
        "start": timestamps[0],
        "end": timestamps[-1],
        "message_count": msg_count,
        "tools": sorted(tools),
        "branch": branch,
        "cc_version": version,
        "model": model,
        "source_mtime": path.stat().st_mtime,
        "source_file": path,
    }


def project_name(cwd: str, fallback: str, name_map: dict) -> str:
    base = Path(cwd).name if cwd else fallback
    return name_map.get(base, base)


def included(cwd: str, allow: list, deny: list) -> bool:
    hay = cwd or ""
    if any(d and d in hay for d in deny):
        return False
    if allow:
        return any(a in hay for a in allow)
    return True


# --------------------------------------------------------------------------- #
# note rendering
# --------------------------------------------------------------------------- #
def render_session_note(s: dict, project: str, summary: str, status: str) -> str:
    fm = [
        "---",
        "type: session",
        f"project: {yq(project)}",
        f"session_id: {yq(s['session_id'])}",
        f"path: {yq(s['path'])}",
        f"start: {yq(s['start'])}",
        f"end: {yq(s['end'])}",
        f"message_count: {s['message_count']}",
        f"tools: {yaml_list(s['tools'])}",
        f"status: {yq(status)}",
        f"summary: {yq(summary)}",
        f"branch: {yq(s['branch'])}",
        f"cc_version: {yq(s['cc_version'])}",
        f"model: {yq(s['model'])}",
        "source: auto",
        "---",
    ]
    body = [
        "> [!info] Auto-generated by sync.py. Everything above `## Notes` is "
        "rewritten on each sync; write below the marker.",
        "",
        f"**Project:** [[{project}]]  ",
        f"**Path:** `{s['path']}`  ",
        f"**Branch:** `{s['branch'] or '-'}`  ",
        f"**Window:** `{s['start']}` -> `{s['end']}`  ",
        f"**Messages:** {s['message_count']}  |  **Tools:** "
        + (", ".join(f"`{t}`" for t in s["tools"]) or "-"),
        "",
        "Resume: `claude -r` in the path above, or `claude -c` for the last session.",
    ]
    return "\n".join(fm) + "\n" + "\n".join(body) + "\n\n" + NOTES_MARKER + "\n\n"


def render_project_hub(project: str, path: str, status: str,
                       last_session: str, count: int) -> str:
    fm = [
        "---",
        "type: project",
        f"project: {yq(project)}",
        f"path: {yq(path)}",
        f"status: {yq(status)}",
        f"last_session: {yq(last_session)}",
        f"session_count: {count}",
        "key_commands: []",
        'cc_link: ""',
        "---",
    ]
    body = [
        "> [!info] Repo launch hub. `path` is the Open-in-Terminal target. Sync "
        "updates status / last_session / session_count; edits below `## Notes` persist.",
        "",
        "## Launch",
        f"- `{path}`",
        "- Open a terminal here, then `claude` (continue `claude -c`, resume `claude -r`).",
        "",
        "## Sessions",
        f"- Latest: `{last_session or '-'}`  |  Total: {count}",
    ]
    return "\n".join(fm) + "\n" + "\n".join(body) + "\n\n" + NOTES_MARKER + "\n\n"


def write_note(target: Path, content: str, dry: bool, state: dict, key: str,
               source_mtime: float | None = None) -> str:
    """Write content, preserving any existing `## Notes` tail. Returns action."""
    preserved = None
    if target.exists():
        existing = target.read_text(encoding="utf-8")
        preserved = split_preserved(existing)
    if preserved is not None:
        # content already ends with marker + blank lines; replace that tail.
        head = content[: content.rfind("\n" + NOTES_MARKER) + 1]
        content = head + preserved
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
    prior = state.get(key)
    if prior and prior.get("hash") == digest and prior.get("mtime") == source_mtime:
        return "skip"
    action = "update" if target.exists() else "create"
    if not dry:
        atomic_write(target, content)
    state[key] = {"hash": digest, "mtime": source_mtime, "file": target.name}
    return action


def archive_transcript(src: Path, project_slug: str, vault: Path, dry: bool) -> bool:
    dest = vault / "Archive" / project_slug / (src.stem + ".jsonl.gz")
    if dest.exists() and dest.stat().st_mtime >= src.stat().st_mtime:
        return False
    if not dry:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with src.open("rb") as fin, gzip.open(dest, "wb") as fout:
            shutil.copyfileobj(fin, fout)
    return True


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description="Mission Control session sync (read-only).")
    ap.add_argument("--dry-run", action="store_true", help="print actions, write nothing")
    ap.add_argument("--since", metavar="WHEN", help="only sessions starting on/after this ISO date or datetime (overrides config)")
    ap.add_argument("--archive", action="store_true", help="gzip raw transcripts into /Archive")
    ap.add_argument("--config", type=Path, help="path to sync-config.yaml")
    ap.add_argument("--vault", type=Path, help="override vault root")
    ap.add_argument("--minutes", type=int, help="override active-window minutes")
    args = ap.parse_args()

    script_dir = Path(__file__).resolve().parent
    cfg = load_config(args.config, script_dir)

    claude_dir = Path(cfg["claude_dir"]).expanduser()
    repo_root = script_dir.parent
    if args.vault:
        vault = args.vault.expanduser().resolve()
    else:
        vraw = Path(str(cfg["vault_dir"])).expanduser()
        vault = vraw.resolve() if vraw.is_absolute() else (repo_root / vraw).resolve()
    active_minutes = args.minutes if args.minutes is not None else int(cfg["active_minutes"])
    do_archive = args.archive or bool(cfg["archive"])
    name_map = dict(cfg.get("name_map") or {})
    allow = list(cfg.get("allow") or [])
    deny = list(cfg.get("deny") or [])
    since = args.since or (str(cfg["since"]) if cfg.get("since") else None)

    if not claude_dir.exists():
        print(f"error: claude_dir not found: {claude_dir}", file=sys.stderr)
        return 2

    state_path = vault / "_meta" / "sync-state.json"
    state: dict = {}
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            state = {}

    history = build_history_index(claude_dir)
    now = datetime.now(timezone.utc).timestamp()

    session_files = sorted(claude_dir.glob("projects/*/*.jsonl"))
    counts = {"create": 0, "update": 0, "skip": 0, "archived": 0, "excluded": 0}
    projects: dict[str, dict] = {}

    for sf in session_files:
        s = parse_session(sf)
        if not s:
            continue
        if not included(s["path"], allow, deny):
            counts["excluded"] += 1
            continue
        if since and s["start"] < since:
            continue

        proj = project_name(s["path"], fallback=sf.parent.name, name_map=name_map)
        proj_slug = slugify(proj)
        status = "active" if (now - s["source_mtime"]) <= active_minutes * 60 else "done"
        summary = sanitize_summary(history.get(s["session_id"], ""))

        fname = f"{s['start'][:10]}-{proj_slug}-{s['session_id'][:8]}.md"
        target = vault / "Sessions" / fname
        action = write_note(
            target, render_session_note(s, proj, summary, status),
            args.dry_run, state, key=f"session:{s['session_id']}",
            source_mtime=s["source_mtime"],
        )
        counts[action] = counts.get(action, 0) + 1

        agg = projects.setdefault(proj, {"path": s["path"], "count": 0,
                                         "last": "", "active": False})
        agg["count"] += 1
        if s["end"] > agg["last"]:
            agg["last"] = s["end"]
            agg["path"] = s["path"]
        if status == "active":
            agg["active"] = True

        if do_archive and archive_transcript(sf, proj_slug, vault, args.dry_run):
            counts["archived"] += 1

    for proj, agg in projects.items():
        target = vault / "Projects" / f"{proj}.md"
        status = "active" if agg["active"] else "idle"
        action = write_note(
            target,
            render_project_hub(proj, agg["path"], status, agg["last"], agg["count"]),
            args.dry_run, state, key=f"project:{proj}", source_mtime=None,
        )
        # project hubs change as sessions accrue; recount under their own labels
        if action != "skip":
            counts[action] = counts.get(action, 0) + 1

    if not args.dry_run:
        atomic_write(state_path, json.dumps(state, indent=2))

    tag = "[dry-run] " if args.dry_run else ""
    print(f"{tag}sessions+hubs  created={counts['create']} updated={counts['update']} "
          f"skipped={counts['skip']} excluded={counts['excluded']} archived={counts['archived']}")
    print(f"{tag}projects: {len(projects)}  vault: {vault}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
