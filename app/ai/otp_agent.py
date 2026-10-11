import os
import re
import logging
from typing import Any, Optional

os.environ["PYDANTIC_AI_NO_BANNER"] = "1"

from pydantic_ai import Agent
from app.ai.providers import get_deepseek_model, is_deepseek_configured
from app.schemas.auth import OTPExtractResult

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
You are an expert security and authentication parser for financial systems and Thai broker SMS notifications.
Your job is to parse incoming SMS or chat messages and extract:
1. `otp`: The 6-digit one-time password / verification code (digits only, exactly 6 characters).
2. `ref`: The broker transaction reference code if present (usually 3-8 uppercase alphanumeric characters, e.g. BIPE, REF: 9A2B).
3. `source_confidence`: Confidence score between 0.0 and 1.0.
4. `raw_message`: The original input string.

Rules:
- If no 6-digit OTP is found, `otp` must be None.
- Ignore phone numbers (10 digits starting with 0), account numbers, dates, or timestamps.
- Extract only the authentic 6-digit verification code.
"""


def create_otp_agent(model_override: Optional[Any] = None) -> Agent[None, OTPExtractResult]:
    """
    Factory creating a PydanticAI Agent configured to extract OTPExtractResult.
    Allows injecting a TestModel or alternative model for testing.
    """
    model = model_override or get_deepseek_model()
    if model is None:
        raise ValueError("Cannot create OTPExtractorAgent: DeepSeek model could not be initialized.")

    return Agent(
        model,
        output_type=OTPExtractResult,
        system_prompt=SYSTEM_PROMPT,
    )


async def extract_otp_from_text(
    text: str,
    model_override: Optional[Any] = None
) -> OTPExtractResult:
    """
    Dual-engine extraction:
    1. Fast regex extraction (< 1ms).
    2. Fallback to PydanticAI if text is complex, unstructured, or ambiguous.
    """
    if not text:
        return OTPExtractResult(raw_message=text, source_confidence=0.0)

    clean_text = text.strip()

    # Fast Path 1: Exact 6-digit input (e.g. "849201")
    if clean_text.isdigit() and len(clean_text) == 6:
        return OTPExtractResult(
            otp=clean_text,
            ref=None,
            source_confidence=1.0,
            raw_message=clean_text
        )

    # Fast Path 2: Common Thai/English SMS patterns with Context Keywords
    ref_match = re.search(
        r"(?:Ref(?:\.|erence)?(?:\s*(?:Code|No\.?))?|รหัสอ้างอิง|หมายเลขอ้างอิง)\s*[:：=]?\s*([A-Za-z0-9]{3,8})\b",
        clean_text,
        re.IGNORECASE
    )
    ref_val = ref_match.group(1).upper() if ref_match else None

    # Contextual OTP match: "Your OTP is 123456", "Your OTP password is 123456", "รหัส OTP ของคุณคือ 123456"
    otp_match = re.search(
        r"(?:OTP|password|code|รหัส(?:ผ่าน|ยืนยัน| OTP)?)\s*(?:is|คือ|:|：|=|\s)*[\"\'<\(]?\s*([0-9]{6})\b",
        clean_text,
        re.IGNORECASE
    )
    if not otp_match:
        # Reverse format: "123456 is your OTP" or "123456 (Ref: ABCD)"
        otp_match = re.search(
            r"\b([0-9]{6})\s*(?:is\s+your\s+OTP|\(Ref|\s*\(รหัส)",
            clean_text,
            re.IGNORECASE
        )

    otp_val = otp_match.group(1) if otp_match else None

    # Safe fallback: if OTP/Ref keywords exist, match any isolated 6-digit integer not part of a URL
    if not otp_val and any(k in clean_text.lower() for k in ["otp", "ref", "kss", "krungsri", "รหัสยืนยัน"]):
        no_url_text = re.sub(r"https?://\S+", "", clean_text)
        isolated_digits = re.findall(r"(?<![\w\-\./])([0-9]{6})(?![\w\-\./])", no_url_text)
        if isolated_digits:
            otp_val = isolated_digits[0]

    if otp_val:
        return OTPExtractResult(
            otp=otp_val,
            ref=ref_val,
            source_confidence=0.98,
            raw_message=clean_text
        )

    # Fallback to PydanticAI if available and regex didn't find a clean match
    has_otp_hint = any(w in clean_text.lower() for w in ["otp", "code", "ref", "รหัส", "verify", "verification", "sms", "liberator", "krungsri", "password"])
    has_digits = bool(re.search(r'\d{3,}', clean_text))
    if (model_override or is_deepseek_configured()) and (has_otp_hint or has_digits):
        try:
            agent = create_otp_agent(model_override=model_override)
            res = await agent.run(clean_text)
            extracted = res.output
            if extracted.raw_message is None:
                extracted.raw_message = clean_text
            return extracted
        except Exception as e:
            logger.warning(f"PydanticAI OTP parsing fallback failed: {e}")

    return OTPExtractResult(
        otp=None,
        ref=ref_val,
        source_confidence=0.0,
        raw_message=clean_text
    )
