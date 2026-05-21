# -*- coding: utf-8 -*-
"""Post-analyze runtime logic for memory and internal follow-up updates."""

import json
import logging
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from agno.agent import Agent

from agent.agno_agent.model_factory import create_llm_model
from agent.agno_agent.schemas.post_analyze_schema import PostAnalyzeResponse
from agent.agno_agent.utils.usage_tracker import usage_tracker
from agent.prompt.chat_contextprompt import (
    CONTEXTPROMPT_人物资料,
    CONTEXTPROMPT_当前的人物关系,
    CONTEXTPROMPT_时间,
    CONTEXTPROMPT_最新聊天消息_双方,
    CONTEXTPROMPT_用户资料,
)
from agent.prompt.chat_taskprompt import TASKPROMPT_总结, get_post_analyze_prompt
from agent.prompt.rendering import render_prompt_template
from agent.reminder.errors import ReminderError
from agent.reminder.models import ReminderSchedule
from util.time_util import get_default_timezone, str2timestamp

logger = logging.getLogger(__name__)


USERP_TEMPLATE_PREFIX = (
    TASKPROMPT_总结
    + CONTEXTPROMPT_时间
    + CONTEXTPROMPT_人物资料
    + CONTEXTPROMPT_用户资料
    + CONTEXTPROMPT_当前的人物关系
    + CONTEXTPROMPT_最新聊天消息_双方
)

RELATION_DESC_COMPRESS_THRESHOLD = 500
RELATION_DESC_TARGET_LENGTH = 300
USER_DESC_COMPRESS_THRESHOLD = 800
USER_DESC_TARGET_LENGTH = 500


def _create_post_analyze_agent() -> Agent:
    return Agent(
        model=create_llm_model(role="post_analyze", max_tokens=8000),
        output_schema=PostAnalyzeResponse,
        use_json_mode=True,
        markdown=False,
    )


async def run_post_analyze(session_state: dict[str, Any]) -> None:
    """Run post-analyze and mutate ``session_state["relation"]`` in place."""
    if "MultiModalResponses" not in session_state:
        session_state["MultiModalResponses"] = []

    multimodal_str = _format_multimodal_responses(
        session_state.get("MultiModalResponses", [])
    )
    session_state["MultiModalResponses"] = multimodal_str

    dynamic_template = _build_userp_template(session_state)

    try:
        rendered_userp = _render_template(dynamic_template, session_state)
    except Exception as exc:
        logger.warning("User prompt 渲染失败: %s", exc)
        rendered_userp = "请分析本次对话"

    logger.debug(
        "[PostAnalyze] PostAnalyzeAgent LLM INPUT (len=%s):\n%s\n%s\n%s",
        len(rendered_userp),
        "=" * 50,
        rendered_userp,
        "=" * 50,
    )

    try:
        agent = _create_post_analyze_agent()
        response = await agent.arun(input=rendered_userp, session_state=session_state)

        if response and hasattr(response, "metrics"):
            usage_tracker.record_from_metrics(
                agent_name="PostAnalyzeAgent",
                metrics=response.metrics,
                user_id=str(session_state.get("user", {}).get("id", "")),
                session_id=session_state.get("conversation_id"),
                workflow_name="PostAnalyzeWorkflow",
            )

        content = _extract_content(response)
        logger.info("PostAnalyzeAgent 执行完成")

        _handle_followup_plan(content, session_state)
        _handle_character_info_update(content, session_state)
        _handle_user_info_update(content, session_state)
        _handle_relationship_update(content, session_state)
    except Exception as exc:
        logger.error("PostAnalyzeAgent 执行失败: %s", exc)
        _get_default_content()


def _reminder_created_with_time(session_state: dict[str, Any]) -> bool:
    relation = session_state.get("relation", {})
    return bool(
        session_state.get("reminder_created_with_time")
        or (isinstance(relation, dict) and relation.get("reminder_created_with_time"))
    )


