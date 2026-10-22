from .._imports import *
class KEYHEAVEN_PT_main_panel(bpy.types.Panel):
    bl_label = "KeyHeaven 4.0.0"
    bl_idname = "KEYHEAVEN_PT_main_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "KeyHeaven"

    def draw(self, context):
        layout = self.layout
        props = context.scene.keyheaven

        mode_str = "Pose Mode (Bones)" if context.mode == "POSE" else "Object Mode (Objects)"
        row = layout.row(align=True)
        row.alignment = "CENTER"
        row.label(
            text=f"Context: {mode_str}",
            icon="ARMATURE_DATA" if context.mode == "POSE" else "OBJECT_DATA",
        )

        box = layout.box()
        box.label(text="Base & Timeline Controls:", icon="ACTION")
        row_b = box.row(align=True)
        row_b.operator("keyheaven.restore_backup", text="Restore Base", icon="BACK")
        row_b.operator("keyheaven.capture_base", text="Capture Base", icon="REC")

        box.prop(props, "master_intensity", slider=True, icon="COLOR")

        box_lock = box.box()
        row_l = box_lock.row(align=True)
        if props.boundary_lock_enabled:
            row_l.label(text="Boundary Protection: ACTIVE", icon="LOCKED")
        else:
            row_l.label(text="Boundary Protection: OFF", icon="UNLOCKED")
        row_l.operator("keyheaven.toggle_boundary", text="", icon="FILE_REFRESH")

        row_gap = box.row(align=True)
        row_gap.prop(props, "min_gap", text="Min Gap")
        row_gap.prop(props, "min_gap_mode", text="")


class KEYHEAVEN_PT_protection(bpy.types.Panel):
    bl_label = "Protection"
    bl_idname = "KEYHEAVEN_PT_protection"
    bl_parent_id = "KEYHEAVEN_PT_main_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        box = layout.box()
        box.label(text="Logical Keyframe Locks:", icon="LOCKED")

        col = box.column(align=True)
        row1 = col.row(align=True)
        op1 = row1.operator("keyheaven.protect_keys", text="Lock Both", icon="LOCKED")
        op1.mode = "BOTH"
        op2 = row1.operator("keyheaven.protect_keys", text="Value Only", icon="FCURVE")
        op2.mode = "VALUE"

        row2 = col.row(align=True)
        op3 = row2.operator("keyheaven.protect_keys", text="Time Group", icon="TIME")
        op3.mode = "TIMING"
        row2.operator("keyheaven.unprotect_keys", text="Unprotect", icon="UNLOCKED")

        box2 = layout.box()
        box2.label(text="Temporal Pins (Shared Timing):", icon="PINNED")
        row3 = box2.row(align=True)
        row3.operator("keyheaven.pin_keys", text="Pin Selected Keys", icon="PINNED")
        row3.operator("keyheaven.unpin_keys", text="Unpin Selected", icon="UNPINNED")


class KEYHEAVEN_PT_randomizer(bpy.types.Panel):
    bl_label = "Randomizer"
    bl_idname = "KEYHEAVEN_PT_randomizer"
    bl_parent_id = "KEYHEAVEN_PT_main_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        props = context.scene.keyheaven

        box = layout.box()
        box.label(text="Temporal Randomizer:", icon="DRIVER")
        col = box.column(align=True)
        col.prop(props, "rhythm_mode", text="Pattern")
        col.prop(props, "random_scope", text="Randomization")
        col.prop(props, "random_seed", text="Seed")
        col.prop(props, "randomizer_iterations", text="Iterations")

        row = col.row(align=True)
        row.label(text="Time Shift:")
        row.prop(props, "var_x_min", text="Min")
        row.prop(props, "var_x_max", text="Max")

        col.operator("keyheaven.apply_randomizer", icon="RNDCURVE")

        channels = box.box()
        channels.label(text="Value Channels:", icon="SNAP_FACE_CENTER")
        row_axis = channels.row(align=True)
        row_axis.prop(props, "rand_time", text="Time")
        row_axis.prop(props, "rand_pos_x", text="X")
        row_axis.prop(props, "rand_pos_y", text="Y")
        row_axis.prop(props, "rand_pos_z", text="Z")
        row_axis.prop(props, "rand_rot", text="Rot")
        row_axis.prop(props, "rand_scale", text="Scale")

        box = layout.box()
        box.label(text="Random Selection:", icon="RESTRICT_SELECT_OFF")
        col = box.column(align=True)
        col.prop(props, "selection_pool_mode", text="Pool")
        col.prop(props, "select_target_pct")
        col.operator("keyheaven.select_random_targets", icon="SELECT_SET")
        col.separator()
        col.prop(props, "select_key_pct")
        col.operator("keyheaven.select_random_keyframes", icon="KEY_HLT")

        box = layout.box()
        box.label(text="Quick Draft Motion Generator:", icon="ANIM")
        col = box.column(align=True)
        col.prop(props, "quick_anim_keys")
        col.operator("keyheaven.quick_animate", icon="PLAY")


