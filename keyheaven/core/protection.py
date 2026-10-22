from .._imports import *
from .logger import *
from .constants import *
from .rng import *
from .validator import *
from .actions_compat import *
from .targets import *
from .base_backup import *
from .transaction import *
class KeyframeMetaStore:
    """JSON metadata stored on the Action: protected keys and pin relationships.

    Keyframe.type is never used as internal state storage. The parsed payload
    and its lookup indexes are cached per action, so the protection lookups of
    a long curve never re-parse the JSON.
    """

    _cache = {}
    _cache_limit = 64

    @staticmethod
    def action_of(owner):
        if owner is None:
            return None
        if HAS_BPY and isinstance(owner, bpy.types.Action):
            return owner
        action = getattr(owner, "id_data", None)
        if action is not None and HAS_BPY and isinstance(action, bpy.types.Action):
            return action
        return None

    @staticmethod
    def _resolve(fc, kp):
        action = KeyframeMetaStore.action_of(fc)
        if action is None or kp is None:
            return None, None
        key = (
            fc.data_path,
            int(fc.array_index),
            round(float(kp.co[0]), TIME_ROUND),
        )
        return action, key

    @staticmethod
    def _build_indexes(data):
        protected = {}
        for entry in data.get("protected", []):
            try:
                key = (
                    entry.get("p", ""),
                    int(entry.get("i", -1)),
                    round(float(entry.get("f", 0.0)), TIME_ROUND),
                )
            except (TypeError, ValueError):
                continue
            mode = entry.get("m", "BOTH")
            protected[key] = mode if mode in ("BOTH", "VALUE", "TIMING") else "BOTH"
        pins = {}
        for pin in data.get("pins", []):
            pin_id = pin.get("id")
            for key in pin.get("keys", []):
                try:
                    index_key = (
                        key[0],
                        int(key[1]),
                        round(float(key[2]), TIME_ROUND),
                    )
                except (TypeError, ValueError, IndexError):
                    continue
                pins.setdefault(index_key, pin_id)
        return protected, pins

    @staticmethod
    def _store(action, raw, data):
        protected, pins = KeyframeMetaStore._build_indexes(data)
        if len(KeyframeMetaStore._cache) >= KeyframeMetaStore._cache_limit:
            KeyframeMetaStore._cache.clear()
        KeyframeMetaStore._cache[id(action)] = (raw, data, protected, pins)
        return data

    @staticmethod
    def load(action):
        empty = {"version": METADATA_VERSION, "protected": [], "pins": []}
        if action is None:
            return empty
        try:
            raw = action.get(METADATA_PROP_KEY)
        except Exception:
            return empty
        if not raw:
            KeyframeMetaStore._cache.pop(id(action), None)
            return empty
        cached = KeyframeMetaStore._cache.get(id(action))
        if cached is not None and cached[0] == raw:
            return cached[1]
        try:
            data = json.loads(raw)
        except Exception:
            return empty
        if not isinstance(data, dict):
            return empty
        data.setdefault("version", METADATA_VERSION)
        data.setdefault("protected", [])
        data.setdefault("pins", [])
        if not isinstance(data["protected"], list):
            data["protected"] = []
        if not isinstance(data["pins"], list):
            data["pins"] = []
        return KeyframeMetaStore._store(action, raw, data)

    @staticmethod
    def save(action, data):
        if action is None:
            return
        try:
            raw = json.dumps(data, separators=(",", ":"))
            action[METADATA_PROP_KEY] = raw
        except Exception as e:
            KeyHeavenLogger.log_warning(f"Metadata save note: {e}")
            return
        KeyframeMetaStore._store(action, raw, data)

    @staticmethod
    def protected_index(action):
        """Returns the protection modes indexed by key for fast lookups."""
        data = KeyframeMetaStore.load(action)
        cached = KeyframeMetaStore._cache.get(id(action))
        if cached is not None and cached[1] is data:
            return cached[2]
        return KeyframeMetaStore._build_indexes(data)[0]

    @staticmethod
    def pin_index(action):
        """Returns the pin identifiers indexed by key for fast lookups."""
        data = KeyframeMetaStore.load(action)
        cached = KeyframeMetaStore._cache.get(id(action))
        if cached is not None and cached[1] is data:
            return cached[3]
        return KeyframeMetaStore._build_indexes(data)[1]

    @staticmethod
    def _same_key(entry_path, entry_index, entry_frame, data_path, index, frame):
        if entry_path != data_path or int(entry_index) != int(index):
            return False
        return abs(float(entry_frame) - float(frame)) <= KEY_PROXIMITY_EPS

    @staticmethod
    def _drop_key(data, data_path, index, frame):
        data["protected"] = [
            entry
            for entry in data["protected"]
            if not KeyframeMetaStore._same_key(
                entry.get("p", ""), entry.get("i", -1), entry.get("f", 0.0),
                data_path, index, frame,
            )
        ]
        for pin in data["pins"]:
            keys = pin.get("keys", [])
            pin["keys"] = [
                key
                for key in keys
                if not KeyframeMetaStore._same_key(
                    key[0], key[1], key[2], data_path, index, frame
                )
            ]
        data["pins"] = [pin for pin in data["pins"] if pin.get("keys")]

    @staticmethod
    def prune(action, fcurves):
        data = KeyframeMetaStore.load(action)
        if not data["protected"] and not data["pins"]:
            return
        live = []
        for fc in fcurves:
            for kp in fc.keyframe_points:
                live.append((fc.data_path, fc.array_index, kp.co[0]))
        data["protected"] = [
            entry
            for entry in data["protected"]
            if any(
                KeyframeMetaStore._same_key(
                    entry.get("p", ""), entry.get("i", -1), entry.get("f", 0.0), path, index, frame
                )
                for path, index, frame in live
            )
        ]
        for pin in data["pins"]:
            pin["keys"] = [
                key
                for key in pin.get("keys", [])
                if any(
                    KeyframeMetaStore._same_key(key[0], key[1], key[2], path, index, frame)
                    for path, index, frame in live
                )
            ]
        data["pins"] = [pin for pin in data["pins"] if pin.get("keys")]
        KeyframeMetaStore.save(action, data)


