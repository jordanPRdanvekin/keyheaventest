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
def _secondary_clamp(value, low=0.0, high=1.0):
    if value < low:
        return low
    if value > high:
        return high
    return value


def _secondary_lerp(low, high, factor):
    low = float(low)
    high = float(high)
    if high < low:
        low, high = high, low
    factor = _secondary_clamp(factor)
    return low + (high - low) * factor


def _secondary_phase(target):
    name = getattr(target, "name", "") or ""
    checksum = zlib.adler32(name.encode("utf-8")) & 0xFFFFFFFF
    return (float(checksum) / 4294967296.0) * (2.0 * math.pi)


def _secondary_intensity(props, context):
    try:
        value = apply_master_intensity_scale(float(props.secondary_intensity), context)
        return max(0.0, float(value))
    except Exception:
        return 0.0


def _secondary_motion_ratios(motion_data):
    dim = max(0.1, float(motion_data.get("target_dim", 1.0)))
    max_speed = max(0.0, float(motion_data.get("max_speed", 0.0)))
    max_accel = max(0.0, float(motion_data.get("max_accel", 0.0)))
    max_ang = max(0.0, float(motion_data.get("max_ang_speed", 0.0)))
    speed_ratio = _secondary_clamp(max_speed / max(1e-4, (dim * 4.0) + max_speed))
    accel_ratio = _secondary_clamp(max_accel / max(1e-4, (dim * 8.0) + max_accel))
    angular_ratio = _secondary_clamp(max_ang / max(1e-4, 2.0 + max_ang))
    activity = _secondary_clamp(
        (0.45 * speed_ratio) + (0.35 * accel_ratio) + (0.20 * angular_ratio)
    )
    return dim, speed_ratio, accel_ratio, angular_ratio, activity


def _secondary_oscillator(phase, frame, index):
    t = (float(frame) * 0.9) + phase + (float(index) * 2.0943951023931953)
    return (
        math.sin(t)
        + (math.sin((t * 2.17) + 0.7) * 0.5)
        + (math.sin((t * 4.31) + 1.3) * 0.25)
    ) / 1.75


def _secondary_noise(frame, scale, phase):
    t = (float(frame) * float(scale)) + phase
    return (
        math.sin(t)
        + (math.sin((t * 2.1) + 0.5) * 0.5)
        + (math.sin((t * 4.3) + 1.1) * 0.25)
    ) / 1.75


def _secondary_action_of(fcurve):
    action = getattr(fcurve, "id_data", None)
    if action is None:
        return None
    if HAS_BPY:
        try:
            if isinstance(action, bpy.types.Action):
                return action
            nested = getattr(action, "id_data", None)
            if isinstance(nested, bpy.types.Action):
                return nested
        except Exception:
            return None
        return None
    return action


def _secondary_load_delta_store(action):
    if action is None:
        return {}
    try:
        raw = action.get("_kh_secondary_deltas")
        if not raw:
            return {}
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _secondary_save_delta_store(action, data):
    if action is None:
        return
    try:
        action["_kh_secondary_deltas"] = json.dumps(data, separators=(",", ":"))
    except Exception:
        return


def _secondary_delta_map(action, effect):
    data = _secondary_load_delta_store(action)
    records = data.get(effect, [])
    mapping = {}
    if not isinstance(records, list):
        return mapping
    for record in records:
        try:
            path = str(record["path"])
            index = int(record["index"])
            frame = round(float(record["frame"]), TIME_ROUND)
            delta = float(record["delta"])
        except Exception:
            continue
        mapping[(path, index, frame)] = delta
    return mapping


def _secondary_store_delta_map(action, effect, mapping):
    if action is None:
        return
    data = _secondary_load_delta_store(action)
    records = []
    for (path, index, frame), delta in mapping.items():
        if abs(float(delta)) <= 1e-12:
            continue
        records.append(
            {
                "path": str(path),
                "index": int(index),
                "frame": round(float(frame), TIME_ROUND),
                "delta": float(delta),
            }
        )
    if records:
        data[effect] = records
    else:
        data.pop(effect, None)
    _secondary_save_delta_store(action, data)


def _secondary_fcurve_map(fcurves):
    mapping = {}
    for fc in fcurves:
        mapping[(fc.data_path, int(fc.array_index))] = fc
    return mapping


def _secondary_find_key(fc, frame):
    target_frame = float(frame)
    for kp in fc.keyframe_points:
        if abs(float(kp.co[0]) - target_frame) <= KEY_PROXIMITY_EPS:
            return kp
    return None


def _secondary_base_value(fc, frame, default=0.0):
    if len(fc.keyframe_points) == 0:
        return float(default)
    return float(fc.evaluate(frame))


