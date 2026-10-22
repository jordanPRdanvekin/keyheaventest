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
from .chains import *
from .secondary import *
from .spatial import *
def rdp_simplify_iterative(points, epsilon):
    if not points or len(points) < 3:
        return list(points) if points else []

    n = len(points)
    keep_mask = [False] * n
    keep_mask[0] = True
    keep_mask[-1] = True
    eps = max(0.0, float(epsilon))
    stack = [(0, n - 1)]

    while stack:
        start_idx, end_idx = stack.pop()
        if end_idx - start_idx < 2:
            continue

        p1 = points[start_idx]
        p2 = points[end_idx]
        dx = float(p2[0]) - float(p1[0])
        dy = float(p2[1]) - float(p1[1])
        line_len_sq = dx * dx + dy * dy
        max_dist = 0.0
        max_idx = start_idx

        for i in range(start_idx + 1, end_idx):
            p = points[i]
            if line_len_sq < 1e-10:
                dist = math.hypot(float(p[0]) - float(p1[0]), float(p[1]) - float(p1[1]))
            else:
                numerator = abs(
                    dy * float(p[0])
                    - dx * float(p[1])
                    + float(p2[0]) * float(p1[1])
                    - float(p2[1]) * float(p1[0])
                )
                dist = numerator / math.sqrt(line_len_sq)

            if dist > max_dist:
                max_dist = dist
                max_idx = i

        if max_dist > eps:
            keep_mask[max_idx] = True
            stack.append((start_idx, max_idx))
            stack.append((max_idx, end_idx))

    return [points[i] for i in range(n) if keep_mask[i]]


def _sanitize_duplicate_indices(fc, start_f, end_f, boundary_enabled):
    points = list(fc.keyframe_points)
    remove_indices = []
    i = 0
    while i < len(points):
        group = [i]
        j = i + 1
        while j < len(points) and abs(
            float(points[j].co[0]) - float(points[group[-1]].co[0])
        ) <= TIME_EPS:
            group.append(j)
            j += 1

        if len(group) > 1:
            anchor = None
            for idx in group:
                if KeyframeProtectionEngine.is_value_locked(fc, points[idx]):
                    anchor = idx
                    break
            if anchor is None:
                for idx in group:
                    if BoundaryLockEngine.is_locked_boundary(
                        float(points[idx].co[0]), start_f, end_f, boundary_enabled
                    ):
                        anchor = idx
                        break
            if anchor is None:
                for idx in group:
                    if KeyframeProtectionEngine.is_timing_locked(fc, points[idx]):
                        anchor = idx
                        break
            if anchor is None:
                anchor = group[0]

            for idx in group:
                if idx == anchor:
                    continue
                kp = points[idx]
                if BoundaryLockEngine.is_locked_boundary(
                    float(kp.co[0]), start_f, end_f, boundary_enabled
                ):
                    continue
                if KeyframeProtectionEngine.is_value_locked(fc, kp):
                    continue
                if KeyframeProtectionEngine.is_timing_locked(fc, kp):
                    continue
                remove_indices.append(idx)

        i = j

    return remove_indices


def _sanitize_protected_times(fc, points, start_f, end_f, boundary_enabled):
    protected = set()
    for kp in points:
        frame = float(kp.co[0])
        if BoundaryLockEngine.is_locked_boundary(frame, start_f, end_f, boundary_enabled):
            protected.add(round(frame, TIME_ROUND))
        elif KeyframeProtectionEngine.is_value_locked(
            fc, kp
        ) or KeyframeProtectionEngine.is_timing_locked(fc, kp):
            protected.add(round(frame, TIME_ROUND))
    return protected


def _sanitize_eval_frames(start_t, end_t, key_count):
    span = float(end_t) - float(start_t)
    if span <= TIME_EPS:
        return []
    step = max(1.0, span / min(500.0, max(2.0, float(key_count) * 2.0)))
    count = int(math.ceil(span / step)) + 1
    return [float(start_t) + i * step for i in range(count)]


def _sanitize_prune_metadata(target, fcurves):
    owner = TargetResolver.get_owner(target)
    candidates = []
    if owner is not None:
        try:
            candidates.extend(ActionAdapter.get_fcurves(owner))
        except Exception as e:
            KeyHeavenLogger.log_error("_sanitize_prune_metadata", e, target)
    candidates.extend(fcurves)

    groups = {}
    seen = set()
    for fc in candidates:
        action = KeyframeMetaStore.action_of(fc)
        if action is None:
            continue
        marker = (
            id(action),
            getattr(fc, "data_path", ""),
            int(getattr(fc, "array_index", 0)),
        )
        if marker in seen:
            continue
        seen.add(marker)
        action_key = id(action)
        if action_key not in groups:
            groups[action_key] = (action, [])
        groups[action_key][1].append(fc)

    for action, action_fcurves in groups.values():
        KeyframeMetaStore.prune(action, action_fcurves)


