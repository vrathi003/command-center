"""Settings API coverage for persisted project configuration."""

from __future__ import annotations

from starlette.testclient import TestClient


def test_settings_get_includes_discord_disabled_by_default(api_client: TestClient) -> None:
    response = api_client.get("/api/settings/")

    assert response.status_code == 200
    assert response.json()["project_config"]["discord_enabled"] is False


def test_settings_project_config_patch_roundtrips(api_client: TestClient) -> None:
    payload = {
        "project_config": {
            "discord_enabled": True,
            "discord_alerts_enabled": True,
            "alerts_in_app_enabled": False,
            "ledger_engine": "legacy",
            "intake_auto_post_min_confidence": 0.9,
            "intake_duplicate_date_window_days": 3,
        }
    }

    response = api_client.put("/api/settings/", json=payload)

    assert response.status_code == 200
    assert response.json()["project_config"] == payload["project_config"]

    response = api_client.get("/api/settings/")

    assert response.status_code == 200
    assert response.json()["project_config"] == payload["project_config"]


def test_settings_project_config_null_fields_do_not_crash(api_client: TestClient) -> None:
    response = api_client.put(
        "/api/settings/",
        json={"project_config": {"ledger_engine": None}},
    )

    assert response.status_code == 200
    assert response.json()["project_config"]["ledger_engine"] == "double_entry"
