from .._imports import *
from .logger import *
TIME_ROUND = 5
TIME_EPS = 1e-5
KEY_PROXIMITY_EPS = 0.005

TRANSFORM_CHANNELS = {
    "location",
    "rotation_euler",
    "rotation_quaternion",
    "scale",
}

METADATA_PROP_KEY = "_kh_meta"
METADATA_VERSION = 1

BASE_PROP_KEY = "_kh_base_action_ptr"

OP_ID_PROP = "_kh_last_op_id"
OP_SNAPSHOT_PROP = "_kh_op_snapshot"
OP_SNAPSHOT_SUFFIX = ".kh_opsnap"

ID_TYPE_BY_CLASS = {
    "Object": "OBJECT",
    "Key": "KEY",
    "Material": "MATERIAL",
    "NodeTree": "NODETREE",
    "Mesh": "MESH",
    "Scene": "SCENE",
    "World": "WORLD",
}


def slot_target_id_type(datablock):
    if datablock is None:
        return "OBJECT"
    return ID_TYPE_BY_CLASS.get(type(datablock).__name__, type(datablock).__name__.upper())


def clamp_value(value, low, high):
    """Clamps a value inside the given range."""
    if value < low:
        return low
    if value > high:
        return high
    return value


def normalise_quaternion(values):
    """Normalises a quaternion given as ``(w, x, y, z)``."""
    length = math.sqrt(sum(component * component for component in values))
    if length < 1e-9:
        return (1.0, 0.0, 0.0, 0.0)
    return tuple(component / length for component in values)


def multiply_quaternions(first, second):
    """Multiplies two quaternions given as ``(w, x, y, z)``."""
    w0, x0, y0, z0 = first
    w1, x1, y1, z1 = second
    return (
        w0 * w1 - x0 * x1 - y0 * y1 - z0 * z1,
        w0 * x1 + x0 * w1 + y0 * z1 - z0 * y1,
        w0 * y1 - x0 * z1 + y0 * w1 + z0 * x1,
        w0 * z1 + x0 * y1 - y0 * x1 + z0 * w1,
    )
