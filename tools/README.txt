DAILY DRESS SKIN STYLER
=======================

Double-click "Open Daily Dress Skin Styler.bat".

The launcher checks its image-library dependency. If Pillow is missing, it asks
before installing it automatically. If Python itself is missing, it gives a
clear Python download address and setup note instead of silently failing.

ORGANIZING A LARGE WARDROBE
---------------------------

Choose "Organize wardrobe…" to browse every PNG as a proper thin-model player
instead of a flat skin texture. The picker shows a large front/back view and
lets you mark each skin Favorite, Maybe, Remove, or Unsorted. Optional Dresses,
Casual, Seasonal, and Other labels make the exported folders easier to browse.
It also detects identical visible skin pixels even when two PNG files were
saved with different compression, labels matching cards with SAME, and includes
a Visual duplicates filter.

The picker saves progress automatically, so it is safe to close and continue
later. Keyboard shortcuts make a large collection quick:

  F Favorite       M Maybe       X Remove       U Unsorted
  1 Dresses        2 Casual      3 Seasonal     0 Other
  Left/Right arrows move between skins
  Ctrl+Z or Backspace undoes the last sorting decision

"Create Favorites master folder" makes a brand-new folder containing only the
favorites, grouped by outfit type. It can immediately become the Styler's new
Source wardrobe. "Create full organized copy" makes safe Favorite, Maybe,
Remove, and Unsorted copies of everything. Neither action modifies, moves,
renames, or deletes an original skin.

1. Source wardrobe should already point to C:\Users\RUBY\Pictures\Skins.
2. Choose Eye gallery to see the faces from every PNG in the current Source
   wardrobe. Search, click one for a large preview, then choose Use these
   reference eyes (or simply double-click it). The gallery closes and opens the
   Eye Designer with that exact eye geometry, asymmetry, colors, and shading
   loaded. A live full-body 3D model beside the pixel grid renders each outer
   layer as a slightly larger floating cuboid and updates with every edit. The
   window and model panel are resizable; drag left/right for a continuous 360°
   turn around the head, jacket, sleeves, trousers, and intermediate angles.
   Uncheck Show outer layers beside the Eye Designer model to temporarily hide
   the hat, jacket, sleeve, and trouser layers and inspect base-layer eyes or
   lashes underneath. This preview toggle never changes the saved skin.
   Use these eyes and Cancel remain pinned in a bottom action bar at every
   supported window size; enlarging the window gives the 3D preview more room
   without being required to reach the save action.
   Iris hue, saturation, and lightness are independently adjustable using HSL,
   so lowering saturation moves the iris toward gray instead of washing a
   bright iris toward white;
   eyeliner and lashes share one separate color because they are the same visual
   material painted in different places. The face grid is also a pixel editor:
   select Iris, Liner/lashes, Eye white, or Eraser, then click or drag inside
   either outlined eye box. Right-click always erases. Mirroring is enabled by
   default for quick symmetric edits and can be switched off for individual
   eyelashes, covered eyes, or other asymmetric designs. Ctrl+Z or the visible
   Undo button restores one complete click-and-drag stroke at a time; Redo,
   Ctrl+Y, or Ctrl+Shift+Z reapplies it. A new stroke after undo correctly
   clears the abandoned redo branch. Editor feedback stays inside a fixed,
   wrapped two-line status area so painting and history actions never resize
   the neighboring 3D preview. Only
   eye-area pixels
   are copied, so
   every destination keeps its own other facial and hair details. Browse remains
   available when you want to select a PNG without immediately editing it.
   "Show eyes / eyeliner over bangs" is on by default for the base face layer.
   "Keep existing 3D hat-layer lashes" separately preserves intentional dark
   lash shapes painted on each destination skin's second head layer and recolors
   them to the chosen liner color; turn it off when those pixels are really
   bangs. Gallery-picked eye shapes are normalized to the standard lower face
   position, leaving exactly one skin pixel beneath the bottom eye row so bangs
   do not crop tall eyes. The custom design and settings are saved next to the
   Styler and automatically reselected.
