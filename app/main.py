
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.agent import VoiceLinkAgent

app = FastAPI(
    title="VoiceLink AI Agent",
    description="AI Sales Assistant for Dealerships",
    version="0.2.0"
)

agent = VoiceLinkAgent()


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: list[dict[str, str]] = Field(default_factory=list)


@app.get("/")
async def home():
    return {
        "service": "VoiceLink AI Agent",
        "status": "running"
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.post("/chat")
async def chat(request: ChatRequest):
    try:
        reply = await agent.reply(
            request.message,
            request.history
        )

        return {
            "reply": reply,
            "agent": "VoiceLink"
        }

    except Exception:
        raise HTTPException(
            status_code=502,
            detail="AI provider request failed"
        )

