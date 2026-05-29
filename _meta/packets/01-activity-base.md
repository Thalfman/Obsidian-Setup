---
type: reference
---
# Packet 01 — Activity board

**Bucket:** new file · **Wave:** C (after 04 merges) · **Depends on:** 04 for the
`tokens` field · **Exclusive:** none (new file, no collisions).

Read `_meta/packets/README.md` header first.

## Goal
A `Dashboards/Activity.base` that answers "where is my effort going" — sessions
grouped by project, with counts and (once 04 lands) summed tokens.

## Bases syntax (verified, do not deviate)
- View sort: a list of `{property, direction: ASC|DESC}`.
- `order:` lists the columns. `groupBy: {property, direction}` groups.
- `summaries:` maps a property to a named aggregation (Sum, Average, Max, etc.).
- Property refs: `note.x` (frontmatter), `file.x` (file). Filters are strings
  like `'note.type == "session"'`.

## Change
Create `Dashboards/Activity.base` with one global filter `note.type == "session"`
and a table view:
- `groupBy: { property: note.project, direction: ASC }`
- columns: `note.project`, `note.start`, `note.message_count`, `note.tokens`,
  `note.status`
- sort by `note.start` DESC
- `summaries:` → `note.message_count: Sum`, `note.tokens: Sum`
Add a second view "By model" grouped on `note.model` if useful.

Embed it on the cockpit: add a `![[Activity.base]]` reference under a new
"Activity" section in `Dashboards/Home.md` ONLY IF Home is not being edited by
another packet this wave (it is not — Home is dispatcher-owned; instead report
the one-line embed snippet in your output for the dispatcher to add).

## Verification
- `.base` is valid YAML: `python -c "import yaml,sys;yaml.safe_load(open('Dashboards/Activity.base',encoding='utf-8'));print('ok')"`
- In Obsidian (human check): the board renders grouped rows with a Sum row.

## Acceptance
- File parses as YAML; columns and summaries match the spec.
- Token column populated once 04 is merged (0s before that — acceptable).

## Do NOT touch
`scripts/sync.py`, `tests/`, css, README, Console Spec, Home.md (report the embed
snippet instead), data folders.