3. Choose a target hair hue, saturation, and lightness. The Styler moves the
   existing palette toward all three targets while preserving pixel-to-pixel
   shading and relative accent colors. This can distinguish sandy blonde from
   bright blonde or muted from vivid hair without flattening every shade. A
   hairband still moves to its own related new color. Dragging any slider updates
   a live original-to-styled three-quarter player model, including hair, chosen
   eyes, and optional skin tone. Drag left or right over those models to rotate
   through front/right, back/right, back/left, and front/left checks. Leave
   "Continue long hair down the
   torso/shoulders" checked to carry the same palette into connected long-hair
   strands. It maps head edges across the model's UV seams, traces vertically
   coherent shading paths, links matching strands painted across the aligned
   base and outer torso layers on the front, back, and sides, fills only tiny
   palette-matched holes touching confirmed strands, and stops at strong visual
   borders. Broad matching
   clothing—especially jackets or sleeves that happen to share the hair color—
   is penalized and protected. Choose Sample to test another full skin.
4. Optionally enable exposed skin-tone adjustment and choose its color. It has
   its own live swatch. Face color supplies the authoritative palette; the
   Styler then traces base-layer skin outward from the forehead, neckline,
   hands, thighs, and feet while stopping at collars, sleeves, waistlines,
   shoes, and other strong local edges. Pale garments and all second-layer
   clothing are protected even when their colors resemble the skin tone.
5. Optionally enable Adjust outfit and/or Adjust hair accessories. Each has its
   own hue, saturation, and brightness sliders and updates the live model.
   Outfit detection includes clothes, shoes, garment details, and outer layers
   while excluding traced skin and hair. Accessory detection separates bows,
   bands, clips, crowns, flowers, and similar bounded colors from the dominant
   hair palette. Flowers or ribbons painted down a braid/long-hair torso UV are
   included only when they stay beside confirmed hair with multiple contacts,
   so a floral print on nearby clothing is protected. Both controls are off by
   default, and all original shading/highlight relationships are preserved.
6. Use Preview styling. Every source skin appears in a scrollable gallery as a
   lightweight original-to-styled thumbnail, even in a 250+ skin master folder.
   Click any card to open one large, resizable comparison; drag anywhere in it
   for a true continuous 360° turn with physically separated outer layers. This
   keeps hundreds of thumbnails inexpensive while only rendering the selected
   pair interactively. It uses the real generation pipeline: designed eyes,
   shifted bands/accents, per-skin eye height, and that skin's own hair
   occlusion. Adjust tolerance if a preview covers too much or too little
   hair/skin. "Reset to 42" restores the recommended hair default; "Reset to
   24" does the same for exposed skin detection.
7. Leave "Prepare this wardrobe for my Minecraft account" checked, then choose
   "Generate + prepare sync". The Styler creates a separate styled
   output and safely replaces the local sync outbox for you.

When you join Roses, Daily Dress sends that outbox through your authenticated
Minecraft connection. The server stores it under the UUID of whichever account
joined. This means Audrey and Lynn can each run the Styler on their own computer
with completely different master folders, then join Roses to update only their
own wardrobe. Ruby does not need to be online and Lynn does not need a copy of
the Roses server folder.

Original skins in C:\Users\RUBY\Pictures\Skins are never modified. Timestamped
outbox backups are stored in the Modrinth profile under:

config\daily-dress\styler-backups\YYYY-MM-DD_HH-MM-SS\sync-outbox

"Generate output only" remains available when you want to experiment without
preparing anything for Minecraft.

After a successful sync, Daily Dress can use the new wardrobe immediately on the
next outfit change. Every selected outfit is applied as the slim/thin model.

IN-GAME SAFETY VALVE
--------------------
If an outfit looks wrong, use /dailydress flag to quarantine that exact PNG
version and immediately change into another. Add a useful note when possible,
for example: /dailydress flag sleeve detected as skin
Roses records the filename, player, timestamp, content hash, and note in
config/daily-dress/FLAGGED OUTFITS.json for later Styler improvements. A newly
generated version of the same filename has a different hash and is eligible
again automatically.
