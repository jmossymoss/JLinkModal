bl_info = {
    "name": "JLink: Link Transforms",
    "author": "Jac Rossiter, Jordan Moss",
    "description": "Adds Link Transforms to Link Menu (Ctrl L) - GPU Modal Set origin rotation from face",
    "blender": (4, 5, 0),
    "version": (1, 0, 1),
    "warning": "",
    "category": "Object",
}


if "bpy" in locals():
    import importlib

    importlib.reload(gui)  # type: ignore[name-defined]
    importlib.reload(preferences)  # type: ignore[name-defined]
    importlib.reload(keymaps)  # type: ignore[name-defined]
    importlib.reload(operators)  # type: ignore[name-defined]
else:
    from . import gui, keymaps, operators, preferences


def register():
    preferences.register()
    operators.register()
    keymaps.register()


def unregister():
    keymaps.unregister()
    operators.unregister()
    preferences.unregister()
