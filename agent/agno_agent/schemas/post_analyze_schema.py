# -*- coding: utf-8 -*-
"""
PostAnalyzeResponse Schema

定义 PostAnalyzeAgent 的输出格式，用于总结对话并更新用户/角色记忆。
"""

from typing import Optional
from pydantic import BaseModel, Field


class PostAnalyzeResponse(BaseModel):
    """PostAnalyzeAgent 的响应模型"""
    
    InnerMonologue: str = Field(
        default="",
        description="角色的内心独白"
    )
    
    CharacterPublicSettings: str = Field(
        default="无",
        description="总结最新聊天消息中，针对角色所新增的人物设定。你可以总结出1条或者多条信息，每条消息为一行；使用'key：value'的形式，例如 xxx-xxx-xxx：xxxxxx。"
    )
    
    CharacterPrivateSettings: str = Field(
        default="无",
        description="总结最新聊天消息中，针对角色所新增的不可公开人物设定。你可以总结出1条或者多条信息，每条消息为一行；使用'key：value'的形式，例如 xxx-xxx-xxx：xxxxxx。"
    )
    
    CharacterKnowledges: str = Field(
        default="无",
        description="总结最新聊天消息中，角色所新增的知识或技能点。你可以总结出1条或者多条信息，每条消息为一行；使用'key：value'的形式，例如 xxx-xxx-xxx：xxxxxx。"
    )
    
    UserSettings: str = Field(
        default="无",
        description="总结最新聊天消息中，针对用户所新增的人物设定。你可以总结出1条或者多条信息，每条消息为一行；使用'key：value'的形式，例如 xxx-xxx-xxx：xxxxxx。"
    )
    
    UserRealName: str = Field(
        default="无",
        description="总结最新聊天消息中，角色所了解到的用户的真名。如果没有，你需要输出'无'。"
    )
    
    UserHobbyName: str = Field(
        default="无",
        description="总结最新聊天消息中，双方约定的给用户的昵称。如果没有，你需要输出'无'。"
    )
    
    UserDescription: str = Field(
        default="无",
        description="总结最新聊天消息中，角色对用户的印象描述。你需要结合'参考上下文'中的印象描述，进行更新。最多不超过100字。"
    )
    
    CharacterPurpose: str = Field(
        default="无",
        description="总结最新聊天消息中，角色的短期目标，可能跟多轮聊天有关，也可能无关。"
    )
    
    CharacterAttitude: str = Field(
        default="无",
        description="总结最新聊天消息中，角色对用户的态度。"
    )
    
    RelationDescription: str = Field(
        default="无",
        description="总结最新聊天消息中，角色和用户的关系变化。如果没有变化，你应该输出原关系。"
    )
    
    Dislike: Optional[int] = Field(
        default=0,
        description="总结最新聊天消息中，角色对用户的的反感度数值变化。如果更加反感了，应该输出正整数。"
    )
