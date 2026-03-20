import bpy
import blf
import gpu
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix, Vector


_active_modal_op = None


def set_active_modal_op(op):
    global _active_modal_op
    _active_modal_op = op


def clear_active_modal_op():
    global _active_modal_op
    _active_modal_op = None


def get_active_modal_op():
    return _active_modal_op


def tag_redraw_all_view3d():
    """Tag all 3D view areas for redraw."""
    for win in bpy.context.window_manager.windows:
        for area in win.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


def _get_view3d_region():
    """Get a VIEW_3D region for drawing - handles menu invocation context."""
    for win in bpy.context.window_manager.windows:
        for area in win.screen.areas:
            if area.type == "VIEW_3D":
                for region in area.regions:
                    if region.type == "WINDOW":
                        return region, area
    return None, None


def draw_modal_ui(op, context):
    """Draw the modal UI overlay in the 3D viewport."""
    # Use current context's region when drawing (correct for multi-viewport)
    ctx = bpy.context
    if ctx.area and ctx.area.type == "VIEW_3D" and ctx.region and ctx.region.type == "WINDOW":
        region = ctx.region
    else:
        region, _ = _get_view3d_region()
    if not region:
        return
    width = region.width
    height = region.height

    # Set up 2D projection for pixel-space coordinates (origin bottom-left)
    gpu.matrix.push_projection()
    scale = Matrix.Diagonal((2.0 / width, 2.0 / height, 1.0, 1.0))
    trans = Matrix.Translation((-1.0, -1.0, 0.0))
    gpu.matrix.load_projection_matrix(trans @ scale)

    # Panel dimensions
    pad = 12
    line_height = 22
    title = getattr(op, "_op_title", "Link Transforms")
    flip_x = getattr(op, "flip_x", False)
    flip_y = getattr(op, "flip_y", False)
    flip_z = getattr(op, "flip_z", False)

    if getattr(op, "_face_pick_mode", False):
        hit_loc = getattr(op, "_hit_location", None)
        face_picked = getattr(op, "_face_picked_once", False)
        flip_str = "".join(a for a, f in [(" X", flip_x), (" Y", flip_y), (" Z", flip_z)] if f)
        lines = [
            title,
            "",
            "LMB        - Select face",
            "X / Y / Z  - Flip axis" + ((" [" + flip_str.strip() + "]") if flip_str else ""),
            "Space / Enter - Confirm",
            "Esc / RMB  - Cancel",
            "",
            "Face: " + ("detected" if hit_loc else "none"),
            "State: " + ("previewing" if face_picked else "waiting"),
        ]
    else:
        lines = [
            title,
            "",
            "X - Flip X axis" + (" [ON]" if flip_x else ""),
            "Y - Flip Y axis" + (" [ON]" if flip_y else ""),
            "Z - Flip Z axis" + (" [ON]" if flip_z else ""),
            "",
            "Enter / LMB - Confirm",
            "Escape / RMB - Cancel",
        ]

    # Calculate panel size
    blf.size(0, 14)
    max_w = 0
    for line in lines:
        if line:
            w, _ = blf.dimensions(0, line)
            max_w = max(max_w, w)
    max_w = max(max_w, 220)

    box_w = max_w + pad * 2
    box_h = len(lines) * line_height + pad * 2

    margin = 20
    addon = context.preferences.addons.get(__package__)
    if addon and getattr(addon.preferences, "modal_hud_side", None) == "RIGHT":
        x0 = width - box_w - margin
    else:
        x0 = margin
    y0 = margin

    # Draw background panel (semi-transparent dark)
    gpu.state.blend_set("ALPHA")
    gpu.state.depth_test_set("NONE")

    shader = gpu.shader.from_builtin("UNIFORM_COLOR")
    vertices = (
        (x0, y0, 0),
        (x0 + box_w, y0, 0),
        (x0 + box_w, y0 + box_h, 0),
        (x0, y0 + box_h, 0),
    )
    indices = ((0, 1, 2), (0, 2, 3))
    batch = batch_for_shader(shader, "TRIS", {"pos": vertices}, indices=indices)
    shader.bind()
    shader.uniform_float("color", (0.1, 0.1, 0.12, 0.92))
    batch.draw(shader)

    # Draw border
    border_color = (0.35, 0.35, 0.4, 0.9)
    line_verts = (
        (x0, y0, 0), (x0 + box_w, y0, 0),
        (x0 + box_w, y0, 0), (x0 + box_w, y0 + box_h, 0),
        (x0 + box_w, y0 + box_h, 0), (x0, y0 + box_h, 0),
        (x0, y0 + box_h, 0), (x0, y0, 0),
    )
    line_batch = batch_for_shader(shader, "LINES", {"pos": line_verts})
    shader.bind()
    shader.uniform_float("color", border_color)
    line_batch.draw(shader)

    # Draw text
    blf.size(0, 14)
    blf.color(0, 1, 1, 1, 1)
    for i, line in enumerate(lines):
        y = y0 + box_h - pad - (i + 1) * line_height + 4
        if line:
            blf.position(0, x0 + pad, y, 0)
            blf.draw(0, line)

    gpu.state.blend_set("NONE")
    gpu.matrix.pop_projection()


