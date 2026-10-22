"""Summary providers.

The technician brief is assembled from stored records by the MCP server. This
module only decides how that brief is *worded*:

* :class:`DeterministicSummaryProvider` is the default. It needs no
  credentials and always produces the same text.
* :class:`BedrockSummaryProvider` calls Amazon Bedrock Runtime when it is
  explicitly enabled and configured. Any error - missing credentials, denied
  permission, unknown model, timeout - falls back to the deterministic text and
  is reported as such. It is never treated as a source of truth.
"""

from __future__ import annotations

from typing import Any, Protocol

PROVIDER_DETERMINISTIC = "deterministic"
PROVIDER_BEDROCK = "bedrock"

BEDROCK_MAX_TOKENS = 600


class SummaryProvider(Protocol):
    """Turns a brief payload into prose plus the provider that produced it."""

    name: str

    def summarize(self, payload: dict[str, Any]) -> tuple[str, str]:
        """Return ``(text, provider_name)``."""


class DeterministicSummaryProvider:
    """Template based summary. No model, no credentials, always available."""

    name = PROVIDER_DETERMINISTIC

    def summarize(self, payload: dict[str, Any]) -> tuple[str, str]:
        summary = payload.get("summary")
        if isinstance(summary, str) and summary.strip():
            return summary.strip(), self.name
        return self._fallback(payload), self.name

    def _fallback(self, payload: dict[str, Any]) -> str:
        facts = payload.get("facts") or []
        lines = [f"- {fact.get('label')}: {fact.get('value')}" for fact in facts if isinstance(fact, dict)]
        return "\n".join(lines) or "HomeOps could not assemble a summary for this request."


class BedrockSummaryProvider:
    """Optional Amazon Bedrock Runtime summariser.

    Only the records that make up the brief are sent. The response is treated
    as untrusted text: it may reorganise or rephrase the supplied facts, but it
    may not add facts. If the call fails for any reason the deterministic text
    is used instead and the provider reports the fallback.
    """

    name = PROVIDER_BEDROCK

    def __init__(
        self,
        model_id: str,
        region: str | None = None,
        client: Any | None = None,
        timeout: int = 20,
    ) -> None:
        self.model_id = model_id
        self.region = region
        self.timeout = timeout
        self._client = client
        self.last_error: str | None = None

    # -- plumbing ----------------------------------------------------------

    def _get_client(self) -> Any:
        if self._client is None:
            import boto3  # imported lazily so the dependency stays optional

            self._client = boto3.client(
                "bedrock-runtime",
                region_name=self.region,
                config=_botocore_config(),
            )
        return self._client

    # -- public API --------------------------------------------------------

    def summarize(self, payload: dict[str, Any]) -> tuple[str, str]:
        fallback = DeterministicSummaryProvider().summarize(payload)[0]
        try:
            client = self._get_client()
            body = self._build_request(payload)
            response = client.converse(
                modelId=self.model_id,
                messages=[{"role": "user", "content": [{"text": body}]}],
                inferenceConfig={"maxTokens": BEDROCK_MAX_TOKENS, "temperature": 0.2},
            )
            text = self._extract_text(response)
            if not text:
                raise RuntimeError("Bedrock returned an empty response")
            self.last_error = None
            return text, self.name
        except Exception as exc:  # noqa: BLE001 - any failure must fall back
            self.last_error = f"{type(exc).__name__}: {exc}"
            return fallback, PROVIDER_DETERMINISTIC

    def _build_request(self, payload: dict[str, Any]) -> str:
        import json

        facts = payload.get("facts") or []
        unknown = payload.get("unknowns") or []
        record_ids = payload.get("record_ids") or []
        prompt = (
            "You are helping a homeowner summarise maintenance records for a technician.\n"
            "Use ONLY the facts listed below. Do not invent dates, prices, causes or warranties.\n"
            "If a detail is unknown, say it is unknown.\n"
            "Write three to five short bullet points.\n\n"
            f"FACTS:\n{json.dumps(facts, indent=2, default=str)}\n\n"
            f"UNKNOWN DETAILS:\n{json.dumps(unknown, default=str)}\n\n"
            f"RECORD IDS: {', '.join(str(i) for i in record_ids)}\n"
        )
        return prompt

    def _extract_text(self, response: dict[str, Any]) -> str | None:
        output = (response or {}).get("output", {})
        message = output.get("message") or {}
        blocks = message.get("content") or []
        parts: list[str] = []
        for block in blocks:
            text = block.get("text")
            if isinstance(text, str) and text.strip():
                parts.append(text.strip())
        if not parts:
            return None
        return "\n".join(parts)


def _botocore_config() -> Any:
    from botocore.config import Config

    return Config(connect_timeout=10, read_timeout=30, retries={"max_attempts": 1})


def build_summary_provider(settings: Any) -> SummaryProvider:
    """Pick the summary provider from configuration."""
    provider = getattr(settings, "summary_provider", PROVIDER_DETERMINISTIC)
    if provider == PROVIDER_BEDROCK and getattr(settings, "bedrock_configured", False):
        return BedrockSummaryProvider(
            model_id=settings.bedrock_model_id or "",
            region=getattr(settings, "aws_region", None),
        )
    return DeterministicSummaryProvider()
