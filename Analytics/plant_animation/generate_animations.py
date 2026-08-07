"""
generate_animations.py — VeryBerryLab Pheno 4 Plant Growth Animations
======================================================================

Reads 'Pheno 4 Worksheet 3.xlsx' (one sheet per cultivar) and generates an
animated GIF per sheet showing the strawberry plant architecture growing
stolon-by-stolon in depth-first order.

Strategy
--------
Rather than calling matplotlib per frame (which is too slow for large sheets),
we render the FINAL complete scene once with matplotlib, rasterise it into a
numpy image, then for each animation frame we use PIL/Pillow to composite
the progressively-revealed structure onto that image.  This keeps frame
generation at millisecond speed regardless of scene complexity.

Usage:
    python generate_animations.py

Output:
    plant_animation/output/growth_<SHEET>.gif

Requires:
    pip install pandas openpyxl numpy matplotlib pillow
"""

import io
import os
import warnings

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D
from PIL import Image, ImageDraw

warnings.filterwarnings('ignore')

# ─── Configuration ───────────────────────────────────────────────────────────

EXCEL_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', 'Pheno 4 Worksheet 3.xlsx'
)
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'output')

DEFAULT_INTERNODE_CM = 2.0    # fallback length when measurement is absent
MOTHER_SPACING_CM    = 130.0  # horizontal gap between mother plants
TARGET_FRAMES        = 250    # desired number of animation frames per GIF
FRAME_DURATION_MS    = 80     # ms per frame  (≈ 12 fps)
CANVAS_PX            = (1200, 860)  # (width, height) of each GIF frame
DPI                  = 120    # matplotlib render DPI (higher = bigger text/marks)

SKIP_SHEETS = {'misc. dry matter'}

# Visual style ----------------------------------------------------------------
STOLON_COLOUR  = {1: '#1b5e20', 2: '#2e7d32', 3: '#66bb6a', 4: '#a5d6a7'}
STOLON_LW_PX   = {1: 3, 2: 2, 3: 1, 4: 1}   # line widths in PIL pixels
MOTHER_COLOUR  = '#4e342e'
NODE_COLOUR    = '#388e3c'
DAUGHTER_COLOUR= '#c62828'
BG_COLOUR      = '#f9fbe7'


# ─── Data Model ──────────────────────────────────────────────────────────────

class Node:
    """One node on a stolon — may hold a daughter plant and/or branch into child stolons."""
    __slots__ = ['num', 'pos', 'daughter_code', 'child_stolons']

    def __init__(self, num):
        self.num            = num
        self.pos            = None   # (x, y) set during layout
        self.daughter_code  = None   # full code string if a DP exists here
        self.child_stolons  = []     # list of stolon keys that branch from this node


class Stolon:
    """A runner (stolon) at a given hierarchical order. key = (mother_id, order, stolon_num)."""
    __slots__ = ['key', 'origin', 'angle', 'nodes', 'ilengths', 'parent_node_key']

    def __init__(self, key):
        self.key             = key
        self.origin          = None
        self.angle           = None
        self.nodes           = {}    # node_num → Node
        self.ilengths        = {}    # node_num → float (distance from prev node/origin)
        self.parent_node_key = None


class Plant:
    """All mothers, stolons, and nodes for one cultivar sheet."""

    def __init__(self):
        self.mothers = {}
        self.stolons = {}

    def stolon(self, mother_id, order, stolon_num):
        key = (mother_id, order, stolon_num)
        if key not in self.stolons:
            self.stolons[key] = Stolon(key)
        return self.stolons[key]

    def node(self, mother_id, order, stolon_num, node_num):
        st = self.stolon(mother_id, order, stolon_num)
        if node_num not in st.nodes:
            st.nodes[node_num] = Node(node_num)
        return st.nodes[node_num]


# ─── Code Parsing ────────────────────────────────────────────────────────────

def _ints(segment: str) -> list:
    """Extract integers from a dot-separated string segment."""
    result = []
    for tok in segment.split('.'):
        tok = tok.strip()
        if tok.lstrip('-').isdigit():
            result.append(int(tok))
    return result


def _parse_parts(parts: list) -> list:
    """
    Convert slash-separated code parts into a list of path entries.

    Each entry: (order, stolon_num, max_node_num, daughter_id_or_None, is_terminal)
    """
    if not parts:
        return []

    first = _ints(parts[0])
    if len(first) < 3:
        return []

    prim_stolon   = first[1]
    prim_node     = first[2]
    prim_daughter = first[3] if len(first) >= 4 else None

    entries = []

    if len(parts) == 1:
        entries.append((1, prim_stolon, prim_node, prim_daughter, True))
    else:
        entries.append((1, prim_stolon, prim_node, None, False))
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
                    entries.append((order, nums[0], 1, nums[1], True))   # stolon.daughter
                else:
                    entries.append((order, nums[0], nums[1], None, False))  # stolon.node
            elif len(nums) == 1:
                entries.append((order, nums[0], 1, None, is_last))

    return entries


