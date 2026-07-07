"""
src/ui.py
=========
Shared UI constants for the Dash pages.
"""

# Publication-ready Plotly config: always-visible toolbar, no plotly logo,
# and the camera button exports a vector SVG (scale 2) suitable for papers.
# SVG opens/edits in Illustrator/Inkscape and converts losslessly to PDF.
GRAPH_CONFIG = {
    "displayModeBar": True,
    "displaylogo": False,
    "toImageButtonOptions": {
        "format": "svg",
        "filename": "veryberry_chart",
        "scale": 2,
    },
}
