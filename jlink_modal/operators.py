import bpy
from bpy.types import Operator
from mathutils import Euler, Matrix, Vector

from .gui import (
    clear_active_modal_op,
    draw_axis_gizmo,
    draw_modal_ui,
    set_active_modal_op,
    tag_redraw_all_view3d,
)


def _remove_draw_handlers(op):
    if hasattr(op, "_handle"):
        try:
            bpy.types.SpaceView3D.draw_handler_remove(op._handle, "WINDOW")
        except Exception:
            pass
    if hasattr(op, "_handle_gizmo"):
        try:
            bpy.types.SpaceView3D.draw_handler_remove(op._handle_gizmo, "WINDOW")
        except Exception:
            pass


class LinkTransformModalMixin:
    """Mixin providing modal behavior with preview and flip axes."""

    @classmethod
    def poll(cls, context):
        return (
            context.mode == "OBJECT"
            and context.selected_objects
            and context.view_layer.objects.active
            and context.view_layer.objects.active in context.selected_objects
        )

    def execute(self, context):
        """Fallback for scripts/redo - applies transform directly without modal."""
        if not self.poll(context):
            return {"CANCELLED"}
        self.flip_x = False
        self.flip_y = False
        self.flip_z = False
        self._originals = []
        for obj in context.selected_objects:
            self._originals.append(
                {
                    "obj": obj,
                    "location": Vector(obj.location),
                    "rotation_euler": Euler(obj.rotation_euler),
                    "scale": Vector(obj.scale),
                }
            )
        self._active_obj = context.view_layer.objects.active
        self._active_location = Vector(self._active_obj.location)
        self._active_rotation = Euler(self._active_obj.rotation_euler)
        self._active_scale = Vector(self._active_obj.scale)
        self._apply_preview(context)
        context.view_layer.update()
        return {"FINISHED"}

    def invoke(self, context, event):
        if not context.selected_objects or not context.view_layer.objects.active:
            self.report({"WARNING"}, "No selection or active object")
            return {"CANCELLED"}

        if context.view_layer.objects.active not in context.selected_objects:
            self.report({"WARNING"}, "Active object must be in selection")
            return {"CANCELLED"}

        self.flip_x = False
        self.flip_y = False
        self.flip_z = False

        # Store original state for revert
        self._originals = []
        for obj in context.selected_objects:
            self._originals.append(
                {
                    "obj": obj,
                    "location": Vector(obj.location),
                    "rotation_euler": Euler(obj.rotation_euler),
                    "scale": Vector(obj.scale),
                }
            )

        # Store active object
        self._active_obj = context.view_layer.objects.active
        self._active_location = Vector(self._active_obj.location)
        self._active_rotation = Euler(self._active_obj.rotation_euler)
        self._active_scale = Vector(self._active_obj.scale)

        # Apply initial preview
        self._apply_preview(context)
        context.view_layer.update()

        # Set global ref so draw callbacks can access operator state
        set_active_modal_op(self)

        # Add draw handlers - UI overlay and 3D axis gizmo
        args = (self, context)
        self._handle = bpy.types.SpaceView3D.draw_handler_add(
            draw_modal_ui, args, "WINDOW", "POST_PIXEL"
        )
        self._handle_gizmo = bpy.types.SpaceView3D.draw_handler_add(
            draw_axis_gizmo, args, "WINDOW", "POST_VIEW"
        )

        # Use 3D view context for modal handler - fixes Ctrl+L menu invocation
        # Prefer current window's 3D view (where user clicked) over other windows
        win = context.window
        for area in win.screen.areas:
            if area.type == "VIEW_3D":
                for region in area.regions:
                    if region.type == "WINDOW":
                        with context.temp_override(window=win, area=area, region=region):
                            context.window_manager.modal_handler_add(self)
                        tag_redraw_all_view3d()
                        return {"RUNNING_MODAL"}
        # Fallback: try any window with 3D view
        for win in context.window_manager.windows:
            for area in win.screen.areas:
                if area.type == "VIEW_3D":
                    for region in area.regions:
                        if region.type == "WINDOW":
                            with context.temp_override(window=win, area=area, region=region):
                                context.window_manager.modal_handler_add(self)
                            tag_redraw_all_view3d()
                            return {"RUNNING_MODAL"}
        # Last resort
        context.window_manager.modal_handler_add(self)
        tag_redraw_all_view3d()
        return {"RUNNING_MODAL"}

    def _apply_preview(self, context):
        """Override in subclasses to apply the specific transform."""
        raise NotImplementedError

    def _revert(self, context):
        """Revert all objects to original state."""
        for data in self._originals:
            obj = data["obj"]
            obj.location = data["location"]
            obj.rotation_euler = data["rotation_euler"]
            obj.scale = data["scale"]

    def modal(self, context, event):
        # Allow viewport navigation (orbit, pan, zoom) while modal is active
        if event.type in {"MIDDLEMOUSE", "WHEELUPMOUSE", "WHEELDOWNMOUSE", "TRACKPAD"}:
            return {"PASS_THROUGH"}
        if event.type in {"X", "Y", "Z"} and event.value == "PRESS":
            if event.type == "X":
                self.flip_x = not self.flip_x
            elif event.type == "Y":
                self.flip_y = not self.flip_y
            elif event.type == "Z":
                self.flip_z = not self.flip_z
            self._apply_preview(context)
            context.view_layer.update()
            tag_redraw_all_view3d()
            return {"RUNNING_MODAL"}

        if event.type in {"RET", "NUMPAD_ENTER"} and event.value == "PRESS":
            clear_active_modal_op()
            _remove_draw_handlers(self)
            tag_redraw_all_view3d()
            return {"FINISHED"}

        if event.type == "LEFTMOUSE" and event.value == "PRESS":
            clear_active_modal_op()
            _remove_draw_handlers(self)
            tag_redraw_all_view3d()
            return {"FINISHED"}

        if event.type in {"ESC", "RIGHTMOUSE"} and event.value == "PRESS":
            clear_active_modal_op()
            self._revert(context)
            context.view_layer.update()
            _remove_draw_handlers(self)
            tag_redraw_all_view3d()
            return {"CANCELLED"}

        return {"RUNNING_MODAL"}

    def _do_raycast(self, context, event):
        """Raycast from mouse position into scene. Stores hit data on self."""
        from bpy_extras import view3d_utils

        region = context.region
        rv3d = context.region_data
        if not region or not rv3d:
            self._hit_location = self._hit_normal = self._hit_face_verts = None
            return
        coord = (event.mouse_region_x, event.mouse_region_y)
        ray_origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)
        ray_dir = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
        result, loc, normal, index, eval_obj, _mat = context.scene.ray_cast(
            context.evaluated_depsgraph_get(), ray_origin, ray_dir
        )
        if result and eval_obj:
            self._hit_location = loc
            self._hit_normal = normal
            orig_obj = getattr(eval_obj, "original", eval_obj)
            try:
                face = orig_obj.data.polygons[index]
                m = orig_obj.matrix_world
                self._hit_face_verts = [m @ orig_obj.data.vertices[vi].co for vi in face.vertices]
            except (IndexError, AttributeError):
                self._hit_face_verts = None
        else:
            self._hit_location = self._hit_normal = self._hit_face_verts = None

    def _apply_flip_vec3(self, vec):
        """Apply flip state to a Vector."""
        return Vector(
            (
                -vec.x if self.flip_x else vec.x,
                -vec.y if self.flip_y else vec.y,
                -vec.z if self.flip_z else vec.z,
            )
        )

    def _apply_flip_euler(self, euler):
        """Apply flip state to an Euler rotation."""
        return Euler(
            (
                -euler.x if self.flip_x else euler.x,
                -euler.y if self.flip_y else euler.y,
                -euler.z if self.flip_z else euler.z,
            )
        )


