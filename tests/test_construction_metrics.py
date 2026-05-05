from finance_common.construction_metrics import effective_completion_pct, floors_pct_of_total


def test_effective_prefers_pct() -> None:
    assert effective_completion_pct(80, 10, total_floors=26) == 80


def test_effective_from_floors_when_pct_missing() -> None:
    # 20/26 ≈ 77%
    assert effective_completion_pct(None, 20, total_floors=26) == 77


def test_effective_caps_at_100() -> None:
    assert effective_completion_pct(None, 30, total_floors=26) == 100


def test_floors_pct() -> None:
    assert floors_pct_of_total(20, total_floors=26) == 77
