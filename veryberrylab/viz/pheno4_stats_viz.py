"""
viz/pheno4_stats_viz.py
=======================
Revolutionary 3-panel research dashboard for Pheno 4:

  LEFT   — Trait navigator with per-date significance dots; ↑↓ keyboard nav
  CENTER — Date timeline (52 px) · animated Plotly bar chart · cultivar sparklines
  RIGHT  — KW statistics card · significance meter · CLD rankings · champion board

  Bar mode : Plotly.animate() transitions · sparkline strip always visible
  Line mode : Plotly multi-line chart (full center height) · sparklines hidden

  Statistical engine:
    • Kruskal-Wallis per (trait × date)
    • Conover-Iman post-hoc · Bonferroni correction
    • Compact Letter Display (Piepho 2004)

Run from the veryberrylab/ directory
--------------------------------------
    python3 viz/pheno4_stats_viz.py

Output
------
    viz/chart_C.html   — self-contained HTML (Plotly via CDN)
"""

from __future__ import annotations

import json
import math
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import scipy.stats as stats

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT     = Path(__file__).resolve().parent.parent
RAW_CSV  = ROOT / "data" / "processed" / "pheno4_clean.csv"
VIZ_DIR  = ROOT / "viz"
OUT_HTML = VIZ_DIR / "chart_C.html"

# ---------------------------------------------------------------------------
# Palette  (Okabe-Ito colorblind-safe, 11 colors)
# ---------------------------------------------------------------------------
PALETTE = [
    "#E69F00", "#56B4E9", "#009E73", "#F0E442", "#0072B2",
    "#D55E00", "#CC79A7", "#000000", "#AA4499", "#44BB99", "#BBCC33",
]

# ---------------------------------------------------------------------------
# Trait definitions
# ---------------------------------------------------------------------------
TRAIT_LABELS = {
    "n_stolon_primary":           "Primary Stolons",
    "n_stolon_secondary":         "Secondary Stolons",
    "n_stolon_tertiary":          "Tertiary Stolons",
    "n_stolon_quaternary":        "Quaternary Stolons",
    "n_dp_alt_primary":           "Daughter Plants (Alt) — Primary",
    "n_dp_alt_secondary":         "Daughter Plants (Alt) — Secondary",
    "n_dp_alt_tertiary":          "Daughter Plants (Alt) — Tertiary",
    "n_dp_alt_quaternary":        "Daughter Plants (Alt) — Quaternary",
    "n_dp_mid_primary":           "Daughter Plants (Mid) — Primary",
    "n_dp_mid_secondary":         "Daughter Plants (Mid) — Secondary",
    "n_dp_mid_tertiary":          "Daughter Plants (Mid) — Tertiary",
    "n_dp_mid_quaternary":        "Daughter Plants (Mid) — Quaternary",
    "n_dp_total_alt":             "Total DPs — Alternate Nodes",
    "n_dp_total_mid":             "Total DPs — Mid Nodes",
    "n_flowers_total":            "Total Flowers",
    "n_flowers_mp":               "Flowers on Mother Plant",
    "n_flowers_dp":               "Flowers on Daughter Plants",
    "stolon_length_primary_cm":   "Primary Stolon Length (cm)",
    "crown_diameter_mm":          "Crown Diameter (mm)",
}

ALL_TRAITS = [
    "n_stolon_primary","n_stolon_secondary","n_stolon_tertiary","n_stolon_quaternary",
    "n_dp_alt_primary","n_dp_alt_secondary","n_dp_alt_tertiary","n_dp_alt_quaternary",
    "n_dp_mid_primary","n_dp_mid_secondary","n_dp_mid_tertiary","n_dp_mid_quaternary",
    "n_dp_total_alt","n_dp_total_mid",
    "n_flowers_total","n_flowers_mp","n_flowers_dp",
    "stolon_length_primary_cm","crown_diameter_mm",
]

ALL_11_CULTIVARS = [
    "Albion","Brilliance","Cabrio","Camarosa","Chandler",
    "Finn","Moxie","Portola","Radiance","Ruby June","Sensation",
]
SORTED_CVS      = sorted(ALL_11_CULTIVARS)
CULTIVAR_COLORS = {cv: PALETTE[i] for i, cv in enumerate(SORTED_CVS)}

NONBEST_ALPHA = 0.28
ALPHA         = 0.05


# ---------------------------------------------------------------------------
# Color helper
# ---------------------------------------------------------------------------
def _hex_to_rgba(hex_color: str, alpha: float = 1.0) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha:.2f})"


# ===========================================================================
# Statistics engine  (unchanged logic)
# ===========================================================================

def sig_label(p) -> str:
    if p is None: return "N/A"
    if p > 0.05:  return "ns"
    if p > 0.01:  return "*"
    if p > 0.001: return "**"
    return "***"


def run_conover_posthoc(groups_dict: dict) -> pd.DataFrame:
    cultivars = list(groups_dict.keys())
    data_list = [groups_dict[cv] for cv in cultivars]
    try:
        import scikit_posthocs as sp
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=RuntimeWarning)
            result = sp.posthoc_conover(data_list, p_adjust="bonferroni")
        result.index   = cultivars
        result.columns = cultivars
        return result
    except Exception:
        pass

    all_values = np.concatenate(data_list)
    all_ranks  = stats.rankdata(all_values)
    N = len(all_values); k = len(cultivars)
    num_comparisons = k * (k - 1) / 2
    group_ranks: dict[str, np.ndarray] = {}
    pos = 0
    for cv in cultivars:
        n = len(groups_dict[cv])
        group_ranks[cv] = all_ranks[pos: pos + n]; pos += n
    try:
        H, _ = stats.kruskal(*data_list)
    except ValueError:
        H = 0.0
    S2_num = float(np.sum(all_ranks ** 2)) - N * (N + 1) ** 2 / 4.0
    S2 = S2_num / (N - 1) if N > 1 else 1.0
    if S2 <= 0: S2 = 1.0
    df_t = N - k
    p_matrix = pd.DataFrame(1.0, index=cultivars, columns=cultivars)
    for i, ci in enumerate(cultivars):
        for j, cj in enumerate(cultivars):
            if i >= j: continue
            ni, nj = len(group_ranks[ci]), len(group_ranks[cj])
            scale = S2 * (N - 1 - H) / (N - k) * (1.0 / ni + 1.0 / nj)
            if scale <= 0:
                p_adj = 1.0
            else:
                t_stat = abs(group_ranks[ci].mean() - group_ranks[cj].mean()) / math.sqrt(scale)
                p_adj  = min(2.0 * stats.t.sf(t_stat, df=df_t) * num_comparisons, 1.0)
            p_matrix.loc[ci, cj] = p_adj
            p_matrix.loc[cj, ci] = p_adj
    return p_matrix


def compact_letter_display(order: list[str], p_matrix: pd.DataFrame, alpha: float) -> dict[str, str]:
    n = len(order)
    if n == 0: return {}
    if n == 1: return {order[0]: "a"}
    letter_classes: list[set] = [set(order)]
    sig_pairs = [(order[i], order[j]) for i in range(n) for j in range(i+1, n)
                 if p_matrix.loc[order[i], order[j]] < alpha]
    for gi, gj in sig_pairs:
        new_classes = []
        for cls in letter_classes:
            if gi in cls and gj in cls:
                ki = {m for m in cls if m == gi or p_matrix.loc[m, gi] >= alpha}
                kj = {m for m in cls if m == gj or p_matrix.loc[m, gj] >= alpha}
                if ki and ki != cls:
                    new_classes.append(ki)
                    if kj and kj != ki: new_classes.append(kj)
                elif kj and kj != cls:
                    new_classes.append(cls - {gi}); new_classes.append(kj)
                else:
                    new_classes.append(cls)
            else:
                new_classes.append(cls)
        letter_classes = new_classes
    unique = [c for i, c in enumerate(letter_classes) if c not in letter_classes[:i]]
    filtered = [c for c in unique if not any(o != c and o.issubset(c) for o in unique)]
    if not filtered: filtered = [set(order)]
    filtered.sort(key=lambda cls: min(order.index(m) for m in cls if m in order))
    letters = "abcdefghijklmnopqrstuvwxyz"
    cld: dict[str, list] = {cv: [] for cv in order}
    for idx, cls in enumerate(filtered):
        for cv in cls:
            if cv in cld: cld[cv].append(letters[idx % len(letters)])
    return {cv: "".join(sorted(set(cld[cv]))) or "a" for cv in order}