class KEYHEAVEN_PT_chains(bpy.types.Panel):
    bl_label = "Chain / Propagation"
    bl_idname = "KEYHEAVEN_PT_chains"
    bl_parent_id = "KEYHEAVEN_PT_main_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        props = context.scene.keyheaven

        box = layout.box()
        box.label(text="Propagation Strategy:", icon="SEQUENCE")
        row = box.row(align=True)
        row.label(text="Delay:")
        row.prop(props, "delay_frames_min", text="Min")
        row.prop(props, "delay_frames_max", text="Max")
        row_w = box.row(align=True)
        row_w.prop(props, "propagation_wave_speed", text="Wave Speed")
        row_w.prop(props, "propagation_max_delay", text="Max Delay")
        row_ops = box.row(align=True)
        row_ops.operator("keyheaven.apply_stagger", text="Stagger", icon="TIME")
        row_ops.operator("keyheaven.apply_propagation_wave", text="Wave", icon="MOD_WAVE")

        box = layout.box()
        box.label(text="Chain Drag Propagation (Root to Tip):", icon="FORCE_DRAG")
        row_d = box.row(align=True)
        row_d.operator("keyheaven.apply_chain_drag", text="Chain Drag", icon="FORCE_DRAG")
        row_d.operator("keyheaven.apply_follow_drag", text="Follow Drag", icon="FORCE_DRAG")


class KEYHEAVEN_PT_polish(bpy.types.Panel):
    bl_label = "Motion Polish"
    bl_idname = "KEYHEAVEN_PT_polish"
    bl_parent_id = "KEYHEAVEN_PT_main_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        props = context.scene.keyheaven

        box = layout.box()
        box.label(text="Anticipation / Overshoot:", icon="IPO_ELASTIC")
        row = box.row(align=True)
        row.label(text="Anticipation:")
        row.prop(props, "anti_factor_min", text="Min")
        row.prop(props, "anti_factor_max", text="Max")

        row = box.row(align=True)
        row.label(text="Overshoot:")
        row.prop(props, "over_factor_min", text="Min")
        row.prop(props, "over_factor_max", text="Max")
        box.operator("keyheaven.apply_polish", icon="ANIM")

        box = layout.box()
        box.label(text="Dynamic Drag & Follow-Through:", icon="FORCE_DRAG")
        row = box.row(align=True)
        row.label(text="Drag:")
        row.prop(props, "drag_factor_min", text="Min")
        row.prop(props, "drag_factor_max", text="Max")
        box.operator("keyheaven.apply_drag", icon="MOD_PHYSICS")


class KEYHEAVEN_PT_cycle(bpy.types.Panel):
    bl_label = "Cycle"
    bl_idname = "KEYHEAVEN_PT_cycle"
    bl_parent_id = "KEYHEAVEN_PT_main_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        props = context.scene.keyheaven

        box = layout.box()
        box.label(text="Loop Synthesizer (Mirror & Reverse):", icon="LOOP_FORWARDS")
        box.prop(props, "loop_mode", text="Mode")
        box.operator("keyheaven.make_it_loop", text="Make It Loop", icon="FILE_REFRESH")


