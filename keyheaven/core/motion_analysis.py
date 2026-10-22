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
def apply_master_intensity_scale(delta_val, context):
    """Scales procedural delta values by Master Intensity (0% - 200%)."""
    try:
        if not HAS_BPY or not context or not hasattr(context.scene, "keyheaven"):
            return delta_val
        return delta_val * context.scene.keyheaven.master_intensity
    except Exception:
        return delta_val


def get_channel_scale(fc):
    """Amplitude range (y_max - y_min) for adaptive threshold scaling."""
    if not fc or not hasattr(fc, "keyframe_points") or len(fc.keyframe_points) == 0:
        return 1.0
    vals = [kp.co[1] for kp in fc.keyframe_points]
    return max(0.01, float(max(vals) - min(vals)))


class MotionAnalyzer:
    """Continuous kinematics: velocities, angular speeds, rest states, impacts."""

    _cache = {}
    _cache_version = 0
    _cache_limit = 256

    @classmethod
    def clear_cache(cls):
        cls._cache.clear()
        cls._cache_version += 1

    @classmethod
    def analyze_target_motion(cls, target, context, sample_step=1):
        empty_motion = {
            "velocities": {}, "speeds": {}, "max_speed": 0.0,
            "angular_velocities": {}, "angular_speeds": {}, "max_ang_speed": 0.0,
            "accelerations": {}, "accel_mags": {}, "max_accel": 0.0,
            "extremas": [], "rest_frames": set(), "impact_frames": set(),
            "target_dim": 1.0, "loc_fcs": {}, "rot_fcs": {}, "rot_quat_fcs": {},
            "scale_fcs": {}, "time_locked_set": set(), "value_locked_set": set(),
        }

        if not HAS_BPY or not target:
            return empty_motion

        try:
            start_f, end_f = BoundaryLockEngine.get_boundary_frames(target, context)
            obj = TargetResolver.get_owner(target)
            anim_data = getattr(obj, "animation_data", None)
            action = anim_data.action if anim_data else None
            act_name = action.name if action else "none"
            fcurves = TargetResolver.get_target_fcurves(target)
            total_kps = sum(len(fc.keyframe_points) for fc in fcurves)
            fingerprint = ActionAdapter.fingerprint(target)

            id_type = type(obj).__name__
            slot = ActionAdapter.get_assigned_slot(anim_data)
            slot_id = getattr(slot, "handle", "none") if slot else "none"
            boundary_enabled = BoundaryLockEngine.is_enabled(context)

            cache_key = (
                obj.name, id_type, getattr(target, "name", "none"),
                act_name, slot_id, total_kps, fingerprint,
                round(float(start_f), 3), round(float(end_f), 3),
                sample_step, boundary_enabled, cls._cache_version,
            )
            if cache_key in cls._cache:
                return cls._cache[cache_key]

            prefix = f'pose.bones["{target.name}"].' if TargetResolver.is_bone(target) else ""
            loc_path = f"{prefix}location"
            rot_path = f"{prefix}rotation_euler"
            rot_quat_path = f"{prefix}rotation_quaternion"
            scale_path = f"{prefix}scale"

            loc_fcs = {fc.array_index: fc for fc in fcurves if fc.data_path == loc_path}
            rot_fcs = {fc.array_index: fc for fc in fcurves if fc.data_path == rot_path}
            rot_quat_fcs = {fc.array_index: fc for fc in fcurves if fc.data_path == rot_quat_path}
            scale_fcs = {fc.array_index: fc for fc in fcurves if fc.data_path == scale_path}

            time_locked_set = set()
            value_locked_set = set()

            for fc in fcurves:
                for kp in fc.keyframe_points:
                    t_val = round(kp.co[0], TIME_ROUND)
                    if BoundaryLockEngine.is_locked_boundary(
                        kp.co[0], start_f, end_f, boundary_enabled
                    ):
                        time_locked_set.add(t_val)
                        value_locked_set.add(t_val)
                    else:
                        if KeyframeProtectionEngine.is_timing_locked(fc, kp):
                            time_locked_set.add(t_val)
                        if KeyframeProtectionEngine.is_value_locked(fc, kp):
                            value_locked_set.add(t_val)

            frames = list(range(int(start_f), int(end_f) + 1, max(1, sample_step)))
            velocities = {}
            speeds = {}
            angular_velocities = {}
            angular_speeds = {}
            accelerations = {}
            accel_mags = {}
            extremas = []
            rest_frames = set()
            impact_frames = set()

            dim = TargetResolver.get_target_dimension(target)
            max_speed = 0.0
            max_ang_speed = 0.0
            max_accel = 0.0

            if len(frames) >= 3 and (loc_fcs or rot_fcs or rot_quat_fcs):
                for i in range(1, len(frames) - 1):
                    f_prev, f_curr, f_next = frames[i - 1], frames[i], frames[i + 1]
                    dt = max(1.0, (f_next - f_prev) / 2.0)

                    if loc_fcs:
                        v1 = Vector([loc_fcs[idx].evaluate(f_prev) if idx in loc_fcs else 0.0 for idx in range(3)])
                        v2 = Vector([loc_fcs[idx].evaluate(f_curr) if idx in loc_fcs else 0.0 for idx in range(3)])
                        v3 = Vector([loc_fcs[idx].evaluate(f_next) if idx in loc_fcs else 0.0 for idx in range(3)])

                        vel = (v3 - v1) / (2.0 * dt)
                        acc = ((v3 - v2) - (v2 - v1)) / (dt * dt)

                        velocities[f_curr] = vel
                        speeds[f_curr] = vel.length
                        accelerations[f_curr] = acc
                        accel_mags[f_curr] = acc.length

                        if i >= 2:
                            previous_vel = velocities.get(f_prev, Vector())
                            if vel.dot(previous_vel) < 0.0:
                                extremas.append(f_curr)

                    if rot_fcs:
                        r1 = Vector([rot_fcs[idx].evaluate(f_prev) if idx in rot_fcs else 0.0 for idx in range(3)])
                        r3 = Vector([rot_fcs[idx].evaluate(f_next) if idx in rot_fcs else 0.0 for idx in range(3)])

                        diff_angles = Vector([
                            math.atan2(math.sin(r3[idx] - r1[idx]), math.cos(r3[idx] - r1[idx]))
                            for idx in range(3)
                        ])
                        ang_vel = diff_angles / (2.0 * dt)
                        angular_velocities[f_curr] = ang_vel
                        angular_speeds[f_curr] = ang_vel.length

                    elif rot_quat_fcs:
                        q1 = Quaternion([
                            rot_quat_fcs[idx].evaluate(f_prev) if idx in rot_quat_fcs else (1.0 if idx == 0 else 0.0)
                            for idx in range(4)
                        ])
                        q3 = Quaternion([
                            rot_quat_fcs[idx].evaluate(f_next) if idx in rot_quat_fcs else (1.0 if idx == 0 else 0.0)
                            for idx in range(4)
                        ])
                        q_diff = q3 @ q1.inverted()
                        axis, angle = q_diff.to_axis_angle()
                        if angle > math.pi:
                            angle -= 2.0 * math.pi
                        ang_vel = (axis * angle) / (2.0 * dt)
                        angular_velocities[f_curr] = ang_vel
                        angular_speeds[f_curr] = abs(angle) / (2.0 * dt)

                max_speed = max(speeds.values()) if speeds else 0.0
                max_ang_speed = max(angular_speeds.values()) if angular_speeds else 0.0
                max_accel = max(accel_mags.values()) if accel_mags else 0.0

                for frame_key, speed in speeds.items():
                    if max_speed > 1e-4 and speed < (max_speed * 0.12):
                        rest_frames.add(frame_key)
                for frame_key, accel_mag in accel_mags.items():
                    if max_accel > 1e-4 and accel_mag > (max_accel * 0.65):
                        impact_frames.add(frame_key)

            result = {
                "velocities": velocities,
                "speeds": speeds,
                "max_speed": max_speed,
                "angular_velocities": angular_velocities,
                "angular_speeds": angular_speeds,
                "max_ang_speed": max_ang_speed,
                "accelerations": accelerations,
                "accel_mags": accel_mags,
                "max_accel": max_accel,
                "extremas": extremas,
                "rest_frames": rest_frames,
                "impact_frames": impact_frames,
                "target_dim": dim,
                "loc_fcs": loc_fcs,
                "rot_fcs": rot_fcs,
                "rot_quat_fcs": rot_quat_fcs,
                "scale_fcs": scale_fcs,
                "time_locked_set": time_locked_set,
                "value_locked_set": value_locked_set,
            }

            if len(cls._cache) >= cls._cache_limit:
                cls._cache.clear()
            cls._cache[cache_key] = result
            return result
        except Exception as e:
            KeyHeavenLogger.log_error("MotionAnalyzer.analyze_target_motion", e, target)
            return empty_motion
