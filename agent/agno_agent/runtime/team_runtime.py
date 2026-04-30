from __future__ import annotations

from typing import Any

from agno.team import Team


def create_manager_team(*, model: Any, members: list[Any]) -> Team:
    return Team(
        name="CokeManagerTeam",
        model=model,
        members=members,
        tools=[],
        db=None,
        add_session_state_to_context=False,
        enable_agentic_state=False,
        cache_session=False,
    )
