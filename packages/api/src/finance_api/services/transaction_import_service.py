"""Load CSV/XLSX and insert transactions (pandas for tabular reads)."""

from __future__ import annotations

import inspect
import io
import sqlite3
import zipfile
from datetime import date, datetime
from typing import Any

import pandas as pd
from xlrd import XLRDError

from finance_common.parsing.transaction_import import (
    canonical_row_for_import,
    detect_header_row,
    parse_import_row,
    trim_trailer_rows,
)
from finance_common.repositories import transactions as tx_repo
from finance_common.types import Paise

MAX_BYTES = 10 * 1024 * 1024
MAX_ROWS = 5000
SOURCE_IMPORT = "import"

# OOXML .xlsx is a Zip file (starts with PK). Legacy Excel .xls is OLE (starts with D0 CF 11 E0).
# Many users have .xls workbooks saved or renamed as .xlsx — detect OLE and use xlrd.
_OLE2_MAGIC_4 = b"\xd0\xcf\x11\xe0"

_MSG_EXCEL_PASSWORD_REQUIRED = (
    "This Excel file is password-protected. Enter the password in the import password "
    "field (same as for encrypted PDFs), then upload again."
)
_MSG_EXCEL_WRONG_PASSWORD = (
    "The password does not match this Excel file. Check for extra spaces, caps lock, "
    "and that you are using the password for opening the file (not only sheet/workbook "
    "protection without file encryption)."
)
_MSG_EXCEL_UNSUPPORTED_ENCRYPTION = (
    "This Excel file uses encryption that cannot be decrypted on the server (common with "
    "Office 365 “extensible” encryption or some legacy formats). "
    "Open the file in Excel on your computer, then File → Info → Protect Workbook → "
    "Encrypt with Password → clear the password and save, or use Save As → CSV UTF-8 "
    "(comma delimited) / an unencrypted copy, then import that file."
)


def _msoffcrypto_load_key(office: object, password: str) -> None:
    """Call load_key with verify_password=True when the format supports it (clearer errors)."""
    load_key = office.load_key
    params = inspect.signature(load_key).parameters
    kw: dict[str, str | bool] = {"password": password}
    if "verify_password" in params:
        kw["verify_password"] = True
    load_key(**kw)


def _decrypt_office_workbook_bytes(content: bytes, password: str | None) -> bytes:
    """Decrypt whole-file password protection (OOXML / some legacy Excel)."""
    import msoffcrypto
    from msoffcrypto import exceptions as mexc

    try:
        office = msoffcrypto.OfficeFile(io.BytesIO(content))
    except mexc.FileFormatError:
        return content
    except mexc.DecryptionError as e:
        raise ValueError(_MSG_EXCEL_UNSUPPORTED_ENCRYPTION) from e
    except Exception:
        return content
    if not office.is_encrypted():
        return content
    pw = password.strip() if password else ""
    if not pw:
        raise ValueError(_MSG_EXCEL_PASSWORD_REQUIRED)
    out = io.BytesIO()
    try:
        _msoffcrypto_load_key(office, pw)
        office.decrypt(out)
    except mexc.InvalidKeyError as e:
        raise ValueError(_MSG_EXCEL_WRONG_PASSWORD) from e
    except mexc.DecryptionError as e:
        detail = str(e).strip()
        if "Extensible" in detail or "Unsupported EncryptionInfo" in detail:
            raise ValueError(_MSG_EXCEL_UNSUPPORTED_ENCRYPTION) from e
        raise ValueError(
            f"{_MSG_EXCEL_UNSUPPORTED_ENCRYPTION} (Technical detail: {detail})",
        ) from e
    except Exception as e:
        raise ValueError(
            "Could not unlock this Excel file. If the password is correct, the file may use "
            "encryption that is not supported here — remove encryption or export CSV in Excel, "
            "then try again.",
        ) from e
    return out.getvalue()


def _pandas_cell_str(val: Any) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    if isinstance(val, pd.Timestamp):
        return val.date().isoformat()
    if isinstance(val, datetime):
        return val.date().isoformat()
    if isinstance(val, date):
        return val.isoformat()
    if isinstance(val, float) and val == int(val):
        return str(int(val))
    return str(val).strip()


def _dataframe_to_row_dicts(df: pd.DataFrame) -> list[dict[str, str]]:
    """Convert DataFrame rows to list of dicts with string values (columns already set)."""
    df = df.iloc[:MAX_ROWS].copy()
    df.columns = [
        str(c).strip() if c is not None and not (isinstance(c, float) and pd.isna(c)) else ""
        for c in df.columns
    ]
    out: list[dict[str, str]] = []
    for _, row in df.iterrows():
        d: dict[str, str] = {}
        for k in df.columns:
            if not k:
                continue
            d[k] = _pandas_cell_str(row[k])
        if any(v.strip() for v in d.values()):
            out.append(d)
    return out


def _detect_and_slice(df: pd.DataFrame) -> pd.DataFrame:
    """Auto-detect the header row in a headerless DataFrame, promote it, and drop preamble."""
    scan_rows: list[list[str]] = [
        [_pandas_cell_str(v) for v in df.iloc[i]]
        for i in range(min(20, len(df)))
    ]
    header_idx = detect_header_row(scan_rows)
    if header_idx is None:
        header_idx = 0
    # Promote detected row to column headers and drop preamble.
    df.columns = [
        str(c).strip() if c is not None and not (isinstance(c, float) and pd.isna(c)) else ""
        for c in df.iloc[header_idx]
    ]
    return df.iloc[header_idx + 1 :].reset_index(drop=True)


