"""Positional-code parsing and the animation render invariant: the rendered
D3 hierarchy must reproduce parsed daughter/stolon counts exactly, with no
invented nodes."""
from pathlib import Path

import pytest

from src.plant_arch import (Plant, _ingest_code, _to_d3_hierarchy,
                            _count_hierarchy, validate_render, load_all_plants)
from src.ws1_parser import load_ws1

DATA = Path(__file__).resolve().parent.parent / "data"


def test_ingest_simple_code():
    p = Plant("Test")
    _ingest_code("1.1.2.1", [2.0, 2.0], p)   # mother1 -> pri stolon1 -> node2 -> daughter1
    assert p.mother_ids() == [1]
    assert p.stolon_count(1) == 1
    assert p.node_count(1) == 2              # nodes 1 and 2
    assert p.dp_count(1) == 1                # one daughter at terminal node


def test_ingest_ignores_blank_and_nan():
    p = Plant("Test")
    _ingest_code("nan", [], p)
    _ingest_code("", [], p)
    _ingest_code("1.2", [], p)               # too short (<3 ints) -> ignored
    assert p.stolon_count() == 0


def test_branch_attaches_to_parent_node():
    p = Plant("Test")
    _ingest_code("1.1.3/2.1.1", [2, 2, 2, 2], p)   # branch off node of pri stolon
    assert p.stolon_count(1) >= 2            # primary + child stolon
    # child stolon must record a parent node (encoded position, not invented)
    child = [s for k, s in p.stolons.items() if s.parent_node_key is not None]
    assert child


@pytest.mark.skipif(not (DATA / "Pheno 4 Worksheet 3.xlsx").exists(),
                    reason="WS3 workbook not present")
def test_render_matches_parsed_counts_all_mothers():
    plants = load_all_plants()
    ws1 = load_ws1()
    assert plants
    for cv in sorted(set(plants) & set(ws1)):
        pl = plants[cv]
        w = ws1[cv]
        n = len(w["dates"])
        cfd = {}
        for i, d in enumerate(w["dates"]):
            for c in w["codes_by_date"].get(d, []):
                cfd.setdefault(c, i)
        for mid in pl.mother_ids():
            v = validate_render(pl, mid, cfd, n)
            assert v["ok"], f"{cv} M{mid} render/parse mismatch: {v}"


def test_count_hierarchy_helper():
    p = Plant("Test")
    _ingest_code("1.1.2.1", [2, 2], p)
    h = _to_d3_hierarchy(p, 1, {"1.1.2.1": 0}, 3)
    dp, st = _count_hierarchy(h)
    assert dp == p.dp_count(1)
    assert st == p.stolon_count(1)
