# Daily Dress — Future Tweaks and Testing Notes

This is the running list for observations found during ordinary Styler and in-game use. Add screenshots and skin filenames when a problem is specific to one skin.

## 2026-08-22 — Eye-layer controls and wording

### Observation

The option currently labeled **“Show eyes / eyeliner over bangs (base face layer only)”** appears to affect the second/outer head layer too. The result looks useful, but the wording does not explain everything the Styler is doing.

### What the current controls actually do

- **Match eyes from the reference skin** is the master eye-edit switch. When it is off, the selected/designed eye shape and its hue, saturation, brightness, liner, and eye-white settings are not applied. Each destination skin keeps its original eyes.
- **Show eyes / eyeliner over bangs (base face layer only)** writes the designed eyes and liner to the base face layer, even where base-layer bangs occupied those pixels. It does not paint the full designed eyes onto the outer/hat layer. To make the base eyes visible, it can also clear outer-layer pixels directly in front of the incoming eye design.
- **Keep existing 3D hat-layer lashes** preserves dark lash/liner pixels that the destination skin already has on its outer/hat layer and recolors those pixels to the selected liner color. When off, those old outer-layer eye accents can be cleared so they do not cover or conflict with the designed base-layer eyes.

This means the first layer option really can cause a visible change to the outer layer, even though the designed eye artwork itself remains on the base layer. Ruby’s observation is correct; the current label is technically narrow and easy to misunderstand.

### Possible clearer future interface

Keep the behavior, but present it as three plainly separated decisions:

1. **Apply my designed eyes** — master switch for the selected eye shape and colors.
2. **Reveal designed eyes through base-layer bangs** — overwrites base-layer bang pixels only where the eye design needs to show.
3. **Outer-layer lashes** — a small choice between:
   - **Preserve + recolor existing outer lashes** (current default and usually the prettiest result), or
   - **Clear outer lashes near the new eyes** (use when the detected pixels are really bangs or look strange).

Potential later enhancement: an advanced per-skin preview override for whether outer-layer lash pixels should be preserved. This would help with skins whose artists intentionally draw eyelashes on the hat layer without making the everyday interface more complicated.

### Decision for now

Do not change the rendering behavior yet. It is currently producing the desired look. Revisit the labels/control grouping after more real-world wardrobe testing.

## 2026-08-22 — Previous outfit / wardrobe history

### Requested behavior

Add `/dailydress previous` as the opposite of `/dailydress next`. It should restore the outfit the player wore immediately before the current one, whether the current outfit was selected by sleeping through the night or by using `/dailydress next`.

Useful details for the eventual implementation:

- Keep a short per-player outfit history rather than remembering only one filename.
- Allow moving backward more than once when useful; ideally `/dailydress next` after going backward should move forward through that history before choosing another random outfit.
- Persist the history across server restarts so a restart does not erase the ability to undo the morning’s outfit change.
- If a historical skin has since been removed from that player’s wardrobe, safely skip it and try the next available earlier entry.
- Never let automatic sleep rotation or random `next` selection wear the same outfit twice in a row.
- Consider `/dailydress current` later so the player can see the current skin filename when reporting or editing a strange one.

Possible friendly wording after the command: **“Changed back to your previous outfit.”** Keep ordinary automatic morning changes silent, as they are now.
