# -*- coding: utf-8 -*-
"""
OrchestratorResponse Schema

定义 OrchestratorAgent 的输出格式，用于智能调度决策。
V2 架构核心组件。
"""

from pydantic import BaseModel, Field


class ContextRetrieveParams(BaseModel):
    """上下文检索参数"""
    
    character_setting_query: str = Field(
        default="",
        description="角色设定检索语句，使用'xxx-xxx'层级格式，如'日常习惯-作息'"
    )
    
    character_setting_keywords: str = Field(
        default="",
        description="角色设定关键词，逗号分隔，每个词不超过4字"
    )
    
    user_profile_query: str = Field(
        default="",
        description="用户资料检索语句"
    )
    
    user_profile_keywords: str = Field(
        default="",
        description="用户资料关键词，逗号分隔"
    )
    
    character_knowledge_query: str = Field(
        default="",
        description="角色知识检索语句"
    )
    
    character_knowledge_keywords: str = Field(
        default="",
        description="角色知识关键词，逗号分隔"
    )


class OrchestratorResponse(BaseModel):
    """
    OrchestratorAgent 输出模型
    
    职责：
    1. 语义理解 - 理解用户意图，生成检索参数
    2. 意图识别 - 识别是否包含提醒、查询等特殊意图
    3. 调度决策 - 决定需要调用哪些 Tool/Agent
    """
    
    # 内心独白
    inner_monologue: str = Field(
        default="",
        description="角色的内心独白，理解用户意图的思考过程"
    )
    
    # 上下文检索决策
    need_context_retrieve: bool = Field(
        default=True,
        description="是否需要检索上下文。默认为 true，仅当用户消息是纯提醒操作时设为 false"
    )
    
    context_retrieve_params: ContextRetrieveParams = Field(
        default_factory=ContextRetrieveParams,
        description="上下文检索参数"
    )
    
    # 提醒决策（只决定是否需要调用 ReminderDetectAgent，不生成具体参数）
    need_reminder_detect: bool = Field(
        default=False,
        description="是否需要调用提醒检测Agent。当用户消息包含提醒相关关键词时设为 true"
    )
