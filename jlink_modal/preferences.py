import bpy
from bpy.props import EnumProperty
from bpy.types import AddonPreferences


def _modal_hud_side_update(self, context):
    from .gui import tag_redraw_all_view3d

    tag_redraw_all_view3d()


class JLINK_Preferences(AddonPreferences):
    bl_idname = __package__

    modal_hud_side: EnumProperty(
        name="Modal HUD",
        description="Horizontal placement of the modal help panel in the 3D View",
        items=(
            ("LEFT", "Left", "Bottom-left of the viewport"),
            ("RIGHT", "Right", "Bottom-right of the viewport"),
        ),
        default="LEFT",
        update=_modal_hud_side_update,
    )

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        col.label(text="JLink Modal")
        col.label(text="Operators are available in Ctrl+L in the 3D View.")
        col.prop(self, "modal_hud_side", expand=True)


CLASSES = (JLINK_Preferences,)


def register():
    from bpy.utils import register_class

    for cls in CLASSES:
        register_class(cls)


def unregister():
    from bpy.utils import unregister_class

    for cls in reversed(CLASSES):
        unregister_class(cls)
