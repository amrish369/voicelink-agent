
import os
import logging
from typing import Any

import httpx

from app.prompts import SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class VoiceLinkConfigurationError(RuntimeError):
    pass


class VoiceLinkProviderError(RuntimeError):
    def __init__(self, message: str, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


class VoiceLinkAgent:

    def __init__(self):
        # Primary provider: Groq (OpenAI-compatible API)
        self.base_url = os.getenv(
            "LLM_BASE_URL", ""
        ).strip().rstrip("/")

        self.api_key = os.getenv(
            "LLM_API_KEY", ""
        ).strip()

        self.model = os.getenv(
            "LLM_MODEL", ""
        ).strip()

        # Secondary provider: Google Gemini
        self.gemini_api_key = os.getenv(
            "GEMINI_API_KEY", ""
        ).strip()

        self.gemini_model = os.getenv(
            "GEMINI_MODEL", "gemini-3.8-flash"
        ).strip()

    def is_configured(self) -> bool:
        return bool(
            self.base_url
            and self.api_key
            and self.model
        )

    def is_gemini_configured(self) -> bool:
        return bool(self.gemini_api_key and self.gemini_model)

    async def reply(
        self,
        message: str,
        history: list[dict[str, Any]] | None = None,
    ) -> str:

        clean_message = (message or "").strip()

        if not clean_message:
            raise ValueError("Message cannot be empty")

        if not self.is_configured() and not self.is_gemini_configured():
            raise VoiceLinkConfigurationError(
                "No AI provider is configured"
            )

        clean_history = self._clean_history(history or [])

        # Try primary provider first.
        if self.is_configured():
            try:
                answer = await self._ask_groq(
                    clean_message,
                    clean_history,
                )
                logger.info("AI response served by Groq")
                return answer

            except VoiceLinkProviderError as exc:
                if not exc.retryable:
                    raise

                if not self.is_gemini_configured():
                    raise

                logger.warning(
                    "Groq temporarily unavailable; trying Gemini fallback"
                )

        # Gemini is used when Groq is unavailable,
        # or when Groq is not configured.
        if self.is_gemini_configured():
            try:
                answer = await self._ask_gemini(
                    clean_message,
                    clean_history,
                )
                logger.info("AI response served by Gemini")
                return answer

            except VoiceLinkProviderError:
                logger.exception("Gemini fallback failed")
                raise

        raise VoiceLinkProviderError(
            "No available AI provider",
            retryable=False,
        )

    def _clean_history(
        self,
        history: list[dict[str, Any]],
    ) -> list[dict[str, str]]:

        cleaned_history = []

        for item in history[-8:]:

            if not isinstance(item, dict):
                continue

            role = item.get("role")
            content = item.get("content")

            if (
                role in ("user", "assistant")
                and isinstance(content, str)
            ):
                content = content.strip()[:2000]

                if content:
                    cleaned_history.append({
                        "role": role,
                        "content": content,
                    })

        return cleaned_history

    async def _ask_groq(
        self,
        message: str,
        history: list[dict[str, str]],
    ) -> str:

        messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            }
        ]

        messages.extend(history)

        messages.append({
            "role": "user",
            "content": message,
        })

        timeout = httpx.Timeout(35.0, connect=10.0)

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:

                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": messages,
                        "temperature": 0.4,
                    },
                )

            if response.status_code >= 400:
                status = response.status_code

                logger.error("Groq HTTP status: %s", status)

                raise VoiceLinkProviderError(
                    f"Groq provider HTTP {status}",
                    retryable=(status == 429 or status >= 500),
                )

            data = response.json()

            content = data["choices"][0]["message"]["content"]

            if not isinstance(content, str) or not content.strip():
                raise VoiceLinkProviderError(
                    "Groq returned an empty response"
                )

            return content.strip()

        except httpx.TimeoutException as exc:
            raise VoiceLinkProviderError(
                "Groq request timed out",
                retryable=True,
            ) from exc

        except httpx.RequestError as exc:
            raise VoiceLinkProviderError(
                "Cannot connect to Groq",
                retryable=True,
            ) from exc

        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise VoiceLinkProviderError(
                "Invalid Groq response",
                retryable=False,
            ) from exc

    async def _ask_gemini(
        self,
        message: str,
        history: list[dict[str, str]],
    ) -> str:

        url = (
            "https://generativelanguage.googleapis.com/"
            f"v1beta/models/{self.gemini_model}:generateContent"
        )

        contents = []

        for item in history:
            contents.append({
                "role": (
                    "model"
                    if item["role"] == "assistant"
                    else "user"
                ),
                "parts": [{"text": item["content"]}],
            })

        contents.append({
            "role": "user",
            "parts": [{"text": message}],
        })

        payload = {
            "systemInstruction": {
                "parts": [{"text": SYSTEM_PROMPT}]
            },
            "contents": contents,
            "generationConfig": {
                "temperature": 0.4,
                "maxOutputTokens": 700,
            },
        }

        timeout = httpx.Timeout(35.0, connect=10.0)

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:

                response = await client.post(
                    url,
                    headers={
                        "x-goog-api-key": self.gemini_api_key,
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )

            if response.status_code >= 400:
                status = response.status_code

                logger.error("Gemini HTTP status: %s", status)

                raise VoiceLinkProviderError(
                    f"Gemini provider HTTP {status}",
                    retryable=(status == 429 or status >= 500),
                )

            data = response.json()

            content = (
                data["candidates"][0]["content"]["parts"][0]["text"]
            )

            if not isinstance(content, str) or not content.strip():
                raise VoiceLinkProviderError(
                    "Gemini returned an empty response"
                )

            return content.strip()

        except httpx.TimeoutException as exc:
            raise VoiceLinkProviderError(
                "Gemini request timed out",
                retryable=True,
            ) from exc

        except httpx.RequestError as exc:
            raise VoiceLinkProviderError(
                "Cannot connect to Gemini",
                retryable=True,
            ) from exc

        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise VoiceLinkProviderError(
                "Invalid Gemini response",
                retryable=False,
            ) from exc