def parse_code(raw_code: str, row_lengths: list, plant: Plant):
    """
    Parse one daughter-plant code and register the structural path into `plant`.

    row_lengths is a flat list [L1, L2, L3, …] mapping sequentially onto every
    node along the full root-to-daughter path.
    """
    code = str(raw_code).strip().replace('//', '/')
    if not code or code.lower() == 'nan':
        return

    parts = code.split('/')
    if not parts:
        return

    first_nums = _ints(parts[0])
    if len(first_nums) < 3:
        return

    mother_id = first_nums[0]
    plant.mothers.setdefault(mother_id, None)

    path_entries = _parse_parts(parts)
    if not path_entries:
        return

    # Assign internode lengths sequentially along the path
    len_ptr = 0
    for (order, stolon_num, max_node, daughter, is_terminal) in path_entries:
        st = plant.stolon(mother_id, order, stolon_num)
        for n in range(1, max_node + 1):
            if n not in st.ilengths:
                if len_ptr < len(row_lengths):
                    st.ilengths[n] = row_lengths[len_ptr]
                else:
                    st.ilengths[n] = DEFAULT_INTERNODE_CM
            len_ptr += 1
        for n in range(1, max_node + 1):
            plant.node(mother_id, order, stolon_num, n)
        if is_terminal and daughter is not None:
            nd = plant.node(mother_id, order, stolon_num, max_node)
            if nd.daughter_code is None:
                nd.daughter_code = code

    # Register parent→child stolon branching links
    for i in range(len(path_entries) - 1):
        o_p, s_p, n_p, _, _ = path_entries[i]
        o_c, s_c, _,  _, _  = path_entries[i + 1]
        parent_st   = plant.stolon(mother_id, o_p, s_p)
        child_st    = plant.stolon(mother_id, o_c, s_c)
        parent_node = parent_st.nodes[n_p]
        if child_st.key not in parent_node.child_stolons:
            parent_node.child_stolons.append(child_st.key)
        if child_st.parent_node_key is None:
            child_st.parent_node_key = (mother_id, o_p, s_p, n_p)


# ─── Sheet Loading ────────────────────────────────────────────────────────────

def load_plant_from_sheet(df: pd.DataFrame):
    """Build a Plant from a sheet DataFrame. Returns None if no daughter-plant column."""
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]

    dp_col = next((c for c in df.columns if c.lower().startswith('daughter')), None)
    if dp_col is None:
        return None

    il_cols = sorted(c for c in df.columns if c.lower().startswith('internode'))
    plant = Plant()

    for _, row in df.iterrows():
        code_val = row.get(dp_col, np.nan)
        if pd.isna(code_val):
            continue
        code_str = str(code_val).strip()
        if not code_str:
            continue

        lengths = []
        for col in il_cols:
            raw = row.get(col, np.nan)
            try:
                v = float(raw)
                lengths.append(v if (not np.isnan(v) and v > 0) else DEFAULT_INTERNODE_CM)
            except (ValueError, TypeError):
                lengths.append(DEFAULT_INTERNODE_CM)

        parse_code(code_str, lengths, plant)

    return plant if plant.stolons else None


# ─── Layout ──────────────────────────────────────────────────────────────────

def assign_positions(plant: Plant):
    """Assign (x, y) coords to all nodes using accumulated internode lengths."""
    mother_ids = sorted(plant.mothers)
    n_mothers  = len(mother_ids)
    for i, mid in enumerate(mother_ids):
        x = (i - (n_mothers - 1) / 2.0) * MOTHER_SPACING_CM
        plant.mothers[mid] = (x, 0.0)

    # Primary stolon directions: spread evenly from the top
    for mid in mother_ids:
        prim_keys = sorted(k for k in plant.stolons if k[0] == mid and k[1] == 1)
        n = len(prim_keys)
        for j, key in enumerate(prim_keys):
            angle = np.pi / 2 + 2 * np.pi * j / max(n, 1)
            st = plant.stolons[key]
            st.origin = plant.mothers[mid]
            st.angle  = angle

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

                # Branch angles for child stolons spread ±72° around parent direction
                nd = st.nodes[n]
                n_ch = len(nd.child_stolons)
                if n_ch:
                    offsets = np.linspace(-np.pi / 2.5, np.pi / 2.5, n_ch)
                    for ci, child_key in enumerate(nd.child_stolons):
                        child_st = plant.stolons[child_key]
                        child_st.origin = (x, y)
                        child_st.angle  = st.angle + offsets[ci]


