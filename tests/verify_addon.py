import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import bpy  # noqa: E402

import keyheaven  # noqa: E402

print("KeyHeaven version:", keyheaven.KEYHEAVEN_VERSION_LABEL)
print("Blender version:", bpy.app.version_string)

keyheaven.register()
print("Registered OK")

# Basic sanity: Scene property exists
assert hasattr(bpy.types.Scene, "keyheaven"), "Scene.keyheaven missing"
print("Scene.keyheaven OK")

keyheaven.unregister()
print("Unregistered OK")
print("VERIFY PASS")