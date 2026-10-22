bl_info = {
    "name": "KeyHeaven (Procedural Animation Engine)",
    "author": "Pipeline Technical Direction",
    "version": (4, 0, 0),
    "blender": (5, 2, 0),
    "location": "View3D > Sidebar (N) > KeyHeaven | Graph Editor > Context Menu",
    "description": "Production-hardened procedural animation engine for Blender 5.x",
    "category": "Animation",
}

from ._imports import *
from . import core
from . import properties
from . import operators
from . import ui
from . import presets
from . import _registration

def register():
    if not HAS_BPY:
        return
    if hasattr(properties, "register"):
        properties.register()
    if hasattr(operators, "register"):
        operators.register()
    if hasattr(ui, "register"):
        ui.register()
    _registration.register()

def unregister():
    if not HAS_BPY:
        return
    _registration.unregister()
    if hasattr(ui, "unregister"):
        ui.unregister()
    if hasattr(operators, "unregister"):
        operators.unregister()
    if hasattr(properties, "unregister"):
        properties.unregister()

if __name__ == "__main__":
    register()