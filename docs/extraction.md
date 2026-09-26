# How extraction works

The internals of the three extractors (`extract_soulknight.py`, `extract_skill_links.py`,
`dump_prefabs.py`) and of `parallel.py`, plus what is and is not decrypted. Read this before
changing any of them.

## Two paths into `extracted/<version>/`

The game is Unity 2022.3 with Addressables. Its content sits in about 465 `.bundle` files
under `<apk>/assets/Asset/`.

**Path 1: localization and items** (`extract_soulknight.py`). It runs these stages:

1. **Localization.** Strings are `TextAsset`s in `localization_*.bundle`, stored as a
   hand-rolled TSV (`Key, Type, English, Chinese, …`). Python's `csv` module breaks on it
   (unescaped quotes and newlines inside cells), so `parse_tsv` splits on record starts
   (`"key"<TAB>"type"<TAB>`).
2. **Addressables catalog.** `assets/aa/catalog.json` stores its keys, buckets and entries as
   base64 blobs. They are decoded into address → asset path.
3. **Sprite index** plus **4. icon PNGs.** One pass over the bundles; icon names match
   `ICON_PATTERN` (`ItemIcon_`, `ICON_`, `UI_SkillIcon`, …). `--all-sprites` drops the filter
   and exports all ~112k sprites (hours, several GB).
5. **Item tables.** Names, descriptions and icons are joined by key.

**Path 2: prefabs** (`dump_prefabs.py`, `extract_skill_links.py`). Every bundle still ships
its Unity **type trees**, so UnityPy's `read_typetree()` returns each `MonoBehaviour` field by
name. The whole prefab side rests on this one fact.

- `dump_prefabs.py` walks each prefab's GameObject hierarchy and keeps MonoBehaviours only,
  dropping Transforms, renderers and particles.
- `extract_skill_links.py` reads `RGSkill.Desc` to link skills to items (see
  [effects.md](effects.md)).

The `build_*` tools are pure joins over that JSON and never touch the APK.

**`extract_named_sprites.py`** exports sprites that `ICON_PATTERN` never matched (`EBF_`,
`Incarnation_`, `icn_equip_`, …). It consults `sprite_index.json` and opens only the bundles
that hold the names asked for. The pipeline runs it four times.

## Bundle variants: the catalog decides, and it matters

44 logical bundles ship two or three files that differ only by content hash, and **none of the
44 groups are byte-identical**.

- **Filename order picks the wrong file.** In 21 of the 44 groups it lands on a bundle the game
  does not load, including `buff_all`, `skill_class_all`, every `skill_directclass_*` and three
  `skp_loc_*` tables.
- **The catalog picks the right one.** `extract_soulknight.shipped_bundles()` reads
  `assets/aa/catalog.json`, whose `m_InternalIds` name exactly one variant per group (44 of 44).
  Every tool filters through it.

Reading the wrong variant caused two silent failures:

- **Stale text.**
  - The orphan `skp_loc_s3`/`s5`/`s7` carry straight quotes where the shipped tables have curly
    ones.
  - `skp_loc_s13_bin` happened to sort first, so it was already the shipped copy.
  - Its `77646` and `82115` read like earlier drafts. `82115` has a malformed
    `#FA3914...</color>` where the orphan has `<color=#25bbbcff>`. That is the game's own
    shipped data, so it stays.
- **Garbage pixels.**
  - Variants reuse the CAB name of their `.resS` stream file. Load two of them into one UnityPy
    environment, and both atlas textures resolve that shared name to the **same** 8 MB blob.
  - The variants pack at different shapes (2048x4096 vs 4096x2048), so every sprite crop lands
    on unrelated pixels, and no exception is raised.
  - This silently scrambled all ~500 `ItemIcon_*` PNGs and the `EBF_*` Fatebound icons.
  - So the extractors load **one bundle per environment**. Do not "optimise" that back into
    `UnityPy.load(*all)`.

Co-loading gains nothing anyway.

- **A packed sprite only exports from its own atlas bundle.** UnityPy looks for a packed
  sprite's SpriteAtlas only in the sprite's *own* assets file (`export/SpriteHelper.py`). Its
  copies elsewhere carry `m_RD.texture` == PathID 0 and raise either way.
- **The catalog filter costs three sprites:** `S13_SKIN_H_icon_4`/`_5`/`_6`. They live only in
  an orphan variant and are not icons.

Not affected by variants: the prefab labels.

- The three `*monoscripts*` variants agree on every shared MonoScript path_id.
- The only path_id a prefab bundle shares with them is `1`, the AssetBundle manifest.

The prefab dumps were only reading stale bundles, never mislabelled ones.

## Parallelism and cache (`parallel.py`)

