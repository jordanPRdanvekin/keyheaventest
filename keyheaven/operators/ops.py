from .._imports import *
from ..core import *
def _keyheaven_ui_poll(context):
    return HAS_BPY and getattr(context, "scene", None) is not None \
        and hasattr(context.scene, "keyheaven")


def _time_scale_tool(target, context):
    return CurvesEngine.apply_time_scale(target, context)


def _run_chain_tool(op, context, tool_func, min_targets=2):
    targets = TargetResolver.collect_active_targets(
        context, min_keyframes=0, filter_type="TRANSFORM"
    )
    if len(targets) < min_targets:
        op.report(
            {"WARNING"},
            f"Select at least {min_targets} animated targets for this operation",
        )
        return {"CANCELLED"}

    tx = TransactionEngine(targets, context)
    tx.capture(context)
    op_token = op_state_begin(op.bl_idname, targets)
    try:
        ActionBackupEngine.prepare_targets_from_base(targets, force_reset=False)
        op_state_snapshot(op.bl_idname, op_token)
        res = tool_func(targets, context)
        if not res.success:
            op_state_rollback(op_token)
            tx.rollback(context)
            report_operation_result(op, res)
            return {"CANCELLED"}
        tx.commit()
        op_state_commit(op_token)
        report_operation_result(op, res)
        return {"FINISHED"}
    except Exception as e:
        op_state_rollback(op_token)
        tx.rollback(context)
        op.report({"ERROR"}, str(e))
        return {"CANCELLED"}


class KEYHEAVEN_OT_protect_keys(bpy.types.Operator):
    bl_idname = "keyheaven.protect_keys"
    bl_label = "Protect Selected Keyframes"
    bl_description = "Locks selected keyframes (value, relative timing, or both)"
    bl_options = {"REGISTER", "UNDO"}

    mode: bpy.props.EnumProperty(
        name="Protection Mode",
        items=[
            ("BOTH", "Lock Both", "Protects value content and time-group coherence"),
            ("VALUE", "Lock Value Only", "Protects value while allowing temporal remapping"),
            ("TIMING", "Lock Time Group Only", "Preserves relative timing while allowing value edits"),
        ],
        default="BOTH",
    )

    @classmethod
    def poll(cls, context):
        return _keyheaven_ui_poll(context)

    def execute(self, context):
        count = KeyframeProtectionEngine.protect_selected_keyframes(context, self.mode)
        self.report({"INFO"}, f"Protected {count} keyframe(s) [{self.mode}]")
        return {"FINISHED"}


class KEYHEAVEN_OT_unprotect_keys(bpy.types.Operator):
    bl_idname = "keyheaven.unprotect_keys"
    bl_label = "Unprotect Selected Keyframes"
    bl_description = "Clears protection locks from selected keyframes"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _keyheaven_ui_poll(context)

    def execute(self, context):
        count = KeyframeProtectionEngine.unprotect_selected_keyframes(context)
        self.report({"INFO"}, f"Unprotected {count} keyframe(s)")
        return {"FINISHED"}


class KEYHEAVEN_OT_pin_keys(bpy.types.Operator):
    bl_idname = "keyheaven.pin_keys"
    bl_label = "Pin Selected Keyframes"
    bl_description = "Pins selected keyframes spatially so pose relationships are preserved"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _keyheaven_ui_poll(context)

    def execute(self, context):
        count = PinsEngine.pin_selected_keyframes(context)
        self.report({"INFO"}, f"Pinned {count} keyframe(s)")
        return {"FINISHED"}


class KEYHEAVEN_OT_unpin_keys(bpy.types.Operator):
    bl_idname = "keyheaven.unpin_keys"
    bl_label = "Unpin Selected Keyframes"
    bl_description = "Removes spatial pins from selected keyframes"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _keyheaven_ui_poll(context)

    def execute(self, context):
        count = PinsEngine.unpin_selected_keyframes(context)
        self.report({"INFO"}, f"Unpinned {count} keyframe(s)")
        return {"FINISHED"}


