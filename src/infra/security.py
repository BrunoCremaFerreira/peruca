"""
API-key authentication for the REST API.

A single static key sent as the ``X-API-Key`` header, adequate for a home
network with known callers (Home Assistant, Node-RED, first-party apps) — no
OAuth/JWT. Migration mode: when the key is unset the dependency is a no-op so
existing deployments keep working (a warning is logged at startup).
"""

import secrets
from typing import Optional

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from infra.settings import Settings


_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(provided: Optional[str] = Security(_api_key_header)) -> None:
    """
    FastAPI dependency: enforce the API key when configured. Constant-time
    comparison over bytes avoids timing attacks and non-ASCII TypeErrors.
    """
    expected = Settings().peruca_api_key.get_secret_value()
    if not expected:
        return  # migration mode: auth not configured
    if provided is None or not secrets.compare_digest(
        provided.encode("utf-8"), expected.encode("utf-8")
    ):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
