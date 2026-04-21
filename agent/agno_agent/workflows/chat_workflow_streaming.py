# -*- coding: utf-8 -*-
"""
ChatWorkflow Streaming Version-流式回复生成

支持流式输出，当检测到完整的一条消息时立即返回，
而不是等待所有内容生成完毕.

核心思路：
1. 不使用 output_schema，让 LLM 按特定格式输出
2. 实时解析流式内容，检测完整消息
3. 检测到完整消息时立即 yield

输出格式约定（让 LLM 按此格式输出）：
[TEXT]消息内容[/TEXT]
[VOICE emotion=高兴]语音内容[/VOICE]
[PHOTO]照片ID[/PHOTO]
"""

import logging
import re
from typing import Any, Dict, Optional

from agno.agent import Agent

from agent.agno_agent.model_factory import create_llm_model
from agent.prompt.agent_instructions_prompt import INSTRUCTIONS_CHAT_RESPONSE
from agent.prompt.chat_contextprompt import (
    CONTEXTPROMPT_主动消息触发,
    CONTEXTPROMPT_人物信息,
    CONTEXTPROMPT_人物状态,
    CONTEXTPROMPT_人物知识和技能,
    CONTEXTPROMPT_人物资料,
    CONTEXTPROMPT_历史对话_精简,
    CONTEXTPROMPT_当前的人物关系,
    CONTEXTPROMPT_当前目标,
    CONTEXTPROMPT_提醒未执行,
    CONTEXTPROMPT_时间,
    CONTEXTPROMPT_最新聊天消息,
    CONTEXTPROMPT_最近的历史对话,
    CONTEXTPROMPT_用户资料,
    CONTEXTPROMPT_系统提醒触发,
    CONTEXTPROMPT_防重复回复,
    get_message_source_context,
    get_relevant_history_context,
    get_reminders_context,
    get_tool_results_context,
    get_url_context,
    get_web_search_context,
)
from agent.prompt.chat_noticeprompt import NOTICE_常规注意事项_分段消息
from agent.prompt.rendering import render_prompt_template
from agent.prompt.chat_taskprompt import (
    TASKPROMPT_微信对话,
    TASKPROMPT_微信对话_推理要求_纯文本,
)
from agent.prompt.onboarding_prompt import get_onboarding_context
from agent.prompt.personality_prompt import CHAT_AGENT_PERSONALITY_MINIMAL

# Note: Usage tracking for streaming mode is not yet implemented.
# Metrics for ChatResponseAgent would need to be captured from the final chunk
# or through alternative means. For now, usage is tracked in PrepareWorkflow
# and PostAnalyzeWorkflow which use non-streaming agent calls.


logger = logging.getLogger(__name__)


# 流式 JSON 解析说明
# LLM 输出 JSON 格式，我们流式解析 MultiModalResponses 数组中的每个元素


