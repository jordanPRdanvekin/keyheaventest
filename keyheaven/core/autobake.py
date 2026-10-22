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
from .sanitize import *
from .validate import *
def _autobake_key_is_protected(fc, kp, start_f, end_f, boundary_enabled, curve_start, curve_end):
    frame = float(kp.co[0])
    if abs(frame - curve_start) <= TIME_EPS or abs(frame - curve_end) <= TIME_EPS:
        return True
    if BoundaryLockEngine.is_locked_boundary(frame, start_f, end_f, boundary_enabled):
        return True
    return KeyframeProtectionEngine.is_value_locked(
        fc, kp
    ) or KeyframeProtectionEngine.is_timing_locked(fc, kp)


def _autobake_sample_frames(start_t, end_t):
    start = float(start_t)
    end = float(end_t)
    if end - start <= TIME_EPS:
        return []

    frames = [start]
    first_frame = int(math.floor(start)) + 1
    last_frame = int(math.ceil(end)) - 1
    for frame in range(first_frame, last_frame + 1):
        frame_value = float(frame)
        if frame_value > start + TIME_EPS and frame_value < end - TIME_EPS:
            frames.append(frame_value)
    frames.append(end)
    return frames


def _autobake_sample_fcurve(fc, context, frames):
    """Samples the source curve.

    The F-Curve evaluation is independent of the current scene frame, so the
    sampling never touches the depsgraph: that keeps the bake linear instead
    of paying a frame update per sampled key.
    """
    values = []
    for frame in frames:
        values.append(float(fc.evaluate(float(frame))))
    return values


