# -*- coding: utf-8 -*-
"""
PostAnalyzeWorkflow-后处理分析 Workflow

总结对话，更新用户 / 角色记忆，并规划内部 follow-up。

V2.5 更新：
- 新增 character_info 更新：CharacterPurpose → shortterm_purpose, CharacterAttitude → attitude
- 新增 user_info 更新：UserRealName → realname, UserHobbyName → hobbyname, UserDescription → description
- 新增 relationship 更新：RelationDescription → description, Dislike → dislike
- 修复了 PostAnalyze 输出字段与 relation 存储字段之间的映射缺失问题

V2.8 更新：
- 新增 RelationDescription 压缩机制：当描述超过阈值时，调用 LLM 进行摘要压缩

V2.11 更新：
- 解耦旧 follow-up 规划：当本轮已创建定时提醒时，跳过内部 follow-up 的 prompt 和处理
- 新增 get_post_analyze_prompt 动态生成 prompt，减少不必要的 token 消耗

Requirements: 5.3
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

from agent.agno_agent.agents import post_analyze_agent
from agent.agno_agent.model_factory import create_llm_model
from agent.agno_agent.tools.deferred_action.service import DeferredActionService
from agent.agno_agent.utils.usage_tracker import usage_tracker
from agent.prompt.chat_contextprompt import (
    CONTEXTPROMPT_人物资料,
    CONTEXTPROMPT_当前的人物关系,
    CONTEXTPROMPT_时间,
    CONTEXTPROMPT_最新聊天消息_双方,
    CONTEXTPROMPT_用户资料,
)
from agent.prompt.rendering import render_prompt_template
from agent.prompt.chat_taskprompt import (
    TASKPROMPT_总结,
    get_post_analyze_prompt,
)
from util.time_util import get_default_timezone, str2timestamp

logger = logging.getLogger(__name__)


class PostAnalyzeWorkflow:
    """
     后处理 Workflow：总结对话，更新记忆

     注意：这是自定义 Workflow 类，不继承 Agno Workflow.

     执行流程：
     1. 渲染 user prompt（包含最新聊天消息和回复）
     2. 调用 PostAnalyzeAgent 进行后处理分析
     3. 返回分析结果（用于更新用户/角色记忆）

     输入：
    -session_state["MultiModalResponses"]-来自 ChatWorkflow 的回复
    -session_state["context_retrieve"]-来自 PrepareWorkflow

     输出：
    -CharacterPublicSettings-角色公开设定更新
    -CharacterPrivateSettings-角色私有设定更新
    -UserSettings-用户资料更新
    -UserRealName-用户真名
    -RelationDescription-关系描述更新

     V2.11 更新：
    -支持动态跳过 internal follow-up planning（当 reminder_created_with_time=True 时）
    """

    # User prompt 模板组合（静态部分）
    # V2.11: 推理要求部分改为动态生成，见 _build_userp_template
    userp_template_prefix = (
        TASKPROMPT_总结
        + CONTEXTPROMPT_时间
        + CONTEXTPROMPT_人物资料
        + CONTEXTPROMPT_用户资料
        + CONTEXTPROMPT_当前的人物关系
        + CONTEXTPROMPT_最新聊天消息_双方
    )

    def _build_userp_template(self, session_state: Dict[str, Any]) -> str:
        """
        V2.11 新增：动态构建 user prompt 模板

        根据 session_state 中的标志决定是否包含 internal follow-up planning 部分

        Args:
            session_state: 会话状态

        Returns:
            组装后的 prompt 模板
        """
        skip_future_response = session_state.get("reminder_created_with_time", False)

        if skip_future_response:
            logger.info(
                "[PostAnalyzeWorkflow] 检测到 reminder_created_with_time=True，跳过 internal follow-up prompt"
            )

        return self.userp_template_prefix + get_post_analyze_prompt(
            skip_future_response
        )

    async def run(
        self, session_state: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        异步执行后处理分析

        V2 重构：新增 RelationChange 和 internal follow-up 处理
        V2.11 更新：支持动态跳过 internal follow-up prompt

        Args:
            session_state: 上下文状态（需包含 MultiModalResponses）

        Returns:
            分析结果字典
        """
        session_state = session_state or {}

        # 确保 MultiModalResponses 存在
        if "MultiModalResponses" not in session_state:
            session_state["MultiModalResponses"] = []

        # 将 MultiModalResponses 转换为字符串格式供模板使用
        multimodal_str = self._format_multimodal_responses(
            session_state.get("MultiModalResponses", [])
        )
        session_state["MultiModalResponses"] = multimodal_str

        # 动态构建 prompt 模板（根据 reminder_created_with_time 决定是否包含 internal follow-up）
        dynamic_template = self._build_userp_template(session_state)

        # 渲染 user prompt
        try:
            rendered_userp = self._render_template(dynamic_template, session_state)
        except Exception as e:
            logger.warning(f"User prompt 渲染失败: {e}")
            rendered_userp = "请分析本次对话"

        # 打印发送给 PostAnalyzeAgent 的 prompt（便于调试）
        logger.debug(
            f"[PostAnalyzeWorkflow] PostAnalyzeAgent LLM INPUT (len={len(rendered_userp)}):\n{'='*50}\n{rendered_userp}\n{'='*50}"
        )

        # 异步调用 Agent 进行后处理分析
        try:
            response = await post_analyze_agent.arun(
                input=rendered_userp, session_state=session_state
            )

            # 记录用量
            if response and hasattr(response, "metrics"):
                usage_tracker.record_from_metrics(
                    agent_name="PostAnalyzeAgent",
                    metrics=response.metrics,
                    user_id=str(session_state.get("user", {}).get("id", "")),
                    session_id=session_state.get("conversation_id"),
                    workflow_name="PostAnalyzeWorkflow",
                )

            # 提取分析结果
            content = self._extract_content(response)
            logger.info("PostAnalyzeAgent 执行完成")

            # V2 新增：处理关系变化
            self._handle_relation_change(content, session_state)

            # 处理内部 follow-up 规划
            self._handle_followup_plan(content, session_state)

            # V2.5 新增：处理角色信息更新（短期目标、态度）
            self._handle_character_info_update(content, session_state)

            # V2.5 新增：处理用户信息更新（真名、昵称、描述）
            self._handle_user_info_update(content, session_state)

            # V2.5 新增：处理关系描述和反感度更新
            self._handle_relationship_update(content, session_state)

        except Exception as e:
            logger.error(f"PostAnalyzeAgent 执行失败: {e}")
            content = self._get_default_content()

        return content

    def _handle_relation_change(self, content: Dict, session_state: Dict) -> None:
        """
        处理关系变化（V2 新增，从 ChatWorkflow 移入）

        Args:
            content: PostAnalyze 返回的内容
            session_state: 会话状态
        """
        relation_change = content.get("RelationChange", {})
        if isinstance(relation_change, str):
            try:
                import json

                relation_change = json.loads(relation_change)
            except Exception:
                relation_change = {}

        closeness_change = relation_change.get("Closeness", 0) or 0
        trustness_change = relation_change.get("Trustness", 0) or 0

        if "relation" in session_state and "relationship" in session_state["relation"]:
            rel = session_state["relation"]["relationship"]

            # 更新亲密度和信任度，限制在 0-100 范围内
            rel["closeness"] = max(
                0, min(100, rel.get("closeness", 0) + closeness_change)
            )
            rel["trustness"] = max(
                0, min(100, rel.get("trustness", 0) + trustness_change)
            )

            logger.info(
                f"关系变化: closeness={closeness_change}, trustness={trustness_change}"
            )

    def _handle_followup_plan(self, content: Dict, session_state: Dict) -> None:
        """Create, replace, or clear the internal proactive follow-up action."""
        conversation_id = str(session_state.get("conversation", {}).get("_id", "")).strip()
        if not conversation_id:
            return

        service = DeferredActionService()

        if session_state.get("reminder_created_with_time"):
            logger.info(
                "[FollowupPlan] 本轮已创建定时提醒，清理内部 proactive follow-up"
            )
            service.clear_internal_followup(conversation_id)
            return

        plan = content.get("FollowupPlan", {})
        if isinstance(plan, str):
            try:
                import json

                plan = json.loads(plan)
            except Exception:
                plan = {}

        followup_action = str(plan.get("FollowupAction", "clear") or "clear").lower()
        followup_time_str = plan.get("FollowupTime", "")
        followup_prompt = plan.get("FollowupPrompt", "无")

        if (
            followup_action not in {"create", "replace"}
            or not followup_time_str
            or not followup_prompt
            or followup_prompt == "无"
        ):
            service.clear_internal_followup(conversation_id)
            logger.info("[FollowupPlan] 未设置内部 proactive follow-up")
            return

        user_tz = session_state.get("user", {}).get("timezone")
        resolved_tz = get_default_timezone() if not user_tz else ZoneInfo(user_tz)
        followup_timestamp = str2timestamp(followup_time_str, tz=resolved_tz)
        if followup_timestamp is None:
            logger.warning("[FollowupPlan] 无法解析 FollowupTime: %s", followup_time_str)
            service.clear_internal_followup(conversation_id)
            return

        proactive_times = int(session_state.get("proactive_times", 0) or 0)
        message_source = session_state.get("message_source", "user")
        deferred_kind = session_state.get("system_message_metadata", {}).get("kind")
        next_proactive_times = (
            proactive_times + 1
            if message_source == "deferred_action" and deferred_kind == "proactive_followup"
            else 0
        )
        dtstart = datetime.fromtimestamp(followup_timestamp, tz=resolved_tz)
        service.create_or_replace_internal_followup(
            conversation_id=conversation_id,
            user_id=str(session_state.get("user", {}).get("id", "")),
            character_id=str(session_state.get("character", {}).get("_id", "")),
            title=followup_prompt[:48],
            prompt=followup_prompt,
            dtstart=dtstart,
            timezone=getattr(resolved_tz, "key", str(resolved_tz)),
            payload_metadata={"proactive_times": next_proactive_times},
        )
        logger.info(
            "[FollowupPlan] 设置内部 proactive follow-up: action=%s time=%s",
            followup_action,
            followup_time_str,
        )

    def _handle_character_info_update(self, content: Dict, session_state: Dict) -> None:
        """
         处理角色信息更新（V2.5 新增）

         将 PostAnalyze 输出的字段映射到 relation.character_info：
        -CharacterLongtermPurpose → longterm_purpose
        -CharacterPurpose → shortterm_purpose
        -CharacterAttitude → attitude

         Args:
             content: PostAnalyze 返回的内容
             session_state: 会话状态
        """
        if (
            "relation" not in session_state
            or "character_info" not in session_state["relation"]
        ):
            return

        char_info = session_state["relation"]["character_info"]

        # 更新长期目标（通常不会频繁变化）
        character_longterm_purpose = content.get("CharacterLongtermPurpose", "")
        if character_longterm_purpose and character_longterm_purpose != "无":
            char_info["longterm_purpose"] = character_longterm_purpose
            logger.info(f"[角色信息更新] 长期目标: {character_longterm_purpose}")

        # 更新短期目标
        character_purpose = content.get("CharacterPurpose", "")
        if character_purpose and character_purpose != "无":
            char_info["shortterm_purpose"] = character_purpose
            logger.info(f"[角色信息更新] 短期目标: {character_purpose}")

        # 更新态度
        character_attitude = content.get("CharacterAttitude", "")
        if character_attitude and character_attitude != "无":
            char_info["attitude"] = character_attitude
            logger.info(f"[角色信息更新] 态度: {character_attitude}")

    def _handle_user_info_update(self, content: Dict, session_state: Dict) -> None:
        """
        处理用户信息更新（V2.5 新增）

        将 PostAnalyze 输出的 UserRealName、UserHobbyName、UserDescription
        映射到 relation.user_info

        Args:
            content: PostAnalyze 返回的内容
            session_state: 会话状态
        """
        if (
            "relation" not in session_state
            or "user_info" not in session_state["relation"]
        ):
            return

        user_info = session_state["relation"]["user_info"]

        # 更新用户真名
        user_realname = content.get("UserRealName", "")
        if user_realname and user_realname != "无":
            user_info["realname"] = user_realname
            logger.info(f"[用户信息更新] 真名: {user_realname}")

        # 更新用户昵称
        user_hobbyname = content.get("UserHobbyName", "")
        if user_hobbyname and user_hobbyname != "无":
            user_info["hobbyname"] = user_hobbyname
            logger.info(f"[用户信息更新] 昵称: {user_hobbyname}")

        # 更新用户描述
        user_description = content.get("UserDescription", "")
        if user_description and user_description != "无":
            # V2.13: 检查是否需要压缩
            if len(user_description) > self.USER_DESC_COMPRESS_THRESHOLD:
                logger.info(
                    f"[用户信息更新] 描述过长({len(user_description)}字)，触发压缩"
                )
                user_description = self._compress_user_description(user_description)
            user_info["description"] = user_description
            logger.info(f"[用户信息更新] 描述: {user_description[:50]}...")

    # RelationDescription 压缩阈值
    RELATION_DESC_COMPRESS_THRESHOLD = 500  # 超过此长度触发压缩
    RELATION_DESC_TARGET_LENGTH = 300  # 压缩后的目标长度

    # UserDescription 压缩阈值（V2.13 新增）
    USER_DESC_COMPRESS_THRESHOLD = 800  # 超过此长度触发压缩
    USER_DESC_TARGET_LENGTH = 500  # 压缩后的目标长度

    def _handle_relationship_update(self, content: Dict, session_state: Dict) -> None:
        """
        处理关系描述和反感度更新（V2.5 新增，V2.8 增加压缩机制）

        将 PostAnalyze 输出的 RelationDescription 和 Dislike
        映射到 relation.relationship

        V2.8 更新：当 RelationDescription 超过阈值时，调用 LLM 进行摘要压缩

        Args:
            content: PostAnalyze 返回的内容
            session_state: 会话状态
        """
        if (
            "relation" not in session_state
            or "relationship" not in session_state["relation"]
        ):
            return

        relationship = session_state["relation"]["relationship"]

        # 更新关系描述
        relation_description = content.get("RelationDescription", "")
        if relation_description and relation_description != "无":
            # V2.8: 检查是否需要压缩
            if len(relation_description) > self.RELATION_DESC_COMPRESS_THRESHOLD:
                logger.info(
                    f"[关系更新] 描述过长({len(relation_description)}字)，触发压缩"
                )
                relation_description = self._compress_relation_description(
                    relation_description
                )

            relationship["description"] = relation_description
            logger.info(f"[关系更新] 描述: {relation_description[:100]}...")

        # 更新反感度
        dislike_change = content.get("Dislike", 0) or 0
        if dislike_change != 0:
            current_dislike = relationship.get("dislike", 0)
            new_dislike = max(0, min(100, current_dislike + dislike_change))
            relationship["dislike"] = new_dislike
            logger.info(
                f"[关系更新] 反感度变化: {dislike_change}, 当前值: {new_dislike}"
            )

    def _compress_relation_description(self, description: str) -> str:
        """
        压缩过长的关系描述（V2.8 新增）

        使用 Agno DeepSeek 模型对超长的关系描述进行摘要压缩，保留关键信息.

        Args:
            description: 原始关系描述

        Returns:
            压缩后的关系描述
        """
        return self._compress_description(
            description, self.RELATION_DESC_TARGET_LENGTH, "关系描述"
        )

    def _compress_user_description(self, description: str) -> str:
        """
        压缩过长的用户印象描述（V2.13 新增）

        使用 Agno DeepSeek 模型对超长的用户印象描述进行摘要压缩，保留关键信息.

        Args:
            description: 原始用户印象描述

        Returns:
            压缩后的用户印象描述
        """
        return self._compress_description(
            description, self.USER_DESC_TARGET_LENGTH, "用户印象描述"
        )

    def _compress_description(
        self, description: str, target_length: int, desc_type: str
    ) -> str:
        """
        通用描述压缩方法（V2.13 重构）

        使用 Agno DeepSeek 模型对超长描述进行摘要压缩，保留关键信息.

        Args:
            description: 原始描述
            target_length: 压缩后的目标长度
            desc_type: 描述类型（用于日志）

        Returns:
            压缩后的描述
        """
        try:
            from agno.agent import Agent

            # 创建轻量级压缩 Agent
            compress_agent = Agent(
                id="description-compress-agent",
                name="DescriptionCompressAgent",
                model=create_llm_model(max_tokens=8000, role="post_analyze"),
                markdown=False,
            )

            compress_prompt = f"""请将以下{desc_type}压缩为不超过{target_length}字的摘要.

要求：
1. 保留核心特征和关键信息
2. 保留最重要的变化节点
3. 删除重复的"没有明显变化"、"进一步强化了"等冗余信息
4. 保留最新的状态
5. 直接输出压缩后的描述，不要添加任何解释

原始描述：
{description}"""

            # 同步调用（压缩是轻量操作）
            response = compress_agent.run(compress_prompt)

            if response and response.content:
                compressed = str(response.content).strip()
                logger.info(
                    f"[{desc_type}压缩] {len(description)}字 -> {len(compressed)}字"
                )
                return compressed
            else:
                raise ValueError("压缩响应为空")

        except Exception as e:
            logger.warning(f"[{desc_type}压缩] 压缩失败: {e}，使用截断方式")
            # 压缩失败时，简单截断保留最新部分
            return description[-target_length:]

    def _render_template(self, template: str, context: Dict[str, Any]) -> str:
        """
        渲染模板字符串

        Args:
            template: 模板字符串
            context: 上下文数据

        Returns:
            渲染后的字符串
        """
        try:
            return render_prompt_template(template, context)
        except KeyError as e:
            logger.warning(f"模板渲染缺少字段: {e}")
            return template

    def _format_multimodal_responses(self, responses: list) -> str:
        """
        将 MultiModalResponses 列表格式化为字符串

        Args:
            responses: MultiModalResponses 列表

        Returns:
            格式化后的字符串
        """
        if not responses:
            return "（无回复）"

        lines = []
        for resp in responses:
            if isinstance(resp, dict):
                resp_type = resp.get("type", "text")
                content = resp.get("content", "")
                if resp_type == "text":
                    lines.append(content)
                elif resp_type == "photo":
                    lines.append(f"[发送了一张照片: {content}]")
                elif resp_type == "voice":
                    lines.append("[发送了一条语音]")
                else:
                    lines.append(str(content))
            else:
                lines.append(str(resp))

        return "\n".join(lines)

    def _extract_content(self, response) -> Dict[str, Any]:
        """
        从 Agent 响应中提取内容

        V2 重构：新增 RelationChange 和 FollowupPlan 字段

        Args:
            response: Agent 响应对象

        Returns:
            提取的内容字典
        """
        if not response or not response.content:
            return self._get_default_content()

        content = response.content

        # 如果是 Pydantic 模型，转换为 dict
        if hasattr(content, "model_dump"):
            content = content.model_dump()
        elif not isinstance(content, dict):
            return self._get_default_content()

        # 确保必要字段存在（V2：新增 RelationChange 和 FollowupPlan；V2.5：新增 CharacterLongtermPurpose）
        result = {
            # 新增：关系变化
            "RelationChange": content.get(
                "RelationChange", {"Closeness": 0, "Trustness": 0}
            ),
            # 新增：内部 follow-up 规划
            "FollowupPlan": content.get(
                "FollowupPlan",
                {
                    "FollowupAction": "clear",
                    "FollowupTime": "",
                    "FollowupPrompt": "无",
                },
            ),
            # 原有字段
            "CharacterPublicSettings": content.get("CharacterPublicSettings", "无"),
            "CharacterPrivateSettings": content.get("CharacterPrivateSettings", "无"),
            "UserSettings": content.get("UserSettings", "无"),
            "CharacterKnowledges": content.get("CharacterKnowledges", "无"),
            "UserRealName": content.get("UserRealName", "无"),
            "UserHobbyName": content.get("UserHobbyName", "无"),
            "UserDescription": content.get("UserDescription", ""),
            "CharacterLongtermPurpose": content.get("CharacterLongtermPurpose", ""),
            "CharacterPurpose": content.get("CharacterPurpose", ""),
            "CharacterAttitude": content.get("CharacterAttitude", ""),
            "RelationDescription": content.get("RelationDescription", ""),
            "Dislike": content.get("Dislike", 0),
        }

        return result

    def _get_default_content(self) -> Dict[str, Any]:
        """获取默认的内容结构（V2：新增 RelationChange 和 FollowupPlan）"""
        return {
            "RelationChange": {"Closeness": 0, "Trustness": 0},
            "FollowupPlan": {
                "FollowupAction": "clear",
                "FollowupTime": "",
                "FollowupPrompt": "无",
            },
            "CharacterPublicSettings": "无",
            "CharacterPrivateSettings": "无",
            "UserSettings": "无",
            "CharacterKnowledges": "无",
            "UserRealName": "无",
            "UserHobbyName": "无",
            "UserDescription": "",
            "CharacterLongtermPurpose": "",
            "CharacterPurpose": "",
            "CharacterAttitude": "",
            "RelationDescription": "",
            "Dislike": 0,
        }
