"""
src/plant_arch.py
=================
Plant architecture module for Phenotyping Batch 4 — Worksheet 3.

Reads the daughter-plant naming convention from `Pheno 4 Worksheet 3.xlsx`,
builds a structural tree for each cultivar × mother-plant combination, lays out
the 2D coordinates using measured internode lengths, and generates a Plotly
figure with growth-animation frames.

Data source
-----------
Worksheet 3 encodes the exact position of every daughter plant in the plant's
stolon network.  Each row corresponds to one daughter plant.

Code format: e.g.  1.1.2.1  or  1.1.2/1.2.1  or  1.1.2/1.2/1.1
  - First number: mother plant ID (= replicate: 1, 2, or 3)
  - Slash (/) = branching point: a new stolon of the next order starts here
  - Numbers after each slash: (stolon_number, node_number [, daughter_id])
  - Last number: daughter plant ID at the terminal node

Internode length columns (L1, L2, L3…) give the distance (cm) between
consecutive nodes along the full root-to-daughter path.
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go

warnings.filterwarnings("ignore")

# ─── Path resolution ─────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent.parent   # veryberrylab/

WS3_CANDIDATES = [
    ROOT / "data" / "raw" / "Pheno 4 Worksheet 3.xlsx",
    ROOT.parent / "Analytics" / "Pheno 4 Worksheet 3.xlsx",
    ROOT.parent / "Phenotyping Data with Aditya 1_27_2026" / "Pheno Batch 4" / "Pheno 4 Worksheet 3.xlsx",
]

# Worksheet 3 sheet name → cultivar full name
WS3_SHEET_MAP: dict[str, str] = {
    "RAD":   "Radiance",
    "SEN":   "Sensation",
    "CHA":   "Chandler",
    "CAM":   "Camarosa",
    "ALB":   "Albion",
    "RJUNE": "Ruby June",
    "FINN":  "Finn",
    "BRI":   "Brilliance",
    "CAB":   "Cabrio",
    "MOX":   "Moxie",
    # POR is skipped — no Daughter plant column
}

SKIP_SHEETS = {"misc. dry matter", "por"}

# ─── Constants ────────────────────────────────────────────────────────────────

DEFAULT_INTERNODE_CM = 2.0    # fallback length when measurement is absent
MOTHER_SPACING_CM    = 130.0  # horizontal gap between mother plants
ANIM_FRAMES          = 150    # target number of animation frames

# Stolon colours by hierarchical order
STOLON_COLOUR = {1: "#1b5e20", 2: "#2e7d32", 3: "#66bb6a", 4: "#a5d6a7"}
STOLON_WIDTH  = {1: 3.0, 2: 2.0, 3: 1.2, 4: 0.8}
MOTHER_COLOUR = "#4e342e"
NODE_COLOUR   = "#388e3c"
DP_COLOUR     = "#c62828"
MEAN_COLOUR   = "#1565c0"   # used when showing "All mothers" mean

# ─── Data model ──────────────────────────────────────────────────────────────

class _Node:
    __slots__ = ["num", "pos", "daughter_code", "child_stolons"]

    def __init__(self, num: int):
        self.num: int                  = num
        self.pos: Optional[tuple]      = None    # (x, y) after layout
        self.daughter_code: Optional[str] = None
        self.child_stolons: list       = []      # stolon keys branching from here


class _Stolon:
    __slots__ = ["key", "origin", "angle", "nodes", "ilengths", "parent_node_key"]

    def __init__(self, key: tuple):
        self.key    = key                       # (mother_id, order, stolon_num)
        self.origin: Optional[tuple] = None
        self.angle:  Optional[float] = None
        self.nodes:  dict = {}                  # node_num → _Node
        self.ilengths: dict = {}                # node_num → float (cm, cumulative distance)
        self.parent_node_key: Optional[tuple] = None


class Plant:
    """Container for all mothers, stolons, and nodes of one cultivar."""

    def __init__(self, cultivar: str):
        self.cultivar = cultivar
        self.mothers: dict = {}    # mother_id → (x, y)
        self.stolons: dict = {}    # (mother_id, order, stolon_num) → _Stolon

    def _stolon(self, mother_id: int, order: int, stolon_num: int) -> _Stolon:
        key = (mother_id, order, stolon_num)
        if key not in self.stolons:
            self.stolons[key] = _Stolon(key)
        return self.stolons[key]

    def _node(self, mother_id: int, order: int, stolon_num: int, node_num: int) -> _Node:
        st = self._stolon(mother_id, order, stolon_num)
        if node_num not in st.nodes:
            st.nodes[node_num] = _Node(node_num)
        return st.nodes[node_num]

    def mother_ids(self) -> list[int]:
        return sorted(self.mothers)

    def stolon_count(self, mother_id: Optional[int] = None) -> int:
        if mother_id is None:
            return len(self.stolons)
        return sum(1 for k in self.stolons if k[0] == mother_id)

    def node_count(self, mother_id: Optional[int] = None) -> int:
        if mother_id is None:
            return sum(len(s.nodes) for s in self.stolons.values())
        return sum(len(s.nodes) for k, s in self.stolons.items() if k[0] == mother_id)

    def dp_count(self, mother_id: Optional[int] = None) -> int:
        def _cnt(st):
            return sum(1 for nd in st.nodes.values() if nd.daughter_code)
        if mother_id is None:
            return sum(_cnt(s) for s in self.stolons.values())
        return sum(_cnt(s) for k, s in self.stolons.items() if k[0] == mother_id)


# ─── Code parsing ─────────────────────────────────────────────────────────────

def _ints(segment: str) -> list[int]:
    return [int(t) for t in segment.split(".") if t.strip().lstrip("-").isdigit()]


def _parse_path(parts: list[str]) -> list[tuple]:
    """
    Convert slash-separated parts into path entries.
    Returns list of (order, stolon_num, max_node, daughter_or_None, is_terminal).
    """
    if not parts:
        return []
    first = _ints(parts[0])
    if len(first) < 3:
        return []

    entries: list[tuple] = []

    if len(parts) == 1:
        entries.append((1, first[1], first[2], first[3] if len(first) >= 4 else None, True))
    else:
        entries.append((1, first[1], first[2], None, False))
        for sub_idx, part in enumerate(parts[1:]):
            order   = sub_idx + 2
            nums    = _ints(part)
            is_last = (sub_idx == len(parts) - 2)
            if not nums:
                continue
            if len(nums) >= 3:
                entries.append((order, nums[0], nums[1], nums[2], True))
            elif len(nums) == 2:
                if is_last:
                    entries.append((order, nums[0], 1, nums[1], True))
                else:
                    entries.append((order, nums[0], nums[1], None, False))
            else:
                entries.append((order, nums[0], 1, None, is_last))

    return entries


def _ingest_code(raw_code: str, row_lengths: list[float], plant: Plant) -> None:
    """Register one daughter-plant code + its internode lengths into `plant`."""
    code = str(raw_code).strip().replace("//", "/")
    if not code or code.lower() == "nan":
        return

    parts = code.split("/")
    first = _ints(parts[0])
    if len(first) < 3:
        return

    mother_id = first[0]
    plant.mothers.setdefault(mother_id, None)

    path = _parse_path(parts)
    if not path:
        return

    len_ptr = 0
    for (order, stolon_num, max_node, daughter, is_terminal) in path:
        st = plant._stolon(mother_id, order, stolon_num)
        for n in range(1, max_node + 1):
            if n not in st.ilengths:
                st.ilengths[n] = (row_lengths[len_ptr]
                                  if len_ptr < len(row_lengths)
                                  else DEFAULT_INTERNODE_CM)
            len_ptr += 1
        for n in range(1, max_node + 1):
            plant._node(mother_id, order, stolon_num, n)
        if is_terminal and daughter is not None:
            nd = plant._node(mother_id, order, stolon_num, max_node)
            if nd.daughter_code is None:
                nd.daughter_code = code

    for i in range(len(path) - 1):
        o_p, s_p, n_p, _, _ = path[i]
        o_c, s_c, _,  _, _  = path[i + 1]
        parent_st   = plant._stolon(mother_id, o_p, s_p)
        child_st    = plant._stolon(mother_id, o_c, s_c)
        parent_node = parent_st.nodes[n_p]
        if child_st.key not in parent_node.child_stolons:
            parent_node.child_stolons.append(child_st.key)
        if child_st.parent_node_key is None:
            child_st.parent_node_key = (mother_id, o_p, s_p, n_p)


# ─── Sheet loading ────────────────────────────────────────────────────────────

def _build_plant_from_df(df: pd.DataFrame, cultivar: str) -> Optional[Plant]:
    """Parse one sheet DataFrame into a Plant. Returns None if no DP column."""
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]

    dp_col = next((c for c in df.columns if c.lower().startswith("daughter")), None)
    if dp_col is None:
        return None

    il_cols = sorted(c for c in df.columns if c.lower().startswith("internode"))
    plant   = Plant(cultivar)

    for _, row in df.iterrows():
        raw = row.get(dp_col, np.nan)
        if pd.isna(raw):
            continue
        code = str(raw).strip()
        if not code:
            continue

        lengths: list[float] = []
        for col in il_cols:
            try:
                v = float(row.get(col, np.nan))
                lengths.append(v if (not np.isnan(v) and v > 0) else DEFAULT_INTERNODE_CM)
            except (ValueError, TypeError):
                lengths.append(DEFAULT_INTERNODE_CM)

        _ingest_code(code, lengths, plant)

    return plant if plant.stolons else None


def load_all_plants(path: Optional[Path] = None) -> dict[str, Plant]:
    """
    Load all cultivar sheets from Worksheet 3 and return a dict
    {cultivar_name → Plant}.  Returns an empty dict if the file is not found.
    """
    candidates = [path] if path else WS3_CANDIDATES
    xl_path = next((p for p in candidates if p and Path(p).exists()), None)

    if xl_path is None:
        return {}

    xl     = pd.ExcelFile(xl_path)
    plants: dict[str, Plant] = {}

    for sheet in xl.sheet_names:
        if sheet.lower().strip() in SKIP_SHEETS:
            continue
        cultivar = WS3_SHEET_MAP.get(sheet.strip())
        if cultivar is None:
            continue
        df    = xl.parse(sheet, header=0)
        plant = _build_plant_from_df(df, cultivar)
        if plant is not None:
            plants[cultivar] = plant

    return plants


# ─── Layout ──────────────────────────────────────────────────────────────────

def _assign_positions(plant: Plant) -> None:
    """Compute (x, y) for every node using internode lengths."""
    mother_ids = sorted(plant.mothers)
    n_mothers  = len(mother_ids)
    for i, mid in enumerate(mother_ids):
        x = (i - (n_mothers - 1) / 2.0) * MOTHER_SPACING_CM
        plant.mothers[mid] = (x, 0.0)

    # Primary stolon angles: evenly distributed, starting upward
    for mid in mother_ids:
        pkeys = sorted(k for k in plant.stolons if k[0] == mid and k[1] == 1)
        n = len(pkeys)
        for j, key in enumerate(pkeys):
            st = plant.stolons[key]
            st.origin = plant.mothers[mid]
            st.angle  = np.pi / 2 + 2 * np.pi * j / max(n, 1)

    max_order = max(k[1] for k in plant.stolons) if plant.stolons else 1
    for order in range(1, max_order + 1):
        for key in sorted(k for k in plant.stolons if k[1] == order):
            st = plant.stolons[key]
            if st.origin is None or st.angle is None:
                continue
            prev = st.origin
            for n in sorted(st.nodes):
                length = st.ilengths.get(n, DEFAULT_INTERNODE_CM)
                x = prev[0] + length * np.cos(st.angle)
                y = prev[1] + length * np.sin(st.angle)
                st.nodes[n].pos = (x, y)
                prev = (x, y)

                nd     = st.nodes[n]
                n_ch   = len(nd.child_stolons)
                if n_ch:
                    offsets = np.linspace(-np.pi / 2.5, np.pi / 2.5, n_ch)
                    for ci, ck in enumerate(nd.child_stolons):
                        child = plant.stolons[ck]
                        child.origin = (x, y)
                        child.angle  = st.angle + offsets[ci]


# ─── DFS event collection ─────────────────────────────────────────────────────

def _collect_steps(plant: Plant, mother_id: Optional[int] = None) -> list[list[tuple]]:
    """
    Depth-first traversal yielding one step per stolon node.
    Each step is a list of (type, ...) tuples for the animation.

    Types: 'mother', 'segment', 'node', 'daughter'
    """
    steps: list[list[tuple]] = []

    target_mothers = [mother_id] if mother_id else sorted(plant.mothers)

    for mid in target_mothers:
        pos = plant.mothers.get(mid)
        if pos:
            steps.append([("mother", mid, pos)])

    def traverse(stolon_key: tuple) -> None:
        st = plant.stolons.get(stolon_key)
        if st is None or st.origin is None:
            return
        prev = st.origin
        for n in sorted(st.nodes):
            nd = st.nodes[n]
            if nd.pos is None:
                continue
            cmds: list[tuple] = [
                ("segment", prev, nd.pos, st.key[1]),
                ("node", nd.pos),
            ]
            if nd.daughter_code:
                cmds.append(("daughter", nd.pos, nd.daughter_code))
            steps.append(cmds)
            for ck in nd.child_stolons:
                traverse(ck)
            prev = nd.pos

    for mid in target_mothers:
        for key in sorted(k for k in plant.stolons if k[0] == mid and k[1] == 1):
            traverse(key)

    return steps


# ─── Plotly figure builder ────────────────────────────────────────────────────

def build_figure(plant: Plant, mother_id: Optional[int] = None) -> go.Figure:
    """
    Build a Plotly figure with animation frames showing the plant architecture
    growing node-by-node in depth-first order.

    Parameters
    ----------
    plant     : Plant object (must have positions already assigned by load_plant)
    mother_id : which mother plant to display; None = show all

    Returns
    -------
    go.Figure with play/pause controls and progress slider
    """
    _assign_positions(plant)
    steps = _collect_steps(plant, mother_id)

    if not steps:
        fig = go.Figure()
        fig.update_layout(
            height=560,
            plot_bgcolor="#f0f7ee", paper_bgcolor="white",
            annotations=[dict(text="No architecture data available.",
                              x=0.5, y=0.5, xref="paper", yref="paper",
                              showarrow=False, font=dict(size=14, color="#888"))],
            xaxis=dict(visible=False), yaxis=dict(visible=False),
        )
        return fig

    # ── Batching: group steps → ANIM_FRAMES ───────────────────────────────
    n_steps = len(steps)
    spf     = max(1, -(-n_steps // ANIM_FRAMES))   # ceiling division
    batches = [steps[i:i + spf] for i in range(0, n_steps, spf)]
    n_frames = len(batches)

    # ── Pre-compute axis limits ───────────────────────────────────────────
    all_x, all_y = [], []
    for step_cmds in steps:
        for cmd in step_cmds:
            if cmd[0] == "mother":
                all_x.append(cmd[2][0]); all_y.append(cmd[2][1])
            elif cmd[0] == "segment":
                all_x += [cmd[1][0], cmd[2][0]]; all_y += [cmd[1][1], cmd[2][1]]
            elif cmd[0] in ("node", "daughter"):
                all_x.append(cmd[1][0]); all_y.append(cmd[1][1])

    pad  = max((max(all_x) - min(all_x)) * 0.07, 8.0)
    xlim = [min(all_x) - pad, max(all_x) + pad]
    ylim = [min(all_y) - pad, max(all_y) + pad]

    # ── Accumulate trace data frame by frame ──────────────────────────────
    # Trace indices: 0=mother, 1=primary lines, 2=secondary lines, 3=tertiary+ lines,
    #                4=nodes, 5=daughter plants
    m_x, m_y, m_text           = [], [], []
    seg_x  = {1: [], 2: [], 3: []}   # order → [x0, x1, None, ...]
    seg_y  = {1: [], 2: [], 3: []}
    node_x, node_y             = [], []
    dp_x,   dp_y, dp_text      = [], [], []

    frames: list[go.Frame] = []

    for fi, batch in enumerate(batches):
        for step_cmds in batch:
            for cmd in step_cmds:
                if cmd[0] == "mother":
                    _, mid, pos = cmd
                    m_x.append(pos[0]); m_y.append(pos[1])
                    m_text.append(f"Mother {mid}")

                elif cmd[0] == "segment":
                    _, p1, p2, order = cmd
                    o = min(order, 3)
                    seg_x[o] += [p1[0], p2[0], None]
                    seg_y[o] += [p1[1], p2[1], None]

                elif cmd[0] == "node":
                    _, pos = cmd
                    node_x.append(pos[0]); node_y.append(pos[1])

                elif cmd[0] == "daughter":
                    _, pos, code = cmd
                    dp_x.append(pos[0]); dp_y.append(pos[1])
                    dp_text.append(code)

        frame_data = [
            # 0 — Mother plants
            go.Scatter(x=list(m_x), y=list(m_y), mode="markers",
                       marker=dict(size=18, color=MOTHER_COLOUR,
                                   line=dict(width=2, color="white")),
                       text=m_text, hovertemplate="%{text}<extra></extra>"),
            # 1 — Primary stolon segments
            go.Scatter(x=list(seg_x[1]), y=list(seg_y[1]), mode="lines",
                       line=dict(color=STOLON_COLOUR[1], width=STOLON_WIDTH[1]),
                       hoverinfo="skip"),
            # 2 — Secondary stolon segments
            go.Scatter(x=list(seg_x[2]), y=list(seg_y[2]), mode="lines",
                       line=dict(color=STOLON_COLOUR[2], width=STOLON_WIDTH[2]),
                       hoverinfo="skip"),
            # 3 — Tertiary+ stolon segments
            go.Scatter(x=list(seg_x[3]), y=list(seg_y[3]), mode="lines",
                       line=dict(color=STOLON_COLOUR[3], width=STOLON_WIDTH[3]),
                       hoverinfo="skip"),
            # 4 — Node dots
            go.Scatter(x=list(node_x), y=list(node_y), mode="markers",
                       marker=dict(size=5, color=NODE_COLOUR),
                       hoverinfo="skip"),
            # 5 — Daughter plants
            go.Scatter(x=list(dp_x), y=list(dp_y), mode="markers",
                       marker=dict(size=10, color=DP_COLOUR,
                                   line=dict(width=1.5, color="white"),
                                   symbol="circle"),
                       text=dp_text,
                       hovertemplate="<b>DP:</b> %{text}<extra></extra>"),
        ]
        frames.append(go.Frame(data=frame_data, name=str(fi)))

    # ── Initial figure (empty traces) ────────────────────────────────────
    empty_scatter = lambda: go.Scatter(x=[], y=[], mode="markers", hoverinfo="skip")
    empty_line    = lambda: go.Scatter(x=[], y=[], mode="lines",   hoverinfo="skip")

    fig = go.Figure(
        data=[
            go.Scatter(x=[], y=[], mode="markers", showlegend=True,
                       name="Mother plant",
                       marker=dict(size=18, color=MOTHER_COLOUR,
                                   line=dict(width=2, color="white"))),
            go.Scatter(x=[], y=[], mode="lines", showlegend=True,
                       name="Primary stolon",
                       line=dict(color=STOLON_COLOUR[1], width=STOLON_WIDTH[1])),
            go.Scatter(x=[], y=[], mode="lines", showlegend=True,
                       name="Secondary stolon",
                       line=dict(color=STOLON_COLOUR[2], width=STOLON_WIDTH[2])),
            go.Scatter(x=[], y=[], mode="lines", showlegend=True,
                       name="Tertiary+ stolon",
                       line=dict(color=STOLON_COLOUR[3], width=STOLON_WIDTH[3])),
            go.Scatter(x=[], y=[], mode="markers", showlegend=False,
                       marker=dict(size=5, color=NODE_COLOUR)),
            go.Scatter(x=[], y=[], mode="markers", showlegend=True,
                       name="Daughter plant",
                       marker=dict(size=10, color=DP_COLOUR,
                                   line=dict(width=1.5, color="white"))),
        ],
        frames=frames,
    )

    # ── Animation controls ────────────────────────────────────────────────
    slider_steps = [
        dict(args=[[str(i)], dict(frame=dict(duration=0), mode="immediate",
                                  transition=dict(duration=0))],
             label="", method="animate")
        for i in range(n_frames)
    ]

    fig.update_layout(
        height=580,
        margin=dict(l=10, r=10, t=10, b=60),
        plot_bgcolor="#f0f7ee",
        paper_bgcolor="white",
        xaxis=dict(range=xlim, showgrid=False, zeroline=False, visible=False,
                   scaleanchor="y"),
        yaxis=dict(range=ylim, showgrid=False, zeroline=False, visible=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.01,
                    xanchor="left", x=0, font=dict(size=11)),
        font=dict(family="Inter, sans-serif", size=12),
        updatemenus=[dict(
            type="buttons",
            showactive=False,
            y=-0.08, x=0.0, xanchor="left", yanchor="top",
            buttons=[
                dict(label="▶  Play",
                     method="animate",
                     args=[None, dict(frame=dict(duration=60, redraw=True),
                                      fromcurrent=True,
                                      transition=dict(duration=0))]),
                dict(label="⏸  Pause",
                     method="animate",
                     args=[[None], dict(frame=dict(duration=0, redraw=False),
                                        mode="immediate",
                                        transition=dict(duration=0))]),
            ],
        )],
        sliders=[dict(
            active=0,
            steps=slider_steps,
            currentvalue=dict(visible=False),
            len=0.88, x=0.12, y=-0.04,
            pad=dict(t=0, b=0),
            bgcolor="#e8f5e9",
            bordercolor="#c8e6c9",
        )],
    )

    return fig


def plant_summary(plant: Plant, mother_id: Optional[int] = None) -> dict:
    """Return summary stats for display in the UI."""
    mid = mother_id
    return {
        "cultivar":  plant.cultivar,
        "mothers":   plant.mother_ids(),
        "stolons":   plant.stolon_count(mid),
        "nodes":     plant.node_count(mid),
        "daughters": plant.dp_count(mid),
        "max_order": (max(k[1] for k in plant.stolons
                          if mid is None or k[0] == mid)
                      if plant.stolons else 0),
    }
