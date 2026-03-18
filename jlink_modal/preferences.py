import bpy
from bpy.types import AddonPreferences


class JLINK_Preferences(AddonPreferences):
    bl_idname = __package__

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        col.label(text="JLink Modal")
        col.label(text="Operators are available in Ctrl+L in the 3D View.")


CLASSES = (JLINK_Preferences,)


def register():
    from bpy.utils import register_class

    for cls in CLASSES:
        register_class(cls)


def unregister():
    from bpy.utils import unregister_class

    for cls in reversed(CLASSES):
        unregister_class(cls)
