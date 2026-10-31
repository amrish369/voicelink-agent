
import os
import re
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.agent import VoiceLinkAgent

app = FastAPI(
    title="VoiceLink AI Agent",
    description="AI Sales Assistant for Dealerships",
    version="0.3.0",
)

agent = VoiceLinkAgent()


class ChatMessage(BaseModel):
    role: str
    content: str = Field(min_length=1, max_length=2000)


class LeadData(BaseModel):
    customer_name: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=8, max_length=20)
    city: str | None = Field(default=None, max_length=100)
    interested_vehicle: str | None = Field(default=None, max_length=120)
    budget_min: float | None = Field(default=None, ge=0)
    budget_max: float | None = Field(default=None, ge=0)
    purchase_timeline: str | None = Field(default=None, max_length=100)

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, value: str) -> str:
        normalized = re.sub(r"[\s()-]", "", value)
        if not re.fullmatch(r"\+?[0-9]{8,15}", normalized):
            raise ValueError("Enter a valid phone number")
        return normalized


class ConsentData(BaseModel):
    granted: bool
    source: str = Field(min_length=2, max_length=80)
    evidence: str = Field(min_length=10, max_length=2000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=20)
    lead: LeadData | None = None
    consent: ConsentData | None = None


async def save_lead(
    lead: LeadData,
    consent: ConsentData,
    history: list[ChatMessage],
) -> str:
    supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    dealership_id = os.getenv("DEALERSHIP_ID", "")

    if not (supabase_url and service_key and dealership_id):
        raise RuntimeError("Lead storage is not configured")

    payload: dict[str, Any] = {
        "p_dealership_id": dealership_id,
        "p_customer_name": lead.customer_name,
        "p_phone": lead.phone,
        "p_city": lead.city,
        "p_interested_vehicle": lead.interested_vehicle,
        "p_budget_min": lead.budget_min,
        "p_budget_max": lead.budget_max,
        "p_purchase_timeline": lead.purchase_timeline,
        "p_consent_source": consent.source,
        "p_consent_evidence": consent.evidence,
        "p_messages": [item.model_dump() for item in history],
    }

    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            f"{supabase_url}/rest/v1/rpc/create_voicelink_lead",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        result = response.json()

    if not isinstance(result, str) or not result:
        raise RuntimeError("Invalid lead storage response")

    return result


@app.get("/")
async def home():
    return {
        "service": "VoiceLink AI Agent",
        "status": "running",
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.get("/ready")
async def ready():
    configured = all(
        os.getenv(key)
        for key in (
            "SUPABASE_URL",
            "SUPABASE_SERVICE_ROLE_KEY",
            "DEALERSHIP_ID",
        )
    )
    return {
        "status": "ready" if configured else "configuration_required"
    }


@app.post("/chat")
async def chat(request: ChatRequest):

    if (request.lead is None) != (request.consent is None):
        raise HTTPException(
            status_code=422,
            detail="Lead details and consent must be submitted together",
        )

    if request.consent is not None and not request.consent.granted:
        raise HTTPException(
            status_code=403,
            detail="Consent is required before saving a lead",
        )

    if (
        request.lead
        and request.lead.budget_min is not None
        and request.lead.budget_max is not None
        and request.lead.budget_min > request.lead.budget_max
    ):
        raise HTTPException(
            status_code=422,
            detail="Minimum budget cannot exceed maximum budget",
        )

    try:
        reply = await agent.reply(
            request.message,
            [item.model_dump() for item in request.history],
        )
    except Exception:
        raise HTTPException(
            status_code=502,
            detail="AI provider request failed",
        )

    result = {
        "reply": reply,
        "agent": "VoiceLink",
    }

    if request.lead and request.consent:
        try:
            lead_id = await save_lead(
                request.lead,
                request.consent,
                request.history,
            )
            result["lead_id"] = lead_id

        except Exception:
            raise HTTPException(
                status_code=502,
                detail="Lead could not be saved. Check server configuration.",
            )

    return result