# ─── Draw events ─────────────────────────────────────────────────────────────

def collect_draw_steps(plant: Plant) -> list:
    """
    Depth-first traversal returning one 'step' per stolon-segment growth.

    Each step is a list of primitive drawing commands to execute at that frame:
        ('mother',   mid, (x, y))
        ('segment',  (x1,y1), (x2,y2), order)
        ('node',     (x, y))
        ('daughter', (x, y))

    Animation plays out stolon-by-stolon rather than node-by-node, keeping the
    number of frames manageable regardless of total node count.
    """
    # One step = one segment + any daughter at its endpoint
    # Mother plants each get their own step
    steps = []

    for mid in sorted(plant.mothers):
        pos = plant.mothers[mid]
        if pos:
            steps.append([('mother', mid, pos)])

    def traverse(stolon_key):
        st = plant.stolons[stolon_key]
        if st.origin is None:
            return
        prev = st.origin
        for n in sorted(st.nodes):
            nd = st.nodes[n]
            if nd.pos is None:
                continue
            cmds = [('segment', prev, nd.pos, st.key[1]),
                    ('node', nd.pos)]
            if nd.daughter_code:
                cmds.append(('daughter', nd.pos))
            steps.append(cmds)
            for child_key in nd.child_stolons:
                traverse(child_key)
            prev = nd.pos

    for mid in sorted(plant.mothers):
        for key in sorted(k for k in plant.stolons if k[0] == mid and k[1] == 1):
            traverse(key)

    return steps


# ─── Coordinate projection ───────────────────────────────────────────────────

