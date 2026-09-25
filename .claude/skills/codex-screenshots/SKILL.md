---
name: codex-screenshots
description: Turn the user's in-game Codex of Equipment screenshots or screen recordings into confirmed icon, effect-text and weapon-type entries (guide/icon_map.json, guide/effect_map.json, guide/weapon_types.json). Use when the user shares PNGs/MP4s from "Soul knight prequel/", when version_diff asks for screenshots, or when deciding what to ask the user to capture.
---

# Codex screenshots → confirmed data

The screenshot is the only ground truth for item → icon, item → effect text, `{n}` values,
`$token$` meanings and weapon type. These all live in the encrypted config (see
`docs/icons.md` and `docs/effects.md`). One codex page shows the item's icon, its name, and
its effect with every token expanded and every `{n}` filled in at Lv.1.

## Screenshots

```bash
PYTHONIOENCODING=utf-8 python tools/match_screenshot_icons.py "Soul knight prequel"/*.PNG
```

The tool pixel-matches the icon against every extracted 20×20 item sprite, and it works at any
resolution.

- **Score.** A correct match scores 0–31, and the runner-up scores 55+. The tool prints `UNSURE`
  when the gap is too small.
- **Output.** For each shot it prints the winning sprite, its score, and the item that currently
  claims it.

Then, per screenshot:

1. **Read the item name** off the image.
2. **Icon.** Add a `confirmed` entry to `guide/icon_map.json`. No tool rewrites these.
3. **Effect text.** Find the key by phrase in `localization_all.json`, then add the item → key
   pair to `guide/effect_map.json`, with the `lv1` values that the screen shows for `{0}`,
   `{1}`, …
   - Several texts have 2-4 near-duplicate keys: older wording, a "Chip" twin, or an alternate
     version.
   - Pick the one whose wording matches the screenshot, never the first regex hit.
4. **Tokens.** New `$token$` meanings go in `guide/ranger.json`'s glossary.
5. **Rebuild:**
   `python tools/build_icon_map.py && python tools/build_equipment.py && python tools/build_guide.py`
   (or `python tools/pipeline.py --from build_icon_map`).

## Screen recordings (cheapest way to cover a whole slot)

A recording of the user tapping › through one codex category covers the slot in one go.
Non-weapon legendary descriptions can only be linked this way. Frames come out landscape at
2868x1320, so the matcher works on them unchanged.

```bash
FF=$(python -c "import imageio_ffmpeg as f; print(f.get_ffmpeg_exe())")   # pip install imageio-ffmpeg
"$FF" -i "Soul knight prequel/<video>.mp4" -vf fps=4 frames/f_%03d.png
python tools/match_screenshot_icons.py frames/*.png --top 1
```

- **Longer videos.** Sample at 10 fps and split the frames into stable pages by frame
  differencing.
- **Text.** Read it by eye from crops of the name and the effect panel, then find it in the
  localization by phrase.
- **Where the frames go.** Put them in the scratchpad, not the repo.

Past runs, 2026-09-22:

- **Necklaces.** One 17 s video covered all 26 legendary necklaces.
- **Other slots.** One 75 s video covered 113 legendaries across Helm, Armor, Boots, Ring,
  Mech Core and Cubis Core.
- **Gaps.** 19 screenshots (IMG_6280-6298) filled every roster name the video skipped.

So every legendary armor, helm, boots, ring, gear and core piece in the `Affixia` roster has its
text. **Weapons need no recording.** Legendary weapons pair one-to-one with a class skill (see
`docs/effects.md`).

## Per-tab grid screenshots → weapon type

`guide/weapon_types.json` was built from one screenshot per weapon-type tab (IMG_6261-6273),
mapping each cell's sprite to its item through `icon_map.json`.

- **Grid geometry on a 2868x1320 shot:**
  - 8 columns, pitch 229.4 px;
  - rows at y = 325 / 771 / 993;
  - rightmost cell origin at x = 2165;
  - 6.48 px per sprite pixel.
- **Owned vs unowned.** Owned cells match in colour. "Unowned" cells are greyscale, so match
  them on luminance correlation over sprite rows 0-12, because the label covers the rest.
- **Axial Incarnate medallions** have a rarity rim, so match the inner disc only.

## Leaderboard profile screenshots → the 8 items a player wears

```bash
PYTHONIOENCODING=utf-8 python tools/match_profile_icons.py "Soul knight prequel"/IMG_6312.PNG
```

Slot layout, scoring and the fallback for icons not in the APK are in `docs/icons.md`
("Leaderboard profiles"). Put the build write-up in a guide JSON (`guide/leaderboard.json`
is the template): one section per player plus what they share.

## Asking the user

The user plays the game and can check anything on screen. Make each question cheap to answer:

- **Let them point.** Render a labelled contact sheet into `extracted/_sheets/`: a grid of
  upscaled PNGs with the sprite name and the item that claims it under each cell. "Which of
  these is the Tophat" takes five seconds. "What is the Tophat's icon ID" does not.
- **Propose, don't ask open-ended.** Give the current answer and ask whether it matches.
- **Ask for a few spot checks, not an audit.** Pick items that bracket runs of unknowns: two
  screenshots with equal offsets settle everything between them (see `docs/icons.md` for
  where the gaps are).
- **Say what is still missing.** The output marks unrecoverable values with a `?` chip and
  missing icons with a placeholder, so nothing looks confirmed when it isn't.
- **Put requests in a numbered "Your action" block.** Never ask for `{n}` values on their own;
  they come with the screenshot.

Write every answer where it cannot be lost: a `confirmed` entry, a line in `docs/`, or a test.
An observation that only exists in chat will be lost.