NULL_RESULT = {"kw_stat":None,"kw_p":None,"sig_label":"N/A",
               "cld":{},"means":{},"ses":{},"ns":{},"order":[],"is_significant":False}


def run_stats_for_combo(df_raw: pd.DataFrame, trait: str, date_str: str) -> dict:
    sub = df_raw[df_raw["date"] == date_str].copy()
    if trait not in sub.columns: return NULL_RESULT.copy()
    groups: dict[str, np.ndarray] = {}
    for cv, grp in sub.groupby("cultivar"):
        vals = grp[trait].dropna().values
        if len(vals): groups[cv] = vals.astype(float)
    if len(groups) < 2:
        r = NULL_RESULT.copy()
        r.update(cld={cv:"a" for cv in groups},
                 means={cv:float(v.mean()) for cv,v in groups.items()},
                 ses={cv:0.0 for cv in groups}, ns={cv:len(v) for cv,v in groups.items()},
                 order=sorted(groups, key=lambda cv: float(groups[cv].mean()), reverse=True))
        return r
    means = {cv: float(v.mean()) for cv,v in groups.items()}
    ses   = {cv: float(v.std(ddof=1)/math.sqrt(len(v))) if len(v)>=2 else 0.0 for cv,v in groups.items()}
    ns    = {cv: len(v) for cv,v in groups.items()}
    order = sorted(groups, key=lambda cv: means[cv], reverse=True)
    try:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=RuntimeWarning)
            kw_stat, kw_p = stats.kruskal(*[groups[cv] for cv in order])
    except ValueError:
        r = NULL_RESULT.copy()
        r.update(cld={cv:"a" for cv in order}, means=means, ses=ses, ns=ns, order=order)
        return r
    if kw_p >= ALPHA:
        return dict(kw_stat=float(kw_stat),kw_p=float(kw_p),sig_label=sig_label(kw_p),
                    cld={cv:"a" for cv in order},means=means,ses=ses,ns=ns,
                    order=order,is_significant=False)
    try:
        p_matrix = run_conover_posthoc(groups)
        cld = compact_letter_display(order, p_matrix, ALPHA)
    except Exception as exc:
        warnings.warn(f"post-hoc failed {trait}@{date_str}: {exc}")
        cld = {cv:"a" for cv in order}
    return dict(kw_stat=float(kw_stat),kw_p=float(kw_p),sig_label=sig_label(kw_p),
                cld=cld,means=means,ses=ses,ns=ns,order=order,is_significant=True)


def precompute_all_stats(df_raw: pd.DataFrame) -> dict:
    df_raw = df_raw.copy()
    df_raw["date"] = pd.to_datetime(df_raw["date"]).dt.strftime("%Y-%m-%d")
    all_dates = sorted(df_raw["date"].unique())
    results   = {}
    print(f"Computing stats for {len(ALL_TRAITS) * len(all_dates)} (trait × date) combos…")
    for trait in ALL_TRAITS:
        for date_str in all_dates:
            results[(trait, date_str)] = run_stats_for_combo(df_raw, trait, date_str)
    n_sig = sum(1 for r in results.values() if r["is_significant"])
    print(f"KW significant (p<0.05): {n_sig}/{len(results)} combinations")
    return results


# ===========================================================================
# Build Plotly figure  (1 bar trace + line traces for line mode)
# ===========================================================================

def build_figure(df_raw: pd.DataFrame, stats_results: dict) -> tuple:
    df_raw = df_raw.copy()
    df_raw["date"] = pd.to_datetime(df_raw["date"]).dt.strftime("%Y-%m-%d")
    all_dates = sorted(df_raw["date"].unique())

    all_bar_data: list[dict] = []
    layout_updates: list[dict] = []

    for t_idx, trait in enumerate(ALL_TRAITS):
        trait_label = TRAIT_LABELS.get(trait, trait)
        for d_idx, date_str in enumerate(all_dates):
            res    = stats_results[(trait, date_str)]
            order  = res["order"];  means  = res["means"]
            ses    = res["ses"];    ns_d   = res["ns"]
            cld    = res["cld"];    is_sig = res["is_significant"]
            kw_stat= res["kw_stat"]; kw_p  = res["kw_p"]
            slbl   = res["sig_label"]

            bar_x, bar_y, bar_mc, bar_mlc, bar_mlw = [], [], [], [], []
            bar_ey, bar_ht, bar_txt, bar_ltr, bar_best = [], [], [], [], []

            for cv in order:
                m = means.get(cv,0.0) or 0.0
                s = ses.get(cv,0.0)   or 0.0
                n = ns_d.get(cv,0)
                ltr = cld.get(cv,"a")
                best = "a" in ltr
                base = CULTIVAR_COLORS.get(cv,"#888888")

                bar_x.append(cv); bar_y.append(m); bar_ey.append(s)
                bar_ltr.append(ltr); bar_best.append(best)
                if best:
                    bar_mc.append(base); bar_mlc.append("rgba(0,0,0,0.45)"); bar_mlw.append(1.5)
                    bar_txt.append(f"★ {ltr}" if is_sig else ltr)
                else:
                    bar_mc.append(_hex_to_rgba(base, NONBEST_ALPHA))
                    bar_mlc.append("rgba(0,0,0,0.12)"); bar_mlw.append(0.5)
                    bar_txt.append(ltr)
                bar_ht.append(f"<b>{cv}</b><br>Mean: {m:.3f}<br>SE: ±{s:.3f}<br>n = {n}<br>CLD: {ltr}")

            if not order:
                bar_x=["(no data)"]; bar_y=[0.0]; bar_mc=["rgba(200,200,200,0.4)"]
                bar_mlc=["rgba(0,0,0,0.1)"]; bar_mlw=[0.5]; bar_ey=[0.0]
                bar_txt=[""]; bar_ht=["No data"]; bar_ltr=[""]; bar_best=[False]

            y_top = max((bar_y[i]+bar_ey[i]) for i in range(len(bar_y))) if bar_y else 0.0
            y_max = max(y_top * 1.38, 0.5)

            all_bar_data.append(dict(x=bar_x, y=bar_y, mc=bar_mc, mlc=bar_mlc, mlw=bar_mlw,
                                     ey=bar_ey, ht=bar_ht, txt=bar_txt,
                                     ltr=bar_ltr, best=bar_best, ymax=y_max))

            fmt_date = datetime.strptime(date_str, "%Y-%m-%d").strftime("%b %d, %Y")
            layout_updates.append({
                "yaxis.title.text": f"Mean {trait_label}",
                "yaxis.range":      [0, y_max],
                "xaxis.categoryarray": bar_x,
                "kw_stat_raw": None if kw_stat is None else float(kw_stat),
                "kw_p_raw":    None if kw_p    is None else float(kw_p),
                "sig_lbl":     slbl,
                "is_sig":      is_sig,
                "n_cvs":       len(order),
                "trait_label": trait_label,
                "date_str":    date_str,
                "fmt_date":    fmt_date,
            })

    fig = go.Figure()
    d0  = all_bar_data[0]
    fig.add_trace(go.Bar(
        x=d0["x"], y=d0["y"],
        text=d0["txt"], textposition="outside",
        textfont=dict(size=11, color="#2d3748", family="monospace"),
        cliponaxis=False,
        marker_color=d0["mc"], marker_line_color=d0["mlc"], marker_line_width=d0["mlw"],
        error_y=dict(type="data", array=d0["ey"], visible=True,
                     thickness=1.2, width=4, color="#94a3b8"),
        hovertext=d0["ht"], hoverinfo="text",
        visible=True, showlegend=False, name="bar_trace",
    ))

    line_traces, line_layout_updates = _build_line_traces(stats_results, all_dates)
    for tr in line_traces:
        fig.add_trace(tr)

    return fig, all_bar_data, layout_updates, line_layout_updates, all_dates


