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


# ── Top-down layout ───────────────────────────────────────────────────────────

def _compute_layout(plant: Plant, mother_id: int,
                    canvas_w: int, canvas_h: int,
                    code_first_date: dict, n_dates: int
                    ) -> tuple[list[dict], int, int]:
    """
    Top-down tree layout for one mother plant.
    Returns (elements, actual_w, actual_h).
    """
    MARGIN   = 55
    CROWN_Y  = 42

    sys.setrecursionlimit(max(8000, sys.getrecursionlimit()))

    pkeys = sorted(k for k in plant.stolons if k[0] == mother_id and k[1] == 1)
    if not pkeys:
        return [], canvas_w, canvas_h

    # ── Step 1 – count leaf slots ─────────────────────────────────────────
    leaf_count: dict[tuple, int] = {}

    def count(sk: tuple) -> int:
        if sk in leaf_count:
            return leaf_count[sk]
        st = plant.stolons.get(sk)
        if st is None:
            leaf_count[sk] = 1
            return 1
        c = 0
        for n in sorted(st.nodes):
            nd = st.nodes[n]
            if nd.child_stolons:
                for ck in nd.child_stolons:
                    c += count(ck)
            else:
                c += 1          # terminal node = 1 leaf slot
        leaf_count[sk] = max(c, 1)
        return leaf_count[sk]

    for pk in pkeys:
        count(pk)

    total_leaves = sum(leaf_count.get(pk, 1) for pk in pkeys)
    actual_w = max(canvas_w,
                   min(CANVAS_W_MAX, int(2 * MARGIN + total_leaves * LEAF_W_MIN)))
    leaf_w   = (actual_w - 2 * MARGIN) / max(total_leaves, 1)

    # ── Step 2 – max depth for Y scaling ─────────────────────────────────
    depth_samples: list[float] = []

    def get_depth(sk: tuple, d: float = 0.0) -> None:
        """Accumulate internode lengths within each stolon correctly."""
        st = plant.stolons.get(sk)
        if st is None:
            depth_samples.append(d)
            return
        cum = d
        for n in sorted(st.nodes):
            cum += st.ilengths.get(n, DEFAULT_INTERNODE_CM)  # accumulate!
            nd = st.nodes[n]
            if nd.child_stolons:
                for ck in nd.child_stolons:
                    get_depth(ck, cum)
            else:
                depth_samples.append(cum)

    for pk in pkeys:
        get_depth(pk)

    max_depth = max(depth_samples) if depth_samples else 1.0
    y_scale   = (canvas_h - CROWN_Y - 40) / max_depth

    # ── Step 3a – assign X positions (DFS, leaf-counter) ─────────────────
    node_x: dict[tuple, float] = {}
    leaf_idx = [0]

    def assign_x(sk: tuple) -> None:
        st = plant.stolons.get(sk)
        if st is None:
            return
        for n in sorted(st.nodes):
            nd = st.nodes[n]
            if nd.child_stolons:
                start = leaf_idx[0]
                for ck in nd.child_stolons:
                    assign_x(ck)
                end = leaf_idx[0]
                node_x[(sk, n)] = MARGIN + (start + end) / 2 * leaf_w
            else:
                node_x[(sk, n)] = MARGIN + (leaf_idx[0] + 0.5) * leaf_w
                leaf_idx[0] += 1

    for pk in pkeys:
        assign_x(pk)

    # ── Step 3b – assign Y positions (BFS from crown) ────────────────────
    node_y: dict[tuple, float] = {}
    stolon_origin_y: dict[tuple, float] = {pk: CROWN_Y for pk in pkeys}

    queue: deque = deque(pkeys)
    visited: set = set()
    while queue:
        sk = queue.popleft()
        if sk in visited:
            continue
        visited.add(sk)
        st = plant.stolons.get(sk)
        if st is None:
            continue
        cum_y = stolon_origin_y.get(sk, CROWN_Y)
        for n in sorted(st.nodes):
            cum_y += st.ilengths.get(n, DEFAULT_INTERNODE_CM) * y_scale
            node_y[(sk, n)] = cum_y
            nd = st.nodes[n]
            for ck in nd.child_stolons:
                stolon_origin_y[ck] = cum_y
                queue.append(ck)

    # ── Step 4 – first-date helpers ───────────────────────────────────────
    def fd(code: str) -> int:
        return code_first_date.get(code, n_dates)

    subtree_fd_memo: dict[tuple, int] = {}

    def subtree_fd(sk: tuple) -> int:
        if sk in subtree_fd_memo:
            return subtree_fd_memo[sk]
        st = plant.stolons.get(sk)
        if st is None:
            subtree_fd_memo[sk] = n_dates
            return n_dates
        best = n_dates
        for n in st.nodes:
            nd = st.nodes[n]
            if nd.daughter_code:
                best = min(best, fd(nd.daughter_code))
            for ck in nd.child_stolons:
                best = min(best, subtree_fd(ck))
        subtree_fd_memo[sk] = best
        return best

    # Precompute subtree first_dates for all stolons
    for sk in plant.stolons:
        if sk[0] == mother_id:
            subtree_fd(sk)

    # ── Step 5 – build element list ───────────────────────────────────────
    crown_x   = actual_w / 2.0
    elements: list[dict] = [{
        "type": "crown", "x": crown_x, "y": CROWN_Y,
        "label": f"M{mother_id}", "first_date": 0,
    }]

    def build(sk: tuple, par_x: float, par_y: float) -> None:
        st = plant.stolons.get(sk)
        if st is None:
            return

        # All structural elements in this stolon become visible when ANY
        # descendant daughter first appears — ensures connected paths.
        sk_fd = subtree_fd_memo.get(sk, n_dates)

        prev_x, prev_y = par_x, par_y

        for n in sorted(st.nodes):
            nd  = st.nodes[n]
            nx  = node_x.get((sk, n), crown_x)
            ny  = node_y.get((sk, n), prev_y + 10.0)

            # Segment and node mark — visible when stolon has any descendant
            elements.append({
                "type": "segment",
                "x1": float(prev_x), "y1": float(prev_y),
                "x2": float(nx),     "y2": float(ny),
                "order": st.key[1],  "first_date": sk_fd,
            })
            elements.append({
                "type": "node",
                "x": float(nx), "y": float(ny),
                "first_date": sk_fd,
            })

            # Daughter ○ — appears on its own specific first_date
            if nd.daughter_code:
                elements.append({
                    "type": "daughter",
                    "x": float(nx), "y": float(ny),
                    "code": nd.daughter_code,
                    "first_date": fd(nd.daughter_code),
                })

            # Recurse into child stolons
            for ck in nd.child_stolons:
                build(ck, nx, ny)

            prev_x, prev_y = nx, ny

    for pk in pkeys:
        build(pk, crown_x, CROWN_Y)

    return elements, actual_w, canvas_h