class KEYHEAVEN_OT_toggle_boundary(bpy.types.Operator):
    bl_idname = "keyheaven.toggle_boundary"
    bl_label = "Toggle Boundary Protection"
    bl_description = "Enables or disables first/last keyframe boundary protection"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _keyheaven_ui_poll(context)

    def execute(self, context):
        props = context.scene.keyheaven
        props.boundary_lock_enabled = not props.boundary_lock_enabled
        state = "enabled" if props.boundary_lock_enabled else "disabled"
        self.report({"INFO"}, f"Boundary protection {state}")
        return {"FINISHED"}


class KEYHEAVEN_OT_restore_backup(bpy.types.Operator):
    bl_idname = "keyheaven.restore_backup"
    bl_label = "Restore Base Animation"
    bl_description = "Restores the pristine .kh_base backup and baseline timeline bounds"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _keyheaven_ui_poll(context)

    def execute(self, context):
        targets = TargetResolver.collect_active_targets(
            context, min_keyframes=0, filter_type="ALL"
        )
        restored = sum(1 for target in targets if ActionBackupEngine.restore_backup(target))
        MotionAnalyzer.clear_cache()
        if restored:
            self.report({"INFO"}, f"Restored base animation for {restored} target(s)")
        else:
            self.report({"WARNING"}, "No pristine base backup found to restore")
        return {"FINISHED"}


class KEYHEAVEN_OT_capture_base(bpy.types.Operator):
    bl_idname = "keyheaven.capture_base"
    bl_label = "Capture Base Animation"
    bl_description = "Overwrites .kh_base with the current animation as new source of truth"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _keyheaven_ui_poll(context)

    def execute(self, context):
        targets = TargetResolver.collect_active_targets(
            context, min_keyframes=0, filter_type="ALL"
        )
        captured = sum(1 for target in targets if ActionBackupEngine.capture_new_base(target))
        MotionAnalyzer.clear_cache()
        if captured:
            self.report({"INFO"}, f"Captured new base for {captured} target(s)")
        else:
            self.report({"WARNING"}, "No active animation data found to capture")
        return {"FINISHED"}


class KEYHEAVEN_OT_apply_randomizer(bpy.types.Operator):
    bl_idname = "keyheaven.apply_randomizer"
    bl_label = "Apply Randomizer"
    bl_description = "Redistributes keyframe timing with the selected rhythm pattern"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _keyheaven_ui_poll(context)

    def execute(self, context):
        return execute_per_target_tool(
            self, context, RandomizerEngine.apply_randomizer,
            min_keyframes=2, filter_type="TRANSFORM",
        )


class KEYHEAVEN_OT_quick_animate(bpy.types.Operator):
    bl_idname = "keyheaven.quick_animate"
    bl_label = "Generate Quick Draft"
    bl_description = "Generates a procedural keyframe motion draft without altering boundaries"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _keyheaven_ui_poll(context)

    def execute(self, context):
        return execute_per_target_tool(
            self, context, RandomizerEngine.quick_animate_generator,
            min_keyframes=0, filter_type="TRANSFORM",
        )


class KEYHEAVEN_OT_select_random_targets(bpy.types.Operator):
    bl_idname = "keyheaven.select_random_targets"
    bl_label = "Select Random Targets"
    bl_description = "Randomly filters active targets using the configured ratio"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _keyheaven_ui_poll(context)

    def execute(self, context):
        props = context.scene.keyheaven
        selected = RandomizerEngine.select_random_targets(
            context, percentage=props.select_target_pct
        )
        self.report({"INFO"}, f"Selected {selected} target(s)")
        return {"FINISHED"}


class KEYHEAVEN_OT_select_random_keyframes(bpy.types.Operator):
    bl_idname = "keyheaven.select_random_keyframes"
    bl_label = "Select Random Keyframes"
    bl_description = "Randomly selects intermediate keyframes across active curves"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _keyheaven_ui_poll(context)

    def execute(self, context):
        props = context.scene.keyheaven
        selected = RandomizerEngine.select_random_keyframes(
            context, percentage=props.select_key_pct
        )
        self.report({"INFO"}, f"Selected {selected} keyframe(s)")
        return {"FINISHED"}


