# Daily Dress 3D viewport

3D pointer picking and UV mapping are adapted with Lynn's permission from
[Blockygotchi / Minecraft Character Editor](https://github.com/lynnvfrank/minecraft-character-editor),
commit `3cdc8a956143a79cb77cf894f24634f67a738c46`, notably
`src/viewer/controls.ts` and `src/skin/coordinates.ts`.

The color area editor's visibility controls and labeled texture guides follow the approach
in Blockygotchi's [Layers panel](https://github.com/lynnvfrank/minecraft-character-editor/blob/main/src/creator/skinLayersPanel.ts)
and [skin layout reference](https://github.com/lynnvfrank/minecraft-character-editor/blob/main/docs/SKIN-LAYOUT.md).

Daily Dress uses Three.js (MIT) and its OrbitControls. The player geometry is built from
the same standard skin face layout used by Daily Dress's software preview.

`idle-clips.json` contains head and upper arm motion extracted from Blockygotchi's
Relaxed Idle and Chatting clips, based on the Universal Animation Library by
Quaternius (CC0 1.0). The rotations are expressed in world axes relative to
each clip's first frame so they can drive Daily Dress's own model.
