DAILY DRESS SKIN STYLER
=======================

Double-click "Open Daily Dress Skin Styler.bat".

This opens the bright QML studio, separate from the older Tkinter workbench.
Browse your real skins, drag/scroll the full-width bottom carousel, use arrow
keys, rotate/zoom the preview, sort/category, filter, and set a reference.
Undo/redo are available from the top bar and Ctrl+Z/Ctrl+Y.
Metadata autosaves only under dev-workspace/styler. Original PNGs and Minecraft
sync files are never changed by this studio.

START WITH A STYLE REFERENCE
Pick a skin from the carousel and click Use selected skin as reference.
Its detected hair color and face tone become the wardrobe’s shared colors in
one undoable step. Eyes are not switched on by this action. If eyes are already
set to follow the style reference, they continue following it.
Browse other skins in Styled or Compare; use Edit Color Areas on individual misses.

QUICK WARDROBE REVIEW
Choose Review Unsorted above the carousel. Press 1 for Favorite, 2 for Keep,
3 for Maybe or 4 for Remove. Each decision saves and moves to the next
undecided skin. Ctrl+Z restores the last decision and returns to that skin.
The review queue ignores browsing filters; Back to wardrobe restores them.

Outside Review the selected skin stays put. If a decision takes it out of
the current filter, it stays visible until you browse away or change filters.
Kept shows Favorite and Keep. Maybe and Removed can be revisited through their
own filters. Categories are independent; Unsort clears a decision without
changing the category.

Old Keep clicks were stored as Unsorted and cannot be distinguished from no
decision. No saved decisions are rewritten. Local wardrobe preparation skips
Maybe and Remove; the legacy All batch still accepts Unsorted so old wardrobes
aren't silently emptied.

EDITING IN THE STUDIO
The preview starts in Compare. Use Original / Compare / Styled under the character. Drag the divider or
rotate the model in Compare. The material tabs stay at the top of the
Inspector; only the selected material’s controls are shown.
Hair and skin tone match the style reference by default when it has a usable
color. Eyes, outfit, and accessories start off. Choose a color or use the
corresponding toggle for this skin. Turn off a material to restore the
artist’s colors and keep your swatch for later. Recent colors and eye designs are reusable.
A shared style reference supplies colors to skins you choose to match.
Duplicate look makes another studio entry from the same original PNG, with
its own styling, pixel corrections, arm model, and sorting decision.
Use the Arms menu to choose Auto, Slim (3 pixels), or Regular (4 pixels)
for the selected skin. Daily Dress remembers overrides per skin.

- Edit Color Areas opens in 3D when the local viewport is available. Hover over
  the model to outline the exact pixel. Left-drag marks the selected material.
  Click the faded skin or arrow at either edge to move through the current
  wardrobe view. Edits autosave as you go, and the editor stays open.
  Right-click restores automatic detection and middle-drag rotates the model.
  Zoom with the wheel or +/− and use Fit to reset the zoom. Transparent overlays
  allow picking the visible layer beneath them. Choose Base layer only to edit
  hidden pixels or Outer layer only to work on the overlay. Corrections and undo are
  shared with the texture editor.
- Use Compare in the 3D editor to drag the divider between original and styled
  while editing. Body parts lets you hide individual limbs, head, or torso for
  access to covered surfaces. Show all restores the view.
- To fix many pixels at once, choose a material and turn on the Match color
  wand beside the material buttons. Each pick assigns all exact matches of
  that original color across both layers in one undoable edit. Leave it on to
  pick more shades, or click it again to return to the brush. Right-click
  restores automatic detection for individual pixels.
- Show texture opens the flat editor, which is also the fallback when 3D is
  unavailable. Pick a material and
  left-drag to reassign it. White corner marks indicate manual corrections.
  Right-drag restores auto-detection. Filter the overlay by material, view
  Automatic only, or hide it. Zoom with the wheel or +/-; pan with middle-drag
  or the Pan tool. Select area and Revert area clear only corrections in the
  box. Revert all fixes clears every correction for that skin. Both ask first.
  Part labels toggles the guides on the flat texture.
- Eyes can follow the main reference, use another selected skin, load the
  saved legacy eyes, or start from the Soft lashes preset. Design Eyes lets
  you paint iris, liner/lashes and whites, mirror the strokes, and save/load
  named designs for this wardrobe. A saved design keeps its eye template even
  if the reference skin moves. Over-bangs and 3D lashes stay independent.
- Hair, Skin Tone, Outfit and Accessories each have a swatch, HEX input, and
  recent colors. Click the swatch or color wheel to open the color chooser.
  The eyedropper samples one texture pixel and also offers the detected hair
  or face color where applicable. Click the reference hair swatch to use
  that color on the selected skin. Skin Tone has its own reference/custom selector.
  Outfit and Accessories report when their mask is empty.
- The close button or Esc leaves an editor at the current skin.

Styles and corrections autosave per skin. Named eye designs are shared within a wardrobe.
The renderer updates one skin in the background, not the entire wardrobe.
The QML studio does not generate or publish the Minecraft outbox. The older
workbench and its existing sync workflow still run with:
python tools/skin_styler_gui.py

LOCAL WEBGL VIEWPORT
From the project folder, build the optional local preview once:

  npm ci --prefix tools/viewport --ignore-scripts
  npm run build --prefix tools/viewport

