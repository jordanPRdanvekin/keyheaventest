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
class CurvesEngine:
    """Curves & Timing Engine: native easing, Bezier shaping, and elastic time scale."""

    @staticmethod
    def apply_custom_easing(target, context):
        result = OperationResult("Custom Easing")
        try:
            TargetResolver.ensure_single_user_action(target)
            MotionAnalyzer.clear_cache()
            props = context.scene.keyheaven
            fcurves = TargetResolver.get_target_fcurves(target, scope='TRANSFORM_ONLY')
            if not fcurves:
                result.add_warning(f"No transform curves found on '{target.name}'")
                result.processed_targets = 1
                return result

            mult = max(0.01, float(props.ease_multiplier))
            ease_type = props.custom_easing_type
            ease_dir = props.custom_easing_ease

            valid_types = {
                'BEZIER', 'SINE', 'QUAD', 'CUBIC', 'QUART',
                'QUINT', 'EXPO', 'CIRC', 'BACK', 'BOUNCE', 'ELASTIC'
            }
            if ease_type not in valid_types:
                ease_type = 'BEZIER'

            boundary_enabled = BoundaryLockEngine.is_enabled(context)
            start_f, end_f = BoundaryLockEngine.get_boundary_frames(target, context)

            for fc in fcurves:
                pts = sorted(list(fc.keyframe_points), key=lambda k: float(k.co[0]))
                if len(pts) < 2:
                    continue

                changed = False
                for i, kp in enumerate(pts):
                    if BoundaryLockEngine.is_locked_boundary(
                        kp.co[0], start_f, end_f, boundary_enabled
                    ):
                        result.skipped_protected += 1
                        continue
                    if (
                        KeyframeProtectionEngine.is_value_locked(fc, kp)
                        or KeyframeProtectionEngine.is_timing_locked(fc, kp)
                    ):
                        result.skipped_protected += 1
                        continue

                    try:
                        kp.interpolation = ease_type
                        if hasattr(kp, "easing") and ease_type != 'BEZIER':
                            kp.easing = ease_dir

                        if ease_type == 'BEZIER':
                            kp.handle_left_type = 'AUTO_CLAMPED'
                            kp.handle_right_type = 'AUTO_CLAMPED'

                            left_dist = float(kp.co[0]) - float(kp.handle_left[0])
                            right_dist = float(kp.handle_right[0]) - float(kp.co[0])

                            new_left = left_dist * mult
                            new_right = right_dist * mult

                            if i > 0:
                                max_left = float(kp.co[0]) - float(pts[i - 1].co[0]) - TIME_EPS
                                new_left = min(new_left, max_left)

                            if i < len(pts) - 1:
                                max_right = float(pts[i + 1].co[0]) - float(kp.co[0]) - TIME_EPS
                                new_right = min(new_right, max_right)

                            kp.handle_left[0] = float(kp.co[0]) - max(TIME_EPS, new_left)
                            kp.handle_right[0] = float(kp.co[0]) + max(TIME_EPS, new_right)

                        result.modified_keyframes += 1
                        changed = True
                    except Exception as e:
                        result.add_warning(f"Native easing note: {e}")

                if not changed:
                    continue
                fc.keyframe_points.sort()
                fc.update()
                result.modified_fcurves += 1

            MotionAnalyzer.clear_cache()
            result.processed_targets = 1
            return result
        except Exception as e:
            KeyHeavenLogger.log_error("CurvesEngine.apply_custom_easing", e, target)
            result.add_error(f"Execution exception: {e}")
            return result

    @staticmethod
    def apply_time_scale(target, context, scale_factor=None):
        result = OperationResult("Elastic Time Scale")
        try:
            TargetResolver.ensure_single_user_action(target)
            MotionAnalyzer.clear_cache()
            props = context.scene.keyheaven
            fcurves = TargetResolver.get_target_fcurves(target, scope='TRANSFORM_ONLY')
            if not fcurves:
                result.add_warning(f"No transform curves found on '{target.name}'")
                result.processed_targets = 1
                return result

            if scale_factor is None:
                low_scale = min(float(props.time_scale_min), float(props.time_scale_max))
                high_scale = max(float(props.time_scale_min), float(props.time_scale_max))
                rng = KeyHeavenRNG.create(context)
                active_scale = rng.uniform(low_scale, high_scale)
            else:
                active_scale = float(scale_factor)

            if active_scale <= TIME_EPS:
                result.add_warning("Time scale factor must be positive.")
                result.processed_targets = 1
                return result

            if abs(active_scale - 1.0) < TIME_EPS:
                result.processed_targets = 1
                return result

            boundary_enabled = BoundaryLockEngine.is_enabled(context)
            wall_min, wall_max = BoundaryLockEngine.get_boundary_frames(target, context)
            if (wall_max - wall_min) < TIME_EPS:
                result.add_warning("Animation span too short to apply time scale.")
                result.processed_targets = 1
                return result

            gap = max(0.0, float(MinGapEngine.gap_for(context)))
            max_remapped_frame = float(context.scene.frame_end)
            min_remapped_frame = float(context.scene.frame_start)

            for fc in fcurves:
                pts = list(fc.keyframe_points)
                if len(pts) < 2:
                    continue

                moved = False
                for kp in pts:
                    old_f = float(kp.co[0])
                    if boundary_enabled and abs(old_f - wall_min) <= TIME_EPS:
                        continue
                    if boundary_enabled and abs(old_f - wall_max) <= TIME_EPS:
                        continue
                    if KeyframeProtectionEngine.is_timing_locked(fc, kp):
                        result.skipped_protected += 1
                        continue

                    rel_t = old_f - wall_min
                    new_f = wall_min + (rel_t * active_scale)
                    if boundary_enabled:
                        new_f = min(max(new_f, wall_min + TIME_EPS), wall_max - TIME_EPS)
                    if abs(new_f - old_f) <= TIME_EPS:
                        continue

                    left_delta = float(kp.handle_left[0]) - old_f
                    right_delta = float(kp.handle_right[0]) - old_f

                    kp.co[0] = new_f
                    kp.handle_left[0] = new_f + (left_delta * active_scale)
                    kp.handle_right[0] = new_f + (right_delta * active_scale)

                    KeyframeProtectionEngine.mark_key_moved(fc, old_f, new_f)
                    result.modified_keyframes += 1
                    moved = True

                    if new_f > max_remapped_frame:
                        max_remapped_frame = new_f
                    if new_f < min_remapped_frame:
                        min_remapped_frame = new_f

                if not moved:
                    continue

                fc.keyframe_points.sort()
                if gap > 0.0:
                    MinGapEngine.enforce_fcurve(
                        fc,
                        gap,
                        start_f=wall_min,
                        end_f=(wall_max if boundary_enabled else None),
                        boundary_enabled=boundary_enabled,
                    )
                fc.update()
                result.modified_fcurves += 1

            if max_remapped_frame > context.scene.frame_end:
                context.scene.frame_end = int(math.ceil(max_remapped_frame)) + 5
            if min_remapped_frame < context.scene.frame_start:
                context.scene.frame_start = int(math.floor(min_remapped_frame)) - 2

            MotionAnalyzer.clear_cache()
            result.processed_targets = 1
            return result
        except Exception as e:
            KeyHeavenLogger.log_error("CurvesEngine.apply_time_scale", e, target)
            result.add_error(f"Execution exception: {e}")
            return result
