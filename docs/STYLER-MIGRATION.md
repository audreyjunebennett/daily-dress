# Daily Dress studio migration

## Agreed design

Bright, cheerful, tactile digital wardrobe. Compact top bar; large interactive
character stage; contextual/collapsible right Inspector; full-width bottom
wardrobe. Readable typography, gentle lavender interaction accent, crisp pixel
renders. No perpetual decorative movement and no fake working controls.

Ruby's later clarification overrides the example in the original brief:
the bottom carousel follows a very shallow **downward-facing U**: its middle
is lower than its edges. Selection rises only a few pixels from that baseline.

This is a persistent studio, not a numbered export wizard. Changes save quietly.
Original skins stay untouched. During development, nothing silently publishes
to the live Minecraft wardrobe or changes the regular Modrinth client.

## Boundary and preserved code

- `skin_styler_core.py`: existing normalization, detection, transformations and
  3D rendering remain the image-processing backend; no rewrite for presentation.
  One backward-compatible extension allows `style_skin(..., target_hair_color=None)`
  to disable hair recoloring while preserving hair/bang protection for eye transfer.
- `wardrobe_picker.py`: existing metadata format remains compatible. PickerState
  now accepts an optional state directory; its established default is unchanged.
- `skin_styler_gui.py` / `integrated_workbench.py`: the complete Tkinter application
  remains available. UI variables, dialogs, preview scheduling, and editor widgets
  are coupled to Tkinter and need adaptation, not direct reuse as QML widgets.
- `daily_dress_qml.py`: Python QObject properties/signals/slots own selection,
  filters, metadata/history, local persistence, and image-provider requests.
  QML owns layout, gestures, scrolling physics, and transitions.

## Current shell

- Real PNG library, source chooser, large preview, drag rotation, zoom/reset.
- Native ListView drag/inertia/snap/elastic ends; keyboard, wheel and card clicks.
- Responsive full-width bottom tray; downward U; selection/hover elevation.
- One composable search/status/category filter; model rows updated in place.
- Favorite/Maybe/Keep/Remove, categories, reversible decisions.
- Persistent reference identity/thumbnail plus face and hair swatch.
- Use selected skin as reference applies wardrobe-wide hair and face tone in
  one undoable edit. The hair sample uses final material masks and pixel
  corrections. Existing eye settings are kept; eyes set to follow the style
  reference continue following it.
- Hair toggle, color picker/hex, visual hue/saturation/lightness sliders, sample
  selected skin and restore reference color; actual styled preview.
- Reference-eye transfer, eyes-over-bangs and keep-3D-lashes controls.
- Skin-tone toggle, color picker/hex, selected-skin sampling.
  From reference samples the reference face (not the old peach preset or hair).
  Custom color is separate; sampling the selected skin switches to custom mode.
  Applying an already-matching tone preserves the original shading unchanged.
- Light input palette and explicit dark hex text remain readable under Windows
  dark mode; selection uses lavender with white selected text.
- Styled/Original and an aligned draggable before/after comparison wipe.
- Extra-long hair tracing stitches aligned leg UVs across the waist and center
  seam, including base/outer layers. It requires a proven calf-length strand;
  ambiguous flesh-like palettes, broad garment panels and short hems stay out.
- Styling/reference edits share undo/redo; a slider gesture is one history entry.
- `studio_preview.py` runs the existing backend in one background worker, coalesces
  to the newest request, rejects stale frames, and keeps the last image visible.
  A bounded texture cache avoids re-classification on rotation.
- Metadata autosave to `dev-workspace/styler`; no source image or outbox writes.
- Edit Color Areas edits the existing per-skin correction map. It includes filtered
  automatic/effective masks, marked corrections, a live preview, fit/zoom/pan,
  and confirmed area/all reset. Each brush stroke is one undo step.
- Design Eyes uses the legacy iris/liner/white segmentation, palette retargeting
  and mirror mapping. Uses a separate skin, a preset or the legacy saved eyes;
  named designs and all color controls autosave per source wardrobe. Named
  designs carry the editable eye band, not a link to the original PNG.
- Outfit and Accessories have independent tint targets and masks, with
  no-pixels indicators. Shared controls support HEX, picker, HSL, recent
  swatches and exact sampling. Only the selected skin is rendered on changes.
- Python backend and QML integration tests, including native drag/key selection,
  filter/history/persistence, source-cache invalidation, editor input, and
  returning to the same comparison and carousel state.

For Windows QA, reuse the prepared Offstage launcher and run the Python suite
with `QT_QPA_PLATFORM=windows` and `DAILY_DRESS_REQUIRE_OFFSTAGE=1`.
`DAILY_DRESS_QA_SHOTS` optionally captures editor snapshots to a scratch folder.
The batch launcher accepts `--source`, `--state-directory` and `--check-launch`
for a native window smoke check on Offstage without touching studio state.

## Next migration steps

1. Per-skin arm/hood/helmet controls. The renderer already reads those overrides.
2. Optional 3D viewport now uses Three.js and Lynn's picking approach.
   Original / Compare / Styled share one camera and Edit Color Areas can mark or
   restore visible material hits without changing the original PNG.
   The software renderer and 2D atlas remain available as fallbacks.
3. Local styled output and explicit development-only Minecraft sync settings.
   Existing account-separated sync remains unchanged in the older workbench.

## 26.3 test status

Java 25 is project-pinned; Gradle build/tests, client start/clean exit, and a
server start/clean stop passed in the earlier Minecraft test.
The test server is an independent copy of the newest verified existing ROSES
backup from D:, stored inside `dev-workspace/26.3/server`. No DD backup was
created on D:. Provenance and copied-file hashes are in `DD-TEST-SOURCE.json`.
Public connections, RCON/query/management and backup launchers are disabled/omitted.

Still required: connected-client wardrobe sync and sleep-triggered outfit change
tests. The reported black-screen flash is not fixed yet. The current Tailor
skin application requests a player refresh; verify a safer visual update path
in the isolated multiplayer environment before changing that behavior.

Never deploy this development build to ROSES or send it to Lynn as ready until
those gameplay checks and the relevant styling feature migrations pass.
