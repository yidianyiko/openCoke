# -*- coding: utf-8 -*-
"""Compatibility shim for the post-analyze runtime extraction."""

from typing import Any

from agent.agno_agent.runtime.post_analyze import run_post_analyze


class PostAnalyzeWorkflow:
    """Temporary runner-compatible shim until Phase 6 rewires the call site."""

    async def run(self, session_state: dict[str, Any] | None = None) -> None:
        await run_post_analyze(session_state or {})
