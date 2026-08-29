# Daily Dress

Daily Dress is a Fabric 26.2 companion for [Fabric Tailor](https://github.com/samolego/FabricTailor).
After an enabled player sleeps through the night, it chooses another outfit from that player's private
wardrobe, avoids the previous outfit, and applies it as a server-visible skin.

## In-game commands

- `/dailydress on` and `/dailydress off` — opt in or out
- `/dailydress next` — move forward after using `previous`, or choose a new outfit
- `/dailydress previous` — return to the previous available outfit
- `/dailydress status` — show the active batch, eligible/total outfits, flags, and model mode
- `/dailydress batch` — query the collection used after sleep
- `/dailydress batch all` — use every kept outfit
- `/dailydress batch favorites`, `casual`, `seasonal`, `dresses`, or `other` — use one saved collection
- `/dailydress batch favorites+casual` — combine favorite status with a category
- `/dailydress flag [optional note]` — quarantine the current PNG version and change outfits
- `/dailydress flags` — count quarantined versions
- `/dailydress reload` — reload `config/daily-dress/config.json`

Personal server wardrobes live in `config/daily-dress/wardrobe/players/<player UUID>`. The joining
player's authenticated UUID chooses the destination, so one client cannot replace another player's
wardrobe. Generated MineSkin texture properties and each player's outfit history are persisted in
`config/daily-dress/state.json`.

The Styler writes a complete personal set to the client's `config/daily-dress/sync-outbox`. While
connected to a compatible server, the client sends changed PNGs and their favorite/category/model
metadata through Fabric's authenticated play connection. The server validates paths, sizes, counts,
hashes, metadata JSON, and every 64×64 PNG, then backs up and atomically replaces that player's set.

`skinModel` in the server config accepts `auto` (recommended), `slim`, or `classic`. Auto mode honors
per-skin Styler overrides and otherwise detects the arm format from the PNG.

## Minecraft-themed Skin Styler

Run `tools/Open Daily Dress Skin Styler.bat`. The main workbench now combines the important flow:

1. Choose the source wardrobe. The app confirms how many PNG skins it found.
2. Sort inline or open the full gallery. Favorite/Maybe/Remove/Unsorted and Dresses/Casual/Seasonal/Other
   save as lightweight metadata; originals are not moved, copied, renamed, or edited.
3. Cycle skins in the large rotatable original → styled 3D viewer. The styled quick-pick strip follows
   the selected working set, including favorite + category combinations.
4. Choose a Hair Gallery reference. Its detected palette becomes both the preview basis and starting
   **Target Hair Color**. An in-skin eyedropper and normal color chooser are also available; hue,
   saturation, and lightness sliders remain refinement tools.
5. Choose eyes from Eye Gallery or use the pixel-level Eye Designer. A selected skin can also supply
   the target exposed-skin tone.
6. Leave auto-tuned detection enabled for good per-skin defaults. For a difficult skin, open **Fix pixel
   categories** and paint sparse Hair/Skin/Outfit/Accessory/Eyes/Ignore corrections. Hooded or helmeted
   skins can be marked as having no visible hair with one click.
7. Optionally recolor outfit and hair-accessory palettes. Hue rotation preserves each material's
   relative color and shading relationships instead of flattening multicolor designs.
8. Preview the kept working set, generate one flat output folder, and prepare sync once the whole round
   looks right.

Dark and black hair is colorized explicitly rather than being skipped as a neutral palette. Textured
hair uses adaptive tolerance, long hair is traced across safe torso/shoulder seams, and skin/outfit
classification remains constrained to Minecraft UV regions. All manual corrections are sparse metadata;
the original PNG collection remains untouched.

## Development

Python tests:

```powershell
python -m unittest discover -s tools -p 'test_*.py'
```

Fabric build (Java 25):

```powershell
./gradlew.bat build
```

Fabric API and Fabric Tailor 2.10.0+ are required on the logical server. The mod targets Minecraft 26.2.
