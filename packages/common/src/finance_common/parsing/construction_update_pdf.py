"""Parse builder construction update PDFs (tabular tower progress + common sections)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

import fitz  # type: ignore[import-untyped]

_MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


def tower_number_from_tabular_index(tabular_index: int) -> int:
    """1-based tabular page index; tower 13 is skipped after 12."""
    if tabular_index < 1:
        msg = "tabular_index must be >= 1"
        raise ValueError(msg)
    return tabular_index + (1 if tabular_index >= 13 else 0)


def tower_zone_key(tower_number: int) -> str:
    return f"tower:{tower_number}"


def normalized_activity_key(activity_raw: str) -> str:
    s = activity_raw.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return re.sub(r"_+", "_", s).strip("_") or "unknown"


@dataclass
class ParsedProgressRow:
    section: str
    activity_raw: str
    floors_complete: int | None
    pct_complete: int | None
    status: str | None
    remark: str | None


@dataclass
class ParsedZone:
    zone_key: str
    zone_type: str
    tower_number: int | None
    tabular_index: int | None
    page_index: int
    rows: list[ParsedProgressRow] = field(default_factory=list)
    raw_preview: str | None = None


@dataclass
class ParsedConstructionReport:
    project_title: str | None
    as_of_date: date | None
    zones: list[ParsedZone]
    warnings: list[str] = field(default_factory=list)


def _parse_as_of_date(full_text: str) -> date | None:
    # e.g. STATUSAS ON 31st-Mar-2026, STATUS AS ON 31-Mar-2026
    m = re.search(
        r"STATUS\s*AS\s*ON\s*(\d{1,2})\s*(?:st|nd|rd|th)?\s*[-\s]*([A-Za-z]{3,9})\s*[-\s]*(\d{4})",
        full_text,
        re.IGNORECASE,
    )
    if not m:
        m = re.search(
            r"AS\s*ON\s*(\d{1,2})\s*(?:st|nd|rd|th)?\s*[-\s]*([A-Za-z]{3,9})\s*[-\s]*(\d{4})",
            full_text,
            re.IGNORECASE,
        )
    if not m:
        return None
    d, mon, y = int(m.group(1)), m.group(2).lower()[:3], int(m.group(3))
    month = _MONTHS.get(mon)
    if month is None:
        return None
    try:
        return date(y, month, d)
    except ValueError:
        return None


def _project_title(full_text: str) -> str | None:
    m = re.search(r"^([A-Za-z][A-Za-z0-9\s\-']{2,60})$", full_text[:200], re.MULTILINE)
    if m:
        line = m.group(1).strip()
        if len(line) > 3 and "STATUS" not in line.upper():
            return line
    return None


def _is_tower_table_page(text: str) -> bool:
    u = text.upper()
    if "TOTAL AREA" in u and "SQ.FT" in u.replace(".", ""):
        return False
    # Slab / area summary page uses "Activity" + "Total Area", not per-floor tower table
    if "ACTIVITY" in u and "TOTAL AREA" in u:
        return False
    if "ACTIVITY" not in u:
        return False
    if "FLOOR" not in u:
        return False
    if "STRUCTURE" not in u:
        return False
    if "TOTAL" in u and "PERCENTAGE" in u and "SLAB" in u:
        return False
    if "FINISHING" in u or "SERVICES" in u:
        return True
    # Minimal tower page: header + Structure block only (still same report format)
    return "COMPLETE*" in u or "COMPLETED STATUS" in u


def _section_from_line(line: str) -> str | None:
    s = line.strip()
    if s in ("Structure", "Finishing", "Services"):
        return s
    return None


_RE_LAST_PCT = re.compile(r"(\d{1,3})%")
# Trailing floor count before %, optional "( Piece)" / "( Up to ...)" noise after the number
_RE_FLOOR_BEFORE_PCT = re.compile(
    r"(.+?)\s+(\d+)\s*(?:\([^)]*\))?\s*$",
    re.DOTALL,
)


def _clean_activity_leading(activity: str) -> str:
    """Strip leading structure %, WIP/Completed, and numbered list prefixes."""
    s = re.sub(r"\s+", " ", activity.strip())
    while True:
        m = re.match(r"^(?:\d{1,3}%\s*)+", s)
        if m:
            s = s[m.end() :].lstrip()
            continue
        m = re.match(r"^(?:WIP|Completed|Complete)\s+", s, re.IGNORECASE)
        if m:
            s = s[m.end() :].lstrip()
            continue
        m = re.match(r"^\d+\)\s*", s)
        if m:
            s = s[m.end() :].lstrip()
            continue
        break
    return s.strip()


def _infer_row_status(original: str) -> str | None:
    o = original.lower()
    if re.search(r"\bwip\b", o):
        return "WIP"
    if "completed" in o or re.search(r"\bcomplete\b", o):
        return "Completed"
    return None


def _is_tower_table_header_text(s: str) -> bool:
    """True for repeated PDF column headers (may be split across lines and merged)."""
    m = re.sub(r"\s+", " ", s.strip()).upper()
    return "ACTIVITY" in m and "FLOOR" in m


def _is_orphan_percent_only(s: str) -> bool:
    """A lone '55%%' or '98%%' column fragment with no activity text."""
    return bool(re.fullmatch(r"\d{1,3}%", s.strip()))


def _parse_table_row(line: str, warnings: list[str]) -> ParsedProgressRow | None:
    """Parse one row; anchor on the rightmost completion percentage."""
    raw = re.sub(r"\s+", " ", line.strip())
    if not raw or raw.startswith("--"):
        return None
    if _section_from_line(raw):
        return None
    if raw.upper() in ("ACTIVITY", "REMARK") or (
        "COMPLETE*" in raw.upper() and "FLOOR" in raw.upper()
    ):
        return None
    if re.match(r"^Activity\s+Floors", raw, re.I):
        return None
    if _is_tower_table_header_text(raw):
        return None
    if _is_orphan_percent_only(raw):
        return None

    pct_iter = list(_RE_LAST_PCT.finditer(raw))
    if not pct_iter:
        return None
    last_pct_m = pct_iter[-1]
    pct = int(last_pct_m.group(1))
    prefix = raw[: last_pct_m.start()].rstrip()

    floors: int | None = None
    activity_left = prefix
    m_floor = _RE_FLOOR_BEFORE_PCT.match(prefix)
    if m_floor:
        candidate = m_floor.group(1).strip()
        fl = int(m_floor.group(2))
        # Duplicate completion columns like "30% 30%" or "98% 98%" — trailing number is not floors
        if len(pct_iter) >= 2 and fl == pct:
            floors = None
            activity_left = re.sub(r"\s+\d+\s*$", "", prefix).rstrip()
        else:
            floors = fl
            activity_left = candidate

    activity = _clean_activity_leading(activity_left)
    if not activity:
        warnings.append(f"unparsed row (empty activity after clean): {raw[:120]}")
        return None

    st = _infer_row_status(raw)
    return ParsedProgressRow(
        section="Other",
        activity_raw=activity,
        floors_complete=floors,
        pct_complete=pct,
        status=st,
        remark=None,
    )


def _skip_tower_header_line(ln: str) -> bool:
    u = ln.upper()
    if "ACTIVITY" in u and "FLOOR" in u:
        return True
    if re.match(r"^Complete\*", ln, re.I):
        return True
    if ln in ("%", "Completed Status Remark"):
        return True
    # Header fragments when PDF splits columns across lines
    if re.match(r"^%?\s*(Complete\*?|Completed)\s*(Status|Remark)?\s*$", ln, re.I):
        return True
    return bool(re.match(r"^Complete\*?\s*%?\s*$", ln, re.I))


def _should_warn_tower_parse_failed(merged: str) -> bool:
    """Only warn when merge looks like a real data row, not headers or orphan %%."""
    if _is_tower_table_header_text(merged):
        return False
    if _is_orphan_percent_only(merged):
        return False
    return len(merged.strip()) >= 6


def _with_section(pr: ParsedProgressRow, current_section: str) -> ParsedProgressRow:
    in_sec = current_section in ("Structure", "Finishing", "Services")
    sec = current_section if in_sec else pr.section
    return ParsedProgressRow(
        section=sec,
        activity_raw=pr.activity_raw,
        floors_complete=pr.floors_complete,
        pct_complete=pr.pct_complete,
        status=pr.status,
        remark=pr.remark,
    )


def _parse_tower_page_body(text: str, warnings: list[str]) -> list[ParsedProgressRow]:
    lines = [re.sub(r"\s+", " ", ln.strip()) for ln in text.splitlines() if ln.strip()]
    rows: list[ParsedProgressRow] = []
    current_section = "Other"
    buf: list[str] = []

    def flush_buf() -> None:
        nonlocal buf
        if not buf:
            return
        merged = " ".join(buf).strip()
        buf = []
        pr = _parse_table_row(merged, warnings)
        if pr:
            rows.append(_with_section(pr, current_section))

    for ln in lines:
        sec = _section_from_line(ln)
        if sec:
            flush_buf()
            current_section = sec
            continue
        if _skip_tower_header_line(ln):
            continue
        # Lone "55%%" / "98%%" — wait for a preceding line in buf, or drop (PDF column junk)
        if "%" in ln and _is_orphan_percent_only(ln) and not buf:
            continue
        # Merge multi-line activity until we see a completion percentage
        if "%" in ln:
            merged = " ".join(buf + [ln]).strip() if buf else ln
            buf = []
            if _is_tower_table_header_text(merged):
                continue
            pr = _parse_table_row(merged, warnings)
            if pr:
                rows.append(_with_section(pr, current_section))
            elif _should_warn_tower_parse_failed(merged):
                warnings.append(f"tower row not parsed: {merged[:140]}")
        else:
            # Continuation of activity name (wrapped) or noise — keep for next line with %
            if len(ln) > 1 and not ln.upper().startswith("PAGE"):
                buf.append(ln)

    flush_buf()
    return rows


def _classify_non_tower_zone(text: str, page_index: int) -> tuple[str, str]:
    u = text.strip()
    low = u.lower()
    if "landscape" in low[:800]:
        return "section:landscape", "landscape"
    if "club house" in low or "clubhouse" in low:
        return "section:club_house", "club_house"
    if "dg room" in low or "d.g" in low:
        return "section:dg_room", "dg_room"
    if "slab" in low and "sq.ft" in low.replace(".", ""):
        return "section:slab_summary", "slab_summary"
    return f"section:page_{page_index + 1}", "other"


def parse_construction_pdf_bytes(
    pdf_bytes: bytes,
    *,
    max_pages: int = 80,
) -> ParsedConstructionReport:
    """Extract structured progress from a builder PDF."""
    warnings: list[str] = []
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        n = min(doc.page_count, max_pages)
        full_head = ""
        for i in range(min(3, n)):
            full_head += doc.load_page(i).get_text("text") or ""
        as_of = _parse_as_of_date(full_head)
        title = _project_title(full_head)

        zones: list[ParsedZone] = []
        tabular_idx = 0

        for page_index in range(n):
            page = doc.load_page(page_index)
            text = page.get_text("text") or ""

            if _is_tower_table_page(text):
                tabular_idx += 1
                tnum = tower_number_from_tabular_index(tabular_idx)
                zk = tower_zone_key(tnum)
                rows = _parse_tower_page_body(text, warnings)
                if not rows:
                    warnings.append(f"tower page {page_index + 1}: no rows parsed")
                zones.append(
                    ParsedZone(
                        zone_key=zk,
                        zone_type="tower",
                        tower_number=tnum,
                        tabular_index=tabular_idx,
                        page_index=page_index,
                        rows=rows,
                    ),
                )
            else:
                zk, zt = _classify_non_tower_zone(text, page_index)
                preview = text.strip()[:2000] or None
                zones.append(
                    ParsedZone(
                        zone_key=zk,
                        zone_type="common",
                        tower_number=None,
                        tabular_index=None,
                        page_index=page_index,
                        rows=[
                            ParsedProgressRow(
                                section="Other",
                                activity_raw=zt.replace("_", " ").title(),
                                floors_complete=None,
                                pct_complete=None,
                                status=None,
                                remark=preview,
                            ),
                        ],
                        raw_preview=preview,
                    ),
                )
    finally:
        doc.close()

    if as_of is None:
        warnings.append(
            "Could not parse STATUS AS ON date from PDF header; use upload date or filename.",
        )

    return ParsedConstructionReport(
        project_title=title,
        as_of_date=as_of,
        zones=zones,
        warnings=warnings,
    )


def parse_construction_report_from_text_per_page(
    pages: list[str],
    *,
    warnings: list[str] | None = None,
) -> ParsedConstructionReport:
    """Test helper: same logic as PDF but with pre-split page texts."""
    w = warnings if warnings is not None else []
    full_head = "".join(pages[:3])
    as_of = _parse_as_of_date(full_head)
    title = _project_title(full_head)
    zones: list[ParsedZone] = []
    tabular_idx = 0
    for page_index, text in enumerate(pages):
        if _is_tower_table_page(text):
            tabular_idx += 1
            tnum = tower_number_from_tabular_index(tabular_idx)
            zk = tower_zone_key(tnum)
            rows = _parse_tower_page_body(text, w)
            zones.append(
                ParsedZone(
                    zone_key=zk,
                    zone_type="tower",
                    tower_number=tnum,
                    tabular_index=tabular_idx,
                    page_index=page_index,
                    rows=rows,
                ),
            )
        else:
            zk, zt = _classify_non_tower_zone(text, page_index)
            preview = text.strip()[:2000] or None
            zones.append(
                ParsedZone(
                    zone_key=zk,
                    zone_type="common",
                    tower_number=None,
                    tabular_index=None,
                    page_index=page_index,
                    rows=[
                        ParsedProgressRow(
                            section="Other",
                            activity_raw=zt.replace("_", " ").title(),
                            floors_complete=None,
                            pct_complete=None,
                            status=None,
                            remark=preview,
                        ),
                    ],
                    raw_preview=preview,
                ),
            )
    if as_of is None:
        w.append("Could not parse STATUS AS ON date from PDF header.")
    return ParsedConstructionReport(
        project_title=title,
        as_of_date=as_of,
        zones=zones,
        warnings=w,
    )
