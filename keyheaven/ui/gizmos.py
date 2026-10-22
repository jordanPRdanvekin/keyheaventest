from .._imports import *
class KEYHEAVEN_GT_clearance_gizmo(bpy.types.Gizmo):
    bl_idname = "VIEW3D_GT_keyheaven_clearance"
    bl_label = "Clearance Volume"

    __slots__ = ("custom_shape",)

    def setup(self):
        if not hasattr(self, "custom_shape"):
            segments = 64
            vertices = []
            for index in range(segments + 1):
                angle = (2.0 * math.pi * index) / segments
                vertices.append((math.cos(angle), math.sin(angle), 0.0))
            self.custom_shape = self.new_custom_shape("LINE_STRIP", vertices)

    def draw(self, context):
        self.draw_custom_shape(self.custom_shape)

    def draw_select(self, context, select_id):
        self.draw_custom_shape(self.custom_shape, select_id=select_id)


class KEYHEAVEN_GGT_clearance(bpy.types.GizmoGroup):
    bl_idname = "VIEW3D_GGT_keyheaven_clearance"
    bl_label = "KeyHeaven Clearance Gizmo"
    bl_space_type = "VIEW_3D"
    bl_region_type = "WINDOW"
    bl_options = {"3D", "PERSISTENT"}

    @classmethod
    def poll(cls, context):
        if not HAS_BPY or not getattr(context, "scene", None):
            return False
        if not hasattr(context.scene, "keyheaven"):
            return False
        props = context.scene.keyheaven
        if not bool(getattr(props, "clearance_edit_mode", False)):
            return False
        return bool(context.active_object or context.active_pose_bone)

    def setup(self, context):
        gizmo = self.gizmos.new(KEYHEAVEN_GT_clearance_gizmo.bl_idname)
        gizmo.color = (0.25, 0.75, 1.0)
        gizmo.alpha = 0.75
        gizmo.color_highlight = (1.0, 0.85, 0.25)
        gizmo.alpha_highlight = 1.0
        gizmo.line_width = 2.0
        gizmo.use_draw_modal = False
        gizmo.hide_select = True
        self.clearance_gizmo = gizmo

    def draw_prepare(self, context):
        gizmo = getattr(self, "clearance_gizmo", None)
        if gizmo is None:
            return
        target_position = None
        try:
            active = context.active_object
            if context.mode == "POSE" and context.active_pose_bone is not None:
                target_position = active.matrix_world @ context.active_pose_bone.head
            elif active is not None:
                target_position = active.matrix_world.translation.copy()
        except Exception:
            target_position = None
        if target_position is None:
            gizmo.hide = True
            return
        props = context.scene.keyheaven
        radius = max(0.0, float(getattr(props, "clearance_edit_radius", 0.5)))
        if radius <= 0.0:
            gizmo.hide = True
            return
        gizmo.hide = False
        gizmo.matrix_basis = Matrix.Translation(target_position)
        gizmo.scale_basis = radius
