
import asyncio

from app.agent import VoiceLinkAgent


def test_empty_message():
    agent = VoiceLinkAgent()

    result = asyncio.run(agent.reply(""))

    assert result == "कृपया अपना सवाल बताइए।"


def test_motorcycle_budget_question():
    agent = VoiceLinkAgent()

    result = asyncio.run(
        agent.reply("Mujhe bike chahiye")
    )

    assert "बजट" in result


def test_scooter_city_question():
    agent = VoiceLinkAgent()

    result = asyncio.run(
        agent.reply("Mujhe scooter chahiye")
    )

    assert "शहर" in result


def test_default_greeting():
    agent = VoiceLinkAgent()

    result = asyncio.run(
        agent.reply("Namaste")
    )

    assert "VoiceLink" in result
