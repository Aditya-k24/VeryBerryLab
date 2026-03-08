"""
tests/test_parser.py
====================
Unit tests for src/parse_codes.py.

Code format uses DOTS as separators (confirmed from Worksheet 1):
    1.1.2.1        → Mother 1 → Primary stolon 1 → Node 2 → Daughter 1
    1.1.2/1.2.1    → Mother 1 → Primary stolon 1 → Node 2 → Secondary stolon 1 → Node 2 → Daughter 1
    3.1.2/1.2/1.2.1 → Mother 3 → ... → Tertiary → Daughter 1
    1.4.1/1.2/1.2/1 → quaternary stolon, terminal (no daughter yet)

Run from veryberrylab/ directory:
    pytest tests/
    pytest tests/ -v
"""

import sys
from pathlib import Path

import pytest

# Allow imports from parent package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.parse_codes import (
    ParsedCode,
    Stolon,
    DaughterNode,
    parse_single_code,
    count_stolons_by_order,
    count_daughters_by_order,
)


# ============================================================
# Helper
# ============================================================

def assert_no_errors(result: ParsedCode, code: str) -> None:
    assert result.parse_errors == [], \
        f"Unexpected parse errors for '{code}': {result.parse_errors}"


# ============================================================
# Primary-only codes
# ============================================================

class TestPrimaryOnly:
    def test_basic_primary(self):
        """1.1.2.1 → Mother 1, primary stolon 1, node 2, daughter 1."""
        r = parse_single_code("1.1.2.1")
        assert_no_errors(r, "1.1.2.1")
        assert r.mother_id == 1
        assert len(r.stolons) == 1
        s = r.stolons[0]
        assert s.stolon_order == 1
        assert s.stolon_id == 1
        assert s.parent_stolon_id is None
        assert len(s.daughters) == 1
        d = s.daughters[0]
        assert d.node_id == 2
        assert d.daughter_id == 1
        assert d.stolon_order == 1

    def test_different_node_and_daughter(self):
        """1.1.4.2 → Node 4, Daughter 2."""
        r = parse_single_code("1.1.4.2")
        assert_no_errors(r, "1.1.4.2")
        assert r.mother_id == 1
        assert r.stolons[0].daughters[0].node_id == 4
        assert r.stolons[0].daughters[0].daughter_id == 2

    def test_different_stolon_id(self):
        """2.3.2.1 → Mother 2, stolon 3."""
        r = parse_single_code("2.3.2.1")
        assert r.mother_id == 2
        assert r.stolons[0].stolon_id == 3

    def test_mother_3(self):
        """3.2.2.1 → Mother 3."""
        r = parse_single_code("3.2.2.1")
        assert r.mother_id == 3

    def test_primary_no_daughter_three_parts(self):
        """1.1.4 → primary stolon exists, node 4, no daughter yet (terminal stolon)."""
        r = parse_single_code("1.1.4")
        assert_no_errors(r, "1.1.4")
        assert r.mother_id == 1
        assert len(r.stolons) == 1
        assert len(r.stolons[0].daughters) == 0


# ============================================================
# Secondary stolon codes
# ============================================================

class TestSecondary:
    def test_basic_secondary(self):
        """1.1.2/1.2.1 → Primary stolon 1, branches at node 2 → Secondary stolon 1, node 2, daughter 1."""
        r = parse_single_code("1.1.2/1.2.1")
        assert_no_errors(r, "1.1.2/1.2.1")
        assert r.mother_id == 1
        assert len(r.stolons) == 2

        primary = r.stolons[0]
        assert primary.stolon_order == 1
        assert primary.stolon_id == 1
        assert primary.branch_node_id is None  # branch node is in next stolon
        assert len(primary.daughters) == 0     # branch at node — no daughter on primary here

        secondary = r.stolons[1]
        assert secondary.stolon_order == 2
        assert secondary.stolon_id == 1
        assert secondary.parent_stolon_id == 1  # parent is primary stolon id=1
        assert len(secondary.daughters) == 1
        assert secondary.daughters[0].node_id == 2
        assert secondary.daughters[0].daughter_id == 1
        assert secondary.daughters[0].stolon_order == 2

    def test_secondary_stolon_id_2(self):
        """2.1.2/2.2.1 → Secondary stolon 2."""
        r = parse_single_code("2.1.2/2.2.1")
        assert r.stolons[1].stolon_id == 2

    def test_secondary_terminal(self):
        """2.2.4 → Primary stolon 2, node 4, branch — secondary has no daughter."""
        # This would appear as 2.2.4/1 in Worksheet 1 (sec stolon 1, no daughter node)
        r = parse_single_code("2.2.4/1")
        assert len(r.stolons) == 2
        sec = r.stolons[1]
        assert sec.stolon_order == 2
        assert sec.stolon_id == 1
        assert len(sec.daughters) == 0


# ============================================================
# Tertiary stolon codes
# ============================================================

class TestTertiary:
    def test_tertiary(self):
        """3.1.2/1.2/1.2.1 → tertiary stolon → daughter 1."""
        r = parse_single_code("3.1.2/1.2/1.2.1")
        assert_no_errors(r, "3.1.2/1.2/1.2.1")
        assert r.mother_id == 3
        assert len(r.stolons) == 3

        primary   = r.stolons[0]
        secondary = r.stolons[1]
        tertiary  = r.stolons[2]

        assert primary.stolon_order   == 1
        assert secondary.stolon_order == 2
        assert tertiary.stolon_order  == 3

        assert tertiary.daughters[0].daughter_id == 1
        assert tertiary.daughters[0].stolon_order == 3

    def test_tertiary_stolon_linking(self):
        """Secondary parent_stolon_id links correctly."""
        r = parse_single_code("1.2.2/1.2/1.2.1")
        primary   = r.stolons[0]
        secondary = r.stolons[1]
        tertiary  = r.stolons[2]
        assert primary.stolon_id         == 2
        assert secondary.parent_stolon_id == 2  # parent = primary stolon_id
        assert tertiary.parent_stolon_id  == secondary.stolon_id