class BoundaryLockEngine:
    """First/last keyframe anchors. Protected by default; can be disabled."""

    @staticmethod
    def is_enabled(context=None):
        try:
            props = context.scene.keyheaven
            return bool(getattr(props, "boundary_lock_enabled", True))
        except Exception:
            return True

    @staticmethod
    def get_boundary_frames(target, context=None):
        fcs = TargetResolver.get_target_fcurves(target, scope="TRANSFORM_ONLY")
        times = [kp.co[0] for fc in fcs for kp in fc.keyframe_points]
        if times:
            return min(times), max(times)
        if HAS_BPY and context and hasattr(context, "scene"):
            return float(context.scene.frame_start), float(context.scene.frame_end)
        return 1.0, 250.0

    @staticmethod
    def is_locked_boundary(frame_val, start_f, end_f, enabled=True):
        if not enabled:
            return False
        return (abs(frame_val - start_f) <= TIME_EPS) or (abs(frame_val - end_f) <= TIME_EPS)


class KeyframeProtectionEngine:
    """Semantic protection stored in Action metadata (never in Keyframe.type).

    BOTH   locks value and relative timing group.
    VALUE  locks value content, time position movable.
    TIMING locks relative time-group coherence, value movable.
    Pinned keys participate in the timing lock set as a temporal relationship.
    """

    MODES = ("BOTH", "VALUE", "TIMING", "NONE")

    @staticmethod
    def _resolve(fc, kp):
        action = KeyframeMetaStore.action_of(fc)
        if action is None or kp is None:
            return None, None
        return action, (fc.data_path, int(fc.array_index), round(float(kp.co[0]), TIME_ROUND))

    @staticmethod
    def _legacy_native_mode(kp):
        """Reads the protection state written by the 3.9.5 baseline.

        The 3.9.5 addon stored its protection state in the native keyframe
        type. It is only read here and never written, so the native types keep
        their Blender meaning.
        """
        if kp is None:
            return "NONE"
        native = getattr(kp, "type", "KEYFRAME")
        if native == "EXTREME":
            return "BOTH"
        if native == "MOVING_HOLD":
            return "VALUE"
        if native == "BREAKDOWN":
            return "TIMING"
        return "NONE"

    @staticmethod
    def get_protection_mode(fc, kp):
        action, key = KeyframeProtectionEngine._resolve(fc, kp)
        if action is None:
            return "NONE"
        index = KeyframeMetaStore.protected_index(action)
        mode = index.get(key)
        if mode is not None:
            return mode
        return KeyframeProtectionEngine._legacy_native_mode(kp)

    @staticmethod
    def set_protection_mode(fc, kp, mode="BOTH"):
        action, key = KeyframeMetaStore._resolve(fc, kp)
        if action is None:
            return
        data = KeyframeMetaStore.load(action)
        KeyframeMetaStore._drop_key(data, key[0], key[1], key[2])
        if mode in {"BOTH", "VALUE", "TIMING"}:
            data["protected"].append(
                {"p": key[0], "i": key[1], "f": round(key[2], TIME_ROUND), "m": mode}
            )
        KeyframeMetaStore.save(action, data)

    @staticmethod
    def is_value_locked(fc, kp):
        return KeyframeProtectionEngine.get_protection_mode(fc, kp) in {"BOTH", "VALUE"}

    @staticmethod
    def is_timing_locked(fc, kp):
        if KeyframeProtectionEngine.get_protection_mode(fc, kp) in {"BOTH", "TIMING"}:
            return True
        return PinsEngine.get_pin_id(fc, kp) is not None

    @staticmethod
    def mark_key_moved(fc, old_frame, new_frame):
        action = KeyframeMetaStore.action_of(fc)
        if action is None:
            return
        data = KeyframeMetaStore.load(action)
        changed = False
        for entry in data["protected"]:
            if KeyframeMetaStore._same_key(
                entry.get("p", ""), entry.get("i", -1), entry.get("f", 0.0),
                fc.data_path, fc.array_index, old_frame,
            ):
                entry["f"] = round(float(new_frame), TIME_ROUND)
                changed = True
        for pin in data["pins"]:
            for key in pin.get("keys", []):
                if KeyframeMetaStore._same_key(
                    key[0], key[1], key[2], fc.data_path, fc.array_index, old_frame
                ):
                    key[2] = round(float(new_frame), TIME_ROUND)
                    changed = True
        if changed:
            KeyframeMetaStore.save(action, data)

    @staticmethod
    def protect_selected_keyframes(context, mode="BOTH"):
        targets = TargetResolver.collect_active_targets(context, min_keyframes=1, filter_type="ALL")
        boundary_enabled = BoundaryLockEngine.is_enabled(context)
        count = 0
        for target in targets:
            start_f, end_f = BoundaryLockEngine.get_boundary_frames(target, context)
            for fc in TargetResolver.get_target_fcurves(target):
                for kp in fc.keyframe_points:
                    if not kp.select_control_point:
                        continue
                    if BoundaryLockEngine.is_locked_boundary(
                        kp.co[0], start_f, end_f, boundary_enabled
                    ):
                        KeyframeProtectionEngine.set_protection_mode(fc, kp, "BOTH")
                    else:
                        KeyframeProtectionEngine.set_protection_mode(fc, kp, mode)
                    count += 1
        return count

    @staticmethod
    def unprotect_selected_keyframes(context):
        targets = TargetResolver.collect_active_targets(context, min_keyframes=1, filter_type="ALL")
        boundary_enabled = BoundaryLockEngine.is_enabled(context)
        count = 0
        for target in targets:
            start_f, end_f = BoundaryLockEngine.get_boundary_frames(target, context)
            for fc in TargetResolver.get_target_fcurves(target):
                for kp in fc.keyframe_points:
                    if not kp.select_control_point:
                        continue
                    if BoundaryLockEngine.is_locked_boundary(
                        kp.co[0], start_f, end_f, boundary_enabled
                    ):
                        continue
                    KeyframeProtectionEngine.set_protection_mode(fc, kp, "NONE")
                    count += 1
        return count

    @staticmethod
    def identify_temporal_clusters(timestamps, time_locked_set):
        sorted_ts = sorted(list(timestamps))
        units = []
        current_cluster = []

        for stamp in sorted_ts:
            if stamp in time_locked_set:
                current_cluster.append(stamp)
            else:
                if current_cluster:
                    units.append(("CLUSTER", list(current_cluster)))
                    current_cluster = []
                units.append(("FREE", stamp))

        if current_cluster:
            units.append(("CLUSTER", list(current_cluster)))

        return units


