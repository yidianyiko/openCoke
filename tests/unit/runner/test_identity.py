from agent.runner.identity import (
    get_agent_entity_id,
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
