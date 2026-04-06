from flask import request


def require_bridge_auth(expected_token: str) -> tuple[bool, tuple[dict, int] | None]:
    header = request.headers.get("Authorization", "")
    if header != f"Bearer {expected_token}":
        return False, ({"ok": False, "error": "unauthorized"}, 401)
    return True, None
