# Fixing the numeric item → icon mapping

**Status:** not started. Written 2026-09-21, after the `Tophat of Six Splendors` icon was found
to be wrong in the rendered guide.

## The bug

`icon_candidates()` in [extract_soulknight.py](tools/extract_soulknight.py) and
`Data.icon_path()` in [build_guide.py](tools/build_guide.py) both assume an arithmetic link
between an item's numeric ID and its sprite's number:

```
103467  ->  (103467 - 100000) * 1000  ->  ItemIcon_3467000
```

**No such link exists.** It was inferred from the two numbers looking similar and was never
checked against the game. It is wrong, and it has been wrong since the first extraction.

Confirmed wrong by four in-game observations (helmets, reported 2026-09-21):

| Item | ID | Formula says | Actually |
|---|---|---|---|
| Frostbound Hood | `103464` | `3464000` | **`3467000`** |
| Tophat of Six Splendors | `103467` | `3467000` | **`3470000`** |
| Crown of the Martial Saint | `103468` | `3468000` | **`3472000`** |
| Rebellion-Queller's Headdress | `103469` | `3469000` | **`3473000`** |

Note the offset is `+3` for the first two and `+4` for the last two. No constant-offset formula
can be correct.

## Why it went unnoticed

The two number series run close together (`3448` against `103448`), so every wrong assignment
still landed on *a helmet* — just the wrong one, three places along. Nothing looked broken until
someone who knew the items compared them against the game.

## The real link is not recoverable

The item → icon table lives in the encrypted Luban config (`code_dll.bundle`, see
[CLAUDE.md](CLAUDE.md) "What is and is not decrypted"). Searched and came up empty:

| Source | Result |
|---|---|
| `global-metadata.dat` (16 MB plaintext) | **0** hits for `ItemIcon_`, `iconId`, `GetItemIcon` |
| `asset_catalog.json` (46,983 addresses) | **0** asset paths containing `ItemIcon` |
| All 18,182 prefab dumps | **0** references to any `ItemIcon_*` name |

So the mapping cannot be derived. It can only be *inferred* structurally, then verified by eye.

## What the structure actually is

Two independent sequences that run in parallel and drift: the item IDs, and the art asset
numbers. They line up **by rank**, not by arithmetic.

For helmets the fit is exact — 25 sprites against 25 items that have no `ITEM_*` alias:

```
sprites  3448 3449 3450 3451 ... 3468 3469 3470 [3471 missing] 3472 3473   (25)
items  103445 ...................................................103469   (25)
```

That reproduces all four observations above, and it also explains the three sprites that had no
owner (`3448`/`3449`/`3450`) and the three helm items that showed `icon: null`
(`103445` Lament of the Fallen, `103446` Rapture of the Fallen, `103447` Tribal Headdress).

Slot 7 is the clearest proof that there is no formula at all: 8 sprites numbered `7501`-`7508`
against 8 items numbered `107702`-`107709`. The offset is `-201`, arbitrary and slot-specific.

## Per-slot survey

`rule-1 rows` is how many equipment rows currently take an icon from the broken formula. The
other 550 of 806 rows go through the `ITEM_*` alias, which is self-verifying (the English name
matches in both directions) and is **not affected by any of this**.

The blast radius really is exactly those 115 rows. Both `build_guide.Data.icon_path()` and
`items_numeric.json` try the broken formula *before* the alias, which would be a second bug if
the two ever collided — but they never do: of all 806 equipment items, **zero** resolve under
both rules. The formula only ever fires where the alias has nothing to say.

