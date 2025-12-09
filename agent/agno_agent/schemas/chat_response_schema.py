# -*- coding: utf-8 -*-
"""
ChatResponse Schema

定义 ChatResponseAgent 的输出格式。

V2 重构：
- 移除 RelationChange 和 FutureResponse，这些职责移至 PostAnalyzeResponse
- ChatResponseAgent 专注于生成高质量的多模态回复
"""

from typing import List, Optional, Literal
from pydantic import BaseModel, Field


class MultiModalResponse(BaseModel):
    """多模态回复项"""
    
    type: Literal["text", "voice", "photo"] = Field(
        description="消息的类型：text（文本）、voice（语音）、photo（图片）"
    )
    
    content: str = Field(
        default="",
        description="根据消息类型的不同，包含不同的内容"
    )
    
    emotion: Optional[Literal["无", "高兴", "悲伤", "愤怒", "害怕", "惊讶", "厌恶", "魅惑"]] = Field(
        default=None,
        description="仅对语音消息有效，表示语音的感情色彩"
    )


# 保留这些模型定义供其他模块使用（如 PostAnalyzeResponse）
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
    """
    ChatResponseAgent 的响应模型 - 精简版
    
    专注于生成多模态回复，不再包含关系变化和未来规划。
    这些分析任务移至 PostAnalyzeResponse，基于完整对话结果进行计算。
    """
    
    InnerMonologue: str = Field(
        default="",
        description="角色的内心独白（用于调试和理解推理过程）"
    )
    
    MultiModalResponses: List[MultiModalResponse] = Field(
        default_factory=list,
        description="角色的多模态回复，可能包含多种类型（text/voice/photo）"
    )
    
    ChatCatelogue: str = Field(
        default="",
        description="回复涉及的知识分类（角色知识、专业知识、人设故事等）"
    )
    
    # 已移除：RelationChange -> PostAnalyzeResponse
    # 已移除：FutureResponse -> PostAnalyzeResponse
