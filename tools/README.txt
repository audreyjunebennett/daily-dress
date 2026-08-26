DAILY DRESS SKIN STYLER
=======================

Double-click "Open Daily Dress Skin Styler.bat".

The launcher checks for Python and Pillow and offers to install Pillow when it
is missing. The app is non-destructive: source PNGs are never moved, renamed,
copied into organizer nests, recolored in place, or deleted.

THE NEW WORKBENCH FLOW
----------------------

1. Choose Source wardrobe. The top-right workbench confirms "Found N skins".
2. Organize before sync. Favorite/Maybe/Remove/Unsorted and the Dresses,
   Casual, Seasonal, or Other category save immediately. Each decision moves
   to the next skin. The full gallery remains available for searching,
   duplicate checks, and batch sorting.
3. Use the Working set menu for all kept skins, favorites, a category, or a
   favorite + category combination. Removed skins are not generated.
4. The large original-to-styled 3D viewer updates for the selected skin. Drag
   left/right to rotate; Previous/Next and the styled quick-pick strip cycle
   through the current working set.
5. Hair Gallery is parallel to Eye Gallery: choose a hairstyle and its
   detected hair becomes the live reference plus the starting Target Hair
   Color. Use Eyedropper for an exact source pixel, Choose for a normal color
   dialog, then use Hue/Saturation/Lightness only for refinement.
6. Eye Gallery and Design eyes retain the reusable eye workflow. "Sample
   selected skin" can also set the target exposed-skin tone.
7. Auto-tune per skin is the recommended detection default. For edge cases,
   choose "Fix pixel categories" and paint only incorrect Hair, Skin, Outfit,
   Accessory, Eyes, or Ignore pixels. Right-click restores auto-detection.
   For a hood or helmet with no visible hair, use the dedicated checkbox.
8. Arm model defaults to automatic per-skin detection; Slim and Classic are
   available as saved overrides for mixed-format wardrobes.
9. Optional outfit and accessory hue changes preserve palette spacing,
   highlights, shadows, and multicolor relationships. Black hair is colorized
   instead of being silently skipped.
10. Use Preview every kept skin, then Generate + prepare sync once the full
    round is ready. Generated output is flat and includes one small metadata
    file for favorites, categories, and arm models.

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
