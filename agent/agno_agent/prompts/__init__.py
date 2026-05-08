__all__ = ["build_manager_input", "build_manager_instructions"]


def __getattr__(name: str):
    if name not in __all__:
        raise AttributeError(name)
    from agent.agno_agent.prompts.manager import (
        build_manager_input,
        build_manager_instructions,
    )

    return {
        "build_manager_input": build_manager_input,
        "build_manager_instructions": build_manager_instructions,
    }[name]
