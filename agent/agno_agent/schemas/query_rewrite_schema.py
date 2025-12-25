# -*- coding: utf-8 -*-
"""
QueryRewriteResponse Schema

定义 QueryRewriteAgent 的输出格式，用于语义理解和生成检索查询词.
"""

from pydantic import BaseModel, Field


class QueryRewriteResponse(BaseModel):
    """QueryRewriteAgent 的响应模型"""

    InnerMonologue: str = Field(default="", description="角色的内心独白")

    CharacterSettingQueryQuestion: str = Field(
        default="", description="你认为针对角色人物设定需要进行的查询语句，不要为空."
    )

    CharacterSettingQueryKeywords: str = Field(
        default="", description="你认为针对角色人物设定需要进行的查询关键词，不要为空."
    )

    UserProfileQueryQuestion: str = Field(
        default="", description="你认为针对用户资料需要进行的查询语句，不要为空."
    )

    UserProfileQueryKeywords: str = Field(
        default="", description="你认为针对用户资料需要进行的查询关键词，不要为空."
    )

    CharacterKnowledgeQueryQuestion: str = Field(
        default="",
        description="你认为针对角色的知识与技能需要进行的查询语句，不要为空.",
    )

    CharacterKnowledgeQueryKeywords: str = Field(
        default="",
        description="你认为针对角色的知识与技能需要进行的查询关键词，不要为空.",
    )
