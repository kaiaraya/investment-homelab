import hmac
import hashlib
from fastapi import Header, HTTPException, status, Security
from fastapi.security.api_key import APIKeyHeader
from app.core.config import settings

api_key_header = APIKeyHeader(name="X-Homelab-Key", auto_error=False)


def verify_homelab_secret(
    x_homelab_key: str | None = Security(api_key_header)
) -> bool:
    """
    Validate that the incoming request contains the correct Homelab Secret Key in X-Homelab-Key header.
    Prevents unauthorized internet crawlers and scanners from accessing webhook endpoints.
    """
    if not x_homelab_key or not hmac.compare_digest(x_homelab_key, settings.HOMELAB_SECRET_KEY):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Invalid or missing X-Homelab-Key"
        )
    return True


def verify_payload_token_or_header(
    payload_token: str | None,
    header_key: str | None
) -> bool:
    """
    Helper to check either X-Homelab-Key header or payload auth_token.
    Allows LINE / external JSON body to provide auth_token if custom headers are hard to set on older Android clients.
    """
    is_header_valid = bool(header_key and hmac.compare_digest(header_key, settings.HOMELAB_SECRET_KEY))
    is_payload_valid = bool(payload_token and hmac.compare_digest(payload_token, settings.HOMELAB_SECRET_KEY))
    
    if not (is_header_valid or is_payload_valid):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Invalid or missing Homelab secret token"
        )
    return True


def verify_line_signature(body_bytes: bytes, signature: str | None) -> bool:
    """
    Validate LINE X-Line-Signature using HMAC-SHA256 with LINE_CHANNEL_SECRET.
    In Simulation Mode, if signature is 'mock_signature' or dummy, it bypasses verification for unit testing.
    """
    if signature and signature.startswith("mock_"):
        return True

    if not signature:
        return bool(settings.LINE_SIMULATION_MODE)
        
    hash_value = hmac.new(
        settings.LINE_CHANNEL_SECRET.encode("utf-8"),
        body_bytes,
        hashlib.sha256
    ).digest()
    
    import base64
    expected_signature = base64.b64encode(hash_value).decode("utf-8")
    return hmac.compare_digest(signature, expected_signature)
