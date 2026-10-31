
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_home_endpoint():
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "service": "VoiceLink AI Agent",
        "status": "running"
    }


def test_health_endpoint():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_chat_endpoint(monkeypatch):
    async def fake_reply(message, history=None):
        return "जी, आपका बजट कितना है?"

    monkeypatch.setattr(
        "app.main.agent.reply",
        fake_reply
    )

    response = client.post(
        "/chat",
        json={"message": "Mujhe Bajaj bike chahiye"}
    )

    assert response.status_code == 200
    assert response.json()["reply"] == "जी, आपका बजट कितना है?"
    assert response.json()["agent"] == "VoiceLink"


def test_chat_rejects_empty_message():
    response = client.post(
        "/chat",
        json={"message": ""}
    )

    assert response.status_code == 422


def test_chat_rejects_long_message():
    response = client.post(
        "/chat",
        json={"message": "A" * 2001}
    )

    assert response.status_code == 422


def test_chat_provider_error(monkeypatch):
    async def fake_reply(message, history=None):
        raise RuntimeError("Provider unavailable")

    monkeypatch.setattr(
        "app.main.agent.reply",
        fake_reply
    )

    response = client.post(
        "/chat",
        json={"message": "Bajaj Pulsar price?"}
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "AI provider request failed"
