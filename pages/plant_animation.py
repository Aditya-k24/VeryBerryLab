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


def _state_table(cultivar, date):
    """All per-plantlet Worksheet 1 measurements for a cultivar. `date` may be
    a single ISO date or "all" (every measurement date). Rows cover all mothers;
    a Mother column identifies each."""
    ws1_cv = cache.ws1_data.get(cultivar, {})
    plants = ws1_cv.get("plants", {})
    all_dates = ws1_cv.get("dates", [])
    sel_dates = all_dates if date in (None, "all") else [date]
    show_date = date in (None, "all")

    rows = []
    for d in sel_dates:
        for c in sorted(ws1_cv.get("codes_by_date", {}).get(d, [])):
            rec = plants.get(c, {}).get(d)
            if not rec:
                continue
            row = {"_d": d,
                   "date": pd.Timestamp(d).strftime("%d %b %Y"),
                   "mother": f"M{c.split('.')[0]}",
                   "code": c}
            for k, _ in _STATE_COLS:
                v = rec.get(k)
                row[k] = round(float(v), 1) if (k == "stolon_length" and v is not None) else v
            rows.append(row)

    if not rows:
        return html.Div(f"No Worksheet 1 measurements recorded for {cultivar}.",
                        className="stats-empty")

    rows.sort(key=lambda r: (r["_d"], r["mother"], r["code"]))
    n_mothers = len({r["mother"] for r in rows})

    # keep only measurement columns that carry a real (non-zero, non-null) value
    active = [(k, lbl) for k, lbl in _STATE_COLS
              if any(r.get(k) not in (None, 0) for r in rows)]
    base = ([("date", "Date")] if show_date else []) + [("mother", "Mother"), ("code", "Code")]
    columns = [{"name": lbl, "id": k} for k, lbl in base + active]
    keep = [k for k, _ in base + active]
    data = [{k: r.get(k) for k in keep} for r in rows]

    when = "all dates" if show_date else pd.Timestamp(date).strftime("%d %b %Y")
    return html.Div([
        html.P(f"{cultivar} · {when} · {len(rows)} plantlet-measurements · "
               f"{n_mothers} mother{'s' if n_mothers != 1 else ''}",
               className="card-subtitle"),
        dash_table.DataTable(
            columns=columns, data=data,
            sort_action="native",
            export_format="csv", export_headers="display", page_size=15,
            style_as_list_view=True,
            style_table={"overflowX": "auto"},
            style_cell={"fontFamily": "Inter, sans-serif", "fontSize": "12.5px",
                        "padding": "7px 14px 7px 0", "textAlign": "left",
                        "backgroundColor": "white", "border": "none"},
            style_header={"backgroundColor": "white", "color": "#99a",
                          "fontWeight": "600", "fontSize": "10.5px",
                          "textTransform": "uppercase", "letterSpacing": "0.5px",
                          "borderBottom": "1px solid #eee",
                          "padding": "0 14px 7px 0"},
            style_data={"borderBottom": "1px solid #f6f6f8"},
            style_cell_conditional=[
                {"if": {"column_id": "code"},   "fontWeight": "600", "color": "#2d7a45"},
                {"if": {"column_id": "mother"}, "color": "#889"},
            ],
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
        html.Details([
            html.Summary("State Data — Worksheet 1 measurements",
                         style={"cursor": "pointer", "fontSize": "15px",
                                "fontWeight": "700", "color": "#14213d"}),
            html.Div(style={"marginTop": "14px"}, children=[
                html.Div(className="filter-row", children=[
                    html.Label("Date", className="filter-label"),
                    dcc.Dropdown(id="pa2-date", clearable=False,
                                 style={"width": "220px"}),
                ]),
                html.P("Every per-plantlet measurement for the chosen cultivar, "
                       "all mothers. Sort by any header or Export to CSV.",
                       className="card-subtitle"),
                dcc.Loading(html.Div(id="pa2-state")),
            ]),
        ]),
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
    opts = [{"label": "All dates", "value": "all"}] + \
           [{"label": pd.Timestamp(d).strftime("%d %b %Y"), "value": d} for d in dates]
    return opts, "all"


@callback(
    Output("pa2-state", "children"),
    Input("pa2-cv", "value"),
    Input("pa2-date", "value"),
)
def upd_state(cultivar, date):
    if not cultivar:
        return html.Div("Select a cultivar.", className="stats-empty")
    return _state_table(cultivar, date or "all")


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
