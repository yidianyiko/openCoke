import sys
import types


def _install_fake_agno_team(monkeypatch):
    team_mod = types.ModuleType("agno.team")

    class FakeTeam:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.name = kwargs.get("name")
            self.model = kwargs.get("model")
            self.members = kwargs.get("members")
            self.db = kwargs.get("db")
            self.add_session_state_to_context = kwargs.get(
                "add_session_state_to_context"
            )
            self.enable_agentic_state = kwargs.get("enable_agentic_state")
            self.cache_session = kwargs.get("cache_session")
            self.tools = kwargs.get("tools")

    team_mod.Team = FakeTeam
    monkeypatch.setitem(sys.modules, "agno.team", team_mod)


def test_team_runtime_disables_agno_persistent_state(monkeypatch):
    _install_fake_agno_team(monkeypatch)
    from agent.agno_agent.runtime.team_runtime import create_manager_team

    team = create_manager_team(model=object(), members=[])

    assert team.db is None
    assert team.add_session_state_to_context is False
    assert team.enable_agentic_state is False
    assert team.cache_session is False


def test_team_runtime_does_not_register_durable_write_tools(monkeypatch):
    _install_fake_agno_team(monkeypatch)
    from agent.agno_agent.runtime.team_runtime import create_manager_team

    team = create_manager_team(model=object(), members=[])

    assert team.tools == []


def test_team_runtime_forwards_manager_identity_and_members(monkeypatch):
    _install_fake_agno_team(monkeypatch)
    from agent.agno_agent.runtime.team_runtime import create_manager_team

    model = object()
    members = [object(), object()]

    team = create_manager_team(model=model, members=members)

    assert team.name == "CokeManagerTeam"
    assert team.model is model
    assert team.members is members
