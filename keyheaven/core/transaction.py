from .._imports import *
from .logger import *
from .constants import *
from .rng import *
from .validator import *
from .actions_compat import *
from .targets import *
from .base_backup import *
def _op_state_dbs(targets):
    dbs = []
    seen = set()
    for target in targets or []:
        obj = TargetResolver.get_owner(target)
        if obj is None:
            continue
        for db in [obj] + ActionBackupEngine._get_animatable_sub_datablocks(obj):
            if db is None or id(db) in seen:
                continue
            seen.add(id(db))
            dbs.append(db)
    return dbs


def op_state_clear_db(db):
    if not HAS_BPY or db is None:
        return
    snap_name = db.get(OP_SNAPSHOT_PROP)
    db[OP_ID_PROP] = ""
    db[OP_SNAPSHOT_PROP] = ""
    snap = bpy.data.actions.get(snap_name) if snap_name else None
    if snap is not None:
        snap.use_fake_user = False
        if snap.users == 0:
            try:
                bpy.data.actions.remove(snap)
            except Exception:
                pass


def op_state_clear(targets):
    for db in _op_state_dbs(targets):
        op_state_clear_db(db)


def op_state_begin(op_id, targets):
    records = []
    for db in _op_state_dbs(targets):
        anim_data = getattr(db, "animation_data", None)
        action = getattr(anim_data, "action", None) if anim_data else None
        if anim_data is None or action is None:
            continue
        previous_id = db.get(OP_ID_PROP, "")
        previous_snapshot = db.get(OP_SNAPSHOT_PROP, "")
        snapshot = bpy.data.actions.get(previous_snapshot) if previous_snapshot else None
        if previous_id == op_id and snapshot is not None and snapshot != action:
            slot = ActionAdapter.get_assigned_slot(anim_data)
            restored = snapshot.copy()
            restored.name = action.name
            ActionAdapter.assign_action_preserving_slot(anim_data, db, restored, slot)
            if (
                action.users == 0
                and action is not snapshot
                and not action.name.endswith(".kh_base")
            ):
                try:
                    bpy.data.actions.remove(action)
                except Exception:
                    pass
        records.append(
            {
                "db": db,
                "previous_id": previous_id,
                "previous_snapshot": previous_snapshot,
                "new_snapshot": None,
            }
        )
    return records


def op_state_snapshot(op_id, records):
    for record in records:
        db = record["db"]
        anim_data = getattr(db, "animation_data", None)
        action = getattr(anim_data, "action", None) if anim_data else None
        if action is None:
            continue
        snapshot = action.copy()
        snapshot.name = f"{action.name}{OP_SNAPSHOT_SUFFIX}"
        snapshot.use_fake_user = True
        record["new_snapshot"] = snapshot.name
        db[OP_ID_PROP] = op_id
        db[OP_SNAPSHOT_PROP] = snapshot.name


def op_state_commit(records):
    for record in records:
        previous_snapshot = record["previous_snapshot"]
        new_snapshot = record["new_snapshot"]
        if not previous_snapshot or previous_snapshot == new_snapshot:
            continue
        old = bpy.data.actions.get(previous_snapshot)
        if old is not None:
            old.use_fake_user = False
            if old.users == 0:
                try:
                    bpy.data.actions.remove(old)
                except Exception:
                    pass


def op_state_rollback(records):
    for record in records:
        db = record["db"]
        db[OP_ID_PROP] = record["previous_id"]
        db[OP_SNAPSHOT_PROP] = record["previous_snapshot"]
        new_snapshot = record["new_snapshot"]
        if new_snapshot and new_snapshot != record["previous_snapshot"]:
            snap = bpy.data.actions.get(new_snapshot)
            if snap is not None:
                snap.use_fake_user = False
                if snap.users == 0:
                    try:
                        bpy.data.actions.remove(snap)
                    except Exception:
                        pass


class TransactionEngine:
    """Atomic capture, rollback, and memory-safe commit across targets and timeline."""

    def __init__(self, targets, context=None):
        self.targets = targets or []
        self.snapshots = {}
        self.frame_data = None
        self.captured = False

    def capture(self, context=None):
        if not HAS_BPY or not self.targets:
            return
        try:
            if context and hasattr(context, "scene"):
                self.frame_data = (
                    context.scene.frame_start,
                    context.scene.frame_end,
                    context.scene.frame_current,
                )

            self.snapshots.clear()
            seen = set()
            for target in self.targets:
                obj = TargetResolver.get_owner(target)
                if obj is None:
                    continue
                all_dbs = [obj] + ActionBackupEngine._get_animatable_sub_datablocks(obj)
                for db in all_dbs:
                    if db in seen:
                        continue
                    seen.add(db)
                    anim_data = getattr(db, "animation_data", None)
                    if anim_data and anim_data.action:
                        slot = ActionAdapter.get_assigned_slot(anim_data)
                        self.snapshots[id(db)] = (
                            db,
                            anim_data.action.copy(),
                            getattr(slot, "identifier", None),
                            getattr(slot, "handle", None),
                        )
            self.captured = True
        except Exception as e:
            KeyHeavenLogger.log_error("TransactionEngine.capture", e)

    def rollback(self, context=None):
        if not self.captured or not HAS_BPY:
            return
        try:
            if self.frame_data and context and hasattr(context, "scene"):
                fs, fe, fc = self.frame_data
                context.scene.frame_start = fs
                context.scene.frame_end = fe
                context.scene.frame_current = fc

            for db, snapshot, identifier, handle in self.snapshots.values():
                anim_data = getattr(db, "animation_data", None)
                if not anim_data or snapshot is None:
                    continue
                current_act = anim_data.action
                previous_slot = ActionAdapter.get_assigned_slot(anim_data)

                restored_slot = None
                if identifier:
                    for candidate in snapshot.slots:
                        if getattr(candidate, "identifier", None) == identifier:
                            restored_slot = candidate
                            break
                if restored_slot is None and handle is not None:
                    for candidate in snapshot.slots:
                        if getattr(candidate, "handle", None) == handle:
                            restored_slot = candidate
                            break
                if restored_slot is None:
                    restored_slot = previous_slot

                ActionAdapter.assign_action_preserving_slot(
                    anim_data, db, snapshot, restored_slot
                )

                if (
                    current_act
                    and current_act.users == 0
                    and not current_act.name.endswith(".kh_base")
                    and current_act is not snapshot
                ):
                    try:
                        bpy.data.actions.remove(current_act)
                    except Exception:
                        pass

            self.snapshots.clear()
            self.captured = False
            KeyHeavenLogger.log_warning("Transaction rollback completed successfully.")
        except Exception as e:
            KeyHeavenLogger.log_error("TransactionEngine.rollback", e)

    def commit(self):
        if not self.captured or not HAS_BPY:
            return
        try:
            for db, snapshot, identifier, handle in self.snapshots.values():
                if (
                    snapshot
                    and snapshot.users == 0
                    and not snapshot.name.endswith(".kh_base")
                ):
                    try:
                        bpy.data.actions.remove(snapshot)
                    except Exception:
                        pass
            self.snapshots.clear()
            self.captured = False
        except Exception as e:
            KeyHeavenLogger.log_warning(f"TransactionEngine.commit note: {e}")
