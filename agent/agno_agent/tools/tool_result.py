"""Utility for tools to record their execution results into session_state."""
from __future__ import annotations


def append_tool_result(
    session_state: dict,
    *,
    tool_name: str,
    ok: bool,
    result_summary: str,
    extra_notes: str = "",
) -> None:
    """Append one tool result entry to session_state["tool_results"].

    Safe to call multiple times per request — results accumulate.
    ChatResponseAgent reads the full list via get_tool_results_context().
    """
    if "tool_results" not in session_state:
        session_state["tool_results"] = []
    session_state["tool_results"].append(
        {
            "tool_name": tool_name,
            "ok": ok,
            "result_summary": result_summary,
            "extra_notes": extra_notes,
        }
    )
