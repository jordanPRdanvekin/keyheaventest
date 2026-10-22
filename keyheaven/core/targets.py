from .._imports import *
from .logger import *
from .constants import *
from .rng import *
from .validator import *
from .actions_compat import *
class TargetResolver:
    """Universal resolver for animatable data, hierarchy sorting, and transform curves."""

    @staticmethod
    def is_target_editable(target):
        if not target:
            return False
        try:
            obj = TargetResolver.get_owner(target)
            if getattr(obj, "library", None) is not None:
                return False
            override = getattr(obj, "override_library", None)
            if override and getattr(override, "is_system_override", False):
                return False
            return True
        except Exception:
            return False

    @staticmethod
    def get_owner(target):
        if target is None:
            return None
        return target.id_data if hasattr(target, "id_data") else target

    @staticmethod
    def is_bone(target):
        return HAS_BPY and isinstance(target, bpy.types.PoseBone)

    @staticmethod
    def is_shape_key(target):
        return HAS_BPY and isinstance(target, bpy.types.ShapeKey)

    @staticmethod
    def get_target_dimension(target):
        if not target or not HAS_BPY:
            return 1.0
        try:
            if TargetResolver.is_bone(target):
                return max(0.1, min(10.0, float(target.length)))
            obj = TargetResolver.get_owner(target)
            if hasattr(obj, "dimensions"):
                dim = obj.dimensions.length
                if dim > 0.01:
                    return max(0.1, min(50.0, float(dim * 0.5)))
            return 1.0
        except Exception:
            return 1.0

    @staticmethod
    def ensure_single_user_action(target):
        try:
            obj = TargetResolver.get_owner(target)
            if obj is None:
                return
            all_dbs = [obj] + ActionBackupEngine._get_animatable_sub_datablocks(obj)
            for db in all_dbs:
                anim_data = getattr(db, "animation_data", None)
                if anim_data and anim_data.action and anim_data.action.users > 1:
                    previous_slot = ActionAdapter.get_assigned_slot(anim_data)
                    copied = anim_data.action.copy()
                    ActionAdapter.assign_action_preserving_slot(
                        anim_data, db, copied, previous_slot
                    )
        except Exception as e:
            KeyHeavenLogger.log_error("TargetResolver.ensure_single_user_action", e, target)

    @staticmethod
    def get_target_fcurves(target, scope="ALL"):
        if not target or not HAS_BPY:
            return []

        try:
            if TargetResolver.is_bone(target):
                obj = TargetResolver.get_owner(target)
                bone_prefix = f'pose.bones["{target.name}"].'
                all_fcs = ActionAdapter.get_fcurves(obj)
                fcs = [fc for fc in all_fcs if fc.data_path.startswith(bone_prefix)]
                if scope == "TRANSFORM_ONLY":
                    return [
                        fc
                        for fc in fcs
                        if fc.data_path[len(bone_prefix):] in TRANSFORM_CHANNELS
                    ]
                return fcs

            if TargetResolver.is_shape_key(target):
                key_block = target
                shape_keys = TargetResolver.get_owner(key_block)
                key_prefix = f'key_blocks["{key_block.name}"].value'
                all_fcs = ActionAdapter.get_fcurves(shape_keys)
                return [
                    fc
                    for fc in all_fcs
                    if fc.data_path == key_prefix or fc.data_path.startswith(key_prefix)
                ]

            fcurves = ActionAdapter.get_fcurves(target)

            if scope == "TRANSFORM_ONLY":
                return [fc for fc in fcurves if fc.data_path in TRANSFORM_CHANNELS]

            obj_data = getattr(target, "data", None)
            if obj_data and hasattr(obj_data, "animation_data"):
                fcurves.extend(ActionAdapter.get_fcurves(obj_data))

            if (
                scope in {"ALL", "INCLUDE_SHAPE_KEYS"}
                and obj_data
                and getattr(obj_data, "shape_keys", None)
            ):
                fcurves.extend(ActionAdapter.get_fcurves(obj_data.shape_keys))

            if scope in {"ALL", "INCLUDE_MATERIALS"}:
                for slot in getattr(target, "material_slots", []):
                    if slot.material:
                        fcurves.extend(ActionAdapter.get_fcurves(slot.material))
                        if slot.material.use_nodes and slot.material.node_tree:
                            fcurves.extend(ActionAdapter.get_fcurves(slot.material.node_tree))

            if scope in {"ALL", "INCLUDE_GEO_NODES"} and hasattr(target, "modifiers"):
                for mod in target.modifiers:
                    if mod.type == "NODES" and getattr(mod, "node_group", None):
                        fcurves.extend(ActionAdapter.get_fcurves(mod.node_group))

            deduped = []
            seen = set()
            for fc in fcurves:
                key = (fc.data_path, fc.array_index, getattr(fc.id_data, "name", ""))
                if key not in seen:
                    seen.add(key)
                    deduped.append(fc)
            return deduped
        except Exception as e:
            KeyHeavenLogger.log_error("TargetResolver.get_target_fcurves", e, target)
            return []

    @staticmethod
    def channel_prefix(target):
        if TargetResolver.is_bone(target):
            return f'pose.bones["{target.name}"].'
        return ""

    @staticmethod
    def channel_data_path(target, channel):
        return f"{TargetResolver.channel_prefix(target)}{channel}"

    @staticmethod
    def channel_index_count(channel):
        if channel == "value":
            return 1
        if channel == "rotation_quaternion":
            return 4
        return 3

    @staticmethod
    def ensure_transform_fcurves(target, channel_type="location"):
        if not target or not HAS_BPY:
            return []
        try:
            TargetResolver.ensure_single_user_action(target)
            owner = TargetResolver.get_owner(target)
            if not getattr(owner, "animation_data", None):
                owner.animation_data_create()

            full_data_path = TargetResolver.channel_data_path(target, channel_type)
            existing = TargetResolver.get_target_fcurves(target)
            existing_indices = {
                fc.array_index
                for fc in existing
                if fc.data_path == full_data_path
            }
            num_channels = TargetResolver.channel_index_count(channel_type)
            missing = [idx for idx in range(num_channels) if idx not in existing_indices]
            if not missing:
                return [
                    fc for fc in existing if fc.data_path == full_data_path
                ]

            created = ActionAdapter.ensure_fcurves(target, full_data_path, missing)
            return [fc for fc in created if fc is not None]
        except Exception as e:
            KeyHeavenLogger.log_error("TargetResolver.ensure_transform_fcurves", e, target)
            return []

    @staticmethod
    def sort_targets_hierarchically(targets, reverse=False):
        if not targets or not HAS_BPY:
            return targets
        try:
            if TargetResolver.is_bone(targets[0]):
                def get_bone_depth(bone):
                    depth = 0
                    current = bone.parent
                    while current:
                        depth += 1
                        current = current.parent
                    return depth

                return sorted(targets, key=get_bone_depth, reverse=reverse)

            if isinstance(targets[0], bpy.types.Object):
                def get_obj_depth(obj):
                    depth = 0
                    current = obj.parent
                    while current:
                        depth += 1
                        current = current.parent
                    return depth

                return sorted(targets, key=get_obj_depth, reverse=reverse)

            return targets
        except Exception as e:
            KeyHeavenLogger.log_error("TargetResolver.sort_targets_hierarchically", e)
            return targets

    @staticmethod
    def sort_targets_spatially(targets, origin):
        if not targets or origin is None:
            return targets
        try:
            origin_pos = TargetResolver.target_world_position(origin)
            if origin_pos is None:
                return targets

            def distance(target):
                pos = TargetResolver.target_world_position(target)
                if pos is None:
                    return float("inf")
                return (pos - origin_pos).length

            return sorted(targets, key=distance)
        except Exception as e:
            KeyHeavenLogger.log_error("TargetResolver.sort_targets_spatially", e)
            return targets

    @staticmethod
    def target_world_position(target):
        if not HAS_BPY or target is None:
            return None
        try:
            if TargetResolver.is_bone(target):
                return target.head.copy()
            if TargetResolver.is_shape_key(target):
                return None
            return target.matrix_world.translation.copy()
        except Exception:
            return None

    @staticmethod
    def collect_active_targets(context, min_keyframes=0, filter_type="TRANSFORM"):
        targets = []
        if not HAS_BPY or not context:
            return targets
        try:
            is_pose = context.mode == "POSE"

            if is_pose and context.active_object:
                active_bone = context.active_pose_bone
                selected_bones = [
                    bone
                    for bone in context.selected_pose_bones
                    if TargetResolver.is_target_editable(bone)
                ]
                if active_bone in selected_bones:
                    ordered = [active_bone] + [b for b in selected_bones if b != active_bone]
                else:
                    ordered = selected_bones

                for bone in ordered:
                    scope = "TRANSFORM_ONLY" if filter_type == "TRANSFORM" else "ALL"
                    fcs = TargetResolver.get_target_fcurves(bone, scope=scope)
                    frames = {kp.co[0] for fc in fcs for kp in fc.keyframe_points}
                    if len(frames) >= min_keyframes or min_keyframes == 0:
                        targets.append(bone)
            else:
                active_obj = context.active_object
                selected_objs = [
                    obj
                    for obj in context.selected_objects
                    if TargetResolver.is_target_editable(obj)
                ]
                if active_obj in selected_objs:
                    ordered = [active_obj] + [o for o in selected_objs if o != active_obj]
                else:
                    ordered = selected_objs

                for obj in ordered:
                    scope = "TRANSFORM_ONLY" if filter_type == "TRANSFORM" else "ALL"
                    fcs = TargetResolver.get_target_fcurves(obj, scope=scope)
                    frames = {kp.co[0] for fc in fcs for kp in fc.keyframe_points}
                    if len(frames) >= min_keyframes or min_keyframes == 0:
                        targets.append(obj)

                    if (
                        filter_type in {"ALL", "VALUE"}
                        and getattr(obj, "data", None)
                        and getattr(obj.data, "shape_keys", None)
                    ):
                        for key_block in obj.data.shape_keys.key_blocks:
                            kb_fcs = TargetResolver.get_target_fcurves(key_block)
                            kb_frames = {
                                kp.co[0] for fc in kb_fcs for kp in fc.keyframe_points
                            }
                            if len(kb_frames) >= min_keyframes and len(kb_frames) > 0:
                                targets.append(key_block)
        except Exception as e:
            KeyHeavenLogger.log_error("TargetResolver.collect_active_targets", e)

        return targets