def _build_line_traces(stats_results: dict, all_dates: list) -> tuple:
    traces: list = []
    line_updates: list[dict] = []
    for t_idx, trait in enumerate(ALL_TRAITS):
        trait_label = TRAIT_LABELS.get(trait, trait)
        for c_idx, cv in enumerate(SORTED_CVS):
            color = CULTIVAR_COLORS.get(cv, "#888")
            cv_dates, cv_means, cv_uppers, cv_lowers, cv_ses, cv_ns = [],[],[],[],[],[]
            for date_str in all_dates:
                res = stats_results[(trait, date_str)]
                if cv in res["means"]:
                    m = res["means"][cv]; s = res["ses"].get(cv,0.0) or 0.0
                    cv_dates.append(date_str); cv_means.append(m)
                    cv_uppers.append(m+s); cv_lowers.append(m-s)
                    cv_ses.append(s); cv_ns.append(res["ns"].get(cv,0))
            if not cv_dates:
                traces += [go.Scatter(x=[],y=[],visible=False,showlegend=False,hoverinfo="skip",name=f"__b_{trait}_{cv}"),
                           go.Scatter(x=[],y=[],visible=False,showlegend=False,hoverinfo="skip",name=f"__l_{trait}_{cv}")]
                continue
            traces.append(go.Scatter(
                x=cv_dates+cv_dates[::-1], y=cv_uppers+cv_lowers[::-1],
                fill="toself", fillcolor=_hex_to_rgba(color,0.13),
                line=dict(width=0), showlegend=False, hoverinfo="skip", visible=False,
                name=f"__b_{trait}_{cv}",
            ))
            hover = [f"<b>{cv}</b><br>{pd.Timestamp(d).strftime('%b %d, %Y')}<br>Mean: {m:.3f}<br>SE: ±{s:.3f}<br>n={n}"
                     for d,m,s,n in zip(cv_dates,cv_means,cv_ses,cv_ns)]
            traces.append(go.Scatter(
                x=cv_dates, y=cv_means, mode="lines+markers", name=cv,
                line=dict(color=color, width=2.5),
                marker=dict(size=8, color=color, line=dict(color="white",width=1.5)),
                legendgroup=cv, showlegend=True, visible=False,
                hovertext=hover, hoverinfo="text",
            ))
        line_updates.append({"yaxis_title": f"Mean {trait_label}", "trait_label": trait_label})
    return traces, line_updates


def apply_layout(fig: go.Figure, layout_updates: list, all_traits: list, all_dates: list) -> go.Figure:
    first = layout_updates[0]
    fig.update_layout(
        title=None,
        xaxis=dict(title=dict(text="Cultivar", font=dict(size=12, color="#64748b")),
                   categoryarray=first["xaxis.categoryarray"], categoryorder="array",
                   tickangle=-32, tickfont=dict(size=11, color="#334155"),
                   gridcolor="rgba(0,0,0,0.04)", linecolor="rgba(0,0,0,0.10)",
                   showline=True, zeroline=False),
        yaxis=dict(title=dict(text=first["yaxis.title.text"], font=dict(size=12, color="#64748b")),
                   range=first["yaxis.range"],
                   gridcolor="rgba(0,0,0,0.04)", zeroline=True,
                   zerolinecolor="rgba(0,0,0,0.10)",
                   tickfont=dict(size=10, color="#475569"),
                   linecolor="rgba(0,0,0,0.10)", showline=True),
        annotations=[], showlegend=False,
        legend=dict(x=1.01, y=0.5, xanchor="left", yanchor="middle",
                    bgcolor="rgba(255,255,255,0.95)", bordercolor="#e2e8f0", borderwidth=1,
                    font=dict(size=11, color="#334155"),
                    title=dict(text="Cultivar", font=dict(size=11, color="#475569"))),
        plot_bgcolor="white", paper_bgcolor="white", autosize=True,
        margin=dict(t=14, b=72, l=64, r=40),
        bargap=0.32,
        hoverlabel=dict(bgcolor="white", bordercolor="#e2e8f0",
                        font=dict(size=12, family="-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif"),
                        namelength=-1),
    )
    return fig


# ===========================================================================
# Pre-computation helpers for dashboard panels
# ===========================================================================

def _compute_spark_data(stats_results: dict, all_dates: list) -> list:
    """sparkline_data[t_idx][cv_idx] = {means, ses, date_indices, y_min, y_max}"""
    spark = []
    for trait in ALL_TRAITS:
        trait_block = []
        for cv in SORTED_CVS:
            cv_means, cv_ses, cv_di = [], [], []
            for d_idx, date_str in enumerate(all_dates):
                res = stats_results[(trait, date_str)]
                if cv in res["means"]:
                    m = res["means"][cv]; s = res["ses"].get(cv,0.0) or 0.0
                    cv_means.append(round(m,4)); cv_ses.append(round(s,4)); cv_di.append(d_idx)
            if cv_means:
                y_lo = min(m-s for m,s in zip(cv_means,cv_ses))
                y_hi = max(m+s for m,s in zip(cv_means,cv_ses))
            else:
                y_lo = y_hi = 0.0
            trait_block.append({"m":cv_means,"s":cv_ses,"di":cv_di,
                                 "lo":round(y_lo,4),"hi":round(y_hi,4)})
        spark.append(trait_block)
    return spark


def _compute_sig_matrix(stats_results: dict, all_dates: list) -> list:
    """sig_matrix[t_idx][d_idx] = 0(N/A) | 1(ns) | 2(sig)"""
    matrix = []
    for trait in ALL_TRAITS:
        row = []
        for date_str in all_dates:
            res = stats_results[(trait, date_str)]
            row.append(2 if res["is_significant"] else (0 if res["kw_p"] is None else 1))
        matrix.append(row)
    return matrix


def _compute_cld_table(stats_results: dict, all_dates: list) -> list:
    """cld_table[t_idx][d_idx] = [{cv,letter,mean,se,is_best,color}]"""
    table = []
    for trait in ALL_TRAITS:
        date_tables = []
        for date_str in all_dates:
            res = stats_results[(trait, date_str)]
            rows = []
            for cv in res["order"]:
                ltr  = res["cld"].get(cv,"a")
                m    = res["means"].get(cv)
                s    = res["ses"].get(cv)
                rows.append({"cv":cv, "letter":ltr,
                              "mean": round(m,3) if m is not None else None,
                              "se":   round(s,3) if s is not None else None,
                              "best": "a" in ltr,
                              "color": CULTIVAR_COLORS.get(cv,"#888")})
            date_tables.append(rows)
        table.append(date_tables)
    return table


def _compute_champion_data(stats_results: dict, all_dates: list) -> list:
    """Per-trait champion board (win %). champion_data[t_idx]"""
    champion = []
    for trait in ALL_TRAITS:
        wins    = {cv: 0 for cv in SORTED_CVS}
        measd   = {cv: 0 for cv in SORTED_CVS}
        total_sig = 0
        for date_str in all_dates:
            res = stats_results[(trait, date_str)]
            if not res["is_significant"]: continue
            total_sig += 1
            for cv in res["means"]:
                measd[cv] = measd.get(cv,0) + 1
            for cv, ltr in res["cld"].items():
                if "a" in ltr: wins[cv] = wins.get(cv,0) + 1
        rankings = sorted(
            [{"cv":cv,
              "wins":wins[cv],
              "measured":measd[cv],
              "pct":round(wins[cv]/measd[cv]*100,1) if measd[cv]>0 else 0.0}
             for cv in SORTED_CVS],
            key=lambda r: (-r["pct"], -r["wins"], r["cv"])
        )
        winner = rankings[0]["cv"] if rankings and rankings[0]["wins"]>0 else None
        champion.append({"sig_dates":total_sig,"rankings":rankings,"winner":winner,
                         "winner_color": CULTIVAR_COLORS.get(winner,"#888") if winner else "#888"})
    return champion


