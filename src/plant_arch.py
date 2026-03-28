"""
src/plant_arch.py
=================
Plant architecture for Phenotyping Batch 4.

Sources
-------
- Worksheet 3  (Pheno 4 Worksheet 3.xlsx) — snapshot with internode lengths;
  provides the full stolon tree topology.
- Worksheet 1  (ws1_parser) — repeated temporal measurements April-July 2025;
  drives which nodes are visible on each date in the animation.

Public API
----------
load_all_plants()  → dict[cultivar → Plant]
build_js_html(plant, ws1_cultivar, mother_id) → str (self-contained HTML)
plant_summary(plant, mother_id)               → dict
_empty_html(msg)                              → str
"""

from __future__ import annotations

import json
import sys
import warnings
from collections import deque
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ── Paths ─────────────────────────────────────────────────────────────────────

_HERE = Path(__file__).resolve().parent    # Analytics/src/
_ROOT = _HERE.parent                       # Analytics/

WS3_CANDIDATES: list[Path] = [
    _ROOT / "data" / "Pheno 4 Worksheet 3.xlsx",
    _ROOT.parent / "Phenotyping Data with Aditya 1_27_2026" / "Pheno Batch 4" / "Pheno 4 Worksheet 3.xlsx",
]

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
}
SKIP_SHEETS = {"misc. dry matter", "por"}

DEFAULT_INTERNODE_CM = 2.0
CANVAS_W_MAX         = 3000   # px cap on generated canvas width
LEAF_W_MIN           = 10     # px per leaf slot (minimum)


# ── Data model ────────────────────────────────────────────────────────────────

class _Node:
    __slots__ = ["num", "pos", "daughter_code", "child_stolons"]

    def __init__(self, num: int):
        self.num:            int            = num
        self.pos:            Optional[tuple]= None
        self.daughter_code:  Optional[str]  = None
        self.child_stolons:  list           = []


class _Stolon:
    __slots__ = ["key", "origin", "angle", "nodes", "ilengths", "parent_node_key"]

    def __init__(self, key: tuple):
        self.key             = key
        self.origin: Optional[tuple] = None
        self.angle:  Optional[float] = None
        self.nodes:  dict   = {}
        self.ilengths: dict = {}
        self.parent_node_key: Optional[tuple] = None


class Plant:
    """All mothers / stolons / nodes for one cultivar."""

    def __init__(self, cultivar: str):
        self.cultivar = cultivar
        self.mothers: dict = {}
        self.stolons: dict = {}

    def _stolon(self, mid: int, order: int, snum: int) -> _Stolon:
        key = (mid, order, snum)
        if key not in self.stolons:
            self.stolons[key] = _Stolon(key)
        return self.stolons[key]

    def _node(self, mid: int, order: int, snum: int, nnum: int) -> _Node:
        st = self._stolon(mid, order, snum)
        if nnum not in st.nodes:
            st.nodes[nnum] = _Node(nnum)
        return st.nodes[nnum]

    def mother_ids(self) -> list[int]:
        return sorted(self.mothers)

    def stolon_count(self, mid: Optional[int] = None) -> int:
        return (len(self.stolons) if mid is None
                else sum(1 for k in self.stolons if k[0] == mid))

    def node_count(self, mid: Optional[int] = None) -> int:
        if mid is None:
            return sum(len(s.nodes) for s in self.stolons.values())
        return sum(len(s.nodes) for k, s in self.stolons.items() if k[0] == mid)

    def dp_count(self, mid: Optional[int] = None) -> int:
        def _c(st):
            return sum(1 for nd in st.nodes.values() if nd.daughter_code)
        if mid is None:
            return sum(_c(s) for s in self.stolons.values())
        return sum(_c(s) for k, s in self.stolons.items() if k[0] == mid)


# ── Code parsing ──────────────────────────────────────────────────────────────

def _ints(seg: str) -> list[int]:
    return [int(t) for t in seg.split(".") if t.strip().lstrip("-").isdigit()]


def _parse_path(parts: list[str]) -> list[tuple]:
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


def _build_plant_from_df(df: pd.DataFrame, cultivar: str) -> Optional[Plant]:
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
    """Load all cultivar sheets from Worksheet 3. Returns {cultivar → Plant}."""
    candidates = [path] if path else WS3_CANDIDATES
    xl_path = next((p for p in candidates if p and Path(p).exists()), None)
    if xl_path is None:
        return {}
    xl = pd.ExcelFile(xl_path)
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


