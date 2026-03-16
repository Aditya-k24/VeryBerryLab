"""
app.py — VeryBerryLab Dashboard
================================
Multi-page Dash application for strawberry phenotyping analysis.

Run from the veryberrylab/ directory:
    python3 app.py

Then open:  http://localhost:5001
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dash
from dash import Dash, Input, Output, dcc, html

import src.data_cache as cache

# ---------------------------------------------------------------------------
# Load data before anything else
# ---------------------------------------------------------------------------
cache.initialize()

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = Dash(
    __name__,
    use_pages=True,
    suppress_callback_exceptions=True,
    title="VeryBerryLab",
)
server = app.server  # expose Flask server for WSGI if needed

NAV_ITEMS = [
    {"label": "Data Health",     "href": "/"},
    {"label": "Trait Explorer",  "href": "/trait-explorer"},
    {"label": "Date Compare",    "href": "/date-compare"},
    {"label": "Season Summary",  "href": "/season-summary"},
    {"label": "Plant Animation", "href": "/plant-animation"},
    {"label": "Export & Methods","href": "/export"},
]

app.layout = html.Div(
    className="app-wrapper",
    children=[
        dcc.Location(id="url", refresh=False),

        # ── Left sidebar ──────────────────────────────────────────────────
        html.Aside(
            className="sidebar",
            children=[
                html.Div(className="brand", children=[
                    html.Span("VeryBerry", className="brand-berry"),
                    html.Span("Lab",       className="brand-lab"),
                ]),
                html.Div(className="batch-badge-row", children=[
                    html.Span("Batch A", className="badge badge-a"),
                    html.Span("Batch B", className="badge badge-b"),
                ]),
                html.Nav(
                    className="nav",
                    children=[
                        dcc.Link(
                            item["label"],
                            href=item["href"],
                            className="nav-link",
                            id={"type": "nav-link", "index": i},
                        )
                        for i, item in enumerate(NAV_ITEMS)
                    ],
                ),
                html.Div(className="sidebar-footer", children=[
                    html.Span("Pheno 4 · 2025", className="sidebar-meta"),
                    html.Span("11 cvs · 12 dates", className="sidebar-meta"),
                ]),
            ],
        ),

        # ── Main content ──────────────────────────────────────────────────
        html.Main(
            className="main-content",
            children=[dash.page_container],
        ),
    ],
)


# ---------------------------------------------------------------------------
# Active nav highlight
# ---------------------------------------------------------------------------
@app.callback(
    Output({"type": "nav-link", "index": dash.ALL}, "className"),
    Input("url", "pathname"),
)
def highlight_nav(pathname):
    classes = []
    for item in NAV_ITEMS:
        if pathname == item["href"]:
            classes.append("nav-link active")
        elif item["href"] != "/" and pathname and pathname.startswith(item["href"]):
            classes.append("nav-link active")
        else:
            classes.append("nav-link")
    return classes


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print()
    print("  ╔══════════════════════════════════════════════════╗")
    print("  ║  VeryBerryLab — Phenotyping Dashboard            ║")
    print("  ║  Open  →  http://localhost:5001                  ║")
    print("  ╚══════════════════════════════════════════════════╝")
    print()
    app.run(debug=False, port=5001, host="0.0.0.0")
