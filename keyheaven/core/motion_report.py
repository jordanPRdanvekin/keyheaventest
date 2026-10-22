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
from .autobake import *
class MotionReportEngine:
    """Turns the shared motion analysis into a readable report.

    The secondary motion, the spatial solver and the randomiser read the same
    analysis, so the report exposes exactly the values those tools use.
    """

    @staticmethod
    def summarise(target, context):
        motion = MotionAnalyzer.analyze_target_motion(target, context)
        start_f, end_f = BoundaryLockEngine.get_boundary_frames(target, context)
        keys = []
        for fcurve in TargetResolver.get_target_fcurves(target, scope="TRANSFORM_ONLY"):
            for keyframe in fcurve.keyframe_points:
                keys.append(float(keyframe.co[0]))
        speeds = list(motion.get("speeds", {}).values())
        accelerations = list(motion.get("accel_mags", {}).values())
        rest = sorted(motion.get("rest_frames", set()))
        impacts = sorted(motion.get("impact_frames", set()))
        direction = MotionReportEngine._net_direction(target, context, start_f, end_f)
        return {
            "name": getattr(target, "name", "target"),
            "keys": len(keys),
            "start": start_f,
            "end": end_f,
            "max_speed": max(speeds) if speeds else 0.0,
            "avg_speed": (sum(speeds) / len(speeds)) if speeds else 0.0,
            "max_acceleration": max(accelerations) if accelerations else 0.0,
            "rest_frames": rest,
            "impact_frames": impacts,
            "direction": direction,
            "dimension": TargetResolver.get_target_dimension(target),
        }

    @staticmethod
    def _net_direction(target, context, start_f, end_f):
        """Direction of the net travel between the first and the last frame."""
        try:
            fcurves = TargetResolver.get_target_fcurves(target, scope="TRANSFORM_ONLY")
            prefix = TargetResolver.channel_prefix(target)
            location = {}
            for fcurve in fcurves:
                if fcurve.data_path == f"{prefix}location":
                    location[fcurve.array_index] = fcurve
            if len(location) < 3:
                return None
            start = Vector([location[index].evaluate(start_f) for index in range(3)])
            end = Vector([location[index].evaluate(end_f) for index in range(3)])
            delta = end - start
            if delta.length < 1e-6:
                return None
            return delta.normalized()
        except Exception:
            return None

    @staticmethod
    def format(summaries):
        """Formats the summaries as the lines shown in the panel."""
        lines = []
        for summary in summaries:
            lines.append(
                f"{summary['name']}: {summary['keys']} keys, "
                f"{summary['start']:.0f}-{summary['end']:.0f} frames"
            )
            lines.append(
                f"  speed max {summary['max_speed']:.3f}  avg {summary['avg_speed']:.3f}"
            )
            lines.append(f"  acceleration max {summary['max_acceleration']:.3f}")
            direction = summary.get("direction")
            if direction is not None:
                lines.append(
                    "  net direction "
                    f"({direction.x:+.2f}, {direction.y:+.2f}, {direction.z:+.2f})"
                )
            rest = summary.get("rest_frames") or []
            if rest:
                shown = ", ".join(str(int(value)) for value in rest[:8])
                lines.append(f"  rest frames: {shown}")
            impacts = summary.get("impact_frames") or []
            if impacts:
                shown = ", ".join(str(int(value)) for value in impacts[:8])
                lines.append(f"  impact frames: {shown}")
            else:
                lines.append("  impact frames: none detected")
        return "\n".join(lines)
