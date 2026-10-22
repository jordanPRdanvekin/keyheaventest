from .._imports import *
from .logger import *
from .constants import *
from .rng import *
from .validator import *
class ActionAdapter:
    """Slot-safe access layer for Blender 5.x slotted actions.

    Rules:
    - Never touch Action.fcurves (removed in Blender 5.x).
    - Never read ChannelBags without a resolved ActionSlot of the owning datablock.
    - Never assign an Action without making sure AnimData.action_slot is valid.
    """

    _enum_cache = {}

    @staticmethod
    def get_owner(target):
        if target is None:
            return None
        return target.id_data if hasattr(target, "id_data") else target

    @staticmethod
    def get_assigned_slot(anim_data):
        if not anim_data:
            return None
        return getattr(anim_data, "action_slot", None)

    @staticmethod
    def _slot_belongs_to_action(slot, action):
        if slot is None or action is None:
            return False
        handle = getattr(slot, "handle", None)
        if handle is None:
            return False
        try:
            for candidate in action.slots:
                if getattr(candidate, "handle", None) == handle:
                    return True
        except Exception:
            return False
        return False

    @staticmethod
    def _find_slot(anim_data, owner, action):
        current = ActionAdapter.get_assigned_slot(anim_data)
        if current is not None and ActionAdapter._slot_belongs_to_action(current, action):
            return current

        last_identifier = getattr(anim_data, "last_slot_identifier", None)
        if last_identifier:
            try:
                for candidate in action.slots:
                    if getattr(candidate, "identifier", None) == last_identifier:
                        return candidate
            except Exception:
                pass

        id_type = slot_target_id_type(owner)
        if hasattr(anim_utils, "action_get_first_suitable_slot"):
            try:
                suitable = anim_utils.action_get_first_suitable_slot(action, id_type)
                if suitable is not None:
                    return suitable
            except Exception:
                pass

        try:
            for candidate in action.slots:
                if getattr(candidate, "target_id_type", None) == id_type:
                    return candidate
        except Exception:
            pass

        return None

    @staticmethod
    def ensure_slot(anim_data, owner, action=None, create=False):
        if not anim_data:
            return None
        action = action or getattr(anim_data, "action", None)
        if not action:
            return None

        slot = ActionAdapter._find_slot(anim_data, owner, action)
        if slot is None and create:
            try:
                slot = action.slots.new(
                    id_type=slot_target_id_type(owner), name=getattr(owner, "name", "Slot")
                )
            except Exception:
                slot = None

        if slot is not None:
            try:
                anim_data.action_slot = slot
            except Exception as exc:
                KeyHeavenLogger.log_error(
                    "ActionAdapter.ensure_slot could not assign the slot", exc
                )
                return None
        return slot

    @staticmethod
    def assign_action(anim_data, owner, action, create_slot=False):
        if not anim_data or not action:
            return None
        anim_data.action = action
        return ActionAdapter.ensure_slot(anim_data, owner, action, create=create_slot)

    @staticmethod
    def assign_action_preserving_slot(anim_data, owner, new_action, previous_slot=None):
        if not anim_data or not new_action:
            return None
        identifier = getattr(previous_slot, "identifier", None) if previous_slot else None
        handle = getattr(previous_slot, "handle", None) if previous_slot else None

        anim_data.action = new_action

        slot = None
        if identifier:
            try:
                for candidate in new_action.slots:
                    if getattr(candidate, "identifier", None) == identifier:
                        slot = candidate
                        break
            except Exception:
                slot = None
        if slot is None and handle is not None:
            try:
                for candidate in new_action.slots:
                    if getattr(candidate, "handle", None) == handle:
                        slot = candidate
                        break
            except Exception:
                slot = None
        if slot is None:
            return ActionAdapter.ensure_slot(anim_data, owner, new_action, create=True)

        try:
            anim_data.action_slot = slot
        except Exception:
            pass
        return slot

    @staticmethod
    def get_channelbag_for_target(target, create=False):
        if not HAS_BPY or not target:
            return None
        try:
            owner = ActionAdapter.get_owner(target)
            if owner is None:
                return None
            anim_data = getattr(owner, "animation_data", None)
            if not anim_data:
                if not create:
                    return None
                anim_data = owner.animation_data_create()

            action = anim_data.action
            if not action and create:
                action = bpy.data.actions.new(name=f"{owner.name}_Action")
                ActionAdapter.assign_action(anim_data, owner, action, create_slot=True)

            if not action:
                return None

            slot = ActionAdapter.ensure_slot(anim_data, owner, action, create=create)
            if slot is None:
                return None

            if hasattr(anim_utils, "animdata_get_channelbag_for_assigned_slot"):
                bag = anim_utils.animdata_get_channelbag_for_assigned_slot(anim_data)
                if bag:
                    return bag
            if hasattr(anim_utils, "action_get_channelbag_for_slot"):
                bag = anim_utils.action_get_channelbag_for_slot(action, slot)
                if bag:
                    return bag
            if create and hasattr(anim_utils, "action_ensure_channelbag_for_slot"):
                bag = anim_utils.action_ensure_channelbag_for_slot(action, slot)
                if bag:
                    return bag
            return None
        except Exception as e:
            KeyHeavenLogger.log_error("ActionAdapter.get_channelbag_for_target", e, target)
            return None

    @staticmethod
    def get_fcurves(target):
        if not HAS_BPY or not target:
            return []
        try:
            bag = ActionAdapter.get_channelbag_for_target(target, create=False)
            if bag is None:
                return []
            return list(bag.fcurves)
        except Exception as e:
            KeyHeavenLogger.log_error("ActionAdapter.get_fcurves", e, target)
            return []

    @staticmethod
    def ensure_fcurves(target, data_path, indices):
        created = []
        if not HAS_BPY or not target:
            return created
        try:
            owner = ActionAdapter.get_owner(target)
            anim_data = getattr(owner, "animation_data", None)
            if not anim_data:
                anim_data = owner.animation_data_create()

            action = anim_data.action
            if not action:
                action = bpy.data.actions.new(name=f"{owner.name}_Action")
                ActionAdapter.assign_action(anim_data, owner, action, create_slot=True)

            bag = ActionAdapter.get_channelbag_for_target(target, create=True)
            for idx in indices:
                fc = None
                if bag is not None:
                    try:
                        fc = bag.fcurves.ensure(data_path=data_path, index=idx)
                    except Exception:
                        fc = None
                    if fc is None:
                        try:
                            fc = bag.fcurves.find(data_path=data_path, index=idx)
                        except TypeError:
                            try:
                                fc = bag.fcurves.find(data_path, index=idx)
                            except Exception:
                                fc = None
                        except Exception:
                            fc = None
                if fc is None:
                    try:
                        fc = action.fcurve_ensure_for_datablock(owner, data_path, index=idx)
                    except Exception:
                        fc = None
                if fc is None:
                    KeyHeavenLogger.log_warning(
                        f"Could not ensure F-Curve '{data_path}'[{idx}] on '{owner.name}'"
                    )
                created.append(fc)
        except Exception as e:
            KeyHeavenLogger.log_error("ActionAdapter.ensure_fcurves", e, target)
        return created

    @staticmethod
    def find_fcurve(target, data_path, index):
        if not HAS_BPY or not target:
            return None
        try:
            bag = ActionAdapter.get_channelbag_for_target(target, create=False)
            if bag is None:
                return None
            try:
                return bag.fcurves.find(data_path=data_path, index=index)
            except TypeError:
                return bag.fcurves.find(data_path, index=index)
        except Exception:
            return None

    @staticmethod
    def read_keyframes(fcurve):
        """Returns the keyframes of a curve as ``(frame, value)`` pairs."""
        if fcurve is None:
            return []
        points = list(fcurve.keyframe_points)
        if not points:
            return []
        coordinates = [0.0] * (len(points) * 2)
        fcurve.keyframe_points.foreach_get("co", coordinates)
        return [
            (coordinates[index * 2], coordinates[index * 2 + 1])
            for index in range(len(points))
        ]

    @staticmethod
    def keyframe_enum_values(name):
        """Returns the integer values of a keyframe enum property."""
        cached = ActionAdapter._enum_cache.get(name)
        if cached is not None:
            return cached
        values = {}
        try:
            prop = bpy.types.Keyframe.bl_rna.properties[name]
            values = {item.identifier: int(item.value) for item in prop.enum_items}
        except Exception:
            values = {}
        ActionAdapter._enum_cache[name] = values
        return values

    @staticmethod
    def write_keyframes(fcurve, keyframes, interpolation="BEZIER", handle_type="AUTO_CLAMPED"):
        """Replaces the keyframes of a curve with a single batch write.

        Writing the coordinates with ``foreach_set`` and rebuilding the curve
        once is orders of magnitude faster than inserting the keys one by one.
        The interpolation, the handle types and the handle positions are reset
        by the rebuild, so the callers that need them restore them afterwards.
        """
        if fcurve is None:
            return 0
        points = fcurve.keyframe_points
        points.clear()
        if not keyframes:
            fcurve.update()
            return 0
        ordered = sorted(keyframes, key=lambda item: float(item[0]))
        coordinates = []
        for frame, value in ordered:
            coordinates.extend((float(frame), float(value)))
        points.add(len(ordered))
        points.foreach_set("co", coordinates)
        interpolation_values = ActionAdapter.keyframe_enum_values("interpolation")
        handle_values = ActionAdapter.keyframe_enum_values("handle_left_type")
        interpolation_id = interpolation_values.get(interpolation, interpolation_values.get("BEZIER", 2))
        handle_id = handle_values.get(handle_type, handle_values.get("AUTO_CLAMPED", 4))
        points.foreach_set("interpolation", [interpolation_id] * len(ordered))
        points.foreach_set("handle_left_type", [handle_id] * len(ordered))
        points.foreach_set("handle_right_type", [handle_id] * len(ordered))
        fcurve.update()
        return len(ordered)

    @staticmethod
    def fingerprint(target):
        try:
            entries = []
            for fc in ActionAdapter.get_fcurves(target):
                count = len(fc.keyframe_points)
                if count == 0:
                    entries.append((fc.data_path, fc.array_index, 0))
                else:
                    first = fc.keyframe_points[0].co
                    last = fc.keyframe_points[-1].co
                    entries.append(
                        (
                            fc.data_path,
                            fc.array_index,
                            count,
                            round(first[0], 3),
                            round(first[1], 5),
                            round(last[0], 3),
                            round(last[1], 5),
                        )
                    )
                if len(entries) >= 96:
                    break
            return zlib.adler32(repr(entries).encode("utf-8")) & 0xFFFFFFFF
        except Exception:
            return 0
