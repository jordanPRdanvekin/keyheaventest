from .._imports import *
from .logger import *
from .constants import *
from .rng import *
class AnimationValidator:
    """Enforces mathematical stability, monotonic timestamps, and gap floors."""

    @staticmethod
    def validate_fcurve(fc, min_gap=0.0):
        if not fc or not hasattr(fc, "keyframe_points"):
            return False, "Invalid FCurve object"

        pts = list(fc.keyframe_points)
        if len(pts) < 2:
            return True, "FCurve valid"

        effective_gap = max(0.0, float(min_gap))

        for i, kp in enumerate(pts):
            if not hasattr(kp, "co") or len(kp.co) < 2:
                return False, f"Invalid keyframe at index {i}"
            if (
                math.isnan(kp.co[0])
                or math.isnan(kp.co[1])
                or math.isinf(kp.co[0])
                or math.isinf(kp.co[1])
            ):
                return False, f"NaN/Inf at key index {i} in '{fc.data_path}'"

        gap_tolerance = max(1e-4, effective_gap * 1e-3)

        for i in range(len(pts) - 1):
            t_curr = pts[i].co[0]
            t_next = pts[i + 1].co[0]
            if t_next < t_curr - TIME_EPS:
                return False, (
                    f"Inversion: {t_curr:.4f} > {t_next:.4f} in "
                    f"'{fc.data_path}[{fc.array_index}]'"
                )
            if effective_gap > 0.0 and (t_next - t_curr) < (effective_gap - gap_tolerance):
                return False, (
                    f"Min gap violation ({t_next - t_curr:.4f} < {effective_gap}) "
                    f"in '{fc.data_path}[{fc.array_index}]'"
                )

        return True, "FCurve integrity verified"

    @staticmethod
    def validate_target(target, min_gap=0.0):
        issues = []
        try:
            fcurves = TargetResolver.get_target_fcurves(target)
        except Exception as e:
            return [f"unresolved fcurves: {e}"]
        for fc in fcurves:
            ok, msg = AnimationValidator.validate_fcurve(fc, min_gap)
            if not ok:
                issues.append(msg)
        return issues

    @staticmethod
    def safe_clear_fcurve(fc):
        if not fc or not hasattr(fc, "keyframe_points"):
            return
        while len(fc.keyframe_points) > 0:
            fc.keyframe_points.remove(fc.keyframe_points[-1])
        fc.update()

    @staticmethod
    def sort_keyframe_points(fc):
        try:
            fc.keyframe_points.sort()
        except Exception:
            pass
        fc.update()

    @staticmethod
    def snapshot_fcurve(fc):
        """Captures the full state of the keyframes of a curve."""
        data = []
        for kp in fc.keyframe_points:
            data.append(
                (
                    float(kp.co[0]),
                    float(kp.co[1]),
                    float(kp.handle_left[0]),
                    float(kp.handle_left[1]),
                    float(kp.handle_right[0]),
                    float(kp.handle_right[1]),
                    kp.handle_left_type,
                    kp.handle_right_type,
                    kp.interpolation,
                    getattr(kp, "easing", "AUTO"),
                )
            )
        return data

    @staticmethod
    def restore_fcurve(fc, snapshot):
        """Restores a curve from a snapshot taken with snapshot_fcurve."""
        while len(fc.keyframe_points) > 0:
            fc.keyframe_points.remove(fc.keyframe_points[-1])
        if not snapshot:
            fc.update()
            return
        ActionAdapter.write_keyframes(
            fc, [(entry[0], entry[1]) for entry in snapshot]
        )
        points = list(fc.keyframe_points)
        for index, entry in enumerate(snapshot):
            if index >= len(points):
                break
            kp = points[index]
            kp.handle_left = (entry[2], entry[3])
            kp.handle_right = (entry[4], entry[5])
            kp.handle_left_type = entry[6]
            kp.handle_right_type = entry[7]
            kp.interpolation = entry[8]
            try:
                kp.easing = entry[9]
            except Exception:
                pass
        fc.keyframe_points.sort()
        fc.update()

    @staticmethod
    def remove_keyframe_indices(fc, indices):
        """Removes the keyframes placed at the given indices.

        The curve is rebuilt in a single batch instead of removing the keys
        one by one, which turns a quadratic operation into a linear one.
        """
        if not fc or not indices:
            return
        remove = set(indices)
        if not remove:
            return
        survivors = []
        for index, kp in enumerate(fc.keyframe_points):
            if index in remove:
                continue
            survivors.append(
                {
                    "frame": float(kp.co[0]),
                    "value": float(kp.co[1]),
                    "handle_left": (float(kp.handle_left[0]), float(kp.handle_left[1])),
                    "handle_right": (float(kp.handle_right[0]), float(kp.handle_right[1])),
                    "handle_left_type": kp.handle_left_type,
                    "handle_right_type": kp.handle_right_type,
                    "interpolation": kp.interpolation,
                    "easing": getattr(kp, "easing", "AUTO"),
                }
            )
        if not survivors:
            ActionAdapter.write_keyframes(fc, [])
            return
        ActionAdapter.write_keyframes(
            fc, [(entry["frame"], entry["value"]) for entry in survivors]
        )
        points = list(fc.keyframe_points)
        for index, entry in enumerate(survivors):
            if index >= len(points):
                break
            kp = points[index]
            kp.handle_left = entry["handle_left"]
            kp.handle_right = entry["handle_right"]
            kp.handle_left_type = entry["handle_left_type"]
            kp.handle_right_type = entry["handle_right_type"]
            kp.interpolation = entry["interpolation"]
            try:
                kp.easing = entry["easing"]
            except Exception:
                pass
        fc.keyframe_points.sort()
        fc.update()

    @staticmethod
    def check_curve_validity(fc, gap, original_gap_valid):
        """Checks the structural integrity and the minimum gap of a curve."""
        structural_ok, structural_reason = AnimationValidator.validate_fcurve(fc, 0.0)
        if not structural_ok:
            return False, structural_reason
        if gap > 0.0 and original_gap_valid:
            gap_ok, gap_reason = AnimationValidator.validate_fcurve(fc, gap)
            if not gap_ok:
                return False, gap_reason
        return True, ""
