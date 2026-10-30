
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(
    title="VoiceLink AI Agent",
    description="AI Sales Assistant for Automobile Dealerships",
    version="0.1.0"
)

class ChatRequest(BaseModel):
    message: str

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
    message = request.message.lower()

    if any(word in message for word in ["bike", "motorcycle", "बाइक"]):
        reply = "जी, आप किस बजट में motorcycle देख रहे हैं?"

    elif any(word in message for word in ["scooter", "स्कूटर"]):
        reply = "जी, आपका scooter का अनुमानित बजट कितना है?"

    else:
        reply = "नमस्ते! आप Bajaj की motorcycle देख रहे हैं या scooter?"

    return {
        "reply": reply,
        "agent": "VoiceLink"
    }
