# JLink
JLink is an addon for Blender that adds additional functionality to the link/transfer data menu (Ctrl L).

What you'll see:

![preview](https://i.imgur.com/DGc9Dbh.png)

At the bottom there are 5 new buttons. **Set Origin Rotation from Face** is **modal** — you can preview the result and flip axes before committing.

## Location
Transfers location from active object to selection.

## Rotation
Transfers rotation from active object to selection.

## Scale
Transfers scale from active object to selection.

## All Transforms
Transfers location, rotation and scale from active object to selection.

## Set Origin Rotation from Face
Sets your selected objects' rotation to that of the selected face, maintaining scene position.

---

## Modal Usage

When you run Set Origin Rotation From Face

1. **Preview** - The transform is applied immediately so you can see the result.
2. **Selection** - Press **Left Mouse** to select faces for the origin rotation to be taken from.
3. **Flip axes** - Press **X**, **Y**, or **Z** to flip that axis (negate). Each key toggles on/off.
4. **Confirm** - Press **Enter** or **Space** to keep the changes.
5. **Cancel** - Press **Escape** or **Right Click** to revert to the original state.

A GPU overlay in the bottom-left of the 3D viewport shows the current flip state and hotkey hints.

---

## Package Layout

The addon now uses a standard Blender package layout:

- `jlink_modal/__init__.py` - addon entry point (`bl_info`, register/unregister)
- `jlink_modal/operators.py` - modal operators and Ctrl+L menu integration
- `jlink_modal/gui.py` - GPU viewport overlay and axis/face drawing
- `jlink_modal/preferences.py` - addon preferences panel
- `jlink_modal/keymaps.py` - keymap registration scaffold
- `jlink_modal/blender_manifest.toml` - blender manifest toml framework for addon
