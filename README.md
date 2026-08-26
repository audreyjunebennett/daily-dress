# Daily Dress

Daily Dress is a tiny Fabric 26.2 companion for [Fabric Tailor](https://github.com/samolego/FabricTailor).
When an enabled player successfully sleeps through the night, it selects a random 64×64 PNG skin,
avoids the previous outfit, applies it as a server-visible skin, and remembers the result across restarts.

## Commands

- `/dailydress on` — opt in
- `/dailydress off` — opt out
- `/dailydress next` — change immediately (useful for testing)
- `/dailydress flag [optional note]` — quarantine the current file version and immediately change outfits
- `/dailydress flags` — show how many outfits you have flagged
- `/dailydress status` — show status, wardrobe size, and model
- `/dailydress reload` — reload `config/daily-dress/config.json`

Each personal server wardrobe lives in `config/daily-dress/wardrobe/players/<player UUID>`. The
joining player's authenticated UUID selects the folder; one client can never choose another player's
destination. Generated MineSkin texture properties are cached in `config/daily-dress/state.json`, so
an outfit is uploaded only once.

Flagging records the player, filename, timestamp, content hash, and optional note in
`config/daily-dress/FLAGGED OUTFITS.json`. That exact PNG version is excluded for that player.
Regenerating or replacing the file changes its hash, so a corrected version becomes eligible
automatically without manually clearing old feedback.

### Adding and removing outfits

The Skin Styler writes a complete personal set to the client's `config/daily-dress/sync-outbox`.
While connected to a compatible server, the client watches that folder and securely uploads a changed
set through Fabric's authenticated play connection. The server validates archive size, paths, count,
hash, and every 64x64 PNG; backs up the previous UUID folder; and replaces it atomically. No server
restart, server-folder access, or host intervention is needed.

The server scans the player's personal folder each time an outfit is selected. Removing a PNG keeps
it out of future selections but does not change an outfit already being worn. The old shared folder
can remain as an inactive safety copy when `includeSharedWardrobe` is false.

The default model is slim/thin. Fabric Tailor and Fabric API are required on the logical server.

## Skin Styler

`tools/Open Daily Dress Skin Styler.bat` opens a non-destructive wardrobe tool. It detects each
skin's own hair palette from the head UV, hue-shifts the detected pixels while preserving their
brightness/shading and exact pixel shape, previews samples, and optionally replaces only facial
features from a selected reference skin. It can also sample each skin's existing face palette and
shift matching exposed-skin pixels toward a separately chosen skin tone, with a deliberately tight
tolerance to protect similarly colored clothes. New files go to a separate folder; originals are untouched.
The GUI shows immediate color swatches and a reference-face preview, restores the recommended hair
and skin tolerances with reset buttons, and prepares the sync outbox without manual copying.
