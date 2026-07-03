"""Merchant rules CRUD API, retroactive apply, and uncategorized queue."""

from __future__ import annotations

from io import BytesIO

from starlette.testclient import TestClient


def _import_csv(api_client: TestClient, rows: list[tuple[str, str, str]]) -> None:
    """rows: (date, amount, merchant) with category left as Other."""
    lines = ["date,amount,category,merchant"]
    for d, amt, merchant in rows:
        lines.append(f"{d},{amt},Other,{merchant}")
    csv_content = "\n".join(lines) + "\n"
    r = api_client.post(
        "/api/transactions/import",
        files={"file": ("txns.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")},
    )
    assert r.status_code == 200


def test_create_list_update_delete_rule(api_client: TestClient) -> None:
    r = api_client.post(
        "/api/merchant-rules/",
        json={
            "match_type": "exact",
            "match_value": "acme corp",
            "canonical_merchant": "Acme Corp",
            "merchant_type": "Retailer",
            "category": "Online Shopping",
            "source": "user",
        },
    )
    assert r.status_code == 201
    body = r.json()
    rid = body["id"]
    assert body["match_value"] == "acme corp"
    assert body["canonical_merchant"] == "Acme Corp"
    assert body["retroactively_applied"] == 0

    listed = api_client.get("/api/merchant-rules/")
    assert listed.status_code == 200
    assert any(x["id"] == rid for x in listed.json())

    upd = api_client.put(
        f"/api/merchant-rules/{rid}",
        json={
            "match_type": "exact",
            "match_value": "acme corp",
            "canonical_merchant": "Acme Corporation",
            "merchant_type": "Retailer",
            "category": "Online Shopping",
        },
    )
    assert upd.status_code == 200
    assert upd.json()["canonical_merchant"] == "Acme Corporation"

    delete = api_client.delete(f"/api/merchant-rules/{rid}")
    assert delete.status_code == 204

    listed2 = api_client.get("/api/merchant-rules/")
    assert all(x["id"] != rid for x in listed2.json())


def test_duplicate_match_value_conflicts(api_client: TestClient) -> None:
    body = {
        "match_type": "exact",
        "match_value": "duplicate merchant",
        "canonical_merchant": "Dup",
        "merchant_type": None,
        "category": "Other",
    }
    r1 = api_client.post("/api/merchant-rules/", json=body)
    assert r1.status_code == 201

    r2 = api_client.post("/api/merchant-rules/", json=body)
    assert r2.status_code == 409


def test_create_rule_retroactively_applies_to_existing_transactions(
    api_client: TestClient,
) -> None:
    _import_csv(
        api_client,
        [
            ("2025-06-01", "100", "Widgetsmith"),
            ("2025-06-02", "200", "Widgetsmith"),
            ("2025-06-03", "300", "OtherPlace"),
        ],
    )

    r = api_client.post(
        "/api/merchant-rules/",
        json={
            "match_type": "exact",
            "match_value": "Widgetsmith",
            "canonical_merchant": "Widgetsmith Co",
            "merchant_type": None,
            "category": "Online Shopping",
        },
    )
    assert r.status_code == 201
    assert r.json()["retroactively_applied"] == 2

    txns = api_client.get("/api/transactions/?limit=50").json()
    widget_rows = [t for t in txns if t.get("merchant") == "Widgetsmith Co"]
    assert len(widget_rows) == 2
    assert all(t["category"] == "Online Shopping" for t in widget_rows)


def test_uncategorized_queue_groups_by_merchant_frequency(api_client: TestClient) -> None:
    _import_csv(
        api_client,
        [
            ("2025-07-01", "50", "FrequentFlyer"),
            ("2025-07-02", "60", "FrequentFlyer"),
            ("2025-07-03", "70", "FrequentFlyer"),
            ("2025-07-04", "10", "RareBird"),
        ],
    )

    r = api_client.get("/api/merchant-rules/uncategorized")
    assert r.status_code == 200
    groups = {g["merchant"]: g for g in r.json()}
    assert "FrequentFlyer" in groups
    assert groups["FrequentFlyer"]["frequency"] == 3
    assert groups["FrequentFlyer"]["total_paise"] == 18_000
    # Frequency-descending order.
    merchants_in_order = [g["merchant"] for g in r.json()]
    assert merchants_in_order.index("FrequentFlyer") < merchants_in_order.index("RareBird")
