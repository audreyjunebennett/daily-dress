DAILY DRESS SKIN STYLER
=======================

Double-click "Open Daily Dress Skin Styler.bat".

The launcher checks for Python and Pillow and offers to install Pillow when it
is missing. The app is non-destructive: source PNGs are never moved, renamed,
copied into organizer nests, recolored in place, or deleted.

THE NEW WORKBENCH FLOW
----------------------

1. Choose Source wardrobe. The top-right workbench confirms "Found N skins".
2. Organize before sync. The complete searchable, filterable wardrobe library
   is embedded below the live preview—there are no quick picks or separate
   gallery windows. Favorite/Maybe/Remove/Unsorted and categories save
   immediately, and each decision moves to the next skin.
3. Use the Working set menu for all kept skins, favorites, a category, or a
   favorite + category combination. Removed skins are not generated.
4. The large original-to-styled 3D viewer updates for the selected skin. Drag
   left/right to rotate. Switch the lower panel between Wardrobe, Hair, Eyes,
   and Pixels without losing the live preview.
5. Hair contains the complete hairstyle library plus an exact-pixel sampler.
   Choose still opens a normal color dialog; Hue/Saturation/Lightness refine.
6. Eyes contains the complete face library and custom eye pixel designer in
   the same panel. "Sample selected skin" can set exposed-skin tone.
7. Auto-tune per skin is the recommended detection default. For edge cases,
   switch to Pixels and paint only incorrect Hair, Skin, Outfit, Accessory,
   Eyes, or Ignore pixels. Right-click restores auto-detection, and edits save
   automatically.
   For a hood or helmet with no visible hair, use the dedicated checkbox.
8. Arm model defaults to automatic per-skin detection; Slim and Classic are
   available as saved overrides for mixed-format wardrobes.
9. Optional outfit and accessory hue changes preserve palette spacing,
   highlights, shadows, and multicolor relationships. Black hair is colorized
   instead of being silently skipped.
10. Inspect every kept skin in the embedded library and live 3D viewer, then
    Generate + prepare sync. Output is flat and includes metadata for
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
