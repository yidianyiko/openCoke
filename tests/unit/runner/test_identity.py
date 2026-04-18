from agent.runner.identity import (
    get_agent_entity_id,
    is_synthetic_coke_account_id,
    resolve_agent_user_context,
)


def test_resolve_agent_user_context_loads_mongo_user_and_sets_canonical_id():
    object_id = "507f1f77bcf86cd799439011"
    loaded_user = {
        "_id": object_id,
        "display_name": "Alice",
    }

    class FakeUserDAO:
        def get_user_by_id(self, user_id):
            assert user_id == object_id
            return dict(loaded_user)

    user = resolve_agent_user_context(
        user_id=object_id,
        input_message={"platform": "wechat", "metadata": {}},
        user_dao=FakeUserDAO(),
    )

    assert user == {
        "_id": object_id,
        "id": object_id,
        "display_name": "Alice",
    }


def test_resolve_agent_user_context_builds_synthetic_coke_account_user():
    class FakeUserDAO:
        def get_user_by_id(self, user_id):
            raise AssertionError("DAO lookup should not happen for synthetic CokeAccount users")

    user = resolve_agent_user_context(
        user_id="acct_123",
        input_message={
            "platform": "business",
            "metadata": {
                "source": "clawscale",
                "coke_account": {
                    "id": "acct_123",
                    "display_name": "Gateway Alice",
                },
            },
        },
        user_dao=FakeUserDAO(),
    )

    assert user == {
        "id": "acct_123",
        "_id": "acct_123",
        "nickname": "Gateway Alice",
        "is_coke_account": True,
    }
    assert get_agent_entity_id(user) == "acct_123"


def test_resolve_agent_user_context_builds_synthetic_user_without_coke_account():
    class FakeUserDAO:
        def get_user_by_id(self, user_id):
            raise AssertionError("DAO lookup should not happen for synthetic CokeAccount users")

    user = resolve_agent_user_context(
        user_id="acct_456789",
        input_message={
            "platform": "business",
            "metadata": {
                "source": "clawscale",
                "sender": "Gateway Sender",
            },
        },
        user_dao=FakeUserDAO(),
    )

    assert user == {
        "id": "acct_456789",
        "_id": "acct_456789",
        "nickname": "Gateway Sender",
        "is_coke_account": True,
    }


def test_resolve_agent_user_context_uses_default_nickname_fallback():
    class FakeUserDAO:
        def get_user_by_id(self, user_id):
            raise AssertionError("DAO lookup should not happen for synthetic CokeAccount users")

    user = resolve_agent_user_context(
        user_id="acct_123456789",
        input_message={
            "platform": "business",
            "metadata": {
                "source": "clawscale",
            },
        },
        user_dao=FakeUserDAO(),
    )

    assert user == {
        "id": "acct_123456789",
        "_id": "acct_123456789",
        "nickname": "user-456789",
        "is_coke_account": True,
    }


def test_resolve_agent_user_context_prefers_customer_metadata_for_ck_ids():
    class FakeUserDAO:
        def get_user_by_id(self, user_id):
            raise AssertionError("DAO lookup should not happen for synthetic customer users")

    user = resolve_agent_user_context(
        user_id="ck_123",
        input_message={
            "platform": "business",
            "metadata": {
                "source": "clawscale",
                "customer": {
                    "id": "ck_123",
                    "display_name": "Gateway Customer",
                },
            },
        },
        user_dao=FakeUserDAO(),
    )

    assert user == {
        "id": "ck_123",
        "_id": "ck_123",
        "nickname": "Gateway Customer",
        "is_coke_account": True,
    }
    assert is_synthetic_coke_account_id("ck_123") is True


def test_resolve_agent_user_context_prefers_business_account_lookup_when_auth_user_is_gone():
    object_id = "507f1f77bcf86cd799439011"

    class FakeUserDAO:
        def get_user_by_id(self, user_id):
            assert user_id == object_id
            return None

        def get_user_by_account_id(self, account_id):
            assert account_id == "acct_123"
            return {
                "account_id": "acct_123",
                "display_name": "Alice",
                "timezone": "Asia/Tokyo",
            }

    user = resolve_agent_user_context(
        user_id=object_id,
        input_message={
            "platform": "business",
            "metadata": {
                "source": "clawscale",
                "customer": {
                    "id": "acct_123",
                    "display_name": "Gateway Alice",
                },
            },
        },
        user_dao=FakeUserDAO(),
    )

    assert user == {
        "account_id": "acct_123",
        "display_name": "Alice",
        "timezone": "Asia/Tokyo",
        "id": "acct_123",
        "_id": "acct_123",
    }


def test_resolve_agent_user_context_keeps_synthetic_account_id_when_metadata_disagrees():
    class FakeUserDAO:
        def get_user_by_account_id(self, account_id):
            assert account_id == "acct_123"
            return {
                "account_id": "acct_123",
                "display_name": "Alice",
            }

    user = resolve_agent_user_context(
        user_id="acct_123",
        input_message={
            "platform": "business",
            "metadata": {
                "source": "clawscale",
                "customer": {
                    "id": "acct_other",
                    "display_name": "Wrong Customer",
                },
                "coke_account": {
                    "id": "acct_other",
                    "display_name": "Wrong Coke Account",
                },
            },
        },
        user_dao=FakeUserDAO(),
    )

    assert user == {
        "account_id": "acct_123",
        "display_name": "Alice",
        "id": "acct_123",
        "_id": "acct_123",
    }
