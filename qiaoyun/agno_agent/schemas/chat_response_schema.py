# -*- coding: utf-8 -*-
"""
ChatResponse Schema

定义 ChatResponseAgent 的输出格式，包含多模态回复、关系变化、未来消息规划等。
"""

from typing import List, Optional, Literal
from pydantic import BaseModel, Field


class MultiModalResponse(BaseModel):
    """多模态回复项"""
    
    type: Literal["text", "voice"] = Field(
        description="消息的类型"
    )
    
    content: str = Field(
        description="根据消息类型的不同，包含不同的内容"
    )
    
    emotion: Optional[Literal["无", "高兴", "悲伤", "愤怒", "害怕", "惊讶", "厌恶", "魅惑"]] = Field(
        default="无",
        description="仅对语音消息有效，表示语音的感情色彩"
    )


class RelationChangeModel(BaseModel):
    """关系变化模型"""
    
    Closeness: float = Field(
        default=0,
        description="亲密度数值变化"
    )
    
    Trustness: float = Field(
        default=0,
        description="信任度数值变化"
    )


class FutureResponseModel(BaseModel):
    """未来消息规划模型"""
    
    FutureResponseTime: str = Field(
        default="",
        description="未来主动的消息时间，格式为xxxx年xx月xx日xx时xx分。"
    )
    
    FutureResponseAction: str = Field(
        default="无",
        description="未来主动消息的大致内容，大约10-20个字。"
    )


class ChatResponse(BaseModel):
    """ChatResponseAgent 的响应模型"""
    
    InnerMonologue: str = Field(
        default="",
        description="角色的内心独白"
    )
    
    MultiModalResponses: List[MultiModalResponse] = Field(
        default_factory=list,
        description="角色的回复，可能包含多种类型。"
    )
    
    ChatCatelogue: str = Field(
        default="",
        description="在MultiModalResponses当中是否涉及角色所熟悉的知识，或者涉及她的专业知识，或者她的一些人设和故事。"
    )
    
    RelationChange: RelationChangeModel = Field(
        default_factory=RelationChangeModel,
        description="当下的关系变化"
    )
    
    FutureResponse: FutureResponseModel = Field(
        default_factory=FutureResponseModel,
        description="假设用户在此之后一直没有任何回复，角色在未来什么时间可能进行再次的未来主动消息"
    )
