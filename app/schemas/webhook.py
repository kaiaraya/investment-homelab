from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class SignalTextPayload(BaseModel):
    text: str = Field(..., description="Freeform text or strategy markdown report")
    auth_token: Optional[str] = Field(default=None, description="Homelab security token")
    auto_execute: bool = Field(default=False, description="If True, immediately creates and queues valid immediate orders")


class WebhookResponse(BaseModel):
    success: bool
    message: str
    order_id: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