class KEYHEAVEN_OT_apply_breathing(bpy.types.Operator):
    bl_idname = "keyheaven.apply_breathing"
    bl_label = "Apply Organic Breathing"
    bl_description = "Adds asymmetric volume-preserving breathing motion"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _keyheaven_ui_poll(context)

    def execute(self, context):
        return execute_per_target_tool(
            self, context, SecondaryPhysicsEngine.apply_organic_breathing,
            min_keyframes=0, filter_type="TRANSFORM",
        )


class KEYHEAVEN_OT_apply_squash(bpy.types.Operator):
    bl_idname = "keyheaven.apply_squash"
    bl_label = "Apply Squash & Stretch"
    bl_description = "Adds velocity-driven, volume-preserving tensor deformation"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _keyheaven_ui_poll(context)

    def execute(self, context):
        return execute_per_target_tool(
            self, context, SecondaryPhysicsEngine.apply_squash_and_stretch,
            min_keyframes=0, filter_type="TRANSFORM",
        )


class KEYHEAVEN_OT_apply_jiggle(bpy.types.Operator):
    bl_idname = "keyheaven.apply_jiggle"
    bl_label = "Apply Inertial Jiggle"
    bl_description = "Adds damped harmonic spring motion from target acceleration"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _keyheaven_ui_poll(context)

    def execute(self, context):
        return execute_per_target_tool(
            self, context, SecondaryPhysicsEngine.apply_inertial_jiggle,
            min_keyframes=0, filter_type="TRANSFORM",
        )


class KEYHEAVEN_OT_apply_drag(bpy.types.Operator):
    bl_idname = "keyheaven.apply_drag"
    bl_label = "Apply Dynamic Drag"
    bl_description = "Adds velocity-based rotational drag and follow-through"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _keyheaven_ui_poll(context)

    def execute(self, context):
        return execute_per_target_tool(
            self, context, SecondaryPhysicsEngine.apply_dynamic_drag,
            min_keyframes=0, filter_type="TRANSFORM",
        )


class KEYHEAVEN_OT_apply_tremor(bpy.types.Operator):
    bl_idname = "keyheaven.apply_tremor"
    bl_label = "Apply Micro-Tremor"
    bl_description = "Adds low-amplitude high-frequency idle jitter"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _keyheaven_ui_poll(context)

    def execute(self, context):
        return execute_per_target_tool(
            self, context, SecondaryPhysicsEngine.apply_micro_tremor,
            min_keyframes=0, filter_type="TRANSFORM",
        )


class KEYHEAVEN_OT_apply_noise(bpy.types.Operator):
    bl_idname = "keyheaven.apply_noise"
    bl_label = "Apply Noise Modifier"
    bl_description = "Adds coherent procedural noise to animation curves"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _keyheaven_ui_poll(context)

    def execute(self, context):
        return execute_per_target_tool(
            self, context, SecondaryPhysicsEngine.apply_noise_modifier,
            min_keyframes=0, filter_type="TRANSFORM",
        )


class KEYHEAVEN_OT_apply_wave(bpy.types.Operator):
    bl_idname = "keyheaven.apply_wave"
    bl_label = "Apply Wave Modifier"
    bl_description = "Adds a procedural wave pattern to animation curves"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _keyheaven_ui_poll(context)

    def execute(self, context):
        return execute_per_target_tool(
            self, context, SecondaryPhysicsEngine.apply_wave_modifier,
            min_keyframes=0, filter_type="TRANSFORM",
        )