def _autobake_tolerances(values, base_tolerance, adaptive):
    count = len(values)
    if count == 0:
        return []

    base = max(0.0001, float(base_tolerance))
    if not adaptive:
        return [base] * count

    global_amplitude = max(values) - min(values)
    if global_amplitude <= 1e-12:
        return [base] * count

    radius = max(1, count // 50)
    tolerances = []
    window = [0] * count
    for index, value in enumerate(values):
        low = max(0, index - radius)
        high = min(count, index + radius + 1)
        window[index] = high - low
    for index in range(count):
        low = max(0, index - radius)
        high = min(count, index + radius + 1)
        local_min = min(values[low:high])
        local_max = max(values[low:high])
        local_amplitude = local_max - local_min
        scale = max(0.25, min(4.0, local_amplitude / global_amplitude))
        tolerances.append(base * scale)
    return tolerances


def _autobake_filter_times(desired, protected_keys, blocked_times, gap):
    filtered = {}
    blocked = sorted(float(value) for value in blocked_times)
    for time_key in sorted(desired.keys()):
        time_value, value = desired[time_key]
        if time_key in protected_keys:
            filtered[time_key] = (time_value, value)
            continue

        too_close = False
        if gap > 0.0 and blocked:
            position = bisect.bisect_left(blocked, time_value)
            neighbours = []
            if position > 0:
                neighbours.append(blocked[position - 1])
            if position < len(blocked):
                neighbours.append(blocked[position])
            for neighbour in neighbours:
                if abs(time_value - neighbour) + TIME_EPS < gap:
                    too_close = True
                    break
        if too_close:
            continue

        filtered[time_key] = (time_value, value)
        if gap > 0.0:
            bisect.insort(blocked, float(time_value))
    return filtered


def _autobake_insert_keys(fc, pending):
    """Inserts a batch of keys with a single rebuild of the curve."""
    if not pending:
        return 0
    ordered = sorted(pending, key=lambda item: item[0])
    for time_value, value in ordered:
        new_key = fc.keyframe_points.insert(frame=time_value, value=value)
        new_key.interpolation = "BEZIER"
        new_key.handle_left_type = "VECTOR"
        new_key.handle_right_type = "VECTOR"
    fc.keyframe_points.sort()
    fc.update()
    return len(ordered)


def _autobake_compare(fc, frames, source_values, tolerances):
    max_deviation = 0.0
    worst_tolerance = max(tolerances) if tolerances else 0.0
    failed = False
    for index, frame in enumerate(frames):
        deviation = abs(float(fc.evaluate(frame)) - float(source_values[index]))
        tolerance = (
            float(tolerances[index]) if index < len(tolerances) else worst_tolerance
        )
        if deviation > max_deviation:
            max_deviation = deviation
            worst_tolerance = tolerance
        if deviation > tolerance:
            failed = True
    return max_deviation, worst_tolerance, failed


def _autobake_build(
    fc,
    candidate_frames,
    protected,
    protected_times,
    gap,
    keep_original,
    start_f,
    end_f,
    boundary_enabled,
    curve_start,
    curve_end,
):
    desired = {}
    for time_value, value in candidate_frames:
        desired[round(float(time_value), TIME_ROUND)] = (
            float(time_value),
            float(value),
        )
    for time_key, entry in protected.items():
        desired[time_key] = entry

    if gap > 0.0:
        if keep_original:
            blocked_times = [float(kp.co[0]) for kp in fc.keyframe_points]
        else:
            blocked_times = [entry[0] for entry in protected.values()]
        filtered = _autobake_filter_times(
            desired, set(protected.keys()), blocked_times, gap
        )
    else:
        filtered = dict(desired)

    if not filtered:
        return None

    removed = 0
    changed = 0
    inserted = 0

    if keep_original:
        existing_times = {
            round(float(kp.co[0]), TIME_ROUND) for kp in fc.keyframe_points
        }
        pending = []
        for time_key in sorted(filtered.keys()):
            if time_key in existing_times:
                continue
            time_value, value = filtered[time_key]
            if round(float(time_value), TIME_ROUND) in existing_times:
                continue
            pending.append((float(time_value), float(value)))
            existing_times.add(time_key)
        inserted += _autobake_insert_keys(fc, pending)
        return removed, changed, inserted

    remove_indices = []
    seen_times = set()
    for index, kp in enumerate(fc.keyframe_points):
        time_key = round(float(kp.co[0]), TIME_ROUND)
        if _autobake_key_is_protected(
            fc, kp, start_f, end_f, boundary_enabled, curve_start, curve_end
        ):
            continue
        if time_key in protected_times:
            remove_indices.append(index)
            continue
        if time_key not in filtered:
            remove_indices.append(index)
            continue
        if time_key in seen_times:
            remove_indices.append(index)
            continue
        seen_times.add(time_key)

    removed = len(remove_indices)
    if remove_indices:
        AnimationValidator.remove_keyframe_indices(fc, remove_indices)

    existing_times = set()
    for kp in list(fc.keyframe_points):
        time_key = round(float(kp.co[0]), TIME_ROUND)
        existing_times.add(time_key)
        if time_key not in filtered:
            continue
        if _autobake_key_is_protected(
            fc, kp, start_f, end_f, boundary_enabled, curve_start, curve_end
        ):
            continue

        target_value = float(filtered[time_key][1])
        if abs(float(kp.co[1]) - target_value) > 1e-12:
            kp.co[1] = target_value
            changed += 1
        if kp.interpolation != 'BEZIER':
            kp.interpolation = 'BEZIER'
            changed += 1
        if kp.handle_left_type != 'VECTOR':
            kp.handle_left_type = 'VECTOR'
            changed += 1
        if kp.handle_right_type != 'VECTOR':
            kp.handle_right_type = 'VECTOR'
            changed += 1

    pending = []
    for time_key in sorted(filtered.keys()):
        if time_key in existing_times:
            continue
        time_value, value = filtered[time_key]
        if round(float(time_value), TIME_ROUND) in existing_times:
            continue
        pending.append((float(time_value), float(value)))
        existing_times.add(time_key)
    inserted += _autobake_insert_keys(fc, pending)

    return removed, changed, inserted


def _autobake_fcurve(fc, context, start_f, end_f, boundary_enabled, gap, base_tolerance, adaptive, simplify, keep_original):
    if len(fc.keyframe_points) < 2:
        return True, 0, 0.0, base_tolerance, ""

    fc.keyframe_points.sort()
    points = list(fc.keyframe_points)
    curve_start = float(points[0].co[0])
    curve_end = float(points[-1].co[0])
    if curve_end - curve_start <= TIME_EPS:
        return True, 0, 0.0, base_tolerance, ""

    original_snapshot = AnimationValidator.snapshot_fcurve(fc)
    original_gap_valid, _ = AnimationValidator.validate_fcurve(fc, gap)
    frames = _autobake_sample_frames(curve_start, curve_end)
    if len(frames) < 2:
        return True, 0, 0.0, base_tolerance, ""

    source_values = _autobake_sample_fcurve(fc, context, frames)
    if len(source_values) != len(frames):
        return False, 0, 0.0, base_tolerance, "could not sample the evaluated curve"

    sample_points = [
        (frames[index], source_values[index]) for index in range(len(frames))
    ]
    if simplify:
        epsilon = max(1e-5, float(base_tolerance) * 0.5)
        candidate_frames = list(rdp_simplify_iterative(sample_points, epsilon))
    else:
        candidate_frames = list(sample_points)

    protected = {}
    for kp in points:
        if _autobake_key_is_protected(
            fc, kp, start_f, end_f, boundary_enabled, curve_start, curve_end
        ):
            protected[round(float(kp.co[0]), TIME_ROUND)] = (
                float(kp.co[0]),
                float(kp.co[1]),
            )
    protected_times = set(protected.keys())
    tolerances = _autobake_tolerances(source_values, base_tolerance, adaptive)
    candidate_keys = {round(float(t), TIME_ROUND) for t, _ in candidate_frames}

    attempts = 0
    while attempts <= 64:
        built = _autobake_build(
            fc,
            candidate_frames,
            protected,
            protected_times,
            gap,
            keep_original,
            start_f,
            end_f,
            boundary_enabled,
            curve_start,
            curve_end,
        )
        if built is None:
            AnimationValidator.restore_fcurve(fc, original_snapshot)
            return False, 0, 0.0, base_tolerance, "no candidate keys satisfied the min gap"

        removed, changed, inserted = built
        if removed == 0 and changed == 0 and inserted == 0:
            return True, 0, 0.0, base_tolerance, ""

        fc.keyframe_points.sort()
        fc.update()
        max_deviation, allowed, failed = _autobake_compare(
            fc, frames, source_values, tolerances
        )
        valid, reason = AnimationValidator.check_curve_validity(fc, gap, original_gap_valid)
        if not failed and valid:
            return True, removed + changed + inserted, max_deviation, allowed, ""
        if not valid:
            AnimationValidator.restore_fcurve(fc, original_snapshot)
            return False, 0, max_deviation, allowed, reason

        worst_index = None
        worst_deviation = 0.0
        for index, frame in enumerate(frames):
            deviation = abs(float(fc.evaluate(frame)) - float(source_values[index]))
            tolerance = (
                float(tolerances[index])
                if index < len(tolerances)
                else (max(tolerances) if tolerances else base_tolerance)
            )
            if deviation > tolerance and deviation > worst_deviation:
                worst_deviation = deviation
                worst_index = index

        if worst_index is None:
            AnimationValidator.restore_fcurve(fc, original_snapshot)
            return False, 0, max_deviation, allowed, ""

        frame_key = round(float(frames[worst_index]), TIME_ROUND)
        if frame_key in candidate_keys:
            AnimationValidator.restore_fcurve(fc, original_snapshot)
            return False, 0, max_deviation, allowed, ""

        candidate_keys.add(frame_key)
        candidate_frames.append((frames[worst_index], source_values[worst_index]))
        attempts += 1
        AnimationValidator.restore_fcurve(fc, original_snapshot)

    AnimationValidator.restore_fcurve(fc, original_snapshot)
    return False, 0, 0.0, base_tolerance, "adaptive refinement limit reached"


class AutoBakeEngine:
    @staticmethod
    def autobake_target(target, context):
        result = OperationResult("AutoBake")
        try:
            if target is None:
                result.add_warning("No target supplied")
                result.processed_targets = 1
                return result

            owner = TargetResolver.get_owner(target)
            if owner is None:
                result.add_warning("Target owner could not be resolved")
                result.processed_targets = 1
                return result

            if not TargetResolver.is_target_editable(target):
                result.add_warning(
                    f"UNSUPPORTED TARGET '{getattr(target, 'name', 'target')}': "
                    f"target is read-only or linked data"
                )
                result.processed_targets = 1
                return result

            anim_data = getattr(owner, "animation_data", None)
            action = getattr(anim_data, "action", None) if anim_data else None
            if not anim_data or not action:
                result.add_warning(
                    f"UNSUPPORTED TARGET '{getattr(target, 'name', 'target')}': "
                    f"no animation_data or action assigned"
                )
                result.processed_targets = 1
                return result

            TargetResolver.ensure_single_user_action(target)
            anim_data = getattr(owner, "animation_data", None)
            action = getattr(anim_data, "action", None) if anim_data else None
            if not anim_data or not action:
                result.add_warning(
                    f"UNSUPPORTED TARGET '{getattr(target, 'name', 'target')}': "
                    f"no animation_data or action assigned"
                )
                result.processed_targets = 1
                return result

            slot = ActionAdapter.ensure_slot(anim_data, owner, action, create=False)
            if slot is None:
                result.add_warning(
                    f"UNSUPPORTED TARGET '{getattr(target, 'name', 'target')}': "
                    f"no action slot assigned"
                )
                result.processed_targets = 1
                return result

            fcurves = TargetResolver.get_target_fcurves(
                target, scope="TRANSFORM_ONLY"
            )
            if not fcurves:
                result.add_warning(
                    f"No transform curves on '{getattr(target, 'name', 'target')}'"
                )
                result.processed_targets = 1
                return result

            props = None
            try:
                props = context.scene.keyheaven
            except Exception:
                props = None

            base_tolerance = max(
                0.0001, float(getattr(props, "autobake_tolerance", 0.05))
            )
            adaptive = bool(getattr(props, "autobake_adaptive", True))
            simplify = bool(getattr(props, "autobake_simplify", True))
            keep_original = bool(getattr(props, "autobake_keep_original", False))
            start_f, end_f = BoundaryLockEngine.get_boundary_frames(target, context)
            boundary_enabled = BoundaryLockEngine.is_enabled(context)
            gap = MinGapEngine.gap_for(context)

            accepted_curves = 0
            rejected_curves = 0
            for fc in fcurves:
                accepted, modified_count, max_deviation, allowed, reason = (
                    _autobake_fcurve(
                        fc,
                        context,
                        start_f,
                        end_f,
                        boundary_enabled,
                        gap,
                        base_tolerance,
                        adaptive,
                        simplify,
                        keep_original,
                    )
                )
                if accepted:
                    if modified_count > 0:
                        accepted_curves += 1
                        result.modified_fcurves += 1
                        result.modified_keyframes += modified_count
                    continue

                rejected_curves += 1
                path = getattr(fc, "data_path", "")
                index = int(getattr(fc, "array_index", -1))
                if reason:
                    result.add_warning(
                        f"AutoBake rejected '{path}'[{index}]: {reason}"
                    )
                else:
                    result.add_warning(
                        f"AutoBake rejected '{path}'[{index}]: max deviation "
                        f"{max_deviation:.6f} > tolerance {allowed:.6f}"
                    )

            result.processed_targets = 1
            if rejected_curves > 0 and accepted_curves == 0:
                KeyHeavenLogger.log_warning(
                    f"AutoBake produced no acceptable reconstruction on "
                    f"'{getattr(target, 'name', 'target')}'"
                )
            return result
        except Exception as e:
            KeyHeavenLogger.log_error("AutoBakeEngine.autobake_target", e, target)
            result.add_error(str(e))
            return result

    @staticmethod
    def autobake_targets(targets, context):
        result = OperationResult("AutoBake")
        if not targets:
            result.add_warning("No targets supplied")
            return result

        seen = set()
        for target in targets:
            marker = id(target)
            if marker in seen:
                continue
            seen.add(marker)
            result.merge(AutoBakeEngine.autobake_target(target, context))
        return result
