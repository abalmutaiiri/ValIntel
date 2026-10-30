"""Windows credential-store integration for the optional HenrikDEV key."""
from __future__ import annotations
import keyring

CREDENTIAL_SERVICE = "ValIntel"
CREDENTIAL_USERNAME = "HenrikDEV_API_Key"

def get_key() -> str:
    try:
        return keyring.get_password(CREDENTIAL_SERVICE, CREDENTIAL_USERNAME) or ""
    except Exception:
        return ""