def _sanitize_repair_spikes(fc, points, start_f, end_f, boundary_enabled):
    """Flattens isolated spikes that reverse the slope of the curve.

    This keeps the adaptive spike repair of the 3.9.5 baseline: a key whose
    slope reverses by more than the adaptive threshold is replaced by the
    average of its neighbours.
    """
    if len(points) < 3:
        return 0
    y_range = get_channel_scale(fc)
    threshold = max(0.01, y_range * 0.35)
    repaired = 0
    for index in range(1, len(points) - 1):
        point = points[index]
        if boundary_enabled and BoundaryLockEngine.is_locked_boundary(
            point.co[0], start_f, end_f, True
        ):
            continue
        if KeyframeProtectionEngine.is_value_locked(fc, point):
            continue
        previous_value = float(points[index - 1].co[1])
        current_value = float(point.co[1])
        next_value = float(points[index + 1].co[1])
        first_slope = current_value - previous_value
        second_slope = next_value - current_value
        if abs(first_slope) > threshold and (
            first_slope * second_slope
        ) < -0.5 * threshold * threshold:
            point.co[1] = (previous_value + next_value) * 0.5
            point.handle_left_type = "AUTO_CLAMPED"
            point.handle_right_type = "AUTO_CLAMPED"
            repaired += 1
    return repaired


