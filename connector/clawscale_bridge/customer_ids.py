from __future__ import annotations


def resolve_customer_id(
    *,
    customer_id: str | None = None,
    account_id: str | None = None,
    coke_account_id: str | None = None,
) -> str:
    for candidate in (customer_id, account_id, coke_account_id):
        if not isinstance(candidate, str):
            continue
        normalized = candidate.strip()
        if normalized:
            return normalized

    raise ValueError("customer_id_required")