class LinkLocation_Operator(LinkTransformModalMixin, Operator):
    bl_idname = "object.jlink_location"
    bl_label = "Link Location"
    bl_description = (
        "Copy Location from active object (modal: X/Y/Z flip, Enter confirm, Esc cancel)"
    )
    bl_options = {"REGISTER"}

    _op_title = "Link Location"

    def _apply_preview(self, context):
        loc = self._apply_flip_vec3(self._active_location)
        for data in self._originals:
            data["obj"].location = loc


class LinkRotation_Operator(LinkTransformModalMixin, Operator):
    bl_idname = "object.jlink_rotation"
    bl_label = "Link Rotation"
    bl_description = (
        "Copy Rotation from active object (modal: X/Y/Z flip, Enter confirm, Esc cancel)"
    )
    bl_options = {"REGISTER"}

    _op_title = "Link Rotation"

    def _apply_preview(self, context):
        rot = self._apply_flip_euler(self._active_rotation)
        for data in self._originals:
            data["obj"].rotation_euler = rot


class LinkScale_Operator(LinkTransformModalMixin, Operator):
    bl_idname = "object.jlink_scale"
    bl_label = "Link Scale"
    bl_description = "Copy Scale from active object (modal: X/Y/Z flip, Enter confirm, Esc cancel)"
    bl_options = {"REGISTER"}

    _op_title = "Link Scale"

    def _apply_preview(self, context):
        scale = self._apply_flip_vec3(self._active_scale)
        for data in self._originals:
            data["obj"].scale = scale