# ===========================================================================
# HTML page builder
# ===========================================================================

def _sanitise_json(obj):
    if isinstance(obj, float): return None if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, dict):  return {k: _sanitise_json(v) for k,v in obj.items()}
    if isinstance(obj, list):  return [_sanitise_json(v) for v in obj]
    return obj


def build_full_page(
    plot_div: str,
    n_traits: int, n_dates: int,
    all_bar_data: list, layout_updates: list,
    line_layout_updates: list,
    spark_data: list, sig_matrix: list,
    cld_table: list, champion_data: list,
    all_dates: list,
) -> str:
    import re as _re

    plot_div = _re.sub(
        r'(<div[^>]+id="pheno4_chart"[^>]+)style="[^"]*"',
        r'\1style="width:100%;height:100%;"',
        plot_div,
    )

    n_cv   = len(SORTED_CVS)
    n_line = n_traits * n_cv * 2

    # JSON payloads
    bar_json      = json.dumps(_sanitise_json(all_bar_data))
    lu_json       = json.dumps(_sanitise_json(layout_updates))
    llu_json      = json.dumps(_sanitise_json(line_layout_updates))
    spark_json    = json.dumps(_sanitise_json(spark_data))
    sig_json      = json.dumps(sig_matrix)
    cld_json      = json.dumps(_sanitise_json(cld_table))
    champ_json    = json.dumps(_sanitise_json(champion_data))
    cv_colors_json= json.dumps(CULTIVAR_COLORS)
    dates_json    = json.dumps(all_dates)
    trait_labels_json = json.dumps([TRAIT_LABELS.get(t,t) for t in ALL_TRAITS])
    sorted_cvs_json   = json.dumps(SORTED_CVS)

    # Build trait navigator HTML (19 rows, each with 12 significance dots)
    trait_nav_html = ""
    for t_idx, trait in enumerate(ALL_TRAITS):
        label = TRAIT_LABELS.get(trait, trait)
        dots  = "".join(f'<span class="td" data-sig="{sig_matrix[t_idx][d]}"></span>'
                        for d in range(n_dates))
        trait_nav_html += (
            f'<div class="trait-item" data-tidx="{t_idx}">'
            f'<span class="trait-name">{label}</span>'
            f'<span class="trait-dots">{dots}</span>'
            f'</div>\n'
        )

    # Build date timeline HTML
    timeline_html = ""
    for d_idx, date_str in enumerate(all_dates):
        fmt = datetime.strptime(date_str, "%Y-%m-%d").strftime("%b %d")
        timeline_html += (
            f'<button class="date-dot" data-didx="{d_idx}">'
            f'<span class="dot-circle"></span>'
            f'<span class="dot-label">{fmt}</span>'
            f'</button>'
        )

    # Build sparkline row HTML (11 cells)
    spark_row_html = ""
    for c_idx, cv in enumerate(SORTED_CVS):
        color = CULTIVAR_COLORS.get(cv,"#888")
        spark_row_html += (
            f'<div class="spark-cell" data-cidx="{c_idx}" '
            f'style="--cv-color:{color};">'
            f'<svg class="spark-svg" id="spark-{c_idx}" viewBox="0 0 100 50" '
            f'preserveAspectRatio="none"></svg>'
            f'<span class="spark-label">{cv}</span>'
            f'</div>'
        )

    # ------------------------------------------------------------------ CSS
    css = r"""
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

html { height: 100%; }
body {
  height: 100%; width: 100%; overflow: hidden;
  display: flex; flex-direction: column;
  background: #0b1120;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  color: #cbd5e1;
}

/* ── Animations ──────────────────────────────────────────────────── */
@keyframes fadeSlideIn {
  from { opacity: 0; transform: translateY(5px); }
  to   { opacity: 1; transform: translateY(0); }
}
@keyframes pulseDot {
  0%,100% { transform: scale(1); opacity: 1; }
  50%      { transform: scale(1.5); opacity: 0.7; }
}

/* ── Header ──────────────────────────────────────────────────────── */
#app-header {
  flex-shrink: 0; height: 46px;
  background: #1e293b;
  border-bottom: 1px solid rgba(255,255,255,0.07);
  display: flex; align-items: center; gap: 16px;
  padding: 0 16px;
  box-shadow: 0 2px 12px rgba(0,0,0,0.4);
  z-index: 200;
}
.hdr-brand h1 {
  font-size: 13.5px; font-weight: 700; color: #f1f5f9; letter-spacing: 0.1px;
  white-space: nowrap;
}
.hdr-brand p { font-size: 9px; color: #475569; margin-top: 1px; letter-spacing: 0.4px; }
.hdr-spacer { flex: 1; }
.view-toggle {
  display: flex; background: rgba(0,0,0,0.25);
  border: 1px solid rgba(255,255,255,0.10); border-radius: 8px;
  padding: 3px; gap: 2px; flex-shrink: 0;
}
.view-btn {
  background: transparent; color: #64748b; border: none; border-radius: 5px;
  padding: 4px 13px; font-size: 11.5px; font-weight: 600; cursor: pointer;
  transition: background .16s, color .16s; white-space: nowrap; font-family: inherit;
}
.view-btn.active { background: #1d4ed8; color: #eff6ff; box-shadow: 0 1px 5px rgba(0,0,0,.4); }
.view-btn:hover:not(.active) { background: rgba(255,255,255,.08); color: #cbd5e1; }
.kbd-pill {
  font-size: 10px; color: #475569;
  background: rgba(255,255,255,.04);
  border: 1px solid rgba(255,255,255,.07);
  border-radius: 20px; padding: 4px 10px;
  flex-shrink: 0; white-space: nowrap;
}
.kbd-pill kbd {
  font-size: 10px; color: #64748b;
  background: rgba(255,255,255,.08);
  border-radius: 3px; padding: 1px 4px;
}

/* ── App body: 3-panel grid ──────────────────────────────────────── */
#app-body {
  flex: 1; min-height: 0;
  display: grid;
  grid-template-columns: 220px 1fr 256px;
  grid-template-rows: 52px 1fr 120px;
  grid-template-areas:
    "left timeline right"
    "left chart    right"
    "left sparks   right";
  background: #0b1120;
  gap: 0;
}
#app-body.line-mode {
  grid-template-rows: 52px 1fr 0px;
}
#app-body.line-mode #sparkline-row { display: none; }
#app-body.line-mode #app-chart { overflow: visible; }

/* ── Left panel ──────────────────────────────────────────────────── */
#left-panel {
  grid-area: left;
  background: #131e30;
  border-right: 1px solid rgba(255,255,255,0.07);
  display: flex; flex-direction: column;
  overflow: hidden;
  position: relative; z-index: 20;
}
.left-header {
  flex-shrink: 0; height: 34px;
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 10px;
  border-bottom: 1px solid rgba(255,255,255,0.07);
}
.left-header-label {
  font-size: 8.5px; font-weight: 800; letter-spacing: 1.2px;
  text-transform: uppercase; color: #475569;
}
.sig-filter-wrap {
  display: flex; align-items: center; gap: 4px;
}
.sig-filter-wrap label {
  font-size: 9px; color: #475569; cursor: pointer; display: flex; align-items: center; gap: 3px;
}
.sig-filter-wrap input { width: 11px; height: 11px; cursor: pointer; accent-color: #ef4444; }
#trait-list {
  flex: 1; overflow-y: auto; overflow-x: hidden;
  scrollbar-width: thin; scrollbar-color: #1e3a5f transparent;
}
.trait-item {
  display: flex; align-items: center; justify-content: space-between;
  padding: 5px 10px 5px 11px;
  cursor: pointer;
  border-left: 2px solid transparent;
  transition: background .12s, border-color .12s;
  gap: 6px;
  min-height: 34px;
}
.trait-item:hover   { background: rgba(255,255,255,.04); }
.trait-item.active  {
  background: rgba(29,78,216,0.18);
  border-left-color: #3b82f6;
}
.trait-name {
  font-size: 11px; color: #94a3b8; flex: 1; min-width: 0;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  line-height: 1.3;
}
.trait-item.active .trait-name { color: #bfdbfe; font-weight: 600; }
.trait-dots {
  display: flex; align-items: center; gap: 2px; flex-shrink: 0;
}
.td {
  width: 5px; height: 5px; border-radius: 50%;
  transition: background .2s;
}
.td[data-sig="0"] { background: #1e293b; }
.td[data-sig="1"] { background: #334155; }
.td[data-sig="2"] { background: #ef4444; }
.trait-item.active .td[data-sig="2"] { background: #f87171; }

/* ── Date timeline ───────────────────────────────────────────────── */
#timeline {
  grid-area: timeline;
  background: #131e30;
  border-bottom: 1px solid rgba(255,255,255,0.07);
  border-right: 1px solid rgba(255,255,255,0.07);
  display: flex; align-items: center;
  padding: 0 14px; gap: 0;
  overflow: hidden;
}
.tl-label {
  font-size: 8px; font-weight: 800; letter-spacing: 1px;
  text-transform: uppercase; color: #334155;
  flex-shrink: 0; margin-right: 8px;
}
.date-dots-row { display: flex; align-items: center; flex: 1; gap: 2px; }
.date-dot {
  flex: 1; display: flex; flex-direction: column; align-items: center;
  gap: 3px; background: none; border: none; cursor: pointer; padding: 4px 2px;
  transition: opacity .12s; min-width: 0;
}
.date-dot:hover .dot-circle { border-color: #60a5fa; transform: scale(1.15); }
.dot-circle {
  width: 10px; height: 10px; border-radius: 50%;
  border: 2px solid #334155; background: transparent;
  transition: border-color .18s, background .18s, transform .18s;
}
.date-dot.active .dot-circle {
  border-color: #3b82f6; background: #3b82f6;
  animation: pulseDot 1.5s ease-in-out 1;
}
.dot-label {
  font-size: 8.5px; color: #475569; white-space: nowrap;
  overflow: hidden; text-overflow: clip; max-width: 36px;
  text-align: center;
}
.date-dot.active .dot-label { color: #93c5fd; font-weight: 600; }

/* ── Chart area ──────────────────────────────────────────────────── */
#app-chart {
  grid-area: chart;
  background: #fff;
  overflow: hidden;
  position: relative; z-index: 1;
  animation: fadeSlideIn 0.4s cubic-bezier(0.16,1,0.3,1) both;
}
#pheno4_chart { width: 100% !important; height: 100% !important; }

/* ── Sparkline row ───────────────────────────────────────────────── */
#sparkline-row {
  grid-area: sparks;
  background: #f8fafc;
  border-top: 1px solid #e2e8f0;
  border-right: 1px solid rgba(255,255,255,0.07);
  display: flex; align-items: stretch;
  overflow: hidden;
}
.spark-cell {
  flex: 1; min-width: 0;
  display: flex; flex-direction: column; align-items: center;
  padding: 5px 3px 3px;
  border-right: 1px solid #e8ecf2;
  cursor: pointer; transition: background .13s;
}
.spark-cell:last-child { border-right: none; }
.spark-cell:hover { background: #eef2f8; }
.spark-cell.active-cv { background: rgba(var(--cv-color-rgb,59,130,246),0.06); }
.spark-svg { width: 100%; flex: 1; min-height: 0; display: block; overflow: visible; }
.spark-label {
  font-size: 8.5px; color: #64748b; text-align: center; white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis; max-width: 100%;
  height: 13px; line-height: 13px; margin-top: 1px;
}

/* ── Right panel ─────────────────────────────────────────────────── */
#right-panel {
  grid-area: right;
  background: #131e30;
  border-left: 1px solid rgba(255,255,255,0.07);
  display: flex; flex-direction: column;
  overflow-y: auto; overflow-x: hidden;
  scrollbar-width: thin; scrollbar-color: #1e3a5f transparent;
}
.rp-section { border-bottom: 1px solid rgba(255,255,255,0.06); padding: 10px 12px; }
.rp-hdr {
  font-size: 8.5px; font-weight: 800; letter-spacing: 1.1px;
  text-transform: uppercase; color: #334155; margin-bottom: 8px;
}
/* KW card */
.kw-row { display: flex; align-items: baseline; gap: 6px; margin-bottom: 4px; }
.kw-key {
  font-size: 9px; color: #334155; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.8px; width: 14px; flex-shrink: 0;
}
.kw-val { font-size: 13px; font-weight: 700; color: #e2e8f0; }
.kw-n   { font-size: 10px; color: #475569; }
.sig-badge {
  font-size: 10px; font-weight: 700; padding: 1px 6px; border-radius: 4px;
}
.sig-badge.sig-ns  { color: #475569; background: rgba(71,85,105,.2); }
.sig-badge.sig-s   { color: #fca5a5; background: rgba(239,68,68,.15); }
.sig-badge.sig-na  { color: #334155; background: transparent; }
.kw-meter-track {
  height: 5px; border-radius: 3px; background: #1e3a5f; margin: 7px 0 3px; overflow: hidden;
}
.kw-meter-fill {
  height: 100%; border-radius: 3px; transition: width .4s ease, background .4s ease; width: 0%;
}
.kw-meter-lbls {
  display: flex; justify-content: space-between;
  font-size: 8px; color: #334155;
}
/* CLD table */
#cld-table {
  width: 100%; border-collapse: collapse; font-size: 11px;
}
#cld-table th {
  font-size: 8px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.8px;
  color: #334155; text-align: left; padding: 2px 4px 5px;
  border-bottom: 1px solid rgba(255,255,255,0.07);
}
#cld-table td { padding: 4px 4px; color: #94a3b8; vertical-align: middle; }
.cld-best-row td { color: #ecfdf5 !important; }
.cld-best-row { background: rgba(34,197,94,0.06); }
.cld-best-row td:first-child { border-left: 2px solid; }
.cld-letter { font-weight: 700; font-family: monospace; font-size: 11px; text-align: center; }
.cv-dot {
  display: inline-block; width: 7px; height: 7px; border-radius: 50%;
  margin-right: 5px; vertical-align: middle; flex-shrink: 0;
}
.se-text { font-size: 9px; color: #475569; }
/* Champion board */
.champ-winner-row {
  display: flex; align-items: center; gap: 8px; margin-bottom: 8px;
}
.champ-winner-name { font-size: 13px; font-weight: 700; color: #f0fdf4; }
.champ-no-winner   { font-size: 10px; color: #475569; font-style: italic; }
.champ-row {
  display: flex; align-items: center; gap: 5px; margin-bottom: 4px;
}
.champ-cv { font-size: 9.5px; color: #64748b; width: 54px; flex-shrink: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.champ-bar-track { flex: 1; height: 6px; background: #1e3a5f; border-radius: 3px; overflow: hidden; }
.champ-bar-fill  { height: 100%; border-radius: 3px; transition: width .35s ease; }
.champ-score { font-size: 9px; color: #475569; width: 28px; text-align: right; flex-shrink: 0; }
.champ-note  { font-size: 8.5px; color: #334155; margin-top: 6px; font-style: italic; }

/* ── Status bar ──────────────────────────────────────────────────── */
#status-bar {
  flex-shrink: 0; height: 34px;
  background: #1e293b;
  border-top: 1px solid rgba(255,255,255,0.06);
  display: flex; align-items: center;
  padding: 0 16px; gap: 0;
  font-size: 11px; color: #64748b;
  box-shadow: 0 -2px 10px rgba(0,0,0,.3);
}
.sb-pill {
  display: flex; align-items: center; gap: 5px;
  padding: 0 14px; height: 100%;
  border-right: 1px solid rgba(255,255,255,0.06);
  white-space: nowrap;
}
.sb-pill:last-child { border-right: none; margin-left: auto; }
.sb-chip {
  font-size: 8px; font-weight: 800; text-transform: uppercase;
  letter-spacing: 1px; color: #334155; flex-shrink: 0;
}
#status-trait, #status-date, #status-kw { transition: opacity 0.18s ease; }
    """

    # ------------------------------------------------------------------ JS
    js = f"""
<script>
(function(){{
"use strict";

/* ── Constants ──────────────────────────────────────────────────── */
var N_TRAITS  = {n_traits};
var N_DATES   = {n_dates};
var N_CV      = {n_cv};
var N_LINE    = N_TRAITS * N_CV * 2;

var allBarData        = {bar_json};
var layoutUpdates     = {lu_json};
var lineLayoutUpdates = {llu_json};
var sparklineData     = {spark_json};
var sigMatrix         = {sig_json};
var cldTable          = {cld_json};
var championData      = {champ_json};
var cvColors          = {cv_colors_json};
var allDates          = {dates_json};
var traitLabels       = {trait_labels_json};
var sortedCvs         = {sorted_cvs_json};

var curT    = 0;
var curD    = 0;
var curMode = 'bar';

var MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
function fmtDate(s) {{
  var p = s.split('-');
  return MONTHS[parseInt(p[1])-1] + ' ' + parseInt(p[2]);
}}

function getGd() {{
  return document.getElementById('pheno4_chart') || document.querySelector('.plotly-graph-div');
}}

/* ── Master navigator ───────────────────────────────────────────── */
function navigate(tIdx, dIdx) {{
  var prevMode = curMode;
  curT = tIdx; curD = dIdx;

  try {{
    if (curMode === 'bar') {{
      doBarAnimate(tIdx, dIdx, prevMode !== 'bar');
    }} else {{
      doLineUpdate(tIdx, prevMode !== 'line');
    }}
  }} catch(e) {{
    console.error('navigate chart error:', e);
  }}

  updateLeftPanel(tIdx);
  updateTimeline(dIdx);
  updateSparklines(tIdx, dIdx);
  updateRightPanel(tIdx, dIdx);
  updateStatusBar(tIdx, dIdx);
}}

/* ── Bar chart (restyle + relayout) ─────────────────────────────── */
function doBarAnimate(tIdx, dIdx, fromLine) {{
  var comboIdx = tIdx * N_DATES + dIdx;
  var bd = allBarData[comboIdx];
  var lu = layoutUpdates[comboIdx];
  var gd = getGd(); if (!gd) return;

  try {{
    if (fromLine) {{
      var vis = new Array(1 + N_LINE).fill(false); vis[0] = true;
      Plotly.restyle(gd, {{visible: vis}});
    }}
    Plotly.restyle(gd, {{
      x:                [bd.x],
      y:                [bd.y],
      text:             [bd.txt],
      hovertext:        [bd.ht],
      'marker.color':   [bd.mc],
      'marker.line.color': [bd.mlc],
      'marker.line.width': [bd.mlw],
      'error_y.array':  [bd.ey],
    }}, [0]);
    Plotly.relayout(gd, {{
      'xaxis.type':          'category',
      'xaxis.tickformat':    '',
      'xaxis.title.text':    'Cultivar',
      'xaxis.categoryarray': lu['xaxis.categoryarray'],
      'xaxis.categoryorder': 'array',
      'xaxis.tickangle':     -32,
      'yaxis.title.text':    lu['yaxis.title.text'],
      'yaxis.range':         lu['yaxis.range'],
      'yaxis.autorange':     false,
      'annotations':         [],
      'showlegend':          false,
      'margin.r':            40,
    }});
  }} catch(e) {{
    console.error('Chart update error:', e);
  }}
}}

/* ── Line chart ─────────────────────────────────────────────────── */
function doLineUpdate(tIdx, fromBar) {{
  var nTotal = 1 + N_LINE;
  var vis = new Array(nTotal).fill(false);
  for (var c=0; c<N_CV; c++) {{
    var base = 1 + tIdx*N_CV*2 + c*2;
    vis[base]=true; vis[base+1]=true;
  }}
  var lu = lineLayoutUpdates[tIdx];
  var gd = getGd(); if (!gd) return;
  Plotly.restyle(gd, {{visible:vis}});
  Plotly.relayout(gd, {{
    'xaxis.type':'date','xaxis.tickformat':'%b %d',
    'xaxis.title.text':'Date','xaxis.tickangle':-20,
    'yaxis.title.text':lu.yaxis_title,'yaxis.autorange':true,
    'annotations':[],'showlegend':true,'legend.title.text':'Cultivar',
    'margin.r':150,
  }});
}}

/* ── Left panel ─────────────────────────────────────────────────── */
function updateLeftPanel(tIdx) {{
  document.querySelectorAll('.trait-item').forEach(function(el){{
    el.classList.toggle('active', parseInt(el.dataset.tidx)===tIdx);
  }});
  var active = document.querySelector('.trait-item[data-tidx="'+tIdx+'"]');
  if (active) active.scrollIntoView({{block:'nearest',behavior:'smooth'}});
}}

/* ── Timeline ───────────────────────────────────────────────────── */
function updateTimeline(dIdx) {{
  document.querySelectorAll('.date-dot').forEach(function(el){{
    el.classList.toggle('active', parseInt(el.dataset.didx)===dIdx);
  }});
}}

/* ── Sparklines ─────────────────────────────────────────────────── */
function updateSparklines(tIdx, dIdx) {{
  for (var c=0; c<N_CV; c++) {{
    var svgEl = document.getElementById('spark-'+c);
    if (svgEl) renderSparkline(svgEl, tIdx, c, dIdx);
  }}
}}

function renderSparkline(svgEl, tIdx, cvIdx, activeDIdx) {{
  var data  = sparklineData[tIdx][cvIdx];
  var means = data.m, ses = data.s, dis = data.di;
  var W=100, H=50, PAD=4;

  if (!means || means.length===0) {{
    svgEl.innerHTML='<text x="50" y="26" text-anchor="middle" font-size="9" fill="#334155">—</text>';
    return;
  }}

  var yLo = data.lo, yHi = data.hi;
  var yRange = (yHi - yLo) || 1;
  function xOf(di) {{ return PAD + (di/11)*(W-2*PAD); }}
  function yOf(v)  {{ return (H-PAD) - ((v-yLo)/yRange)*(H-2*PAD); }}

  /* SE band */
  var bUp=[], bDn=[];
  for (var i=0;i<means.length;i++) {{
    bUp.push(xOf(dis[i])+','+yOf(means[i]+ses[i]));
    bDn.unshift(xOf(dis[i])+','+yOf(means[i]-ses[i]));
  }}
  var bandPts = bUp.concat(bDn).join(' ');

  /* Mean polyline */
  var linePts = means.map(function(m,i){{ return xOf(dis[i])+','+yOf(m); }}).join(' ');

  /* Dots */
  var color = cvColors[sortedCvs[cvIdx]] || '#888';
  var dotsHtml = means.map(function(m,i){{
    var cx=xOf(dis[i]), cy=yOf(m);
    var isActive = (dis[i]===activeDIdx);
    return '<circle cx="'+cx+'" cy="'+cy+'" r="'+(isActive?3:1.5)+
           '" fill="'+color+'" stroke="white" stroke-width="'+(isActive?1.5:0.5)+'"/>';
  }}).join('');

  /* Active date line */
  var activeLine = '';
  if (dis.indexOf(activeDIdx) >= 0) {{
    var ax = xOf(activeDIdx);
    activeLine='<line x1="'+ax+'" y1="'+PAD+'" x2="'+ax+'" y2="'+(H-PAD)+
               '" stroke="rgba(99,102,241,0.55)" stroke-width="1.5" stroke-dasharray="2,2"/>';
  }}

  svgEl.innerHTML =
    '<polygon points="'+bandPts+'" fill="'+color+'" opacity="0.15"/>' +
    '<polyline points="'+linePts+'" stroke="'+color+
      '" stroke-width="1.5" fill="none" stroke-linejoin="round"/>' +
    dotsHtml + activeLine;
}}

/* ── Right panel ─────────────────────────────────────────────────── */
function updateRightPanel(tIdx, dIdx) {{
  updateKWCard(tIdx, dIdx);
  updateCLDTable(tIdx, dIdx);
  updateChampionBoard(tIdx);
}}

function updateKWCard(tIdx, dIdx) {{
  var lu = layoutUpdates[tIdx*N_DATES+dIdx];
  var kwS = lu.kw_stat_raw, kwP = lu.kw_p_raw, slbl = lu.sig_lbl, nCvs = lu.n_cvs;

  document.getElementById('kw-chi2').textContent = kwS!==null ? kwS.toFixed(3) : '—';
  document.getElementById('kw-p-val').textContent = kwP!==null ? kwP.toFixed(4) : '—';
  document.getElementById('kw-ncvs').textContent  = nCvs + ' cultivar' + (nCvs!==1?'s':'');

  var sbEl = document.getElementById('kw-sig-badge');
  sbEl.textContent = slbl;
  sbEl.className   = 'sig-badge ' + (slbl==='N/A'?'sig-na':slbl==='ns'?'sig-ns':'sig-s');

  var meterEl  = document.getElementById('kw-meter');
  var meterPct = 0, meterColor = '#334155';
  if (kwP!==null) {{
    meterPct = Math.min((-Math.log10(Math.max(kwP,1e-10)))/4*100, 100);
    meterColor = kwP<0.001?'#ef4444':kwP<0.01?'#f97316':kwP<0.05?'#eab308':'#475569';
  }}
  meterEl.style.width      = meterPct.toFixed(1)+'%';
  meterEl.style.background = meterColor;
}}

function updateCLDTable(tIdx, dIdx) {{
  var rows = cldTable[tIdx][dIdx];
  var html = '';
  rows.forEach(function(row) {{
    var bestClass = row.best ? ' class="cld-best-row"' : '';
    var borderStyle = row.best ? ' style="border-left-color:'+row.color+';"' : '';
    var meanSe = row.mean!==null
      ? row.mean.toFixed(2)+'<span class="se-text"> ±'+(row.se||0).toFixed(2)+'</span>'
      : '—';
    html +=
      '<tr'+bestClass+'>'+
      '<td'+borderStyle+'><span class="cv-dot" style="background:'+row.color+'"></span>'+row.cv+'</td>'+
      '<td>'+meanSe+'</td>'+
      '<td class="cld-letter">'+row.letter+'</td>'+
      '</tr>';
  }});
  document.getElementById('cld-tbody').innerHTML = html;
}}

function updateChampionBoard(tIdx) {{
  var ch = championData[tIdx];
  var winnerEl = document.getElementById('champion-winner');
  if (ch.winner) {{
    var wColor = ch.winner_color || '#888';
    winnerEl.innerHTML =
      '<div class="champ-winner-row">'+
      '<span class="cv-dot" style="background:'+wColor+';width:10px;height:10px;"></span>'+
      '<span class="champ-winner-name">'+ch.winner+'</span>'+
      '</div>';
  }} else {{
    winnerEl.innerHTML = '<div class="champ-no-winner">No significant dates for this trait</div>';
  }}

  var listHtml = '';
  var maxPct = ch.rankings.reduce(function(a,r){{ return Math.max(a,r.pct); }}, 0.01);
  ch.rankings.forEach(function(r) {{
    if (r.measured===0) return;
    var color   = cvColors[r.cv] || '#888';
    var barW    = (r.pct/100*100).toFixed(1)+'%';
    var cvShort = r.cv.length>9 ? r.cv.slice(0,9)+'…' : r.cv;
    listHtml +=
      '<div class="champ-row">'+
      '<span class="champ-cv" title="'+r.cv+'">'+cvShort+'</span>'+
      '<div class="champ-bar-track"><div class="champ-bar-fill" style="width:'+barW+';background:'+color+'"></div></div>'+
      '<span class="champ-score">'+r.wins+'/'+r.measured+'</span>'+
      '</div>';
  }});
  document.getElementById('champion-list').innerHTML = listHtml;
}}

/* ── Status bar ─────────────────────────────────────────────────── */
function updateStatusBar(tIdx, dIdx) {{
  var els = ['status-trait','status-date','status-kw'];
  els.forEach(function(id){{ document.getElementById(id).style.opacity='0'; }});
  setTimeout(function(){{
    var lu = layoutUpdates[tIdx*N_DATES+dIdx];
    document.getElementById('status-trait').textContent = traitLabels[tIdx];
    document.getElementById('status-date').textContent  = fmtDate(allDates[dIdx]);
    var kwEl = document.getElementById('status-kw');
    if (lu.kw_p_raw!==null) {{
      kwEl.textContent = 'p='+lu.kw_p_raw.toFixed(4)+' '+lu.sig_lbl;
      kwEl.style.color = lu.kw_p_raw<0.05?'#f87171':'#475569';
    }} else {{
      kwEl.textContent='—'; kwEl.style.color='#475569';
    }}
    els.forEach(function(id){{ document.getElementById(id).style.opacity='1'; }});
  }}, 140);
}}

/* ── Resize chart ───────────────────────────────────────────────── */
function resizeChart() {{
  var gd   = getGd();
  var wrap = document.getElementById('app-chart');
  if (gd && wrap && wrap.clientHeight>0) {{
    Plotly.relayout(gd, {{height: wrap.clientHeight}});
  }}
}}

/* ── Keyboard navigation ────────────────────────────────────────── */
function initKeyboard() {{
  document.addEventListener('keydown', function(e) {{
    var tag = document.activeElement ? document.activeElement.tagName : '';
    if (tag==='INPUT'||tag==='SELECT'||tag==='TEXTAREA') return;
    var handled = true;
    switch(e.key) {{
      case 'ArrowUp':   navigate(Math.max(0,curT-1), curD); break;
      case 'ArrowDown': navigate(Math.min(N_TRAITS-1,curT+1), curD); break;
      case 'ArrowLeft': navigate(curT, Math.max(0,curD-1)); break;
      case 'ArrowRight':navigate(curT, Math.min(N_DATES-1,curD+1)); break;
      case 'b': case 'B': switchToBar();  break;
      case 'l': case 'L': switchToLine(); break;
      case 'f': case 'F': toggleSigFilter(); break;
      default: handled=false;
    }}
    if (handled) e.preventDefault();
  }});
}}

/* ── Mode switching ─────────────────────────────────────────────── */
function switchToBar() {{
  if (curMode==='bar') return;
  curMode='bar';
  document.getElementById('app-body').classList.remove('line-mode');
  document.getElementById('btn-bar').classList.add('active');
  document.getElementById('btn-line').classList.remove('active');
  doBarAnimate(curT, curD, true);
  updateSparklines(curT, curD);
  setTimeout(resizeChart, 30);
}}

function switchToLine() {{
  if (curMode==='line') return;
  curMode='line';
  document.getElementById('app-body').classList.add('line-mode');
  document.getElementById('btn-line').classList.add('active');
  document.getElementById('btn-bar').classList.remove('active');
  doLineUpdate(curT, true);
  setTimeout(resizeChart, 30);
}}

/* ── Sig filter ─────────────────────────────────────────────────── */
function toggleSigFilter() {{
  var cb = document.getElementById('sig-filter');
  cb.checked = !cb.checked;
  applySigFilter(cb.checked);
}}

function applySigFilter(show_only_sig) {{
  document.querySelectorAll('.trait-item').forEach(function(el){{
    var tIdx = parseInt(el.dataset.tidx);
    var hasSig = sigMatrix[tIdx].some(function(v){{return v===2;}});
    el.style.display = (!show_only_sig || hasSig) ? '' : 'none';
  }});
}}

/* ── DOM ready ──────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', function() {{
  document.getElementById('btn-bar').addEventListener('click', switchToBar);
  document.getElementById('btn-line').addEventListener('click', switchToLine);
  document.getElementById('sig-filter').addEventListener('change', function(){{
    applySigFilter(this.checked);
  }});

  /* Trait list — event delegation (inline onclick can't reach IIFE scope) */
  document.getElementById('trait-list').addEventListener('click', function(e) {{
    var item = e.target.closest('.trait-item');
    if (item) navigate(parseInt(item.dataset.tidx), curD);
  }});

  /* Date timeline — event delegation */
  document.getElementById('timeline').addEventListener('click', function(e) {{
    var btn = e.target.closest('.date-dot');
    if (btn) navigate(curT, parseInt(btn.dataset.didx));
  }});

  initKeyboard();
  navigate(0, 0);
  setTimeout(resizeChart, 0);
}});

window.addEventListener('resize', resizeChart);

}})();
</script>
"""

    # ---------------------------------------------------------------- HTML
    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>Pheno 4 — Strawberry Research Dashboard</title>
  <style>{css}</style>