# ============================================================
# Quaternary stolon codes
# ============================================================

class TestQuaternary:
    def test_quaternary_terminal(self):
        """1.4.1/1.2/1.2/1 → quaternary stolon id=1, no daughter."""
        r = parse_single_code("1.4.1/1.2/1.2/1")
        assert len(r.stolons) == 4
        quat = r.stolons[3]
        assert quat.stolon_order == 4
        assert quat.stolon_id   == 1
        assert len(quat.daughters) == 0

    def test_quaternary_with_daughter(self):
        """1.1.1/1.1/1.1/1.1.1 → quaternary stolon 1, node 1, daughter 1."""
        r = parse_single_code("1.1.1/1.1/1.1/1.1.1")
        assert_no_errors(r, "1.1.1/1.1/1.1/1.1.1")
        quat = r.stolons[3]
        assert quat.stolon_order == 4
        assert len(quat.daughters) == 1
        assert quat.daughters[0].daughter_id == 1

    def test_stolon_orders_all_four(self):
        r = parse_single_code("2.1.2/1.2/1.2/1.2.1")
        orders = [s.stolon_order for s in r.stolons]
        assert orders == [1, 2, 3, 4]


# ============================================================
# Error handling
# ============================================================

class TestErrorHandling:
    def test_malformed_primary(self):
        """Too few parts in primary segment."""
        r = parse_single_code("1.1")
        assert len(r.parse_errors) > 0
        assert r.mother_id == -1

    def test_empty_string(self):
        r = parse_single_code("")
        assert len(r.parse_errors) > 0
        assert r.mother_id == -1

    def test_single_digit(self):
        """A bare digit as code — should fail gracefully."""
        r = parse_single_code("1")
        assert len(r.parse_errors) > 0 or len(r.stolons) == 0


# ============================================================
# Counting helpers
# ============================================================

class TestCountHelpers:
    def test_count_stolons_primary_only(self):
        codes = [parse_single_code("1.1.2.1"), parse_single_code("1.2.2.1")]
        counts = count_stolons_by_order(codes)
        assert counts[1] == 2  # stolon ids 1 and 2
        assert counts[2] == 0
        assert counts[3] == 0
        assert counts[4] == 0

    def test_count_daughters_primary_only(self):
        codes = [parse_single_code("1.1.2.1"), parse_single_code("1.2.4.2")]
        counts = count_daughters_by_order(codes)
        assert counts[1] == 2  # two daughters on primary stolons
        assert counts[2] == 0

    def test_count_mixed_orders(self):
        codes = [
            parse_single_code("1.1.2.1"),         # primary daughter
            parse_single_code("1.1.2/1.2.1"),      # secondary daughter
            parse_single_code("3.1.2/1.2/1.2.1"),  # tertiary daughter
        ]
        s_counts = count_stolons_by_order(codes)
        d_counts = count_daughters_by_order(codes)
        assert s_counts[1] >= 1
        assert s_counts[2] >= 1
        assert s_counts[3] >= 1
        assert d_counts[1] == 1
        assert d_counts[2] == 1
        assert d_counts[3] == 1

    def test_count_unique_stolon_ids(self):
        """Duplicate stolon IDs across different codes should be counted once."""
        codes = [
            parse_single_code("1.1.2.1"),
            parse_single_code("1.1.4.2"),  # same primary stolon id=1
        ]
        counts = count_stolons_by_order(codes)
        # stolon_id=1 appears in both codes; unique count should be 1
        assert counts[1] == 1

    def test_empty_codes(self):
        counts = count_stolons_by_order([])
        assert all(v == 0 for v in counts.values())


# ============================================================
# Integration: real-looking codes from Worksheet 1
# ============================================================

class TestRealCodes:
    """Examples taken directly from Worksheet 1 (Finn sheet, confirmed values)."""

    @pytest.mark.parametrize("code,expected_orders", [
        ("1.1.2.1",           [1]),
        ("1.1.4.2",           [1]),
        ("1.1.2/1.2.1",       [1, 2]),
        ("1.1.2/2.2.1",       [1, 2]),
        ("3.1.2/1.2/1.2.1",   [1, 2, 3]),
        ("1.4.1/1.2/1.2/1",   [1, 2, 3, 4]),
    ])
    def test_stolon_orders_present(self, code, expected_orders):
        r = parse_single_code(code)
        actual_orders = sorted({s.stolon_order for s in r.stolons})
        assert actual_orders == expected_orders, \
            f"Code '{code}': expected orders {expected_orders}, got {actual_orders}"

    @pytest.mark.parametrize("code", [
        "1.1.2.1", "2.1.2.1", "3.1.2.1",  # all three mothers
        "1.2.2.1", "1.3.2.1",               # different primary stolons
        "1.1.2/1.2.1",
        "3.1.2/1.2/1.2.1",
    ])
    def test_no_parse_errors(self, code):
        r = parse_single_code(code)
        assert r.parse_errors == [], f"Parse errors in '{code}': {r.parse_errors}"