Restart the launcher. If the bundle, Qt WebEngine or WebGL is unavailable,
the original preview and texture editor still work. No web server, Electron,
or internet connection is used to render skins after the build. Pass
--software-preview to the launcher to force the original preview.
See tools/viewport/ATTRIBUTION.md for Lynn's contribution and the included
Three.js license. No original model or skin assets from Lynn's repo are shipped.

SAFE DAILY DRESS TEST PLAYGROUND
--------------------------------

`Run Daily Dress Test Server.bat` and `Run Daily Dress Test Client.bat` start
an isolated Fabric development server/client. Their files stay in
`dev-workspace/26.3/server` and `dev-workspace/26.3/client`, separate from the
regular Modrinth runtime and live server. A fresh empty test server requires
EULA acceptance; the verified ROSES clone inherits your existing acceptance.
The launcher does not accept it for you. Start the server first, then use Multiplayer in the test client
to join `localhost:25566`. The test server is local-only and has no connection
to the live server.

The 26.3 test server is copied from the newest verified existing ROSES backup
in D:\ROSES_AUTO_BACKUPS by `Initialize Roses Test Server.ps1`. That script
refuses to replace an existing test directory. It never changes ROSES or its
backup slots. `DD-TEST-SOURCE.json` in the test directory records its source.
FastBack history and obsolete runtimes are excluded. Fabric API, Fabric
Tailor, and the development DD build are supplied by Gradle.

The launcher checks for Python and Pillow and offers to install Pillow when it
is missing. The app is non-destructive: source PNGs are never moved, renamed,
copied into organizer nests, recolored in place, or deleted.

THE EXISTING TKINTER WORKBENCH FLOW (not yet migrated to QML)
----------------------

1. Choose Source wardrobe. The top-right workbench confirms "Found N skins".
2. Organize before sync. The complete searchable, filterable wardrobe library
   is embedded below the live preview—there are no quick picks or separate
   gallery windows. Favorite/Maybe/Remove/Unsorted and categories save
   immediately, and each decision moves to the next skin.
3. Use the Working set menu for all kept skins, favorites, a category, or a
   favorite + category combination. Removed skins are not generated.
4. Choose one Reference skin. That one click sets the preview, starting hair
   color, and reference eyes together. Refine colors or eyes only if wanted.
5. Switch the lower panel between Wardrobe, Reference, Eyes, and Re-designate.
   Hair/material detection is automatic; there is no detection slider.
6. Re-designate takes over the right panel with a large texture. Paint only
   incorrect Hair, Skin, Outfit, Accessory, Eyes, or Ignore pixels. Right-click
   restores auto-detection, and edits save automatically.
7. Reference also contains an exact-pixel hair-color sampler for unusual
   palettes. "Sample selected skin" can set exposed-skin tone.
   For a hood or helmet with no visible hair, use the dedicated checkbox.
8. Arm model defaults to automatic per-skin detection; Slim and Classic are
   available as saved overrides for mixed-format wardrobes.
9. Optional outfit and accessory hue changes preserve palette spacing,
   highlights, shadows, and multicolor relationships. Black hair is colorized
   instead of being silently skipped.
10. Inspect every kept skin in the embedded library and live 3D viewer. The
    styled wardrobe and optional personal sync outbox auto-save in the
    background after changes settle. Output is flat and includes metadata for
    favorites, categories, and arm models.

IN ROSES
--------

Join Roses after preparing sync. The mod uploads the outbox only for the
authenticated Minecraft account that joined. The server validates and backs up
the previous personal wardrobe before replacing it.

Useful commands:

  /dailydress status
  /dailydress next
  /dailydress batch
  /dailydress batch all
  /dailydress batch favorites
  /dailydress batch seasonal
  /dailydress batch favorites+casual
  /dailydress flag optional note here

A batch selection persists across restarts and controls the pool used after
sleep. If a requested batch has no matching synced outfits, Daily Dress keeps
the current batch and explains the problem.

Reviewed material pixels (Edit Color Areas)
--------------------------------------------
In the 3D editor, choose Hair, Skin, Eyes, Outfit, Accessories or Ignore,
inspect the current angle, and select Looks good! Rotate and repeat; approvals
accumulate. Undo approval removes only the chosen material visible from the
current angle. Hidden body parts/layers and pixels covered by other geometry
are not approved. A pixel is included only if its center projects on screen and
the transparent-aware picker hits that exact face and texel first. Thin visible
slivers with hidden centers are omitted. Approvals only cover already classified
pixels of the chosen material; paint mistakes first. In Compare mode both
halves count as visible, subject to each half's actual displayed transparency.

Approvals live in the top-level approvals section of wardrobe-picker-state.json,
separate from correction maps and source images. Each record includes source
path and SHA-256, the SHA-256 of the detector source file, the resolved arm
model, schema version, and coordinate-to-label/approval-time entries. Manual
edits invalidate approvals for changed coordinates. Changing arm model clears
that skin's approvals. A changed source or detector hash makes older approvals
ineligible for use; comparing effective current labels is also necessary before
export. An exporter should verify identity and compare every stored label with
the current effective classification, and skip mismatches; never infer labels
for unapproved coordinates. No training or automatic export is performed.