class KEYHEAVEN_PT_effects(bpy.types.Panel):
    bl_label = "Secondary Motion"
    bl_idname = "KEYHEAVEN_PT_effects"
    bl_parent_id = "KEYHEAVEN_PT_main_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        props = context.scene.keyheaven

        box = layout.box()
        box.label(text="Secondary Motion:", icon="FORCE_VORTEX")
        col = box.column(align=True)
        col.prop(props, "secondary_effect", text="Effect")
        col.prop(props, "secondary_intensity", slider=True, icon="COLOR")
        col.operator("keyheaven.apply_secondary", icon="PLAY")

        advanced = layout.box()
        advanced.label(text="Advanced Parameters:", icon="PREFERENCES")
        advanced.use_property_split = True
        advanced.use_property_decorate = False

        box = advanced.box()
        box.label(text="Organic Breathing:", icon="FORCE_VORTEX")
        row = box.row(align=True)
        row.label(text="Rate:")
        row.prop(props, "breathing_rate_min", text="Min")
        row.prop(props, "breathing_rate_max", text="Max")
        row = box.row(align=True)
        row.label(text="Amplitude:")
        row.prop(props, "breathing_amp_min", text="Min")
        row.prop(props, "breathing_amp_max", text="Max")
        box.operator("keyheaven.apply_breathing", icon="PLAY")

        box = advanced.box()
        box.label(text="Squash & Stretch:", icon="MOD_MESHDEFORM")
        row = box.row(align=True)
        row.label(text="Factor:")
        row.prop(props, "squash_factor_min", text="Min")
        row.prop(props, "squash_factor_max", text="Max")
        box.operator("keyheaven.apply_squash", icon="CON_STRETCHTO")

        box = advanced.box()
        box.label(text="Inertial Spring Jiggle:", icon="MOD_SOFT")
        row = box.row(align=True)
        row.label(text="Stiffness:")
        row.prop(props, "jiggle_stiffness_min", text="Min")
        row.prop(props, "jiggle_stiffness_max", text="Max")
        row = box.row(align=True)
        row.label(text="Damping:")
        row.prop(props, "jiggle_damping_min", text="Min")
        row.prop(props, "jiggle_damping_max", text="Max")
        box.operator("keyheaven.apply_jiggle", icon="FORCE_HARMONIC")

        box = advanced.box()
        box.label(text="Living Micro-Tremor:", icon="MOD_WAVE")
        row = box.row(align=True)
        row.label(text="Jitter:")
        row.prop(props, "tremor_amp_min", text="Min")
        row.prop(props, "tremor_amp_max", text="Max")
        box.operator("keyheaven.apply_tremor", icon="PARTICLES")

        box = advanced.box()
        box.label(text="Procedural Noise Modifier:", icon="TEXTURE")
        row = box.row(align=True)
        row.label(text="Scale:")
        row.prop(props, "noise_scale_min", text="Min")
        row.prop(props, "noise_scale_max", text="Max")
        row = box.row(align=True)
        row.label(text="Strength:")
        row.prop(props, "noise_strength_min", text="Min")
        row.prop(props, "noise_strength_max", text="Max")
        box.operator("keyheaven.apply_noise", icon="MOD_NOISE")

        box = advanced.box()
        box.label(text="Wave Pattern Modifier:", icon="MOD_WAVE")
        row = box.row(align=True)
        row.label(text="Frequency:")
        row.prop(props, "wave_frequency_min", text="Min")
        row.prop(props, "wave_frequency_max", text="Max")
        row = box.row(align=True)
        row.label(text="Amplitude:")
        row.prop(props, "wave_amplitude_min", text="Min")
        row.prop(props, "wave_amplitude_max", text="Max")
        box.operator("keyheaven.apply_wave", icon="MOD_WAVE")