class SanitizerEngine:
    @staticmethod
    def sanitize_target(target, context):
        result = OperationResult("Sanitize")
        try:
            if target is None:
                result.add_warning("No target supplied")
                result.processed_targets = 1
                return result

            props = context.scene.keyheaven
            TargetResolver.ensure_single_user_action(target)
            fcurves = TargetResolver.get_target_fcurves(target, scope="TRANSFORM_ONLY")
            if not fcurves:
                result.add_warning(
                    f"No transform curves on '{getattr(target, 'name', 'target')}'"
                )
                result.processed_targets = 1
                return result

            start_f, end_f = BoundaryLockEngine.get_boundary_frames(target, context)
            boundary_enabled = BoundaryLockEngine.is_enabled(context)
            final_epsilon = max(
                1e-5, float(getattr(props, "cleanup_rdp_epsilon", 1.0))
            )
            tolerance = max(
                0.0001, float(getattr(props, "cleanup_error_tolerance", 0.05))
            )
            gap = MinGapEngine.gap_for(context)
            total_removed = 0
            total_repaired = 0

            for fc in fcurves:
                fc.keyframe_points.sort()
                points = list(fc.keyframe_points)
                if len(points) < 2:
                    continue

                repaired = _sanitize_repair_spikes(
                    fc, points, start_f, end_f, boundary_enabled
                )
                if repaired:
                    total_repaired += repaired
                    fc.keyframe_points.sort()
                    fc.update()
                    points = list(fc.keyframe_points)
                snapshot = AnimationValidator.snapshot_fcurve(fc)
                original_gap_valid, _ = AnimationValidator.validate_fcurve(fc, gap)
                duplicate_indices = _sanitize_duplicate_indices(
                    fc, start_f, end_f, boundary_enabled
                )
                duplicate_set = set(duplicate_indices)
                cleaned_snapshot = [
                    entry for i, entry in enumerate(snapshot) if i not in duplicate_set
                ]
                survivors = [
                    (i, kp) for i, kp in enumerate(points) if i not in duplicate_set
                ]
                start_t = float(survivors[0][1].co[0])
                end_t = float(survivors[-1][1].co[0])

                if len(survivors) < 3 or (end_t - start_t) <= TIME_EPS:
                    if not duplicate_indices:
                        continue
                    AnimationValidator.remove_keyframe_indices(fc, duplicate_indices)
                    fc.keyframe_points.sort()
                    fc.update()
                    valid, reason = AnimationValidator.check_curve_validity(
                        fc, gap, original_gap_valid
                    )
                    if not valid:
                        AnimationValidator.restore_fcurve(fc, snapshot)
                        result.add_warning(
                            f"Sanitize reverted '{fc.data_path}'[{fc.array_index}]: {reason}"
                        )
                    else:
                        total_removed += len(duplicate_indices)
                        result.modified_fcurves += 1
                    continue

                eval_frames = _sanitize_eval_frames(
                    start_t, end_t, len(survivors)
                )
                original_eval = {
                    frame: float(fc.evaluate(frame)) for frame in eval_frames
                }
                survivor_points = [kp for i, kp in survivors]
                protected_times = _sanitize_protected_times(
                    fc, survivor_points, start_f, end_f, boundary_enabled
                )
                coords = [
                    (float(kp.co[0]), float(kp.co[1])) for kp in survivor_points
                ]
                simplified = rdp_simplify_iterative(coords, final_epsilon)
                keep_times = {
                    round(float(entry[0]), TIME_ROUND) for entry in simplified
                }
                keep_times.update(protected_times)
                keep_times.add(round(start_t, TIME_ROUND))
                keep_times.add(round(end_t, TIME_ROUND))
                decimation_indices = [
                    i
                    for i, kp in survivors
                    if round(float(kp.co[0]), TIME_ROUND) not in keep_times
                ]
                remove_indices = duplicate_indices + decimation_indices
                if not remove_indices:
                    continue

                AnimationValidator.remove_keyframe_indices(fc, remove_indices)
                fc.keyframe_points.sort()
                fc.update()

                max_error = 0.0
                for frame in eval_frames:
                    deviation = abs(
                        float(fc.evaluate(frame)) - original_eval[frame]
                    )
                    if deviation > max_error:
                        max_error = deviation

                valid, reason = AnimationValidator.check_curve_validity(fc, gap, original_gap_valid)
                if not valid:
                    AnimationValidator.restore_fcurve(fc, snapshot)
                    result.add_warning(
                        f"Sanitize reverted '{fc.data_path}'[{fc.array_index}]: {reason}"
                    )
                    continue

                if max_error > tolerance:
                    AnimationValidator.restore_fcurve(fc, cleaned_snapshot)
                    cleaned_valid, cleaned_reason = AnimationValidator.check_curve_validity(
                        fc, gap, original_gap_valid
                    )
                    if not cleaned_valid:
                        AnimationValidator.restore_fcurve(fc, snapshot)
                        result.add_warning(
                            f"Sanitize reverted '{fc.data_path}'[{fc.array_index}]: {cleaned_reason}"
                        )
                        continue
                    if duplicate_indices:
                        total_removed += len(duplicate_indices)
                        result.modified_fcurves += 1
                    result.add_warning(
                        f"Decimation rejected on '{fc.data_path}'[{fc.array_index}]: "
                        f"max deviation {max_error:.6f} > tolerance {tolerance:.6f}"
                    )
                    continue

                total_removed += len(remove_indices)
                result.modified_fcurves += 1

            result.modified_keyframes = total_removed
            result.processed_targets = 1
            if total_repaired:
                result.add_warning(
                    f"Adaptive spike repair fixed {total_repaired} keyframe(s)"
                )
            _sanitize_prune_metadata(target, fcurves)
            return result
        except Exception as e:
            KeyHeavenLogger.log_error("SanitizerEngine.sanitize_target", e, target)
            result.add_error(str(e))
            return result


