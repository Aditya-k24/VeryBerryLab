"""
pages/plant_animation.py
========================
Page 5 — Plant Architecture Animation

Shows the actual daughter-plant stolon network for a selected cultivar and
mother plant, drawn from the hierarchical naming codes in Worksheet 3.

Architecture:
  • Crown (mother plant) is the root of the tree
  • Primary stolons radiate outward; count and lengths from measured internode data
  • Secondary/tertiary stolons branch off at measured branching nodes
  • Daughter plants (red circles) appear at the correct nodes in depth-first order

The Plotly figure includes built-in Play / Pause animation controls and a
progress slider. Selecting a different cultivar or mother plant re-builds the
figure from scratch.

Data source: Pheno 4 Worksheet 3.xlsx (parsed by src/plant_arch.py)
"""

import dash
import pandas as pd
from dash import Input, Output, callback, dcc, html
from dash.exceptions import PreventUpdate

import src.data_cache as cache
import src.plant_arch as arch

dash.register_page(__name__, path="/plant-animation", name="Plant Animation", order=4)

# ─── Helpers ─────────────────────────────────────────────────────────────────

def _cultivar_options() -> list[dict]:
    """Build dropdown options from loaded plants, sorted alphabetically."""
    plants = cache.ws3_plants
    if not plants:
        return [{"label": "No data loaded", "value": "__none__"}]
    return [{"label": cv, "value": cv} for cv in sorted(plants)]


def _default_cultivar() -> str:
    plants = cache.ws3_plants
    if not plants:
        return "__none__"
    # Prefer Radiance (largest dataset) if available
    return "Radiance" if "Radiance" in plants else sorted(plants)[0]


def _empty_fig(msg: str):
    import plotly.graph_objects as go
    fig = go.Figure()
    fig.update_layout(
        height=560,
        plot_bgcolor="#f0f7ee", paper_bgcolor="white",
        xaxis=dict(visible=False), yaxis=dict(visible=False),
        annotations=[dict(text=msg, x=0.5, y=0.5, xref="paper", yref="paper",
                          showarrow=False, font=dict(size=14, color="#888"))],
    )
    return fig


def _stat_card(label: str, value) -> html.Div:
    return html.Div(className="stat-card", children=[
        html.Div(str(value), className="stat-number"),
        html.Div(label,      className="stat-label"),
    ])


# ─── Layout ──────────────────────────────────────────────────────────────────

layout = html.Div([
    html.Div(className="page-header", children=[
        html.H1("Plant Architecture", className="page-title"),
        html.P(
            "Actual stolon network reconstructed from daughter-plant naming codes "
            "(Worksheet 3). Growing depth-first from each mother crown outward. "
            "Press ▶ Play to animate.",
            className="page-subtitle",
        ),
    ]),
    html.Div(className="content-area", children=[

        # ── Controls card ──────────────────────────────────────────────────
        html.Div(className="card filter-card", children=[
            html.Div(className="filter-row", children=[

                html.Div([
                    html.Label("Cultivar", className="filter-label"),
                    dcc.Dropdown(
                        id="pa3-cultivar",
                        options=_cultivar_options(),
                        value=_default_cultivar(),
                        clearable=False,
                        style={"width": "200px"},
                    ),
                ]),

                html.Div([
                    html.Label("Mother plant (replicate)", className="filter-label"),
                    dcc.RadioItems(
                        id="pa3-mother",
                        options=[
                            {"label": "Mother 1", "value": 1},
                            {"label": "Mother 2", "value": 2},
                            {"label": "Mother 3", "value": 3},
                            {"label": "All", "value": 0},
                        ],
                        value=1,
                        inline=True,
                        className="radio-inline",
                    ),
                ]),

            ]),

            # Summary stats row
            html.Div(id="pa3-stats-row", className="stats-row",
                     style={"marginTop": "14px"}),
        ]),

        # ── Figure card ────────────────────────────────────────────────────
        html.Div(className="card", style={"padding": "16px"}, children=[
            html.P(
                "Each node in the animation is a real measurement. "
                "Stolon directions are evenly distributed for clarity; "
                "lengths are proportional to measured internode lengths (cm).",
                className="disclaimer",
                style={"marginBottom": "10px"},
            ),
            dcc.Graph(
                id="pa3-figure",
                config={"displayModeBar": False, "responsive": True},
            ),
        ]),

    ]),
])


# ─── Callbacks ───────────────────────────────────────────────────────────────

@callback(
    Output("pa3-figure",    "figure"),
    Output("pa3-stats-row", "children"),
    Input("pa3-cultivar",   "value"),
    Input("pa3-mother",     "value"),
)
def update_figure(cultivar: str, mother_val: int):
    """Re-build the animation figure when cultivar or mother selection changes."""
    plants = cache.ws3_plants

    if not plants or cultivar == "__none__" or cultivar not in plants:
        msg = ("Worksheet 3 not found.  Place 'Pheno 4 Worksheet 3.xlsx' in "
               "the Analytics/ folder and restart the app.")
        return _empty_fig(msg), []

    plant     = plants[cultivar]
    mother_id = int(mother_val) if mother_val else None   # 0 = All → None

    fig     = arch.build_figure(plant, mother_id)
    summary = arch.plant_summary(plant, mother_id)

    stats_cards = [
        _stat_card("Stolons",        summary["stolons"]),
        _stat_card("Nodes",          summary["nodes"]),
        _stat_card("Daughter plants",summary["daughters"]),
        _stat_card("Max stolon order", summary["max_order"]),
    ]

    return fig, stats_cards
