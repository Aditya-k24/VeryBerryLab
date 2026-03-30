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
<title>Strawberry Plant Architecture</title>
<script src="https://d3js.org/d3.v7.min.js"></script>
<style>
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%;overflow:hidden;
  font-family:'Segoe UI',Tahoma,Geneva,Verdana,-apple-system,sans-serif}
body{background:#f4f1ea;color:#2c3e50;display:flex;flex-direction:column}

#ctrl{
  background:#faf8f5;border-bottom:1px solid #e8e3d9;
  padding:10px 16px;display:flex;align-items:center;gap:10px;
  flex-shrink:0;flex-wrap:wrap;min-height:50px;
}
.btn{
  background:#fff;border:1px solid #d4cfc4;color:#3e5c29;
  padding:5px 12px;border-radius:8px;cursor:pointer;font-size:12px;
  font-weight:600;transition:background .15s,border-color .15s;white-space:nowrap;
}
.btn:hover{background:#f0ebe3;border-color:#b8b0a2}
.btn:focus{outline:2px solid #5d8a3e;outline-offset:2px}
.btn.primary{background:#3e5c29;color:#f4f1ea;border-color:#3e5c29}
.btn.primary:hover{background:#2d4420}
#date-badge{
  background:#ecf4e8;color:#2d4a1c;padding:5px 14px;border-radius:8px;
  font-size:13px;font-weight:700;min-width:130px;text-align:center;
  border:1px solid #c5d9b8;
}
#prog-track{
  flex:1;height:7px;background:#e0dcd4;border-radius:4px;cursor:pointer;
  position:relative;min-width:80px;
}
#prog-track:focus{outline:2px solid #5d8a3e;outline-offset:3px}
#prog-fill{
  height:100%;border-radius:4px;width:0%;
  background:linear-gradient(90deg,#5d8a3e,#7bb242);transition:width .35s ease;
}
#prog-thumb{
  position:absolute;width:12px;height:12px;background:#5d8a3e;
  border-radius:50%;top:50%;left:0%;
  transform:translate(-50%,-50%);transition:left .35s ease;
  box-shadow:0 0 0 2px rgba(93,138,62,.3);
}
#cnt{font-size:11px;color:#6b7d62;white-space:nowrap}
#hint{font-size:10px;color:#a8b0a0;white-space:nowrap}

#svg-wrap{
  flex:1;min-height:0;position:relative;
  background:linear-gradient(180deg,#faf8f5 0%,#f0ebe3 100%);
  border-bottom:1px solid #e8e3d9;overflow:hidden;
}
svg{width:100%;height:100%;min-height:400px;display:block;cursor:default}

.link{fill:none;stroke-linecap:round;stroke-linejoin:round;pointer-events:none}
.leaflet{stroke-width:0.9px;pointer-events:none}
.crown-circle{stroke-width:2px;pointer-events:none}
.crown-text{font-size:11px;font-weight:800;fill:#fff;pointer-events:none}
.dp-ring{fill:none;stroke-width:2px;pointer-events:none}
.hit-area{fill:transparent;cursor:pointer;stroke:none}

#tooltip{
  position:fixed;display:none;
  background:rgba(22,32,18,.93);color:#e4f2db;
  border:1px solid rgba(140,190,110,.25);border-radius:10px;
  padding:10px 14px;font-size:11px;line-height:1.65;
  pointer-events:none;z-index:9999;max-width:230px;
  box-shadow:0 4px 18px rgba(0,0,0,.3);
}
.tt-code{font-weight:800;font-size:12px;color:#9de05a;margin-bottom:5px}
.tt-row{display:flex;justify-content:space-between;gap:12px;color:#b8d4a0}
.tt-row span:last-child{color:#fff;font-weight:600}
.tt-date{color:#82a070;font-size:10px;margin-top:5px;border-top:1px solid rgba(255,255,255,.08);padding-top:4px}

#legend{
  position:absolute;bottom:10px;left:50%;transform:translateX(-50%);
  background:rgba(255,255,255,.92);border:1px solid #e8e3d9;border-radius:10px;
  padding:6px 14px;display:flex;flex-wrap:wrap;gap:10px;justify-content:center;
  pointer-events:none;font-size:10px;color:#5c6b52;max-width:96%;
  box-shadow:0 1px 3px rgba(0,0,0,.06);
}
.lg{display:flex;align-items:center;gap:5px}
.lg-sw{width:18px;height:4px;border-radius:2px}
.lg-lf{width:10px;height:13px;background:#7bb242;border-radius:50%;border:1px solid #4a752c}
.lg-cr{width:9px;height:9px;border-radius:50%;background:#3e5c29;border:1.5px solid #c8e063}
.lg-dp{width:9px;height:9px;border-radius:50%;border:2px solid #E69F00}
</style>
</head>
<body>

<div id="ctrl" role="toolbar" aria-label="Playback controls">
  <button class="btn" id="b-prev" aria-label="Previous date">&#9664; Prev</button>
  <button class="btn primary" id="b-play" aria-label="Play">&#9654; Play</button>
  <button class="btn" id="b-next" aria-label="Next date">Next &#9654;</button>
  <span id="date-badge" role="status" aria-live="polite">—</span>
  <div id="prog-track" role="slider" aria-label="Date timeline"
       aria-valuemin="0" aria-valuenow="0" tabindex="0">
    <div id="prog-fill"></div>
    <div id="prog-thumb"></div>
  </div>
  <span id="cnt"></span>
  <button class="btn" id="b-export" aria-label="Export SVG">&#8681; SVG</button>
  <span id="hint">&#8592; &#8594; Space</span>
</div>

<div id="svg-wrap">
  <svg id="tree-svg" aria-label="Strawberry plant growth animation" role="img"></svg>
  <div id="legend">
    <div class="lg"><div class="lg-sw" style="background:#009E73"></div>Primary</div>
    <div class="lg"><div class="lg-sw" style="background:#0072B2"></div>Secondary</div>
    <div class="lg"><div class="lg-sw" style="background:#D55E00"></div>Tertiary</div>
    <div class="lg"><div class="lg-sw" style="background:#CC79A7"></div>Quaternary+</div>
    <div class="lg"><div class="lg-lf"></div>Node / leaf</div>
    <div class="lg"><div class="lg-dp"></div>Daughter plant</div>
    <div class="lg"><div class="lg-cr"></div>Crown</div>
  </div>
</div>

<div id="tooltip"></div>

<script>
const DATA=__DATA__;

/* Okabe-Ito colorblind-safe palette indexed by stolon order */
const OCOL=['#4a7c59','#009E73','#0072B2','#D55E00','#CC79A7'];
const OWID=[6,4.2,3.2,2.4,1.8];
const LFIL=['#6aaa3e','#7bb242','#5a9de0','#e87a3e','#d982c0'];
const LSTK=['#4a752c','#4a752c','#3870b0','#b05020','#9a5090'];

function oc(o){return OCOL[Math.min(o,4)];}
function ow(o){return OWID[Math.min(o,4)];}
function lf(o){return LFIL[Math.min(o,4)];}
function ls(o){return LSTK[Math.min(o,4)];}

/* Trifoliate leaf path: top leaflet + lower-left + lower-right
   All three leaflets meet at (0,0) for clean scaling. */
const TRI=
  "M0,0 C-3,-4 -4,-13 0,-19 C4,-13 3,-4 0,0 Z"+
  "M0,0 C-1,2 -11,-2 -15,5 C-13,13 -4,11 0,0 Z"+
  "M0,0 C1,2 11,-2 15,5 C13,13 4,11 0,0 Z";

let di=0,playing=false,tmr=null;
const IV=2200;

const wrap=document.getElementById('svg-wrap');
const W=wrap.clientWidth||900;
const H=Math.max(420,wrap.clientHeight||520);

const svg=d3.select('#tree-svg')
  .attr('viewBox',`0 0 ${W} ${H}`)
  .attr('preserveAspectRatio','xMidYMid meet');

/* Glow filter */
const defs=svg.append('defs');
const gf=defs.append('filter').attr('id','glow')
  .attr('x','-50%').attr('y','-50%').attr('width','200%').attr('height','200%');
gf.append('feGaussianBlur').attr('stdDeviation','2.5').attr('result','blur');
const fm=gf.append('feMerge');
fm.append('feMergeNode').attr('in','blur');
fm.append('feMergeNode').attr('in','SourceGraphic');

const mainG=svg.append('g');

/* Build D3 hierarchy & layout */
const hier=d3.hierarchy(DATA.tree);
const nLeaves=hier.leaves().length;
const DX=Math.max(18,Math.min(38,(W-100)/Math.max(nLeaves,1)));
d3.tree().nodeSize([DX,88])(hier);

/* Override y with actual internode depth_cm for biological accuracy */
const maxD=Math.max(...hier.descendants().map(d=>d.data.depth_cm||0));
if(maxD>0){
  const treeH=(H-100)*0.88;
  hier.each(d=>{d.y=52+(d.data.depth_cm/maxD)*treeH;});
}

/* Curved Bézier stolon links, colored by stolon order */
const lgen=d3.linkVertical().x(d=>d.x).y(d=>d.y);
const linkG=mainG.append('g');
const links=linkG.selectAll('path')
  .data(hier.links())
  .join('path')
  .attr('class','link')
  .attr('d',lgen)
  .attr('stroke',d=>oc(d.target.data.order))
  .attr('stroke-width',d=>ow(d.target.data.order))
  .attr('opacity',0.04);

/* Node groups */
const nodeG=mainG.append('g');
const ng=nodeG.selectAll('g')
  .data(hier.descendants())
  .join('g')
  .attr('transform',d=>`translate(${d.x},${d.y})`);

/* Crown nodes */
ng.filter(d=>d.data.type==='crown').each(function(d){
  const g=d3.select(this);
  g.append('circle').attr('r',14).attr('class','crown-circle')
    .attr('fill','#3e5c29').attr('stroke','#c8e063').attr('filter','url(#glow)');
  g.append('text').attr('class','crown-text')
    .attr('text-anchor','middle').attr('dominant-baseline','central')
    .text(d.data.label||'');
});

/* Trifoliate leaf clusters for non-crown nodes, colored by stolon order */
const nonCrown=ng.filter(d=>d.data.type!=='crown');
const leafG=nonCrown.append('g').attr('class','leaf-cluster').attr('opacity',0.04);
leafG.append('path').attr('class','leaflet')
  .attr('d',TRI)
  .attr('fill',d=>lf(d.data.order))
  .attr('stroke',d=>ls(d.data.order))
  .attr('transform','scale(0.72)');

/* Daughter plant ring (amber) */
nonCrown.filter(d=>d.data.has_dp)
  .append('circle').attr('class','dp-ring')
  .attr('cx',11).attr('cy',1).attr('r',5)
  .attr('stroke','#E69F00').attr('opacity',0.04);

/* Invisible hit areas for tooltips — cover crown + leaf nodes */
ng.append('circle').attr('class','hit-area').attr('r',16)
  .on('mouseover',showTip)
  .on('mousemove',moveTip)
  .on('mouseout',hideTip);

function fitView(){
  const b=mainG.node().getBBox();
  if(!b.width||!b.height)return;
  const sc=Math.min(.92,Math.min((W-48)/(b.width+48),(H-48)/(b.height+48)));
  const tx=W/2-sc*(b.x+b.width/2);
  const ty=H/2-sc*(b.y+b.height/2);
  mainG.attr('transform',`translate(${tx},${ty}) scale(${sc})`);
}
fitView();

/* ── Tooltip ──────────────────────────────────────────────────── */
const ttEl=document.getElementById('tooltip');

function fmtDate(iso){
  try{return new Date(iso).toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'});}
  catch(e){return iso;}
}

function showTip(event,d){
  let html='';
  if(d.data.type==='crown'){
    html=`<div class="tt-code">${d.data.label||'Crown'}</div>
      <div class="tt-date">Mother plant — root of stolon network</div>`;
  } else {
    const code=d.data.code||'';
    const oNames=['','Primary','Secondary','Tertiary','Quaternary'];
    const oName=oNames[Math.min(d.data.order,4)]||'Stolon';
    const fd=DATA.dates[d.data.first_date]||'';
    const dpfd=d.data.has_dp?(DATA.dates[d.data.dp_first_date]||''):'';
    const curDate=DATA.dates[di]||'';
    const rec=(DATA.timeline_by_date&&DATA.timeline_by_date[curDate])?DATA.timeline_by_date[curDate][code]||null:null;

    if(code)html+=`<div class="tt-code">${code}</div>`;
    html+=`<div class="tt-row"><span>Stolon order</span><span>${oName}</span></div>`;
    html+=`<div class="tt-row"><span>Depth</span><span>${d.data.depth_cm.toFixed(1)} cm</span></div>`;
    if(fd)html+=`<div class="tt-row"><span>First seen</span><span>${fmtDate(fd)}</span></div>`;
    if(d.data.has_dp&&dpfd)html+=`<div class="tt-row"><span>Daughter rooted</span><span>${fmtDate(dpfd)}</span></div>`;
    if(rec){
      if(rec.stolon_length!=null)html+=`<div class="tt-row"><span>Stolon length</span><span>${rec.stolon_length.toFixed(1)} cm</span></div>`;
      if(rec.sec_stolon)html+=`<div class="tt-row"><span>Sec stolons</span><span>${rec.sec_stolon}</span></div>`;
      if(rec.sec_daughters)html+=`<div class="tt-row"><span>Sec daughters</span><span>${rec.sec_daughters}</span></div>`;
      if(rec.ter_stolon)html+=`<div class="tt-row"><span>Ter stolons</span><span>${rec.ter_stolon}</span></div>`;
      if(rec.ter_daughters)html+=`<div class="tt-row"><span>Ter daughters</span><span>${rec.ter_daughters}</span></div>`;
      if(rec.quart_stolon)html+=`<div class="tt-row"><span>Quart stolons</span><span>${rec.quart_stolon}</span></div>`;
      if(rec.quart_daughters)html+=`<div class="tt-row"><span>Quart daughters</span><span>${rec.quart_daughters}</span></div>`;
    }
    if(curDate)html+=`<div class="tt-date">@ ${fmtDate(curDate)}</div>`;
  }
  ttEl.innerHTML=html;
  ttEl.style.display='block';
  moveTip(event);
}

function moveTip(event){
  const x=event.clientX+14, y=event.clientY-28;
  ttEl.style.left=Math.min(x,window.innerWidth-250)+'px';
  ttEl.style.top=Math.max(y,8)+'px';
}

function hideTip(){ttEl.style.display='none';}

/* ── Render ───────────────────────────────────────────────────── */
function render(anim){
  const dur=anim?480:0;

  /* Links: color by stolon order, highlight new arrivals */
  links.transition().duration(dur)
    .attr('opacity',d=>{
      const f=d.target.data.first_date;
      return f>di?0.04:(f===di?1:0.65);
    })
    .attr('stroke-width',d=>{
      const w=ow(d.target.data.order);
      return d.target.data.first_date===di?w*1.3:w;
    });

  /* Leaf clusters */
  leafG.transition().duration(dur)
    .attr('opacity',d=>d.data.first_date>di?0.04:1);

  leafG.select('.leaflet').transition().duration(dur)
    .attr('transform',d=>d.data.first_date>di?'scale(0.06)':'scale(0.72)');

  /* Daughter rings */
  nonCrown.filter(d=>d.data.has_dp).select('.dp-ring').transition().duration(dur)
    .attr('r',d=>d.data.dp_first_date===di?7:5)
    .attr('stroke',d=>d.data.dp_first_date>di?'#e0dcd4':(d.data.dp_first_date===di?'#E69F00':'#c8a000'))
    .attr('stroke-width',d=>d.data.dp_first_date===di?2.6:2)
    .attr('opacity',d=>d.data.dp_first_date>di?0.04:1)
    .attr('filter',d=>d.data.dp_first_date===di?'url(#glow)':null);

  /* Entrance animations for newly appearing elements */
  if(anim){
    leafG.filter(d=>d.data.first_date===di).select('.leaflet')
      .attr('transform','scale(0.05)')
      .transition().duration(560).ease(d3.easeElastic.period(0.45))
      .attr('transform','scale(0.72)');

    nonCrown.filter(d=>d.data.has_dp&&d.data.dp_first_date===di).select('.dp-ring')
      .attr('r',0)
      .transition().duration(400).delay(100).ease(d3.easeBackOut)
      .attr('r',7);
  }
}

/* ── UI ───────────────────────────────────────────────────────── */
function updateUI(){
  const date=DATA.dates[di];
  const fmt=fmtDate(date);
  document.getElementById('date-badge').textContent=fmt;
  const n=DATA.dates.length;
  document.getElementById('cnt').textContent=`${di+1} / ${n}`;
  const pct=n>1?di/(n-1)*100:0;
  document.getElementById('prog-fill').style.width=pct+'%';
  document.getElementById('prog-thumb').style.left=pct+'%';
  const t=document.getElementById('prog-track');
  t.setAttribute('aria-valuenow',di);
  t.setAttribute('aria-valuemax',n-1);
  t.setAttribute('aria-valuetext',fmt);
}

function goTo(i,anim){
  di=Math.max(0,Math.min(DATA.dates.length-1,i));
  updateUI();render(!!anim);
}

function startPlay(){
  playing=true;
  const b=document.getElementById('b-play');
  b.textContent='\u23f8 Pause';b.setAttribute('aria-label','Pause');b.classList.add('primary');
  if(di>=DATA.dates.length-1)di=-1;
  tmr=setInterval(()=>{
    if(di<DATA.dates.length-1)goTo(di+1,true); else stopPlay();
  },IV);
}

function stopPlay(){
  playing=false;
  const b=document.getElementById('b-play');
  b.textContent='\u25b6 Play';b.setAttribute('aria-label','Play');b.classList.remove('primary');
  if(tmr){clearInterval(tmr);tmr=null;}
}

/* ── Export SVG ───────────────────────────────────────────────── */
function exportSVG(){
  const el=document.getElementById('tree-svg');
  const clone=el.cloneNode(true);
  clone.setAttribute('xmlns','http://www.w3.org/2000/svg');
  const s=document.createElement('style');
  s.textContent='.link{fill:none;stroke-linecap:round}.leaflet{stroke-width:0.9px}.crown-circle{stroke-width:2px}.dp-ring{fill:none;stroke-width:2px}';
  clone.insertBefore(s,clone.firstChild);
  const blob=new Blob([new XMLSerializer().serializeToString(clone)],{type:'image/svg+xml'});
  const url=URL.createObjectURL(blob);
  const a=document.createElement('a');
  a.href=url;a.download='plant_architecture.svg';a.click();
  URL.revokeObjectURL(url);
}

/* ── Events ───────────────────────────────────────────────────── */
document.getElementById('b-prev').onclick=()=>{stopPlay();goTo(di-1,true);};
document.getElementById('b-next').onclick=()=>{stopPlay();goTo(di+1,true);};
document.getElementById('b-play').onclick=()=>playing?stopPlay():startPlay();
document.getElementById('b-export').onclick=exportSVG;

document.getElementById('prog-track').addEventListener('click',e=>{
  const r=e.currentTarget.getBoundingClientRect();
  stopPlay();goTo(Math.round((e.clientX-r.left)/r.width*(DATA.dates.length-1)),true);
});

/* Keyboard: arrow keys on progress track */
document.getElementById('prog-track').addEventListener('keydown',e=>{
  if(e.key==='ArrowLeft'){stopPlay();goTo(di-1,true);e.preventDefault();}
  if(e.key==='ArrowRight'){stopPlay();goTo(di+1,true);e.preventDefault();}
});

/* Global keyboard: arrows + space */
document.addEventListener('keydown',e=>{
  const tag=e.target.tagName;
  if(tag==='INPUT'||tag==='BUTTON')return;
  if(e.key==='ArrowLeft'){stopPlay();goTo(di-1,true);e.preventDefault();}
  else if(e.key==='ArrowRight'){stopPlay();goTo(di+1,true);e.preventDefault();}
  else if(e.key===' '){playing?stopPlay():startPlay();e.preventDefault();}
});

window.addEventListener('resize',fitView);

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
