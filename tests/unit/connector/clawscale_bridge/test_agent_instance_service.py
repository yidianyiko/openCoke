from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest


def _service(*, instance=None, character=None):
    from connector.clawscale_bridge.agent_instance_service import AgentInstanceService

    dao = MagicMock()
    dao.get_active_agent_instance.return_value = instance
    dao.upsert_active_agent_instance.return_value = instance or {
        "agent_instance_id": "agentinst_1",
        "owner_user_id": "ck_1",
        "base_agent_type": "coke_companion",
        "base_character_id": "char_1",
        "active": True,
        "display_name": "沈妄",
        "nickname": None,
        "user_address_name": None,
        "persona": "custom persona",
        "background": None,
        "speaking_style": None,
        "extra_rules": None,
        "status": {"place": None, "action": None},
        "proactive": {"enabled": True},
        "memory": {"enabled": True},
        "created_at": datetime(2026, 5, 1, tzinfo=UTC),
        "updated_at": datetime(2026, 5, 22, tzinfo=UTC),
    }
    dao.reset_active_agent_instance.return_value = {
        "agent_instance_id": "agentinst_1",
        "owner_user_id": "ck_1",
        "base_agent_type": "coke_companion",
        "base_character_id": "char_1",
        "active": True,
        "display_name": None,
        "nickname": None,
        "user_address_name": None,
        "persona": None,
        "background": None,
        "speaking_style": None,
        "extra_rules": None,
        "status": {"place": None, "action": None},
        "proactive": {"enabled": None},
        "memory": {"enabled": None},
    }
    character_provider = MagicMock(
        return_value=character
        or {
            "_id": "char_1",
            "name": "kap",
            "nickname": "Coke",
            "user_info": {
                "description": "base prompt",
                "status": {"place": "工位", "action": "陪伴中"},
            },
        }
    )
    return (
        AgentInstanceService(dao=dao, character_provider=character_provider),
        dao,
        character_provider,
    )


def test_get_synthesizes_defaults_without_persisting_empty_instance():
    service, dao, character_provider = _service(instance=None)

    result = service.get_agent_instance(customer_id="ck_1")

    dao.get_active_agent_instance.assert_called_once_with(
        "ck_1", base_agent_type="coke_companion"
    )
    dao.upsert_active_agent_instance.assert_not_called()
    character_provider.assert_called_once()
    assert result["agent_instance"]["owner_user_id"] == "ck_1"
    assert result["agent_instance"]["display_name"] is None
    assert result["effective_profile"]["display_name"] == "Coke"
    assert result["effective_profile"]["status"] == {
        "place": "工位",
        "action": "陪伴中",
    }
    assert result["effective_profile"]["proactive"]["enabled"] is True


def test_get_preserves_trusted_identity_when_dao_returns_rogue_fields():
    service, _, _ = _service(
        instance={
            "agent_instance_id": "agentinst_rogue",
            "owner_user_id": "ck_attacker",
            "base_agent_type": "evil_companion",
            "base_character_id": "char_attacker",
            "active": False,
            "display_name": "沈妄",
        }
    )

    result = service.get_agent_instance(customer_id="ck_1")

    assert result["agent_instance"]["agent_instance_id"] == "agentinst_rogue"
    assert result["agent_instance"]["owner_user_id"] == "ck_1"
    assert result["agent_instance"]["base_agent_type"] == "coke_companion"
    assert result["agent_instance"]["base_character_id"] == "char_1"
    assert result["agent_instance"]["active"] is True
    assert result["agent_instance"]["display_name"] == "沈妄"


def test_update_rejects_unknown_and_identity_fields():
    service, dao, _ = _service(instance=None)

    with pytest.raises(ValueError) as exc:
        service.update_agent_instance(
            customer_id="ck_1",
            body={
                "display_name": "沈妄",
                "owner_user_id": "ck_attacker",
            },
        )

    assert str(exc.value) == "invalid_body"
    dao.upsert_active_agent_instance.assert_not_called()


