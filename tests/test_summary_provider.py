"""Summary provider tests (checklist F and H).

These tests use a mocked Bedrock client. They never contact AWS, so they prove
the fallback behaviour without claiming a real invocation happened.
"""

from __future__ import annotations

from typing import Any

from homeops_api.summary import (
    PROVIDER_BEDROCK,
    PROVIDER_DETERMINISTIC,
    BedrockSummaryProvider,
    DeterministicSummaryProvider,
)

BRIEF = {
    "title": "Technician brief - Washing Machine",
    "summary": "HomeOps brief for Washing Machine.",
    "facts": [
        {"label": "Asset", "value": "Washing Machine", "is_unknown": False},
        {"label": "Warranty end date (as saved)", "value": "2026-11-14", "is_unknown": False},
    ],
    "unknowns": ["Warranty terms and exclusions"],
    "record_ids": ["asset_washer_01"],
}


def test_deterministic_provider_needs_no_credentials() -> None:
    text, provider = DeterministicSummaryProvider().summarize(BRIEF)
    assert provider == PROVIDER_DETERMINISTIC
    assert "HomeOps" in text


class _FakeBedrockClient:
    def __init__(self, response: dict[str, Any] | None = None, error: Exception | None = None) -> None:
        self._response = response
        self._error = error
        self.calls: list[dict[str, Any]] = []

    def converse(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return self._response or {}


def test_bedrock_provider_uses_the_model_response_when_it_succeeds() -> None:
    client = _FakeBedrockClient(
        response={"output": {"message": {"content": [{"text": "Bullet one\nBullet two"}]}}}
    )
    provider = BedrockSummaryProvider(model_id="test-model", region="eu-west-2", client=client)
    text, name = provider.summarize(BRIEF)
    assert name == PROVIDER_BEDROCK
    assert text == "Bullet one\nBullet two"
    assert client.calls[0]["modelId"] == "test-model"


def test_bedrock_request_only_contains_the_brief_records() -> None:
    client = _FakeBedrockClient(
        response={"output": {"message": {"content": [{"text": "ok"}]}}}
    )
    provider = BedrockSummaryProvider(model_id="test-model", region="eu-west-2", client=client)
    provider.summarize(BRIEF)
    sent = client.calls[0]["messages"][0]["content"][0]["text"]
    assert "Washing Machine" in sent
    assert "asset_washer_01" in sent
    assert "Do not invent dates" in sent


def test_bedrock_falls_back_on_a_permission_error() -> None:
    client = _FakeBedrockClient(error=RuntimeError("AccessDeniedException"))
    provider = BedrockSummaryProvider(model_id="test-model", region="eu-west-2", client=client)
    text, name = provider.summarize(BRIEF)
    assert name == PROVIDER_DETERMINISTIC
    assert "HomeOps" in text
    assert provider.last_error is not None


def test_bedrock_falls_back_on_a_timeout() -> None:
    client = _FakeBedrockClient(error=TimeoutError("read timeout"))
    provider = BedrockSummaryProvider(model_id="test-model", region="eu-west-2", client=client)
    text, name = provider.summarize(BRIEF)
    assert name == PROVIDER_DETERMINISTIC
    assert text


def test_bedrock_falls_back_on_an_empty_response() -> None:
    client = _FakeBedrockClient(response={"output": {"message": {"content": []}}})
    provider = BedrockSummaryProvider(model_id="test-model", region="eu-west-2", client=client)
    text, name = provider.summarize(BRIEF)
    assert name == PROVIDER_DETERMINISTIC
    assert text


def test_no_bedrock_configuration_means_the_deterministic_provider() -> None:
    """Without explicit configuration the app must never try to reach AWS."""
    from homeops_api.summary import build_summary_provider
    from homeops_core.config import build_settings

    settings = build_settings({})
    provider = build_summary_provider(settings)
    assert provider.name == PROVIDER_DETERMINISTIC
    assert settings.bedrock_configured is False