def _secondary_apply_delta(
    fc,
    frame,
    base_value,
    delta,
    delta_map,
    result,
    boundary_enabled,
    start_f,
    end_f,
    scale_floor=None,
    minimum_gap=0.0,
):
    if abs(float(delta)) <= TIME_EPS:
        return False
    kp = _secondary_find_key(fc, frame)
    if kp is not None:
        key_frame = float(kp.co[0])
        if boundary_enabled and BoundaryLockEngine.is_locked_boundary(
            key_frame, start_f, end_f, True
        ):
            result.skipped_protected += 1
            return False
        if KeyframeProtectionEngine.is_value_locked(fc, kp):
            result.skipped_protected += 1
            return False
        old_value = float(kp.co[1])
        new_value = old_value + float(delta)
        if scale_floor is not None:
            new_value = max(float(scale_floor), new_value)
        actual = new_value - old_value
        if abs(actual) <= TIME_EPS:
            return False
        kp.co[1] = new_value
    else:
        if boundary_enabled and BoundaryLockEngine.is_locked_boundary(
            frame, start_f, end_f, True
        ):
            result.skipped_protected += 1
            return False
        if minimum_gap > 0.0:
            for existing in fc.keyframe_points:
                if abs(float(existing.co[0]) - float(frame)) < (
                    float(minimum_gap) - TIME_EPS
                ):
                    return False
        new_value = float(base_value) + float(delta)
        if scale_floor is not None:
            new_value = max(float(scale_floor), new_value)
        actual = new_value - float(base_value)
        if abs(actual) <= TIME_EPS:
            return False
        fc.keyframe_points.insert(frame=frame, value=new_value)
    record_key = (fc.data_path, int(fc.array_index), round(float(frame), TIME_ROUND))
    delta_map[record_key] = float(delta_map.get(record_key, 0.0)) + actual
    result.modified_keyframes += 1
    return True


def _secondary_revert_effect(action, effect, fcurve_map, boundary_enabled, start_f, end_f):
    touched = {}
    previous = _secondary_delta_map(action, effect)
    for (path, index, frame), delta in previous.items():
        fc = fcurve_map.get((path, index))
        if fc is None:
            continue
        kp = _secondary_find_key(fc, frame)
        if kp is None:
            continue
        if boundary_enabled and BoundaryLockEngine.is_locked_boundary(
            kp.co[0], start_f, end_f, True
        ):
            continue
        if KeyframeProtectionEngine.is_value_locked(fc, kp):
            continue
        kp.co[1] = float(kp.co[1]) - float(delta)
        touched[(path, index)] = fc
    return touched


def _secondary_finalize(touched, result):
    for fc in touched.values():
        fc.keyframe_points.sort()
        fc.update()
        result.modified_fcurves += 1


def _secondary_has_mesh_geometry(target):
    try:
        if TargetResolver.is_bone(target):
            return True
        if TargetResolver.is_shape_key(target):
            key = getattr(target, "id_data", None)
            vertices = getattr(key, "vertices", None)
            if vertices is None:
                owner = getattr(key, "user", None)
                mesh = getattr(owner, "data", None)
                vertices = getattr(mesh, "vertices", None)
            return bool(vertices is not None and len(vertices) > 0)
        obj = TargetResolver.get_owner(target)
        if obj is None:
            return False
        if getattr(obj, "type", None) != "MESH":
            return False
        mesh = getattr(obj, "data", None)
        vertices = getattr(mesh, "vertices", None)
        return bool(vertices is not None and len(vertices) > 0)
    except Exception:
        return False


