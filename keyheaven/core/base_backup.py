from .._imports import *
from .logger import *
from .constants import *
from .rng import *
from .validator import *
from .actions_compat import *
from .targets import *
class ActionBackupEngine:
    """Manages pristine backups (.kh_base) and timeline frame bounds per datablock."""

    BASE_PROP_KEY = BASE_PROP_KEY

    @staticmethod
    def _get_animatable_sub_datablocks(obj):
        sub_dbs = []
        if not obj or not HAS_BPY:
            return sub_dbs

        data = getattr(obj, "data", None)
        if data is not None:
            if getattr(data, "shape_keys", None):
                sub_dbs.append(data.shape_keys)
            if hasattr(data, "animation_data"):
                sub_dbs.append(data)

        if hasattr(obj, "material_slots"):
            for slot in obj.material_slots:
                if slot.material:
                    sub_dbs.append(slot.material)
                    if slot.material.use_nodes and slot.material.node_tree:
                        sub_dbs.append(slot.material.node_tree)

        if hasattr(obj, "modifiers"):
            for mod in obj.modifiers:
                if mod.type == "NODES" and getattr(mod, "node_group", None):
                    sub_dbs.append(mod.node_group)

        return sub_dbs

    @staticmethod
    def _generate_datablock_base_name(db):
        type_prefix = type(db).__name__
        clean_name = db.name.split(".kh_base")[0].split(".kh_purge")[0]
        name_hash = zlib.adler32(f"{type_prefix}_{clean_name}".encode("utf-8")) & 0xFFFF
        return f"{clean_name}_{type_prefix}_{name_hash:04x}.kh_base"

    @staticmethod
    def get_base_action(target):
        if not HAS_BPY or not target:
            return None
        try:
            obj = TargetResolver.get_owner(target)
            if obj is None:
                return None
            all_dbs = [obj] + ActionBackupEngine._get_animatable_sub_datablocks(obj)
            primary_base = None

            for db in all_dbs:
                anim_data = getattr(db, "animation_data", None)
                if not anim_data or not anim_data.action:
                    continue

                act = anim_data.action
                if act.name.endswith(".kh_base"):
                    if db == obj:
                        primary_base = act
                    continue

                ptr_name = db.get(ActionBackupEngine.BASE_PROP_KEY)
                base_act = bpy.data.actions.get(ptr_name) if ptr_name else None

                if not base_act:
                    base_name = ActionBackupEngine._generate_datablock_base_name(db)
                    base_act = bpy.data.actions.get(base_name)
                    if not base_act:
                        base_act = act.copy()
                        base_act.name = base_name
                        base_act.use_fake_user = True
                    db[ActionBackupEngine.BASE_PROP_KEY] = base_act.name
                    KeyHeavenLogger.log_info(
                        f"Stashed pristine Base Action '{base_act.name}' for datablock '{db.name}'"
                    )

                if db == obj:
                    primary_base = base_act

            if HAS_BPY and bpy.context and bpy.context.scene:
                sc = bpy.context.scene
                if "_kh_base_frame_start" not in sc:
                    sc["_kh_base_frame_start"] = sc.frame_start
                    sc["_kh_base_frame_end"] = sc.frame_end
                    sc["_kh_base_frame_current"] = sc.frame_current

            return primary_base
        except Exception as e:
            KeyHeavenLogger.log_error("ActionBackupEngine.get_base_action", e, target)
            return None

    @staticmethod
    def prepare_target_from_base(target, force_reset=False):
        if not HAS_BPY or not target:
            return None
        try:
            obj = TargetResolver.get_owner(target)
            if obj is None:
                return None
            all_dbs = [obj] + ActionBackupEngine._get_animatable_sub_datablocks(obj)
            primary_act = None

            for db in all_dbs:
                anim_data = getattr(db, "animation_data", None)
                if not anim_data or not anim_data.action:
                    continue

                act = anim_data.action
                base_act = ActionBackupEngine.get_base_action(db)
                if not base_act:
                    if db == obj:
                        primary_act = act
                    continue

                if not act.name.endswith(".kh_base") and not force_reset:
                    if db == obj:
                        primary_act = act
                    continue

                clean_name = base_act.name.split(".kh_base")[0]
                old_act = anim_data.action
                old_slot = ActionAdapter.get_assigned_slot(anim_data)

                if old_act and old_act != base_act:
                    old_act.name = f"{old_act.name}_kh_purge"

                new_act = base_act.copy()
                new_act.name = clean_name
                new_act.use_fake_user = False
                ActionAdapter.assign_action_preserving_slot(
                    anim_data, db, new_act, old_slot
                )

                if (
                    old_act
                    and old_act != base_act
                    and old_act != new_act
                    and old_act.users == 0
                ):
                    try:
                        bpy.data.actions.remove(old_act)
                    except Exception:
                        pass

                if db == obj:
                    primary_act = new_act

            return primary_act
        except Exception as e:
            KeyHeavenLogger.log_error("ActionBackupEngine.prepare_target_from_base", e, target)
            return None

    @staticmethod
    def prepare_targets_from_base(targets, force_reset=False):
        if not targets:
            return []
        prepared_objs = set()
        prepared_actions = []

        for target in targets:
            try:
                obj = TargetResolver.get_owner(target)
                if obj in prepared_objs:
                    continue
                prepared_objs.add(obj)
                ActionBackupEngine.get_base_action(target)
                act = ActionBackupEngine.prepare_target_from_base(
                    target, force_reset=force_reset
                )
                if act:
                    prepared_actions.append(act)
            except Exception as e:
                KeyHeavenLogger.log_error(
                    "ActionBackupEngine.prepare_targets_from_base", e, target
                )

        return prepared_actions

    @staticmethod
    def restore_backup(target):
        if not HAS_BPY or not target:
            return False
        try:
            obj = TargetResolver.get_owner(target)
            if obj is None:
                return False
            all_dbs = [obj] + ActionBackupEngine._get_animatable_sub_datablocks(obj)
            restored_any = False

            for db in all_dbs:
                anim_data = getattr(db, "animation_data", None)
                if not anim_data or not anim_data.action:
                    continue

                ptr_name = db.get(ActionBackupEngine.BASE_PROP_KEY)
                base_act = bpy.data.actions.get(ptr_name) if ptr_name else None
                if not base_act:
                    base_name = ActionBackupEngine._generate_datablock_base_name(db)
                    base_act = bpy.data.actions.get(base_name)

                if base_act:
                    old_act = anim_data.action
                    old_slot = ActionAdapter.get_assigned_slot(anim_data)
                    clean_name = base_act.name.split(".kh_base")[0]
                    if old_act != base_act:
                        old_act.name = f"{old_act.name}_kh_purge"

                    new_act = base_act.copy()
                    new_act.name = clean_name
                    new_act.use_fake_user = False
                    ActionAdapter.assign_action_preserving_slot(
                        anim_data, db, new_act, old_slot
                    )

                    if (
                        old_act
                        and old_act != base_act
                        and old_act != new_act
                        and old_act.users == 0
                    ):
                        try:
                            bpy.data.actions.remove(old_act)
                        except Exception:
                            pass

                    op_state_clear_db(db)
                    restored_any = True
                    KeyHeavenLogger.log_info(
                        f"Restored Action for '{db.name}' from Base '{base_act.name}'"
                    )

            if restored_any and HAS_BPY and bpy.context and bpy.context.scene:
                sc = bpy.context.scene
                if "_kh_base_frame_start" in sc:
                    sc.frame_start = int(sc["_kh_base_frame_start"])
                if "_kh_base_frame_end" in sc:
                    sc.frame_end = int(sc["_kh_base_frame_end"])
                if "_kh_base_frame_current" in sc:
                    sc.frame_current = int(sc["_kh_base_frame_current"])
                KeyHeavenLogger.log_info(
                    f"Restored base timeline bounds: [{sc.frame_start}, {sc.frame_end}]"
                )

            return restored_any
        except Exception as e:
            KeyHeavenLogger.log_error("ActionBackupEngine.restore_backup", e, target)
            return False

    @staticmethod
    def capture_new_base(target):
        if not HAS_BPY or not target:
            return False
        try:
            obj = TargetResolver.get_owner(target)
            if obj is None:
                return False
            all_dbs = [obj] + ActionBackupEngine._get_animatable_sub_datablocks(obj)
            captured_any = False

            for db in all_dbs:
                anim_data = getattr(db, "animation_data", None)
                if not anim_data or not anim_data.action:
                    continue

                act = anim_data.action
                ptr_name = db.get(ActionBackupEngine.BASE_PROP_KEY)
                old_base = bpy.data.actions.get(ptr_name) if ptr_name else None
                base_name = ActionBackupEngine._generate_datablock_base_name(db)

                new_base = act.copy()
                new_base.name = base_name
                new_base.use_fake_user = True
                db[ActionBackupEngine.BASE_PROP_KEY] = new_base.name

                if old_base and old_base != new_base:
                    old_base.use_fake_user = False
                    if old_base.users == 0:
                        try:
                            bpy.data.actions.remove(old_base)
                        except Exception:
                            pass

                op_state_clear_db(db)
                captured_any = True
                KeyHeavenLogger.log_info(
                    f"Captured new Base Action '{base_name}' for datablock '{db.name}'"
                )

            if captured_any and HAS_BPY and bpy.context and bpy.context.scene:
                sc = bpy.context.scene
                sc["_kh_base_frame_start"] = sc.frame_start
                sc["_kh_base_frame_end"] = sc.frame_end
                sc["_kh_base_frame_current"] = sc.frame_current
                KeyHeavenLogger.log_info(
                    f"Captured new baseline timeline bounds: [{sc.frame_start}, {sc.frame_end}]"
                )

            return captured_any
        except Exception as e:
            KeyHeavenLogger.log_error("ActionBackupEngine.capture_new_base", e, target)
            return False
