
import os
import logging
from typing import Any

import httpx

from app.prompts import SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class VoiceLinkConfigurationError(RuntimeError):
    pass


class VoiceLinkProviderError(RuntimeError):
    pass


class VoiceLinkAgent:

    def __init__(self):
        self.base_url = os.getenv(
            "LLM_BASE_URL", ""
        ).strip().rstrip("/")

        self.api_key = os.getenv(
            "LLM_API_KEY", ""
        ).strip()

        self.model = os.getenv(
            "LLM_MODEL", ""
        ).strip()

    def is_configured(self) -> bool:
        return bool(
            self.base_url
            and self.api_key
            and self.model
        )

    async def reply(
        self,
        message: str,
        history: list[dict[str, Any]] | None = None,
    ) -> str:

        clean_message = (message or "").strip()

        if not clean_message:
            raise ValueError("Message cannot be empty")

        missing = [
            name
            for name, value in (
                ("LLM_BASE_URL", self.base_url),
                ("LLM_API_KEY", self.api_key),
                ("LLM_MODEL", self.model),
            )
            if not value
        ]

        if missing:
            raise VoiceLinkConfigurationError(
                "AI provider configuration missing: "
                + ", ".join(missing)
            )

        return await self._ask_llm(
            clean_message,
            history or [],
        )

    async def _ask_llm(
        self,
        message: str,
        history: list[dict[str, Any]],
    ) -> str:

        messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            }
        ]

        # Only accept user and assistant messages from history.
        for item in history[-8:]:

            if not isinstance(item, dict):
                continue

            role = item.get("role")
            content = item.get("content")

            if (
                role in ("user", "assistant")
                and isinstance(content, str)
            ):
                cleaned = content.strip()[:2000]

                if cleaned:
                    messages.append({
                        "role": role,
                        "content": cleaned,
                    })

        messages.append({
            "role": "user",
            "content": message,
        })

        timeout = httpx.Timeout(
            35.0,
            connect=10.0,
        )

        try:
            async with httpx.AsyncClient(
                timeout=timeout
            ) as client:

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
                logger.error(
                    "LLM provider HTTP status: %s",
                    response.status_code,
                )

                raise VoiceLinkProviderError(
                    f"AI provider failed: HTTP {response.status_code}"
                )

            data = response.json()

        except httpx.TimeoutException as exc:
            logger.exception("AI provider timeout")
            raise VoiceLinkProviderError(
                "AI provider timed out"
            ) from exc

        except httpx.RequestError as exc:
            logger.exception("AI provider connection failed")
            raise VoiceLinkProviderError(
                "Cannot connect to AI provider"
            ) from exc

        except ValueError as exc:
            logger.exception("Invalid AI provider JSON")
            raise VoiceLinkProviderError(
                "AI provider returned invalid JSON"
            ) from exc

        try:
            content = data["choices"][0]["message"]["content"]

        except (KeyError, IndexError, TypeError) as exc:
            logger.error(
                "Unexpected AI provider response structure"
            )

            raise VoiceLinkProviderError(
                "Invalid AI provider response"
            ) from exc

        if not isinstance(content, str) or not content.strip():
            raise VoiceLinkProviderError(
                "AI provider returned an empty response"
            )

        return content.strip()