def _make_projector(plant: Plant, canvas_w: int, canvas_h: int):
    """
    Return a function that maps plant cm-coordinates → canvas pixel coordinates.
    Also returns the pixel radius to use for markers.
    """
    all_x, all_y = [], []
    for mid, pos in plant.mothers.items():
        if pos:
            all_x.append(pos[0]); all_y.append(pos[1])
    for st in plant.stolons.values():
        for nd in st.nodes.values():
            if nd.pos:
                all_x.append(nd.pos[0]); all_y.append(nd.pos[1])

    if not all_x:
        return lambda p: (canvas_w // 2, canvas_h // 2), 4

    pad_frac = 0.08
    x_range  = max(all_x) - min(all_x) or 1.0
    y_range  = max(all_y) - min(all_y) or 1.0
    pad_x    = x_range * pad_frac + 5
    pad_y    = y_range * pad_frac + 5

    x_min, x_max = min(all_x) - pad_x, max(all_x) + pad_x
    y_min, y_max = min(all_y) - pad_y, max(all_y) + pad_y

    # Scale while preserving aspect ratio, centred in canvas
    sx = canvas_w / (x_max - x_min)
    sy = canvas_h / (y_max - y_min)
    s  = min(sx, sy) * 0.92   # 92% of the fit to leave a small border

    cx = (canvas_w - s * (x_max - x_min)) / 2
    cy = (canvas_h - s * (y_max - y_min)) / 2

    def project(pt):
        px = int(cx + s * (pt[0] - x_min))
        py = int(cy + s * (y_max - pt[1]))   # flip y (screen y increases downward)
        return (px, py)

    # Marker size: ~1% of the shorter canvas dimension
    marker_r = max(3, int(min(canvas_w, canvas_h) * 0.008))
    return project, marker_r


# ─── PIL-based frame rendering ───────────────────────────────────────────────

def _hex_to_rgb(h: str) -> tuple:
    h = h.lstrip('#')
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def _draw_commands_on_image(draw: ImageDraw.Draw, cmds: list,
                             proj, marker_r: int):
    """Apply a list of drawing commands to a PIL ImageDraw context."""
    for cmd in cmds:
        if cmd[0] == 'mother':
            _, mid, pos = cmd
            px, py = proj(pos)
            r = marker_r * 3
            draw.ellipse([px - r, py - r, px + r, py + r],
                         fill=MOTHER_COLOUR, outline='#2d1b14', width=1)

        elif cmd[0] == 'segment':
            _, p1, p2, order = cmd
            px1, py1 = proj(p1)
            px2, py2 = proj(p2)
            lw = STOLON_LW_PX.get(order, 1)
            col = STOLON_COLOUR.get(order, '#c8e6c9')
            draw.line([px1, py1, px2, py2], fill=col, width=lw)

        elif cmd[0] == 'node':
            _, pos = cmd
            px, py = proj(pos)
            r = max(2, marker_r // 2)
            draw.ellipse([px - r, py - r, px + r, py + r],
                         fill=NODE_COLOUR)

        elif cmd[0] == 'daughter':
            _, pos = cmd
            px, py = proj(pos)
            r = int(marker_r * 1.8)
            draw.ellipse([px - r, py - r, px + r, py + r],
                         fill=DAUGHTER_COLOUR, outline='white', width=1)


def _render_title_bar(canvas_w: int, sheet_name: str, frame: int, total: int) -> Image.Image:
    """Render a thin title strip using matplotlib, return as PIL image."""
    fig, ax = plt.subplots(figsize=(canvas_w / DPI, 0.45))
    fig.patch.set_facecolor('#eceff1')
    ax.set_facecolor('#eceff1')
    ax.axis('off')
    pct = int(100 * frame / max(total, 1))
    ax.text(0.5, 0.5,
            f'{sheet_name}  —  Strawberry Plant Architecture Growth  ({pct}%)',
            ha='center', va='center', fontsize=10, fontweight='bold',
            transform=ax.transAxes)
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=DPI, bbox_inches='tight', pad_inches=0)
    plt.close(fig)
    buf.seek(0)
    return Image.open(buf).convert('RGBA')


# ─── Animation ───────────────────────────────────────────────────────────────

def animate_plant(plant: Plant, sheet_name: str, output_path: str):
    steps = collect_draw_steps(plant)
    if not steps:
        print(f'  [!] No draw steps for {sheet_name}, skipping.')
        return

    n_steps = len(steps)
    # Batch steps so we hit TARGET_FRAMES
    spf = max(1, -(-n_steps // TARGET_FRAMES))   # steps per frame (ceiling div)
    batches  = [steps[i:i + spf] for i in range(0, n_steps, spf)]
    n_frames = len(batches)
    print(f'  Steps: {n_steps} → {n_frames} frames (spf={spf})')

    W, H = CANVAS_PX
    proj, marker_r = _make_projector(plant, W, H)

    # We build the GIF incrementally: each frame composites on top of the previous
    frames: list[Image.Image] = []
    canvas = Image.new('RGBA', (W, H), BG_COLOUR)

    for fi, batch in enumerate(batches):
        draw = ImageDraw.Draw(canvas)
        for step in batch:
            _draw_commands_on_image(draw, step, proj, marker_r)
        del draw

        # Add mother-plant labels on the first frame
        if fi == 0:
            draw2 = ImageDraw.Draw(canvas)
            for mid, pos in plant.mothers.items():
                if pos:
                    px, py = proj(pos)
                    r = marker_r * 3
                    # Mother circle drawn here too (covered by first batch already)
                    draw2.text((px, py + r + 4), f'M{mid}',
                               fill=MOTHER_COLOUR, anchor='mt')
            del draw2

        # Append a copy of the current canvas as a GIF frame
        frames.append(canvas.copy().convert('P', dither=Image.Dither.NONE,
                                            palette=Image.Palette.ADAPTIVE))

    if not frames:
        print(f'  [!] No frames generated for {sheet_name}.')
        return

    # Save as animated GIF
    frames[0].save(
        output_path,
        save_all=True,
        append_images=frames[1:],
        duration=FRAME_DURATION_MS,
        loop=0,
        optimize=True
    )
    size_mb = os.path.getsize(output_path) / 1e6
    print(f'  Saved → {output_path}  ({size_mb:.1f} MB)')


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    if not os.path.exists(EXCEL_PATH):
        print(f'ERROR: Cannot find:\n  {EXCEL_PATH}')
        print('Place "Pheno 4 Worksheet 3.xlsx" inside the Analytics/ folder.')
        return

    print(f'Source : {EXCEL_PATH}')
    print(f'Output : {OUTPUT_DIR}\n')

    xl = pd.ExcelFile(EXCEL_PATH)

    for sheet_name in xl.sheet_names:
        if sheet_name.lower().strip() in SKIP_SHEETS:
            print(f'Skipping: {sheet_name}')
            continue

        print(f'Sheet: {sheet_name}')
        df    = xl.parse(sheet_name, header=0)
        plant = load_plant_from_sheet(df)

        if plant is None:
            print(f'  [!] No "Daughter plant" column — skipping.\n')
            continue

        n_stolons = len(plant.stolons)
        n_nodes   = sum(len(s.nodes) for s in plant.stolons.values())
        n_dps     = sum(
            sum(1 for nd in s.nodes.values() if nd.daughter_code)
            for s in plant.stolons.values()
        )
        print(f'  Mothers: {sorted(plant.mothers)}  '
              f'Stolons: {n_stolons}  Nodes: {n_nodes}  DPs: {n_dps}')

        assign_positions(plant)

        out_path = os.path.join(OUTPUT_DIR, f'growth_{sheet_name}.gif')
        animate_plant(plant, sheet_name, out_path)
        print()

    print('All done.')


if __name__ == '__main__':
    main()
