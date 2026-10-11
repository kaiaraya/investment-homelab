import os
import logging
from typing import Optional

from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.models.openai import OpenAIChatModel
from app.core.config import settings

logger = logging.getLogger(__name__)

DEFAULT_GEMINI_MODEL = "gemini-3.6-flash"
DEFAULT_DEEPSEEK_MODEL = "deepseek-chat"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"


def get_gemini_api_key() -> Optional[str]:
    """Retrieves Google / Gemini API key from settings or OS environment."""
    return settings.GEMINI_API_KEY or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")


def is_gemini_configured() -> bool:
    """Returns True if a non-empty API key is present."""
    key = get_gemini_api_key()
    return bool(key and len(key.strip()) > 5 and key != "mock_key")


def get_google_provider() -> Optional[GoogleProvider]:
    """Instantiates GoogleProvider with configured API key."""
    key = get_gemini_api_key()
    if not key:
        return None
    # Ensure standard env var is set for sub-libraries
    os.environ["GOOGLE_API_KEY"] = key
    return GoogleProvider(api_key=key)


def get_gemini_model(model_name: Optional[str] = None) -> Optional[GoogleModel]:
    """
    Factory function returning a configured GoogleModel instance for PydanticAI Agents.
    Defaults to 'gemini-3.6-flash'.
    """
    provider = get_google_provider()
    if not provider:
        logger.warning("GoogleProvider cannot be created: GEMINI_API_KEY is not configured.")
        return None

    target_model = model_name or DEFAULT_GEMINI_MODEL
    return GoogleModel(target_model, provider=provider)


# ==============================================================================
# DeepSeek (OpenAI-compatible) Provider
# DeepSeek exposes an OpenAI-compatible /chat/completions endpoint, so it is
# routed through pydantic_ai's OpenAIProvider with a DeepSeek base_url.
# Used as the PRIMARY AI interpreter for the Signal and OTP agents.
# ==============================================================================
def get_deepseek_api_key() -> Optional[str]:
    """Retrieves DeepSeek API key from settings or OS environment."""
    return settings.DEEPSEEK_API_KEY or os.getenv("DEEPSEEK_API_KEY")


def is_deepseek_configured() -> bool:
    """Returns True if a non-empty DeepSeek API key is present."""
    key = get_deepseek_api_key()
    return bool(key and len(key.strip()) > 5 and key != "mock_key")


def get_deepseek_provider() -> Optional[OpenAIProvider]:
    """Instantiates an OpenAIProvider pointed at the DeepSeek base URL."""
    key = get_deepseek_api_key()
    if not key:
        return None
    base_url = settings.DEEPSEEK_BASE_URL or DEEPSEEK_BASE_URL
    return OpenAIProvider(base_url=base_url, api_key=key)


def get_deepseek_model(model_name: Optional[str] = None) -> Optional[OpenAIChatModel]:
    """
    Factory function returning a configured OpenAIChatModel instance for PydanticAI Agents,
    pointed at the DeepSeek API. Defaults to 'deepseek-chat'.
    """
    provider = get_deepseek_provider()
    if not provider:
        logger.warning("DeepSeek provider cannot be created: DEEPSEEK_API_KEY is not configured.")
        return None

    target_model = model_name or settings.DEEPSEEK_MODEL or DEFAULT_DEEPSEEK_MODEL
    return OpenAIChatModel(target_model, provider=provider)
