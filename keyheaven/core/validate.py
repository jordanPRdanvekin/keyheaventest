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
def report_operation_result(op, res):
    if res.success:
        if res.warnings:
            op.report({'WARNING'}, f"{res.get_summary()}")
        else:
            op.report({'INFO'}, res.get_summary())
    else:
        msg = "; ".join(res.errors[:2]) if res.errors else "Operation failed"
        op.report({'ERROR'}, msg)


def _validation_gap_and_mode(context):
    mode = "SAFE"
    gap = 0.0
    try:
        props = context.scene.keyheaven
        mode = str(getattr(props, "min_gap_mode", "SAFE"))
        if mode == "OFF":
            gap = 0.0
        elif mode == "RELAXED":
            gap = 0.0
        else:
            gap = max(0.0, float(MinGapEngine.gap_for(context)))
    except Exception:
        gap = 0.0
    return gap, mode


def _validation_issue_set(target, context, gap):
    try:
        return set(ValidationEngine.validate_after_write(target, context, gap))
    except Exception as e:
        KeyHeavenLogger.log_error("_validation_issue_set", e, target)
        return {f"validation exception: {type(e).__name__}: {e}"}


def _validation_is_gap_issue(issue):
    return "min gap violation" in str(issue).lower()


def _validation_issue_key(issue):
    """Normalises an issue so the same category compares equal."""
    import re

    text = str(issue)
    return re.sub(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", "#", text)


def _validation_new_issues(post_issues, baseline_issues):
    """Returns the issues that the operation introduced.

    A pre-existing problem of the same category is not a regression, so the
    comparison uses the category and the number of occurrences instead of the
    exact message.
    """
    baseline_counts = {}
    for issue in baseline_issues:
        key = _validation_issue_key(issue)
        baseline_counts[key] = baseline_counts.get(key, 0) + 1
    post_counts = {}
    for issue in post_issues:
        key = _validation_issue_key(issue)
        post_counts[key] = post_counts.get(key, 0) + 1
    introduced = []
    for issue in post_issues:
        key = _validation_issue_key(issue)
        if post_counts[key] > baseline_counts.get(key, 0):
            introduced.append(issue)
            post_counts[key] -= 1
            baseline_counts[key] = baseline_counts.get(key, 0) + 1
    return introduced


class ValidationEngine:
    @staticmethod
    def validate_after_write(target, context, min_gap):
        issues = []
        if target is None:
            return ["target is None"]

        owner = TargetResolver.get_owner(target)
        if owner is None:
            return ["target owner could not be resolved"]

        try:
            fcurves = TargetResolver.get_target_fcurves(target)
        except Exception as e:
            return [f"F-Curve resolution failed: {e}"]

        if not fcurves:
            return issues

        try:
            effective_gap = max(0.0, float(min_gap))
        except Exception:
            effective_gap = 0.0

        try:
            issues.extend(AnimationValidator.validate_target(target, effective_gap))
        except Exception as e:
            issues.append(f"AnimationValidator failure: {e}")

        seen_markers = set()
        for fc in fcurves:
            path = getattr(fc, "data_path", "")
            index = int(getattr(fc, "array_index", -1))
            if not path:
                issues.append("F-Curve with empty data path")
            marker = (path, index)
            if marker in seen_markers:
                issues.append(f"Duplicate F-Curve reference '{path}'[{index}]")
            seen_markers.add(marker)

        unique_issues = []
        seen_issues = set()
        for issue in issues:
            if issue not in seen_issues:
                seen_issues.add(issue)
                unique_issues.append(issue)
        return unique_issues

    @staticmethod
    def describe_target(target, operation_name):
        """Returns the reason why a target is not compatible, or None."""
        if target is None:
            return "UNSUPPORTED TARGET 'unknown': no target supplied"
        name = getattr(target, "name", "target")
        owner = TargetResolver.get_owner(target)
        if owner is None:
            return f"UNSUPPORTED TARGET '{name}': owner could not be resolved"
        if not TargetResolver.is_target_editable(target):
            return f"UNSUPPORTED TARGET '{name}': target is read-only or linked data"
        anim_data = getattr(owner, "animation_data", None)
        if not anim_data:
            return f"UNSUPPORTED TARGET '{name}': owner has no animation_data"
        action = getattr(anim_data, "action", None)
        if not action:
            return f"UNSUPPORTED TARGET '{name}': no action assigned"
        slot = ActionAdapter.ensure_slot(anim_data, owner, action, create=False)
        if slot is None:
            return f"UNSUPPORTED TARGET '{name}': no action slot assigned"
        try:
            fcurves = TargetResolver.get_target_fcurves(target)
        except Exception as exc:
            return f"UNSUPPORTED TARGET '{name}': F-Curve resolution failed: {exc}"
        if not fcurves:
            return (
                f"PARTIALLY SUPPORTED TARGET '{name}': action '{action.name}' "
                f"has no matching F-Curves for this target"
            )
        return None

    @staticmethod
    def unsupported_target_result(target, operation_name):
        result = OperationResult(operation_name)
        if target is None:
            result.add_warning(
                f"UNSUPPORTED TARGET 'unknown': no target supplied for '{operation_name}'"
            )
            return result

        issue = ValidationEngine.describe_target(target, operation_name)
        if issue:
            result.add_warning(issue)
            return result

        result.processed_targets = 1
        KeyHeavenLogger.log_info(
            f"SUPPORTED TARGET '{name}' for '{operation_name}'"
        )
        return result


def execute_per_target_tool(op, context, tool_func, min_keyframes=0, filter_type='TRANSFORM', prepare_base=True):
    targets = TargetResolver.collect_active_targets(
        context,
        min_keyframes=min_keyframes,
        filter_type=filter_type
    )

    if not targets:
        op.report({'WARNING'}, "No editable animation targets found")
        return {'CANCELLED'}

    compatible = []
    for target in targets:
        issue = ValidationEngine.describe_target(target, op.bl_label)
        if issue:
            op.report({'WARNING'}, issue)
            continue
        compatible.append(target)
    targets = compatible
    if not targets:
        op.report({'WARNING'}, "No compatible animation targets found")
        return {'CANCELLED'}

    tx = TransactionEngine(targets, context)
    tx.capture(context)
    op_token = op_state_begin(op.bl_idname, targets)

    def _cancel(result):
        op_state_rollback(op_token)
        tx.rollback(context)
        report_operation_result(op, result)
        return {'CANCELLED'}

    try:
        if prepare_base:
            ActionBackupEngine.prepare_targets_from_base(targets, force_reset=False)
        op_state_snapshot(op.bl_idname, op_token)

        gap, gap_mode = _validation_gap_and_mode(context)
        baseline = [
            _validation_issue_set(target, context, gap) for target in targets
        ]

        combined = OperationResult(op.bl_label)
        RandomizerEngine.begin_pin_run()
        try:
            for t in targets:
                res = tool_func(t, context)
                combined.merge(res)
        finally:
            RandomizerEngine.end_pin_run()

        if not combined.success:
            return _cancel(combined)

        structural_failure = False
        for index, target in enumerate(targets):
            try:
                post_issues = ValidationEngine.validate_after_write(
                    target, context, gap
                )
            except Exception as e:
                KeyHeavenLogger.log_error(
                    "execute_per_target_tool.validate_after_write", e, target
                )
                post_issues = [f"post-write validation exception: {e}"]

            new_issues = _validation_new_issues(post_issues, baseline[index])
            if not new_issues:
                continue

            label = getattr(target, "name", "target")
            detail = "; ".join(new_issues[:3])
            if len(new_issues) > 3:
                detail += f"; (+{len(new_issues) - 3} more)"
            combined.add_warning(f"Post-write validation '{label}': {detail}")

            gap_only = all(_validation_is_gap_issue(issue) for issue in new_issues)
            if not gap_only:
                structural_failure = True

        if structural_failure:
            combined.add_warning(
                "Operation rolled back by post-write validation"
            )
            return _cancel(combined)

        tx.commit()
        op_state_commit(op_token)
        report_operation_result(op, combined)
        return {'FINISHED'}
    except Exception as e:
        op_state_rollback(op_token)
        tx.rollback(context)
        op.report({'ERROR'}, str(e))
        return {'CANCELLED'}
