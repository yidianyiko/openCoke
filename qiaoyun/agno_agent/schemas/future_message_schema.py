# -*- coding: utf-8 -*-
"""
主动消息（Future Message）Schema 定义

用于主动消息生成的响应模型，复用 ChatResponse 的大部分结构。

Requirements: FR-036, FR-038
Design: Property 1 - Schema 结构完整性
"""

from typing import List
from pydantic import BaseModel, Field, field_validator

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
    
    Requirements:
    - 1.1: 包含 InnerMonologue、MultiModalResponses、RelationChange、FutureResponse 字段
    - 1.2: FutureResponse 包含 FutureResponseTime 和 FutureResponseAction 子字段
    - 1.3: MultiModalResponse 支持 text、voice、photo 三种消息类型
    """
    
    InnerMonologue: str = Field(
        default="",
        description="角色的内心独白，描述角色在发送主动消息时的心理活动"
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
        description="当下的关系变化，包含 Closeness（亲密度）和 Trustness（信任度）的变化值"
    )
    
    FutureResponse: FutureResponseModel = Field(
        default_factory=FutureResponseModel,
        description="下一次主动消息的规划，包含 FutureResponseTime（触发时间）和 FutureResponseAction（规划行动）"
    )
    
    @field_validator('MultiModalResponses', mode='before')
    @classmethod
    def validate_multimodal_responses(cls, v):
        """确保 MultiModalResponses 是列表类型"""
        if v is None:
            return []
        return v
    
    @field_validator('RelationChange', mode='before')
    @classmethod
    def validate_relation_change(cls, v):
        """确保 RelationChange 有默认值"""
        if v is None:
            return RelationChangeModel()
        return v
    
    @field_validator('FutureResponse', mode='before')
    @classmethod
    def validate_future_response(cls, v):
        """确保 FutureResponse 有默认值"""
        if v is None:
            return FutureResponseModel()
        return v


__all__ = [
    "FutureMessageResponse",
]
