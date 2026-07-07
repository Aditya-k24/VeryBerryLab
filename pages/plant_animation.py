"""
pages/plant_animation.py — Page 5: Plant Growth Animation

Top-down stolon tree driven by Worksheet 1 temporal data.
Worksheet 3 provides the structural tree (internode lengths).
Worksheet 1 provides the date-by-date growth timeline.

Layout: cultivar + mother controls, then a self-contained iframe
that handles all playback (play/pause, date scrubber, data table).
"""

import dash
import pandas as pd
from dash import Input, Output, callback, dash_table, dcc, html

import src.data_cache as cache
from src.plant_arch import build_js_html, plant_summary, validate_render, _empty_html

dash.register_page(__name__, path="/plant-animation", name="Plant Animation", order=4)

# Worksheet-1 measurement columns shown in the state table (key → label)
_STATE_COLS = [
    ("stolon_length",   "Stolon length (cm)"),
    ("sec_stolon",      "Sec stolons"),
    ("sec_daughters",   "Sec daughters"),
    ("ter_stolon",      "Ter stolons"),
    ("ter_daughters",   "Ter daughters"),
    ("quart_stolon",    "Qrt stolons"),
    ("quart_daughters", "Qrt daughters"),
]


def _state_table(cultivar, mid, date):
    """Per-plantlet Worksheet 1 measurements for one cultivar/mother/date."""
    ws1_cv = cache.ws1_data.get(cultivar, {})
    plants = ws1_cv.get("plants", {})
    codes = sorted(
        c for c in ws1_cv.get("codes_by_date", {}).get(date, [])
        if c.split(".")[0] == str(mid)           # code starts with the mother id
    )
    rows = []
    for c in codes:
        rec = plants.get(c, {}).get(date)
        if not rec:
            continue
        row = {"code": c}
        row.update({k: rec.get(k) for k, _ in _STATE_COLS})
        rows.append(row)

    if not rows:
        return html.Div(
            f"No plantlet measurements recorded for M{mid} on "
            f"{pd.Timestamp(date).strftime('%d %b %Y')}.",
            className="stats-empty",
        )

    # keep only columns that carry at least one real (non-zero, non-null) value
    active = [(k, lbl) for k, lbl in _STATE_COLS
              if any(r.get(k) not in (None, 0) for r in rows)]
    columns = [{"name": "Code", "id": "code"}] + \
              [{"name": lbl, "id": k} for k, lbl in active]
    keep = ["code"] + [k for k, _ in active]
    data = [{k: r.get(k) for k in keep} for r in rows]

    return html.Div([
        html.P(
            f"M{mid} · {pd.Timestamp(date).strftime('%d %b %Y')} · "
            f"{len(rows)} plantlet{'s' if len(rows) != 1 else ''} measured",
            className="card-subtitle",
        ),
        dash_table.DataTable(
            columns=columns, data=data,
            sort_action="native", export_format="csv",
            export_headers="display", page_size=15,
            style_table={"overflowX": "auto"},
            style_cell={"fontFamily": "Inter, sans-serif", "fontSize": "12px",
                        "padding": "6px 10px", "textAlign": "left"},
            style_header={"fontWeight": "600", "backgroundColor": "#f0ebe3",
                          "border": "none"},
            style_data={"border": "none", "borderBottom": "1px solid #f0ebe3"},
            style_cell_conditional=[{"if": {"column_id": "code"},
                                     "fontWeight": "600", "color": "#3e5c29"}],
        ),
    ])

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
            "Top-down architecture flowing like a root system: the mother crown "
            "sits at the top and runners branch downward, thick near the crown "
            "and tapering to fine tips. Daughter plantlets root at their encoded "
            "stolon/node positions. Structure from Worksheet 3, growth timeline "
            "from Worksheet 1. Amber ring = rooted this date.",
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

    # ── Bottom half: pick a date, see that state's measurements ───────────────
    html.Div(className="card", children=[
        html.H3("State Data — measurements on a date", className="card-title"),
        html.Div(className="filter-row", children=[
            html.Label("Date", className="filter-label"),
            dcc.Dropdown(id="pa2-date", clearable=False, style={"width": "220px"}),
        ]),
        html.P("Per-plantlet Worksheet 1 measurements for the selected cultivar, "
               "mother, and date. Click a header to sort; use Export for CSV.",
               className="card-subtitle"),
        dcc.Loading(html.Div(id="pa2-state")),
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
    Output("pa2-date", "options"),
    Output("pa2-date", "value"),
    Input("pa2-cv", "value"),
)
def upd_date_options(cultivar):
    dates = cache.ws1_data.get(cultivar, {}).get("dates", []) if cultivar else []
    opts = [{"label": pd.Timestamp(d).strftime("%d %b %Y"), "value": d} for d in dates]
    return opts, (dates[-1] if dates else None)


@callback(
    Output("pa2-state", "children"),
    Input("pa2-cv", "value"),
    Input("pa2-mother", "value"),
    Input("pa2-date", "value"),
)
def upd_state(cultivar, mother_id, date):
    if not cultivar or not date:
        return html.Div("Select a cultivar and date.", className="stats-empty")
    return _state_table(cultivar, mother_id or 1, date)


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

    # Validate the rendered tree reproduces parsed counts exactly
    code_first_date: dict = {}
    for idx, d in enumerate(dates):
        for code in ws1_cv.get("codes_by_date", {}).get(d, []):
            code_first_date.setdefault(code, idx)
    v = validate_render(plant, mid, code_first_date, len(dates))
    check = ("✓ render matches data" if v["ok"] else
             f"⚠ render/data mismatch (dp {v['rendered_daughters']}/{v['parsed_daughters']}, "
             f"stolons {v['rendered_stolons']}/{v['parsed_stolons']})")

    status = (
        f"M{mid}: {s['daughters']} DPs · {s['stolons']} stolons · "
        f"{len(dates)} dates · {n_codes} plant-date observations · {check}"
    )
    return html_str, status
