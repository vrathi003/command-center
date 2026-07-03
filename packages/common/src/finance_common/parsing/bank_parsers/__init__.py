"""Per-bank credit-card statement text parsers — canonical source for statement import.

Originally ported from CardQL (`CardQL/src/cardql/parsers/banks/`). The CardQL directory
can be removed from the repo once statement import is verified; maintain parsers here only.

Each `<bank>_v<n>.py` module exposes `parse(text: str) -> list[dict[str, str]]`, returning
canonical import-row dicts (`date`, `amount`, `category`, `merchant`, `transaction_type`,
optionally `notes`) — the same shape `finance_common.parsing.transaction_import.parse_import_row`
already consumes, so bank-specific extraction plugs directly into the existing merchant-rules
classification and transaction-insert pipeline. See `registry.py` for bank selection.
"""
