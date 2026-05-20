import importlib
import sys


def test_message_dispatcher_imports_without_access_gate_module(monkeypatch):
    sys.modules.pop("agent.runner.message_processor", None)
    sys.modules.pop("agent.runner.access_gate", None)
    monkeypatch.setitem(sys.modules, "agent.runner.access_gate", None)

    module = importlib.import_module("agent.runner.message_processor")

    dispatcher = module.MessageDispatcher("[T]")
    assert hasattr(dispatcher, "access_gate") is False


def test_message_dispatcher_does_not_block_on_legacy_dislike(monkeypatch):
    sys.modules.pop("agent.runner.message_processor", None)
    module = importlib.import_module("agent.runner.message_processor")
    dispatcher = module.MessageDispatcher("[T]")
    dispatcher.admin_user_id = "admin"

    context = {
        "user": {"id": "user-1"},
        "relation": {
            "relationship": {"dislike": 100},
            "character_info": {"status": "空闲"},
        },
    }
    msg_ctx = module.MessageContext(
        input_messages=[{"message": "hello"}],
        context=context,
        conversation={},
        lock_id="worker-1",
    )

    assert dispatcher.dispatch(msg_ctx) == ("normal", None)
