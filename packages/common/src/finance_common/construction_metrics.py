"""Completion % helpers (e.g. total floors in building for PDF-reported floor counts)."""

from __future__ import annotations


def effective_completion_pct(
    pct_complete: int | None,
    floors_complete: int | None,
    *,
    total_floors: int,
) -> int | None:
    """Prefer PDF %%; else derive from floors_complete / total_floors."""
    if total_floors <= 0:
        return None
    if pct_complete is not None:
        return min(100, max(0, int(pct_complete)))
    if floors_complete is not None:
        return min(100, max(0, round(100 * floors_complete / total_floors)))
    return None


def floors_pct_of_total(
    floors_complete: int | None,
    *,
    total_floors: int,
) -> int | None:
    if floors_complete is None or total_floors <= 0:
        return None
    return min(100, max(0, round(100 * floors_complete / total_floors)))
