"""Mocked-LLM tests for merchant classification suggestion parsing."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from finance_common.classification.llm_classifier import suggest_classifications


def _mock_client(content: str) -> Any:
    message = SimpleNamespace(content=content)
    choice = SimpleNamespace(message=message)
    response = SimpleNamespace(choices=[choice])
    return SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=AsyncMock(return_value=response))
        )
    )


@pytest.mark.asyncio
async def test_suggest_classifications_parses_valid_json() -> None:
    content = (
        '{"suggestions": [{"raw_merchant": "swiggy", "canonical_merchant": "Swiggy", '
        '"merchant_type": "Food Delivery Platform", "category": "Food Delivery", '
        '"confidence": 0.95}]}'
    )
    result = await suggest_classifications(_mock_client(content), "test-model", ["swiggy"], [])
    assert len(result) == 1
    assert result[0].raw_merchant == "swiggy"
    assert result[0].canonical_merchant == "Swiggy"
    assert result[0].category == "Food Delivery"
    assert result[0].confidence == pytest.approx(0.95)


@pytest.mark.asyncio
async def test_suggest_classifications_handles_markdown_fence() -> None:
    content = (
        "```json\n"
        '{"suggestions": [{"raw_merchant": "zomato", "canonical_merchant": "Zomato", '
        '"merchant_type": null, "category": "Food Delivery", "confidence": 0.8}]}\n'
        "```"
    )
    result = await suggest_classifications(_mock_client(content), "test-model", ["zomato"], [])
    assert len(result) == 1
    assert result[0].raw_merchant == "zomato"
    assert result[0].merchant_type is None


@pytest.mark.asyncio
async def test_suggest_classifications_rejects_hallucinated_merchant() -> None:
    """Model returns a merchant not in the requested batch — must be dropped."""
    content = (
        '{"suggestions": [{"raw_merchant": "not_requested", "canonical_merchant": "X", '
        '"merchant_type": null, "category": "Other", "confidence": 0.5}]}'
    )
    result = await suggest_classifications(_mock_client(content), "test-model", ["swiggy"], [])
    assert result == []


@pytest.mark.asyncio
async def test_suggest_classifications_rejects_invalid_category() -> None:
    """A category that doesn't map to a real Category (and isn't literally 'Other') is dropped."""
    content = (
        '{"suggestions": [{"raw_merchant": "swiggy", "canonical_merchant": "Swiggy", '
        '"merchant_type": null, "category": "Not A Real Category", "confidence": 0.9}]}'
    )
    result = await suggest_classifications(_mock_client(content), "test-model", ["swiggy"], [])
    assert result == []


@pytest.mark.asyncio
async def test_suggest_classifications_empty_batch_returns_empty_without_request() -> None:
    client = _mock_client("")
    result = await suggest_classifications(client, "test-model", [], [])
    assert result == []
    client.chat.completions.create.assert_not_called()


@pytest.mark.asyncio
async def test_suggest_classifications_request_failure_raises_value_error() -> None:
    async def _boom(**_kwargs: object) -> None:
        raise RuntimeError("connection refused")

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=_boom)))
    with pytest.raises(ValueError, match="Local LLM request failed"):
        await suggest_classifications(client, "test-model", ["swiggy"], [])


@pytest.mark.asyncio
async def test_suggest_classifications_unparseable_output_returns_empty() -> None:
    result = await suggest_classifications(
        _mock_client("I am a thinking model with no JSON here."), "test-model", ["swiggy"], []
    )
    assert result == []