class KEYHEAVEN_PT_curves(bpy.types.Panel):
    bl_label = "Time Scale"
    bl_idname = "KEYHEAVEN_PT_curves"
    bl_parent_id = "KEYHEAVEN_PT_main_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        props = context.scene.keyheaven

        box = layout.box()
        box.label(text="Elastic Time Scale (Compression/Expansion):", icon="TIME")
        row = box.row(align=True)
        row.label(text="Factor:")
        row.prop(props, "time_scale_min", text="Min")
        row.prop(props, "time_scale_max", text="Max")
        box.operator("keyheaven.apply_time_scale", icon="TIME")

        box = layout.box()
        box.label(text="Procedural Custom Easing (Native):", icon="FCURVE")
        col = box.column(align=True)
        col.prop(props, "custom_easing_type", text="Function")
        col.prop(props, "custom_easing_ease", text="Phase")
        col.prop(props, "ease_multiplier", text="Ease Multiplier / Divider")
        col.operator("keyheaven.apply_easing", icon="SHADERFX")


class KEYHEAVEN_PT_deoverlap(bpy.types.Panel):
    bl_label = "Spatial Clearance"
    bl_idname = "KEYHEAVEN_PT_deoverlap"
    bl_parent_id = "KEYHEAVEN_PT_main_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        props = context.scene.keyheaven

        box = layout.box()
        box.label(text="Clearance:", icon="MOD_PHYSICS")
        col = box.column(align=True)
        col.prop(props, "clearance_edit_radius")
        col.prop(props, "clearance_edit_mode", text="Edit Clearance")
        col.operator("keyheaven.adjust_clearance", icon="MOUSE_MOVE")
        box.operator(
            "keyheaven.deoverlap_objects",
            text="Resolve Spatial Collision",
            icon="AUTOMERGE_ON",
        )

        advanced = layout.box()
        advanced.label(text="Advanced:", icon="PREFERENCES")
        col = advanced.column(align=True)
        col.prop(props, "deoverlap_min_dist", text="Clearance Floor")
        col.prop(props, "deoverlap_margin", text="Safety Margin")
        col.prop(props, "deoverlap_max_dist", text="Max Distance")
        col.prop(props, "deoverlap_iterations", text="Correction Passes")
        col.prop(props, "deoverlap_return_to_path")
        col.prop(props, "deoverlap_orbit")


class KEYHEAVEN_PT_sanitizer(bpy.types.Panel):
    bl_label = "Sanitize / Bake"
    bl_idname = "KEYHEAVEN_PT_sanitizer"
    bl_parent_id = "KEYHEAVEN_PT_main_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        props = context.scene.keyheaven

        box = layout.box()
        box.label(text="Sanitize & Repair (Duplicate Purge):", icon="AUTOMERGE_ON")
        box.operator("keyheaven.sanitize_and_repair_all", icon="AUTOMERGE_ON")

        box = layout.box()
        box.label(text="Extrema-Lock & Error-Tolerant Decimation:", icon="MOD_SIMPLIFY")
        col = box.column(align=True)
        col.prop(props, "cleanup_error_tolerance")
        col.prop(props, "cleanup_rdp_epsilon")
        col.operator("keyheaven.cleanup_bake", icon="TRASH")

        box = layout.box()
        box.label(text="Autobake (Minimum Keys Within Tolerance):", icon="ACTION")
        col = box.column(align=True)
        col.prop(props, "autobake_tolerance")
        col.prop(props, "autobake_adaptive")
        col.prop(props, "autobake_simplify")
        col.prop(props, "autobake_keep_original")
        col.operator("keyheaven.autobake", icon="REC")


class KEYHEAVEN_PT_analysis(bpy.types.Panel):
    bl_label = "Motion Analysis"
    bl_idname = "KEYHEAVEN_PT_analysis"
    bl_parent_id = "KEYHEAVEN_PT_main_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        props = context.scene.keyheaven

        box = layout.box()
        box.label(text="Adaptive Motion Analysis:", icon="ANALYSE")
        col = box.column(align=True)
        col.operator("keyheaven.analyze_motion", icon="DRIVER")
        col.operator("keyheaven.pin_impacts", icon="PINNED")

        report = props.motion_report
        if report:
            box2 = layout.box()
            box2.label(text="Report:", icon="INFO")
            column = box2.column(align=True)
            for line in report.split("\n"):
                column.label(text=line)


