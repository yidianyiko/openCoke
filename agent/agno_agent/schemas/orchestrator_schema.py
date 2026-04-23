# -*- coding: utf-8 -*-
"""
OrchestratorResponse Schema

定义 OrchestratorAgent 的输出格式，用于智能调度决策.
V2 架构核心组件.

设计原则：
- Schema Field.description 负责格式约束（字段类型、格式要求、示例）
- Instructions 负责决策逻辑（什么时候设 true/false）
"""

from pydantic import BaseModel, Field


class ContextRetrieveParams(BaseModel):
    """上下文检索参数"""

    character_setting_query: str = Field(
        default="",
        description=(
            "角色设定检索语句。"
            "格式：使用'xxx-xxx'层级格式。"
            "示例：'日常习惯-作息'、'性格特点-社交'、'兴趣爱好-运动'"
        ),
    )

    character_setting_keywords: str = Field(
        default="",
        description=(
            "角色设定检索关键词。"
            "格式：逗号分隔，每个词不超过4字。"
            "示例：'习惯,作息,睡眠'、'性格,社交,朋友'"
        ),
    )

    user_profile_query: str = Field(
        default="",
        description=(
            "用户资料检索语句。"
            "格式：使用'xxx-xxx'层级格式。"
            "示例：'个人信息-职业'、'兴趣爱好-音乐'"
        ),
    )

    user_profile_keywords: str = Field(
        default="",
        description=(
            "用户资料检索关键词。"
            "格式：逗号分隔，每个词不超过4字。"
            "示例：'工作,职业,公司'"
        ),
    )

    character_knowledge_query: str = Field(
        default="",
        description=(
            "角色知识检索语句，用于检索角色的专业知识或技能。"
            "格式：使用'xxx-xxx'层级格式。"
            "示例：'专业知识-烹饪'、'技能-绘画'"
        ),
    )

    character_knowledge_keywords: str = Field(
        default="",
        description=(
            "角色知识检索关键词。"
            "格式：逗号分隔，每个词不超过4字。"
            "示例：'烹饪,食谱,做饭'"
        ),
    )

    chat_history_query: str = Field(
        default="",
        description=(
            "历史对话检索语句，用于找回与当前话题相关的过往对话。"
            "格式：自然语言描述。"
            "示例：'上次聊到的旅行计划'、'之前讨论的工作问题'"
        ),
    )

    chat_history_keywords: str = Field(
        default="",
        description=(
            "历史对话检索关键词。"
            "格式：逗号分隔，每个词不超过4字。"
            "示例：'旅行,计划,度假'"
        ),
    )


class OrchestratorResponse(BaseModel):
    """
    OrchestratorAgent 输出模型

    职责：
    1. 语义理解 - 理解用户意图，生成检索参数
    2. 意图识别 - 识别是否包含提醒、查询等特殊意图
    3. 调度决策 - 决定需要调用哪些 Tool/Agent
    """

    inner_monologue: str = Field(
        default="",
        description=(
            "角色的内心独白，推测用户意图的思考过程。"
            "长度：20-50字。"
            "示例：'用户想设置一个明天早上的提醒，需要调用提醒检测'"
        ),
    )

    need_context_retrieve: bool = Field(
        default=True,
        description=(
            "是否需要检索上下文。"
            "默认：true。"
            "何时设为 false：纯提醒操作（取消/查看/删除提醒）"
        ),
    )

    context_retrieve_params: ContextRetrieveParams = Field(
        default_factory=ContextRetrieveParams,
        description="上下文检索参数，当 need_context_retrieve 为 true 时填写",
    )

    need_reminder_detect: bool = Field(
        default=False,
        description=(
            "是否需要调用提醒检测 Agent。"
            "默认：false。"
            "何时设为 true：用户表达提醒相关意图（创建/修改/删除/查看提醒）"
        ),
    )

    need_web_search: bool = Field(
        default=False,
        description=(
            "是否需要联网搜索。"
            "默认：false。"
            "何时设为 true：用户询问实时信息（天气、新闻、股价）或外部世界的事实"
        ),
    )

    web_search_query: str = Field(
        default="",
        description=(
            "联网搜索的关键词。"
            "格式：简洁的搜索词，中英文皆可。"
            "示例：'杭州今天天气'、'特斯拉最新股价'、'2024世界杯'"
        ),
    )

    need_timezone_update: bool = Field(
        default=False,
        description=(
            "是否需要更新用户时区。"
            "默认：false。"
            "何时设为 true：用户提到自己所在城市/国家/地区，或明确要求切换时区"
        ),
    )

    timezone_action: str = Field(
        default="none",
        description=(
            "时区动作类型。"
            "可选值：none、direct_set、proposal。"
            "direct_set 表示用户明确要求立即切换时区；"
            "proposal 表示检测到新的时区信号，需要先征求确认。"
        ),
    )

    timezone_value: str = Field(
        default="",
        description=(
            "用户所在地对应的 IANA 时区名称。"
            "当 need_timezone_update=true 或 timezone_action 不为 none 时填写。"
            "示例：'America/New_York'、'Asia/Tokyo'、'Europe/London'"
        ),
    )
