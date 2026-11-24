"""The widget colors a workspace can choose from.

A short list instead of any color, so the widget always looks right: it puts white text on
a deep color and dark text on a bright one, and darkens a bright one for text on white
(frontend/src/lib/contrast.ts; frontend/tests/colors.test.ts checks every color is readable). The dashboard shows the same list
(frontend/src/lib/colors.ts; a test there keeps the two equal).
"""

WIDGET_COLORS = {
    "#2563eb": "Blue",
    "#0369a1": "Ocean",
    "#4f46e5": "Indigo",
    "#7c3aed": "Violet",
    "#a21caf": "Plum",
    "#be185d": "Rose",
    "#dc2626": "Red",
    "#c2410c": "Orange",
    "#b45309": "Amber",
    "#15803d": "Green",
    "#0f766e": "Teal",
    "#1f2937": "Charcoal",
    "#22d3ee": "Cyan",
    "#86efac": "Light green",
    "#f472b6": "Pink",
    "#39ff14": "Neon green",
}
DEFAULT_COLOR = "#2563eb"
