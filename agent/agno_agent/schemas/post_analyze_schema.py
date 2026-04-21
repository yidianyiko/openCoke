# -*- coding: utf-8 -*-
"""PostAnalyzeResponse Schema."""

from typing import Optional

from pydantic import BaseModel, Field

from agent.agno_agent.schemas.chat_response_schema import RelationChangeModel


class FollowupPlanModel(BaseModel):
    """Internal proactive follow-up planning payload."""

    FollowupAction: str = Field(
        default="clear",
        description="Internal follow-up action: create | replace | clear",
    )
    FollowupTime: str = Field(
        default="",
        description="Future proactive follow-up time, format xxxx年xx月xx日xx时xx分.",
    )
    FollowupPrompt: str = Field(
        default="无",
        description="Rough content for the next proactive follow-up.",
    )


class PostAnalyzeResponse(BaseModel):
    """
     PostAnalyzeAgent 的响应模型-扩展版

     V2 重构后承担更多分析职责：
    -关系变化分析（从 ChatResponse 移入）
    -未来消息规划（从 ChatResponse 移入）
    -记忆更新（原有职责）
    """

    InnerMonologue: str = Field(default="", description="角色的内心独白")

    # ===== 新增：关系变化（从 ChatResponse 移入）=====
    RelationChange: RelationChangeModel = Field(
        default_factory=RelationChangeModel,
        description="本轮对话的关系变化（亲密度/信任度数值变化）",
    )

    FollowupPlan: FollowupPlanModel = Field(
        default_factory=FollowupPlanModel,
        description="Internal proactive follow-up planning payload",
    )

    # ===== 原有字段：记忆更新 =====
    CharacterPublicSettings: str = Field(
        default="无",
        description="总结最新聊天消息中，针对角色所新增的人物设定.你可以总结出1条或者多条信息，每条消息为一行；使用'key：value'的形式，例如 xxx-xxx-xxx：xxxxxx.",
    )

    CharacterPrivateSettings: str = Field(
        default="无",
        description="总结最新聊天消息中，针对角色所新增的不可公开人物设定.你可以总结出1条或者多条信息，每条消息为一行；使用'key：value'的形式，例如 xxx-xxx-xxx：xxxxxx.",
    )

    CharacterKnowledges: str = Field(
        default="无",
        description="总结最新聊天消息中，角色所新增的知识或技能点.你可以总结出1条或者多条信息，每条消息为一行；使用'key：value'的形式，例如 xxx-xxx-xxx：xxxxxx.",
    )

    UserSettings: str = Field(
        default="无",
        description="总结最新聊天消息中，针对用户所新增的人物设定.你可以总结出1条或者多条信息，每条消息为一行；使用'key：value'的形式，例如 xxx-xxx-xxx：xxxxxx.",
    )

    UserRealName: str = Field(
        default="无",
        description="总结最新聊天消息中，角色所了解到的用户的真名.如果没有，你需要输出'无'.",
    )

    UserHobbyName: str = Field(
        default="无",
        description="总结最新聊天消息中，双方约定的给用户的昵称.如果没有，你需要输出'无'.",
    )

    UserDescription: str = Field(
        default="无",
        description="总结最新聊天消息中，角色对用户的印象描述.你需要结合'参考上下文'中的印象描述，进行更新.最多不超过100字.",
    )

    CharacterLongtermPurpose: str = Field(
        default="无",
        description="总结角色对用户的长期目标.这是一个持续性的目标，通常不会频繁变化，例如'帮助用户实现生活目标'、'成为用户的知心朋友'等.如果本次对话中没有体现出长期目标的变化，输出'无'.",
    )

    CharacterPurpose: str = Field(
        default="无",
        description="总结最新聊天消息中，角色的短期目标，可能跟多轮聊天有关，也可能无关.例如'了解用户的兴趣爱好'、'帮用户解决当前问题'等.",
    )

    CharacterAttitude: str = Field(
        default="无", description="总结最新聊天消息中，角色对用户的态度."
    )

    RelationDescription: str = Field(
        default="无",
        description="总结最新聊天消息中，角色和用户的关系变化.如果没有变化，你应该输出原关系.",
    )

    Dislike: Optional[int] = Field(
        default=0,
        description="总结最新聊天消息中，角色对用户的的反感度数值变化.如果更加反感了，应该输出正整数.",
    )