# ── Legacy layout (kept for generate_animations.py) ──────────────────────────

def _legacy_assign_positions(plant: Plant) -> None:
    mother_ids = sorted(plant.mothers)
    n_mothers  = len(mother_ids)
    for i, mid in enumerate(mother_ids):
        x = (i - (n_mothers - 1) / 2.0) * 130.0
        plant.mothers[mid] = (x, 0.0)
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
                nd   = st.nodes[n]
                n_ch = len(nd.child_stolons)
                if n_ch:
                    offsets = np.linspace(-np.pi / 2.5, np.pi / 2.5, n_ch)
                    for ci, ck in enumerate(nd.child_stolons):
                        child = plant.stolons[ck]
                        child.origin = (x, y)
                        child.angle  = st.angle + offsets[ci]


def _legacy_collect_steps(plant: Plant,
                           mother_id: Optional[int] = None) -> list[list[tuple]]:
    steps: list[list[tuple]] = []
    target_mothers = [mother_id] if mother_id else sorted(plant.mothers)
    for mid in target_mothers:
        pos = plant.mothers.get(mid)
        if pos:
            steps.append([("mother", mid, pos)])
    visited_stolons: set = set()

    def traverse(stolon_key: tuple) -> None:
        if stolon_key in visited_stolons:
            return
        visited_stolons.add(stolon_key)
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



# ── D3 hierarchy builder ──────────────────────────────────────────────────────

def _to_d3_hierarchy(plant: Plant, mother_id: int,
                     code_first_date: dict, n_dates: int) -> dict:
    """
    Convert the plant structure for one mother into a D3-compatible nested
    hierarchy JSON.  Each dict node has:
        id, type, order, first_date, dp_first_date, has_dp, code, depth_cm
    Children list is populated so d3.hierarchy() can traverse it.
    """
    sys.setrecursionlimit(max(10000, sys.getrecursionlimit()))

    # Memoised subtree first-date (earliest date any descendant daughter appears)
    _sfm: dict = {}

    def _sfd(sk: tuple) -> int:
        if sk in _sfm:
            return _sfm[sk]
        st = plant.stolons.get(sk)
        if st is None:
            _sfm[sk] = n_dates
            return n_dates
        best = n_dates
        for nd in st.nodes.values():
            if nd.daughter_code:
                best = min(best, code_first_date.get(nd.daughter_code, n_dates))
            for ck in nd.child_stolons:
                best = min(best, _sfd(ck))
        _sfm[sk] = best
        return best

    def _make(sk: tuple, node_num: int, depth: float, visited: set) -> Optional[dict]:
        visit_key = (sk, node_num)
        if visit_key in visited:
            return None
        visited.add(visit_key)

        st = plant.stolons.get(sk)
        if st is None or node_num not in st.nodes:
            return None

        nd     = st.nodes[node_num]
        il     = st.ilengths.get(node_num, DEFAULT_INTERNODE_CM)
        d      = round(depth + il, 3)
        sk_fd  = _sfd(sk)
        dp_fd  = code_first_date.get(nd.daughter_code, n_dates) if nd.daughter_code else n_dates

        node: dict = {
            "id":           f"{sk[0]}_{sk[1]}_{sk[2]}_{node_num}",
            "type":         "node",
            "order":        sk[1],
            "first_date":   int(sk_fd),
            "dp_first_date": int(dp_fd),
            "has_dp":       bool(nd.daughter_code),
            "code":         nd.daughter_code or "",
            "depth_cm":     d,
            "children":     [],
        }

        # Continuation: next node in the same stolon (insert first so it's
        # the "straight-down" branch in the layout)
        sorted_ns = sorted(st.nodes)
        idx = sorted_ns.index(node_num)
        if idx + 1 < len(sorted_ns):
            child = _make(sk, sorted_ns[idx + 1], d, visited)
            if child:
                node["children"].insert(0, child)

        # Child stolons branching off at this node
        for ck in nd.child_stolons:
            child_st = plant.stolons.get(ck)
            if child_st and child_st.nodes:
                fn = min(child_st.nodes)
                child = _make(ck, fn, d, visited)
                if child:
                    node["children"].append(child)

        return node

    pkeys = sorted(k for k in plant.stolons if k[0] == mother_id and k[1] == 1)

    root: dict = {
        "id":            f"M{mother_id}",
        "type":          "crown",
        "order":         0,
        "first_date":    0,
        "dp_first_date": n_dates,
        "has_dp":        False,
        "code":          "",
        "depth_cm":      0.0,
        "label":         f"M{mother_id}",
        "children":      [],
    }

    vis: set = set()
    for pk in pkeys:
        child_st = plant.stolons.get(pk)
        if child_st and child_st.nodes:
            fn    = min(child_st.nodes)
            child = _make(pk, fn, 0.0, vis)
            if child:
                root["children"].append(child)

    return root