class KEYHEAVEN_OT_apply_secondary(bpy.types.Operator):
    bl_idname = "keyheaven.apply_secondary"
    bl_label = "Apply Secondary Motion"
    bl_description = "Adds adaptive secondary motion based on the existing animation"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _keyheaven_ui_poll(context)

    def execute(self, context):
        props = context.scene.keyheaven
        effect = str(getattr(props, "secondary_effect", "NONE"))
        tools = {
            "SQUASH_STRETCH": SecondaryPhysicsEngine.apply_squash_and_stretch,
            "DYNAMIC_FOLLOW": SecondaryPhysicsEngine.apply_dynamic_drag,
            "INERTIAL_JIGGLE": SecondaryPhysicsEngine.apply_inertial_jiggle,
            "MICRO_TREMOR": SecondaryPhysicsEngine.apply_micro_tremor,
            "BREATHING": SecondaryPhysicsEngine.apply_organic_breathing,
        }
        tool = tools.get(effect)
        if tool is None:
            self.report({'WARNING'}, f"Unsupported secondary motion effect '{effect}'")
            return {'CANCELLED'}
        return execute_per_target_tool(
            self, context, tool, min_keyframes=2, filter_type="TRANSFORM",
        )


class KEYHEAVEN_OT_analyze_motion(bpy.types.Operator):
    bl_idname = "keyheaven.analyze_motion"
    bl_label = "Analyze Motion"
    bl_description = "Reports the velocity, acceleration, rest and impact frames of the targets"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _keyheaven_ui_poll(context)

    def execute(self, context):
        targets = TargetResolver.collect_active_targets(
            context, min_keyframes=2, filter_type="TRANSFORM"
        )
        if not targets:
            self.report({'WARNING'}, "No editable animation targets found")
            return {'CANCELLED'}
        summaries = [MotionReportEngine.summarise(target, context) for target in targets]
        report = MotionReportEngine.format(summaries)
        context.scene.keyheaven.motion_report = report
        for line in report.split("\n"):
            print(f"[KeyHeaven] {line}")
        self.report({'INFO'}, "Motion analysis updated")
        return {'FINISHED'}


class KEYHEAVEN_OT_pin_impacts(bpy.types.Operator):
    bl_idname = "keyheaven.pin_impacts"
    bl_label = "Pin Impact Frames"
    bl_description = "Pins the impact frames detected by the motion analysis"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _keyheaven_ui_poll(context)

    def execute(self, context):
        targets = TargetResolver.collect_active_targets(
            context, min_keyframes=2, filter_type="TRANSFORM"
        )
        if not targets:
            self.report({'WARNING'}, "No editable animation targets found")
            return {'CANCELLED'}
        pinned = 0
        restore = []
        for target in targets:
            motion = MotionAnalyzer.analyze_target_motion(target, context)
            impact_frames = sorted(motion.get("impact_frames", set()))
            if not impact_frames:
                continue
            for fcurve in TargetResolver.get_target_fcurves(target):
                for keyframe in fcurve.keyframe_points:
                    previous = bool(keyframe.select_control_point)
                    restore.append((keyframe, previous))
                    keyframe.select_control_point = any(
                        abs(float(keyframe.co[0]) - float(frame)) <= KEY_PROXIMITY_EPS
                        for frame in impact_frames
                    )
                    if keyframe.select_control_point:
                        pinned += 1
        if pinned:
            PinsEngine.pin_selected_keyframes(context, targets=targets)
        for keyframe, previous in restore:
            keyframe.select_control_point = previous
        if not pinned:
            self.report({'WARNING'}, "No impact frames were detected")
            return {'CANCELLED'}
        self.report({'INFO'}, f"Pinned {pinned} impact keyframe(s)")
        return {'FINISHED'}


