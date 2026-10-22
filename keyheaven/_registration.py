from ._imports import *
from .core import *
from .properties import *
from .operators.ops import *
from .ui.panels import *
from .ui.gizmos import *
from .ui.tooltips import *
if HAS_BPY:
    classes = (
        KeyHeaven_Properties,
        KEYHEAVEN_OT_protect_keys,
        KEYHEAVEN_OT_unprotect_keys,
        KEYHEAVEN_OT_pin_keys,
        KEYHEAVEN_OT_unpin_keys,
        KEYHEAVEN_OT_toggle_boundary,
        KEYHEAVEN_OT_restore_backup,
        KEYHEAVEN_OT_capture_base,
        KEYHEAVEN_OT_apply_randomizer,
        KEYHEAVEN_OT_quick_animate,
        KEYHEAVEN_OT_select_random_targets,
        KEYHEAVEN_OT_select_random_keyframes,
        KEYHEAVEN_OT_apply_breathing,
        KEYHEAVEN_OT_apply_squash,
        KEYHEAVEN_OT_apply_jiggle,
        KEYHEAVEN_OT_apply_drag,
        KEYHEAVEN_OT_apply_tremor,
        KEYHEAVEN_OT_apply_noise,
        KEYHEAVEN_OT_apply_wave,
        KEYHEAVEN_OT_apply_secondary,
        KEYHEAVEN_OT_analyze_motion,
        KEYHEAVEN_OT_pin_impacts,
        KEYHEAVEN_OT_adjust_clearance,
        KEYHEAVEN_OT_apply_stagger,
        KEYHEAVEN_OT_apply_propagation_wave,
        KEYHEAVEN_OT_apply_chain_drag,
        KEYHEAVEN_OT_apply_follow_drag,
        KEYHEAVEN_OT_apply_polish,
        KEYHEAVEN_OT_make_it_loop,
        KEYHEAVEN_OT_apply_easing,
        KEYHEAVEN_OT_apply_time_scale,
        KEYHEAVEN_OT_deoverlap_objects,
        KEYHEAVEN_OT_sanitize_and_repair_all,
        KEYHEAVEN_OT_cleanup_bake,
        KEYHEAVEN_OT_autobake,
        KEYHEAVEN_OT_apply_preset,
        KEYHEAVEN_GT_clearance_gizmo,
        KEYHEAVEN_GGT_clearance,
        KEYHEAVEN_MT_context_menu,
        KEYHEAVEN_PT_main_panel,
        KEYHEAVEN_PT_protection,
        KEYHEAVEN_PT_randomizer,
        KEYHEAVEN_PT_chains,
        KEYHEAVEN_PT_polish,
        KEYHEAVEN_PT_cycle,
        KEYHEAVEN_PT_effects,
        KEYHEAVEN_PT_curves,
        KEYHEAVEN_PT_deoverlap,
        KEYHEAVEN_PT_sanitizer,
        KEYHEAVEN_PT_analysis,
        KEYHEAVEN_PT_presets,
    )
else:
    classes = ()


def keyheaven_version_supported():
    if not HAS_BPY:
        return False
    try:
        return tuple(bpy.app.version) >= (5, 0, 0)
    except Exception:
        return False


def register():
    if not HAS_BPY:
        return
    if not keyheaven_version_supported():
        KeyHeavenLogger.log_error(
            "register",
            RuntimeError(
                f"KeyHeaven 4.0.0 requires Blender 5.x; found {bpy.app.version_string}"
            ),
        )
        return
    for cls in classes:
        try:
            bpy.utils.register_class(cls)
        except Exception as e:
            KeyHeavenLogger.log_error("register_class", e, cls.__name__)
    bpy.types.Scene.keyheaven = bpy.props.PointerProperty(type=KeyHeaven_Properties)
    register_menus()


def unregister():
    if not HAS_BPY:
        return
    unregister_menus()
    try:
        if hasattr(bpy.types.Scene, "keyheaven"):
            del bpy.types.Scene.keyheaven
    except Exception:
        pass
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception as e:
            KeyHeavenLogger.log_error("unregister_class", e, cls.__name__)


if __name__ == "__main__":
    register()