class KEYHEAVEN_PT_presets(bpy.types.Panel):
    bl_label = "Advanced"
    bl_idname = "KEYHEAVEN_PT_presets"
    bl_parent_id = "KEYHEAVEN_PT_main_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        box = layout.box()
        box.label(text="Coherent Presets:", icon="PRESET")
        col = box.column(align=True)
        op = col.operator("keyheaven.apply_preset", text="Subtle", icon="PLAY")
        op.preset = "SUBTLE"
        op = col.operator("keyheaven.apply_preset", text="Energetic", icon="PLAY")
        op.preset = "ENERGETIC"
        op = col.operator("keyheaven.apply_preset", text="Mechanical", icon="PLAY")
        op.preset = "MECHANICAL"
        op = col.operator("keyheaven.apply_preset", text="Organic", icon="PLAY")
        op.preset = "ORGANIC"

        box2 = layout.box()
        box2.label(text="Workflow:", icon="INFO")
        draw_workflow_help(box2)


def draw_keyheaven_context_menu(self, context):
    layout = self.layout
    layout.separator()
    layout.menu("KEYHEAVEN_MT_context_menu", text="KeyHeaven", icon="KEYINGSET")


def draw_keyheaven_tools_menu(self, context):
    layout = self.layout
    layout.separator()
    col = layout.column()
    col.label(text="KeyHeaven", icon="KEYINGSET")
    col.operator("keyheaven.apply_randomizer", text="Apply Randomizer")
    col.operator("keyheaven.make_it_loop", text="Make It Loop")
    col.operator("keyheaven.deoverlap_objects", text="Resolve Spatial Collision")
    col.operator("keyheaven.autobake", text="Autobake")
    col.operator("keyheaven.restore_backup", text="Restore Base")


class KEYHEAVEN_MT_context_menu(bpy.types.Menu):
    bl_label = "KeyHeaven Animation Tools"
    bl_idname = "KEYHEAVEN_MT_context_menu"

    def draw(self, context):
        layout = self.layout
        layout.operator("keyheaven.protect_keys", text="Protect Selected Keyframes")
        layout.operator("keyheaven.unprotect_keys", text="Unprotect Selected Keyframes")
        layout.operator("keyheaven.pin_keys", text="Pin Selected Keyframes")
        layout.separator()
        layout.operator("keyheaven.apply_randomizer", text="Apply Randomizer")
        layout.operator("keyheaven.make_it_loop", text="Make It Loop")
        layout.operator("keyheaven.deoverlap_objects", text="Resolve Spatial Collision")
        layout.operator("keyheaven.autobake", text="Autobake")
        layout.separator()
        layout.operator("keyheaven.restore_backup", text="Restore Base")
        layout.operator("keyheaven.sanitize_and_repair_all", text="Sanitize Keyframes")


def register_menus():
    if not HAS_BPY:
        return
    unregister_menus()
    for menu_name in (
        "GRAPH_MT_keyframe",
        "GRAPH_MT_context_menu",
        "DOPESHEET_MT_keyframe",
        "DOPESHEET_MT_context_menu",
    ):
        menu_cls = getattr(bpy.types, menu_name, None)
        if menu_cls is not None:
            try:
                menu_cls.append(draw_keyheaven_context_menu)
            except Exception:
                pass


def unregister_menus():
    if not HAS_BPY:
        return
    for menu_name in (
        "GRAPH_MT_keyframe",
        "GRAPH_MT_context_menu",
        "DOPESHEET_MT_keyframe",
        "DOPESHEET_MT_context_menu",
    ):
        menu_cls = getattr(bpy.types, menu_name, None)
        if menu_cls is not None:
            try:
                menu_cls.remove(draw_keyheaven_context_menu)
            except Exception:
                pass