- **Workers.** `map_bundles()` runs one worker per bundle (CPUs − 1).
- **Order.** Results merge **in bundle order**, through a `consume` hook for streamed PNGs, so
  "first bundle wins" output is byte-identical to a sequential run (checked on all 5,409
  files).
- **Cache.** Each bundle's result is cached in `.cache/<tag>/<basename>.<size>.pkl`.
  - The basename contains the content hash.
  - The tag hashes the worker's source file and the UnityPy version, so a code change
    invalidates it by itself.
  - Error results are never cached (the `cacheable` predicate).
  - A new APK re-reads only the bundles that changed.
- **Flags.** `--no-cache` and `--workers N` work on every extractor. `--workers 1` runs inline,
  which is useful under a debugger.
- **Timings.** Cold, the three extractors take about 35 s / 15 s / 25 s; warm, about 35 s
  together. Before this it was 642 s cold. 364 s of that was one bundle, because UnityPy
  re-parses a sprite's whole SpriteAtlas for every sprite it crops. `_share_atlas()` parses it
  once per bundle, on both lookup paths (the `m_SpriteAtlas` pointer and the `m_AtlasTags`
  name).

## Iterating

```bash
python tools/dump_prefabs.py --groups buff skill     # one group instead of all nine
python tools/dump_prefabs.py --list                  # groups and their bundle counts
python tools/extract_skill_links.py --dump 1500441   # one prefab's whole component tree
python tools/extract_soulknight.py --skip-icons      # text + catalog + item tables only
```

To re-run a single stage, import the module rather than adding a flag:

```python
import sys, json; sys.path.insert(0, 'tools')
import extract_soulknight as E
s = E.stage_localization('soul-knight-prequel-1-13-0/assets/Asset', 'extracted/1.13.0')
sprites = {n for v in json.load(open('extracted/1.13.0/sprite_index.json')).values() for n in v}
E.stage_items(s, sprites, 'extracted/1.13.0')
```

## Decrypted, and handled automatically

- **`skp_loc_s13_bin` is XOR-obfuscated, not encrypted.**
  - Every table starts with the same `"Key"<TAB>"Type"<TAB>"English"…` header row, so
    `ciphertext ^ header` *is* the key stream. It repeats every 120 bytes.
  - `deobfuscate()` recovers it from a sibling table's header.
  - This added 1,777 strings, including the `111563`-`112171` effect texts and the
    `95xxx`/`96xxx` blocks.
- **`global-metadata.dat` is not encrypted.** Only its 0x108-byte header is scrambled. The whole
  string-literal table after it is plaintext and greppable with plain `re`.

## Still closed: do not repeat this search, it has been done exhaustively

**`code_dll.bundle` / `code_aot.bundle`** hold the Luban config tables: item → effect ID, drop
rates, prices, enemy HP/ATK, and item → icon.

- **Where the Luban tables are not.** `Luban.Runtime.dll` is referenced in the metadata, but
  its `.bytes` tables are not in Addressables, not in `Resources`, and not in any other bundle.
  These two files, or the server, are all that is left.
- **How they load.** They are not in the Addressables catalog, and only the two stock providers
  are registered. The game's own bootstrap loads them.
- **What the plaintext is.** It is an AssetBundle holding `SoulKnight-Prequel.dll.bytes`
  (`加载 SoulKnight-Prequel.dll.bytes成功` is in the metadata). So the first 32 plaintext bytes
  are the fixed `UnityFS … 2022.3.62f3` header, and known-plaintext attacks are easy to run.
- **The cipher.** It is a **block cipher in ECB mode** (block size 8, 16 or 32). The two files
  share their first 32 bytes, and past byte 32 `file1 ^ file2` is uniformly random, which rules
  out a keystream.
- **Every contiguous key candidate has been tried.**
  - Files: every byte offset of `global-metadata.dat`, all four `classes*.dex`,
    `libnative-lib.so`, `libanogs.so`, `libanort.so` and `libil2cpp.so`.
  - Ciphers: AES-128/192/256 (ECB and CBC), DES/3DES, SM4, SEED and Camellia.
  - Derived keys: MD5/SHA-256 of every printable string.

  Nothing matched.
- **Where the key probably is.** It is most likely built in ARM64 code as `MOV`/`MOVK`
  immediates. The only remaining route is a real disassembler on `libil2cpp.so`, starting from
  the xref to the `code_aot.bundle` string literal.

**`assets/*.bytes`** (`distroConfig`, `cmjax`, `rnjax`) are channel/SDK config, not game
content.

- **Format.** They are base64 of an 8-byte-block ECB cipher. `distroConfig.bytes` and
  `iOS_CNdistroConfig.bytes` share exactly 7 blocks.
- **Probably DES.** `CoreKit.Util|CryptUtil.DecryptDES` exists, but the key has not been found.
