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
    "CAB":   "Cabrillo",
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
<link href="https://fonts.googleapis.com/css2?family=Work+Sans:wght@400;600;700&display=swap" rel="stylesheet">
<script src="https://d3js.org/d3.v7.min.js"></script>
<style>
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%;overflow:hidden;
  font-family:'Work Sans','Segoe UI',system-ui,sans-serif}
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
#cv-badge{
  font-size:12px;font-weight:700;color:#3e5c29;
  background:#ecf4e8;border:1px solid #c5d9b8;
  padding:4px 12px;border-radius:8px;white-space:nowrap;letter-spacing:.01em;
}
#date-range{font-size:10px;color:#8a9e7e;white-space:nowrap;align-self:center;}

#svg-wrap{
  flex:1;min-height:0;position:relative;
  background:linear-gradient(180deg,#3b2c1d 0%,#241a10 55%,#150f09 100%);
  border-bottom:1px solid #e8e3d9;overflow:hidden;
}
svg{width:100%;height:100%;min-height:400px;display:block;cursor:default}

.root{fill:none;stroke-linecap:round;stroke-linejoin:round;pointer-events:none}
.rhair{fill:none;stroke-linecap:round;pointer-events:none}
.leaflet{stroke-width:0.8px;pointer-events:none}
.crown-core{pointer-events:none}
.crown-text{font-size:10px;font-weight:800;fill:#fff;pointer-events:none}
.stem-node{pointer-events:none}
.dp-ring{fill:none;stroke-width:2px;pointer-events:none}
.plantlet{pointer-events:none}
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

#tbl-wrap{
  flex-shrink:0;overflow:hidden;border-top:1px solid #e8e3d9;
  background:#faf8f5;max-height:0;transition:max-height .35s ease;
}
#tbl-wrap.open{max-height:300px;}
#tbl-scroll{overflow-y:auto;max-height:280px;padding:8px 16px 12px;}
#data-tbl{width:100%;border-collapse:collapse;}
#data-tbl th{
  position:sticky;top:0;background:#f0ebe3;padding:5px 8px;
  text-align:left;font-weight:600;border-bottom:1px solid #d4cfc4;
  white-space:nowrap;color:#5c6b52;font-size:10px;
}
#data-tbl td{
  padding:4px 8px;border-bottom:1px solid #f0ebe3;
  white-space:nowrap;font-size:11px;color:#2c3e50;
}
#data-tbl tr:hover td{background:#f4f1ea;}
#data-tbl td:first-child{font-weight:600;color:#3e5c29;}
#tbl-empty{padding:20px;text-align:center;color:#a8b0a0;font-size:11px;display:none;}
.lg{display:flex;align-items:center;gap:5px}
.lg-sw{width:18px;height:4px;border-radius:2px}
.lg-lf{width:11px;height:11px;background:#57a83f;border-radius:50% 50% 50% 0;transform:rotate(45deg);border:1px solid #2f6b25}
.lg-cr{width:10px;height:10px;border-radius:50%;background:#7a4a2a;border:1.5px solid #c8e063}
.lg-dp{width:9px;height:9px;border-radius:50%;border:2px solid #E69F00}
</style>
</head>
<body>

<div id="ctrl" role="toolbar" aria-label="Playback controls">
  <span id="cv-badge">__CULTIVAR__ &middot; M__MOTHER__</span>
  <button class="btn" id="b-prev" aria-label="Previous day">&#9664;</button>
  <button class="btn primary" id="b-play" aria-label="Play">&#9654; Play</button>
  <button class="btn" id="b-next" aria-label="Next day">&#9654;</button>
  <span id="date-badge" role="status" aria-live="polite">-</span>
  <div id="prog-track" role="slider" aria-label="Day timeline"
       aria-valuemin="0" aria-valuenow="0" tabindex="0">
    <div id="prog-fill"></div>
    <div id="prog-thumb"></div>
  </div>
  <span id="cnt"></span>
  <span id="date-range"></span>
  <button class="btn" id="b-export" aria-label="Export SVG" style="margin-left:auto">&#8681; SVG</button>
  <button class="btn" id="b-tbl" aria-expanded="false">&#9660; Data</button>
</div>

<div id="svg-wrap">
  <svg id="tree-svg" aria-label="Strawberry plant growth animation" role="img"></svg>
  <div id="legend">
    <div class="lg"><div class="lg-sw" style="background:#6b4423"></div>Main runner</div>
    <div class="lg"><div class="lg-sw" style="background:#a07845"></div>Branch</div>
    <div class="lg"><div class="lg-sw" style="background:#d8bd97"></div>Fine tip</div>
    <div class="lg"><div class="lg-cr"></div>Mother crown</div>
    <div class="lg"><div class="lg-lf"></div>Daughter plantlet</div>
    <div class="lg"><div class="lg-dp"></div>New this date</div>
  </div>
</div>

<div id="tbl-wrap" role="region" aria-label="Measurement data table">
  <div id="tbl-scroll">
    <table id="data-tbl"></table>
    <div id="tbl-empty">No measurements recorded for this date.</div>
  </div>
</div>

<div id="tooltip"></div>

<script>
const DATA=__DATA__;

/* Root/runner browns by depth: dark near the crown → pale at the fine tips */
const rootCol=t=>d3.interpolateRgb('#6b4423','#d8bd97')(Math.max(0,Math.min(1,t)));
/* Leaf greens for daughter plantlets */
const LFIL=['#4f9e3a','#57a83f','#63b24b','#6fbb58','#7cc466'];
const LSTK=['#2f6b25','#2f6b25','#357a2a','#3a852f','#409034'];
function lf(o){return LFIL[Math.min(o,4)];}
function ls(o){return LSTK[Math.min(o,4)];}


/* Trifoliate strawberry leaf: top leaflet + lower-left + lower-right,
   all three leaflets meeting at (0,0) for clean scaling. */
const TRI=
  "M0,0 C-3,-4 -4,-13 0,-19 C4,-13 3,-4 0,0 Z"+
  "M0,0 C-1,2 -11,-2 -15,5 C-13,13 -4,11 0,0 Z"+
  "M0,0 C1,2 11,-2 15,5 C13,13 4,11 0,0 Z";

/* A rosette: n trifoliate leaves radiating from a point (crown/plantlet). */
function rosette(sel,n,s,fill,stroke){
  const g=sel.append('g').attr('class','rosette');
  for(let i=0;i<n;i++){
    g.append('path').attr('class','leaflet')
      .attr('d',TRI).attr('fill',fill).attr('stroke',stroke)
      .attr('transform',`rotate(${i*360/n}) translate(0,-3) scale(${s})`);
  }
  return g;
}

let di=0,playing=false,tmr=null;
const IV=1600;

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

/* Build hierarchy & TOP-DOWN layout — mother crown at the top, roots flowing
   downward and branching like a tree's root system. */
const hier=d3.hierarchy(DATA.tree);
const maxDepth=d3.max(hier.descendants(),d=>d.depth)||1;
const nLeaves=hier.leaves().length;
const rowH=Math.max(54,Math.min(122,(H-150)/(maxDepth+1)));
const dx=Math.max(12,Math.min(32,(W-100)/Math.max(nLeaves,1)));
const TOP=52;

/* Subtree leaf mass → root thickness (thick trunk near crown, fine at tips) */
hier.eachAfter(d=>{ d._m=d.children?d.children.reduce((s,c)=>s+c._m,0):1; });
const maxM=hier._m||1;
function rw(d){ return 1.0 + 7.0*Math.pow(d._m/maxM,0.55); }

/* Tidy-tree layout reserves a horizontal slot per subtree, so NO two branches
   ever overlap. nodeSize → x = horizontal slot, y = depth (downward). A mild
   depth-proportional horizontal spread makes the roots fan out organically
   while preserving the collision-free ordering. */
d3.tree().nodeSize([dx,rowH])
  .separation((a,b)=>(a.parent===b.parent?1:1.4))(hier);
hier.each(d=>{
  const fan=1+0.55*(d.depth/(maxDepth+0.001));   // deeper roots splay wider
  d.X=d.x*fan; d.Y=d.y+TOP;
});

/* Smooth root link — leaves the parent downward and arrives at the child
   downward (vertical cubic Bézier). Flowing curves that cannot cross because
   the node x-slots are already collision-free. */
function rootPath(s,t){
  const x0=s.X,y0=s.Y,x1=t.X,y1=t.Y;
  const my=(y0+y1)/2;
  return `M${x0},${y0} C${x0},${my} ${x1},${my} ${x1},${y1}`;
}

/* Roots — curved, tapered by subtree mass, coloured dark→pale by depth */
const linkG=mainG.append('g');
const links=linkG.selectAll('path')
  .data(hier.links()).join('path')
  .attr('class','root')
  .attr('d',d=>rootPath(d.source,d.target))
  .attr('stroke',d=>rootCol(d.target.depth/(maxDepth+0.001)))
  .attr('stroke-width',d=>rw(d.target))
  .attr('opacity',0);
/* Prep the grow-downward draw: dash each root by its own length */
links.each(function(d){ const L=this.getTotalLength()||1; d._L=L;
  d3.select(this).attr('stroke-dasharray',L).attr('stroke-dashoffset',L); });

/* Node groups */
const nodeG=mainG.append('g');
const ng=nodeG.selectAll('g')
  .data(hier.descendants()).join('g')
  .attr('transform',d=>`translate(${d.X},${d.Y})`);

/* Mother crown at top — leaf rosette + woody core + label */
ng.filter(d=>d.data.type==='crown').each(function(d){
  const g=d3.select(this);
  rosette(g,7,1.0,'#4f9e3a','#2f6b25');
  g.append('circle').attr('r',9).attr('class','crown-core')
    .attr('fill','#7a4a2a').attr('stroke','#c8e063').attr('stroke-width',2)
    .attr('filter','url(#glow)');
  g.append('text').attr('class','crown-text')
    .attr('text-anchor','middle').attr('dominant-baseline','central')
    .text(d.data.label||'');
});

const nonCrown=ng.filter(d=>d.data.type!=='crown');

/* Fine root hairs fanning downward from growing tips (bare leaf nodes) */
nonCrown.filter(d=>!d.children&&!d.data.has_dp).each(function(d){
  const g=d3.select(this), col=rootCol(1);
  for(let i=-1;i<=1;i++){
    const a=Math.PI/2 + i*0.55;
    g.append('path').attr('class','rhair')
      .attr('d',`M0,0 Q${Math.cos(a)*5},${Math.sin(a)*7} ${Math.cos(a)*9},${Math.sin(a)*13}`)
      .attr('stroke',col).attr('stroke-width',0.9).attr('opacity',0);
  }
});

/* Bare internode nodes — small thickening on the root */
nonCrown.filter(d=>!d.data.has_dp).append('circle')
  .attr('class','stem-node').attr('r',1.8)
  .attr('fill',d=>rootCol(d.depth/(maxDepth+0.001))).attr('opacity',0);

/* Daughter plantlets — a small rooted rosette (a new little plant) */
const plantlet=nonCrown.filter(d=>d.data.has_dp).append('g')
  .attr('class','plantlet').attr('opacity',0);
plantlet.each(function(d){
  const g=d3.select(this);
  rosette(g,5,0.46,lf(d.data.order),ls(d.data.order));
  g.append('circle').attr('r',2.8)
    .attr('fill','#8a5a34').attr('stroke','#e9c46a').attr('stroke-width',1);
});
/* Amber "rooted this date" ring around plantlets */
nonCrown.filter(d=>d.data.has_dp).append('circle').attr('class','dp-ring')
  .attr('r',8).attr('stroke','#E69F00').attr('opacity',0);

/* Invisible hit areas for tooltips */
ng.append('circle').attr('class','hit-area').attr('r',12)
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
  try{
    const days=Math.round((new Date(iso)-new Date(DATA.dates[0]))/86400000);
    return 'Day '+days;
  }catch(e){return iso;}
}

function showTip(event,d){
  let html='';
  if(d.data.type==='crown'){
    html=`<div class="tt-code">${d.data.label||'Crown'}</div>
      <div class="tt-date">Mother plant, root of stolon network</div>`;
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
  const dur=anim?680:0;

  /* Roots grow downward from the crown (dash draw), fade in on arrival */
  links.transition().duration(dur).ease(d3.easeCubicOut)
    .attr('opacity',d=>{
      const f=d.target.data.first_date;
      return f>di?0:(f===di?1:0.92);
    })
    .attr('stroke-dashoffset',d=>d.target.data.first_date>di?d._L:0)
    .attr('stroke-width',d=>{
      const w=rw(d.target);
      return d.target.data.first_date===di?w*1.3:w;
    });

  /* Bare root thickenings appear with their segment */
  nonCrown.select('.stem-node').transition().duration(dur)
    .attr('opacity',d=>d.data.first_date>di?0:0.8);

  /* Root hairs fade in at grown tips */
  nonCrown.selectAll('.rhair').transition().duration(dur)
    .attr('opacity',function(){
      const d=d3.select(this.parentNode).datum();
      return d.data.first_date>di?0:0.5;
    });

  /* Daughter plantlets unfurl when they root */
  const pl=nonCrown.select('.plantlet');
  pl.transition().duration(dur)
    .attr('opacity',d=>d.data.dp_first_date>di?0:1)
    .attr('transform',d=>d.data.dp_first_date>di?'scale(0.01)':'scale(1)');

  /* Amber "rooted this date" ring */
  nonCrown.select('.dp-ring').transition().duration(dur)
    .attr('opacity',d=>d.data.dp_first_date===di?1:0)
    .attr('r',d=>d.data.dp_first_date===di?10:8)
    .attr('filter',d=>d.data.dp_first_date===di?'url(#glow)':null);

  /* Elastic pop for plantlets rooting this date */
  if(anim){
    pl.filter(d=>d.data.dp_first_date===di)
      .attr('transform','scale(0.05)')
      .transition().duration(640).ease(d3.easeElastic.period(0.5))
      .attr('transform','scale(1)');
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
  if(tblOpen)buildTable();
}

/* ── Data Table ─────────────────────────────────────────────────── */
let tblOpen=false;

function buildTable(){
  const date=DATA.dates[di];
  const recs=(DATA.timeline_by_date&&DATA.timeline_by_date[date])||{};
  const codes=Object.keys(recs).sort();
  const tbl=document.getElementById('data-tbl');
  const empty=document.getElementById('tbl-empty');
  if(!codes.length){
    tbl.innerHTML='';tbl.style.display='none';
    empty.style.display='block';
    empty.textContent='No measurements recorded for '+fmtDate(date)+'.';
    return;
  }
  tbl.style.display='';empty.style.display='none';
  const COLS=[
    ['code','Code'],
    ['stolon_length','Stolon Length (cm)'],
    ['sec_stolon','Sec Stolons'],
    ['sec_daughters','Sec Daughters'],
    ['ter_stolon','Ter Stolons'],
    ['ter_daughters','Ter Daughters'],
    ['quart_stolon','Qrt Stolons'],
    ['quart_daughters','Qrt Daughters'],
  ];
  /* only show columns that have at least one non-zero value */
  const active=COLS.filter(([k])=>k==='code'||codes.some(c=>{
    const v=recs[c][k];return v!=null&&v!==0;
  }));
  let h='<thead><tr>'+active.map(([,l])=>`<th>${l}</th>`).join('')+'</tr></thead><tbody>';
  for(const code of codes){
    const r=recs[code];
    h+='<tr>'+active.map(([k])=>{
      if(k==='code')return`<td>${code}</td>`;
      const v=r[k];
      if(v==null)return'<td style="color:#ccc">-</td>';
      if(typeof v==='number')return`<td>${Number.isInteger(v)?v:v.toFixed(1)}</td>`;
      return`<td>${v}</td>`;
    }).join('')+'</tr>';
  }
  h+='</tbody>';
  tbl.innerHTML=h;
}

document.getElementById('b-tbl').onclick=()=>{
  tblOpen=!tblOpen;
  document.getElementById('tbl-wrap').classList.toggle('open',tblOpen);
  const btn=document.getElementById('b-tbl');
  btn.textContent=(tblOpen?'\u25b2':'\u25bc')+' Data Table';
  btn.setAttribute('aria-expanded',String(tblOpen));
  if(tblOpen)buildTable();
};

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
  s.textContent='.root{fill:none;stroke-linecap:round}.rhair{fill:none}.leaflet{stroke-width:0.8px}.dp-ring{fill:none;stroke-width:2px}';
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

/* Date range label */
if(DATA.dates.length>1){
  const dr=document.getElementById('date-range');
  dr.textContent=fmtDate(DATA.dates[0])+' → '+fmtDate(DATA.dates[DATA.dates.length-1]);
}

/* Tick marks on progress bar — one per date */
const pt=document.getElementById('prog-track');
if(DATA.dates.length>2){
  DATA.dates.forEach((_,i)=>{
    if(i===0||i===DATA.dates.length-1)return;
    const p=i/(DATA.dates.length-1)*100;
    const t=document.createElement('div');
    t.style.cssText=`position:absolute;left:${p}%;top:50%;`+
      `transform:translate(-50%,-50%);width:1.5px;height:5px;`+
      `background:rgba(93,138,62,.35);border-radius:1px;pointer-events:none`;
    pt.appendChild(t);
  });
}

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

    return (
        _JS_TEMPLATE
        .replace("__DATA__",     json.dumps(payload, separators=(",", ":")))
        .replace("__CULTIVAR__", plant.cultivar)
        .replace("__MOTHER__",   str(mother_id))
    )


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


def _count_hierarchy(node: dict) -> tuple[int, int]:
    """Count (daughter plants, distinct stolons) actually present in a rendered
    D3 hierarchy subtree."""
    dp = 0
    stolons: set = set()
    stack = [node]
    while stack:
        n = stack.pop()
        if n.get("has_dp"):
            dp += 1
        if n.get("type") == "node":
            stolons.add("_".join(n["id"].split("_")[:3]))
        stack.extend(n.get("children", []))
    return dp, len(stolons)


def validate_render(plant: Plant, mother_id: int,
                    code_first_date: dict, n_dates: int) -> dict:
    """Confirm the rendered hierarchy for one mother reproduces the parsed
    daughter/stolon counts exactly. Returns a dict the UI can display; `ok`
    is False if the animation would show a different structure than the data.
    """
    hier = _to_d3_hierarchy(plant, mother_id, code_first_date, n_dates)
    r_dp, r_st = _count_hierarchy(hier)
    p_dp, p_st = plant.dp_count(mother_id), plant.stolon_count(mother_id)
    return {
        "ok":               (r_dp == p_dp and r_st == p_st),
        "parsed_daughters": p_dp, "rendered_daughters": r_dp,
        "parsed_stolons":   p_st, "rendered_stolons":   r_st,
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
