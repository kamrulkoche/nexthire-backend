"""Gemini client — the only code in this service that talks to Gemini.

sp-company-backend keeps its AI providers under `shared/infrastructure/ai/`;
this follows it. Modules never build a Gemini request themselves: they hand
this client a prompt and a response schema and get parsed JSON back.

It calls the REST endpoint (`models/{model}:generateContent`) with `httpx`
rather than the SDK, for two reasons: `httpx` is already a dependency, and a
test mocks one transport instead of an SDK's object graph.

The API key travels in the `x-goog-api-key` header, never the URL, so it
cannot end up in an access log. Error messages raised from here never echo the
response body.
"""

import json
from typing import Any, Optional

import httpx

from ...domain.exceptions.external_service_error import ExternalServiceError
from ...utils.config import settings
from ..logging import get_logger

logger = get_logger(__name__)

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

SERVICE_NAME = "gemini"


class GeminiClient:
    """Structured-output calls to Gemini."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        """Configure the client. Defaults come from settings.

        Args:
            api_key: Gemini API key
            model: Model id, e.g. ``gemini-2.5-flash``
            timeout_seconds: Whole-request timeout
            transport: An httpx transport — tests pass a ``MockTransport``
        """
        self.api_key = api_key if api_key is not None else settings.gemini_api_key
        self.model = model or settings.gemini_model
        self.timeout_seconds = timeout_seconds or settings.gemini_timeout_seconds
        self._transport = transport

    @property
    def is_configured(self) -> bool:
        """Whether a key is present. Without one, callers use their fallback."""
        return bool(self.api_key)

    async def generate_json(
        self,
        prompt: str,
        response_schema: dict[str, Any],
        *,
        system_instruction: Optional[str] = None,
        temperature: float = 0.2,
    ) -> Any:
        """Ask Gemini for JSON matching ``response_schema`` and parse it.

        Args:
            prompt: The user turn
            response_schema: An OpenAPI-subset schema Gemini constrains its output to
            system_instruction: Standing instructions, kept apart from the data
            temperature: Sampling temperature; low, because scoring should be stable

        Returns:
            The parsed JSON value

        Raises:
            ExternalServiceError: No key, a transport failure, a non-2xx answer,
                a blocked prompt, or output that is not valid JSON
        """
        if not self.is_configured:
            raise ExternalServiceError(SERVICE_NAME, "GEMINI_API_KEY is not set.")

        body: dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": response_schema,
                "temperature": temperature,
            },
        }
        if system_instruction:
            body["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        url = f"{GEMINI_BASE_URL}/models/{self.model}:generateContent"
        headers = {"x-goog-api-key": str(self.api_key)}

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds, transport=self._transport
            ) as client:
                response = await client.post(url, json=body, headers=headers)
        except httpx.HTTPError as e:
            logger.warning(f"Gemini transport error: {type(e).__name__}")
            raise ExternalServiceError(SERVICE_NAME, "Request failed.") from e

        if response.status_code >= 400:
            # The body can carry the key back in some error shapes; log only
            # the status.
            logger.warning(f"Gemini answered HTTP {response.status_code}")
            raise ExternalServiceError(
                SERVICE_NAME, f"Answered HTTP {response.status_code}."
            )

        return _parse_candidate(response.json())


def _parse_candidate(payload: dict[str, Any]) -> Any:
    """Pull the JSON text out of a generateContent response.

    Args:
        payload: The decoded response body

    Returns:
        The parsed JSON the model produced

    Raises:
        ExternalServiceError: Blocked, empty, or not JSON
    """
    feedback = payload.get("promptFeedback") or {}
    if feedback.get("blockReason"):
        raise ExternalServiceError(
            SERVICE_NAME, f"Prompt blocked ({feedback['blockReason']})."
        )

    candidates = payload.get("candidates") or []
    if not candidates:
        raise ExternalServiceError(SERVICE_NAME, "Returned no candidates.")

    parts = (candidates[0].get("content") or {}).get("parts") or []
    text = "".join(part.get("text", "") for part in parts if isinstance(part, dict))
    if not text.strip():
        raise ExternalServiceError(SERVICE_NAME, "Returned an empty answer.")

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise ExternalServiceError(SERVICE_NAME, "Returned invalid JSON.") from e
