"""Models for migrating legacy transactions to the ledger."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MigrationReport:
    migrated: int
    quarantined: int
    skipped_deleted: int
    noop: int
    backup_path: str | None
    cutover_at: str | None
