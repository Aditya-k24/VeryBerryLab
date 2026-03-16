"""
app.py — VeryBerryLab Analytics Dashboard
==========================================
Multi-page Dash application for strawberry phenotyping analysis.

Run from the Analytics/ directory:
    python3 app.py

Then open:  http://localhost:5001
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import src.data_cache as cache
cache.initialize()

import dash
from dash import Dash, Input, Output, dcc, html

app = Dash(
    __name__,
    use_pages=True,
    suppress_callback_exceptions=True,
    title="VeryBerryLab",
)
server = app.server

NAV = [
    {"label": "Data Health",      "href": "/"},
    {"label": "Trait Explorer",   "href": "/trait-explorer"},
    {"label": "Date Compare",     "href": "/date-compare"},
    {"label": "Season Summary",   "href": "/season-summary"},
    {"label": "Plant Animation",  "href": "/plant-animation"},
    {"label": "Export & Methods", "href": "/export"},
]

app.layout = html.Div(className="app-wrapper", children=[
    dcc.Location(id="url", refresh=False),

    # Sidebar
    html.Aside(className="sidebar", children=[
        html.Div(className="brand", children=[
            html.Span("VeryBerry", className="brand-berry"),
            html.Span("Lab",       className="brand-lab"),
        ]),
        html.Div(className="batch-badges", children=[
            html.Span("Batch A", className="badge badge-a"),
            html.Span("Batch B", className="badge badge-b"),
        ]),
        html.Nav(className="nav", children=[
            dcc.Link(item["label"], href=item["href"],
                     className="nav-link",
                     id={"type": "nav-link", "index": i})
            for i, item in enumerate(NAV)
        ]),
        html.Div(className="sidebar-footer", children=[
            html.Span("Pheno 4 · 2025",    className="sidebar-meta"),
            html.Span("11 cvs · 12 dates", className="sidebar-meta"),
        ]),
    ]),

    # Main
    html.Main(className="main-content", children=[dash.page_container]),
])


@app.callback(
    Output({"type": "nav-link", "index": dash.ALL}, "className"),
    Input("url", "pathname"),
)
def highlight_nav(pathname):
    out = []
    for item in NAV:
        if pathname == item["href"]:
            out.append("nav-link active")
        elif item["href"] != "/" and pathname and pathname.startswith(item["href"]):
            out.append("nav-link active")
        else:
            out.append("nav-link")
    return out


if __name__ == "__main__":
    print()
    print("  ╔══════════════════════════════════════════════════╗")
    print("  ║  VeryBerryLab — Phenotyping Dashboard            ║")
    print("  ║  Open  →  http://localhost:5001                  ║")
    print("  ╚══════════════════════════════════════════════════╝")
    print()
    app.run(debug=False, port=5001, host="0.0.0.0")
