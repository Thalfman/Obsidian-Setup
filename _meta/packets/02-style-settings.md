---
type: reference
---
# Packet 02 — Style Settings toggles

**Bucket:** css · **Wave:** A · **Depends on:** none · **Exclusive:** owns
`.obsidian/snippets/console.css`.

Read `_meta/packets/README.md` header first.

## Goal
Expose the console's accent and density as UI toggles via the Style Settings
community plugin, without changing the default look.

## Background
Style Settings reads a special annotated comment block in the CSS — a
`/* @settings ... */` block containing YAML that declares the plugin id, a title,
and settings of types `variable-color`, `variable-number`, `variable-select`,
`class-toggle`. Each setting maps to a CSS custom property the stylesheet already
uses.

## Change
At the top of `console.css`, add a `/* @settings */` YAML block declaring:
- `name: Mission Control`
- a `variable-color` for the accent, default `#FF5A1F`, bound to
  `--interactive-accent` / `--text-accent` (use `opacity` false; alt format hex).
- a `variable-number` for base font size, default 16, bound to `--font-text-size`.
- a `variable-number` for the data-row vertical padding (introduce a new var,
  e.g. `--mc-row-pad`, default 6, and use it in the Bases `td` rule).
- a `variable-select` "density" with options compact/normal/relaxed that switch
  `--line-height-normal`.
Keep all current defaults identical so nothing changes until the user toggles.

## Verification
- CSS still valid (no syntax errors); the file still loads as a snippet.
- The `@settings` block is valid YAML:
  extract between the markers and `yaml.safe_load` it.

## Acceptance
- With Style Settings installed, a "Mission Control" section appears with the
  declared controls; defaults match the current palette/spacing exactly.
- No visual change with all settings at default.

## Do NOT touch
`scripts/`, `tests/`, `Dashboards/`, README, Console Spec, data folders.
