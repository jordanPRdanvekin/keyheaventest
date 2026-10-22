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
class MinGapEngine:
    @staticmethod
    def gap_for(context):
        try:
            props = context.scene.keyheaven
            mode = getattr(props, "min_gap_mode", "SAFE")
            if mode == "SAFE":
                return max(0.0, float(getattr(props, "min_gap", 0.0)))
            return 0.0
        except Exception:
            return 0.0

    @staticmethod
    def magnitude_for(context):
        """Raw minimum gap magnitude configured by the user."""
        try:
            props = context.scene.keyheaven
            return max(0.0, float(getattr(props, "min_gap", 0.0)))
        except Exception:
            return 0.0

    @staticmethod
    def enforce_fcurve(fc, gap, start_f=None, end_f=None, boundary_enabled=True):
        moved = []
        if not fc or not hasattr(fc, "keyframe_points"):
            return moved
        try:
            points = sorted(list(fc.keyframe_points), key=lambda kp: kp.co[0])
            if len(points) < 2:
                return moved

            gap = max(0.0, float(gap if gap is not None else 0.0))
            times = [float(kp.co[0]) for kp in points]
            start = float(start_f) if start_f is not None else min(times)
            end = float(end_f) if end_f is not None else max(times)
            if end < start:
                start, end = end, start

            fixed = []
            for kp in points:
                locked = KeyframeProtectionEngine.is_timing_locked(fc, kp)
                if boundary_enabled and (
                    abs(kp.co[0] - start) <= TIME_EPS
                    or abs(kp.co[0] - end) <= TIME_EPS
                ):
                    locked = True
                fixed.append(locked)

            next_fixed = [None] * len(points)
            upcoming = None
            for i in range(len(points) - 1, -1, -1):
                next_fixed[i] = upcoming
                if fixed[i]:
                    upcoming = float(points[i].co[0])

            prev_time = None
            for i, kp in enumerate(points):
                old_time = float(kp.co[0])
                if fixed[i]:
                    prev_time = old_time
                    continue

                target = old_time
                if gap > 0.0 and prev_time is not None:
                    target = max(target, prev_time + gap)
                elif prev_time is not None and target < prev_time:
                    target = prev_time

                if next_fixed[i] is not None:
                    limit = next_fixed[i] - gap if gap > 0.0 else next_fixed[i]
                    if target > limit:
                        target = limit if limit >= old_time else old_time

                if target > end:
                    target = end if end >= old_time else old_time

                if abs(target - old_time) > TIME_EPS:
                    delta = target - old_time
                    kp.co[0] = target
                    kp.handle_left[0] += delta
                    kp.handle_right[0] += delta
                    moved.append((old_time, target))
                prev_time = float(kp.co[0])

            fc.keyframe_points.sort()
            fc.update()
        except Exception as e:
            KeyHeavenLogger.log_error("MinGapEngine.enforce_fcurve", e)
        return moved

    @staticmethod
    def guard_result_against_gap(target, context):
        warnings = []
        if not target:
            return warnings
        gap = MinGapEngine.gap_for(context)
        try:
            fcurves = TargetResolver.get_target_fcurves(target)
        except Exception as e:
            warnings.append(f"Unable to resolve F-Curves: {e}")
            return warnings
        for fc in fcurves:
            valid, reason = AnimationValidator.validate_fcurve(fc, min_gap=gap)
            if not valid:
                warnings.append(reason)
        return warnings
