"""Tests for construction update PDF parsing."""

from __future__ import annotations

from finance_common.parsing.construction_update_pdf import (
    parse_construction_report_from_text_per_page,
    tower_number_from_tabular_index,
    tower_zone_key,
)


def test_tower_number_skips_13() -> None:
    assert tower_number_from_tabular_index(1) == 1
    assert tower_number_from_tabular_index(12) == 12
    assert tower_number_from_tabular_index(13) == 14
    assert tower_number_from_tabular_index(14) == 15


def test_tower_zone_key() -> None:
    assert tower_zone_key(14) == "tower:14"


def test_parse_sample_page1() -> None:
    page1 = """
STATUS AS ON 31st-Mar-2026
ATS Destinaire

Activity Floors
Complete*
%
Completed Status Remark
Structure
Structure 26 100% Completed
Brickwork 26 100% Completed
Finishing
Internal Plaster Gypsum 26 100% Completed
Services
Plumbing CPVC 26 100% Complete
"""
    rep = parse_construction_report_from_text_per_page([page1])
    assert rep.as_of_date is not None
    assert rep.as_of_date.year == 2026
    assert len(rep.zones) == 1
    z = rep.zones[0]
    assert z.zone_key == "tower:1"
    assert z.tower_number == 1
    activities = [r.activity_raw for r in z.rows]
    assert any("Structure" in a for a in activities)
    assert any("Brickwork" in a for a in activities)
    assert any("Internal Plaster" in a for a in activities)


def test_pdf_noise_lines_no_spurious_warnings() -> None:
    """Column headers and lone %% fragments must not emit tower row / empty activity warnings."""
    from finance_common.parsing.construction_update_pdf import _parse_tower_page_body

    w: list[str] = []
    text = """
Activity Floors
Complete*
%
Completed Status Remark
Activity Floors Complete* % Completed
Structure
Structure 26 100% Completed
55%
30%
98%
97%
WIP Brickwork 10 38%
"""
    rows = _parse_tower_page_body(text, w)
    assert len(rows) >= 2
    noise = [x for x in w if "tower row not parsed" in x or "empty activity" in x]
    assert not noise, noise


def test_parse_builder_pdf_style_lines() -> None:
    """Lines as extracted from real builder PDFs (status / % column order varies)."""
    from finance_common.parsing.construction_update_pdf import _parse_table_row

    w: list[str] = []
    cases = [
        ("100% Completed Brickwork 26 100%", "Brickwork", 26, 100),
        ("Completed Staircase Railing 26 100%", "Staircase Railing", 26, 100),
        ("WIP Toilet Water Proofing 7 27%", "Toilet Water Proofing", 7, 27),
        ("WIP Electricity Meters 0%", "Electricity Meters", None, 0),
        ("WIP UPVC Fittings (W&D) 0 0%", "UPVC Fittings (W&D)", 0, 0),
        ("Completed Expect Builder Hoist Balcony GRC Jali 5 ( Piece) 9%", "GRC Jali", 5, 9),
        ("Completed External Plaster ( Up to Level plast) 30% 30%", "External Plaster ( Up to Level plast)", None, 30),
        ("98% WIP UPVC Frame & Shutter (W&D) 26 96%", "UPVC Frame & Shutter (W&D)", 26, 96),
    ]
    for raw, want_act, want_fl, want_pct in cases:
        pr = _parse_table_row(raw, w)
        assert pr is not None, raw
        assert want_act in pr.activity_raw or pr.activity_raw == want_act, (raw, pr.activity_raw)
        assert pr.floors_complete == want_fl
        assert pr.pct_complete == want_pct


def test_parse_multiple_tower_pages_and_common() -> None:
    tower_a = """
Activity Floors
Complete*
Structure
Structure 26 100% Completed
Finishing
Wall Tiles 7 27% WIP
Services
Lift 0 0%
"""
    tower_b = """
Activity Floors
Complete*
Structure
Structure 26 100% Completed
"""
    common = """
Landscape
some notes here
"""
    rep = parse_construction_report_from_text_per_page([tower_a, tower_b, common])
    assert len(rep.zones) == 3
    assert rep.zones[0].zone_key == "tower:1"
    assert rep.zones[1].zone_key == "tower:2"
    assert rep.zones[2].zone_key == "section:landscape"