class LinkTransform_Operator(LinkTransformModalMixin, Operator):
    bl_idname = "object.jlink_transform"
    bl_label = "Link Transform"
    bl_description = (
        "Copy Transforms from active object (modal: X/Y/Z flip, Enter confirm, Esc cancel)"
    )
    bl_options = {"REGISTER"}

    _op_title = "Link All Transforms"

    def _apply_preview(self, context):
        loc = self._apply_flip_vec3(self._active_location)
        rot = self._apply_flip_euler(self._active_rotation)
        scale = self._apply_flip_vec3(self._active_scale)
        for data in self._originals:
            data["obj"].location = loc
            data["obj"].rotation_euler = rot
            data["obj"].scale = scale


class RotationFromCursor_Operator(LinkTransformModalMixin, Operator):
    bl_idname = "object.jlink_cursor_rotation"
    bl_label = "Set Origin Rotation from Face"
    bl_description = (
        "Align selection rotation to a picked face normal; "
        "Space or Enter to confirm, Esc to cancel; 3D cursor position is restored afterward"
    )
    bl_options = {"REGISTER"}

    _op_title = "Set Origin Rotation from Face"

    def execute(self, context):
        """Fallback for scripts/redo - applies face-aligned rotation directly."""
        self._mesh_backups = []
        self._face_pick_mode = False
        self._face_picked = False
        for obj in context.selected_objects:
            if obj.type == "MESH" and obj.data:
                self._mesh_backups.append(
                    {
                        "obj": obj,
                        "verts": [v.co.copy() for v in obj.data.vertices],
                    }
                )
        return super().execute(context)

    def invoke(self, context, event):
        # Enable face-pick mode
        self._face_pick_mode = True
        self._face_picked = False
        self._face_picked_once = False
        self._hit_location = None
        self._hit_normal = None
        self._hit_face_verts = None
        # Last confirmed pick (separate from hover hit so flips can re-apply)
        self._picked_location = None
        self._picked_normal = None
        self._picked_face_verts = None
        # Backup mesh vertices (face alignment modifies mesh)
        self._mesh_backups = []
        for obj in context.selected_objects:
            if obj.type == "MESH" and obj.data:
                self._mesh_backups.append(
                    {
                        "obj": obj,
                        "verts": [v.co.copy() for v in obj.data.vertices],
                    }
                )
        return super().invoke(context, event)

    def modal(self, context, event):
        """Override to implement face-pick interaction."""
        # Navigation passthrough
        if event.type in {"MIDDLEMOUSE", "WHEELUPMOUSE", "WHEELDOWNMOUSE", "TRACKPAD"}:
            return {"PASS_THROUGH"}

        # Raycast on every mouse move so the highlight stays current
        if event.type == "MOUSEMOVE":
            self._do_raycast(context, event)
            tag_redraw_all_view3d()
            return {"RUNNING_MODAL"}

        # LMB selects a face and previews the result — stays in modal so user can see the axes update
        if event.type == "LEFTMOUSE" and event.value == "PRESS":
            if getattr(self, "_hit_location", None) is not None:
                # Freeze this pick so X/Y/Z flips can re-apply to the same face
                self._picked_location = self._hit_location
                self._picked_normal = self._hit_normal
                self._picked_face_verts = self._hit_face_verts
                self._apply_face_rotation(context)
                self._face_picked_once = True
                context.view_layer.update()
                tag_redraw_all_view3d()
            return {"RUNNING_MODAL"}

        # X/Y/Z flip — re-applies to the last picked face if one exists
        if event.type in {"X", "Y", "Z"} and event.value == "PRESS":
            if event.type == "X":
                self.flip_x = not self.flip_x
            elif event.type == "Y":
                self.flip_y = not self.flip_y
            else:
                self.flip_z = not self.flip_z
            if self._face_picked_once:
                self._reapply_picked_face(context)
                context.view_layer.update()
            tag_redraw_all_view3d()
            return {"RUNNING_MODAL"}

        # Space or Enter confirms and closes the modal
        if event.type in {"SPACE", "RET", "NUMPAD_ENTER"} and event.value == "PRESS":
            clear_active_modal_op()
            _remove_draw_handlers(self)
            tag_redraw_all_view3d()
            return {"FINISHED"}

        if event.type in {"ESC", "RIGHTMOUSE"} and event.value == "PRESS":
            self._revert(context)
            context.view_layer.update()
            clear_active_modal_op()
            _remove_draw_handlers(self)
            tag_redraw_all_view3d()
            return {"CANCELLED"}

        return {"RUNNING_MODAL"}

    def _apply_preview(self, context):
        # In face-pick mode, don't touch objects until the user clicks a face
        if self._face_pick_mode and not self._face_picked:
            return

        context.scene.cursor.rotation_mode = "XYZ"
        source = context.scene.cursor
        # Use cursor rotation as the base frame, then apply local axis flips via object scale signs.
        # This makes flips local to the picked face frame instead of world Euler channels.
        rot = Euler(source.rotation_euler)
        sx = -1.0 if self.flip_x else 1.0
        sy = -1.0 if self.flip_y else 1.0
        sz = -1.0 if self.flip_z else 1.0

        for data in self._originals:
            obj = data["obj"]
            orig_rot = data["rotation_euler"]
            orig_scale = data["scale"]
            new_scale = Vector((orig_scale.x * sx, orig_scale.y * sy, orig_scale.z * sz))

            # Keep visual world-space mesh placement by transforming from original object basis
            # to the new object basis (rotation + signed local scale).
            mat_new = rot.to_matrix() @ Matrix.Diagonal((new_scale.x, new_scale.y, new_scale.z))
            mat_orig = orig_rot.to_matrix() @ Matrix.Diagonal((orig_scale.x, orig_scale.y, orig_scale.z))
            mat = mat_new.inverted_safe() @ mat_orig

            if obj.type == "MESH" and obj.data:
                orig_coords = next(
                    (b["verts"] for b in self._mesh_backups if b["obj"] == obj),
                    [v.co.copy() for v in obj.data.vertices],
                )
                for i, v in enumerate(obj.data.vertices):
                    v.co = mat @ orig_coords[i]
                obj.data.update()
            obj.rotation_euler = rot
            obj.scale = new_scale

    def _reapply_picked_face(self, context):
        """Re-apply the rotation for the last LMB-picked face (used when flip axes change)."""
        if not self._face_picked_once:
            return
        # Temporarily swap to the frozen pick so _apply_face_rotation uses it
        saved = (self._hit_location, self._hit_normal, self._hit_face_verts)
        self._hit_location = self._picked_location
        self._hit_normal = self._picked_normal
        self._hit_face_verts = self._picked_face_verts
        self._apply_face_rotation(context)
        self._hit_location, self._hit_normal, self._hit_face_verts = saved

    def _apply_face_rotation(self, context):
        """Temporarily snap cursor to the picked face and apply preview, then restore cursor."""
        loc = self._hit_location
        normal = self._hit_normal
        if loc is None or normal is None:
            return
        scene = context.scene
        # Save cursor
        saved_loc = scene.cursor.location.copy()
        saved_rot = Euler(scene.cursor.rotation_euler)
        saved_mode = scene.cursor.rotation_mode

        # Base face frame: Z axis = face normal (local flips are handled in _apply_preview).
        scene.cursor.location = loc
        scene.cursor.rotation_mode = "XYZ"
        scene.cursor.rotation_euler = normal.to_track_quat("Z", "Y").to_euler()

        self._face_picked = True
        self._apply_preview(context)
        self._face_picked = False

        # Restore cursor
        scene.cursor.location = saved_loc
        scene.cursor.rotation_euler = saved_rot
        scene.cursor.rotation_mode = saved_mode

    def _revert(self, context):
        # Restore mesh vertices first
        for backup in getattr(self, "_mesh_backups", []):
            obj = backup["obj"]
            for i, co in enumerate(backup["verts"]):
                obj.data.vertices[i].co = co.copy()
            obj.data.update()
        super()._revert(context)


