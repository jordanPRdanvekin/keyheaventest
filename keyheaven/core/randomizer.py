from .._imports import *
from .logger import *
from .constants import *
from .rng import *
from .validator import *
from .actions_compat import *
from .targets import *
from .base_backup import *
from .transaction import *
from .protection import *
from .motion_analysis import *
from .min_gap import *
class RandomizerEngine:
    PIN_DISPLACEMENTS = {}
    PIN_RUN_ACTIVE = False

    @staticmethod
    def begin_pin_run():
        """Starts a run so the pinned groups stay coherent between targets."""
        RandomizerEngine.reset_pin_registry()
        RandomizerEngine.PIN_RUN_ACTIVE = True

    @staticmethod
    def end_pin_run():
        """Ends the current run and drops the pinned group registry."""
        RandomizerEngine.PIN_RUN_ACTIVE = False
        RandomizerEngine.reset_pin_registry()

    @staticmethod
    def reset_pin_registry():
        """Clears the registry that keeps the pinned groups coherent."""
        RandomizerEngine.PIN_DISPLACEMENTS = {}
        RandomizerEngine.PIN_RUN = None

    @staticmethod
    def _cluster_pin_id(unit):
        for pose in unit.get("poses", []):
            for fcurve, keyframe in pose.get("entries", []):
                pin_id = PinsEngine.get_pin_id(fcurve, keyframe)
                if pin_id:
                    return pin_id
        return None

    @staticmethod
    def _align_pinned_cluster(unit):
        """Keeps a pinned group on the same temporal relationship.

        The first target of a pin group defines the displacement of the group
        and the rest of the targets reuse it, so the shared timing of the
        pinned keys is preserved across targets.
        """
        pin_id = RandomizerEngine._cluster_pin_id(unit)
        if not pin_id:
            return
        origin = unit["origin_times"][0]
        own_displacement = unit["current_times"][0] - origin
        reference = RandomizerEngine.PIN_DISPLACEMENTS.get(pin_id)
        if reference is None:
            RandomizerEngine.PIN_DISPLACEMENTS[pin_id] = own_displacement
            return
        if abs(own_displacement - reference) > 1e-6:
            RandomizerEngine.PIN_DISPLACEMENTS[pin_id] = own_displacement
        correction = reference - own_displacement
        if abs(correction) <= 1e-6:
            return
        unit["current_times"] = [value + correction for value in unit["current_times"]]
        for pose, new_time in zip(unit["poses"], unit["current_times"]):
            pose["current_time"] = new_time

    @staticmethod
    def _slack_delta(rng, rhythm, slack, var_x, index):
        if rhythm == "ROBOTIC":
            delta = slack * rng.uniform(-0.25, 0.25)
            return max(-var_x, min(var_x, delta))
        if rhythm == "RANDOM":
            return max(-var_x, min(var_x, rng.uniform(-var_x, var_x)))
        delta_u = rng.uniform(-var_x, var_x)
        delta_g = rng.gauss(0.0, max(0.01, var_x * 0.5))
        accent = (2.0 if index % 2 == 0 else 0.3) * rng.uniform(0.7, 1.3)
        delta_sync = var_x * (accent - 1.0) * 0.5
        delta = 0.35 * delta_u + 0.25 * delta_g + 0.40 * delta_sync
        return max(-var_x, min(var_x, delta))

    @staticmethod
    def apply_randomizer(target, context):
        result = OperationResult("Randomizer")
        if not RandomizerEngine.PIN_RUN_ACTIVE:
            RandomizerEngine.reset_pin_registry()
        try:
            TargetResolver.ensure_single_user_action(target)
            MotionAnalyzer.clear_cache()
            props = context.scene.keyheaven
            fcurves = TargetResolver.get_target_fcurves(target, scope="TRANSFORM_ONLY")
            if not fcurves:
                result.add_warning(f"No active transform curves found on '{target.name}'")
                result.processed_targets = 1
                return result

            rng = KeyHeavenRNG.create(context)
            effective_gap = MinGapEngine.gap_for(context)
            gap_mode = str(getattr(props, "min_gap_mode", "SAFE"))
            gap_magnitude = MinGapEngine.magnitude_for(context)
            if gap_mode == "SAFE":
                placement_gap = gap_magnitude if gap_magnitude > 1e-2 else 0.01
            elif gap_mode == "RELAXED":
                placement_gap = max(0.01, gap_magnitude * 0.25)
            else:
                placement_gap = 0.01
            boundary_enabled = BoundaryLockEngine.is_enabled(context)
            scope = str(getattr(props, "random_scope", "TIME"))
            temporal_active = bool(getattr(props, "rand_time", True)) and scope in ("TIME", "BOTH")
            value_scope = scope in ("VALUES", "BOTH")
            pose_dict = {}
            wall_min = 0.0
            wall_max = 0.0

            if temporal_active:
                for fc in fcurves:
                    for kp in fc.keyframe_points:
                        t_val = round(float(kp.co[0]), TIME_ROUND)
                        pose = pose_dict.get(t_val)
                        if pose is None:
                            pose = {
                                "current_time": float(kp.co[0]),
                                "entries": [],
                                "is_selected": False,
                            }
                            pose_dict[t_val] = pose
                        pose["entries"].append((fc, kp))
                        if kp.select_control_point:
                            pose["is_selected"] = True

                sorted_initial_times = sorted(pose_dict.keys())
                if len(sorted_initial_times) < 2:
                    result.add_warning(
                        f"Target '{target.name}' has less than 2 keyframe poses."
                    )
                    temporal_active = False
                else:
                    wall_min = sorted_initial_times[0]
                    wall_max = sorted_initial_times[-1]

            if temporal_active:
                motion_info = MotionAnalyzer.analyze_target_motion(target, context)
                time_locked_set = set(motion_info.get("time_locked_set", set()))
                has_selection = any(p["is_selected"] for p in pose_dict.values())
                iterations = max(1, int(props.randomizer_iterations))

                raw_clusters = KeyframeProtectionEngine.identify_temporal_clusters(
                    sorted_initial_times, time_locked_set
                )
                pose_units = []
                for unit_type, times in raw_clusters:
                    if unit_type == "FREE":
                        t_val = times
                        unit_times = [t_val]
                        is_barrier = (
                            boundary_enabled
                            and (
                                abs(t_val - wall_min) <= TIME_EPS
                                or abs(t_val - wall_max) <= TIME_EPS
                            )
                        )
                        if has_selection and not pose_dict[t_val]["is_selected"]:
                            is_barrier = True
                    else:
                        unit_times = list(times)
                        is_barrier = boundary_enabled and any(
                            abs(t_val - wall_min) <= TIME_EPS
                            or abs(t_val - wall_max) <= TIME_EPS
                            for t_val in unit_times
                        )
                        if has_selection and all(
                            not pose_dict[t_val]["is_selected"]
                            for t_val in unit_times
                        ):
                            is_barrier = True

                    pose_units.append(
                        {
                            "type": unit_type,
                            "times": unit_times,
                            "is_barrier": is_barrier,
                            "current_times": [
                                pose_dict[t_val]["current_time"] for t_val in unit_times
                            ],
                            "origin_times": [
                                pose_dict[t_val]["current_time"] for t_val in unit_times
                            ],
                            "poses": [pose_dict[t_val] for t_val in unit_times],
                        }
                    )

                rhythm_choice = getattr(props, "rhythm_mode", "ORGANIC")
                var_x_min = float(props.var_x_min)
                var_x_max = float(props.var_x_max)
                displacement_limit = max(
                    1e-6, apply_master_intensity_scale(var_x_max, context)
                )

                for pass_idx in range(iterations):
                    for unit in pose_units:
                        unit["current_times"] = [
                            pose["current_time"] for pose in unit["poses"]
                        ]

                    active_var_x = apply_master_intensity_scale(
                        rng.uniform(var_x_min, var_x_max), context
                    )

                    unit_count = len(pose_units)
                    idx = 0
                    while idx < unit_count:
                        if pose_units[idx]["is_barrier"]:
                            idx += 1
                            continue

                        seg_start = idx
                        while idx < unit_count and not pose_units[idx]["is_barrier"]:
                            idx += 1
                        seg_end = idx

                        left_limit = (
                            wall_min
                            if seg_start == 0
                            else pose_units[seg_start - 1]["current_times"][-1]
                        )
                        right_limit = (
                            wall_max
                            if seg_end == unit_count
                            else pose_units[seg_end]["current_times"][0]
                        )
                        if right_limit <= left_limit:
                            continue

                        seg_units = pose_units[seg_start:seg_end]
                        k = len(seg_units)
                        if k == 0:
                            continue

                        unit_widths = [
                            unit["current_times"][-1] - unit["current_times"][0]
                            for unit in seg_units
                        ]
                        total_unit_width = sum(unit_widths)
                        min_required_space = total_unit_width + (k + 1) * placement_gap
                        total_interval_span = right_limit - left_limit
                        free_slack = total_interval_span - min_required_space

                        if free_slack <= 1e-4:
                            step_span = max(
                                placement_gap, total_interval_span / max(1.0, float(k + 1))
                            )
                            curr_pos = left_limit + step_span
                            for i_u, unit in enumerate(seg_units):
                                unit_span = unit_widths[i_u]
                                rel_offsets = [
                                    unit["current_times"][idx_t]
                                    - unit["current_times"][0]
                                    for idx_t in range(len(unit["current_times"]))
                                ]
                                clamped_pos = min(
                                    right_limit - placement_gap - unit_span, curr_pos
                                )
                                unit["current_times"] = [
                                    clamped_pos + rel_offset
                                    for rel_offset in rel_offsets
                                ]
                                curr_pos += unit_span + step_span
                            for unit in seg_units:
                                for pose, new_time in zip(
                                    unit["poses"], unit["current_times"]
                                ):
                                    pose["current_time"] = new_time
                            continue

                        slacks = [
                            max(
                                0.0,
                                seg_units[0]["current_times"][0]
                                - left_limit
                                - placement_gap,
                            )
                        ]
                        for i_u in range(1, k):
                            prev_end = seg_units[i_u - 1]["current_times"][-1]
                            curr_start = seg_units[i_u]["current_times"][0]
                            slacks.append(
                                max(0.0, curr_start - prev_end - placement_gap)
                            )
                        slacks.append(
                            max(
                                0.0,
                                right_limit
                                - seg_units[-1]["current_times"][-1]
                                - placement_gap,
                            )
                        )

                        walk = [0.0]
                        walk_current = 0.0
                        for j_s, s_val in enumerate(slacks):
                            step = RandomizerEngine._slack_delta(
                                rng, rhythm_choice, s_val, active_var_x, j_s
                            )
                            walk_current += step
                            if walk_current > displacement_limit:
                                walk_current = 2.0 * displacement_limit - walk_current
                            elif walk_current < -displacement_limit:
                                walk_current = -2.0 * displacement_limit - walk_current
                            walk.append(walk_current)

                        walk_count = len(walk)
                        trend = walk[-1]
                        adjustments = [
                            walk[index] - trend * ((index + 1) / walk_count)
                            for index in range(walk_count)
                        ]

                        final_slacks = []
                        for j_s, s_val in enumerate(slacks):
                            previous = adjustments[j_s - 1] if j_s > 0 else 0.0
                            final_slacks.append(
                                max(1e-5, s_val + (adjustments[j_s] - previous))
                            )

                        sum_final = sum(final_slacks)
                        norm_factor = (
                            free_slack / sum_final if sum_final > 1e-6 else 1.0
                        )
                        final_slacks = [value * norm_factor for value in final_slacks]

                        curr_pos = left_limit + placement_gap + final_slacks[0]
                        for i_u, unit in enumerate(seg_units):
                            unit_span = unit_widths[i_u]
                            rel_offsets = [
                                unit["current_times"][idx_t]
                                - unit["current_times"][0]
                                for idx_t in range(len(unit["current_times"]))
                            ]
                            unit["current_times"] = [
                                curr_pos + rel_offset for rel_offset in rel_offsets
                            ]
                            curr_pos = (
                                unit["current_times"][-1]
                                + placement_gap
                                + final_slacks[i_u + 1]
                            )

                        for unit in seg_units:
                            for pose, new_time in zip(
                                unit["poses"], unit["current_times"]
                            ):
                                pose["current_time"] = new_time
                            RandomizerEngine._align_pinned_cluster(unit)

                for pose in pose_dict.values():
                    for fc, kp in pose["entries"]:
                        old_frame = float(kp.co[0])
                        new_frame = pose["current_time"]
                        delta_x = new_frame - old_frame
                        if abs(delta_x) > 1e-5:
                            kp.co[0] = new_frame
                            kp.handle_left[0] += delta_x
                            kp.handle_right[0] += delta_x
                            KeyframeProtectionEngine.mark_key_moved(
                                fc, old_frame, new_frame
                            )
                            result.modified_keyframes += 1

            value_touched = []
            boundary_start, boundary_end = BoundaryLockEngine.get_boundary_frames(
                target, context
            )
            location_path = TargetResolver.channel_data_path(target, "location")
            rotation_euler_path = TargetResolver.channel_data_path(
                target, "rotation_euler"
            )
            rotation_quat_path = TargetResolver.channel_data_path(
                target, "rotation_quaternion"
            )
            scale_path = TargetResolver.channel_data_path(target, "scale")

            for fc in fcurves:
                if not value_scope:
                    break
                enabled = False
                if fc.data_path == location_path:
                    if fc.array_index == 0:
                        enabled = bool(props.rand_pos_x)
                    elif fc.array_index == 1:
                        enabled = bool(props.rand_pos_y)
                    elif fc.array_index == 2:
                        enabled = bool(props.rand_pos_z)
                elif fc.data_path == rotation_euler_path:
                    enabled = bool(props.rand_rot)
                elif fc.data_path == scale_path:
                    enabled = bool(props.rand_scale)

                if not enabled:
                    continue

                sigma = apply_master_intensity_scale(
                    0.02 * get_channel_scale(fc), context
                )
                if sigma <= 0.0:
                    continue

                changed = False
                for kp in fc.keyframe_points:
                    if boundary_enabled and BoundaryLockEngine.is_locked_boundary(
                        kp.co[0],
                        boundary_start,
                        boundary_end,
                        boundary_enabled,
                    ):
                        result.skipped_protected += 1
                        continue
                    if KeyframeProtectionEngine.is_value_locked(fc, kp):
                        result.skipped_protected += 1
                        continue
                    kp.co[1] += rng.gauss(0.0, sigma)
                    result.modified_keyframes += 1
                    changed = True
                if changed:
                    value_touched.append(fc)

            if value_scope and props.rand_rot and rotation_quat_path:
                quaternion_channels = [
                    fc for fc in fcurves if fc.data_path == rotation_quat_path
                ]
                if quaternion_channels:
                    modified = RandomizerEngine._randomize_quaternion_values(
                        target, quaternion_channels, props, context, rng, result
                    )
                    value_touched.extend(quaternion_channels)
                    result.modified_keyframes += modified

            update_fcurves = fcurves if temporal_active else value_touched
            validation_gap = effective_gap if temporal_active else 0.0
            for fc in update_fcurves:
                try:
                    fc.keyframe_points.sort()
                except Exception:
                    pass
                fc.update()
                structural_ok, reason = AnimationValidator.validate_fcurve(fc, 0.0)
                if not structural_ok:
                    result.add_error(
                        f"Validation failed on '{fc.data_path}': {reason}"
                    )
                elif validation_gap > 0.0:
                    gap_ok, gap_reason = AnimationValidator.validate_fcurve(
                        fc, validation_gap
                    )
                    if not gap_ok:
                        result.add_warning(
                            f"Min gap notice on '{fc.data_path}': {gap_reason}"
                        )
                result.modified_fcurves += 1

            MotionAnalyzer.clear_cache()
            result.processed_targets = 1
            return result
        except Exception as e:
            KeyHeavenLogger.log_error("RandomizerEngine.apply_randomizer", e, target)
            result.add_error(f"Execution exception: {e}")
            return result

    @staticmethod
    def quick_animate_generator(target, context):
        result = OperationResult("Quick Animate")
        try:
            TargetResolver.ensure_transform_fcurves(target, "location")
            TargetResolver.ensure_single_user_action(target)
            MotionAnalyzer.clear_cache()
            props = context.scene.keyheaven
            count = max(4, int(props.quick_anim_keys))

            start_f, end_f = BoundaryLockEngine.get_boundary_frames(target, context)
            span = max(1.0, end_f - start_f)
            step = span / float(count - 1)

            fcurves = TargetResolver.get_target_fcurves(
                target, scope="TRANSFORM_ONLY"
            )
            loc_fcs = [fc for fc in fcurves if fc.data_path.endswith("location")]
            rng = KeyHeavenRNG.create(context)
            boundary_enabled = BoundaryLockEngine.is_enabled(context)

            for fc in loc_fcs:
                for i in range(count):
                    frame = start_f + (i * step)
                    if BoundaryLockEngine.is_locked_boundary(
                        frame, start_f, end_f, boundary_enabled
                    ):
                        continue

                    val_delta = apply_master_intensity_scale(
                        rng.uniform(-0.5, 0.5), context
                    )

                    existing_kp = None
                    for kp in fc.keyframe_points:
                        if abs(kp.co[0] - frame) < KEY_PROXIMITY_EPS:
                            existing_kp = kp
                            break

                    if existing_kp is not None:
                        if boundary_enabled and BoundaryLockEngine.is_locked_boundary(
                            existing_kp.co[0],
                            start_f,
                            end_f,
                            boundary_enabled,
                        ):
                            result.skipped_protected += 1
                            continue
                        if KeyframeProtectionEngine.is_value_locked(fc, existing_kp):
                            result.skipped_protected += 1
                            continue
                        existing_kp.co[1] += val_delta
                        result.modified_keyframes += 1
                    else:
                        orig_val = fc.evaluate(frame)
                        fc.keyframe_points.insert(
                            frame=frame, value=orig_val + val_delta
                        )
                        result.modified_keyframes += 1

                fc.keyframe_points.sort()
                for kp in fc.keyframe_points:
                    if kp.handle_left_type not in {"FREE", "ALIGNED", "VECTOR"}:
                        kp.handle_left_type = "AUTO_CLAMPED"
                        kp.handle_right_type = "AUTO_CLAMPED"
                fc.update()
                result.modified_fcurves += 1

            MotionAnalyzer.clear_cache()
            result.processed_targets = 1
            return result
        except Exception as e:
            KeyHeavenLogger.log_error(
                "RandomizerEngine.quick_animate_generator", e, target
            )
            result.add_error(f"Execution exception: {e}")
            return result

    @staticmethod
    def select_random_targets(context, percentage=50.0):
        selected_total = 0
        try:
            props = context.scene.keyheaven
            pool_mode = getattr(props, "selection_pool_mode", "ALL")
            rng = KeyHeavenRNG.create(context)
            all_targets = TargetResolver.collect_active_targets(
                context, min_keyframes=2, filter_type="ALL"
            )
            eligible = [
                target
                for target in all_targets
                if TargetResolver.is_bone(target)
                or (HAS_BPY and isinstance(target, bpy.types.Object))
            ]
            if not eligible:
                return 0

            currently_selected = []
            for target in eligible:
                if TargetResolver.is_bone(target):
                    if target.select:
                        currently_selected.append(target)
                else:
                    if target.select_get():
                        currently_selected.append(target)

            pool = currently_selected if pool_mode == "CURRENT" else eligible
            if not pool:
                return 0

            pct = max(0.0, min(100.0, float(percentage)))
            count = max(1, int(len(pool) * (pct / 100.0))) if pct > 0.0 else 0
            count = min(count, len(pool))
            kept_indices = set(rng.sample(range(len(pool)), count))
            kept_ids = {id(pool[i]) for i in kept_indices}

            if pool_mode != "CURRENT":
                for target in pool:
                    try:
                        if TargetResolver.is_bone(target):
                            target.select = False
                        else:
                            target.select_set(False)
                    except Exception:
                        pass

            for target in pool:
                is_kept = id(target) in kept_ids
                try:
                    if TargetResolver.is_bone(target):
                        target.select = is_kept
                    else:
                        target.select_set(is_kept)
                except Exception:
                    pass

            selected_total = len(kept_ids)
        except Exception as e:
            KeyHeavenLogger.log_error("RandomizerEngine.select_random_targets", e)
        return selected_total

    @staticmethod
    def select_random_keyframes(context, percentage=50.0):
        selected_total = 0
        try:
            props = context.scene.keyheaven
            pool_mode = getattr(props, "selection_pool_mode", "ALL")
            rng = KeyHeavenRNG.create(context)
            boundary_enabled = BoundaryLockEngine.is_enabled(context)
            pct = max(0.0, min(100.0, float(percentage)))

            targets = TargetResolver.collect_active_targets(
                context, min_keyframes=2, filter_type="ALL"
            )
            for target in targets:
                start_f, end_f = BoundaryLockEngine.get_boundary_frames(
                    target, context
                )
                for fc in TargetResolver.get_target_fcurves(target):
                    points = list(fc.keyframe_points)
                    if len(points) < 3:
                        continue

                    movable = [
                        kp
                        for kp in points
                        if not (
                            boundary_enabled
                            and BoundaryLockEngine.is_locked_boundary(
                                kp.co[0],
                                start_f,
                                end_f,
                                boundary_enabled,
                            )
                        )
                        and not KeyframeProtectionEngine.is_timing_locked(fc, kp)
                    ]

                    if pool_mode == "CURRENT":
                        pool = [
                            kp for kp in movable if kp.select_control_point
                        ]
                    else:
                        pool = movable

                    if not pool:
                        continue

                    count = max(1, int(len(pool) * (pct / 100.0))) if pct > 0.0 else 0
                    count = min(count, len(pool))
                    kept_indices = set(rng.sample(range(len(pool)), count))
                    kept_ids = {id(pool[i]) for i in kept_indices}

                    if pool_mode != "CURRENT":
                        for kp in pool:
                            kp.select_control_point = False

                    for kp in pool:
                        kp.select_control_point = id(kp) in kept_ids

                    selected_total += len(kept_ids)
                    fc.update()
        except Exception as e:
            KeyHeavenLogger.log_error("RandomizerEngine.select_random_keyframes", e)
        return selected_total

    @staticmethod
    def _randomize_quaternion_values(target, channels, props, context, rng, result):
        """Randomises a quaternion rotation as a coherent unit.

        The four components are never perturbed independently: the rotation is
        expressed as an axis angle offset and the result is normalised, so the
        quaternion stays a valid rotation.
        """
        reference = channels[0]
        pairs = ActionAdapter.read_keyframes(reference)
        if not pairs:
            return 0
        times = [frame for frame, _ in pairs]
        axis = Vector(
            (rng.uniform(-1.0, 1.0), rng.uniform(-1.0, 1.0), rng.uniform(-1.0, 1.0))
        )
        if axis.length < 1e-6:
            axis = Vector((0.0, 0.0, 1.0))
        axis.normalize()
        amplitude = math.radians(8.0) * apply_master_intensity_scale(
            0.02 * get_channel_scale(reference), context
        )
        component_values = []
        for fcurve in channels:
            values = ActionAdapter.read_keyframes(fcurve)
            component_values.append(
                [
                    values[index][1] if index < len(values) else 0.0
                    for index in range(len(pairs))
                ]
            )
        boundary_enabled = BoundaryLockEngine.is_enabled(context)
        boundary_start, boundary_end = BoundaryLockEngine.get_boundary_frames(
            target, context
        )
        modified = 0
        for index, frame in enumerate(times):
            components = [
                component_values[axis_index][index]
                for axis_index in range(len(channels))
            ]
            quaternion = normalise_quaternion(components)
            if boundary_enabled and BoundaryLockEngine.is_locked_boundary(
                frame, boundary_start, boundary_end, True
            ):
                continue
            points = list(reference.keyframe_points)
            if index >= len(points):
                continue
            if KeyframeProtectionEngine.is_value_locked(reference, points[index]):
                result.skipped_protected += 1
                continue
            angle = amplitude * rng.gauss(0.0, 1.0)
            half = angle * 0.5
            delta = (
                math.cos(half),
                axis.x * math.sin(half),
                axis.y * math.sin(half),
                axis.z * math.sin(half),
            )
            w0, x0, y0, z0 = quaternion
            w1, x1, y1, z1 = delta
            merged = normalise_quaternion(
                (
                    w0 * w1 - x0 * x1 - y0 * y1 - z0 * z1,
                    w0 * x1 + x0 * w1 + y0 * z1 - z0 * y1,
                    w0 * y1 - x0 * z1 + y0 * w1 + z0 * x1,
                    w0 * z1 + x0 * y1 - y0 * x1 + z0 * w1,
                )
            )
            for axis_index, fcurve in enumerate(channels):
                fcurve_points = list(fcurve.keyframe_points)
                if index >= len(fcurve_points):
                    continue
                value = merged[axis_index] if axis_index < len(merged) else merged[0]
                fcurve_points[index].co[1] = value
            modified += 1
        return modified