class KEYHEAVEN_OT_adjust_clearance(bpy.types.Operator):
    bl_idname = "keyheaven.adjust_clearance"
    bl_label = "Adjust Clearance"
    bl_description = "Drags the clearance radius of the active target in the viewport"
    bl_options = {"REGISTER", "UNDO"}

    _center = None

    @classmethod
    def poll(cls, context):
        if not _keyheaven_ui_poll(context):
            return False
        if context.area is None or context.area.type != "VIEW_3D":
            return False
        return context.active_object is not None

    def invoke(self, context, event):
        target = context.active_object
        if target is None:
            return {'CANCELLED'}
        self._center = target.matrix_world.translation.copy()
        context.window_manager.modal_handler_add(self)
        context.scene.keyheaven.clearance_edit_mode = True
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        props = context.scene.keyheaven
        if event.type == "MOUSEMOVE":
            radius = self._radius_from_mouse(context, event)
            if radius is not None:
                props.clearance_edit_radius = radius
        elif event.type in {"LEFTMOUSE", "RIGHTMOUSE", "RET", "NUMPAD_ENTER"}:
            return {'FINISHED'}
        elif event.type == "ESC":
            return {'CANCELLED'}
        return {'RUNNING_MODAL'}

    def _radius_from_mouse(self, context, event):
        region = context.region
        region_data = context.region_data
        if region is None or region_data is None or self._center is None:
            return None
        try:
            center_2d = view3d_utils.location_3d_to_region_2d(
                region, region_data, self._center
            )
            if center_2d is None:
                return None
            depth = max(1e-6, float(region_data.view_distance))
            mouse_3d = view3d_utils.region_2d_to_location_3d(
                region, region_data, (event.mouse_x, event.mouse_y), depth
            )
            if mouse_3d is None:
                return None
            return max(0.0, (mouse_3d - self._center).length)
        except Exception as exc:
            KeyHeavenLogger.log_error("KEYHEAVEN_OT_adjust_clearance", exc)
            return None


class KEYHEAVEN_OT_apply_stagger(bpy.types.Operator):
    bl_idname = "keyheaven.apply_stagger"
    bl_label = "Apply Chain Stagger"
    bl_description = "Offsets keyframe timing across hierarchy chains"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _keyheaven_ui_poll(context)

    def execute(self, context):
        return _run_chain_tool(
            self, context, HierarchicalChainsEngine.apply_chain_stagger
        )


class KEYHEAVEN_OT_apply_propagation_wave(bpy.types.Operator):
    bl_idname = "keyheaven.apply_propagation_wave"
    bl_label = "Apply Propagation Wave"
    bl_description = "Delays targets by distance from the active origin without copying motion"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _keyheaven_ui_poll(context)

    def execute(self, context):
        return _run_chain_tool(
            self, context, HierarchicalChainsEngine.apply_propagation_wave
        )


class KEYHEAVEN_OT_apply_chain_drag(bpy.types.Operator):
    bl_idname = "keyheaven.apply_chain_drag"
    bl_label = "Apply Chain Drag Propagation"
    bl_description = "Propagates progressive rotational drag down hierarchy chains"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _keyheaven_ui_poll(context)

    def execute(self, context):
        return _run_chain_tool(
            self, context, HierarchicalChainsEngine.apply_chain_drag_propagation
        )


class KEYHEAVEN_OT_apply_follow_drag(bpy.types.Operator):
    bl_idname = "keyheaven.apply_follow_drag"
    bl_label = "Apply Follow Drag"
    bl_description = "Adds hierarchical delayed follow-through to child targets"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _keyheaven_ui_poll(context)

    def execute(self, context):
        return _run_chain_tool(
            self, context, HierarchicalChainsEngine.apply_follow_drag
        )


class KEYHEAVEN_OT_apply_polish(bpy.types.Operator):
    bl_idname = "keyheaven.apply_polish"
    bl_label = "Apply Motion Polish"
    bl_description = "Adds anticipation and overshoot at local trajectory extrema"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _keyheaven_ui_poll(context)

    def execute(self, context):
        return execute_per_target_tool(
            self, context, HierarchicalChainsEngine.apply_motion_polish,
            min_keyframes=0, filter_type="TRANSFORM",
        )


