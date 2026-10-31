
import os
import re
import logging
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from app.agent import (
    VoiceLinkAgent,
    VoiceLinkConfigurationError,
    VoiceLinkProviderError,
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="VoiceLink AI Agent",
    description="AI Sales Assistant for Dealerships",
    version="0.4.0",
)

# CORS: allow the VoiceLink customer website domains
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://voicelink-customer.vercel.app",
        "https://voicelink-customer-amrish369s-projects.vercel.app",
        "https://voicelink-customer-itlull4k4-amrish369s-projects.vercel.app",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

agent = VoiceLinkAgent()


class ChatMessage(BaseModel):
    role: str
    content: str = Field(min_length=1, max_length=2000)

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        if value not in ("user", "assistant"):
            raise ValueError("Invalid message role")
        return value


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
    history: list[ChatMessage] = Field(
        default_factory=list,
        max_length=20,
    )
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

    if not all([supabase_url, service_key, dealership_id]):
        raise RuntimeError("Supabase configuration is incomplete")

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
        "p_messages": [
            item.model_dump() for item in history
        ],
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

        if response.status_code >= 400:
            logger.error(
                "Supabase lead save failed with HTTP %s",
                response.status_code,
            )
            raise RuntimeError("Supabase lead save failed")

        result = response.json()

    if not isinstance(result, str) or not result:
        raise RuntimeError("Invalid Supabase response")

    return result


@app.get("/")
async def home():
    return {
        "service": "VoiceLink AI Agent",
        "status": "running",
        "version": "0.4.0",
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.get("/ready")
async def ready():
    ai_ready = agent.is_configured()

    supabase_ready = all(
        os.getenv(key)
        for key in (
            "SUPABASE_URL",
            "SUPABASE_SERVICE_ROLE_KEY",
            "DEALERSHIP_ID",
        )
    )

    return {
        "status": (
            "ready" if ai_ready and supabase_ready
            else "configuration_required"
        ),
        "ai_configured": ai_ready,
        "supabase_configured": supabase_ready,
    }


@app.post("/chat")
async def chat(request: ChatRequest):

    if (request.lead is None) != (request.consent is None):
        raise HTTPException(
            status_code=422,
            detail="Lead and consent must be submitted together",
        )

    if request.consent and not request.consent.granted:
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

    except VoiceLinkConfigurationError:
        logger.error("VoiceLink AI configuration is incomplete")
        raise HTTPException(
            status_code=503,
            detail="AI service is not configured",
        )

    except VoiceLinkProviderError as exc:
        logger.warning("VoiceLink AI provider error: %s", str(exc))
        raise HTTPException(
            status_code=502,
            detail="AI provider is temporarily unavailable",
        )

    except Exception:
        logger.exception("Unexpected VoiceLink chat error")
        raise HTTPException(
            status_code=500,
            detail="Internal assistant error",
        )

    result: dict[str, Any] = {
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
            logger.exception("Lead saving failed")
            raise HTTPException(
                status_code=502,
                detail="Lead could not be saved",
            )

    return result
