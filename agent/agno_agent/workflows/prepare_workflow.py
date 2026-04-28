# -*- coding: utf-8 -*-
"""
PrepareWorkflow-准备阶段 Workflow (V2 架构)

V2 架构改进：
- 引入 OrchestratorAgent 作为调度中心 (1次 LLM)
- context_retrieve_tool 直接函数调用 (0次 LLM)
- ReminderDetectAgent 按需调用 (0-1次 LLM)

执行顺序：OrchestratorAgent → context_retrieve_tool → ReminderDetectAgent(按需)

LLM 调用次数：
- 普通消息：1次 (Orchestrator)
- 提醒消息：2次 (Orchestrator + ReminderDetect)

Requirements: 5.1
"""

import logging
import os
import re
import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from agent.agno_agent.agents import (
    orchestrator_agent,
    reminder_detect_agent,
)
from agent.agno_agent.tools.reminder_protocol import (
    set_reminder_session_state,
    visible_reminder_tool,
)
from agent.agno_agent.tools.context_retrieve_tool import context_retrieve_tool
from agent.agno_agent.tools.calendar_import_handoff import (
    create_calendar_import_handoff_link,
)
from agent.agno_agent.tools.url_reader import extract_urls_content, format_url_context
from agent.agno_agent.tools.web_search_tool import web_search_tool
from agent.agno_agent.tools.timezone_tools import (
    PENDING_PROPOSAL_EXPIRED_MESSAGE,
    clear_pending_timezone_proposal,
    consume_timezone_confirmation,
    is_timezone_proposal_expired,
    normalize_timezone_confirmation_decision,
    set_user_timezone,
    store_timezone_proposal,
)
from agent.agno_agent.tools.tool_result import append_tool_result
from agent.agno_agent.utils.usage_tracker import usage_tracker
from agent.prompt.chat_contextprompt import (
    CONTEXTPROMPT_历史对话_精简,
    CONTEXTPROMPT_时间,
    CONTEXTPROMPT_最新聊天消息,
)
from agent.prompt.rendering import render_prompt_template
from agent.prompt.chat_taskprompt import (
    TASKPROMPT_语义理解,
)
from agent.util.message_util import messages_to_str

logger = logging.getLogger(__name__)


def _float_env(name: str, default: float) -> float:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    try:
        value = float(raw_value)
    except ValueError:
        logger.warning("%s=%r is not a valid float; using %.1f", name, raw_value, default)
        return default
    return value if value > 0 else default


_PREPARE_ORCHESTRATOR_TIMEOUT_SECONDS = _float_env(
    "COKE_PREPARE_ORCHESTRATOR_TIMEOUT_SECONDS",
    45.0,
)
_PREPARE_REMINDER_DETECT_TIMEOUT_SECONDS = _float_env(
    "COKE_PREPARE_REMINDER_DETECT_TIMEOUT_SECONDS",
    45.0,
)

_EXPLICIT_TIMEZONE_OVERRIDE_PATTERNS = (
    re.compile(r"(以后|之后|后面|今后|从现在起|往后).{0,12}按.{0,20}时间"),
    re.compile(r"(以后|之后|后面|今后|从现在起|往后).{0,12}(用|按照).{0,20}(时间|时区)"),
    re.compile(
        r"(from now on|going forward|after this).{0,24}(use|follow).{0,24}(time|timezone)"
    ),
)

_CALENDAR_IMPORT_PATH = "/account/calendar-import"
_CALENDAR_IMPORT_INTENT_PATTERNS = (
    re.compile(r"(导入|同步|绑定|接入|连接|授权).{0,12}(谷歌|google)?日历", re.IGNORECASE),
    re.compile(r"(谷歌|google).{0,12}日历.{0,12}(导入|同步|绑定|接入|连接|授权)", re.IGNORECASE),
    re.compile(
        r"\b(import|sync|connect|link|authorize|integrate)\b.{0,40}\b(google\s+calendar|calendar)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(google\s+calendar|calendar)\b.{0,40}\b(import|sync|connect|link|authorize|integrate)\b",
        re.IGNORECASE,
    ),
)
_REMINDER_FIRST_PATTERNS = (
    re.compile(r"(提醒我|到时候|闹钟)"),
    re.compile(r"\b(remind me|set a reminder|alarm)\b", re.IGNORECASE),
)
_EXPLICIT_REMINDER_INTENT_PATTERNS = (
    re.compile(r"(提醒我|闹钟|通知我|别忘了提醒)"),
    re.compile(
        r"\b(remind me|set a reminder|set an alarm|notify me)\b",
        re.IGNORECASE,
    ),
)
_CALL_ME_MARKER_PATTERN = re.compile(r"(叫我|喊我)")
_ACTIONABLE_CALL_ME_TIME_PATTERN = re.compile(
    r"(\d{1,2}\s*[:：]\s*[0-5]\d|[零〇一二两三四五六七八九十\d]{1,3}点"
    r"|点半|明早|明天|今天|今晚|早上|上午|中午|下午|晚上|凌晨|一会|分钟|小时)"
)
_ACTIONABLE_CALL_ME_TASK_PATTERN = re.compile(
    r"(起床|出门|离开|吃药|吃饭|睡觉|背书|学习|打卡|工作)"
)
_VAGUE_REMINDER_CAPABILITY_PATTERN = re.compile(
    r"^(你)?(可以|能不能|能|会不会|会).{0,8}(循环|重复|定期)?提醒我[吗么嘛]?[？?]?$"
)
_IMPLICIT_REMINDER_INTENT_PATTERNS = (
    re.compile(
        r"(\d{1,2}\s*[:：]\s*[0-5]\d|[零〇一二两三四五六七八九十\d]{1,3}点)"
        r".{0,12}(开始|背书|学习|起床|出门|跑步|乐跑|喝水|吃饭)"
    ),
)
_SIMPLE_TIME_REMINDER_PATTERN = re.compile(
    r"(?P<hour>[01]?\d|2[0-3])\s*[:：]\s*(?P<minute>[0-5]\d)"
)
_SIMPLE_CHINESE_TIME_REMINDER_PATTERN = re.compile(
    r"(?P<period>今天晚上|今晚|晚上|下午|上午|早上|中午|凌晨)?"
    r"(?P<hour>[零〇一二两三四五六七八九十\d]{1,3})点"
    r"(?P<minute>半|[0-5]?\d|[零〇一二两三四五六七八九十]{1,3})?分?"
)
_REMINDER_TITLE_AFTER_MARKER_PATTERN = re.compile(
    r"(提醒我|叫我|通知我)(?P<title>[^，。！？!?；;\n]+)"
)
_TOMORROW_WORK_END_DEADLINE_PATTERN = re.compile(
    r"(?P<title>.+?)\s*明天下班前(?P<tail>.*?(?:必须|要|得|需要).*(?:学完|完成|做完|弄完)|.*(?:学完|完成|做完|弄完))"
)


