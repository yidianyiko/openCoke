from agent.agno_agent.runtime.selector import RuntimeSelectionInput, select_runtime


def test_explicit_override_wins_over_env(monkeypatch):
    monkeypatch.setenv("AGENT_RUNTIME_VERSION", "legacy")
    selected = select_runtime(
        RuntimeSelectionInput(
            explicit_override="team",
            conversation_override=None,
            customer_override=None,
        )
    )

    assert selected == "team"


def test_conversation_override_wins_over_customer_and_env(monkeypatch):
    monkeypatch.setenv("AGENT_RUNTIME_VERSION", "legacy")
    selected = select_runtime(
        RuntimeSelectionInput(
            explicit_override=None,
            conversation_override="team",
            customer_override="legacy",
        )
    )

    assert selected == "team"


def test_customer_override_wins_over_env(monkeypatch):
    monkeypatch.setenv("AGENT_RUNTIME_VERSION", "legacy")
    selected = select_runtime(
        RuntimeSelectionInput(
            explicit_override=None,
            conversation_override=None,
            customer_override="team",
        )
    )

    assert selected == "team"


def test_env_default_is_used(monkeypatch):
    monkeypatch.setenv("AGENT_RUNTIME_VERSION", "team")
    selected = select_runtime(RuntimeSelectionInput())

    assert selected == "team"


def test_invalid_values_fall_back_to_legacy(monkeypatch):
    monkeypatch.setenv("AGENT_RUNTIME_VERSION", "banana")
    selected = select_runtime(RuntimeSelectionInput())

    assert selected == "legacy"


def test_invalid_higher_precedence_value_falls_through_to_valid_candidate(monkeypatch):
    monkeypatch.setenv("AGENT_RUNTIME_VERSION", "legacy")
    selected = select_runtime(
        RuntimeSelectionInput(
            explicit_override="TEAM",
            conversation_override="team",
            customer_override="legacy",
        )
    )

    assert selected == "team"