class JLinkCursorRotationInvoke_Operator(Operator):
    """Wrapper to invoke Set Origin Rotation from Face with correct 3D view context (fixes Ctrl+L menu)."""

    bl_idname = "object.jlink_cursor_rotation_invoke"
    bl_label = "Set Origin Rotation from Face"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return RotationFromCursor_Operator.poll(context)

    def execute(self, context):
        for area in context.window.screen.areas:
            if area.type == "VIEW_3D":
                for region in area.regions:
                    if region.type == "WINDOW":
                        with context.temp_override(area=area, region=region):
                            bpy.ops.object.jlink_cursor_rotation("INVOKE_DEFAULT")
                        return {"FINISHED"}
        self.report({"ERROR"}, "No 3D view found")
        return {"CANCELLED"}


def draw_menu(self, context):
    layout = self.layout
    layout.separator()
    layout.operator("object.jlink_location", text="Location")
    layout.operator("object.jlink_rotation", text="Rotation")
    layout.operator("object.jlink_scale", text="Scale")
    layout.operator("object.jlink_transform", text="All Transforms")
    layout.operator("object.jlink_cursor_rotation_invoke", text="Set Origin Rotation from Face")


CLASSES = (
    LinkLocation_Operator,
    LinkRotation_Operator,
    LinkScale_Operator,
    LinkTransform_Operator,
    RotationFromCursor_Operator,
    JLinkCursorRotationInvoke_Operator,
)


def register():
    from bpy.utils import register_class

    for cls in CLASSES:
        register_class(cls)
    bpy.types.VIEW3D_MT_make_links.append(draw_menu)


def unregister():
    from bpy.utils import unregister_class

    try:
        bpy.types.VIEW3D_MT_make_links.remove(draw_menu)
    except Exception:
        pass
    clear_active_modal_op()
    for cls in reversed(CLASSES):
        unregister_class(cls)
