from unittest.mock import MagicMock


def test_register_hashes_password_and_returns_token():
    from connector.clawscale_bridge.user_auth import UserAuthService

    user_dao = MagicMock()
    user_dao.get_user_by_email.return_value = None
    user_dao.create_user.return_value = "65f000000000000000000111"

    service = UserAuthService(
        user_dao=user_dao,
        secret_key="test-secret",
        token_ttl_seconds=3600,
    )

    result = service.register(
        display_name="Alice",
        email="Alice@Example.com",
        password="correct horse battery staple",
    )

    stored = user_dao.create_user.call_args[0][0]
    assert stored["email"] == "alice@example.com"
    assert stored["password_hash"] != "correct horse battery staple"
    assert result["user"]["email"] == "alice@example.com"
    assert result["token"]


def test_login_rejects_invalid_password():
    from werkzeug.security import generate_password_hash
    from connector.clawscale_bridge.user_auth import UserAuthService

    user_dao = MagicMock()
    user_dao.get_user_by_email.return_value = {
        "_id": "65f000000000000000000111",
        "email": "alice@example.com",
        "display_name": "Alice",
        "password_hash": generate_password_hash("correct-password"),
        "is_character": False,
    }

    service = UserAuthService(
        user_dao=user_dao,
        secret_key="test-secret",
        token_ttl_seconds=3600,
    )

    ok, error = service.login("alice@example.com", "wrong-password")

    assert ok is False
    assert error == "invalid_credentials"