class KEYHEAVEN_OT_make_it_loop(bpy.types.Operator):
    bl_idname = "keyheaven.make_it_loop"
    bl_label = "Make It Loop"
    bl_description = "Builds a seamless loop (cycle or ping-pong) across the timeline"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _keyheaven_ui_poll(context)

    def execute(self, context):
        targets = TargetResolver.collect_active_targets(
            context, min_keyframes=2, filter_type="TRANSFORM"
        )
        if not targets:
            self.report({"WARNING"}, "Select at least 1 animated target to loop")
            return {"CANCELLED"}
        return _run_chain_tool(
            self, context, HierarchicalChainsEngine.make_it_loop, min_targets=1
        )


class KEYHEAVEN_OT_apply_easing(bpy.types.Operator):
    bl_idname = "keyheaven.apply_easing"
    bl_label = "Apply Custom Easing"
    bl_description = "Reshapes selected keys with the configured easing function"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _keyheaven_ui_poll(context)

    def execute(self, context):
        return execute_per_target_tool(
            self, context, CurvesEngine.apply_custom_easing,
            min_keyframes=0, filter_type="TRANSFORM",
        )


class KEYHEAVEN_OT_apply_time_scale(bpy.types.Operator):
    bl_idname = "keyheaven.apply_time_scale"
    bl_label = "Apply Elastic Time Scale"
    bl_description = "Compresses or expands keyframe timing around the timeline center"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _keyheaven_ui_poll(context)

    def execute(self, context):
        return execute_per_target_tool(
            self, context, _time_scale_tool,
            min_keyframes=0, filter_type="TRANSFORM",
        )


class KEYHEAVEN_OT_deoverlap_objects(bpy.types.Operator):
    bl_idname = "keyheaven.deoverlap_objects"
    bl_label = "Resolve Spatial Collision"
    bl_description = "Detects clearance-volume intrusion and applies bounded local corrections"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _keyheaven_ui_poll(context)

    def execute(self, context):
        targets = TargetResolver.collect_active_targets(
            context, min_keyframes=0, filter_type="ALL"
        )
        if len(targets) < 2:
            self.report({"WARNING"}, "Select at least 2 targets for spatial clearance")
            return {"CANCELLED"}

        tx = TransactionEngine(targets, context)
        tx.capture(context)
        op_token = op_state_begin(self.bl_idname, targets)
        try:
            ActionBackupEngine.prepare_targets_from_base(targets, force_reset=False)
            op_state_snapshot(self.bl_idname, op_token)
            res = SpatialDeoverlapEngine.deoverlap_targets(targets, context)
            if not res.success:
                op_state_rollback(op_token)
                tx.rollback(context)
                report_operation_result(self, res)
                return {"CANCELLED"}
            tx.commit()
            op_state_commit(op_token)
            report_operation_result(self, res)
            return {"FINISHED"}
        except Exception as e:
            op_state_rollback(op_token)
            tx.rollback(context)
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}


class KEYHEAVEN_OT_sanitize_and_repair_all(bpy.types.Operator):
    bl_idname = "keyheaven.sanitize_and_repair_all"
    bl_label = "Sanitize & Repair All"
    bl_description = "Removes duplicates, repairs monotonic time and prunes stale metadata"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _keyheaven_ui_poll(context)

    def execute(self, context):
        return execute_per_target_tool(
            self, context, SanitizerEngine.sanitize_target,
            min_keyframes=0, filter_type="ALL",
        )


class KEYHEAVEN_OT_cleanup_bake(bpy.types.Operator):
    bl_idname = "keyheaven.cleanup_bake"
    bl_label = "Cleanup Bake"
    bl_description = "Decimates redundant keys while preserving extrema and boundaries"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _keyheaven_ui_poll(context)

    def execute(self, context):
        return execute_per_target_tool(
            self, context, CleanupEngine.cleanup_target,
            min_keyframes=0, filter_type="ALL",
        )


