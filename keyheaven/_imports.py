"""Common imports shared by all KeyHeaven modules (Blender 5.x)."""
from __future__ import annotations

import bisect
import json
import math
import os
import random
import sys
import time
import traceback
import uuid
import zlib

try:
    import bpy
    import mathutils
    from mathutils import Vector, Matrix, Quaternion, Euler
    from mathutils.bvhtree import BVHTree
    import bpy_extras
    from bpy_extras import anim_utils
    from bpy_extras import view3d_utils

    HAS_BPY = True
except ImportError:
    import types as _types
    HAS_BPY = False

    class _BpyTypes:
        PropertyGroup = object
        Operator = object
        Panel = object
        Menu = object
        Gizmo = object
        GizmoGroup = object
        Scene = object

    class _BpyProps:
        @staticmethod
        def FloatProperty(*a, **k): return None
        @staticmethod
        def IntProperty(*a, **k): return None
        @staticmethod
        def BoolProperty(*a, **k): return None
        @staticmethod
        def EnumProperty(*a, **k): return None
        @staticmethod
        def PointerProperty(*a, **k): return None
        @staticmethod
        def StringProperty(*a, **k): return None

    class _BpyUtils:
        @staticmethod
        def register_class(*a, **k): return None
        @staticmethod
        def unregister_class(*a, **k): return None

    bpy = _types.SimpleNamespace(
        types=_BpyTypes,
        props=_BpyProps,
        utils=_BpyUtils,
        app=_types.SimpleNamespace(version=(0, 0, 0), version_string="0.0.0", online_access=False),
        context=None,
        data=None,
        ops=None,
    )
    mathutils = _types.SimpleNamespace()
    Vector = lambda *a, **k: None
    Matrix = lambda *a, **k: None
    Quaternion = lambda *a, **k: None
    Euler = lambda *a, **k: None
    BVHTree = None
    bpy_extras = _types.SimpleNamespace()
    anim_utils = _types.SimpleNamespace()
    view3d_utils = _types.SimpleNamespace()

KEYHEAVEN_VERSION = (4, 0, 0)
KEYHEAVEN_VERSION_LABEL = "4.0.0"
TIME_EPS = 1e-6
KEY_PROXIMITY_EPS = 1e-4
TIME_ROUND = 6