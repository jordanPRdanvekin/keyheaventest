from .._imports import *
KEYHEAVEN_WORKFLOW_STEPS = (
    "1. Select animated objects or pose bones.",
    "2. Capture Base before destructive edits.",
    "3. Apply tools; boundaries, locks and temporal pins persist.",
    "4. Use Restore Base to return to the source of truth.",
)


def draw_workflow_help(layout):
    column = layout.column(align=True)
    for step in KEYHEAVEN_WORKFLOW_STEPS:
        column.label(text=step, icon="DOT")
