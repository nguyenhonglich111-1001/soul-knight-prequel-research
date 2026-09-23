# CLAUDE.md

A **data-extraction project**, not an application. Python scripts read an unpacked Soul Knight
Prequel APK (Unity 2022.3, Addressables, ~465 bundles) and write readable JSON and PNG icons
into `extracted/<version>/`. A hand-written guide in `guide/` is rendered from that output.

## Layout

- `soul-knight-prequel-<a-b-c>/`: one unpacked APK per game version (git-ignored). Made by
  `tools/unpack_apk.py`; do not unzip by hand.
- `extracted/<a.b.c>/`: one version's output (~132 MB of JSON plus ~5,660 PNGs), all
  regenerable. `extracted/_sheets/` (contact sheets, guide PNGs) is shared.
- `guide/`: the **only hand-authored data**. It holds guide prose plus the confirmed maps
  (`icon_map.json`, `effect_map.json`, `weapon_types.json`), rendered by `tools/build_guide.py`.
- `tools/`: the pipeline. Every tool defaults to the newest version (`tools/versions.py`);
  `--apk-dir` / `--out` override.
- `tests/`: pytest. `docs/`: the domain knowledge below. `PLAN.md`: the current work plan.

## Commands

Python 3.10+, `pip install UnityPy pypinyin`. **On Windows, always set `PYTHONIOENCODING=utf-8`**,
otherwise printing any Chinese string crashes with `UnicodeEncodeError`.

```bash
python tools/unpack_apk.py            # new .apk/.xapk/.apks/.zip in root -> soul-knight-prequel-<v>/
python tools/pipeline.py              # all 12 stages -> extracted/<v>/ (~90 s cold), then version_diff
python tools/pipeline.py --list       # stage names; --from <stage> resumes there
python tools/version_diff.py [old new]   # -> extracted/<new>/changes_from_<old>.md + "Your action"
python tools/build_icon_map.py --check   # guard guide/icon_map.json
python tools/export_guide_png.py      # guide -> Discord PNGs (playwright, system Edge)
python -m pytest                      # fast tests;  -m "" adds the slow golden-output test
```

Stage order matters:

1. The extractors run first: `extract_soulknight`, `extract_named_sprites` ×3,
   `extract_skill_links`, `dump_prefabs`.
2. `build_icon_map` runs next.
3. Then `build_equipment` → `build_indexes` → `build_glossary` → `build_item_details` →
   `build_guide`.

The `build_*` stages are pure joins over the JSON and run instantly. What each one reads:

- `build_equipment` reads `localization_all`, `items_numeric`, `skill_links`,
  `guide/icon_map` and `guide/effect_map`.
- `build_indexes` reads `localization_all` and `prefabs/`.
- `build_glossary` reads `localization_all` and the `glossary` of `guide/*.json`.
- `build_guide` reads `guide/*.json`, `localization_all`, `items_numeric`, `equipment` and
  `icons/`.

## Dev loop

`pre-commit install` once (`pip install ruff pre-commit pytest`). Each commit then runs:

- `ruff check --fix` and `ruff format` (config in `ruff.toml`: single quotes, 100 columns);
- the fast tests.

The slow test rebuilds the instant stages and fails if any committed output changes. So after
changing a build tool, either the output stays identical or the regenerated output is committed
with it.

## Hard rules

- **Never invent an ID → sprite-number or item → effect-key formula.** Both have been tried and
  disproved, and the real tables are encrypted. Unknown means no icon or no text, never a
  guess. See `docs/icons.md` and `docs/effects.md`.
- **Never rewrite `confirmed` entries** in `guide/*.json` from a tool. They are the user's
  in-game observations.
- **Load one bundle per UnityPy environment, filtered through the catalog.** Co-loading
  scrambles sprites without any error. See `docs/extraction.md`.
- **Do not re-search what is recorded as a dead end:**
  - `code_dll`/`code_aot` decryption;
  - `ItemIcon` in metadata, catalog or prefabs;
  - the ~140 downloaded icons;
  - the description blocks listed in `docs/effects.md`.
- **Compare the `Chinese` column before concluding** that two English strings name different
  things (see `docs/data-model.md`).
- **Keep refactors byte-identical.** When optimising or reorganising a tool, prove the output is
  unchanged before committing.

## When the data cannot settle it, ask the user

The user plays the game and is the ground truth for anything the encrypted config hides: which
icon belongs to an item, what `{0}` resolves to, whether a name matches the screen.

- **Ask early and cheaply.** Show a labelled contact sheet to point at, or state the current
  answer and ask whether it matches. Ask for a few spot checks, not an audit.
- **Use the `codex-screenshots` skill** to turn screenshots or recordings into confirmed
  entries.
- **Write every answer down where it cannot be re-derived away:** a `confirmed` entry, a line in
  `docs/`, or a test.

## Where knowledge lives (read on demand)

| Read before working on… | File |
|---|---|
| icons, `icon_map.json`, sprite series, Axial Incarnates | `docs/icons.md` |
| descriptions, legendary effects, `effect_map.json`, `$token$` glossary/`{0}`, dead ends | `docs/effects.md` |
| output files, ID schemes, `ITEM_*` alias, class/rarity, prefab fields, Chinese cross-check | `docs/data-model.md` |
| extractor internals, bundle variants, cache, decryption status, single-stage re-runs | `docs/extraction.md` |
| screenshots, recordings, codex grids, asking the user | `.claude/skills/codex-screenshots/` |

`README.md` is the user's short how-to. Keep its counts in sync when the pipeline changes.