# ── JavaScript animation template ─────────────────────────────────────────────

_JS_TEMPLATE = """\
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0d1117;font-family:'Courier New',monospace;color:#e2e8f0;
     height:100vh;display:flex;flex-direction:column;overflow:hidden}
#ctrl{padding:7px 14px;background:#161b22;border-bottom:1px solid #30363d;
      display:flex;align-items:center;gap:8px;flex-shrink:0;flex-wrap:wrap}
button{background:#21262d;color:#c9d1d9;border:1px solid #30363d;
       padding:4px 10px;cursor:pointer;border-radius:4px;font-size:12px}
button:hover{background:#30363d}
#dl{color:#22c55e;font-size:13px;font-weight:bold;min-width:105px}
#pw{flex:1;background:#21262d;border-radius:3px;height:8px;
    cursor:pointer;border:1px solid #30363d;min-width:60px}
#pb{background:#22c55e;height:100%;border-radius:3px;width:0%}
#cnt{font-size:11px;color:#4a5568;white-space:nowrap}
#cw{overflow:auto;flex-shrink:0;background:#0d1117;max-height:500px}
canvas{display:block}
#tw{flex:1;overflow-y:auto;border-top:1px solid #30363d}
table{width:100%;border-collapse:collapse;font-size:11px}
thead{position:sticky;top:0;background:#161b22;z-index:10}
th{padding:5px 10px;color:#586069;border-bottom:1px solid #30363d;
   text-align:left;font-weight:normal}
td{padding:3px 10px;border-bottom:1px solid #111619;white-space:nowrap}
.rn td{color:#fbbf24;background:#1c170066}
.rs td{color:#94a3b8}
</style>
</head>
<body>
<div id="ctrl">
  <button id="bp">◀ Prev</button>
  <button id="bpl">▶ Play</button>
  <button id="bn">Next ▶</button>
  <span id="dl">—</span>
  <div id="pw"><div id="pb"></div></div>
  <span id="cnt"></span>
</div>
<div id="cw"><canvas id="c"></canvas></div>
<div id="tw">
<table>
  <thead><tr>
    <th>Plant Code</th><th>Sec Stolons</th><th>Sec DPs</th>
    <th>Ter Stolons</th><th>Ter DPs</th><th>Length (cm)</th>
  </tr></thead>
  <tbody id="tb"></tbody>
</table>
</div>
<script>
const D=__DATA__;
const cv=document.getElementById('c'),ctx=cv.getContext('2d');
cv.width=D.width; cv.height=D.height;

let di=0,playing=false,tmr=null;
const IV=2500;
const SC=['#22c55e','#4ade80','#86efac','#bbf7d0'];
function sc(o){return SC[Math.min(o-1,3)];}

function render(){
  ctx.clearRect(0,0,cv.width,cv.height);
  ctx.fillStyle='#0d1117';
  ctx.fillRect(0,0,cv.width,cv.height);
  for(const el of D.elements){
    const seen=el.first_date<=di;
    const isnew=el.first_date===di;
    const future=el.first_date>di;
    ctx.globalAlpha=1;
    if(el.type==='crown'){
      ctx.beginPath();ctx.arc(el.x,el.y,14,0,Math.PI*2);
      ctx.fillStyle='#d97706';ctx.fill();
      ctx.strokeStyle='rgba(255,255,255,0.3)';ctx.lineWidth=1.5;ctx.stroke();
      ctx.fillStyle='#fff';ctx.font='bold 11px monospace';
      ctx.textAlign='center';ctx.textBaseline='middle';
      ctx.fillText(el.label,el.x,el.y);
    } else if(el.type==='segment'){
      ctx.globalAlpha=future?0.07:(isnew?1.0:0.7);
      ctx.beginPath();ctx.moveTo(el.x1,el.y1);ctx.lineTo(el.x2,el.y2);
      ctx.strokeStyle=future?'#1a2a1a':sc(el.order);
      ctx.lineWidth=future?0.5:Math.max(0.5,3.5-el.order*0.8);
      ctx.stroke();
    } else if(el.type==='node'){
      ctx.globalAlpha=future?0.07:1.0;
      const s=isnew?4.5:2.5;
      ctx.strokeStyle=future?'#1e2d1e':(isnew?'#ffffff':'#fbbf24');
      ctx.lineWidth=isnew?1.5:0.8;
      ctx.beginPath();
      ctx.moveTo(el.x-s,el.y-s);ctx.lineTo(el.x+s,el.y+s);
      ctx.moveTo(el.x+s,el.y-s);ctx.lineTo(el.x-s,el.y+s);
      ctx.stroke();
    } else if(el.type==='daughter'){
      ctx.globalAlpha=future?0.05:1.0;
      const r=isnew?5.5:3.5;
      ctx.beginPath();ctx.arc(el.x,el.y,r,0,Math.PI*2);
      ctx.strokeStyle=future?'#1a1a1a':(isnew?'#ff6b6b':'#ef4444');
      ctx.lineWidth=isnew?2:1;
      ctx.stroke();
      if(isnew){ctx.globalAlpha=0.2;ctx.fillStyle='#ff6b6b';ctx.fill();}
    }
  }
  ctx.globalAlpha=1;
}

function updateTable(){
  const date=D.dates[di];
  const prevDates=D.dates.slice(0,di);
  const prevSet=new Set();
  for(const d of prevDates) for(const c of(D.codes_by_date[d]||[])) prevSet.add(c);
  const todayCodes=D.codes_by_date[date]||[];
  const todayData=D.timeline_by_date[date]||{};
  const newCodes=todayCodes.filter(c=>!prevSet.has(c));
  const oldCodes=todayCodes.filter(c=>prevSet.has(c));
  const rows=[];
  for(const code of [...newCodes,...oldCodes]){
    const m=todayData[code];
    const sl=m&&m.stolon_length!=null?m.stolon_length.toFixed(1):'—';
    const cls=newCodes.includes(code)?'rn':'rs';
    rows.push(`<tr class="${cls}"><td>${code}</td>`+
      `<td>${m?m.sec_stolon:'—'}</td><td>${m?m.sec_daughters:'—'}</td>`+
      `<td>${m?m.ter_stolon:'—'}</td><td>${m?m.ter_daughters:'—'}</td>`+
      `<td>${sl}</td></tr>`);
  }
  document.getElementById('tb').innerHTML=rows.join('');
}

function ui(){
  document.getElementById('dl').textContent=D.dates[di];
  const n=D.dates.length;
  document.getElementById('cnt').textContent=(di+1)+' / '+n;
  document.getElementById('pb').style.width=(n>1?di/(n-1)*100:0)+'%';
  render();updateTable();
}

function goTo(i){di=Math.max(0,Math.min(D.dates.length-1,i));ui();}

function startPlay(){
  playing=true;
  document.getElementById('bpl').textContent='⏸ Pause';
  if(di>=D.dates.length-1)di=-1;
  tmr=setInterval(()=>{
    if(di<D.dates.length-1){goTo(di+1);}else stopPlay();
  },IV);
}
function stopPlay(){
  playing=false;
  document.getElementById('bpl').textContent='▶ Play';
  if(tmr){clearInterval(tmr);tmr=null;}
}

document.getElementById('bp').onclick=()=>{stopPlay();goTo(di-1);};
document.getElementById('bn').onclick=()=>{stopPlay();goTo(di+1);};
document.getElementById('bpl').onclick=()=>{playing?stopPlay():startPlay();};
document.getElementById('pw').addEventListener('click',e=>{
  const r=e.currentTarget.getBoundingClientRect();
  stopPlay();goTo(Math.round((e.clientX-r.left)/r.width*(D.dates.length-1)));
});

goTo(0);
</script>
</body>
</html>"""


