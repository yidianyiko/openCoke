from werkzeug.security import generate_password_hash


def test_bind_service_rejects_invalid_secret():
    from connector.clawscale_bridge.bind_service import BindService

    user_dao = type(
        "UserDAOStub",
        (),
        {
            "get_user_by_phone_number": lambda self, phone: {
                "_id": "user_1",
                "phone_number": phone,
                "bind_secret_hash": generate_password_hash("correct-secret"),
            }
        },
    )()

    service = BindService(
        user_dao=user_dao,
        external_identity_dao=None,
        binding_ticket_dao=None,
    )

    ok, reason = service.verify_account("13800138000", "wrong-secret")

    assert ok is False
    assert reason == "invalid_credentials"
