from unittest.mock import MagicMock

import pytest
from pymongo.errors import DuplicateKeyError


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


def test_register_maps_duplicate_email_to_value_error():
    from connector.clawscale_bridge.user_auth import UserAuthService

    user_dao = MagicMock()
    user_dao.get_user_by_email.return_value = None
    user_dao.create_user.side_effect = DuplicateKeyError("duplicate key")

    service = UserAuthService(
        user_dao=user_dao,
        secret_key="test-secret",
        token_ttl_seconds=3600,
    )

    with pytest.raises(ValueError, match="email_already_exists"):
        service.register(
            display_name="Alice",
            email="Alice@Example.com",
            password="correct horse battery staple",
        )


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


def test_login_rejects_missing_password_hash():
    from connector.clawscale_bridge.user_auth import UserAuthService

    user_dao = MagicMock()
    user_dao.get_user_by_email.return_value = {
        "_id": "65f000000000000000000111",
        "email": "alice@example.com",
        "display_name": "Alice",
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


def test_login_rejects_when_web_auth_disabled():
    from werkzeug.security import generate_password_hash
    from connector.clawscale_bridge.user_auth import UserAuthService

    user_dao = MagicMock()
    user_dao.get_user_by_email.return_value = {
        "_id": "65f000000000000000000111",
        "email": "alice@example.com",
        "display_name": "Alice",
        "password_hash": generate_password_hash("correct-password"),
        "status": "normal",
        "web_auth_enabled": False,
        "is_character": False,
    }

    service = UserAuthService(
        user_dao=user_dao,
        secret_key="test-secret",
        token_ttl_seconds=3600,
    )

    ok, error = service.login("alice@example.com", "correct-password")

    assert ok is False
    assert error == "account_unavailable"


def test_login_rejects_when_user_is_character():
    from werkzeug.security import generate_password_hash
    from connector.clawscale_bridge.user_auth import UserAuthService

    user_dao = MagicMock()
    user_dao.get_user_by_email.return_value = {
        "_id": "65f000000000000000000111",
        "email": "alice@example.com",
        "display_name": "Alice",
        "password_hash": generate_password_hash("correct-password"),
        "status": "normal",
        "web_auth_enabled": True,
        "is_character": True,
    }

    service = UserAuthService(
        user_dao=user_dao,
        secret_key="test-secret",
        token_ttl_seconds=3600,
    )

    ok, error = service.login("alice@example.com", "correct-password")

    assert ok is False
    assert error == "account_unavailable"


def test_verify_token_returns_none_when_signed_payload_has_no_user_id():
    from connector.clawscale_bridge.user_auth import UserAuthService

    user_dao = MagicMock()
    service = UserAuthService(
        user_dao=user_dao,
        secret_key="test-secret",
        token_ttl_seconds=3600,
    )

    token = service.serializer.dumps({})

    assert service.verify_token(token) is None
    user_dao.get_user_by_id.assert_not_called()


def test_verify_token_returns_none_when_account_status_is_not_normal():
    from connector.clawscale_bridge.user_auth import UserAuthService

    user_dao = MagicMock()
    user_dao.get_user_by_id.return_value = {
        "_id": "65f000000000000000000111",
        "status": "disabled",
        "web_auth_enabled": True,
        "is_character": False,
    }
    service = UserAuthService(
        user_dao=user_dao,
        secret_key="test-secret",
        token_ttl_seconds=3600,
    )

    token = service.serializer.dumps({"user_id": "65f000000000000000000111"})

    assert service.verify_token(token) is None


def test_verify_token_returns_none_when_web_auth_disabled():
    from connector.clawscale_bridge.user_auth import UserAuthService

    user_dao = MagicMock()
    user_dao.get_user_by_id.return_value = {
        "_id": "65f000000000000000000111",
        "status": "normal",
        "web_auth_enabled": False,
        "is_character": False,
    }
    service = UserAuthService(
        user_dao=user_dao,
        secret_key="test-secret",
        token_ttl_seconds=3600,
    )

    token = service.serializer.dumps({"user_id": "65f000000000000000000111"})

    assert service.verify_token(token) is None


def test_verify_token_returns_none_when_user_is_character():
    from connector.clawscale_bridge.user_auth import UserAuthService

    user_dao = MagicMock()
    user_dao.get_user_by_id.return_value = {
        "_id": "65f000000000000000000111",
        "status": "normal",
        "web_auth_enabled": True,
        "is_character": True,
    }
    service = UserAuthService(
        user_dao=user_dao,
        secret_key="test-secret",
        token_ttl_seconds=3600,
    )

    token = service.serializer.dumps({"user_id": "65f000000000000000000111"})

    assert service.verify_token(token) is None
