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
from .randomizer import *
from .curves import *
def _chains_depth(target):
    try:
        if TargetResolver.is_bone(target):
            depth = 0
            current = target.parent
            while current:
                depth += 1
                current = current.parent
            return depth
        owner = TargetResolver.get_owner(target)
        depth = 0
        current = getattr(owner, "parent", None)
        while current:
            depth += 1
            current = current.parent
        return depth
    except Exception:
        return 0


def _chains_depth_ranks(ordered):
    depths = [_chains_depth(target) for target in ordered]
    base = min(depths) if depths else 0
    ranks = [depth - base for depth in depths]
    if len(ranks) > 1 and max(ranks) == 0:
        return list(range(len(ranks)))
    return ranks


def _chains_local_spacing(target):
    try:
        stamps = set()
        for fc in TargetResolver.get_target_fcurves(target, scope="TRANSFORM_ONLY"):
            for kp in fc.keyframe_points:
                stamps.add(round(float(kp.co[0]), TIME_ROUND))
        sorted_stamps = sorted(stamps)
        if len(sorted_stamps) < 2:
            return 1.0
        diffs = [
            sorted_stamps[index + 1] - sorted_stamps[index]
            for index in range(len(sorted_stamps) - 1)
        ]
        diffs.sort()
        return max(TIME_EPS, float(diffs[len(diffs) // 2]))
    except Exception:
        return 1.0


def _chains_shift_target(target, offset, context, result, boundary_enabled):
    """Applies a temporal phase offset to the whole target.

    The propagation is a phase offset of the target timeline, so every key of
    the target moves together and the target keeps its own motion.  Boundary
    protection still guards the content (values) of the keys.
    """
    try:
        TargetResolver.ensure_single_user_action(target)
        fcurves = TargetResolver.get_target_fcurves(target, scope="TRANSFORM_ONLY")
        if not fcurves:
            return False

        poses = {}
        for fc in fcurves:
            for kp in fc.keyframe_points:
                stamp = round(float(kp.co[0]), TIME_ROUND)
                pose = poses.get(stamp)
                if pose is None:
                    pose = {"frame": float(kp.co[0]), "keys": []}
                    poses[stamp] = pose
                pose["keys"].append((fc, kp))

        stamps = sorted(poses.keys())
        if len(stamps) < 2:
            return True

        wall_min = poses[stamps[0]]["frame"]
        wall_max = poses[stamps[-1]]["frame"]

        effective = float(offset)
        if abs(effective) <= TIME_EPS:
            return True

        touched_min = None
        touched_max = None
        for frame, pose in ((poses[stamp]["frame"], poses[stamp]) for stamp in stamps):
            new_frame = frame + effective
            for fc, kp in pose["keys"]:
                old_frame = float(kp.co[0])
                delta = new_frame - old_frame
                if abs(delta) <= TIME_EPS:
                    continue
                kp.co[0] = new_frame
                kp.handle_left[0] += delta
                kp.handle_right[0] += delta
                KeyframeProtectionEngine.mark_key_moved(fc, old_frame, new_frame)
                result.modified_keyframes += 1
            if touched_min is None or new_frame < touched_min:
                touched_min = new_frame
            if touched_max is None or new_frame > touched_max:
                touched_max = new_frame

        gap = max(0.0, float(MinGapEngine.gap_for(context)))
        for fc in fcurves:
            count = len(fc.keyframe_points)
            if count == 0:
                continue
            if gap > 0.0 and count >= 2:
                moved = MinGapEngine.enforce_fcurve(
                    fc,
                    gap,
                    start_f=wall_min + effective,
                    end_f=wall_max + effective,
                    boundary_enabled=True,
                )
                for old_time, new_time in moved:
                    KeyframeProtectionEngine.mark_key_moved(fc, old_time, new_time)
            else:
                fc.keyframe_points.sort()
                fc.update()
            result.modified_fcurves += 1

        if touched_min is not None:
            try:
                if touched_max > float(context.scene.frame_end):
                    context.scene.frame_end = int(math.ceil(touched_max)) + 5
                if touched_min < float(context.scene.frame_start):
                    context.scene.frame_start = int(math.floor(touched_min)) - 2
            except Exception:
                pass
        return True
    except Exception as e:
        KeyHeavenLogger.log_error(
            "HierarchicalChainsEngine._chains_shift_target", e, target
        )
        return False


class HierarchicalChainsEngine:
    """Hierarchical chains and propagation: stagger, origin wave, chained drag, follow lag."""

    @staticmethod
    def apply_chain_stagger(targets, context):
        result = OperationResult("Chain Stagger")
        try:
            if not targets or len(targets) < 2:
                result.add_warning("Select at least 2 targets for chain stagger.")
                return result

            ordered = TargetResolver.sort_targets_hierarchically(list(targets))
            MotionAnalyzer.clear_cache()
            props = context.scene.keyheaven
            rng = KeyHeavenRNG.create(context)
            boundary_enabled = BoundaryLockEngine.is_enabled(context)

            low = float(props.delay_frames_min)
            high = float(props.delay_frames_max)
            if high < low:
                low, high = high, low

            ranks = _chains_depth_ranks(ordered)
            max_rank = max(ranks) if ranks else 0
            offsets = [0.0] * (max_rank + 1)
            cumulative = 0.0
            for level in range(1, max_rank + 1):
                cumulative += apply_master_intensity_scale(
                    rng.uniform(low, high), context
                )
                offsets[level] = cumulative

            for target, rank in zip(ordered, ranks):
                if _chains_shift_target(
                    target, offsets[rank], context, result, boundary_enabled
                ):
                    result.processed_targets += 1

            MotionAnalyzer.clear_cache()
            return result
        except Exception as e:
            KeyHeavenLogger.log_error("HierarchicalChainsEngine.apply_chain_stagger", e)
            result.add_error(f"Execution exception: {e}")
            return result

    @staticmethod
    def apply_propagation_wave(targets, context):
        result = OperationResult("Propagation Wave")
        try:
            if not targets or len(targets) < 2:
                result.add_warning("Select at least 2 targets for propagation wave.")
                return result

            MotionAnalyzer.clear_cache()
            props = context.scene.keyheaven
            speed = max(1e-4, float(props.propagation_wave_speed))
            max_delay = max(0.0, float(props.propagation_max_delay))
            boundary_enabled = BoundaryLockEngine.is_enabled(context)

            origin = targets[0]
            if getattr(context, "mode", "") == "POSE":
                candidate = getattr(context, "active_pose_bone", None)
            else:
                candidate = getattr(context, "active_object", None)
            if candidate is not None and candidate in targets:
                origin = candidate

            origin_pos = TargetResolver.target_world_position(origin)
            ordered = TargetResolver.sort_targets_spatially(list(targets), origin)
            origin_index = 0
            for probe_index, probe in enumerate(ordered):
                if probe == origin:
                    origin_index = probe_index
                    break

            for index, target in enumerate(ordered):
                distance = 0.0
                if target != origin:
                    target_pos = TargetResolver.target_world_position(target)
                    if origin_pos is not None and target_pos is not None:
                        distance = (target_pos - origin_pos).length
                    else:
                        distance = float(abs(index - origin_index))
                delay = min(max_delay, distance / speed)
                delay = apply_master_intensity_scale(delay, context)
                if _chains_shift_target(target, delay, context, result, boundary_enabled):
                    result.processed_targets += 1

            MotionAnalyzer.clear_cache()
            return result
        except Exception as e:
            KeyHeavenLogger.log_error(
                "HierarchicalChainsEngine.apply_propagation_wave", e
            )
            result.add_error(f"Execution exception: {e}")
            return result

    @staticmethod
    def apply_chain_drag_propagation(targets, context):
        result = OperationResult("Chain Drag Propagation")
        try:
            if not targets or len(targets) < 2:
                result.add_warning("Select at least 2 hierarchy targets for chain drag.")
                return result

            ordered = TargetResolver.sort_targets_hierarchically(list(targets))
            MotionAnalyzer.clear_cache()
            props = context.scene.keyheaven
            boundary_enabled = BoundaryLockEngine.is_enabled(context)
            drag_strength = apply_master_intensity_scale(
                float(props.drag_factor_max), context
            )
            gap = max(0.0, float(MinGapEngine.gap_for(context)))

            leader = ordered[0]
            leader_motion = MotionAnalyzer.analyze_target_motion(leader, context)
            ang_vels = leader_motion.get("angular_velocities", {})
            speeds = leader_motion.get("speeds", {})
            start_f, end_f = BoundaryLockEngine.get_boundary_frames(leader, context)

            for depth, target in enumerate(ordered[1:], start=1):
                TargetResolver.ensure_transform_fcurves(target, "rotation_euler")
                TargetResolver.ensure_single_user_action(target)
                rotation_path = TargetResolver.channel_data_path(target, "rotation_euler")
                rot_fcs = {
                    fc.array_index: fc
                    for fc in TargetResolver.get_target_fcurves(
                        target, scope="TRANSFORM_ONLY"
                    )
                    if fc.data_path == rotation_path
                }
                if not rot_fcs:
                    continue

                depth_delay = depth * 1.5
                depth_damping = math.exp(-0.2 * depth)
                sample_frames = set(range(int(start_f), int(end_f) + 1, 2))
                sample_frames.update(leader_motion.get("extremas", []))

                for sample_frame in sorted(sample_frames):
                    if BoundaryLockEngine.is_locked_boundary(
                        sample_frame, start_f, end_f, boundary_enabled
                    ):
                        continue

                    eval_frame = max(int(start_f), int(round(sample_frame - depth_delay)))
                    angular_velocity = ang_vels.get(eval_frame, Vector((0.0, 0.0, 0.0)))
                    speed = speeds.get(eval_frame, 0.0)
                    drag_vector = -drag_strength * depth_damping * (
                        angular_velocity
                        + Vector((speed * 0.05, speed * 0.05, speed * 0.05))
                    )
                    if drag_vector.length < 1e-5:
                        continue

                    for axis in range(3):
                        fc = rot_fcs.get(axis)
                        if fc is None:
                            continue
                        drag_value = drag_vector[axis]
                        existing_kp = None
                        for kp in fc.keyframe_points:
                            if abs(kp.co[0] - sample_frame) < KEY_PROXIMITY_EPS:
                                existing_kp = kp
                                break
                        if existing_kp is not None:
                            if KeyframeProtectionEngine.is_value_locked(fc, existing_kp):
                                continue
                            existing_kp.co[1] += drag_value
                            result.modified_keyframes += 1
                        else:
                            original_value = fc.evaluate(sample_frame)
                            fc.keyframe_points.insert(
                                frame=sample_frame, value=original_value + drag_value
                            )
                            result.modified_keyframes += 1

                for fc in rot_fcs.values():
                    count = len(fc.keyframe_points)
                    if count == 0:
                        continue
                    for kp in fc.keyframe_points:
                        if kp.handle_left_type not in {"FREE", "ALIGNED", "VECTOR"}:
                            kp.handle_left_type = "AUTO_CLAMPED"
                        if kp.handle_right_type not in {"FREE", "ALIGNED", "VECTOR"}:
                            kp.handle_right_type = "AUTO_CLAMPED"
                    if gap > 0.0 and count >= 2:
                        moved = MinGapEngine.enforce_fcurve(
                            fc, gap, boundary_enabled=boundary_enabled
                        )
                        for old_time, new_time in moved:
                            KeyframeProtectionEngine.mark_key_moved(fc, old_time, new_time)
                    else:
                        fc.keyframe_points.sort()
                        fc.update()
                    result.modified_fcurves += 1
                result.processed_targets += 1

            MotionAnalyzer.clear_cache()
            return result
        except Exception as e:
            KeyHeavenLogger.log_error(
                "HierarchicalChainsEngine.apply_chain_drag_propagation", e
            )
            result.add_error(f"Execution exception: {e}")
            return result

    @staticmethod
    def apply_follow_drag(targets, context):
        result = OperationResult("Follow Drag")
        try:
            if not targets or len(targets) < 2:
                result.add_warning("Select at least 2 targets for follow drag.")
                return result

            ordered = TargetResolver.sort_targets_hierarchically(list(targets))
            MotionAnalyzer.clear_cache()
            props = context.scene.keyheaven
            boundary_enabled = BoundaryLockEngine.is_enabled(context)

            low = float(props.drag_factor_min)
            high = float(props.drag_factor_max)
            if high < low:
                low, high = high, low

            ranks = _chains_depth_ranks(ordered)
            max_rank = max(ranks) if ranks else 0

            for index, target in enumerate(ordered):
                factor = low
                if max_rank > 0:
                    factor = low + (high - low) * (ranks[index] / max_rank)
                factor = apply_master_intensity_scale(factor, context)
                offset = factor * _chains_local_spacing(target)
                if _chains_shift_target(target, offset, context, result, boundary_enabled):
                    result.processed_targets += 1

            MotionAnalyzer.clear_cache()
            return result
        except Exception as e:
            KeyHeavenLogger.log_error("HierarchicalChainsEngine.apply_follow_drag", e)
            result.add_error(f"Execution exception: {e}")
            return result

    @staticmethod
    def apply_motion_polish(target, context):
        result = OperationResult("Motion Polish")
        try:
            TargetResolver.ensure_single_user_action(target)
            MotionAnalyzer.clear_cache()
            props = context.scene.keyheaven
            fcurves = TargetResolver.get_target_fcurves(target, scope='TRANSFORM_ONLY')
            if not fcurves:
                result.add_warning(f"No transform curves found on '{target.name}'")
                result.processed_targets = 1
                return result

            rng = KeyHeavenRNG.create(context)
            anti_min = min(float(props.anti_factor_min), float(props.anti_factor_max))
            anti_max = max(float(props.anti_factor_min), float(props.anti_factor_max))
            over_min = min(float(props.over_factor_min), float(props.over_factor_max))
            over_max = max(float(props.over_factor_min), float(props.over_factor_max))
            active_anti = apply_master_intensity_scale(rng.uniform(anti_min, anti_max), context)
            active_over = apply_master_intensity_scale(rng.uniform(over_min, over_max), context)

            start_f, end_f = BoundaryLockEngine.get_boundary_frames(target, context)
            boundary_enabled = BoundaryLockEngine.is_enabled(context)
            gap = max(0.0, float(MinGapEngine.gap_for(context)))
            proximity = max(KEY_PROXIMITY_EPS, gap)
            low = start_f + gap
            high = end_f - gap

            motion = MotionAnalyzer.analyze_target_motion(target, context)
            analyzer_extremas = {
                int(round(float(frame))) for frame in motion.get('extremas', [])
            }

            if high > low:
                for fc in fcurves:
                    pts = sorted(list(fc.keyframe_points), key=lambda k: float(k.co[0]))
                    if len(pts) < 3:
                        continue

                    accepted = [float(kp.co[0]) for kp in pts]
                    insertions = []
                    for i in range(1, len(pts) - 1):
                        p_prev, p_peak, p_next = pts[i - 1], pts[i], pts[i + 1]

                        if BoundaryLockEngine.is_locked_boundary(
                            p_peak.co[0], start_f, end_f, boundary_enabled
                        ):
                            result.skipped_protected += 1
                            continue
                        if (
                            KeyframeProtectionEngine.is_value_locked(fc, p_peak)
                            or KeyframeProtectionEngine.is_timing_locked(fc, p_peak)
                        ):
                            result.skipped_protected += 1
                            continue

                        d1 = float(p_peak.co[1]) - float(p_prev.co[1])
                        d2 = float(p_next.co[1]) - float(p_peak.co[1])
                        peak_frame = int(round(float(p_peak.co[0])))
                        is_extreme = (d1 * d2) < 0.0
                        if (
                            not is_extreme
                            and peak_frame in analyzer_extremas
                            and (abs(d1) <= TIME_EPS) != (abs(d2) <= TIME_EPS)
                        ):
                            is_extreme = True
                        if not is_extreme:
                            continue

                        f_anti = (float(p_prev.co[0]) + float(p_peak.co[0])) / 2.0
                        if low < f_anti < high and all(
                            abs(existing - f_anti) >= proximity for existing in accepted
                        ):
                            y_anti = float(p_prev.co[1]) - (d1 * active_anti)
                            insertions.append((f_anti, y_anti))
                            accepted.append(f_anti)

                        f_over = (float(p_peak.co[0]) + float(p_next.co[0])) / 2.0
                        if low < f_over < high and all(
                            abs(existing - f_over) >= proximity for existing in accepted
                        ):
                            y_over = float(p_peak.co[1]) + (d2 * active_over)
                            insertions.append((f_over, y_over))
                            accepted.append(f_over)

                    if not insertions:
                        continue

                    for f_ins, y_ins in insertions:
                        nkp = fc.keyframe_points.insert(frame=f_ins, value=y_ins)
                        nkp.handle_left_type = 'AUTO_CLAMPED'
                        nkp.handle_right_type = 'AUTO_CLAMPED'
                        result.modified_keyframes += 1

                    fc.keyframe_points.sort()
                    fc.update()
                    result.modified_fcurves += 1

            MotionAnalyzer.clear_cache()
            result.processed_targets = 1
            return result
        except Exception as e:
            KeyHeavenLogger.log_error("HierarchicalChainsEngine.apply_motion_polish", e, target)
            result.add_error(f"Execution exception: {e}")
            return result

    @staticmethod
    def make_it_loop(targets, context):
        result = OperationResult("Make It Loop")
        try:
            targets = list(targets) if targets else []
            if not targets:
                result.add_warning("No targets selected for Make It Loop.")
                return result

            MotionAnalyzer.clear_cache()
            props = context.scene.keyheaven
            loop_mode = getattr(props, "loop_mode", "CYCLE")
            ping_pong = loop_mode == 'PING_PONG'
            gap = max(0.0, float(MinGapEngine.gap_for(context)))
            proximity = max(KEY_PROXIMITY_EPS, gap)

            all_starts = []
            all_ends = []
            for target in targets:
                target_start, target_end = BoundaryLockEngine.get_boundary_frames(target, context)
                all_starts.append(float(target_start))
                all_ends.append(float(target_end))

            global_start = min(all_starts)
            global_end = max(all_ends)
            span = global_end - global_start

            if span < 1.0:
                result.add_warning("Animation span too short (< 1 frame) to construct loop.")
                return result

            new_loop_end = global_end + span

            for target in targets:
                TargetResolver.ensure_single_user_action(target)
                fcurves = TargetResolver.get_target_fcurves(target, scope='TRANSFORM_ONLY')
                if not fcurves:
                    result.add_warning(f"No transform curves found on '{target.name}'")
                    continue

                for fc in fcurves:
                    pts = sorted(list(fc.keyframe_points), key=lambda kp: float(kp.co[0]))
                    if len(pts) < 2:
                        continue

                    forward_pts = [
                        kp for kp in pts if float(kp.co[0]) < global_end - TIME_EPS
                    ]
                    if not forward_pts:
                        continue

                    occupied = [float(kp.co[0]) for kp in pts]
                    first_value = float(pts[0].co[1])
                    mirror_specs = []
                    for kp in forward_pts:
                        mirror_specs.append(
                            (
                                float(kp.co[0]),
                                float(kp.co[1]),
                                float(kp.handle_left[0]),
                                float(kp.handle_left[1]),
                                float(kp.handle_right[0]),
                                float(kp.handle_right[1]),
                                kp.interpolation,
                                getattr(kp, "easing", None),
                                getattr(kp, "handle_right_type", "AUTO_CLAMPED"),
                                getattr(kp, "handle_left_type", "AUTO_CLAMPED"),
                            )
                        )

                    inserted_any = False
                    for (
                        orig_t,
                        orig_y,
                        hl_x,
                        hl_y,
                        hr_x,
                        hr_y,
                        source_interpolation,
                        source_easing,
                        source_left_type,
                        source_right_type,
                    ) in mirror_specs:
                        mirrored_t = global_end + (global_end - orig_t)
                        if any(
                            abs(existing - mirrored_t) < proximity for existing in occupied
                        ):
                            continue

                        nkp = fc.keyframe_points.insert(frame=mirrored_t, value=orig_y)
                        nkp.handle_left[0] = global_end + (global_end - hr_x)
                        nkp.handle_left[1] = hr_y
                        nkp.handle_right[0] = global_end + (global_end - hl_x)
                        nkp.handle_right[1] = hl_y
                        nkp.handle_left_type = source_left_type
                        nkp.handle_right_type = source_right_type

                        if ping_pong:
                            nkp.interpolation = 'BEZIER'
                            KeyframeProtectionEngine.set_protection_mode(fc, nkp, "NONE")
                        else:
                            nkp.interpolation = source_interpolation
                            if hasattr(nkp, "easing") and source_easing is not None:
                                nkp.easing = source_easing

                        occupied.append(mirrored_t)
                        occupied.sort()
                        inserted_any = True
                        result.modified_keyframes += 1

                    if ping_pong and inserted_any:
                        final_time = new_loop_end
                        final_existing = None
                        for kp in fc.keyframe_points:
                            if abs(float(kp.co[0]) - final_time) <= TIME_EPS:
                                final_existing = kp
                                break

                        if final_existing is not None:
                            final_existing.co[1] = first_value
                            final_existing.interpolation = 'BEZIER'
                            final_existing.handle_left_type = 'AUTO_CLAMPED'
                            final_existing.handle_right_type = 'AUTO_CLAMPED'
                        elif all(
                            abs(existing - final_time) >= proximity
                            for existing in occupied
                        ):
                            nkp = fc.keyframe_points.insert(
                                frame=final_time, value=first_value
                            )
                            nkp.interpolation = 'BEZIER'
                            nkp.handle_left_type = 'AUTO_CLAMPED'
                            nkp.handle_right_type = 'AUTO_CLAMPED'
                            KeyframeProtectionEngine.set_protection_mode(fc, nkp, "NONE")
                            occupied.append(final_time)
                            inserted_any = True
                            result.modified_keyframes += 1
                        else:
                            result.add_warning(
                                f"Loop closure key skipped on '{fc.data_path}' "
                                f"[{fc.array_index}] by min gap."
                            )
                    elif inserted_any:
                        ordered = sorted(
                            list(fc.keyframe_points), key=lambda kp: float(kp.co[0])
                        )
                        first_k = ordered[0]
                        last_k = ordered[-1]
                        last_k.co[1] = float(first_k.co[1])
                        last_k.handle_left[1] = float(first_k.handle_right[1])
                        last_k.handle_right[1] = float(first_k.handle_left[1])

                    if not inserted_any:
                        continue

                    fc.keyframe_points.sort()
                    fc.update()
                    result.modified_fcurves += 1

                result.processed_targets += 1

            if result.modified_fcurves > 0 and new_loop_end > context.scene.frame_end:
                context.scene.frame_end = int(math.ceil(new_loop_end))
            KeyHeavenLogger.log_info(
                f"Make It Loop synthesized cycle: [{int(global_start)}, {int(new_loop_end)}]"
            )

            MotionAnalyzer.clear_cache()
            return result
        except Exception as e:
            KeyHeavenLogger.log_error("HierarchicalChainsEngine.make_it_loop", e)
            result.add_error(f"Execution exception: {e}")
            return result