class SecondaryPhysicsEngine:
    """Deterministic adaptive additive secondary motion with explicit cumulative deltas."""

    @staticmethod
    def apply_organic_breathing(target, context):
        result = OperationResult("Organic Breathing")
        try:
            props = context.scene.keyheaven
            intensity = _secondary_intensity(props, context)
            if intensity <= TIME_EPS:
                result.processed_targets = 1
                return result

            TargetResolver.ensure_single_user_action(target)
            TargetResolver.ensure_transform_fcurves(target, "scale")
            MotionAnalyzer.clear_cache()
            fcurves = TargetResolver.get_target_fcurves(target, scope="TRANSFORM_ONLY")
            scale_path = TargetResolver.channel_data_path(target, "scale")
            scale_fcs = {
                fc.array_index: fc
                for fc in fcurves
                if fc.data_path == scale_path
            }
            if not scale_fcs:
                result.add_warning(f"No scale curves on '{target.name}'")
                result.processed_targets = 1
                return result

            boundary_enabled = BoundaryLockEngine.is_enabled(context)
            minimum_gap = max(0.0, float(MinGapEngine.gap_for(context)))
            start_f, end_f = BoundaryLockEngine.get_boundary_frames(target, context)
            start_i = int(start_f)
            end_i = int(end_f)
            if start_i >= end_i:
                end_i = start_i + 30

            fcurve_map = _secondary_fcurve_map(scale_fcs.values())
            action = _secondary_action_of(next(iter(scale_fcs.values())))
            touched = _secondary_revert_effect(
                action, "organic_breathing", fcurve_map, boundary_enabled, start_f, end_f
            )
            MotionAnalyzer.clear_cache()
            motion_data = MotionAnalyzer.analyze_target_motion(target, context)
            speeds = motion_data.get("speeds", {})
            max_spd = max(1e-4, float(motion_data.get("max_speed", 1.0)))
            activity = _secondary_motion_ratios(motion_data)[4]

            raw_rate = _secondary_lerp(
                props.breathing_rate_min,
                props.breathing_rate_max,
                _secondary_clamp(0.35 + (0.65 * activity)),
            )
            duration = max(1.0, float(end_i - start_i))
            cycles = max(1, int(round(duration * raw_rate / (2.0 * math.pi))))
            active_rate = (2.0 * math.pi * cycles) / duration
            phase = _secondary_phase(target)
            active_amp = _secondary_lerp(
                props.breathing_amp_min,
                props.breathing_amp_max,
                _secondary_clamp(1.0 - (0.5 * activity)),
            ) * intensity

            sample_frames = set(range(start_i, end_i + 1, 4))
            sample_frames.update(motion_data.get("rest_frames", set()))
            sample_frames.update(motion_data.get("extremas", []))
            sorted_samples = sorted(
                frame
                for frame in sample_frames
                if start_f <= float(frame) <= end_f
            )

            base_values = {}
            for axis, fc in scale_fcs.items():
                for frame in sorted_samples:
                    key = _secondary_find_key(fc, frame)
                    base_values[(axis, frame)] = (
                        float(key.co[1])
                        if key is not None
                        else _secondary_base_value(fc, frame, 1.0)
                    )

            delta_map = {}
            for frame in sorted_samples:
                if boundary_enabled and BoundaryLockEngine.is_locked_boundary(
                    frame, start_f, end_f, True
                ):
                    result.skipped_protected += 1
                    continue

                current_speed = float(speeds.get(frame, 0.0))
                speed_attenuation = max(0.2, 1.0 - (current_speed / max_spd))
                cycle_time = (((frame - start_i) * active_rate) + phase) % (2.0 * math.pi)
                if cycle_time < (0.35 * 2.0 * math.pi):
                    part = cycle_time / (0.35 * 2.0 * math.pi)
                    wave = (1.0 - math.cos(math.pi * part)) * 0.5
                else:
                    part = (cycle_time - 0.35 * 2.0 * math.pi) / (0.65 * 2.0 * math.pi)
                    wave = (1.0 + math.cos(math.pi * part)) * 0.5 * math.exp(-1.5 * part)

                z_factor = 1.0 + (wave * active_amp * speed_attenuation)
                xy_factor = 1.0 / math.sqrt(max(0.001, z_factor))

                for axis in range(3):
                    fc = scale_fcs.get(axis)
                    if fc is None:
                        continue
                    axis_factor = z_factor if axis == 2 else xy_factor
                    base = base_values[(axis, frame)]
                    delta = (axis_factor - 1.0) * base
                    if _secondary_apply_delta(
                        fc,
                        frame,
                        base,
                        delta,
                        delta_map,
                        result,
                        boundary_enabled,
                        start_f,
                        end_f,
                        minimum_gap=minimum_gap,
                    ):
                        touched[(fc.data_path, int(fc.array_index))] = fc

            _secondary_store_delta_map(action, "organic_breathing", delta_map)
            _secondary_finalize(touched, result)
            MotionAnalyzer.clear_cache()
            result.processed_targets = 1
            return result
        except Exception as e:
            KeyHeavenLogger.log_error(
                "SecondaryPhysicsEngine.apply_organic_breathing", e, target
            )
            result.add_error(f"Execution exception: {e}")
            return result

    @staticmethod
    def apply_squash_and_stretch(target, context):
        result = OperationResult("Squash & Stretch")
        try:
            props = context.scene.keyheaven
            intensity = _secondary_intensity(props, context)
            if intensity <= TIME_EPS:
                result.processed_targets = 1
                return result

            if not _secondary_has_mesh_geometry(target):
                result.add_warning(
                    "There is not enough mesh geometry for the deformation."
                )
                result.processed_targets = 1
                return result

            TargetResolver.ensure_single_user_action(target)
            TargetResolver.ensure_transform_fcurves(target, "scale")
            TargetResolver.ensure_transform_fcurves(target, "location")
            MotionAnalyzer.clear_cache()
            fcurves = TargetResolver.get_target_fcurves(target, scope="TRANSFORM_ONLY")
            scale_path = TargetResolver.channel_data_path(target, "scale")
            scale_fcs = {
                fc.array_index: fc
                for fc in fcurves
                if fc.data_path == scale_path
            }
            if not scale_fcs:
                result.add_warning(f"No scale curves found on '{target.name}'")
                result.processed_targets = 1
                return result

            boundary_enabled = BoundaryLockEngine.is_enabled(context)
            minimum_gap = max(0.0, float(MinGapEngine.gap_for(context)))
            start_f, end_f = BoundaryLockEngine.get_boundary_frames(target, context)
            if end_f <= start_f:
                result.add_warning(f"Timeline span too short on '{target.name}'")
                result.processed_targets = 1
                return result

            fcurve_map = _secondary_fcurve_map(scale_fcs.values())
            action = _secondary_action_of(next(iter(scale_fcs.values())))
            touched = _secondary_revert_effect(
                action, "squash_and_stretch", fcurve_map, boundary_enabled, start_f, end_f
            )
            MotionAnalyzer.clear_cache()
            motion_data = MotionAnalyzer.analyze_target_motion(target, context)
            velocities = motion_data.get("velocities", {})
            accelerations = motion_data.get("accelerations", {})
            accel_mags = motion_data.get("accel_mags", {})
            max_accel = max(1e-4, float(motion_data.get("max_accel", 0.0)))
            dim, speed_ratio, accel_ratio, angular_ratio, activity = _secondary_motion_ratios(
                motion_data
            )
            raw_factor = _secondary_lerp(
                props.squash_factor_min,
                props.squash_factor_max,
                _secondary_clamp(0.25 + (0.75 * activity)),
            )
            active_factor = (raw_factor * intensity) / dim

            target_samples = set(motion_data.get("impact_frames", set()))
            target_samples.update(motion_data.get("extremas", []))
            target_samples.update(range(int(start_f), int(end_f) + 1, 3))
            sorted_samples = sorted(
                frame
                for frame in target_samples
                if start_f <= float(frame) <= end_f
            )

            base_values = {}
            for axis, fc in scale_fcs.items():
                for frame in sorted_samples:
                    key = _secondary_find_key(fc, frame)
                    base_values[(axis, frame)] = (
                        float(key.co[1])
                        if key is not None
                        else _secondary_base_value(fc, frame, 1.0)
                    )

            delta_map = {}
            for frame in sorted_samples:
                if boundary_enabled and BoundaryLockEngine.is_locked_boundary(
                    frame, start_f, end_f, True
                ):
                    result.skipped_protected += 1
                    continue

                frame_key = int(round(float(frame)))
                velocity = velocities.get(frame_key)
                if velocity is None and frame != frame_key:
                    velocity = velocities.get(frame)
                if velocity is None:
                    velocity = Vector((0.0, 0.0, 0.0))

                acceleration = accelerations.get(frame_key)
                if acceleration is None and frame != frame_key:
                    acceleration = accelerations.get(frame)
                if acceleration is None:
                    acceleration = Vector((0.0, 0.0, 0.0))

                speed = velocity.length
                accel_mag = acceleration.length
                if accel_mag <= 1e-5:
                    accel_mag = float(
                        accel_mags.get(frame_key, accel_mags.get(frame, 0.0))
                    )

                local_accel_ratio = _secondary_clamp(accel_mag / max_accel)
                deceleration = 0.0
                if speed > 1e-5 and accel_mag > 1e-5:
                    deceleration = _secondary_clamp(
                        (-acceleration.dot(velocity)) / max(1e-6, speed * accel_mag)
                    )

                if speed > 1e-5:
                    direction = velocity / speed
                elif accel_mag > 1e-5:
                    direction = -acceleration / accel_mag
                else:
                    continue

                motion_stretch = speed * active_factor * (1.0 - (0.45 * deceleration))
                impact_compression = (
                    local_accel_ratio * active_factor * (1.0 + deceleration)
                )
                stretch = 1.0 + motion_stretch - impact_compression
                stretch = max(0.05, min(4.0, stretch))
                if abs(stretch - 1.0) <= TIME_EPS:
                    continue

                axis_factors = []
                for axis in range(3):
                    component = float(direction[axis])
                    factor = stretch ** ((1.5 * component * component) - 0.5)
                    axis_factors.append(max(0.0011, min(8.0, factor)))

                for axis in range(3):
                    fc = scale_fcs.get(axis)
                    if fc is None:
                        continue
                    base = base_values[(axis, frame)]
                    delta = (axis_factors[axis] - 1.0) * base
                    if _secondary_apply_delta(
                        fc,
                        frame,
                        base,
                        delta,
                        delta_map,
                        result,
                        boundary_enabled,
                        start_f,
                        end_f,
                        scale_floor=0.0011,
                        minimum_gap=minimum_gap,
                    ):
                        touched[(fc.data_path, int(fc.array_index))] = fc

            _secondary_store_delta_map(action, "squash_and_stretch", delta_map)
            _secondary_finalize(touched, result)
            MotionAnalyzer.clear_cache()
            result.processed_targets = 1
            return result
        except Exception as e:
            KeyHeavenLogger.log_error(
                "SecondaryPhysicsEngine.apply_squash_and_stretch", e, target
            )
            result.add_error(f"Execution exception: {e}")
            return result

    @staticmethod
    def apply_inertial_jiggle(target, context):
        result = OperationResult("Inertial Jiggle")
        try:
            props = context.scene.keyheaven
            intensity = _secondary_intensity(props, context)
            if intensity <= TIME_EPS:
                result.processed_targets = 1
                return result

            TargetResolver.ensure_single_user_action(target)
            TargetResolver.ensure_transform_fcurves(target, "scale")
            MotionAnalyzer.clear_cache()
            fcurves = TargetResolver.get_target_fcurves(target, scope="TRANSFORM_ONLY")
            scale_path = TargetResolver.channel_data_path(target, "scale")
            scale_fcs = {
                fc.array_index: fc
                for fc in fcurves
                if fc.data_path == scale_path
            }
            if not scale_fcs:
                result.add_warning(f"No scale curves found on '{target.name}'")
                result.processed_targets = 1
                return result

            boundary_enabled = BoundaryLockEngine.is_enabled(context)
            minimum_gap = max(0.0, float(MinGapEngine.gap_for(context)))
            start_f, end_f = BoundaryLockEngine.get_boundary_frames(target, context)
            if end_f <= start_f:
                result.add_warning(f"Timeline span too short on '{target.name}'")
                result.processed_targets = 1
                return result

            fcurve_map = _secondary_fcurve_map(scale_fcs.values())
            action = _secondary_action_of(next(iter(scale_fcs.values())))
            touched = _secondary_revert_effect(
                action, "inertial_jiggle", fcurve_map, boundary_enabled, start_f, end_f
            )
            MotionAnalyzer.clear_cache()
            motion_data = MotionAnalyzer.analyze_target_motion(target, context)
            accel_mags = motion_data.get("accel_mags", {})
            impact_frames = motion_data.get("impact_frames", set())
            dim, speed_ratio, accel_ratio, angular_ratio, activity = _secondary_motion_ratios(
                motion_data
            )
            max_accel = max(1e-4, float(motion_data.get("max_accel", 0.0)))
            max_speed = max(1e-4, float(motion_data.get("max_speed", 0.0)))
            event_ratio = _secondary_clamp(max_accel / (max_accel + (dim * 4.0)))
            tempo_ratio = _secondary_clamp(max_speed / (max_speed + (dim * 4.0)))
            stiffness = _secondary_lerp(
                props.jiggle_stiffness_min,
                props.jiggle_stiffness_max,
                event_ratio,
            )
            damping = _secondary_lerp(
                props.jiggle_damping_min,
                props.jiggle_damping_max,
                _secondary_clamp(1.0 - (0.5 * (event_ratio + tempo_ratio))),
            )
            phase = _secondary_phase(target)

            active_impulses = (
                sorted(impact_frames)
                if impact_frames
                else [f for f, a in accel_mags.items() if a > 0.05]
            )

            decay_frames = set()
            for impulse in active_impulses:
                base_frame = int(round(float(impulse)))
                for step in range(1, 6):
                    decay_f = base_frame + step
                    if decay_f >= end_f:
                        break
                    decay_frames.add(decay_f)
            sorted_decay_frames = sorted(decay_frames)

            base_values = {}
            for axis, fc in scale_fcs.items():
                for frame in sorted_decay_frames:
                    key = _secondary_find_key(fc, frame)
                    base_values[(axis, frame)] = (
                        float(key.co[1])
                        if key is not None
                        else _secondary_base_value(fc, frame, 1.0)
                    )

            delta_map = {}
            for impulse in active_impulses:
                base_frame = int(round(float(impulse)))
                accel = float(accel_mags.get(impulse, accel_mags.get(base_frame, 0.0)))
                if accel <= 0.05:
                    continue
                energy_scale = math.tanh(accel * 0.5)
                for step in range(1, 6):
                    decay_f = base_frame + step
                    if decay_f >= end_f:
                        break
                    if boundary_enabled and BoundaryLockEngine.is_locked_boundary(
                        decay_f, start_f, end_f, True
                    ):
                        result.skipped_protected += 1
                        continue

                    t_decay = step * 0.2
                    jiggle_raw = (
                        0.08
                        * energy_scale
                        * math.exp(-damping * stiffness * t_decay)
                        * math.cos((4.0 * t_decay) + phase)
                    )
                    jiggle_delta = jiggle_raw * intensity
                    if abs(jiggle_delta) <= TIME_EPS:
                        continue

                    for axis in range(3):
                        fc = scale_fcs.get(axis)
                        if fc is None:
                            continue
                        base = base_values[(axis, decay_f)]
                        delta = base * jiggle_delta
                        if _secondary_apply_delta(
                            fc,
                            decay_f,
                            base,
                            delta,
                            delta_map,
                            result,
                            boundary_enabled,
                            start_f,
                            end_f,
                            minimum_gap=minimum_gap,
                        ):
                            touched[(fc.data_path, int(fc.array_index))] = fc

            _secondary_store_delta_map(action, "inertial_jiggle", delta_map)
            _secondary_finalize(touched, result)
            MotionAnalyzer.clear_cache()
            result.processed_targets = 1
            return result
        except Exception as e:
            KeyHeavenLogger.log_error(
                "SecondaryPhysicsEngine.apply_inertial_jiggle", e, target
            )
            result.add_error(f"Execution exception: {e}")
            return result

    @staticmethod
    def apply_dynamic_drag(target, context):
        result = OperationResult("Dynamic Drag")
        try:
            props = context.scene.keyheaven
            intensity = _secondary_intensity(props, context)
            if intensity <= TIME_EPS:
                result.processed_targets = 1
                return result

            TargetResolver.ensure_single_user_action(target)
            TargetResolver.ensure_transform_fcurves(target, "rotation_euler")
            MotionAnalyzer.clear_cache()
            fcurves = TargetResolver.get_target_fcurves(target, scope="TRANSFORM_ONLY")
            rot_path = TargetResolver.channel_data_path(target, "rotation_euler")
            rot_fcs = {
                fc.array_index: fc
                for fc in fcurves
                if fc.data_path == rot_path
            }
            if not rot_fcs:
                result.add_warning(f"No rotation curves found on '{target.name}'")
                result.processed_targets = 1
                return result

            boundary_enabled = BoundaryLockEngine.is_enabled(context)
            minimum_gap = max(0.0, float(MinGapEngine.gap_for(context)))
            start_f, end_f = BoundaryLockEngine.get_boundary_frames(target, context)
            if end_f <= start_f:
                result.add_warning(f"Timeline span too short on '{target.name}'")
                result.processed_targets = 1
                return result

            fcurve_map = _secondary_fcurve_map(rot_fcs.values())
            action = _secondary_action_of(next(iter(rot_fcs.values())))
            touched = _secondary_revert_effect(
                action, "dynamic_drag", fcurve_map, boundary_enabled, start_f, end_f
            )
            MotionAnalyzer.clear_cache()
            motion_data = MotionAnalyzer.analyze_target_motion(target, context)
            ang_vels = motion_data.get("angular_velocities", {})
            speeds = motion_data.get("speeds", {})
            dim, speed_ratio, accel_ratio, angular_ratio, activity = _secondary_motion_ratios(
                motion_data
            )
            drag_ratio = _secondary_clamp(
                (0.45 * angular_ratio) + (0.35 * speed_ratio) + (0.20 * activity)
            )
            active_drag = _secondary_lerp(
                props.drag_factor_min,
                props.drag_factor_max,
                drag_ratio,
            ) * intensity

            sample_frames = set(range(int(start_f), int(end_f) + 1, 2))
            sample_frames.update(motion_data.get("extremas", []))
            sorted_samples = sorted(
                frame
                for frame in sample_frames
                if start_f <= float(frame) <= end_f
            )

            base_values = {}
            for axis, fc in rot_fcs.items():
                for frame in sorted_samples:
                    key = _secondary_find_key(fc, frame)
                    base_values[(axis, frame)] = (
                        float(key.co[1])
                        if key is not None
                        else _secondary_base_value(fc, frame, 0.0)
                    )

            delta_map = {}
            zero_vector = Vector((0.0, 0.0, 0.0))
            for frame in sorted_samples:
                if boundary_enabled and BoundaryLockEngine.is_locked_boundary(
                    frame, start_f, end_f, True
                ):
                    result.skipped_protected += 1
                    continue

                frame_key = int(round(float(frame)))
                angular_velocity = ang_vels.get(frame_key)
                if angular_velocity is None and frame != frame_key:
                    angular_velocity = ang_vels.get(frame)
                if angular_velocity is None:
                    angular_velocity = zero_vector
                speed = float(speeds.get(frame_key, speeds.get(frame, 0.0)))
                drag_vector = -active_drag * (
                    angular_velocity
                    + Vector((speed * 0.05, speed * 0.05, speed * 0.05))
                )
                if drag_vector.length < 1e-5:
                    continue

                for axis in range(3):
                    fc = rot_fcs.get(axis)
                    if fc is None:
                        continue
                    base = base_values[(axis, frame)]
                    delta = float(drag_vector[axis])
                    if _secondary_apply_delta(
                        fc,
                        frame,
                        base,
                        delta,
                        delta_map,
                        result,
                        boundary_enabled,
                        start_f,
                        end_f,
                        minimum_gap=minimum_gap,
                    ):
                        touched[(fc.data_path, int(fc.array_index))] = fc

            _secondary_store_delta_map(action, "dynamic_drag", delta_map)
            _secondary_finalize(touched, result)
            MotionAnalyzer.clear_cache()
            result.processed_targets = 1
            return result
        except Exception as e:
            KeyHeavenLogger.log_error(
                "SecondaryPhysicsEngine.apply_dynamic_drag", e, target
            )
            result.add_error(f"Execution exception: {e}")
            return result

    @staticmethod
    def apply_micro_tremor(target, context):
        result = OperationResult("Micro-Tremor")
        try:
            props = context.scene.keyheaven
            intensity = _secondary_intensity(props, context)
            if intensity <= TIME_EPS:
                result.processed_targets = 1
                return result

            TargetResolver.ensure_single_user_action(target)
            MotionAnalyzer.clear_cache()
            fcurves = TargetResolver.get_target_fcurves(target, scope="TRANSFORM_ONLY")
            if not fcurves:
                result.add_warning(f"No transform curves found on '{target.name}'")
                result.processed_targets = 1
                return result

            boundary_enabled = BoundaryLockEngine.is_enabled(context)
            start_f, end_f = BoundaryLockEngine.get_boundary_frames(target, context)
            fcurve_map = _secondary_fcurve_map(fcurves)
            action = _secondary_action_of(fcurves[0])
            touched = _secondary_revert_effect(
                action, "micro_tremor", fcurve_map, boundary_enabled, start_f, end_f
            )
            MotionAnalyzer.clear_cache()
            motion_data = MotionAnalyzer.analyze_target_motion(target, context)
            speeds = motion_data.get("speeds", {})
            max_spd = max(1e-4, float(motion_data.get("max_speed", 1.0)))
            rest_frames = motion_data.get("rest_frames", set())
            activity = _secondary_motion_ratios(motion_data)[4]
            active_amp = _secondary_lerp(
                props.tremor_amp_min,
                props.tremor_amp_max,
                _secondary_clamp(1.0 - (0.5 * activity)),
            ) * intensity
            phase = _secondary_phase(target)

            delta_map = {}
            for fc in fcurves:
                axis_index = int(fc.array_index)
                for kp in list(fc.keyframe_points):
                    key_frame = round(float(kp.co[0]), TIME_ROUND)
                    if boundary_enabled and BoundaryLockEngine.is_locked_boundary(
                        key_frame, start_f, end_f, True
                    ):
                        result.skipped_protected += 1
                        continue
                    if KeyframeProtectionEngine.is_value_locked(fc, kp):
                        result.skipped_protected += 1
                        continue

                    frame_key = int(round(key_frame))
                    current_speed = float(speeds.get(frame_key, 0.0))
                    rest_mod = (
                        1.0
                        if frame_key in rest_frames
                        else max(0.05, 1.0 - (current_speed / max_spd))
                    )
                    wave = _secondary_oscillator(phase, key_frame, axis_index)
                    delta = wave * active_amp * rest_mod
                    if _secondary_apply_delta(
                        fc,
                        key_frame,
                        float(kp.co[1]),
                        delta,
                        delta_map,
                        result,
                        boundary_enabled,
                        start_f,
                        end_f,
                    ):
                        touched[(fc.data_path, axis_index)] = fc

            _secondary_store_delta_map(action, "micro_tremor", delta_map)
            _secondary_finalize(touched, result)
            MotionAnalyzer.clear_cache()
            result.processed_targets = 1
            return result
        except Exception as e:
            KeyHeavenLogger.log_error(
                "SecondaryPhysicsEngine.apply_micro_tremor", e, target
            )
            result.add_error(f"Execution exception: {e}")
            return result

    @staticmethod
    def apply_noise_modifier(target, context):
        result = OperationResult("Noise Modifier")
        try:
            props = context.scene.keyheaven
            intensity = _secondary_intensity(props, context)
            if intensity <= TIME_EPS:
                result.processed_targets = 1
                return result

            TargetResolver.ensure_single_user_action(target)
            MotionAnalyzer.clear_cache()
            fcurves = TargetResolver.get_target_fcurves(target, scope="TRANSFORM_ONLY")
            if not fcurves:
                result.add_warning(f"No transform curves found on '{target.name}'")
                result.processed_targets = 1
                return result

            boundary_enabled = BoundaryLockEngine.is_enabled(context)
            start_f, end_f = BoundaryLockEngine.get_boundary_frames(target, context)
            fcurve_map = _secondary_fcurve_map(fcurves)
            action = _secondary_action_of(fcurves[0])
            touched = _secondary_revert_effect(
                action, "noise_modifier", fcurve_map, boundary_enabled, start_f, end_f
            )
            MotionAnalyzer.clear_cache()
            motion_data = MotionAnalyzer.analyze_target_motion(target, context)
            activity = _secondary_motion_ratios(motion_data)[4]
            noise_scale = _secondary_lerp(
                props.noise_scale_min,
                props.noise_scale_max,
                _secondary_clamp(0.25 + (0.75 * activity)),
            )
            noise_strength = _secondary_lerp(
                props.noise_strength_min,
                props.noise_strength_max,
                _secondary_clamp(1.0 - (0.5 * activity)),
            ) * intensity
            duration = max(1.0, float(end_f - start_f))
            phase = _secondary_phase(target)

            delta_map = {}
            for fc in fcurves:
                axis_index = int(fc.array_index)
                for kp in list(fc.keyframe_points):
                    key_frame = round(float(kp.co[0]), TIME_ROUND)
                    if boundary_enabled and BoundaryLockEngine.is_locked_boundary(
                        key_frame, start_f, end_f, True
                    ):
                        result.skipped_protected += 1
                        continue
                    if KeyframeProtectionEngine.is_value_locked(fc, kp):
                        result.skipped_protected += 1
                        continue

                    alpha = _secondary_clamp((key_frame - start_f) / duration)
                    first_noise = _secondary_noise(key_frame, noise_scale, phase)
                    second_noise = _secondary_noise(
                        key_frame - duration, noise_scale, phase
                    )
                    noise_val = (
                        ((1.0 - alpha) * first_noise) + (alpha * second_noise)
                    ) * noise_strength
                    if _secondary_apply_delta(
                        fc,
                        key_frame,
                        float(kp.co[1]),
                        noise_val,
                        delta_map,
                        result,
                        boundary_enabled,
                        start_f,
                        end_f,
                    ):
                        touched[(fc.data_path, axis_index)] = fc

            _secondary_store_delta_map(action, "noise_modifier", delta_map)
            _secondary_finalize(touched, result)
            MotionAnalyzer.clear_cache()
            result.processed_targets = 1
            return result
        except Exception as e:
            KeyHeavenLogger.log_error(
                "SecondaryPhysicsEngine.apply_noise_modifier", e, target
            )
            result.add_error(f"Execution exception: {e}")
            return result

    @staticmethod
    def apply_wave_modifier(target, context):
        result = OperationResult("Wave Modifier")
        try:
            props = context.scene.keyheaven
            intensity = _secondary_intensity(props, context)
            if intensity <= TIME_EPS:
                result.processed_targets = 1
                return result

            TargetResolver.ensure_single_user_action(target)
            MotionAnalyzer.clear_cache()
            fcurves = TargetResolver.get_target_fcurves(target, scope="TRANSFORM_ONLY")
            if not fcurves:
                result.add_warning(f"No transform curves found on '{target.name}'")
                result.processed_targets = 1
                return result

            boundary_enabled = BoundaryLockEngine.is_enabled(context)
            start_f, end_f = BoundaryLockEngine.get_boundary_frames(target, context)
            fcurve_map = _secondary_fcurve_map(fcurves)
            action = _secondary_action_of(fcurves[0])
            touched = _secondary_revert_effect(
                action, "wave_modifier", fcurve_map, boundary_enabled, start_f, end_f
            )
            MotionAnalyzer.clear_cache()
            motion_data = MotionAnalyzer.analyze_target_motion(target, context)
            activity = _secondary_motion_ratios(motion_data)[4]
            duration = max(1.0, float(end_f - start_f))
            raw_frequency = _secondary_lerp(
                props.wave_frequency_min,
                props.wave_frequency_max,
                _secondary_clamp(0.25 + (0.75 * activity)),
            )
            cycles = max(1, int(round(duration * raw_frequency / (2.0 * math.pi))))
            wave_frequency = (2.0 * math.pi * cycles) / duration
            wave_phase = _secondary_phase(target)
            wave_amplitude = _secondary_lerp(
                props.wave_amplitude_min,
                props.wave_amplitude_max,
                _secondary_clamp(1.0 - (0.5 * activity)),
            ) * intensity

            delta_map = {}
            for fc in fcurves:
                axis_index = int(fc.array_index)
                for kp in list(fc.keyframe_points):
                    key_frame = round(float(kp.co[0]), TIME_ROUND)
                    if boundary_enabled and BoundaryLockEngine.is_locked_boundary(
                        key_frame, start_f, end_f, True
                    ):
                        result.skipped_protected += 1
                        continue
                    if KeyframeProtectionEngine.is_value_locked(fc, kp):
                        result.skipped_protected += 1
                        continue

                    relative_time = key_frame - start_f
                    wave_val = (
                        math.sin((relative_time * wave_frequency) + wave_phase)
                        * wave_amplitude
                    )
                    if _secondary_apply_delta(
                        fc,
                        key_frame,
                        float(kp.co[1]),
                        wave_val,
                        delta_map,
                        result,
                        boundary_enabled,
                        start_f,
                        end_f,
                    ):
                        touched[(fc.data_path, axis_index)] = fc

            _secondary_store_delta_map(action, "wave_modifier", delta_map)
            _secondary_finalize(touched, result)
            MotionAnalyzer.clear_cache()
            result.processed_targets = 1
            return result
        except Exception as e:
            KeyHeavenLogger.log_error(
                "SecondaryPhysicsEngine.apply_wave_modifier", e, target
            )
            result.add_error(f"Execution exception: {e}")
            return result