</head>
<body>

<header id="app-header">
  <div class="hdr-brand">
    <h1>&#127827; Pheno 4 &mdash; Strawberry Cultivar Analysis</h1>
    <p>11 cultivars &middot; 12 dates &middot; 19 traits &middot; Kruskal-Wallis &middot; Conover-Iman &middot; CLD</p>
  </div>
  <div class="hdr-spacer"></div>
  <div class="view-toggle" role="group">
    <button class="view-btn active" id="btn-bar">&#9646;&#9646; Bar Chart</button>
    <button class="view-btn"        id="btn-line">&#8599; Line Chart</button>
  </div>
  <div class="kbd-pill">
    <kbd>↑↓</kbd> trait &nbsp;
    <kbd>←→</kbd> date &nbsp;
    <kbd>F</kbd> filter &nbsp;
    <kbd>L</kbd>/<kbd>B</kbd> mode
  </div>
</header>

<div id="app-body">

  <!-- LEFT: Trait navigator -->
  <nav id="left-panel">
    <div class="left-header">
      <span class="left-header-label">Traits</span>
      <div class="sig-filter-wrap">
        <label>
          <input type="checkbox" id="sig-filter">
          sig. only
        </label>
      </div>
    </div>
    <div id="trait-list">
{trait_nav_html}    </div>
  </nav>

  <!-- CENTER TOP: Date timeline -->
  <div id="timeline">
    <span class="tl-label">Date</span>
    <div class="date-dots-row">
      {timeline_html}
    </div>
  </div>

  <!-- CENTER MID: Plotly chart -->
  <div id="app-chart">
    {plot_div}
  </div>

  <!-- CENTER BOTTOM: Cultivar sparklines -->
  <div id="sparkline-row">
    {spark_row_html}
  </div>

  <!-- RIGHT: Statistics panel -->
  <aside id="right-panel">

    <div class="rp-section">
      <div class="rp-hdr">Kruskal-Wallis</div>
      <div class="kw-row">
        <span class="kw-key">&#967;&#178;</span>
        <span class="kw-val" id="kw-chi2">—</span>
        <span class="sig-badge sig-na" id="kw-sig-badge">—</span>
      </div>
      <div class="kw-row">
        <span class="kw-key">p</span>
        <span class="kw-val" id="kw-p-val">—</span>
      </div>
      <div class="kw-row">
        <span class="kw-n" id="kw-ncvs">—</span>
      </div>
      <div class="kw-meter-track">
        <div class="kw-meter-fill" id="kw-meter"></div>
      </div>
      <div class="kw-meter-lbls"><span>ns</span><span>*</span><span>***</span></div>
    </div>

    <div class="rp-section">
      <div class="rp-hdr">CLD Rankings</div>
      <table id="cld-table">
        <thead>
          <tr>
            <th>Cultivar</th>
            <th>Mean&nbsp;&#177;&nbsp;SE</th>
            <th>CLD</th>
          </tr>
        </thead>
        <tbody id="cld-tbody"></tbody>
      </table>
    </div>

    <div class="rp-section">
      <div class="rp-hdr">Trait Champion</div>
      <div id="champion-winner"></div>
      <div id="champion-list"></div>
      <div class="champ-note">wins / sig. dates measured</div>
    </div>

  </aside>

