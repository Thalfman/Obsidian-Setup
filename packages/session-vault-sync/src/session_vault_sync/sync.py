"""Local Claude Code transcript indexer. See README and SECURITY for boundaries."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import tempfile
import stat
from contextlib import contextmanager
import sys
from datetime import datetime, timezone
from pathlib import Path


def check_path(path: Path) -> None:
    """Reject symlinks/junctions and nonregular files, including ancestors."""
    path = path.absolute()
    for part in [*reversed(path.parents), path]:
        reparse = getattr(part.lstat(), "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0) if part.exists() else 0
        if part.is_symlink() or reparse or (hasattr(part, "is_junction") and part.is_junction()):
            raise ValueError(f"symlink/junction path refused: {part}")
        if part.exists() and not (part.is_dir() or part.is_file()):
            raise ValueError(f"nonregular path refused: {part}")
    if path.is_file() and path.stat().st_nlink > 1:
        raise ValueError(f"hard-linked file refused: {path}")


def atomic_write(path: Path, text: str) -> None:
    """Replace using a uniquely named private temporary file in the same directory."""
    check_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".session-sync-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            out.write(text)
        check_path(path)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


@contextmanager
def vault_lock(vault: Path, dry: bool):
    """Serialize cooperating writers; a stale lock must be inspected manually."""
    if dry:
        yield
        return
    meta = vault / "_meta"
    check_path(meta)
    meta.mkdir(parents=True, exist_ok=True)
    lock = meta / "session-vault-sync.lock"
    check_path(lock)
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise ValueError(f"another sync or stale lock exists: {lock}") from None
    try:
        with os.fdopen(fd, "w") as out:
            out.write(str(os.getpid()))
        yield
    finally:
        lock.unlink()


NOTES_MARKER = "## Notes"

DEFAULTS = {
    "claude_dir": "~/.claude",
    # Config-relative paths resolve against the selected config directory.
    # No implicit vault is selected when installed.
    "vault_dir": None,
    "active_minutes": 30,
    # Liveness tiers from a transcript's mtime: "active" within active_minutes,
    # "idle" until active_minutes * idle_factor, "done" beyond. Three tiers so a
    # stalled-but-open session stops masquerading as active.
    "idle_factor": 4,
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
def load_config(explicit: Path | None, script_dir: Path | None = None) -> dict:
    """Only an explicitly selected config is read; failures never widen scope."""
    cfg = dict(DEFAULTS)
    if explicit is None:
        return cfg
    explicit = explicit.expanduser()
    check_path(explicit)
    import yaml
    with explicit.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ValueError("config must be a mapping")
    unknown = set(data) - set(DEFAULTS)
    if unknown:
        raise ValueError(f"unknown config keys: {', '.join(map(str, unknown))}")
    cfg.update(data)
    for key in ("claude_dir", "vault_dir", "since"):
        if cfg[key] is not None and not isinstance(cfg[key], str):
            raise ValueError(f"{key} must be a string (quote dates)")
    if not cfg["claude_dir"]:
        raise ValueError("claude_dir must not be empty")
    for key in ("active_minutes", "idle_factor", "retention_days"):
        if type(cfg[key]) is not int or cfg[key] < 0:
            raise ValueError(f"{key} must be a nonnegative integer")
    if cfg["idle_factor"] < 1:
        raise ValueError("idle_factor must be at least 1")
    if type(cfg["archive"]) is not bool:
        raise ValueError("archive must be a boolean")
    for key in ("allow", "deny"):
        if not isinstance(cfg[key], list) or any(not isinstance(x, str) or not x for x in cfg[key]):
            raise ValueError(f"{key} must be a list of nonempty strings")
    if not isinstance(cfg["name_map"], dict) or any(
        not isinstance(k, str) or not isinstance(v, str) or not v
        for k, v in cfg["name_map"].items()
    ):
        raise ValueError("name_map must map strings to nonempty strings")
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
    if isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 2**63 - 1:
        return str(value)
    text = json.dumps(str(value), ensure_ascii=False)
    # YAML double-quoted scalars do not combine JSON UTF-16 surrogate pairs.
    # Escape all non-ASCII characters with YAML Unicode escapes instead.
    return "".join((f"\\U{ord(c):08x}" if ord(c) > 0xFFFF else f"\\u{ord(c):04x}") if ord(c) > 0x7F else c for c in text)


def yaml_list(items) -> str:
    return "[" + ", ".join(yq(i) for i in items) + "]"


def sanitize_summary(text: str, limit: int = 140) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


def iter_jsonl(path: Path):
    check_path(path)
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                if isinstance(rec, dict):
                    yield rec
            except json.JSONDecodeError:
                continue


def parse_ts(value):
    """Return an ISO 'YYYY-MM-DDTHH:mm' string from an ISO record timestamp."""
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M")
    except (ValueError, OverflowError):
        return None


def split_preserved(text: str) -> str | None:
    """Return the `## Notes ...` tail of an existing note, or None."""
    match = re.search(r"(?m)^## Notes[ \t]*$", text)
    return text[match.start():] if match else None


def token_sum(usage) -> int:
    """Total tokens for one assistant record's `message.usage` dict.

    Sums prompt, completion, and both cache token counts; any missing or
    non-integer sub-key defaults to 0. A missing/non-dict `usage` yields 0.
    """
    if not isinstance(usage, dict):
        return 0
    total = 0
    for key in ("input_tokens", "output_tokens",
                "cache_read_input_tokens", "cache_creation_input_tokens"):
        value = usage.get(key, 0)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 2**63 - 1:
            total += int(value)
    return total


def liveness(now: float, mtime: float, active_minutes: int, idle_factor: int) -> str:
    """Three-tier freshness from a transcript's mtime (all epoch seconds).

    "active" within active_minutes; "idle" within active_minutes * idle_factor;
    "done" beyond that. Both thresholds are inclusive. A stalled-but-open
    session ages out of "active" instead of reading live forever.
    """
    age = now - mtime
    if age <= active_minutes * 60:
        return "active"
    if age <= active_minutes * 60 * idle_factor:
        return "idle"
    return "done"


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
        if not isinstance(sid, str) or not isinstance(disp, str) or not isinstance(ts, (int, float)) or isinstance(ts, bool) or not 0 <= ts <= 2**63 - 1:
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
    tokens = 0

    for rec in iter_jsonl(path):
        if isinstance(rec.get("sessionId"), str) and rec["sessionId"]:
            sid = rec["sessionId"]
        if not cwd and isinstance(rec.get("cwd"), str):
            cwd = rec["cwd"]
        if not branch and isinstance(rec.get("gitBranch"), str):
            branch = rec["gitBranch"]
        if not version and isinstance(rec.get("version"), str):
            version = rec["version"]

        ts = parse_ts(rec.get("timestamp"))
        if ts:
            timestamps.append(ts)

        rtype = rec.get("type")
        if rtype in ("user", "assistant") and not rec.get("isSidechain") and not rec.get("isMeta"):
            msg_count += 1
        msg = rec.get("message")
        if isinstance(msg, dict):
            if not model and isinstance(msg.get("model"), str):
                model = msg["model"]
            tokens += token_sum(msg.get("usage"))
            content = msg.get("content")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        name = block.get("name")
                        if isinstance(name, str) and name:
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
        "tokens": tokens,
        "tools": sorted(tools),
        "branch": branch,
        "cc_version": version,
        "model": model,
        "source_mtime": path.stat().st_mtime,
        "source_file": path,
    }


def project_name(cwd: str, fallback: str, name_map: dict) -> str:
    base = cwd.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1] if cwd else fallback
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
def md_code(value: str) -> str:
    # HTML entities also neutralize Markdown punctuation in HTML-aware renderers.
    text = " ".join(str(value).split())
    return "<code>" + "".join(f"&#{ord(c)};" for c in text) + "</code>"


def render_session_note(s: dict, project: str, summary: str, status: str,
                        last_synced: str, project_file: str | None = None) -> str:
    if project_file is not None and not re.fullmatch(r"[a-z0-9-]+", project_file):
        raise ValueError("unsafe project link")
    project_link = f"[Project hub](../Projects/{project_file}.md) · " if project_file else ""
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
        f"tokens: {s['tokens']}",
        f"last_synced: {yq(last_synced)}",
        "source: auto",
        "---",
    ]
    body = [
        "> [!info] Auto-generated by sync.py. Everything above `## Notes` is "
        "rewritten on each sync; write below the marker.",
        "",
        f"**Project:** {project_link}{md_code(project)}  ",
        f"**Path:** {md_code(s['path'])}  ",
        f"**Branch:** {md_code(s['branch'] or '-')}  ",
        f"**Window:** `{s['start']}` -> `{s['end']}`  ",
        f"**Messages:** {s['message_count']}  |  **Tools:** "
        + (", ".join(md_code(t) for t in s["tools"]) or "-"),
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
        f"- {md_code(path)}",
        "- Open a terminal here, then `claude` (continue `claude -c`, resume `claude -r`).",
        "",
        "## Sessions",
        f"- Latest: `{last_session or '-'}`  |  Total: {count}",
    ]
    return "\n".join(fm) + "\n" + "\n".join(body) + "\n\n" + NOTES_MARKER + "\n\n"


def write_note(target: Path, content: str, dry: bool, state: dict, key: str,
               source_mtime: float | None = None) -> str:
    """Write content, preserving any existing `## Notes` tail. Returns action."""
    check_path(target)
    # The machine-owned region is everything up to (and including) the marker.
    # Hash only that, so edits below `## Notes` never trigger a rewrite.
    head = content[: content.rfind("\n" + NOTES_MARKER) + 1]
    # last_synced is stamped fresh on every render; exclude it from the change
    # hash so a note whose real content is unchanged still skips (idempotency).
    hashable = re.sub(r"(?m)^last_synced: .*\n", "", head)
    digest = hashlib.sha256(hashable.encode("utf-8")).hexdigest()[:16]
    prior = state.get(key)
    if target.exists() and isinstance(prior, dict) and not prior.get("pending") and prior.get("hash") == digest and prior.get("mtime") == source_mtime:
        return "skip"
    # Preserve any existing user notes below the marker.
    if target.exists():
        if not isinstance(prior, dict) or prior.get("file") != target.name:
            raise ValueError(f"refusing to overwrite unmanaged note: {target}")
        preserved = split_preserved(target.read_text(encoding="utf-8"))
        if preserved is not None:
            content = head + preserved
    action = "update" if target.exists() else "create"
    record = {"hash": digest, "mtime": source_mtime, "file": target.name}
    if not dry:
        state[key] = {**record, "pending": True}
        atomic_write(target, content)
    state[key] = record
    return action


class PersistentState(dict):
    """Persist write intent before replacing notes, and completion afterward."""
    def __init__(self, path: Path, data: dict):
        super().__init__(data)
        self.path = path

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        atomic_write(self.path, json.dumps(self, indent=2))


def load_state(path: Path) -> dict:
    check_path(path)
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or any(not isinstance(v, dict) for v in data.values()):
        raise ValueError(f"invalid state: {path}")
    return data


def file_digest(path: Path) -> str:
    check_path(path)
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def archive_transcript(src: Path, project_slug: str, vault: Path, dry: bool) -> bool:
    check_path(src)
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", project_slug):
        raise ValueError("unsafe archive project name")
    # Full source-path digest prevents duplicate basenames overwriting one another.
    ident = hashlib.sha256(str(src.absolute()).encode()).hexdigest()
    dest = vault / "Archive" / project_slug / (ident + ".jsonl.gz")
    check_path(dest)
    manifest_path = vault / "_meta" / "archive-state.json"
    manifest = load_state(manifest_path)
    key = dest.relative_to(vault / "Archive").as_posix()
    prior = manifest.get(key, {})
    if dest.exists():
        current_hash = file_digest(dest)
        if not prior or current_hash not in (prior.get("sha256"), prior.get("previous_sha256")):
            raise ValueError(f"refusing to overwrite unmanaged or modified archive: {dest}")
        if current_hash == prior.get("sha256") and prior.get("source_sha256") == file_digest(src):
            if "previous_sha256" in prior and not dry:
                manifest[key] = {k: v for k, v in prior.items() if k != "previous_sha256"}
                atomic_write(manifest_path, json.dumps(manifest, indent=2))
            return False
    if not dry:
        dest.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".session-sync-", dir=dest.parent)
        try:
            source_hash = hashlib.sha256()
            with os.fdopen(fd, "wb") as raw:
                with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as out, src.open("rb") as inp:
                    for block in iter(lambda: inp.read(1024 * 1024), b""):
                        source_hash.update(block)
                        out.write(block)
            check_path(dest)
            manifest[key] = {"sha256": file_digest(Path(tmp)), "source_sha256": source_hash.hexdigest(),
                             "previous_sha256": file_digest(dest) if dest.exists() else None}
            atomic_write(manifest_path, json.dumps(manifest, indent=2))
            os.replace(tmp, dest)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        manifest[key] = {"sha256": file_digest(dest), "source_sha256": source_hash.hexdigest()}
        atomic_write(manifest_path, json.dumps(manifest, indent=2))
    return True


def prune_archive(vault: Path, retention_days: int, now: float, dry: bool) -> int:
    """Prune only recorded, unmodified generated archives; never arbitrary files."""
    if retention_days <= 0:
        return 0
    root = vault / "Archive"
    check_path(root)
    manifest_path = vault / "_meta" / "archive-state.json"
    manifest = load_state(manifest_path)
    count = 0
    for key, entry in list(manifest.items()):
        if not re.fullmatch(r"[a-zA-Z0-9_-]+/[a-f0-9]{64}\.jsonl\.gz", key):
            raise ValueError("unsafe archive manifest entry")
        dest = root / key
        check_path(dest)
        if (dest.is_file() and dest.stat().st_mtime < now - retention_days * 86400
                and file_digest(dest) == entry.get("sha256")):
            if not dry:
                dest.unlink()
                del manifest[key]
            count += 1
    if count and not dry:
        atomic_write(manifest_path, json.dumps(manifest, indent=2))
    return count


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def run(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Index local Claude Code sessions into a Markdown vault.")
    ap.add_argument("--dry-run", action="store_true", help="print actions, write nothing")
    ap.add_argument("--since", metavar="WHEN", help="only sessions starting on/after this ISO date or datetime (overrides config)")
    ap.add_argument("--archive", action="store_true", help="gzip raw transcripts into /Archive")
    ap.add_argument("--prune-archive", action="store_true",
                    help="delete archives older than retention_days (config); honors --dry-run")
    ap.add_argument("--config", type=Path, help="path to sync-config.yaml")
    ap.add_argument("--vault", type=Path, help="override vault root")
    ap.add_argument("--minutes", type=int, help="override active-window minutes")
    ap.add_argument("--claude-dir", type=Path,
                    help="override Claude Code data dir (default: config or ~/.claude)")
    ap.add_argument("--version", action="version", version="session-vault-sync 0.1.0")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    base = args.config.expanduser().absolute().parent if args.config else Path.cwd()
    def config_path(value: str) -> Path:
        path = Path(value).expanduser()
        return path if path.is_absolute() else base / path
    claude_dir = args.claude_dir.expanduser().absolute() if args.claude_dir else config_path(cfg["claude_dir"]).absolute()
    if not args.vault and not cfg["vault_dir"]:
        raise ValueError("--vault or an explicit config vault_dir is required")
    vault = args.vault.expanduser().absolute() if args.vault else config_path(cfg["vault_dir"]).absolute()
    check_path(claude_dir)
    check_path(vault)
    claude_dir = claude_dir.resolve()
    vault = vault.resolve()
    if vault.is_relative_to(claude_dir) or claude_dir.is_relative_to(vault):
        raise ValueError("source and vault directories must not overlap")
    for name in ("Sessions", "Projects", "Archive", "_meta"):
        check_path(vault / name)
    active_minutes = args.minutes if args.minutes is not None else int(cfg["active_minutes"])
    if active_minutes < 0:
        raise ValueError("minutes must be nonnegative")
    idle_factor = int(cfg["idle_factor"])
    do_archive = args.archive or bool(cfg["archive"])
    name_map = dict(cfg.get("name_map") or {})
    allow = list(cfg.get("allow") or [])
    deny = list(cfg.get("deny") or [])
    since = args.since if args.since is not None else cfg["since"]

    if since is not None:
        normalized = parse_ts(since)
        if normalized is None:
            raise ValueError("since must be an ISO date or datetime")
        since = normalized

    if not claude_dir.is_dir():
        print(f"error: claude_dir not found: {claude_dir}", file=sys.stderr)
        return 2

    with vault_lock(vault, args.dry_run):
        state_path = vault / "_meta" / "sync-state.json"
        state = load_state(state_path)
        if not args.dry_run:
            state = PersistentState(state_path, state)
    
        history = build_history_index(claude_dir)
        now = datetime.now(timezone.utc).timestamp()
        synced_at = datetime.fromtimestamp(now, timezone.utc).strftime("%Y-%m-%dT%H:%M")
    
        check_path(claude_dir / "projects")
        session_files = sorted(claude_dir.glob("projects/*/*.jsonl"))
        for sf in session_files:
            check_path(sf)
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
            project_id = s["path"] or sf.parent.name
            proj_slug = slugify(proj)[:60] + "-" + hashlib.sha256(project_id.encode()).hexdigest()
            source_id = hashlib.sha256(sf.relative_to(claude_dir).as_posix().encode()).hexdigest()
            status = liveness(now, s["source_mtime"], active_minutes, idle_factor)
            summary = sanitize_summary(history.get(s["session_id"], ""))
    
            fname = f"{s['start'][:10]}-{slugify(proj)[:60]}-{source_id}.md"
            target = vault / "Sessions" / fname
            action = write_note(
                target, render_session_note(s, proj, summary, status, synced_at, proj_slug),
                args.dry_run, state, key=f"session:{source_id}",
                source_mtime=s["source_mtime"],
            )
            counts[action] = counts.get(action, 0) + 1
    
            agg = projects.setdefault(proj_slug, {"name": proj, "path": s["path"], "count": 0,
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
                render_project_hub(agg["name"], agg["path"], status, agg["last"], agg["count"]),
                args.dry_run, state, key=f"project:{proj}", source_mtime=None,
            )
            # project hubs change as sessions accrue; recount under their own labels
            if action != "skip":
                counts[action] = counts.get(action, 0) + 1
    
        pruned = 0
        if args.prune_archive:
            pruned = prune_archive(vault, int(cfg["retention_days"]), now, args.dry_run)
    
        if not args.dry_run:
            atomic_write(state_path, json.dumps(state, indent=2))
    
        tag = "[dry-run] " if args.dry_run else ""
        print(f"{tag}sessions+hubs  created={counts['create']} updated={counts['update']} "
              f"skipped={counts['skip']} excluded={counts['excluded']} archived={counts['archived']} "
              f"pruned={pruned}")
        print(f"{tag}projects: {len(projects)}  vault: {vault}")
        return 0


def main(argv: list[str] | None = None) -> int:
    try:
        return run(argv)
    except (OSError, ValueError, ImportError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        # PyYAML parse errors need a clean fail-closed diagnostic, not defaults.
        import yaml
        if isinstance(exc, yaml.YAMLError):
            print(f"error: invalid YAML config: {exc}", file=sys.stderr)
            return 2
        raise


if __name__ == "__main__":
    raise SystemExit(main())