def draw_axis_gizmo(op, context):
    """Draw local XYZ axis lines for all objects being edited using GPU module."""
    if not hasattr(op, "_originals") or not op._originals:
        return

    viewport = gpu.state.viewport_get()
    line_shader = gpu.shader.from_builtin("POLYLINE_SMOOTH_COLOR")
    flat_shader = gpu.shader.from_builtin("POLYLINE_UNIFORM_COLOR")

    # Always render on top of mesh geometry
    gpu.state.depth_test_set("ALWAYS")
    gpu.state.blend_set("ALPHA")

    # --- Object local axes (X red, Y green, Z blue) ---
    axis_len = 1.0
    axis_vectors = [
        Vector((axis_len, 0, 0)),
        Vector((0, axis_len, 0)),
        Vector((0, 0, axis_len)),
    ]
    axis_colors = [
        (1.0, 0.2, 0.2, 1.0),
        (0.2, 1.0, 0.2, 1.0),
        (0.2, 0.2, 1.0, 1.0),
    ]
    for axiscol in range(3):
        verts, colors = [], []
        for data in op._originals:
            try:
                mat = data["obj"].matrix_world
                origin = mat.translation.copy()
                tip = mat @ axis_vectors[axiscol]
                verts.extend([tuple(origin), tuple(tip)])
                colors.extend([axis_colors[axiscol], axis_colors[axiscol]])
            except (ReferenceError, AttributeError):
                continue
        if not verts:
            continue
        batch = batch_for_shader(line_shader, "LINES", {"pos": verts, "color": colors})
        line_shader.bind()
        line_shader.uniform_float("viewportSize", (viewport[2], viewport[3]))
        line_shader.uniform_float("lineWidth", 3.0)
        batch.draw(line_shader)

    # --- Face highlight overlay (face-pick mode) ---
    hit_verts = getattr(op, "_hit_face_verts", None)
    hit_loc = getattr(op, "_hit_location", None)
    hit_normal = getattr(op, "_hit_normal", None)

    if hit_verts and hit_loc and hit_normal and len(hit_verts) >= 3:
        fill_shader = gpu.shader.from_builtin("UNIFORM_COLOR")

        # Filled face polygon (semi-transparent yellow)
        fill_v = [tuple(v) for v in hit_verts]
        fill_tris = [(0, i, i + 1) for i in range(1, len(hit_verts) - 1)]
        fill_batch = batch_for_shader(fill_shader, "TRIS", {"pos": fill_v}, indices=fill_tris)
        fill_shader.bind()
        fill_shader.uniform_float("color", (1.0, 0.85, 0.1, 0.30))
        fill_batch.draw(fill_shader)

        # Face outline (bright yellow)
        edge_v = []
        for i in range(len(hit_verts)):
            edge_v.extend([tuple(hit_verts[i]), tuple(hit_verts[(i + 1) % len(hit_verts)])])
        edge_batch = batch_for_shader(flat_shader, "LINES", {"pos": edge_v})
        flat_shader.bind()
        flat_shader.uniform_float("viewportSize", (viewport[2], viewport[3]))
        flat_shader.uniform_float("lineWidth", 2.5)
        flat_shader.uniform_float("color", (1.0, 0.85, 0.1, 1.0))
        edge_batch.draw(flat_shader)

    gpu.state.depth_test_set("NONE")
    gpu.state.blend_set("NONE")
