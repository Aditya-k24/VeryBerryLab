"""
pages/plant_animation.py — Page 5: Plant Growth Animation

Top-down stolon tree driven by Worksheet 1 temporal data.
Worksheet 3 provides the structural tree (internode lengths).
Worksheet 1 provides the date-by-date growth timeline.

Layout: cultivar + mother controls, then a self-contained iframe
that handles all playback (play/pause, date scrubber, data table).
"""

import dash
from dash import Input, Output, callback, dcc, html

import src.data_cache as cache
from src.plant_arch import build_js_html, plant_summary, _empty_html

dash.register_page(__name__, path="/plant-animation", name="Plant Animation", order=4)

# ── Cultivar list ─────────────────────────────────────────────────────────────

_DEFAULT_CV = "Radiance"

def _cv_options():
    """Build dropdown options from whichever cultivars have both WS1 and WS3 data."""
    ws3 = cache.ws3_plants
    ws1 = cache.ws1_data
    both = sorted(set(ws3) & set(ws1)) or sorted(ws3) or sorted(ws1) or [_DEFAULT_CV]
    return [{"label": cv, "value": cv} for cv in both], both[0]


# ── Layout ────────────────────────────────────────────────────────────────────

layout = html.Div([
    html.Div(className="page-header", children=[
        html.H1("Plant Growth Animation", className="page-title"),
        html.P(
            "Top-down stolon network grown date-by-date from Worksheet 1 measurements. "
            "Tree structure from Worksheet 3. × = node, ○ = daughter plant. "
            "Amber = new this date.",
            className="page-subtitle",
        ),
    ]),

    html.Div(className="card filter-card", children=[
        html.Div(className="filter-row", children=[
            html.Div([
                html.Label("Cultivar", className="filter-label"),
                dcc.Dropdown(
                    id="pa2-cv",
                    options=[],          # populated by callback
                    value=None,
                    clearable=False,
                    style={"width": "200px"},
                ),
            ]),
            html.Div([
                html.Label("Mother plant", className="filter-label"),
                dcc.RadioItems(
                    id="pa2-mother",
                    options=[
                        {"label": "  M1", "value": 1},
                        {"label": "  M2", "value": 2},
                        {"label": "  M3", "value": 3},
                    ],
                    value=1,
                    inline=True,
                    inputStyle={"marginLeft": "12px"},
                    style={"display": "flex", "alignItems": "center", "gap": "4px"},
                ),
            ]),
            html.Div(id="pa2-status", style={"fontSize": "12px", "color": "#666",
                                              "alignSelf": "center"}),
        ]),
    ]),

    html.Div(className="card", style={"padding": "0", "overflow": "hidden"}, children=[
        html.Iframe(
            id="pa2-iframe",
            srcDoc=_empty_html("Select a cultivar to begin."),
            style={
                "width":   "100%",
                "height":  "760px",
                "border":  "none",
                "display": "block",
            },
        ),
    ]),
])


# ── Callbacks ─────────────────────────────────────────────────────────────────

@callback(
    Output("pa2-cv", "options"),
    Output("pa2-cv", "value"),
    Input("pa2-cv", "id"),          # fires once on page load
)
def init_dropdown(_):
    opts, default = _cv_options()
    return opts, default


@callback(
    Output("pa2-iframe", "srcDoc"),
    Output("pa2-status", "children"),
    Input("pa2-cv", "value"),
    Input("pa2-mother", "value"),
)
def update_animation(cultivar, mother_id):
    if not cultivar:
        return _empty_html("Select a cultivar."), ""

    ws3 = cache.ws3_plants
    ws1 = cache.ws1_data

    plant   = ws3.get(cultivar)
    ws1_cv  = ws1.get(cultivar, {})

    if plant is None and not ws1_cv:
        msg = f"No Worksheet 3 or Worksheet 1 data found for {cultivar}."
        return _empty_html(msg), f"⚠ {msg}"

    if plant is None:
        msg = f"Worksheet 3 data not found for {cultivar}. Cannot build tree structure."
        return _empty_html(msg), f"⚠ {msg}"

    if not ws1_cv:
        msg = f"Worksheet 1 data not found for {cultivar}. No temporal timeline."
        return _empty_html(msg), f"⚠ {msg}"

    # Resolve mother_id — fall back to first available
    mid = mother_id or 1
    if mid not in plant.mother_ids() and plant.mother_ids():
        mid = plant.mother_ids()[0]

    html_str = build_js_html(plant, ws1_cv, mid, canvas_w=900, canvas_h=480)

    # Status line
    s = plant_summary(plant, mid)
    dates = ws1_cv.get("dates", [])
    n_codes = sum(len(ws1_cv.get("codes_by_date", {}).get(d, [])) for d in dates)
    status = (
        f"M{mid}: {s['daughters']} DPs · {s['stolons']} stolons · "
        f"{len(dates)} dates · {n_codes} plant-date observations"
    )
    return html_str, status
