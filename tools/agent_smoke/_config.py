"""Read runtime settings the smoke helpers need.

We read from `conf/config.json` via the project's own loader so the helpers
match what the live bridge / gateway see — no second source of truth.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Loader uses cwd to find conf/config.json.
_prev_cwd = os.getcwd()
os.chdir(PROJECT_ROOT)
try:
    from conf.config import CONF  # noqa: E402
finally:
    os.chdir(_prev_cwd)


def _bridge() -> dict:
    return CONF.get("clawscale_bridge", {}) or {}


def bridge_base_url() -> str:
    host = _bridge().get("host") or "127.0.0.1"
    if host == "0.0.0.0":
        host = "127.0.0.1"
    port = _bridge().get("port") or 8090
    return f"http://{host}:{port}"


def bridge_api_key() -> str:
    key = _bridge().get("api_key") or ""
    if not isinstance(key, str) or not key.strip() or key.startswith("${"):
        raise RuntimeError("clawscale_bridge.api_key not configured")
    return key


def gateway_api_base_url() -> str:
    """Derive the gateway API origin from the bridge's identity_api_url.

    If unset (placeholder), fall back to the conventional local gateway port.
    """
    identity = _bridge().get("identity_api_url") or ""
    if isinstance(identity, str) and identity and not identity.startswith("${"):
        parts = urlsplit(identity)
        if parts.scheme and parts.netloc:
            return urlunsplit((parts.scheme, parts.netloc, "", "", ""))
    return "http://127.0.0.1:4041"


def gateway_identity_api_key() -> str:
    """Bearer token for gateway /api/internal/coke-users/provision."""
    key = _bridge().get("identity_api_key") or ""
    if not isinstance(key, str) or not key.strip() or key.startswith("${"):
        raise RuntimeError("clawscale_bridge.identity_api_key not configured")
    return key


def mongo_uri() -> str:
    mongo = CONF.get("mongodb", {}) or {}
    ip = mongo.get("mongodb_ip") or "127.0.0.1"
    port = mongo.get("mongodb_port") or "27017"
    return f"mongodb://{ip}:{port}/"


def mongo_db_name() -> str:
    mongo = CONF.get("mongodb", {}) or {}
    return mongo.get("mongodb_name") or "mymongo"


def character_alias() -> str:
    return CONF.get("default_character_alias", "coke")
