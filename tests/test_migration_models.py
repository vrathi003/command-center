from dataclasses import asdict

from finance_common.migration.models import MigrationReport


def test_migration_report_exposes_required_fields() -> None:
    report = MigrationReport(
        migrated=4,
        quarantined=2,
        skipped_deleted=1,
        noop=3,
        backup_path="/tmp/pre-ledger.db",
        cutover_at="2026-08-10T12:00:00+00:00",
    )

    assert asdict(report) == {
        "migrated": 4,
        "quarantined": 2,
        "skipped_deleted": 1,
        "noop": 3,
        "backup_path": "/tmp/pre-ledger.db",
        "cutover_at": "2026-08-10T12:00:00+00:00",
    }
