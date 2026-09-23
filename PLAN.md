# Pipeline overhaul plan (2026-09-23)

Four phases, each ending in one local commit. Commits are allowed; **no push**.
Tick boxes as phases land.

Decisions already made by the user:

- New APKs are dropped in the repo root and auto-detected.
- Each game version gets its own output folder, `extracted/<version>/`.
- Ruff runs lint + format on every commit.
- README.md is for the user only, so it can shrink to a short how-to.

## What was measured before planning

- Every extractor opens bundles **one at a time on one core**; the machine has 8.
- Stage 3 (sprite index) and stage 4 (icons) each open the same 209 bundles, so every
  bundle is loaded twice.
- Nothing is cached between runs; a re-run redoes everything.
- Not the bottleneck: loading the monoscript bundle (~0.2 s) or reading sprite names
  (`peek_name` saves < 0.3 s per large bundle). Bundle loading and typetree reads dominate.
- Every bundle filename already contains its content hash, a free cache key.

## Phase 1 — Ruff + pre-commit hook

- [x] `ruff.toml`: line length 100, single quotes (matches current code; only 9 lines
      exceed 100 today). Rules: defaults + `B`, `UP`, `I`, noisy ones ignored.
- [x] `.pre-commit-config.yaml` with `ruff-pre-commit` (lint --fix, then format);
      `pip install pre-commit ruff`, `pre-commit install`.
- [x] Run once over `tools/`.
- [x] `tests/`: 32 unit tests + 1 slow golden test (rebuild instant stages, outputs must
      not change). Mutation spot-check: 4 of 4 injected bugs caught.
- [x] Verify: re-run the instant stages (`build_icon_map --check`, `build_equipment`,
      `build_indexes`, `build_item_details`, `build_guide`) → `git status extracted/`
      shows no change.

## Phase 2 — Speed without changing results

- [x] Baseline: time each slow script once (background) and profile it.
- [x] Same-output test: after a re-run, JSON and PNGs must be byte-identical
      (`git status extracted/` clean). This is the gate for this phase.
- [x] Parallelise bundle processing (`ProcessPoolExecutor`). Safe: one bundle per
      UnityPy environment is already the rule and stays the rule.
- [x] Merge stages 3 + 4 so each bundle is opened once.
- [x] Per-bundle cache keyed by the hashed filename: unchanged bundles are skipped on
      re-runs and on new APK versions.
- [x] Build the MonoScript name table once, not per bundle.
- [x] Report measured before/after times (expected: ~4-6x cold, near-instant warm).
- [x] Found while profiling: UnityPy re-parses a sprite's whole SpriteAtlas for every
      sprite it crops; one bundle took 364 s of the icon pass. `_share_atlas()` parses
      it once per bundle (104 s -> 6 s on `ui-dynamic_common`).

Results (8 cores, 7 workers):

| script | before | after, cold | after, warm |
|---|---|---|---|
| extract_soulknight | 561 s | 33 s | 15 s |
| extract_skill_links | 30 s | 13 s | 3 s |
| dump_prefabs | 51 s | 26 s | 16 s |
| **total** | **642 s** | **72 s (8.9x)** | **34 s** |

All 5,409 output files byte-identical to the baseline, cold and warm; the baseline in
turn matched the committed `extracted/`. `extract_named_sprites` re-export of the 121
`EBF_*` icons also identical.

## Phase 3 — New APK versions without re-capturing everything

Short answer: **no full re-capture.** Hand data (`guide/icon_map.json`,
`effect_map.json`, `weapon_types.json`) is keyed on item IDs, loc keys and sprite names,
which patches normally keep. Only new items and flagged changes need screenshots.

- [x] `tools/unpack_apk.py`: `.apk`/`.xapk`/`.zip` in the root → read the version →
      unpack to `soul-knight-prequel-<version>/`. Tools default to the newest folder.
- [x] Move current output to `extracted/1.13.0/` with `git mv` (renames, no size cost);
      `extracted/_sheets/` stays shared. Every tool takes the version's output dir.
- [x] `tools/pipeline.py`: one command runs every stage in order.
- [x] `tools/version_diff.py <old> <new>` reports:
  - new / removed equipment;
  - changed text on loc keys used by `effect_map.json` or the guide;
  - confirmed sprites whose **pixels** changed (catches silent reassignment);
  - confirmed sprites that disappeared;
  - ends with a short "Your action" capture list + contact sheet of only new items.
- [x] Test: 1.13.0 vs itself → zero changes; vs a deliberately altered copy → each
      change detected.
- Trade-off: each new version adds ~130 MB of new files to the repo.

Done. Notes from doing it:

- Version comes from the game's own `assets/bundleVersionData.txt`; fallback is a small
  AXML parser for `versionName` (checked on the real 1.13.0 manifest), then the XAPK's
  `manifest.json`, then `--version`.
- Split APKs are merged into base without overwriting it (each split has its own
  `AndroidManifest.xml`). Zip-slip paths are refused.
- The pipeline reproduces the committed 1.13.0 output exactly: after moving it to
  `extracted/1.13.0/` and re-running every stage, git shows 5,680 pure renames and no
  content change.
- `build_icon_map` stamped today's date into `guide/icon_map.json` on every run; it now
  only does so when the derived entries change. In the pipeline it is non-fatal, so a
  missing confirmed sprite on a new version ends in the diff report instead of a stop.
- Self-diff of 1.13.0 first reported 28 "renamed" hand-mapped items: the maps type `'`,
  the game has `’`. Names are now compared with quotes, case and spacing normalised.
- 17 new tests: synthetic apk/wrapped-zip/xapk unpacking, zip-slip, version lookup, every
  diff category on synthetic data, and a slow test on the real 1.13.0 data (clean against
  itself; an altered copy reports each alteration). Mutation check: 6 of 6 caught.

## Phase 4 — Context engineering (docs)

- [ ] Research Anthropic's current Claude Code guidance: CLAUDE.md size, `@imports`,
      path-scoped `.claude/rules/`, project skills.
- [ ] CLAUDE.md: 31 KB (~8k tokens per session) → ~120 lines: what the repo is,
      commands, hard "don'ts", and a map of where each topic lives.
- [ ] Move domain knowledge to on-demand `docs/*.md` (icons, effect text, IDs, bundles,
      decryption dead ends); merge `icon-mapping-plan.md` into `docs/icons.md`.
- [ ] Screenshot/recording workflow → project skill (loads only when used).
- [ ] README → short how-to for the user.
- [ ] Check every fact has a new home before deleting the old text; measure the
      always-loaded token count before and after.
