
import os
import httpx

from app.prompts import SYSTEM_PROMPT


class VoiceLinkAgent:

    def __init__(self):
        self.base_url = os.getenv("LLM_BASE_URL", "").rstrip("/")
        self.api_key = os.getenv("LLM_API_KEY", "")
        self.model = os.getenv("LLM_MODEL", "")

    async def reply(self, message: str, history=None) -> str:

        if not message.strip():
            return "कृपया अपना सवाल बताइए।"

        if self.base_url and self.model:
            return await self._ask_llm(message, history or [])

        return self._demo_reply(message)

    async def _ask_llm(self, message, history):

        url = f"{self.base_url}/chat/completions"

        headers = {
            "Content-Type": "application/json"
        }

        if self.api_key:
            headers["Authorization"] = (
                f"Bearer {self.api_key}"
            )

        messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            }
        ]

        for item in history[-8:]:
            if (
                item.get("role") in ["user", "assistant"]
                and isinstance(item.get("content"), str)
            ):
                messages.append(item)

        messages.append({
            "role": "user",
            "content": message
        })

        async with httpx.AsyncClient(timeout=30) as client:

            response = await client.post(
                url,
                headers=headers,
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": 0.4
                }
            )

            response.raise_for_status()
            data = response.json()

        return data["choices"][0]["message"]["content"].strip()

    def _demo_reply(self, message):

        text = message.lower()

        if any(x in text for x in ["bike", "बाइक", "motorcycle"]):
            return "जी, आपका अनुमानित बजट कितना है?"

        if any(x in text for x in ["scooter", "स्कूटर"]):
            return "जी, आप किस शहर में रहते हैं?"

        if any(x in text for x in ["price", "कीमत", "दाम"]):
            return "आप किस Bajaj मॉडल की कीमत जानना चाहते हैं?"

        return (
            "नमस्ते! मैं VoiceLink AI Sales Assistant हूँ। "
            "आप Bajaj की motorcycle देख रहे हैं या scooter?"
        )