# ── Public API ────────────────────────────────────────────────────────────────

def build_js_html(plant: Plant,
                  ws1_cultivar: dict,
                  mother_id: int,
                  canvas_w: int = 900,
                  canvas_h: int = 480) -> str:
    """
    Build a self-contained HTML page with a temporal canvas animation.

    Parameters
    ----------
    plant         : Plant object from load_all_plants()
    ws1_cultivar  : ws1_data[cultivar_name] dict from ws1_parser.load_ws1()
    mother_id     : which mother to display (1, 2, or 3)
    canvas_w      : target canvas width in px (may grow to fit tree)
    canvas_h      : canvas height in px

    Returns
    -------
    Complete self-contained HTML string.
    """
    if not plant or not ws1_cultivar:
        return _empty_html("No data available for this cultivar / mother.")

    dates = ws1_cultivar.get("dates", [])
    if not dates:
        return _empty_html("No temporal dates found in Worksheet 1 for this cultivar.")

    codes_by_date  = ws1_cultivar.get("codes_by_date", {})
    ws1_plants_raw = ws1_cultivar.get("plants", {})

    # code_first_date: code → first date index it appears in codes_by_date
    code_first_date: dict[str, int] = {}
    for di, d in enumerate(dates):
        for code in codes_by_date.get(d, []):
            if code not in code_first_date:
                code_first_date[code] = di

    # Check that this mother exists in the plant
    if mother_id not in plant.mothers:
        available = plant.mother_ids()
        if not available:
            return _empty_html(f"No mothers found in WS3 data for this cultivar.")
        mother_id = available[0]

    # Compute layout
    elements, actual_w, actual_h = _compute_layout(
        plant, mother_id, canvas_w, canvas_h, code_first_date, len(dates)
    )
    if not elements:
        return _empty_html(f"No stolon structure found for Mother {mother_id}.")

    # Build timeline_by_date: {date → {code → measurements}}
    timeline_by_date: dict[str, dict] = {}
    for d in dates:
        tbl: dict[str, dict] = {}
        for code, date_data in ws1_plants_raw.items():
            if d in date_data:
                tbl[code] = date_data[d]
        timeline_by_date[d] = tbl

    payload = {
        "width":            actual_w,
        "height":           actual_h,
        "elements":         elements,
        "dates":            dates,
        "codes_by_date":    codes_by_date,
        "timeline_by_date": timeline_by_date,
    }

    data_json = json.dumps(payload, separators=(",", ":"))
    return _JS_TEMPLATE.replace("__DATA__", data_json)


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
        "<!DOCTYPE html><html><body style='margin:0;background:#0d1117;"
        "display:flex;align-items:center;justify-content:center;height:100vh;"
        "font-family:monospace;color:#555;font-size:14px'>"
        f"<p>{msg}</p></body></html>"
    )