def _build_userp_template(session_state: dict[str, Any]) -> str:
    skip_future_response = _reminder_created_with_time(session_state)

    if skip_future_response:
        logger.info(
            "[PostAnalyze] 检测到 reminder_created_with_time=True，跳过 internal follow-up prompt"
        )

    return USERP_TEMPLATE_PREFIX + get_post_analyze_prompt(skip_future_response)


def _handle_followup_plan(
    content: dict[str, Any], session_state: dict[str, Any]
) -> None:
    """Create, replace, or clear the internal proactive follow-up action."""
    from agent.agno_agent.adapters.coke_reminder_adapter import CokeReminderAdapter

    adapter = CokeReminderAdapter()

    if _reminder_created_with_time(session_state):
        logger.info("[FollowupPlan] 本轮已创建定时提醒，清理内部 proactive follow-up")
        try:
            adapter.clear_internal_followup(session_state=session_state)
        except ReminderError as exc:
            logger.warning(
                "[FollowupPlan] 无法清理内部 follow-up: %s", exc.user_message
            )
        return

    plan = content.get("FollowupPlan", {})
    if isinstance(plan, str):
        try:
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
        try:
            adapter.clear_internal_followup(session_state=session_state)
        except ReminderError as exc:
            logger.warning(
                "[FollowupPlan] 无法清理内部 follow-up: %s", exc.user_message
            )
        logger.info("[FollowupPlan] 未设置内部 proactive follow-up")
        return

    user_tz = session_state.get("user", {}).get("timezone")
    resolved_tz = get_default_timezone() if not user_tz else ZoneInfo(user_tz)
    followup_timestamp = str2timestamp(followup_time_str, tz=resolved_tz)
    if followup_timestamp is None:
        logger.warning("[FollowupPlan] 无法解析 FollowupTime: %s", followup_time_str)
        try:
            adapter.clear_internal_followup(session_state=session_state)
        except ReminderError as exc:
            logger.warning(
                "[FollowupPlan] 无法清理内部 follow-up: %s", exc.user_message
            )
        return

    proactive_times = int(session_state.get("proactive_times", 0) or 0)
    message_source = session_state.get("message_source", "user")
    deferred_kind = session_state.get("system_message_metadata", {}).get("kind")
    next_proactive_times = (
        proactive_times + 1
        if message_source == "reminder" and deferred_kind == "internal_followup"
        else 0
    )
    dtstart = datetime.fromtimestamp(followup_timestamp, tz=resolved_tz)
    reminder_schedule = ReminderSchedule(
        anchor_at=dtstart.astimezone(timezone.utc),
        local_date=dtstart.date(),
        local_time=dtstart.time().replace(tzinfo=None),
        timezone=getattr(resolved_tz, "key", str(resolved_tz)),
        rrule=None,
    )
    try:
        adapter.create_or_replace_internal_followup(
            session_state=session_state,
            title=followup_prompt[:48],
            prompt=followup_prompt,
            schedule=reminder_schedule,
            metadata={"proactive_times": next_proactive_times},
        )
    except ReminderError as exc:
        logger.warning("[FollowupPlan] 无法设置内部 follow-up: %s", exc.user_message)
        return
    logger.info(
        "[FollowupPlan] 设置内部 proactive follow-up: action=%s time=%s",
        followup_action,
        followup_time_str,
    )


def _handle_character_info_update(
    content: dict[str, Any], session_state: dict[str, Any]
) -> None:
    if (
        "relation" not in session_state
        or "character_info" not in session_state["relation"]
    ):
        return

    char_info = session_state["relation"]["character_info"]

    character_longterm_purpose = content.get("CharacterLongtermPurpose", "")
    if character_longterm_purpose and character_longterm_purpose != "无":
        char_info["longterm_purpose"] = character_longterm_purpose
        logger.info("[角色信息更新] 长期目标: %s", character_longterm_purpose)

    character_purpose = content.get("CharacterPurpose", "")
    if character_purpose and character_purpose != "无":
        char_info["shortterm_purpose"] = character_purpose
        logger.info("[角色信息更新] 短期目标: %s", character_purpose)

    character_attitude = content.get("CharacterAttitude", "")
    if character_attitude and character_attitude != "无":
        char_info["attitude"] = character_attitude
        logger.info("[角色信息更新] 态度: %s", character_attitude)