# ── D3 animation template ─────────────────────────────────────────────────────

_JS_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<script src="https://d3js.org/d3.v7.min.js"></script>
<style>
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%;overflow:hidden;
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','Inter',sans-serif}
body{background:#f2f4f7;display:flex;flex-direction:column}

/* ── Controls bar (matches dashboard filter-card) ────────────── */
#ctrl{
  background:#fff;border-bottom:1px solid #e4e8ef;
  padding:10px 20px;display:flex;align-items:center;gap:12px;
  flex-shrink:0;flex-wrap:wrap;min-height:52px;
}
.btn{
  background:#f2f4f7;border:1px solid #d8dce4;color:#14213d;
  padding:5px 14px;border-radius:20px;cursor:pointer;font-size:12px;
  font-weight:500;transition:all .15s;white-space:nowrap;
}
.btn:hover{background:#e4e8ef;border-color:#b8bcc8}
.btn.primary{background:#14213d;color:#7ec8a4;border-color:#14213d}
.btn.primary:hover{background:#1e2e52}
#date-badge{
  background:#14213d;color:#7ec8a4;
  padding:4px 14px;border-radius:20px;font-size:12px;font-weight:600;
  min-width:120px;text-align:center;letter-spacing:.3px;
}
#prog-track{
  flex:1;height:6px;background:#e4e8ef;border-radius:3px;cursor:pointer;
  position:relative;min-width:80px;
}
#prog-fill{
  height:100%;border-radius:3px;width:0%;
  background:linear-gradient(90deg,#2d7a45,#7ec8a4);transition:width .35s ease;
}
#prog-thumb{
  position:absolute;width:13px;height:13px;background:#2d7a45;
  border-radius:50%;top:50%;left:0%;
  transform:translate(-50%,-50%);transition:left .35s ease;
  box-shadow:0 0 0 3px rgba(45,122,69,.2);
}
#cnt{font-size:11px;color:#9aa4b2;white-space:nowrap}

/* ── SVG area ───────────────────────────────────────────────── */
#svg-wrap{flex:1;min-height:0;position:relative;background:#f8fafb;
  border-bottom:1px solid #e4e8ef;overflow:hidden}
svg{width:100%;height:100%;cursor:grab}
svg:active{cursor:grabbing}
.link{fill:none;stroke-linecap:round;stroke-linejoin:round}