def test_update_rejects_invalid_body_before_loading_base_character():
    service, dao, character_provider = _service(instance=None)

    with pytest.raises(ValueError) as exc:
        service.update_agent_instance(
            customer_id="ck_1",
            body={"display_name": "沈妄", "owner_user_id": "ck_attacker"},
        )

    assert str(exc.value) == "invalid_body"
    character_provider.assert_not_called()
    dao.upsert_active_agent_instance.assert_not_called()


def test_update_validates_lengths_and_nested_shapes():
    service, dao, _ = _service(instance=None)

    bad_payloads = [
        {"display_name": ""},
        {"display_name": "x" * 21},
        {"user_address_name": "x" * 11},
        {"status": {"place": "x" * 21, "action": "ok"}},
        {"status": {"place": "desk", "mood": "hidden"}},
        {"proactive": {"enabled": "yes"}},
        {"proactive": {"enabled": True, "x": True}},
        {"memory": {"enabled": "yes"}},
        {"memory": {"enabled": True, "x": True}},
        {"persona": "x" * 2001},
        {"background": "x" * 4001},
        {"speaking_style": "x" * 1001},
        {"extra_rules": "x" * 1001},
    ]

    for payload in bad_payloads:
        with pytest.raises(ValueError) as exc:
            service.update_agent_instance(customer_id="ck_1", body=payload)
        assert str(exc.value) == "invalid_body"

    dao.upsert_active_agent_instance.assert_not_called()


def test_update_merges_valid_overrides_and_keeps_base_type():
    service, dao, _ = _service(instance=None)
    dao.upsert_active_agent_instance.return_value["nickname"] = "阿妄"
    dao.upsert_active_agent_instance.return_value["proactive"] = {"enabled": False}

    result = service.update_agent_instance(
        customer_id="ck_1",
        body={
            "display_name": "沈妄",
            "nickname": "阿妄",
            "user_address_name": "姐姐",
            "persona": "custom persona",
            "status": {"place": "书桌", "action": "陪伴中"},
            "proactive": {"enabled": False},
            "memory": {"enabled": True},
        },
    )

    dao.upsert_active_agent_instance.assert_called_once()
    assert dao.upsert_active_agent_instance.call_args.args == (
        "ck_1",
        {
            "display_name": "沈妄",
            "nickname": "阿妄",
            "user_address_name": "姐姐",
            "persona": "custom persona",
            "status": {"place": "书桌", "action": "陪伴中"},
            "proactive": {"enabled": False},
            "memory": {"enabled": True},
        },
    )
    kwargs = dao.upsert_active_agent_instance.call_args.kwargs
    assert kwargs["base_character_id"] == "char_1"
    assert result["agent_instance"]["base_agent_type"] == "coke_companion"
    assert result["effective_profile"]["display_name"] == "沈妄"
    assert result["effective_profile"]["nickname"] == "阿妄"
    assert result["effective_profile"]["proactive"]["enabled"] is False


def test_update_response_uses_persisted_dao_result_not_request_body():
    service, dao, _ = _service(instance=None)
    dao.upsert_active_agent_instance.return_value = {
        "agent_instance_id": "agentinst_1",
        "owner_user_id": "ck_1",
        "base_agent_type": "coke_companion",
        "base_character_id": "char_1",
        "active": True,
        "display_name": "persisted name",
        "nickname": "persisted nickname",
        "user_address_name": None,
        "persona": None,
        "background": None,
        "speaking_style": None,
        "extra_rules": None,
        "status": {"place": None, "action": None},
        "proactive": {"enabled": True},
        "memory": {"enabled": True},
    }

    result = service.update_agent_instance(
        customer_id="ck_1",
        body={
            "display_name": "request name",
            "nickname": "request nickname",
        },
    )

    assert result["agent_instance"]["display_name"] == "persisted name"
    assert result["effective_profile"]["display_name"] == "persisted name"
    assert result["effective_profile"]["nickname"] == "persisted nickname"


def test_reset_clears_overrides_and_returns_effective_defaults():
    service, dao, _ = _service(instance=None)

    result = service.reset_agent_instance(customer_id="ck_1")

    dao.reset_active_agent_instance.assert_called_once_with(
        "ck_1",
        base_character_id="char_1",
        base_agent_type="coke_companion",
    )
    assert result["agent_instance"]["display_name"] is None
    assert result["effective_profile"]["display_name"] == "Coke"