class PrepareWorkflow:
    """
     准备阶段 Workflow (V2 架构)

     注意：这是自定义 Workflow 类，不继承 Agno Workflow，
     因为需要 Runner 层控制分段执行和打断检测.

     执行流程：
     1. OrchestratorAgent-语义理解 + 调度决策 (1次 LLM)
     2. context_retrieve_tool-直接函数调用 (0次 LLM)
     2.5. web_search_tool-联网搜索 (0次 LLM, 按需)
     3. ReminderDetectAgent-按需调用 (0-1次 LLM)

     输出：
    -session_state["orchestrator"]-OrchestratorAgent 的输出
    -session_state["context_retrieve"]-context_retrieve_tool 的输出
    -session_state["web_search_result"]-联网搜索结果 (按需)

     兼容性：
    -session_state["query_rewrite"]-保留旧字段，从 orchestrator 映射
    """

    # User prompt 模板：Orchestrator 任务
    # V2.6 优化：使用精简版历史对话（最近6条），减少 token 消耗
    # OrchestratorAgent 只需理解当前意图，不需要完整 50 轮历史
    orchestrator_template = (
        TASKPROMPT_语义理解
        + CONTEXTPROMPT_时间
        + CONTEXTPROMPT_历史对话_精简
        + CONTEXTPROMPT_最新聊天消息
    )

    # ReminderDetectAgent 上下文模板
    # V2.7 新增：传入最近5条对话作为上下文，支持跨消息意图整合
    REMINDER_CONTEXT_TEMPLATE = """### 当前时间
{time_str}

### 用户时区
{timezone}

### 最近对话上下文（最近5条）
{recent_chat_context}

### 当前用户消息
{current_message}"""

    async def run(
        self, input_message: str, session_state: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        异步执行准备阶段 (V2 架构)

        Args:
            input_message: 用户输入消息
            session_state: 上下文状态

        Returns:
            包含 session_state 的结果字典

        重构说明：复杂度从 21 降低到约 10，通过提取步骤方法实现
        """
        session_state = session_state or {}

        if self._consume_pending_timezone_confirmation(input_message, session_state):
            return {"session_state": session_state}

        # Step 1: Orchestrator 决策 (1次 LLM)
        await self._run_orchestrator(input_message, session_state)

        # 获取调度决策
        orchestrator = session_state.get("orchestrator", {})
        need_context = orchestrator.get("need_context_retrieve", True)
        need_reminder = self._should_run_reminder_detect(
            input_message,
            orchestrator,
            session_state,
        )

        # Step 2: 上下文检索 (直接调用 Tool，0次 LLM)
        self._run_context_retrieve(session_state, need_context)

        # Step 2.5: 联网搜索 (按需调用，0次 LLM)
        need_web_search = orchestrator.get("need_web_search", False)
        if need_web_search:
            self._run_web_search(session_state, orchestrator)
        else:
            logger.info("跳过联网搜索 (need_web_search=False)")

        # Step 2.7: 时区更新 (按需调用，0次 LLM)
        need_timezone_update = orchestrator.get("need_timezone_update", False)
        timezone_action = self._resolve_timezone_action(orchestrator)
        timezone_value = orchestrator.get("timezone_value", "")
        if self._should_force_direct_timezone_set(
            input_message=input_message,
            timezone_action=timezone_action,
            timezone_value=timezone_value,
        ):
            logger.info(
                "[PrepareWorkflow] 将明确时区请求从 proposal 升级为 direct_set: %s",
                timezone_value,
            )
            timezone_action = "direct_set"
        if timezone_action == "direct_set" and timezone_value:
            self._run_timezone_update(session_state, timezone_value)
        elif timezone_action == "proposal" and timezone_value:
            self._store_pending_timezone_change(session_state, timezone_value)
        elif need_timezone_update or timezone_action != "none":
            logger.warning("时区更新被请求但 timezone_value 为空，跳过")
        else:
            logger.info("跳过时区更新 (timezone_action=none)")

        # Step 2.75: Google Calendar import is a web-only flow; surface the entry link in chat.
        self._surface_calendar_import_entry_if_needed(input_message, session_state)

        # Step 2.6: 链接内容提取 (检测消息中的 URL 并获取内容)
        self._run_url_extraction(input_message, session_state)

        # Step 3: 提醒检测 (按需调用 Agent，0-1次 LLM)
        if need_reminder:
            await self._run_reminder_detect(input_message, session_state, orchestrator)
        else:
            logger.info("跳过提醒检测 (need_reminder_detect=False)")

        return {"session_state": session_state}

    async def _run_orchestrator(
        self, input_message: str, session_state: Dict[str, Any]
    ) -> None:
        """执行 OrchestratorAgent 决策"""
        try:
            rendered_prompt = self._render_template(
                self.orchestrator_template, session_state
            )
        except Exception as e:
            logger.warning(f"Orchestrator prompt 渲染失败: {e}")
            rendered_prompt = input_message

        logger.debug(
            f"[PrepareWorkflow] OrchestratorAgent LLM INPUT (len={len(rendered_prompt)})"
        )

        try:
            orchestrator_response = await asyncio.wait_for(
                orchestrator_agent.arun(
                    input=rendered_prompt,
                    session_state=session_state,
                ),
                timeout=_PREPARE_ORCHESTRATOR_TIMEOUT_SECONDS,
            )

            # 记录用量
            if orchestrator_response and hasattr(orchestrator_response, "metrics"):
                usage_tracker.record_from_metrics(
                    agent_name="OrchestratorAgent",
                    metrics=orchestrator_response.metrics,
                    user_id=str(session_state.get("user", {}).get("id", "")),
                    session_id=session_state.get("conversation_id"),
                    workflow_name="PrepareWorkflow",
                )

            if orchestrator_response and orchestrator_response.content:
                if hasattr(orchestrator_response.content, "model_dump"):
                    orchestrator_result = orchestrator_response.content.model_dump()
                elif isinstance(orchestrator_response.content, dict):
                    orchestrator_result = orchestrator_response.content
                else:
                    orchestrator_result = self._get_default_orchestrator()

                session_state["orchestrator"] = orchestrator_result
                self._map_to_query_rewrite(session_state, orchestrator_result)
                logger.info("OrchestratorAgent 执行完成")
            else:
                logger.warning("OrchestratorAgent 返回空内容")
                session_state["orchestrator"] = self._get_default_orchestrator()
                session_state["query_rewrite"] = self._get_default_query_rewrite()

        except asyncio.TimeoutError:
            logger.error(
                "OrchestratorAgent 执行超时: timeout=%.1fs",
                _PREPARE_ORCHESTRATOR_TIMEOUT_SECONDS,
            )
            orchestrator_result = self._get_default_orchestrator()
            if self._looks_like_reminder_intent(input_message):
                orchestrator_result["need_reminder_detect"] = True
                logger.info(
                    "[PrepareWorkflow] Orchestrator 超时后命中提醒意图规则，"
                    "使用默认调度继续提醒检测"
                )
            session_state["orchestrator"] = orchestrator_result
            session_state["prepare_orchestrator_timeout"] = True
            self._map_to_query_rewrite(session_state, orchestrator_result)
        except Exception as e:
            logger.error(f"OrchestratorAgent 执行失败: {e}")
            session_state["orchestrator"] = self._get_default_orchestrator()
            session_state["query_rewrite"] = self._get_default_query_rewrite()

    def _should_run_reminder_detect(
        self,
        input_message: str,
        orchestrator: Dict[str, Any],
        session_state: Dict[str, Any],
    ) -> bool:
        """判断是否需要执行提醒检测"""
        need_reminder = orchestrator.get("need_reminder_detect", False)

        # 系统延迟动作跳过提醒检测
        message_source = session_state.get("message_source", "user")
        if message_source == "deferred_action":
            logger.info(f"系统消息 (source={message_source})，跳过提醒检测")
            return False

        if self._looks_like_vague_reminder_capability_question(input_message):
            orchestrator["need_reminder_detect"] = False
            session_state["direct_reply"] = (
                "可以循环提醒。你告诉我提醒内容、开始时间和循环频率，"
                "比如“每天晚上八点提醒我冥想”。"
            )
            logger.info(
                "[PrepareWorkflow] 提醒能力问句缺少可执行内容，跳过 ReminderDetectAgent"
            )
            return False

        if not need_reminder and self._looks_like_reminder_intent(
            input_message
        ):
            orchestrator["need_reminder_detect"] = True
            logger.info(
                "[PrepareWorkflow] 提醒意图命中规则，覆盖 Orchestrator need_reminder_detect=False"
            )
            return True

        return need_reminder

    def _looks_like_explicit_reminder_intent(self, input_message: str) -> bool:
        text = str(input_message or "").strip()
        if not text:
            return False
        return any(
            pattern.search(text) for pattern in _EXPLICIT_REMINDER_INTENT_PATTERNS
        ) or self._looks_like_actionable_call_me_reminder(text)

    def _looks_like_actionable_call_me_reminder(self, input_message: str) -> bool:
        text = str(input_message or "").strip()
        if not _CALL_ME_MARKER_PATTERN.search(text):
            return False
        return bool(
            _ACTIONABLE_CALL_ME_TIME_PATTERN.search(text)
            or _ACTIONABLE_CALL_ME_TASK_PATTERN.search(text)
        )

    def _looks_like_vague_reminder_capability_question(
        self, input_message: str
    ) -> bool:
        text = str(input_message or "").strip()
        return bool(_VAGUE_REMINDER_CAPABILITY_PATTERN.search(text))

    def _looks_like_implicit_reminder_intent(self, input_message: str) -> bool:
        text = str(input_message or "").strip()
        if not text:
            return False
        return any(pattern.search(text) for pattern in _IMPLICIT_REMINDER_INTENT_PATTERNS)

    def _looks_like_reminder_intent(self, input_message: str) -> bool:
        return self._looks_like_explicit_reminder_intent(
            input_message
        ) or self._looks_like_implicit_reminder_intent(input_message)

    def _run_context_retrieve(
        self, session_state: Dict[str, Any], need_context: bool
    ) -> None:
        """执行上下文检索"""
        if not need_context:
            logger.info("跳过上下文检索 (need_context_retrieve=False)")
            session_state["context_retrieve"] = self._get_default_context_retrieve()
            return

        try:
            orchestrator = session_state.get("orchestrator", {})
            params = orchestrator.get("context_retrieve_params", {})
            character_id = str(session_state.get("character", {}).get("_id", ""))
            user_id = str(session_state.get("user", {}).get("id", ""))

            context_result = context_retrieve_tool(
                character_setting_query=params.get("character_setting_query", ""),
                character_setting_keywords=params.get("character_setting_keywords", ""),
                user_profile_query=params.get("user_profile_query", ""),
                user_profile_keywords=params.get("user_profile_keywords", ""),
                character_knowledge_query=params.get("character_knowledge_query", ""),
                character_knowledge_keywords=params.get(
                    "character_knowledge_keywords", ""
                ),
                chat_history_query=params.get("chat_history_query", ""),
                chat_history_keywords=params.get("chat_history_keywords", ""),
                character_id=character_id,
                user_id=user_id,
            )
            session_state["context_retrieve"] = context_result
            logger.info("context_retrieve_tool 执行完成")
        except Exception as e:
            logger.error(f"context_retrieve_tool 执行失败: {e}")
            session_state["context_retrieve"] = self._get_default_context_retrieve()

    def _run_web_search(
        self, session_state: Dict[str, Any], orchestrator: dict
    ) -> None:
        """执行联网搜索"""
        try:
            query = orchestrator.get("web_search_query", "")
            if not query:
                logger.warning("联网搜索被请求但未提供搜索词")
                return

            logger.info(f"执行联网搜索: query='{query}'")

            search_result = web_search_tool.entrypoint(query=query)
            session_state["web_search_result"] = search_result

            if search_result.get("ok"):
                result_count = len(search_result.get("results", []))
                logger.info(f"联网搜索完成: 获取 {result_count} 条结果")
            else:
                logger.warning(f"联网搜索失败: {search_result.get('error', 'unknown')}")

        except Exception as e:
            logger.error(f"联网搜索执行异常: {e}")
            session_state["web_search_result"] = {"ok": False, "error": str(e)}

    def _run_timezone_update(
        self, session_state: Dict[str, Any], timezone_value: str
    ) -> None:
        """更新用户时区 (直接调用，0次 LLM)"""
        try:
            result = set_user_timezone.entrypoint(
                timezone=timezone_value,
                session_state=session_state,
            )
            if result.get("ok"):
                logger.info(f"[PrepareWorkflow] 时区更新成功: {timezone_value}")
                session_state["timezone_update_message"] = result.get("message", "")
                if result.get("state"):
                    session_state.setdefault("user", {}).update(result["state"])
            else:
                logger.warning(f"[PrepareWorkflow] 时区更新失败: {result.get('message')}")
        except Exception as e:
            logger.error(f"[PrepareWorkflow] 时区更新异常: {e}")

    def _store_pending_timezone_change(
        self, session_state: Dict[str, Any], timezone_value: str
    ) -> None:
        """记录待确认的时区提议"""
        try:
            result = store_timezone_proposal.entrypoint(
                timezone=timezone_value,
                session_state=session_state,
            )
            if result.get("ok"):
                logger.info(f"[PrepareWorkflow] 时区提议已记录: {timezone_value}")
                session_state["timezone_update_message"] = result.get("message", "")
                if result.get("state"):
                    session_state.setdefault("user", {}).update(result["state"])
            else:
                logger.warning(f"[PrepareWorkflow] 时区提议记录失败: {result.get('message')}")
        except Exception as e:
            logger.error(f"[PrepareWorkflow] 时区提议记录异常: {e}")

    def _consume_pending_timezone_confirmation(
        self, input_message: str, session_state: Dict[str, Any]
    ) -> bool:
        """同一会话中的简短 yes/no 回复优先消费待确认的时区变更"""
        pending_change = session_state.get("user", {}).get("pending_timezone_change")
        if not pending_change:
            return False
        if pending_change.get("origin_conversation_id") != self._get_current_conversation_id(
            session_state
        ):
            return False
        decision = self._match_short_confirmation_reply(input_message)
        if is_timezone_proposal_expired(pending_change):
            clear_result = clear_pending_timezone_proposal(session_state=session_state)
            if clear_result.get("state"):
                session_state.setdefault("user", {}).update(clear_result["state"])
            if decision:
                append_tool_result(
                    session_state,
                    tool_name="时区确认",
                    ok=False,
                    result_summary=PENDING_PROPOSAL_EXPIRED_MESSAGE,
                )
                logger.info("[PrepareWorkflow] 已向用户返回过期的时区确认提示")
                return True
            logger.info("[PrepareWorkflow] 已清理过期的时区提议")
            return False

        if not decision:
            clear_result = clear_pending_timezone_proposal(session_state=session_state)
            if clear_result.get("state"):
                session_state.setdefault("user", {}).update(clear_result["state"])
            logger.info("[PrepareWorkflow] 已清理未被确认的同会话时区提议")
            return False

        try:
            result = consume_timezone_confirmation.entrypoint(
                decision=decision,
                session_state=session_state,
            )
        except Exception as e:
            logger.error(f"[PrepareWorkflow] 时区确认消费异常: {e}")
            return False

        if not result.get("ok"):
            logger.info("[PrepareWorkflow] 当前消息未消费待确认时区变更")
            return False

        session_state["timezone_update_message"] = result.get("message", "")
        if result.get("state"):
            session_state.setdefault("user", {}).update(result["state"])
        logger.info("[PrepareWorkflow] 已消费待确认的时区变更")
        return True

    def _match_short_confirmation_reply(self, input_message: str) -> str:
        normalized = str(input_message or "").strip().lower()
        if not normalized or len(normalized) > 12 or " " in normalized:
            return ""
        return normalize_timezone_confirmation_decision(normalized)

    def _resolve_timezone_action(self, orchestrator: Dict[str, Any]) -> str:
        if "timezone_action" not in orchestrator:
            if orchestrator.get("need_timezone_update"):
                return "direct_set"
            return "none"

        action = str(orchestrator.get("timezone_action", "none") or "none").strip()
        if action in {"none", "direct_set", "proposal"}:
            return action
        return "none"

    def _should_force_direct_timezone_set(
        self,
        *,
        input_message: str,
        timezone_action: str,
        timezone_value: str,
    ) -> bool:
        if timezone_action != "proposal" or not timezone_value:
            return False

        raw_text = str(input_message or "").strip()
        if not raw_text:
            return False

        normalized_lower = " ".join(raw_text.lower().split())
        return any(
            pattern.search(raw_text) or pattern.search(normalized_lower)
            for pattern in _EXPLICIT_TIMEZONE_OVERRIDE_PATTERNS
        )

    def _get_current_conversation_id(self, session_state: Dict[str, Any]) -> str:
        conversation = session_state.get("conversation", {})
        return str(
            conversation.get("_id") or session_state.get("conversation_id", "")
        ).strip()

    def _run_url_extraction(
        self, input_message: str, session_state: Dict[str, Any]
    ) -> None:
        """
        提取消息中的 URL 并获取内容

        链接理解功能：自动检测用户消息中的 URL，获取其内容作为上下文
        """
        try:
            url_contents = extract_urls_content(input_message)
            if url_contents:
                session_state["url_context"] = [uc.to_dict() for uc in url_contents]
                session_state["url_context_str"] = format_url_context(url_contents)
                logger.info(f"[PrepareWorkflow] 提取了 {len(url_contents)} 个链接内容")
            else:
                logger.debug("[PrepareWorkflow] 消息中未检测到 URL")
        except Exception as e:
            logger.warning(f"[PrepareWorkflow] URL 提取失败: {e}")

    def _surface_calendar_import_entry_if_needed(
        self, input_message: str, session_state: Dict[str, Any]
    ) -> None:
        if not self._looks_like_calendar_import_intent(input_message):
            return

        link = None
        handoff_error = None
        if self._is_clawscale_business_context(session_state):
            payload = self._build_calendar_import_handoff_payload(session_state)
            if not payload:
                handoff_error = "missing_handoff_context"
            else:
                try:
                    link = create_calendar_import_handoff_link(payload)
                except Exception as exc:
                    handoff_error = str(exc) or exc.__class__.__name__
                    logger.warning(
                        "[PrepareWorkflow] Google Calendar handoff link create failed: %s",
                        handoff_error,
                    )

        if self._is_clawscale_business_context(session_state) and not link:
            append_tool_result(
                session_state,
                tool_name="日历导入入口",
                ok=False,
                result_summary=(
                    "暂时无法生成你的专属导入链接，请稍后再试。"
                    f"失败原因：{handoff_error or 'handoff_link_unavailable'}。"
                ),
            )
            return

        if not link:
            link = self._build_customer_web_url(_CALENDAR_IMPORT_PATH)
        append_tool_result(
            session_state,
            tool_name="日历导入入口",
            ok=True,
            result_summary=(
                "用户想导入 Google Calendar。请把这个入口链接发给用户："
                f"{link}。"
                "说明打开后登录或验证邮箱，然后点击 Start Google Calendar import 授权 Google。"
                "不要说导入已经完成。"
            ),
        )
        logger.info("[PrepareWorkflow] 已添加 Google Calendar 导入入口链接")

    def _latest_input_metadata(self, session_state: Dict[str, Any]) -> Dict[str, Any]:
        input_messages = (
            session_state.get("conversation", {})
            .get("conversation_info", {})
            .get("input_messages", [])
        )
        if not isinstance(input_messages, list):
            return {}
        for message in reversed(input_messages):
            metadata = message.get("metadata") if isinstance(message, dict) else None
            if isinstance(metadata, dict):
                return metadata
        return {}

    def _is_clawscale_business_context(self, session_state: Dict[str, Any]) -> bool:
        return self._latest_input_metadata(session_state).get("source") == "clawscale"

    def _build_calendar_import_handoff_payload(
        self, session_state: Dict[str, Any]
    ) -> Dict[str, str] | None:
        metadata = self._latest_input_metadata(session_state)
        business_protocol = metadata.get("business_protocol")
        if not isinstance(business_protocol, dict):
            business_protocol = {}
        customer = metadata.get("customer")
        if not isinstance(customer, dict):
            customer = {}

        source_customer_id = str(
            customer.get("id") or session_state.get("user", {}).get("id") or ""
        ).strip()
        payload = {
            "source_customer_id": source_customer_id,
            "tenant_id": str(business_protocol.get("tenant_id") or "").strip(),
            "channel_id": str(business_protocol.get("channel_id") or "").strip(),
            "end_user_id": str(business_protocol.get("end_user_id") or "").strip(),
            "external_id": str(business_protocol.get("external_id") or "").strip(),
            "gateway_conversation_id": str(
                business_protocol.get("gateway_conversation_id") or ""
            ).strip(),
            "business_conversation_key": str(
                business_protocol.get("business_conversation_key") or ""
            ).strip(),
        }
        if not all(payload.values()):
            return None
        return payload

    def _looks_like_calendar_import_intent(self, input_message: str) -> bool:
        text = str(input_message or "").strip()
        if not text:
            return False
        if any(pattern.search(text) for pattern in _REMINDER_FIRST_PATTERNS):
            return False
        return any(pattern.search(text) for pattern in _CALENDAR_IMPORT_INTENT_PATTERNS)

    def _build_customer_web_url(self, path: str) -> str:
        for key in (
            "DOMAIN_CLIENT",
            "NEXT_PUBLIC_COKE_API_URL",
            "NEXT_PUBLIC_API_URL",
            "COKE_WEB_ALLOWED_ORIGIN",
        ):
            base_url = os.environ.get(key, "").strip().rstrip("/")
            if base_url:
                return f"{base_url}{path}"
        return path

    async def _run_reminder_detect(
        self,
        input_message: str,
        session_state: Dict[str, Any],
        orchestrator: Dict[str, Any],
    ) -> None:
        """执行提醒检测"""
        try:
            # 设置 session_state 供 visible_reminder_tool 使用
            set_reminder_session_state(session_state)

            # 续期锁
            self._renew_lock_if_needed(session_state)

            if self._should_use_deterministic_create_before_detector(input_message):
                if self._try_simple_reminder_create_fallback(
                    input_message,
                    session_state,
                ):
                    logger.info(
                        "[PrepareWorkflow] ReminderDetectAgent 前确定性提醒创建成功"
                    )
                    return

            # 构建并执行 ReminderDetectAgent
            reminder_input = self._build_reminder_input(input_message, session_state)
            logger.debug(f"[PrepareWorkflow] ReminderDetectAgent LLM INPUT")

            reminder_response = await asyncio.wait_for(
                reminder_detect_agent.arun(
                    input=reminder_input,
                    session_state=session_state,
                ),
                timeout=_PREPARE_REMINDER_DETECT_TIMEOUT_SECONDS,
            )

            # 记录用量
            if reminder_response and hasattr(reminder_response, "metrics"):
                usage_tracker.record_from_metrics(
                    agent_name="ReminderDetectAgent",
                    metrics=reminder_response.metrics,
                    user_id=str(session_state.get("user", {}).get("id", "")),
                    session_id=session_state.get("conversation_id"),
                    workflow_name="PrepareWorkflow",
                )

            # 记录结果
            self._log_reminder_result(reminder_response, session_state)

        except asyncio.TimeoutError:
            logger.error(
                "ReminderDetectAgent 执行超时: timeout=%.1fs",
                _PREPARE_REMINDER_DETECT_TIMEOUT_SECONDS,
            )
            session_state["prepare_reminder_detect_timeout"] = True
            if self._try_simple_reminder_create_fallback(
                input_message,
                session_state,
            ):
                return
            append_tool_result(
                session_state,
                tool_name="提醒操作",
                ok=False,
                result_summary="提醒操作失败：提醒识别超时，未能完成提醒设置",
                extra_notes="action=detect; error_code=ReminderDetectTimeout",
            )
        except Exception as e:
            logger.error(f"ReminderDetectAgent 执行失败: {e}")
            # 提醒检测失败不影响主流程

    def _renew_lock_if_needed(self, session_state: Dict[str, Any]) -> None:
        """如果有锁信息则续期"""
        lock_id = session_state.get("lock_id")
        conversation_id = session_state.get("conversation_id")
        if lock_id and conversation_id:
            from dao.lock import MongoDBLockManager

            lock_manager = MongoDBLockManager()
            lock_manager.renew_lock(
                "conversation", conversation_id, lock_id, timeout=180
            )
            logger.debug("[PrepareWorkflow] 锁续期成功 (ReminderDetectAgent 前)")

    def _log_reminder_result(
        self,
        reminder_response,
        session_state: Dict[str, Any],
    ) -> None:
        """记录提醒检测结果"""
        if reminder_response:
            tools_info = getattr(reminder_response, "tools", None)
            if tools_info:
                logger.debug(
                    f"[PrepareWorkflow] ReminderDetectAgent 工具调用: {len(tools_info)} 次"
                )
            else:
                logger.debug("[PrepareWorkflow] ReminderDetectAgent 未调用工具")

        logger.info("ReminderDetectAgent 执行完成")

        tool_results = session_state.get("tool_results", [])
        reminder_results = [r for r in tool_results if r.get("tool_name") == "提醒操作"]
        if reminder_results:
            last = reminder_results[-1]
            logger.info(f"ReminderDetectAgent 结果: {last.get('result_summary', '')}")
            if not last.get("ok", True):
                logger.warning(
                    f"[PrepareWorkflow] 用户意图未被满足: result={last.get('result_summary')}"
                )
        else:
            logger.warning(
                "[PrepareWorkflow] ReminderDetectAgent 执行完成但未调用 visible_reminder_tool，"
                "可能是 LLM 判断为普通对话而非提醒操作请求"
            )

    def _try_simple_reminder_create_fallback(
        self,
        input_message: str,
        session_state: Dict[str, Any],
    ) -> bool:
        operations = self._parse_simple_reminder_creates(input_message, session_state)
        if not operations:
            return False
        try:
            entrypoint = getattr(visible_reminder_tool, "entrypoint", visible_reminder_tool)
            entrypoint = getattr(entrypoint, "raw_function", entrypoint)
            if len(operations) == 1:
                operation = operations[0]
                result = entrypoint(
                    action="create",
                    title=operation["title"],
                    trigger_at=operation["trigger_at"],
                    rrule=operation["rrule"],
                )
            else:
                result = entrypoint(action="batch", operations=operations)
            logger.info(
                "[PrepareWorkflow] ReminderDetectAgent 超时后简单提醒 fallback 成功: %s",
                result,
            )
            return True
        except Exception:
            logger.exception(
                "[PrepareWorkflow] ReminderDetectAgent 超时后简单提醒 fallback 失败"
            )
            return False

    def _should_use_deterministic_create_before_detector(self, input_message: str) -> bool:
        return self._looks_like_implicit_reminder_intent(
            input_message
        ) and not self._looks_like_explicit_reminder_intent(input_message)

    def _parse_simple_reminder_creates(
        self,
        input_message: str,
        session_state: Dict[str, Any],
    ) -> list[dict[str, str | None]]:
        text = str(input_message or "").replace("：", ":").strip()

        time_matches = (
            list(_SIMPLE_TIME_REMINDER_PATTERN.finditer(text))
            if self._looks_like_reminder_intent(text)
            else []
        )

        timezone_name = self._get_user_timezone_name(session_state)
        try:
            tzinfo = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            logger.warning(
                "[PrepareWorkflow] 简单提醒 fallback 遇到无效时区: %s",
                timezone_name,
            )
            return []

        now = datetime.now(tzinfo)
        operations: list[dict[str, str | None]] = []
        for index, time_match in enumerate(time_matches):
            segment_start = self._previous_clause_boundary(text, time_match.start())
            segment_end = (
                time_matches[index + 1].start()
                if index + 1 < len(time_matches)
                else len(text)
            )
            title = self._extract_simple_reminder_title_after_time(
                text[time_match.end() : segment_end]
            )
            if not title:
                continue

            hour = int(time_match.group("hour"))
            minute = int(time_match.group("minute"))
            trigger_at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if trigger_at <= now:
                trigger_at += timedelta(days=1)

            recurrence_segment = text[segment_start : time_match.start()]
            operations.append(
                {
                    "action": "create",
                    "title": title,
                    "trigger_at": trigger_at.isoformat(),
                    "rrule": (
                        "FREQ=DAILY"
                        if self._segment_has_simple_recurrence(recurrence_segment)
                        else None
                    ),
                }
            )
        if operations:
            return operations
        operations = self._parse_chinese_time_reminder_creates(text, now)
        if operations:
            return operations
        return self._parse_deadline_reminder_creates(text, now)

    def _parse_chinese_time_reminder_creates(
        self,
        text: str,
        now: datetime,
    ) -> list[dict[str, str | None]]:
        if not self._looks_like_reminder_intent(text):
            return []

        operations: list[dict[str, str | None]] = []
        time_matches = list(_SIMPLE_CHINESE_TIME_REMINDER_PATTERN.finditer(text))
        for index, time_match in enumerate(time_matches):
            hour = self._parse_simple_time_number(time_match.group("hour"))
            minute = self._parse_simple_minute(time_match.group("minute"))
            if hour is None or minute is None:
                continue
            hour = self._apply_day_period(hour, time_match.group("period") or "")
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                continue

            segment_start = self._previous_clause_boundary(text, time_match.start())
            segment_end = (
                time_matches[index + 1].start()
                if index + 1 < len(time_matches)
                else len(text)
            )
            title = self._extract_simple_reminder_title_after_time(
                text[time_match.end() : segment_end]
            )
            if not title:
                continue

            trigger_at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if trigger_at <= now:
                trigger_at += timedelta(days=1)

            recurrence_segment = text[segment_start : time_match.start()]
            operations.append(
                {
                    "action": "create",
                    "title": title,
                    "trigger_at": trigger_at.isoformat(),
                    "rrule": (
                        "FREQ=DAILY"
                        if self._segment_has_simple_recurrence(recurrence_segment)
                        else None
                    ),
                }
            )
        return operations

    def _parse_simple_time_number(self, value: str | None) -> int | None:
        text = str(value or "").strip()
        if not text:
            return None
        if text.isdigit():
            return int(text)
        digits = {
            "零": 0,
            "〇": 0,
            "一": 1,
            "二": 2,
            "两": 2,
            "三": 3,
            "四": 4,
            "五": 5,
            "六": 6,
            "七": 7,
            "八": 8,
            "九": 9,
        }
        if text == "十":
            return 10
        if "十" in text:
            left, _, right = text.partition("十")
            tens = digits.get(left, 1 if not left else None)
            ones = digits.get(right, 0 if not right else None)
            if tens is None or ones is None:
                return None
            return tens * 10 + ones
        return digits.get(text)

    def _parse_simple_minute(self, value: str | None) -> int | None:
        if value is None or value == "":
            return 0
        if value == "半":
            return 30
        return self._parse_simple_time_number(value)

    def _apply_day_period(self, hour: int, period: str) -> int:
        if period in {"下午", "晚上", "今晚", "今天晚上"} and 1 <= hour < 12:
            return hour + 12
        if period == "中午" and 1 <= hour < 11:
            return hour + 12
        return hour

    def _parse_deadline_reminder_creates(
        self,
        text: str,
        now: datetime,
    ) -> list[dict[str, str | None]]:
        deadline_match = _TOMORROW_WORK_END_DEADLINE_PATTERN.search(text)
        if not deadline_match:
            return []
        title = self._clean_deadline_reminder_title(deadline_match.group("title"))
        if not title:
            return []

        trigger_at = (now + timedelta(days=1)).replace(
            hour=17,
            minute=0,
            second=0,
            microsecond=0,
        )
        return [
            {
                "action": "create",
                "title": title,
                "trigger_at": trigger_at.isoformat(),
                "rrule": None,
            }
        ]

    def _previous_clause_boundary(self, text: str, position: int) -> int:
        boundary = 0
        for separator in "，,。；;！？!?\n":
            index = text.rfind(separator, 0, position)
            if index >= boundary:
                boundary = index + 1
        return boundary

    def _segment_has_simple_recurrence(self, segment: str) -> bool:
        return bool(re.search(r"每天|每日|每个小时|每小时|每周|每月", segment))

    def _extract_simple_reminder_title_after_time(self, suffix: str) -> str:
        title = str(suffix or "").strip()
        title = re.sub(r"^(提醒我|提醒一下我|提醒|叫我|喊我|通知我|让我|帮我|记得)+", "", title)
        title = re.split(r"[，,。；;！？!?\n]", title, maxsplit=1)[0]
        title = re.sub(r"^(一个是|一是|二是|三是|还有|再|去|要|开始)+", "", title).strip()
        return self._clean_simple_reminder_title(title)

    def _clean_deadline_reminder_title(self, raw_title: str) -> str:
        title = str(raw_title or "").strip()
        title = re.sub(r"^(最近|最近要|我最近要|我想|我想要|我要|要|需要|得|必须)+", "", title)
        return self._clean_simple_reminder_title(title)

    def _clean_simple_reminder_title(self, raw_title: str) -> str:
        title = str(raw_title or "").strip()
        title = re.sub(r"^(一下|下|去|要|：|:|\s)+", "", title)
        title = re.sub(r"(可以吗|可以么|行吗|好吗|好么|吗|么|呀|呢|吧|哈)+$", "", title)
        return title.strip(" ，。！？!?；;")

    def _get_user_timezone_name(self, session_state: Dict[str, Any]) -> str:
        user = session_state.get("user") or {}
        timezone_name = (
            user.get("effective_timezone")
            or user.get("timezone")
            or "Asia/Shanghai"
        )
        return str(timezone_name)

    def _build_reminder_input(self, current_message: str, session_state: dict) -> str:
        """
        构建 ReminderDetectAgent 的输入：当前消息 + 最近5条对话上下文

        Args:
            current_message: 当前用户消息
            session_state: 会话状态

        Returns:
            渲染后的输入字符串
        """
        # 获取最近5条聊天记录
        chat_history = (
            session_state.get("conversation", {})
            .get("conversation_info", {})
            .get("chat_history", [])
        )
        recent_messages = chat_history[-5:] if len(chat_history) > 5 else chat_history

        # 格式化最近对话
        if recent_messages:
            recent_chat_context = messages_to_str(recent_messages)
        else:
            recent_chat_context = "（无历史消息）"

        # 获取当前时间
        time_str = (
            session_state.get("conversation", {})
            .get("conversation_info", {})
            .get("time_str", "")
        )
        user = session_state.get("user", {})
        timezone = (
            user.get("effective_timezone")
            or user.get("timezone")
            or "unknown"
        )

        # 渲染模板
        return self.REMINDER_CONTEXT_TEMPLATE.format(
            time_str=time_str,
            timezone=timezone,
            recent_chat_context=recent_chat_context,
            current_message=current_message,
        )

    def _render_template(self, template: str, context: Dict[str, Any]) -> str:
        """渲染模板字符串"""
        try:
            return render_prompt_template(template, context)
        except KeyError as e:
            logger.warning(f"模板渲染缺少字段: {e}")
            return template

    def _map_to_query_rewrite(
        self, session_state: Dict[str, Any], orchestrator: Dict[str, Any]
    ) -> None:
        """
        将 Orchestrator 输出映射到旧的 query_rewrite 字段，保持兼容性
        """
        params = orchestrator.get("context_retrieve_params", {})
        session_state["query_rewrite"] = {
            "InnerMonologue": orchestrator.get("inner_monologue", ""),
            "CharacterSettingQueryQuestion": params.get("character_setting_query", ""),
            "CharacterSettingQueryKeywords": params.get(
                "character_setting_keywords", ""
            ),
            "UserProfileQueryQuestion": params.get("user_profile_query", ""),
            "UserProfileQueryKeywords": params.get("user_profile_keywords", ""),
            "CharacterKnowledgeQueryQuestion": params.get(
                "character_knowledge_query", ""
            ),
            "CharacterKnowledgeQueryKeywords": params.get(
                "character_knowledge_keywords", ""
            ),
        }

    def _get_default_orchestrator(self) -> Dict[str, Any]:
        """获取默认的 orchestrator 结构"""
        return {
            "inner_monologue": "",
            "need_context_retrieve": True,
            "context_retrieve_params": {
                "character_setting_query": "",
                "character_setting_keywords": "",
                "user_profile_query": "",
                "user_profile_keywords": "",
                "character_knowledge_query": "",
                "character_knowledge_keywords": "",
            },
            "need_reminder_detect": False,
            "need_web_search": False,
            "web_search_query": "",
            "need_timezone_update": False,
            "timezone_action": "none",
            "timezone_value": "",
        }

    def _get_default_query_rewrite(self) -> Dict[str, str]:
        """获取默认的 query_rewrite 结构（兼容旧代码）"""
        return {
            "InnerMonologue": "",
            "CharacterSettingQueryQuestion": "",
            "CharacterSettingQueryKeywords": "",
            "UserProfileQueryQuestion": "",
            "UserProfileQueryKeywords": "",
            "CharacterKnowledgeQueryQuestion": "",
            "CharacterKnowledgeQueryKeywords": "",
        }

    def _get_default_context_retrieve(self) -> Dict[str, str]:
        """获取默认的 context_retrieve 结构"""
        return {
            "character_global": "",
            "character_private": "",
            "user": "",
            "character_knowledge": "",
            "confirmed_reminders": "",
            "relevant_history": "",
        }
