"""Mint synthetic Coke accounts for the smoke run.

Coke's runtime accepts ids prefixed `ck_` or `acct_` as synthetic accounts and
auto-creates the user document on first inbound (see
`agent/runner/identity.py::is_synthetic_coke_account_id`). For friend-link and
shared-reminder flows that read user profile fields, we also call the gateway's
`/api/internal/coke-users/provision` to bind a ClawScale user record.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass

import requests

from tools.agent_smoke import _config


@dataclass
class SmokeAccount:
    coke_account_id: str
    display_name: str
    label: str
    tenant_id: str | None
    clawscale_user_id: str | None


_LABEL_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,32}$")


def _new_account_id(batch_id: str, label: str) -> str:
    return f"ck_smoke_{batch_id}_{label}"


def synthetic_account_id(batch_id: str, label: str) -> str:
    """Return a deterministic synthetic id without calling gateway."""
    if not _LABEL_RE.match(label):
        raise ValueError(f"invalid label: {label!r}")
    return _new_account_id(batch_id, label)


def provision_account(
    label: str,
    *,
    batch_id: str | None = None,
    display_name: str | None = None,
    skip_provision: bool = False,
) -> SmokeAccount:
    """Mint an account and (unless `skip_provision`) bind it via gateway.

    If gateway provisioning fails, returns the synthetic account anyway and
    leaves `tenant_id` / `clawscale_user_id` as None so callers can decide
    whether to treat it as fatal.
    """
    if batch_id is None:
        batch_id = time.strftime("%Y%m%dt%H%M%S", time.gmtime())
    coke_account_id = synthetic_account_id(batch_id, label)
    if not display_name:
        display_name = f"Smoke {label.title()}"

    tenant_id: str | None = None
    clawscale_user_id: str | None = None

    if not skip_provision:
        url = _config.gateway_api_base_url() + "/api/internal/coke-users/provision"
        headers = {
            "Authorization": f"Bearer {_config.gateway_identity_api_key()}",
            "Content-Type": "application/json",
        }
        body = {"coke_account_id": coke_account_id, "display_name": display_name}
        try:
            response = requests.post(url, json=body, headers=headers, timeout=15)
            data = response.json() if response.headers.get("content-type", "").startswith("application/json") else None
            if response.status_code == 200 and isinstance(data, dict) and data.get("ok"):
                payload = data.get("data") or {}
                tenant_id = payload.get("tenant_id")
                clawscale_user_id = payload.get("clawscale_user_id")
            else:
                # provisioning is best-effort; record absence and continue
                print(
                    f"[smoke] provision warn label={label} status={response.status_code} body={data!r}"
                )
        except requests.RequestException as exc:
            print(f"[smoke] provision exception label={label} err={exc}")

    return SmokeAccount(
        coke_account_id=coke_account_id,
        display_name=display_name,
        label=label,
        tenant_id=tenant_id,
        clawscale_user_id=clawscale_user_id,
    )
