
import os
import httpx

from app.prompts import SYSTEM_PROMPT


class VoiceLinkAgent:

    def __init__(self):
        self.base_url = os.getenv(
            "LLM_BASE_URL", ""
        ).rstrip("/")

        self.api_key = os.getenv("LLM_API_KEY", "")
        self.model = os.getenv("LLM_MODEL", "")

    async def reply(self, message: str, history=None) -> str:

        if not message or not message.strip():
            return "कृपया अपना सवाल बताइए।"

        if self.base_url and self.model:
            if not self.api_key:
                raise RuntimeError(
                    "LLM_API_KEY is required"
                )

            return await self._ask_llm(
                message.strip(),
                history or [],
            )

        return self._demo_reply(message)

    async def _ask_llm(self, message: str, history: list) -> str:

        messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            }
        ]

        for item in history[-8:]:

            if not isinstance(item, dict):
                continue

            role = item.get("role")
            content = item.get("content")

            if role in ("user", "assistant") and isinstance(content, str):
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

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0)
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

            response.raise_for_status()
            data = response.json()

        try:
            content = data["choices"][0]["message"]["content"]

        except (KeyError, IndexError, TypeError):
            raise RuntimeError(
                "AI provider returned an invalid response"
            )

        if not isinstance(content, str) or not content.strip():
            raise RuntimeError(
                "AI provider returned an empty response"
            )

        return content.strip()

    def _demo_reply(self, message: str) -> str:

        text = message.lower()

        if any(x in text for x in [
            "bike", "बाइक", "motorcycle", "मोटरसाइकिल"
        ]):
            return "जी, आपका अनुमानित बजट कितना है?"

        if any(x in text for x in [
            "scooter", "स्कूटर"
        ]):
            return "जी, आप किस शहर में रहते हैं?"

        if any(x in text for x in [
            "price", "कीमत", "दाम"
        ]):
            return "आप किस Bajaj मॉडल की कीमत जानना चाहते हैं?"

        return (
            "नमस्ते! मैं VoiceLink AI Sales Assistant हूँ। "
            "आप Bajaj की motorcycle देख रहे हैं या scooter?"
        )