def _handle_user_info_update(
    content: dict[str, Any], session_state: dict[str, Any]
) -> None:
    if "relation" not in session_state or "user_info" not in session_state["relation"]:
        return

    user_info = session_state["relation"]["user_info"]

    user_realname = content.get("UserRealName", "")
    if user_realname and user_realname != "无":
        user_info["realname"] = user_realname
        logger.info("[用户信息更新] 真名: %s", user_realname)

    user_hobbyname = content.get("UserHobbyName", "")
    if user_hobbyname and user_hobbyname != "无":
        user_info["hobbyname"] = user_hobbyname
        logger.info("[用户信息更新] 昵称: %s", user_hobbyname)

    user_description = content.get("UserDescription", "")
    if user_description and user_description != "无":
        if len(user_description) > USER_DESC_COMPRESS_THRESHOLD:
            logger.info(
                "[用户信息更新] 描述过长(%s字)，触发压缩", len(user_description)
            )
            user_description = _compress_user_description(user_description)
        user_info["description"] = user_description
        logger.info("[用户信息更新] 描述: %s...", user_description[:50])


def _handle_relationship_update(
    content: dict[str, Any], session_state: dict[str, Any]
) -> None:
    if (
        "relation" not in session_state
        or "relationship" not in session_state["relation"]
    ):
        return

    relationship = session_state["relation"]["relationship"]

    relation_description = content.get("RelationDescription", "")
    if relation_description and relation_description != "无":
        if len(relation_description) > RELATION_DESC_COMPRESS_THRESHOLD:
            logger.info(
                "[关系更新] 描述过长(%s字)，触发压缩", len(relation_description)
            )
            relation_description = _compress_relation_description(relation_description)

        relationship["description"] = relation_description
        logger.info("[关系更新] 描述: %s...", relation_description[:100])


def _compress_relation_description(description: str) -> str:
    return _compress_description(description, RELATION_DESC_TARGET_LENGTH, "关系描述")


def _compress_user_description(description: str) -> str:
    return _compress_description(description, USER_DESC_TARGET_LENGTH, "用户印象描述")


def _compress_description(description: str, target_length: int, desc_type: str) -> str:
    try:
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

        response = compress_agent.run(compress_prompt)

        if response and response.content:
            compressed = str(response.content).strip()
            logger.info(
                "[%s压缩] %s字 -> %s字", desc_type, len(description), len(compressed)
            )
            return compressed
        raise ValueError("压缩响应为空")

    except Exception as exc:
        logger.warning("[%s压缩] 压缩失败: %s，使用截断方式", desc_type, exc)
        return description[-target_length:]


def _render_template(template: str, context: dict[str, Any]) -> str:
    try:
        return render_prompt_template(template, context)
    except KeyError as exc:
        logger.warning("模板渲染缺少字段: %s", exc)
        return template


def _format_multimodal_responses(responses: list[Any]) -> str:
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


def _extract_content(response: Any) -> dict[str, Any]:
    if not response or not response.content:
        return _get_default_content()

    content = response.content

    if hasattr(content, "model_dump"):
        content = content.model_dump()
    elif not isinstance(content, dict):
        return _get_default_content()

    return {
        "FollowupPlan": content.get(
            "FollowupPlan",
            {
                "FollowupAction": "clear",
                "FollowupTime": "",
                "FollowupPrompt": "无",
            },
        ),
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
    }


def _get_default_content() -> dict[str, Any]:
    return {
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
    }