class PinsEngine:
    """Pins are temporal relationships: a group of related keys moves as a unit."""

    @staticmethod
    def get_pin_id(fc, kp):
        action = KeyframeMetaStore.action_of(fc)
        if action is None or kp is None:
            return None
        index = KeyframeMetaStore.pin_index(action)
        key = (
            fc.data_path,
            int(fc.array_index),
            round(float(kp.co[0]), TIME_ROUND),
        )
        return index.get(key)

    @staticmethod
    def pin_selected_keyframes(context, targets=None):
        selected = []
        if targets is None:
            targets = TargetResolver.collect_active_targets(
                context, min_keyframes=1, filter_type="ALL"
            )
        for target in targets:
            for fc in TargetResolver.get_target_fcurves(target):
                for kp in fc.keyframe_points:
                    if kp.select_control_point:
                        selected.append((fc, kp))
        if not selected:
            return 0

        pin_id = uuid.uuid4().hex[:12]
        grouped = {}
        for fc, kp in selected:
            action = KeyframeMetaStore.action_of(fc)
            if action is None:
                continue
            grouped.setdefault(action, []).append((fc, kp))

        count = 0
        for action, items in grouped.items():
            data = KeyframeMetaStore.load(action)
            keys = []
            for fc, kp in items:
                key = [fc.data_path, int(fc.array_index), round(float(kp.co[0]), TIME_ROUND)]
                if not any(existing == key for existing in keys):
                    keys.append(key)
                count += 1
            data["pins"].append({"id": pin_id, "keys": keys})
            KeyframeMetaStore.save(action, data)
        return count

    @staticmethod
    def unpin_selected_keyframes(context):
        count = 0
        targets = TargetResolver.collect_active_targets(context, min_keyframes=1, filter_type="ALL")
        for target in targets:
            for fc in TargetResolver.get_target_fcurves(target):
                for kp in fc.keyframe_points:
                    if not kp.select_control_point:
                        continue
                    action = KeyframeMetaStore.action_of(fc)
                    if action is None:
                        continue
                    data = KeyframeMetaStore.load(action)
                    for pin in data["pins"]:
                        original = len(pin.get("keys", []))
                        pin["keys"] = [
                            key
                            for key in pin.get("keys", [])
                            if not KeyframeMetaStore._same_key(
                                key[0], key[1], key[2], fc.data_path, fc.array_index, kp.co[0]
                            )
                        ]
                        if len(pin["keys"]) != original:
                            count += 1
                    data["pins"] = [pin for pin in data["pins"] if pin.get("keys")]
                    KeyframeMetaStore.save(action, data)
        return count
