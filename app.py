"""
app.py — VeryBerryLab Analytics Dashboard
==========================================
Multi-page Dash application for strawberry phenotyping analysis.

Run from the Analytics/ directory:
    python3 app.py

Then open:  http://localhost:5001
"""

import sys
import urllib.parse
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
    title="VeryBerryLab — Phenotyping Analytics",
    external_stylesheets=[
        "https://fonts.googleapis.com/css2?"
        "family=IBM+Plex+Serif:wght@500;600;700&"
        "family=IBM+Plex+Sans:wght@400;500;600;700&"
        "family=IBM+Plex+Mono:wght@400;500;600&display=swap",
    ],
)
server = app.server


# ── Line-icon helper (SVG → CSS mask data-URI, recolourable via currentColor) ──
def _icon(inner: str) -> str:
    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' "
        "stroke='black' stroke-width='1.8' stroke-linecap='round' "
        f"stroke-linejoin='round'>{inner}</svg>"
    )
    return "url(\"data:image/svg+xml," + urllib.parse.quote(svg) + "\")"


ICONS = {
    "health":  _icon("<rect x='3' y='3' width='7' height='7' rx='1'/><rect x='14' y='3' width='7' height='7' rx='1'/><rect x='3' y='14' width='7' height='7' rx='1'/><rect x='14' y='14' width='7' height='7' rx='1'/>"),
    "trait":   _icon("<path d='M3 3v18h18'/><path d='M7 14l4-5 3 3 5-7'/>"),
    "plant":   _icon("<path d='M12 21V9'/><path d='M12 9c0-3.3 2.7-6 6-6 0 3.3-2.7 6-6 6z'/><path d='M12 13c0-2.8-2.2-5-5-5 0 2.8 2.2 5 5 5z'/>"),
    "compare": _icon("<path d='M12 3v18'/><path d='M3 7h18'/><path d='M7 7l-3 6a3 3 0 006 0z'/><path d='M17 7l3 6a3 3 0 01-6 0z'/>"),
    "season":  _icon("<rect x='3' y='4' width='18' height='17' rx='2'/><path d='M3 9h18M8 2v4M16 2v4'/>"),
    "batch":   _icon("<path d='M12 2l9 5-9 5-9-5 9-5z'/><path d='M3 12l9 5 9-5'/><path d='M3 17l9 5 9-5'/>"),
    "export":  _icon("<path d='M12 3v12'/><path d='M7 10l5 5 5-5'/><path d='M4 21h16'/>"),
}

# Grouped navigation — (section label, [(label, href, icon_key), ...])
NAV_GROUPS = [
    ("Explore", [
        ("Data Health",     "/",                "health"),
        ("Trait Explorer",  "/trait-explorer",  "trait"),
        ("Plant Animation", "/plant-animation", "plant"),
    ]),
    ("Analyze", [
        ("Date Compare",    "/date-compare",    "compare"),
        ("Season Summary",  "/season-summary",  "season"),
        ("Cross-Batch",     "/cross-batch",     "batch"),
    ]),
    ("Export", [
        ("Export & Methods", "/export",         "export"),
    ]),
]
# flat list drives the highlight callback (index-stable)
NAV = [item for _, items in NAV_GROUPS for item in items]


# ── Dataset context for the top bar ──
def _dataset_meta():
    df = cache.df_clean
    if df is None or df.empty:
        return "Phenotyping dataset", ""
    n_cv = df["cultivar"].nunique()
    n_obs = len(df)
    d0, d1 = df["date"].min(), df["date"].max()
    span = f"{d0.strftime('%b %Y')} – {d1.strftime('%b %Y')}"
    return "Phenotyping Batch 4", f"{n_cv} cultivars · {n_obs} observations · {span}"


_TITLE, _META = _dataset_meta()


def _nav_link(label, href, icon_key, idx):
    return dcc.Link(
        href=href, className="nav-link",
        id={"type": "nav-link", "index": idx},
        children=[
            html.Span(className="nav-ico", style={"--i": ICONS.get(icon_key, "")}),
            html.Span(label, className="nav-txt"),
        ],
    )


app.layout = html.Div(className="app-wrapper", children=[
    dcc.Location(id="url", refresh=False),

    # ── Sidebar ──────────────────────────────────────────────────────────
    html.Aside(className="sidebar", children=[
        html.Div(className="brand", children=[
            html.Div(className="brand-mark", children="🍓"),
            html.Div(children=[
                html.Span("VeryBerry", className="brand-berry"),
                html.Span("Lab", className="brand-lab"),
                html.Div("Phenotyping Analytics", className="brand-sub"),
            ]),
        ]),
        html.Div(className="batch-badges", children=[
            html.Span("Batch A", className="badge badge-a"),
            html.Span("Batch B", className="badge badge-b"),
        ]),
        html.Nav(className="nav", children=[
            child
            for gi, (group, items) in enumerate(NAV_GROUPS)
            for child in (
                [html.Div(group, className="nav-group")] +
                [_nav_link(lbl, href, ic,
                           sum(len(g[1]) for g in NAV_GROUPS[:gi]) + j)
                 for j, (lbl, href, ic) in enumerate(items)]
            )
        ]),
        html.Div(className="sidebar-footer", children=[
            html.Span("Pheno 1–5 · 2024–2026", className="sidebar-meta"),
            html.Span("v2 · research build", className="sidebar-meta"),
        ]),
    ]),

    # ── Main column ──────────────────────────────────────────────────────
    html.Div(className="main-col", children=[
        html.Header(className="topbar", children=[
            html.Div(className="topbar-context", children=[
                html.Span(_TITLE, className="topbar-title"),
                html.Span("•", className="topbar-dot"),
                html.Span(_META, className="topbar-meta"),
            ]),
            html.Div(className="topbar-actions", children=[
                html.A("Methods", href="/export", className="topbar-link"),
            ]),
        ]),
        html.Main(className="main-content", children=[dash.page_container]),
    ]),
])


@app.callback(
    Output({"type": "nav-link", "index": dash.ALL}, "className"),
    Input("url", "pathname"),
)
def highlight_nav(pathname):
    out = []
    for _, href, _ in NAV:
        if pathname == href:
            out.append("nav-link active")
        elif href != "/" and pathname and pathname.startswith(href):
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