def _rows_from_csv_pandas(content: bytes) -> list[dict[str, str]]:
    df = pd.read_csv(io.BytesIO(content), encoding="utf-8-sig", header=None)
    df = _detect_and_slice(df)
    rows = _dataframe_to_row_dicts(df)
    return trim_trailer_rows(rows)


def _rows_from_excel_pandas(content: bytes, *, engine: str) -> list[dict[str, str]]:
    try:
        df = pd.read_excel(
            io.BytesIO(content),
            sheet_name=0,
            header=None,
            engine=engine,
        )
    except (zipfile.BadZipFile, ValueError, OSError) as e:
        if engine == "openpyxl":
            msg = (
                "Could not open as Excel (.xlsx). File may be corrupt, truncated, or not a real "
                "workbook. Re-download or Save As → Excel Workbook (.xlsx). "
                "If this is CSV, use a .csv file."
            )
            raise ValueError(msg) from e
        raise
    except XLRDError as e:
        msg = (
            "Could not read as Excel (.xls). The file may be corrupt, use unsupported encryption, "
            "or not be an Excel workbook (e.g. Word .doc). Try Save As .xlsx in Excel, "
            "remove workbook protection, or export CSV."
        )
        raise ValueError(msg) from e
    df = _detect_and_slice(df)
    rows = _dataframe_to_row_dicts(df)
    return trim_trailer_rows(rows)


def load_rows_from_upload(
    filename: str,
    content: bytes,
    *,
    password: str | None = None,
) -> list[dict[str, str]]:
    name = filename.lower().strip()
    if len(content) > MAX_BYTES:
        msg = f"file too large (max {MAX_BYTES // (1024 * 1024)} MB)"
        raise ValueError(msg)
    if name.endswith(".csv"):
        try:
            return _rows_from_csv_pandas(content)
        except (UnicodeDecodeError, pd.errors.ParserError, ValueError) as e:
            raise ValueError(f"Could not parse CSV: {e}") from e
    if name.endswith((".xlsx", ".xlsm")):
        body = _decrypt_office_workbook_bytes(content, password)
        body = body[3:] if body.startswith(b"\xef\xbb\xbf") else body
        # Misnamed legacy .xls: extension .xlsx but binary is OLE, not Zip.
        if len(body) >= 4 and body[:4] == _OLE2_MAGIC_4:
            try:
                return _rows_from_excel_pandas(body, engine="xlrd")
            except ImportError as e:
                raise ValueError("xlrd missing (needed for legacy Excel binary).") from e
        if len(body) >= 2 and not body.startswith(b"PK"):
            msg = (
                "This file does not look like a modern .xlsx (real .xlsx files are Zip and start "
                "with PK). If it opens in Excel, use File → Save As → Excel Workbook (.xlsx). "
                "If it is actually old .xls format, rename the file to .xls or re-save as .xlsx."
            )
            raise ValueError(msg)
        try:
            return _rows_from_excel_pandas(body, engine="openpyxl")
        except ImportError as e:
            raise ValueError("openpyxl is required for .xlsx — check the API environment.") from e
    if name.endswith(".xls"):
        body = _decrypt_office_workbook_bytes(content, password)
        try:
            return _rows_from_excel_pandas(body, engine="xlrd")
        except ImportError as e:
            raise ValueError("xlrd is required for .xls — check the API environment.") from e
    raise ValueError("unsupported type — use .csv, .xlsx, .xlsm, or .xls")


async def import_transactions_from_rows(
    conn: Any,
    rows: list[dict[str, str]],
    *,
    account_name: str | None = None,
) -> tuple[int, int, list[tuple[int, str]]]:
    """Insert rows; returns (imported_count, failed_count, list of (row_index, error)).

    ``account_name`` — when supplied, overrides the account field for every row that
    does not already have one from the file itself (e.g. when uploading a single bank
    statement you know came from a specific account).
    """
    trimmed_rows = rows[:MAX_ROWS]

    imported = 0
    failed = 0
    errors: list[tuple[int, str]] = []

    for i, raw in enumerate(trimmed_rows, start=2):
        if not any(str(v).strip() for v in raw.values() if v is not None):
            continue  # blank row
        canon = canonical_row_for_import(raw)
        if "date" not in canon or "amount" not in canon:
            failed += 1
            errors.append(
                (
                    i,
                    "could not find date and amount columns (rename headers to include date, amount, "
                    "or debit/credit; category defaults to Other if omitted)",
                ),
            )
            continue
        try:
            parsed = parse_import_row(canon)
        except ValueError as e:
            failed += 1
            errors.append((i, str(e)))
            continue
        effective_account = parsed.account or account_name or None
        try:
            await tx_repo.insert_transaction(
                conn,
                tx_date=parsed.tx_date,
                amount_paise=Paise(parsed.amount_paise),
                category=parsed.category,
                merchant=parsed.merchant,
                payment_mode=parsed.payment_mode,
                account=effective_account,
                notes=parsed.notes,
                transaction_type=parsed.transaction_type,
                source=SOURCE_IMPORT,
                discord_message_id=None,
            )
            imported += 1
        except (sqlite3.Error, ValueError, TypeError, OSError) as e:
            failed += 1
            errors.append((i, str(e)))
    return imported, failed, errors
