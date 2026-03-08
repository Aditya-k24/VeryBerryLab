"""
src/parse_codes.py
==================
Phase 2 — parser for Worksheet 1 raw stolon path codes.

Code format (confirmed from Worksheet 1 inspection):
    Uses DOTS as intra-level separators, SLASHES for stolon-order transitions.

    Primary only  :  m.s.n.d        e.g.  1.1.2.1
    With secondary:  m.s.n/s2.n2.d  e.g.  1.1.2/1.2.1
    With tertiary :  m.s.n/s2.n2/s3.n3.d  e.g.  3.1.2/1.2/1.2.1
    Quaternary    :  m.s.n/s2.n2/s3.n3/s4.n4.d

    A path may end without a daughter_id if the stolon exists but has no
    daughter plant yet (terminal stolon):
        e.g.  2.1.4.2  has 4 dot-parts (mother, stolon, node, daughter)
              2.1.4    has 3 dot-parts (mother, stolon, node — no daughter)

    NOTE: The plan BNF used hyphens; actual data uses dots. The grammar
    is otherwise identical. See ASSUMPTIONS.md.

Usage:
    from src.parse_codes import parse_single_code, parse_plant_codes

    result = parse_single_code("1.1.2.1")
    print(result.mother_id, result.stolons)

Run standalone (demo):
    python src/parse_codes.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pandas as pd

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class DaughterNode:
    """A daughter plant at a specific node on a stolon."""
    node_id:      int
    daughter_id:  int
    stolon_order: int  # 1=primary, 2=secondary, 3=tertiary, 4=quaternary


@dataclass
class Stolon:
    """One stolon, possibly carrying daughters and child stolons."""
    stolon_order:    int                  # 1–4
    stolon_id:       int                  # sequential ID within parent
    parent_stolon_id: Optional[int]       # None for primary
    branch_node_id:  Optional[int]        # node on parent where this stolon branches
    daughters:       list[DaughterNode] = field(default_factory=list)
    children:        list["Stolon"]    = field(default_factory=list)


@dataclass
class ParsedCode:
    """Result of parsing one code string."""
    raw:          str
    mother_id:    int
    stolons:      list[Stolon]
    parse_errors: list[str] = field(default_factory=list)


@dataclass
class MotherPlant:
    """All parsed codes for one mother plant on one measurement date."""
    date:           str
    cultivar:       str
    mother_id:      int
    parsed_codes:   list[ParsedCode] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Single-code parser
# ---------------------------------------------------------------------------

def parse_single_code(raw: str) -> ParsedCode:
    """
    Parse one code string into a ParsedCode object.

    Algorithm
    ---------
    1. Split on '/' → segments.
       e.g. "1.1.2/1.2.1" → ["1.1.2", "1.2.1"]

    2. Segment 0 is the primary stolon path:
       parts = split on '.', length 3 or 4
         parts[0] = mother_id
         parts[1] = primary stolon_id
         parts[2] = node_id  (the branching node — daughter in next segment,
                              OR the terminal node if no slash follows AND len==4)
         parts[3] = daughter_id (only if len == 4 AND no slash follows)

    3. For each subsequent segment i (1-indexed → stolon order i+1):
       parts = split on '.'
         parts[0] = stolon_id
         parts[1] = node_id        (if len >= 2)
         parts[2] = daughter_id    (if len == 3)
       parent node for the branch = previous segment's last node_id

    4. A segment with only one part (stolon_id only) means a terminal stolon
       with no node or daughter recorded yet.
    """
    raw = raw.strip()
    errors: list[str] = []
    segments = raw.split("/")

    # ---- Segment 0: primary stolon ----
    primary_parts = segments[0].split(".")
    if len(primary_parts) < 3:
        return ParsedCode(
            raw=raw, mother_id=-1, stolons=[],
            parse_errors=[f"Malformed primary segment: '{segments[0]}'"],
        )

    try:
        mother_id = int(primary_parts[0])
    except ValueError:
        return ParsedCode(
            raw=raw, mother_id=-1, stolons=[],
            parse_errors=[f"Non-integer mother_id: '{primary_parts[0]}'"],
        )

    # Primary node_id is parts[2]; if only 3 parts and no following segments → no daughter
    primary_node_id = int(primary_parts[2])
    primary_stolon = Stolon(
        stolon_order=1,
        stolon_id=int(primary_parts[1]),
        parent_stolon_id=None,
        branch_node_id=None,
    )

    # A 4-part primary segment AND no more segments → daughter on this primary stolon
    if len(primary_parts) == 4 and len(segments) == 1:
        primary_stolon.daughters.append(DaughterNode(
            node_id=primary_node_id,
            daughter_id=int(primary_parts[3]),
            stolon_order=1,
        ))

    stolons: list[Stolon] = [primary_stolon]
    # Track the node_id of the branch point from the previous segment
    branch_node_stack = [primary_node_id]

    # ---- Subsequent segments: secondary, tertiary, quaternary ----
    for i, seg in enumerate(segments[1:], start=2):
        parts = seg.split(".")
        branch_node = branch_node_stack[-1]

        stolon_id: int
        node_id:   Optional[int] = None
        daughter_id: Optional[int] = None

        if not parts[0].isdigit():
            errors.append(f"Non-integer stolon_id in segment {i}: '{parts[0]}'")
            stolon_id = -1
        else:
            stolon_id = int(parts[0])

        if len(parts) >= 2:
            try:
                node_id = int(parts[1])
            except ValueError:
                errors.append(f"Non-integer node_id in segment {i}: '{parts[1]}'")

        if len(parts) == 3:
            try:
                daughter_id = int(parts[2])
            except ValueError:
                errors.append(f"Non-integer daughter_id in segment {i}: '{parts[2]}'")

        stolon = Stolon(
            stolon_order=i,
            stolon_id=stolon_id,
            parent_stolon_id=stolons[i - 2].stolon_id,  # parent is previous stolon
            branch_node_id=branch_node,
        )

        # Last segment with a daughter_id → record it
        if daughter_id is not None and i == len(segments):
            stolon.daughters.append(DaughterNode(
                node_id=node_id if node_id is not None else -1,
                daughter_id=daughter_id,
                stolon_order=i,
            ))

        stolons.append(stolon)
        branch_node_stack.append(node_id if node_id is not None else -1)

    return ParsedCode(
        raw=raw,
        mother_id=mother_id,
        stolons=stolons,
        parse_errors=errors,
    )


# ---------------------------------------------------------------------------
# Plant-level summary from parsed codes
# ---------------------------------------------------------------------------

def count_stolons_by_order(parsed_codes: list[ParsedCode]) -> dict[int, int]:
    """
    Count unique stolons by order from a list of ParsedCode objects.

    NOTE: This UNDERCOUNTS stolons that have no daughter paths (barren stolons).
    Cross-reference with Worksheet 2 totals. See ASSUMPTIONS.md and the
    reconciliation logic below.
    """
    id_sets: dict[int, set[int]] = {1: set(), 2: set(), 3: set(), 4: set()}
    for code in parsed_codes:
        for stolon in code.stolons:
            if 1 <= stolon.stolon_order <= 4:
                id_sets[stolon.stolon_order].add(stolon.stolon_id)
    return {order: len(ids) for order, ids in id_sets.items()}


def count_daughters_by_order(parsed_codes: list[ParsedCode]) -> dict[int, int]:
    """Count total daughter plants by stolon order."""
    counts: dict[int, int] = {1: 0, 2: 0, 3: 0, 4: 0}
    for code in parsed_codes:
        for stolon in code.stolons:
            for dp in stolon.daughters:
                if 1 <= dp.stolon_order <= 4:
                    counts[dp.stolon_order] += 1
    return counts


# ---------------------------------------------------------------------------
# Batch parser for one cultivar sheet
# ---------------------------------------------------------------------------

def parse_plant_codes(
    ws,              # openpyxl worksheet (Worksheet 1 sheet)
    cultivar: str,
) -> list[MotherPlant]:
    """
    Parse all code entries in one Worksheet 1 cultivar sheet.

    Worksheet 1 layout (confirmed by inspection):
      - Row 2: column headers
      - Blocks separated by 'Date' rows (row[0] == 'Date')
      - Within each date block: data rows where row[0] is a code string
        (starts with a digit and contains dots)
      - '# Stolons total' in col 5 (index 5) = stolon total for that group
    """
    plants: list[MotherPlant] = []
    current_date: Optional[str] = None
    current_plants: dict[int, MotherPlant] = {}  # mother_id → MotherPlant

    for row in ws.iter_rows(values_only=True):
        cell0 = row[0]
        if cell0 is None:
            continue

        cell0_str = str(cell0).strip()

        # Date marker row
        if cell0_str == "Date":
            # Flush previous date's plants
            plants.extend(current_plants.values())
            current_plants = {}
            # Extract date from column 1
            date_val = row[1]
            if hasattr(date_val, "strftime"):
                current_date = date_val.strftime("%Y-%m-%d")
            else:
                current_date = str(date_val) if date_val else None
            continue

        if current_date is None:
            continue

        # Code row: starts with a digit (mother_id)
        if cell0_str and cell0_str[0].isdigit() and "." in cell0_str:
            code = parse_single_code(cell0_str)
            if code.mother_id not in current_plants:
                current_plants[code.mother_id] = MotherPlant(
                    date=current_date,
                    cultivar=cultivar,
                    mother_id=code.mother_id,
                )
            current_plants[code.mother_id].parsed_codes.append(code)

    # Flush last date
    plants.extend(current_plants.values())
    return plants


# ---------------------------------------------------------------------------
# Reconciliation against Worksheet 2
# ---------------------------------------------------------------------------

def reconcile(
    plants: list[MotherPlant],
    ws2_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Compare parsed stolon/daughter counts against Worksheet 2 ground-truth counts.

    Returns a DataFrame with columns:
        date, cultivar, mother_id, order,
        parsed_stolon_count, ws2_stolon_count, barren_count,
        parsed_daughter_count, ws2_daughter_count, daughter_discrepancy
    """
    ws2_stolon_cols = {
        1: "n_stolon_primary",
        2: "n_stolon_secondary",
        3: "n_stolon_tertiary",
        4: "n_stolon_quaternary",
    }

    records = []
    for plant in plants:
        stolon_counts   = count_stolons_by_order(plant.parsed_codes)
        daughter_counts = count_daughters_by_order(plant.parsed_codes)

        try:
            ws2_row = ws2_df.loc[
                (ws2_df["date"] == plant.date)
                & (ws2_df["cultivar"] == plant.cultivar)
                & (ws2_df["rep"] == plant.mother_id)
            ].iloc[0]
        except IndexError:
            ws2_row = None

        for order in range(1, 5):
            parsed_s = stolon_counts.get(order, 0)
            ws2_s    = int(ws2_row[ws2_stolon_cols[order]]) if ws2_row is not None else None
            barren   = (ws2_s - parsed_s) if ws2_s is not None else None

            if barren is not None and barren < 0:
                flag = "ERROR: parsed > worksheet2"
            elif barren is not None and barren > 0:
                flag = "barren stolons present"
            else:
                flag = "ok"

            records.append({
                "date":                  plant.date,
                "cultivar":              plant.cultivar,
                "mother_id":             plant.mother_id,
                "stolon_order":          order,
                "parsed_stolon_count":   parsed_s,
                "ws2_stolon_count":      ws2_s,
                "barren_count":          barren,
                "parsed_daughter_count": daughter_counts.get(order, 0),
                "flag":                  flag,
            })

    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Demo / entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import openpyxl

    ROOT = Path(__file__).resolve().parent.parent
    WS1_PATH = ROOT / "data" / "raw" / "Phenotyping 4 Worksheet 1.xlsx"

    print("=== Demo: parse first few codes ===")
    test_codes = [
        "1.1.2.1",
        "1.1.4.2",
        "1.1.2/1.2.1",
        "3.1.2/1.2/1.2.1",
        "1.4.1/1.2/1.2/1",
    ]
    for code in test_codes:
        result = parse_single_code(code)
        print(f"\nCode : {code}")
        print(f"  mother_id = {result.mother_id}")
        for s in result.stolons:
            d_str = ", ".join(
                f"dp@node{d.node_id}={d.daughter_id}" for d in s.daughters
            ) or "no daughter"
            print(f"  Stolon order={s.stolon_order} id={s.stolon_id} "
                  f"branch_node={s.branch_node_id} | {d_str}")
        if result.parse_errors:
            print(f"  ERRORS: {result.parse_errors}")

    print("\n=== Batch parse Worksheet 1 (Finn sheet) ===")
    from src.etl import CULTIVAR_MAP  # noqa: E402
    wb = openpyxl.load_workbook(str(WS1_PATH), read_only=True, data_only=True)
    fin_ws = wb["Fin"]
    plants = parse_plant_codes(fin_ws, "Finn")
    wb.close()

    print(f"Parsed {len(plants)} mother-plant × date records")
    for p in plants[:3]:
        s_counts = count_stolons_by_order(p.parsed_codes)
        d_counts = count_daughters_by_order(p.parsed_codes)
        print(f"  {p.date}  mother={p.mother_id}  "
              f"stolons={s_counts}  daughters={d_counts}  "
              f"codes={len(p.parsed_codes)}")