class KEYHEAVEN_OT_autobake(bpy.types.Operator):
    bl_idname = "keyheaven.autobake"
    bl_label = "Autobake"
    bl_description = "Reconstructs each curve with the minimum keys within tolerance"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _keyheaven_ui_poll(context)

    def execute(self, context):
        targets = TargetResolver.collect_active_targets(
            context, min_keyframes=0, filter_type="ALL"
        )
        if not targets:
            self.report({"WARNING"}, "No editable animation targets found")
            return {"CANCELLED"}

        tx = TransactionEngine(targets, context)
        tx.capture(context)
        op_token = op_state_begin(self.bl_idname, targets)
        try:
            ActionBackupEngine.prepare_targets_from_base(targets, force_reset=False)
            op_state_snapshot(self.bl_idname, op_token)
            res = AutoBakeEngine.autobake_targets(targets, context)
            if not res.success:
                op_state_rollback(op_token)
                tx.rollback(context)
                report_operation_result(self, res)
                return {"CANCELLED"}
            tx.commit()
            op_state_commit(op_token)
            report_operation_result(self, res)
            return {"FINISHED"}
        except Exception as e:
            op_state_rollback(op_token)
            tx.rollback(context)
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}


class KEYHEAVEN_OT_apply_preset(bpy.types.Operator):
    bl_idname = "keyheaven.apply_preset"
    bl_label = "Apply Preset"
    bl_description = "Applies a coherent configuration preset to the KeyHeaven panel"
    bl_options = {"REGISTER", "UNDO"}

    preset: bpy.props.EnumProperty(
        name="Preset",
        items=[
            ("SUBTLE", "Subtle", "Low intensity, slow organic motion"),
            ("ENERGETIC", "Energetic", "Stronger timing variation and secondary motion"),
            ("MECHANICAL", "Mechanical", "Robotic timing, tight gaps, minimal secondary"),
            ("ORGANIC", "Organic", "Balanced organic motion with breathing and drag"),
        ],
        default="SUBTLE",
    )

    @classmethod
    def poll(cls, context):
        return _keyheaven_ui_poll(context)

    def execute(self, context):
        props = context.scene.keyheaven
        if self.preset == "SUBTLE":
            props.master_intensity = 0.65
            props.secondary_intensity = 0.7
            props.rhythm_mode = "ORGANIC"
            props.randomizer_iterations = 6
            props.breathing_rate_min, props.breathing_rate_max = 0.02, 0.05
            props.breathing_amp_min, props.breathing_amp_max = 0.004, 0.012
            props.drag_factor_min, props.drag_factor_max = 0.005, 0.02
        elif self.preset == "ENERGETIC":
            props.master_intensity = 1.35
            props.secondary_intensity = 1.4
            props.rhythm_mode = "RANDOM"
            props.randomizer_iterations = 14
            props.breathing_rate_min, props.breathing_rate_max = 0.06, 0.12
            props.breathing_amp_min, props.breathing_amp_max = 0.01, 0.04
            props.anti_factor_min, props.anti_factor_max = 0.10, 0.25
            props.over_factor_min, props.over_factor_max = 0.10, 0.25
        elif self.preset == "MECHANICAL":
            props.master_intensity = 1.0
            props.secondary_intensity = 0.35
            props.rhythm_mode = "ROBOTIC"
            props.min_gap_mode = "SAFE"
            props.min_gap = 0.5
            props.breathing_amp_min, props.breathing_amp_max = 0.001, 0.004
            props.drag_factor_min, props.drag_factor_max = 0.0, 0.01
        else:
            props.master_intensity = 1.0
            props.secondary_intensity = 1.0
            props.rhythm_mode = "ORGANIC"
            props.randomizer_iterations = 10
            props.var_x_min, props.var_x_max = 0.0, 2.0
            props.breathing_rate_min, props.breathing_rate_max = 0.03, 0.08
            props.breathing_amp_min, props.breathing_amp_max = 0.005, 0.02
            props.drag_factor_min, props.drag_factor_max = 0.01, 0.05
        self.report({"INFO"}, f"Applied preset: {self.preset}")
        return {"FINISHED"}