/* ── Overlay stats ──────────────────────────────────────────── */
#stats{
  position:absolute;top:10px;right:14px;display:flex;gap:12px;
  pointer-events:none;
}
.stat{
  background:rgba(255,255,255,.88);backdrop-filter:blur(6px);
  border:1px solid #e4e8ef;border-radius:8px;
  padding:6px 12px;text-align:center;
}
.stat-v{font-size:18px;font-weight:700;color:#14213d;line-height:1}
.stat-l{font-size:9px;color:#9aa4b2;letter-spacing:.8px;margin-top:2px}

/* ── Legend ─────────────────────────────────────────────────── */
#legend{
  position:absolute;bottom:10px;left:14px;
  background:rgba(255,255,255,.88);backdrop-filter:blur(6px);
  border:1px solid #e4e8ef;border-radius:8px;
  padding:8px 12px;display:flex;flex-direction:column;gap:5px;
  pointer-events:none;
}
.lg{display:flex;align-items:center;gap:7px;font-size:10px;color:#667}
.lg-dot{width:10px;height:10px;border-radius:50%;flex-shrink:0}
.lg-line{width:18px;height:3px;border-radius:2px;flex-shrink:0}

/* ── Zoom buttons ───────────────────────────────────────────── */
#zoom-btns{
  position:absolute;bottom:10px;right:14px;display:flex;
  flex-direction:column;gap:4px;
}
.zoom-btn{
  background:rgba(255,255,255,.88);backdrop-filter:blur(6px);
  border:1px solid #e4e8ef;color:#14213d;border-radius:6px;
  width:30px;height:30px;cursor:pointer;font-size:16px;
  display:flex;align-items:center;justify-content:center;
}
.zoom-btn:hover{background:#fff;border-color:#b8bcc8}

/* ── Data table ─────────────────────────────────────────────── */
#tbl-wrap{
  height:190px;overflow-y:auto;flex-shrink:0;background:#fff;
}
table{width:100%;border-collapse:collapse;font-size:11px;
  font-family:'Courier New',monospace}
thead{position:sticky;top:0;background:#fff;z-index:10;
  border-bottom:2px solid #e4e8ef}
th{padding:6px 14px;color:#9aa4b2;text-align:left;font-weight:600;
   font-size:10px;letter-spacing:.5px;text-transform:uppercase}
td{padding:3px 14px;border-bottom:1px solid #f2f4f7;color:#1a1a2e}
.r-new td{color:#2d7a45;font-weight:600;background:#f0faf4}
.r-seen td{color:#667}
</style>
</head>
<body>

<div id="ctrl">
  <button class="btn" id="b-prev">&#9664; Prev</button>
  <button class="btn primary" id="b-play">&#9654; Play</button>
  <button class="btn" id="b-next">Next &#9654;</button>
  <span id="date-badge">—</span>
  <div id="prog-track">
    <div id="prog-fill"></div>
    <div id="prog-thumb"></div>
  </div>
  <span id="cnt"></span>
  <button class="btn" id="b-fit">&#8853; Fit</button>
</div>

<div id="svg-wrap">
  <svg id="tree-svg"></svg>

  <div id="stats">
    <div class="stat"><div class="stat-v" id="sv">0</div><div class="stat-l">VISIBLE</div></div>
    <div class="stat"><div class="stat-v" id="sn">0</div><div class="stat-l">NEW</div></div>
    <div class="stat"><div class="stat-v" id="st2">0</div><div class="stat-l">TOTAL DPs</div></div>
  </div>

  <div id="legend">
    <div class="lg"><div class="lg-line" style="background:#2d7a45"></div>Primary stolon</div>
    <div class="lg"><div class="lg-line" style="background:#4ade80;height:2px"></div>Secondary</div>
    <div class="lg"><div class="lg-line" style="background:#86efac;height:1.5px"></div>Tertiary+</div>
    <div class="lg"><div class="lg-dot" style="background:#d97706;width:10px;height:10px;border-radius:2px"></div>Crown</div>
    <div class="lg"><div class="lg-dot" style="background:#fbbf24;border-radius:1px;width:9px;height:9px"></div>Node (&#10005;)</div>
    <div class="lg"><div class="lg-dot" style="border:2px solid #ef4444;background:none"></div>Daughter (&#9675;)</div>
  </div>

  <div id="zoom-btns">
    <button class="zoom-btn" id="bzi">+</button>
    <button class="zoom-btn" id="bzo">&#8722;</button>
  </div>
</div>

<div id="tbl-wrap">
  <table>
    <thead><tr>
      <th>Plant Code</th><th>Sec Stolons</th><th>Sec DPs</th>
      <th>Ter Stolons</th><th>Ter DPs</th><th>Length&nbsp;cm</th>
    </tr></thead>
    <tbody id="tbody"></tbody>
  </table>
</div>

<script>
const DATA=__DATA__;

// ── Palette ────────────────────────────────────────────────────
const SC=['#2d7a45','#4ade80','#86efac','#bbf7d0'];
const SW=[3,2,1.5,1];
function sc(o){return SC[Math.min(o-1,3)];}
function sw(o){return SW[Math.min(o-1,3)];}

// ── State ──────────────────────────────────────────────────────
let di=0,playing=false,tmr=null;
const IV=2400;

// ── SVG + zoom ─────────────────────────────────────────────────
const wrap=document.getElementById('svg-wrap');
const W=wrap.clientWidth||900, H=wrap.clientHeight||460;

const svg=d3.select('#tree-svg')
  .attr('viewBox',`0 0 ${W} ${H}`)
  .attr('preserveAspectRatio','xMidYMid meet');

// defs: glow + arrowhead
const defs=svg.append('defs');
const f=defs.append('filter').attr('id','glow').attr('x','-40%').attr('y','-40%').attr('width','180%').attr('height','180%');
f.append('feGaussianBlur').attr('stdDeviation','2.5').attr('result','cb');
const fm=f.append('feMerge');
fm.append('feMergeNode').attr('in','cb');
fm.append('feMergeNode').attr('in','SourceGraphic');

const zoom=d3.zoom().scaleExtent([0.05,8])
  .on('zoom',e=>mainG.attr('transform',e.transform));
svg.call(zoom).on('dblclick.zoom',null);

const mainG=svg.append('g');

// ── D3 hierarchy + layout ──────────────────────────────────────
const hier=d3.hierarchy(DATA.tree);
const nLeaves=hier.leaves().length;

// Use nodeSize for consistent spacing regardless of tree width
const DX=Math.max(18, Math.min(36, (W-80)/Math.max(nLeaves,1)));
const DY=90;
d3.tree().nodeSize([DX,DY])(hier);

// Override Y with depth_cm for realistic internode proportions
const maxD=Math.max(...hier.descendants().map(d=>d.data.depth_cm||0));
if(maxD>0){
  const treeH=(H-80)*0.92;
  hier.each(d=>{d.y=40+(d.data.depth_cm/maxD)*treeH;});
}

// ── Draw links ─────────────────────────────────────────────────
const lgen=d3.linkVertical().x(d=>d.x).y(d=>d.y);
const linkG=mainG.append('g').attr('class','links');
const links=linkG.selectAll('path')
  .data(hier.links())
  .join('path')
  .attr('class','link')
  .attr('d',lgen)
  .attr('stroke',d=>sc(d.target.data.order||1))
  .attr('stroke-width',d=>sw(d.target.data.order||1))
  .attr('opacity',0.04);

// ── Draw nodes ─────────────────────────────────────────────────
const nodeG=mainG.append('g').attr('class','nodes');
const ng=nodeG.selectAll('g')
  .data(hier.descendants())
  .join('g')
  .attr('transform',d=>`translate(${d.x},${d.y})`);

// Crown
ng.filter(d=>d.data.type==='crown').each(function(d){
  const g2=d3.select(this);
  g2.append('circle').attr('r',13).attr('fill','#d97706')
    .attr('stroke','#fef3c7').attr('stroke-width',2)
    .attr('filter','url(#glow)');
  g2.append('text').attr('text-anchor','middle').attr('dominant-baseline','central')
    .attr('fill','#fff').attr('font-size','10px').attr('font-weight','700')
    .text(d.data.label||'');
});

// Stolon nodes — × mark
const nonCrown=ng.filter(d=>d.data.type!=='crown');
nonCrown.append('line').attr('class','xa')
  .attr('x1',-3).attr('y1',-3).attr('x2',3).attr('y2',3)
  .attr('stroke','#fbbf24').attr('stroke-width',1.3).attr('opacity',0.04);
nonCrown.append('line').attr('class','xb')
  .attr('x1',3).attr('y1',-3).attr('x2',-3).attr('y2',3)
  .attr('stroke','#fbbf24').attr('stroke-width',1.3).attr('opacity',0.04);

// Daughter plants — ○ ring (offset slightly to right so it doesn't overlap ×)
ng.filter(d=>d.data.has_dp)
  .append('circle').attr('class','dp')
  .attr('cx',6).attr('cy',0)
  .attr('r',5).attr('fill','none')
  .attr('stroke','#ef4444').attr('stroke-width',1.8).attr('opacity',0.04);

// ── Fit view ───────────────────────────────────────────────────
function fitView(anim){
  const b=mainG.node().getBBox();
  if(!b.width||!b.height)return;
  const sc2=Math.min(.95,Math.min((W-60)/(b.width+60),(H-40)/(b.height+40)));
  const tx=W/2-sc2*(b.x+b.width/2);
  const ty=H/2-sc2*(b.y+b.height/2);
  const t=d3.zoomIdentity.translate(tx,ty).scale(sc2);
  (anim?svg.transition().duration(650):svg).call(zoom.transform,t);
}
fitView(false);

// ── Render ─────────────────────────────────────────────────────
function render(anim){
  const dur=anim?450:0;
  const n=DATA.dates.length;

  // Links
  links.transition().duration(dur)
    .attr('opacity',d=>{
      const f=d.target.data.first_date;
      return f>di?.04:(f===di?1:.6);
    })
    .attr('stroke-width',d=>{
      const f=d.target.data.first_date;
      return f===di?sw(d.target.data.order||1)*2:sw(d.target.data.order||1);
    });

  // × marks
  nonCrown.select('.xa').transition().duration(dur)
    .attr('x1',d=>d.data.first_date<=di?-3.5:-2.5)
    .attr('y1',d=>d.data.first_date<=di?-3.5:-2.5)
    .attr('x2',d=>d.data.first_date<=di?3.5:2.5)
    .attr('y2',d=>d.data.first_date<=di?3.5:2.5)
    .attr('stroke',d=>d.data.first_date>di?'#d8dce4':(d.data.first_date===di?'#92400e':'#fbbf24'))
    .attr('stroke-width',d=>d.data.first_date===di?2:1.3)
    .attr('opacity',d=>d.data.first_date>di?.05:1);

  nonCrown.select('.xb').transition().duration(dur)
    .attr('stroke',d=>d.data.first_date>di?'#d8dce4':(d.data.first_date===di?'#92400e':'#fbbf24'))
    .attr('stroke-width',d=>d.data.first_date===di?2:1.3)
    .attr('opacity',d=>d.data.first_date>di?.05:1);

  // ○ daughter rings
  ng.filter(d=>d.data.has_dp).select('.dp').transition().duration(dur)
    .attr('r',d=>d.data.dp_first_date===di?7:5)
    .attr('stroke',d=>d.data.dp_first_date>di?'#d8dce4':(d.data.dp_first_date===di?'#dc2626':'#ef4444'))
    .attr('stroke-width',d=>d.data.dp_first_date===di?2.5:1.8)
    .attr('opacity',d=>d.data.dp_first_date>di?.04:1)
    .attr('filter',d=>d.data.dp_first_date===di?'url(#glow)':null);

  // Entrance pop for newly visible nodes
  if(anim){
    ng.filter(d=>d.data.first_date===di)
      .attr('transform',d=>`translate(${d.x},${d.y}) scale(0)`)
      .transition().duration(400).ease(d3.easeBackOut.overshoot(1.5))
      .attr('transform',d=>`translate(${d.x},${d.y}) scale(1)`);
    ng.filter(d=>d.data.has_dp&&d.data.dp_first_date===di)
      .select('.dp')
      .attr('r',0)
      .transition().duration(400).delay(100).ease(d3.easeBackOut)
      .attr('r',7);
  }

  // Stats
  const dps=hier.descendants().filter(d=>d.data.has_dp);
  document.getElementById('st2').textContent=dps.length;
  document.getElementById('sv').textContent=dps.filter(d=>d.data.dp_first_date<=di).length;
  document.getElementById('sn').textContent=dps.filter(d=>d.data.dp_first_date===di).length;
}

// ── Table ──────────────────────────────────────────────────────
function updateTable(){
  const date=DATA.dates[di];
  const prevSet=new Set();
  DATA.dates.slice(0,di).forEach(d=>(DATA.codes_by_date[d]||[]).forEach(c=>prevSet.add(c)));
  const today=DATA.codes_by_date[date]||[];
  const meas=DATA.timeline_by_date[date]||{};
  const newCs=today.filter(c=>!prevSet.has(c));
  const oldCs=today.filter(c=>prevSet.has(c));
  const rows=[...newCs,...oldCs].map(code=>{
    const m=meas[code];
    const cls=newCs.includes(code)?'r-new':'r-seen';
    const sl=m&&m.stolon_length!=null?m.stolon_length.toFixed(1):'—';
    return`<tr class="${cls}"><td>${code}</td>`+
      `<td>${m?m.sec_stolon:'—'}</td><td>${m?m.sec_daughters:'—'}</td>`+
      `<td>${m?m.ter_stolon:'—'}</td><td>${m?m.ter_daughters:'—'}</td>`+
      `<td>${sl}</td></tr>`;
  });
  document.getElementById('tbody').innerHTML=rows.join('');
}

// ── Controls UI ────────────────────────────────────────────────
function updateUI(){
  const date=DATA.dates[di];
  const fmt=new Date(date).toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'});
  document.getElementById('date-badge').textContent=fmt;
  const n=DATA.dates.length;
  document.getElementById('cnt').textContent=`${di+1} / ${n}`;
  const pct=n>1?di/(n-1)*100:0;
  document.getElementById('prog-fill').style.width=pct+'%';
  document.getElementById('prog-thumb').style.left=pct+'%';
}

function goTo(i,anim){
  di=Math.max(0,Math.min(DATA.dates.length-1,i));
  updateUI();render(!!anim);updateTable();
}

function startPlay(){
  playing=true;
  document.getElementById('b-play').textContent='⏸ Pause';
  document.getElementById('b-play').classList.add('primary');
  if(di>=DATA.dates.length-1)di=-1;
  tmr=setInterval(()=>{
    if(di<DATA.dates.length-1){goTo(di+1,true);}else stopPlay();
  },IV);
}
function stopPlay(){
  playing=false;
  document.getElementById('b-play').textContent='▶ Play';
  if(tmr){clearInterval(tmr);tmr=null;}
}

document.getElementById('b-prev').onclick=()=>{stopPlay();goTo(di-1,true);};
document.getElementById('b-next').onclick=()=>{stopPlay();goTo(di+1,true);};
document.getElementById('b-play').onclick=()=>playing?stopPlay():startPlay();
document.getElementById('b-fit').onclick=()=>fitView(true);
document.getElementById('bzi').onclick=()=>svg.transition().duration(300).call(zoom.scaleBy,1.5);
document.getElementById('bzo').onclick=()=>svg.transition().duration(300).call(zoom.scaleBy,0.67);

document.getElementById('prog-track').addEventListener('click',e=>{
  const r=e.currentTarget.getBoundingClientRect();
  stopPlay();goTo(Math.round((e.clientX-r.left)/r.width*(DATA.dates.length-1)),true);
});

// ── Init ───────────────────────────────────────────────────────
goTo(0,false);
</script>
</body>
</html>"""


# ── Public API ────────────────────────────────────────────────────────────────

def build_js_html(plant: Plant,
                  ws1_cultivar: dict,
                  mother_id: int,
                  canvas_w: int = 900,   # kept for API compat, not used by D3
                  canvas_h: int = 480) -> str:
    """
    Build a self-contained D3-animated HTML page for one mother plant.

    Returns complete HTML string suitable for html.Iframe(srcDoc=...).
    """
    if not plant or not ws1_cultivar:
        return _empty_html("No data available.")

    dates = ws1_cultivar.get("dates", [])
    if not dates:
        return _empty_html("No dates found in Worksheet 1 for this cultivar.")

    codes_by_date  = ws1_cultivar.get("codes_by_date", {})
    ws1_plants_raw = ws1_cultivar.get("plants", {})

    # code → first date index it appears in codes_by_date
    code_first_date: dict[str, int] = {}
    for idx, d in enumerate(dates):
        for code in codes_by_date.get(d, []):
            code_first_date.setdefault(code, idx)

    # Resolve mother
    if mother_id not in plant.mothers and plant.mothers:
        mother_id = min(plant.mothers)

    hierarchy = _to_d3_hierarchy(plant, mother_id, code_first_date, len(dates))
    if not hierarchy.get("children"):
        return _empty_html(f"No stolon data for Mother {mother_id}.")

    # timeline_by_date: {date → {code → measurements}}
    timeline_by_date: dict[str, dict] = {
        d: {code: data[d] for code, data in ws1_plants_raw.items() if d in data}
        for d in dates
    }

    payload = {
        "tree":             hierarchy,
        "dates":            dates,
        "codes_by_date":    codes_by_date,
        "timeline_by_date": timeline_by_date,
    }

    return _JS_TEMPLATE.replace("__DATA__", json.dumps(payload, separators=(",", ":")))


def plant_summary(plant: Plant, mother_id: Optional[int] = None) -> dict:
    """Return summary statistics for display in the UI."""
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


def _empty_html(msg: str = "No data") -> str:
    return (
        "<!DOCTYPE html><html><body style='"
        "margin:0;background:#f2f4f7;display:flex;align-items:center;"
        "justify-content:center;height:100vh;"
        "font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;"
        "color:#9aa4b2;font-size:14px'>"
        f"<p>{msg}</p></body></html>"
    )
