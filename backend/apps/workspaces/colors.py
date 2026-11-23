"""The widget colors a workspace can choose from.

A short list instead of any color, so the widget always looks right: it puts white text on
the color and uses the color for text on white, and each of these is readable both ways
(tests/test_colors.py checks the contrast). The dashboard shows the same list
(frontend/src/lib/colors.ts; a test there keeps the two equal).
"""

WIDGET_COLORS = {
    "#2563eb": "Blue",
    "#0369a1": "Ocean",
    "#4f46e5": "Indigo",
    "#7c3aed": "Violet",
    "#a21caf": "Plum",
    "#be185d": "Pink",
    "#dc2626": "Red",
    "#c2410c": "Orange",
    "#b45309": "Amber",
    "#15803d": "Green",
    "#0f766e": "Teal",
    "#1f2937": "Charcoal",
}
DEFAULT_COLOR = "#2563eb"
