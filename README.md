# Soul Knight Prequel: extracted data

Readable JSON and icons pulled out of the Soul Knight Prequel APK, plus the Ranger guide
(`range-guide.html`) built from them.

## New game version

1. Put the download (`.apk`, `.xapk`, `.apks`, or a `.zip` of the unpacked folder) in the
   project root.
2. Run:
   ```powershell
   $env:PYTHONIOENCODING = 'utf-8'
   python tools/unpack_apk.py     # -> soul-knight-prequel-<version>/
   python tools/pipeline.py       # -> extracted/<version>/   (~90 s; ~35 s re-run)
   ```
3. Open `extracted/<version>/changes_from_<old>.md`. It lists what changed and ends with the
   codex pages to screenshot. New icons are on a contact sheet in `extracted/_sheets/`.
4. Share the screenshots with Claude. It updates the confirmed maps in `guide/` and rebuilds.

If a stage fails, fix it and resume with `python tools/pipeline.py --from <stage>`;
`--list` shows the stage names.

## Look things up

Search `extracted/<version>/localization_all.json` in VS Code; the line above a match is the
key. From a terminal:

```powershell
python -c "import json;s=json.load(open('extracted/1.13.0/localization_all.json',encoding='utf8'));[print(k,'|',v['English'][:100]) for k,v in s.items() if 'paradox' in v['English'].lower()]"
```

| Want | File in `extracted/<version>/` |
|---|---|
| Any string, 13 languages | `localization_all.json` (28,703 keys) |
| Equipment: slot, icon, legendary effect | `equipment.json` (806 rows, 767 with icon, 201 with effect) |
| Weapon type, armor class, tier, class | `item_details.json` |
| Other items | `items.json` (`ITEM_*`), `items_numeric.json` (numeric keys) |
| Skills, buffs, characters with names | `named_prefabs.json`, `buffs.json`, `characters.json` |
| Keywords (`$jisu$` = Swift) and their rules text | `glossary.json` (128 tokens) |
| Raw game logic | `prefabs/*.json` (18,182 prefabs) |
| Icons | `icons/` |

## Guide

Edit `guide/*.json`, then run `python tools/build_guide.py` to regenerate `range-guide.html`.
`python tools/export_guide_png.py` cuts it into Discord-sized PNGs in
`extracted/_sheets/guide_png/` (needs `pip install playwright`; it uses the installed Edge).

## Known gaps

These can only be filled from the game itself (screenshots):

- 39 equipment icons and ~600 equipment effect texts are unknown. The item → icon and
  item → effect tables are in the encrypted config.
- About 140 equipment icons are not in the APK at all; the game downloads them.
- Rarity, drop rates, prices, enemy stats and every `{0}` value live in the same encrypted
  config.

Details for each: `docs/`.

## Setup

- Python 3.10+.
- Run `pip install UnityPy pypinyin`.
- For development, run `pip install ruff pre-commit pytest && pre-commit install`. Every commit
  is then linted, formatted and tested.
