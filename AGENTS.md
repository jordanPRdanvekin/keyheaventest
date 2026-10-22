# KeyHeaven — Blender 5.2 add-on (modular package)

Runtime artifact is the `keyheaven/` package (not a single file). Install by zipping its *contents* (`__init__.py` + `blender_manifest.toml` + subpackages) for drag-and-drop.

## Structure
- `keyheaven/` — installable add-on package
  - `_imports.py` — shared imports + `HAS_BPY` guard (dummy bpy when unavailable)
  - `core/` — pure logic (RNG, curves, chains, spatial, sanitize, etc.)
  - `operators/` — `bpy.types.Operator` classes (`ops.py`)
  - `ui/` — panels, gizmos, tooltips, context menus
  - `properties.py` — `KeyHeaven_Properties` PropertyGroup
  - `_registration.py` — class list + register/unregister
- `tests/verify_addon.py` — non-interactive Blender check

## Verification (no Blender needed)
- `python -m py_compile keyheaven/**/*.py`
- `python -c "import keyheaven; print(keyheaven.HAS_BPY)"`
- Manifest: `python -c "import tomllib; tomllib.load(open('keyheaven/blender_manifest.toml','rb'))"`

## With Blender 5.2
- `blender --background --python tests/verify_addon.py`

## Conventions
- Do not edit generated monoliths; source is the modular package.
- Keep `HAS_BPY` guard so static import works without bpy.
- Register classes in `_registration.classes`; unregister in reverse order; `del bpy.types.Scene.keyheaven` before unregistering `KeyHeaven_Properties`.
- F-Curves only via `core.actions_compat` (slotted actions); never `Action.fcurves`.
- RNG must stay deterministic (seed-based).
- Clean `__pycache__` before committing.