| Slot | rule-1 rows | sprites | sprite numbers | alias-less tail | verdict |
|---|---|---|---|---|---|
| helm | 22 | 25 | `3448`-`3473`, gap `3471` | `103445`-`103469`, contiguous | **confirmed** by 4 observations |
| armor | 18 | 22 | `2447`, `2451`-`2470`, `2472` | `102446`-`102467`, contiguous | plausible, unverified |
| necklace | 5 | 22 | `6440`-`6469`, 8 gaps | `106727`-`106748`, contiguous | plausible, unverified |
| gear | 1 | 8 | `7501`-`7508`, no gaps | `107702`-`107709`, contiguous | plausible, unverified |
| weapon | 61 | 63 | `1591`-`1655`, gaps `1616` `1642` | `101591`-`101655`, **not contiguous** | risky |
| boots | 1 | 19 | `4445`-`4466`, 3 gaps | `104445`-`104717`, **not contiguous** | risky — tail spans 272 IDs |
| ring | 6 | 31 | `5440`-`5474`, gaps `5446`-`5449` | `105444`-`105737`, **not contiguous** | risky — tail spans 293 IDs |
| core | 1 | 21 | `8200`, `8300`, `8400`-`8418` | `108710`-`108730`, contiguous | **reject** — sprites are three separate runs, not one sequence |

## Plan

### 1. Derive the mapping by rank, per slot

For each slot: take the numeric sprites in that slot's range, take the items with no `ITEM_*`
alias, align the last *N* items to the *N* sprites in order. Helm already reproduces all four
observations with no special-casing.

### 2. Freeze it in `guide/icon_map.json`, do not recompute at build time

The generator writes the file once; `build_equipment.py` and `build_guide.py` *read* it.

This is the point of the whole exercise. Rank alignment is an inference, and an inference that
silently re-derives itself on every build is exactly how the original bug survived. Freezing it
means a change in the data shows up as a diff rather than as different pixels.

Shape:

```json
{
  "generated": "2026-09-21",
  "derived": { "103467": "ItemIcon_3470000" },
  "confirmed": { "103464": "ItemIcon_3467000" },
  "rejected": { "108710": "slot 8 sprites are three separate runs" }
}
```

`confirmed` entries are hand-checked against the game and the generator **never** overwrites
them. `derived` is regenerable. `rejected` items render the missing-icon placeholder.

### 3. Add `--check` to the generator

Re-derives and compares against the frozen file. Fails loudly on any disagreement, and fails on
any `confirmed` entry the derivation contradicts. This is the regression test the repo does not
otherwise have.

### 4. Verify by eye, slot by slot

Contact sheets, as used to find this bug — `extracted/_sheets/helm_proposed.png` is the helm one.
Nothing graduates from `derived` to `confirmed` without a human looking at it.

**Ask.** The user plays the game and is the only source of truth here; the whole bug surfaced
from one observation and was pinned down by four. Hand over a labelled sheet with the current
answer already on it and ask which cells are wrong — that is a few seconds of their time and it
is the only thing that can turn `derived` into `confirmed`. Do not sit on an inference because
asking felt like an interruption.

Order: helm (21 entries still unchecked), then armor, necklace, gear. **Weapon, boots and ring
should render the placeholder until checked** — their alias-less tails are far too spread out
for rank alignment to be trustworthy, and a wrong icon is worse than no icon. Core is rejected
outright.

### 5. Propagate

Re-run `build_equipment.py` and `build_guide.py`, republish the artifact, and correct the
"Finding an item's icon" sections in [CLAUDE.md](CLAUDE.md) and [README.md](README.md) — both
currently state the broken rule as fact.

## Verification

1. `--check` passes on a clean tree.
2. The four observed helmets resolve to `3467000` / `3470000` / `3472000` / `3473000`.
3. `build_equipment.py` prints a `with icon` count that drops (weapon/boots/ring/core move to
   placeholder) rather than rises — a rise would mean guesses were added.
4. The guide's Early-gear block shows the right hat.

## Known limits, to state rather than hide

- The mapping stays an inference for every slot no human has checked.
- ~140 equipment icons are genuinely absent from the APK and no mapping will conjure them.
- If Chillyroom adds or removes art in a patch, every `derived` entry in that slot shifts.
  That is what `--check` is for.