class CleanupEngine:
    @staticmethod
    def cleanup_target(target, context):
        result = OperationResult("Cleanup")
        try:
            if target is None:
                result.add_warning("No target supplied")
                result.processed_targets = 1
                return result

            props = context.scene.keyheaven
            TargetResolver.ensure_single_user_action(target)
            fcurves = TargetResolver.get_target_fcurves(target, scope="TRANSFORM_ONLY")
            if not fcurves:
                result.add_warning(
                    f"No transform curves on '{getattr(target, 'name', 'target')}'"
                )
                result.processed_targets = 1
                return result

            start_f, end_f = BoundaryLockEngine.get_boundary_frames(target, context)
            boundary_enabled = BoundaryLockEngine.is_enabled(context)
            base_tolerance = max(
                0.0001, float(getattr(props, "cleanup_error_tolerance", 0.05))
            )
            base_epsilon = max(
                1e-5, float(getattr(props, "cleanup_rdp_epsilon", 1.0))
            )
            gap = MinGapEngine.gap_for(context)
            total_removed = 0

            for fc in fcurves:
                fc.keyframe_points.sort()
                points = list(fc.keyframe_points)
                if len(points) < 2:
                    continue

                snapshot = AnimationValidator.snapshot_fcurve(fc)
                original_gap_valid, _ = AnimationValidator.validate_fcurve(fc, gap)
                duplicate_indices = _sanitize_duplicate_indices(
                    fc, start_f, end_f, boundary_enabled
                )
                duplicate_set = set(duplicate_indices)
                cleaned_snapshot = [
                    entry for i, entry in enumerate(snapshot) if i not in duplicate_set
                ]
                survivors = [
                    (i, kp) for i, kp in enumerate(points) if i not in duplicate_set
                ]
                start_t = float(survivors[0][1].co[0])
                end_t = float(survivors[-1][1].co[0])

                if len(points) < 4 or len(survivors) < 4 or (end_t - start_t) <= TIME_EPS:
                    if not duplicate_indices:
                        continue
                    AnimationValidator.remove_keyframe_indices(fc, duplicate_indices)
                    fc.keyframe_points.sort()
                    fc.update()
                    valid, reason = AnimationValidator.check_curve_validity(
                        fc, gap, original_gap_valid
                    )
                    if not valid:
                        AnimationValidator.restore_fcurve(fc, snapshot)
                        result.add_warning(
                            f"Cleanup reverted '{fc.data_path}'[{fc.array_index}]: {reason}"
                        )
                    else:
                        total_removed += len(duplicate_indices)
                        result.modified_fcurves += 1
                    continue

                y_scale = get_channel_scale(fc)
                effective_tolerance = base_tolerance * y_scale
                effective_epsilon = base_epsilon * y_scale
                eval_frames = _sanitize_eval_frames(
                    start_t, end_t, len(survivors)
                )
                original_eval = {
                    frame: float(fc.evaluate(frame)) for frame in eval_frames
                }
                survivor_points = [kp for i, kp in survivors]
                protected_times = _sanitize_protected_times(
                    fc, survivor_points, start_f, end_f, boundary_enabled
                )
                coords = [
                    (float(kp.co[0]), float(kp.co[1])) for kp in survivor_points
                ]
                simplified = rdp_simplify_iterative(coords, effective_epsilon)
                keep_times = {
                    round(float(entry[0]), TIME_ROUND) for entry in simplified
                }
                keep_times.update(protected_times)
                keep_times.add(round(start_t, TIME_ROUND))
                keep_times.add(round(end_t, TIME_ROUND))
                decimation_indices = [
                    i
                    for i, kp in survivors
                    if round(float(kp.co[0]), TIME_ROUND) not in keep_times
                ]
                remove_indices = duplicate_indices + decimation_indices
                if not remove_indices:
                    continue

                AnimationValidator.remove_keyframe_indices(fc, remove_indices)
                fc.keyframe_points.sort()
                fc.update()

                max_error = 0.0
                for frame in eval_frames:
                    deviation = abs(
                        float(fc.evaluate(frame)) - original_eval[frame]
                    )
                    if deviation > max_error:
                        max_error = deviation

                valid, reason = AnimationValidator.check_curve_validity(fc, gap, original_gap_valid)
                if not valid:
                    AnimationValidator.restore_fcurve(fc, snapshot)
                    result.add_warning(
                        f"Cleanup reverted '{fc.data_path}'[{fc.array_index}]: {reason}"
                    )
                    continue

                if max_error > effective_tolerance:
                    AnimationValidator.restore_fcurve(fc, cleaned_snapshot)
                    cleaned_valid, cleaned_reason = AnimationValidator.check_curve_validity(
                        fc, gap, original_gap_valid
                    )
                    if not cleaned_valid:
                        AnimationValidator.restore_fcurve(fc, snapshot)
                        result.add_warning(
                            f"Cleanup reverted '{fc.data_path}'[{fc.array_index}]: {cleaned_reason}"
                        )
                        continue
                    if duplicate_indices:
                        total_removed += len(duplicate_indices)
                        result.modified_fcurves += 1
                    result.add_warning(
                        f"Decimation error ({max_error:.6f}) exceeded tolerance "
                        f"({effective_tolerance:.6f}) on '{fc.data_path}', "
                        f"restored pre-decimation curve"
                    )
                    continue

                total_removed += len(remove_indices)
                result.modified_fcurves += 1

            result.modified_keyframes = total_removed
            result.processed_targets = 1

            validation_issues = AnimationValidator.validate_target(target, gap)
            seen_issues = set()
            for issue in validation_issues:
                if issue not in seen_issues:
                    seen_issues.add(issue)
                    result.add_warning(issue)
            return result
        except Exception as e:
            KeyHeavenLogger.log_error("CleanupEngine.cleanup_target", e, target)
            result.add_error(str(e))
            return result
