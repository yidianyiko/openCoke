import importlib
import sys


def test_message_dispatcher_imports_without_access_gate_module(monkeypatch):
    sys.modules.pop("agent.runner.message_processor", None)
    sys.modules.pop("agent.runner.access_gate", None)
    monkeypatch.setitem(sys.modules, "agent.runner.access_gate", None)

    module = importlib.import_module("agent.runner.message_processor")

    dispatcher = module.MessageDispatcher("[T]")
    assert hasattr(dispatcher, "access_gate") is False
