# -*- coding: utf-8 -*-
"""
主动消息（Future Message）Schema 定义

用于主动消息生成的响应模型，复用 ChatResponse 的大部分结构。

Requirements: FR-036, FR-038
"""

from typing import List, Optional
from pydantic import BaseModel, Field

from qiaoyun.agno_agent.schemas.chat_response_schema import (
    MultiModalResponse,
    RelationChangeModel,
    FutureResponseModel,
)


class FutureMessageResponse(BaseModel):
    """
    主动消息响应模型
    
    与 ChatResponse 结构类似，但用于主动消息场景。
    主动消息是角色在用户没有回复的情况下，主动发起的消息。
    """
    
    InnerMonologue: str = Field(
        default="",
        description="角色的内心独白"
    )
    
    MultiModalResponses: List[MultiModalResponse] = Field(
        default_factory=list,
        description="角色的回复，可能包含多种类型（text/voice/photo）"
    )
    
    ChatCatelogue: str = Field(
        default="否",
        description="在 MultiModalResponses 中是否涉及角色所熟悉的知识"
    )
    
    RelationChange: RelationChangeModel = Field(
        default_factory=RelationChangeModel,
        description="当下的关系变化"
    )
    
    FutureResponse: FutureResponseModel = Field(
        default_factory=FutureResponseModel,
        description="下一次主动消息的规划"
    )


__all__ = [
    "FutureMessageResponse",
]
