# -*- coding: utf-8 -*-
"""
Album tool adapters for Agno Agent.
"""

from __future__ import annotations

from agno.tools import tool

from agent.agno_agent.capabilities.album import AlbumCapabilityPort


@tool(description="删除指定照片")
def photo_delete_tool(photo_id: str) -> dict:
    """
    照片删除工具
    """
    result = AlbumCapabilityPort().run(
        "",
        None,
        {"action": "delete_photo", "photo_id": photo_id},
    )
    return dict(result.content)


__all__ = ["photo_delete_tool"]