class StreamingChatWorkflow:
    """
     流式回复生成 Workflow

     与 ChatWorkflow 的区别：
    -使用 stream=True 调用 Agent
    -实时解析输出，检测到完整消息立即 yield
    -不使用 output_schema，改用标签格式

     V2.7 优化：
    -待办提醒和相关历史对话按需加载（仅在有内容时添加到上下文）
    """

    # User prompt 模板组合-基础部分（不包含按需加载的上下文）
    # V2.7 优化：移除 CONTEXTPROMPT_待办提醒 和 CONTEXTPROMPT_历史最相关的十条对话，改为按需加载
    # V2.13 重构：
    #   - 使用 CHAT_AGENT_PERSONALITY_MINIMAL 替代完整版（去除与角色 system_prompt 重复的部分）
    #   - 人格规范放在角色信息后面（先定义“你是谁”，再定义“如何行为”）
    userp_template_base_core = (
        TASKPROMPT_微信对话
        + CONTEXTPROMPT_时间
        + CONTEXTPROMPT_人物信息
        + CHAT_AGENT_PERSONALITY_MINIMAL  # 精简版人格规范，放在角色信息后
        + CONTEXTPROMPT_人物资料
        + CONTEXTPROMPT_用户资料
        + CONTEXTPROMPT_人物知识和技能
        + CONTEXTPROMPT_人物状态
        + CONTEXTPROMPT_当前目标
        + CONTEXTPROMPT_当前的人物关系
    )

    # User prompt 模板组合-基础部分（包含完整历史对话，用于用户消息）
    # 保留旧属性以兼容
    userp_template_base = userp_template_base_core + CONTEXTPROMPT_最近的历史对话

    # User prompt 模板组合-精简版（只包含最近对话，用于主动消息/提醒）
    userp_template_base_lite = userp_template_base_core + CONTEXTPROMPT_历史对话_精简

    # 消息来源相关的上下文模板
    userp_template_user_message = CONTEXTPROMPT_最新聊天消息  # 用户消息
    userp_template_reminder = CONTEXTPROMPT_系统提醒触发  # 提醒触发
    userp_template_future = CONTEXTPROMPT_主动消息触发  # 主动消息

    # V2.8 新增：提醒未执行提示模板（当检测到提醒意图但工具未调用时使用）
    userp_template_reminder_not_executed = CONTEXTPROMPT_提醒未执行

    # 消息分段注意事项模板（用于主动消息和提醒消息）
    userp_template_notice_segmentation = NOTICE_常规注意事项_分段消息

    # 任务要求部分
    userp_template_task = TASKPROMPT_微信对话_推理要求_纯文本

    # 兼容旧代码：默认用户消息模板
    userp_template = (
        userp_template_base + userp_template_user_message + userp_template_task
    )

    def __init__(self):
        """初始化流式 Agent

        添加 use_json_mode=True 避免 DeepSeek structured output 解析失败
        """
        self.agent = Agent(
            id="chat-response-agent-streaming",
            name="ChatResponseAgentStreaming",
            model=create_llm_model(max_tokens=4096, role="chat_response"),
            instructions=INSTRUCTIONS_CHAT_RESPONSE,
            use_json_mode=True,
            markdown=False,
            # 上下文压缩配置
            num_history_messages=15,  # 保留最近 15 条消息
            compress_tool_results=True,  # 压缩工具结果
        )

    async def run_stream(
        self, input_message: str, session_state: Optional[Dict[str, Any]] = None
    ):
        """
        异步流式执行回复生成

        Args:
            input_message: 用户输入消息
            session_state: 上下文状态

        Yields:
            检测到的完整消息，格式：
            {
                "type": "message",
                "data": {"type": "text/voice/photo", "content": "...", "emotion": "..."}
            }
            或
            {
                "type": "done",
                "data": {"full_response": "完整响应文本"}
            }
        """
        session_state = session_state or {}

        # 根据消息来源选择不同的上下文模板和基础模板
        message_source = session_state.get("message_source", "user")

        # V2.12 新增：根据消息来源生成说明（代码层面直接注入，LLM 不需要判断）
        message_source_context = get_message_source_context(
            message_source, session_state
        )

        notice_segmentation = ""  # 消息分段注意事项（仅用于主动消息和提醒）
        deferred_kind = session_state.get("system_message_metadata", {}).get("kind")
        if message_source == "deferred_action":
            if deferred_kind == "user_reminder":
                source_template = self.userp_template_reminder
            else:
                source_template = self.userp_template_future
            base_template = self.userp_template_base_lite
            notice_segmentation = self.userp_template_notice_segmentation
        elif message_source == "reminder":
            source_template = self.userp_template_reminder
            base_template = self.userp_template_base_lite  # 提醒消息使用精简版
            notice_segmentation = self.userp_template_notice_segmentation
        elif message_source == "future":
            source_template = self.userp_template_future
            base_template = self.userp_template_base_lite  # 主动消息使用精简版
            notice_segmentation = self.userp_template_notice_segmentation
        else:
            source_template = self.userp_template_user_message
            base_template = self.userp_template_base  # 用户消息使用完整版

        # Generic tool results context (timezone, reminder, future tools)
        tool_results_context = get_tool_results_context(session_state)
        if tool_results_context:
            logger.info("[ChatWorkflow] 添加系统操作结果上下文")

        # V2.8 guard：OrchestratorAgent 判断需要提醒检测，但工具未执行时，
        # 使用 CONTEXTPROMPT_提醒未执行 提示 LLM 不要假设提醒已创建
        reminder_not_executed_context = ""
        orchestrator = session_state.get("orchestrator", {})
        need_reminder = orchestrator.get("need_reminder_detect", False)
        if need_reminder and message_source == "user" and not tool_results_context:
            reminder_not_executed_context = self.userp_template_reminder_not_executed
            logger.warning(
                "[ChatWorkflow] OrchestratorAgent 判断 need_reminder_detect=True，但未找到提醒工具结果.添加提醒未执行提示"
            )

        # V2.7 优化：按需加载待办提醒和相关历史对话
        context_retrieve = session_state.get("context_retrieve", {})
        user_state = session_state.get("user", {})
        user_nickname = (
            user_state.get("display_name")
            or user_state.get("name")
            or user_state.get("nickname")
            or "用户"
        )

        # 按需生成待办提醒上下文
        reminders_context = get_reminders_context(context_retrieve, user_nickname)

        # 联网搜索结果上下文
        web_search_context = get_web_search_context(session_state)
        if web_search_context:
            logger.info("[ChatWorkflow] 添加联网搜索结果上下文")

        # 链接内容上下文
        url_context = get_url_context(session_state)
        if url_context:
            logger.info("[ChatWorkflow] 添加链接内容上下文")

        # V2.15 新增：获取防重复回复提示（所有消息场景）
        anti_repeat_context = ""
        proactive_forbidden = session_state.get("proactive_forbidden_messages", "")
        if proactive_forbidden and proactive_forbidden.strip():
            anti_repeat_context = CONTEXTPROMPT_防重复回复

        # 按需生成相关历史对话上下文（仅用户消息场景）
        # V2.13 优化：传入最近历史对话字符串，过滤掉重复内容
        relevant_history_context = ""
        if message_source == "user":
            recent_history_str = (
                session_state.get("conversation", {})
                .get("conversation_info", {})
                .get("chat_history_str", "")
            )
            relevant_history_context = get_relevant_history_context(
                context_retrieve, recent_history_str
            )

        # V2.14 新增：新用户 onboarding 提示词（仅首次对话时注入）
        onboarding_context = ""
        if message_source == "user":
            is_new_user = session_state.get("is_new_user", False)
            onboarding_context = get_onboarding_context(is_new_user)
            if onboarding_context:
                logger.info("[ChatWorkflow] 新用户首次对话，注入 onboarding 提示词")

        # 组合完整模板
        # V2.13 重构：优化模板顺序，提升 LLM 注意力分配
        # V2.14 新增：onboarding 提示词放在基础上下文之前，优先级最高
        # V2.15 新增：防重复回复提示，放在注意事项后面
        # 新顺序：
        #   1. 消息来源说明 - 让 LLM 知道场景
        #   2. Onboarding 提示（仅新用户）- 高优先级指导
        #   3. 当前输入 - 提前，让 LLM 立即知道要回复什么
        #   4. 基础上下文 - 角色信息、人格规范、历史对话等
        #   5. 补充上下文 - 待办提醒、相关历史
        #   6. 注意事项 - 分段注意等
        #   7. 防重复回复提示 - V2.15 新增
        #   8. 提醒工具结果 - 放在输出格式前
        #   9. 输出格式要求 - 放最后，利用 recency effect
        full_template = (
            message_source_context
            + "\n"
            + (
                onboarding_context + "\n" if onboarding_context else ""
            )  # V2.14: Onboarding
            + source_template  # 当前输入提前
            + "\n"
            + base_template
            + ("\n" + reminders_context if reminders_context else "")
            + ("\n" + relevant_history_context if relevant_history_context else "")
            + ("\n" + web_search_context if web_search_context else "")  # 联网搜索结果
            + ("\n" + url_context if url_context else "")  # 链接内容
            + ("\n" + notice_segmentation if notice_segmentation else "")
            + (
                "\n" + anti_repeat_context if anti_repeat_context else ""
            )  # V2.15: 防重复
        )
        # 注意：userp_template_task 和 reminder_result_context 在渲染后追加

        # 渲染 user prompt
        try:
            rendered_userp = self._render_template(full_template, session_state)
            # 工具结果上下文放在输出格式前
            if tool_results_context:
                rendered_userp = rendered_userp + "\n" + tool_results_context
            if reminder_not_executed_context:
                rendered_userp = rendered_userp + "\n" + reminder_not_executed_context
            # 输出格式要求放最后
            rendered_userp = (
                rendered_userp
                + "\n"
                + self._render_template(self.userp_template_task, session_state)
            )
        except Exception as e:
            logger.warning(f"User prompt 渲染失败: {e}")
            rendered_userp = input_message

        # 打印实际发送给 LLM 的 prompt（便于调试）
        logger.info(
            f"[ChatWorkflow] message_source={message_source}, 使用模板: "
            f"{'CONTEXTPROMPT_系统提醒触发' if (message_source == 'reminder' or (message_source == 'deferred_action' and deferred_kind == 'user_reminder')) else 'CONTEXTPROMPT_主动消息触发' if (message_source == 'future' or (message_source == 'deferred_action' and deferred_kind == 'proactive_followup')) else 'CONTEXTPROMPT_最新聊天消息'}"
        )
        logger.debug(
            f"[ChatWorkflow] LLM INPUT (len={len(rendered_userp)}):\n{'='*50}\n{rendered_userp}\n{'='*50}"
        )

        # 累积的响应文本
        accumulated_text = ""
        # 已经 yield 过的消息数量（避免重复）
        yielded_count = 0

        try:
            # 异步流式调用 Agent (Agno v2 arun with stream=True returns AsyncIterator)
            async for chunk in self.agent.arun(
                input=rendered_userp, session_state=session_state, stream=True
            ):
                # 提取 chunk 中的文本内容
                chunk_text = self._extract_chunk_text(chunk)
                if chunk_text:
                    accumulated_text += chunk_text

                    # 尝试解析已累积的文本，检测完整消息
                    messages = self._parse_messages(accumulated_text)

                    # yield 新检测到的消息
                    for i in range(yielded_count, len(messages)):
                        yield {"type": "message", "data": messages[i]}
                        yielded_count += 1
                        logger.info(f"流式输出消息: {messages[i]}")

            # 解析 InnerMonologue 用于调试
            inner_monologue = self._parse_inner_monologue(accumulated_text)
            if inner_monologue:
                logger.info(f"[ChatResponseAgent] InnerMonologue: {inner_monologue}")
                # 保存到 session_state 供后续使用（如果需要）
                session_state["last_inner_monologue"] = inner_monologue

            # 完成后，返回完整响应
            yield {
                "type": "done",
                "data": {
                    "full_response": accumulated_text,
                    "total_messages": yielded_count,
                    "inner_monologue": inner_monologue,
                },
            }

            logger.info(f"ChatResponseAgent 流式执行完成，共 {yielded_count} 条消息")

        except Exception as e:
            error_msg = str(e)
            logger.error(f"ChatResponseAgent 流式执行失败: {error_msg}")

            # 检测 "Content Exists Risk" 错误-内容安全审核失败
            # 简单处理：标记为 content_blocked，不写入历史记录
            if "Content Exists Risk" in error_msg:
                logger.warning(
                    "检测到内容安全审核失败 (Content Exists Risk)，不写入历史记录"
                )
                yield {"type": "content_blocked", "data": {"error": error_msg}}
            else:
                yield {"type": "error", "data": {"error": error_msg}}

    async def run(
        self, input_message: str, session_state: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        异步非流式执行（兼容原接口）

        收集所有流式输出后一次性返回
        """
        messages = []
        inner_monologue = ""

        async for event in self.run_stream(input_message, session_state):
            if event["type"] == "message":
                messages.append(event["data"])
            elif event["type"] == "done":
                inner_monologue = event["data"].get("inner_monologue", "")

        # 转换为原 ChatWorkflow 的返回格式（精简版）
        # V2 重构：不再包含 RelationChange 和 follow-up planning，这些移至 PostAnalyzeWorkflow
        multimodal_responses = []
        for msg in messages:
            multimodal_responses.append(
                {
                    "type": msg.get("type", "text"),
                    "content": msg.get("content", ""),
                    "emotion": msg.get("emotion"),
                }
            )

        return {
            "content": {
                "InnerMonologue": inner_monologue,
                "MultiModalResponses": multimodal_responses,
                "ChatCatelogue": "",
            },
            "session_state": session_state,
        }

    def _render_template(self, template: str, context: Dict[str, Any]) -> str:
        """渲染模板字符串"""
        try:
            return render_prompt_template(template, context)
        except KeyError as e:
            logger.warning(f"模板渲染缺少字段: {e}")
            return template

    def _extract_chunk_text(self, chunk) -> str:
        """从流式 chunk 中提取文本内容"""
        if hasattr(chunk, "content") and chunk.content:
            if isinstance(chunk.content, str):
                return chunk.content
        return ""

    def _parse_inner_monologue(self, text: str) -> str:
        """
        从 JSON 输出中解析 InnerMonologue

        Returns:
            InnerMonologue 内容，如果未找到则返回空字符串
        """
        # 匹配 "InnerMonologue": "..."
        pattern = r'"InnerMonologue"\s*:\s*"([^"]*)"'
        match = re.search(pattern, text)
        if match:
            inner_monologue = match.group(1)
            # 处理 JSON 转义字符
            inner_monologue = (
                inner_monologue.replace("\\n", "\n")
                .replace('\\"', '"')
                .replace("\\\\", "\\")
            )
            return inner_monologue
        return ""

    def _parse_messages(self, text: str) -> list:
        """
        从 JSON 流式输出中解析 MultiModalResponses 数组中的完整消息

        策略：使用正则匹配 JSON 数组中的完整对象

        Returns:
            解析出的消息列表
        """
        messages = []

        # 查找 MultiModalResponses 数组的内容
        # 匹配 "MultiModalResponses": [ ... ] 中的内容
        array_match = re.search(r'"MultiModalResponses"\s*:\s*\[', text)
        if not array_match:
            return messages

        # 从数组开始位置提取内容
        array_start = array_match.end()
        array_content = text[array_start:]

        # 匹配数组中的每个完整对象 {...}
        # 使用简单的正则匹配完整的 JSON 对象
        # 格式: {"type": "text", "content": "...", "emotion": "..."}
        object_pattern = r'\{\s*"type"\s*:\s*"([^"]+)"\s*,\s*"content"\s*:\s*"([^"]*)"(?:\s*,\s*"emotion"\s*:\s*"([^"]*)")?\s*\}'

        for match in re.finditer(object_pattern, array_content):
            msg_type = match.group(1)
            content = match.group(2)
            emotion = match.group(3)

            # 处理 JSON 转义字符
            content = (
                content.replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\")
            )

            if content:
                msg = {"type": msg_type, "content": content}
                if emotion:
                    msg["emotion"] = emotion
                messages.append(msg)

        return messages