</div><!-- #app-body -->

<div id="status-bar">
  <div class="sb-pill">
    <span class="sb-chip">Trait</span>
    <span id="status-trait" style="color:#94a3b8;">—</span>
  </div>
  <div class="sb-pill">
    <span class="sb-chip">Date</span>
    <span id="status-date" style="color:#94a3b8;">—</span>
  </div>
  <div class="sb-pill">
    <span class="sb-chip">KW</span>
    <span id="status-kw" style="color:#475569;">—</span>
  </div>
  <div class="sb-pill">
    <span style="color:#334155;font-size:10px;">
      Red dots = significant (p&lt;0.05) &nbsp;&#183;&nbsp;
      Colored bars = best group &nbsp;&#183;&nbsp;
      &#9733; = best &amp; sig.
    </span>
  </div>
</div>

{js}
</body>
</html>"""

    return page


# ===========================================================================
# Public API — callable from Flask or standalone
# ===========================================================================

def generate_html(df: pd.DataFrame) -> str:
    """
    Run the full analysis pipeline on *df* (tidy, row-per-rep DataFrame as
    produced by etl.run_etl_from_bytes / etl.run_etl) and return the complete
    dashboard HTML string.  Does not write any files.
    """
    stats_results = precompute_all_stats(df)

    df_dated = df.copy()
    df_dated["date"] = pd.to_datetime(df_dated["date"]).dt.strftime("%Y-%m-%d")
    all_dates = sorted(df_dated["date"].unique())

    fig, all_bar_data, layout_updates, line_layout_updates, _ = \
        build_figure(df_dated, stats_results)
    fig = apply_layout(fig, layout_updates, ALL_TRAITS, all_dates)

    spark_data    = _compute_spark_data(stats_results, all_dates)
    sig_matrix    = _compute_sig_matrix(stats_results, all_dates)
    cld_table     = _compute_cld_table(stats_results, all_dates)
    champion_data = _compute_champion_data(stats_results, all_dates)

    plot_div = fig.to_html(
        include_plotlyjs="cdn", full_html=False, div_id="pheno4_chart",
    )

    return build_full_page(
        plot_div,
        len(ALL_TRAITS), len(all_dates),
        all_bar_data, layout_updates, line_layout_updates,
        spark_data, sig_matrix, cld_table, champion_data,
        all_dates,
    )


# ===========================================================================
# Entry point
# ===========================================================================

def main() -> None:
    if not RAW_CSV.exists():
        print(f"ERROR: {RAW_CSV} not found. Run src/etl.py first.")
        raise SystemExit(1)

    print(f"Loading: {RAW_CSV}")
    df_raw = pd.read_csv(str(RAW_CSV), parse_dates=["date"])
    print(f"  {df_raw.shape[0]} rows × {df_raw.shape[1]} columns")

    print("Building dashboard…")
    html_str = generate_html(df_raw)
    OUT_HTML.write_text(html_str, encoding="utf-8")
    print(f"Saved → {OUT_HTML}")
    print(f"Size  : {OUT_HTML.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
