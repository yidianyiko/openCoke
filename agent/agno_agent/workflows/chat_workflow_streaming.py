# -*- coding: utf-8 -*-
"""
ChatWorkflow Streaming Version - 流式回复生成

支持流式输出，当检测到完整的一条消息时立即返回，
而不是等待所有内容生成完毕。

核心思路：
1. 不使用 output_schema，让 LLM 按特定格式输出
2. 实时解析流式内容，检测完整消息
3. 检测到完整消息时立即 yield

输出格式约定（让 LLM 按此格式输出）：
[TEXT]消息内容[/TEXT]
[VOICE emotion=高兴]语音内容[/VOICE]
[PHOTO]照片ID[/PHOTO]
"""

import re
import logging
from typing import Any, Dict, Generator, Optional

from agno.agent import Agent
from agno.models.deepseek import DeepSeek

from agent.prompt.chat_taskprompt import (
    TASKPROMPT_微信对话,
    TASKPROMPT_微信对话_推理要求_纯文本,
)
from agent.prompt.chat_contextprompt import (
    CONTEXTPROMPT_时间,
    CONTEXTPROMPT_历史对话,
    CONTEXTPROMPT_历史对话_精简,
    CONTEXTPROMPT_最新聊天消息,
    CONTEXTPROMPT_人物信息,
    CONTEXTPROMPT_人物资料,
    CONTEXTPROMPT_用户资料,
    CONTEXTPROMPT_待办提醒,
    CONTEXTPROMPT_人物知识和技能,
    CONTEXTPROMPT_人物状态,
    CONTEXTPROMPT_当前目标,
    CONTEXTPROMPT_当前的人物关系,
    CONTEXTPROMPT_系统提醒触发,
    CONTEXTPROMPT_主动消息触发,
    CONTEXTPROMPT_提醒工具结果,
)
from agent.prompt.agent_instructions_prompt import INSTRUCTIONS_CHAT_RESPONSE

logger = logging.getLogger(__name__)


# 流式 JSON 解析说明
# LLM 输出 JSON 格式，我们流式解析 MultiModalResponses 数组中的每个元素


class StreamingChatWorkflow:
    """
    流式回复生成 Workflow
    
    与 ChatWorkflow 的区别：
    - 使用 stream=True 调用 Agent
    - 实时解析输出，检测到完整消息立即 yield
    - 不使用 output_schema，改用标签格式
    """
    
    # User prompt 模板组合 - 基础部分（包含完整历史对话，用于用户消息）
    userp_template_base = (
        TASKPROMPT_微信对话 +
        CONTEXTPROMPT_时间 +
        CONTEXTPROMPT_人物信息 +
        CONTEXTPROMPT_人物资料 +
        CONTEXTPROMPT_用户资料 +
        CONTEXTPROMPT_待办提醒 +
        CONTEXTPROMPT_人物知识和技能 +
        CONTEXTPROMPT_人物状态 +
        CONTEXTPROMPT_当前目标 +
        CONTEXTPROMPT_当前的人物关系 +
        CONTEXTPROMPT_历史对话
    )
    
    # User prompt 模板组合 - 精简版（只包含最近对话，用于主动消息/提醒）
    userp_template_base_lite = (
        TASKPROMPT_微信对话 +
        CONTEXTPROMPT_时间 +
        CONTEXTPROMPT_人物信息 +
        CONTEXTPROMPT_人物资料 +
        CONTEXTPROMPT_用户资料 +
        CONTEXTPROMPT_待办提醒 +
        CONTEXTPROMPT_人物知识和技能 +
        CONTEXTPROMPT_人物状态 +
        CONTEXTPROMPT_当前目标 +
        CONTEXTPROMPT_当前的人物关系 +
        CONTEXTPROMPT_历史对话_精简
    )
    
    # 消息来源相关的上下文模板
    userp_template_user_message = CONTEXTPROMPT_最新聊天消息  # 用户消息
    userp_template_reminder = CONTEXTPROMPT_系统提醒触发      # 提醒触发
    userp_template_future = CONTEXTPROMPT_主动消息触发        # 主动消息
    
    # V2.7 新增：提醒工具结果上下文模板
    userp_template_reminder_result = CONTEXTPROMPT_提醒工具结果
    
    # 任务要求部分
    userp_template_task = (
        TASKPROMPT_微信对话_推理要求_纯文本       
    )
    
    # 兼容旧代码：默认用户消息模板
    userp_template = (
        userp_template_base +
        userp_template_user_message +
        userp_template_task
    )
    
    def __init__(self):
        """初始化流式 Agent（不使用 output_schema）"""
        self.agent = Agent(
            id="chat-response-agent-streaming",
            name="ChatResponseAgentStreaming",
            model=DeepSeek(id="deepseek-chat"),
            instructions=INSTRUCTIONS_CHAT_RESPONSE,
            markdown=False,
            # 不使用 output_schema，让我们自己解析
        )
    
    async def run_stream(
        self,
        input_message: str,
        session_state: Optional[Dict[str, Any]] = None
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
        if message_source == "reminder":
            source_template = self.userp_template_reminder
            base_template = self.userp_template_base_lite  # 提醒消息使用精简版
        elif message_source == "future":
            source_template = self.userp_template_future
            base_template = self.userp_template_base_lite  # 主动消息使用精简版
        else:
            source_template = self.userp_template_user_message
            base_template = self.userp_template_base  # 用户消息使用完整版
        
        # V2.7 新增：检查是否有提醒工具结果，如有则添加到上下文
        reminder_result_template = ""
        if "【提醒设置工具消息】" in session_state and session_state["【提醒设置工具消息】"]:
            reminder_result_template = self.userp_template_reminder_result
            logger.info(f"[ChatWorkflow] 添加提醒工具结果上下文: {session_state['【提醒设置工具消息】']}")
        
        # 组合完整模板
        full_template = base_template + source_template + reminder_result_template + self.userp_template_task
        
        # 渲染 user prompt
        try:
            rendered_userp = self._render_template(full_template, session_state)
        except Exception as e:
            logger.warning(f"User prompt 渲染失败: {e}")
            rendered_userp = input_message
        
        # 打印实际发送给 LLM 的 prompt（便于调试）
        logger.info(f"[ChatWorkflow] message_source={message_source}, 使用模板: {'CONTEXTPROMPT_主动消息触发' if message_source == 'future' else 'CONTEXTPROMPT_系统提醒触发' if message_source == 'reminder' else 'CONTEXTPROMPT_最新聊天消息'}")
        logger.debug(f"[ChatWorkflow] LLM INPUT (len={len(rendered_userp)}):\n{'='*50}\n{rendered_userp}\n{'='*50}")
        
        # 累积的响应文本
        accumulated_text = ""
        # 已经 yield 过的消息数量（避免重复）
        yielded_count = 0
        
        try:
            # 异步流式调用 Agent (Agno v2 arun with stream=True returns AsyncIterator)
            async for chunk in self.agent.arun(
                input=rendered_userp,
                session_state=session_state,
                stream=True
            ):
                # 提取 chunk 中的文本内容
                chunk_text = self._extract_chunk_text(chunk)
                if chunk_text:
                    accumulated_text += chunk_text
                    
                    # 尝试解析已累积的文本，检测完整消息
                    messages = self._parse_messages(accumulated_text)
                    
                    # yield 新检测到的消息
                    for i in range(yielded_count, len(messages)):
                        yield {
                            "type": "message",
                            "data": messages[i]
                        }
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
                    "inner_monologue": inner_monologue
                }
            }
            
            logger.info(f"ChatResponseAgent 流式执行完成，共 {yielded_count} 条消息")
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"ChatResponseAgent 流式执行失败: {error_msg}")
            
            # 检测 "Content Exists Risk" 错误 - 内容安全审核失败
            # 简单处理：标记为 content_blocked，不写入历史记录
            if "Content Exists Risk" in error_msg:
                logger.warning(f"检测到内容安全审核失败 (Content Exists Risk)，不写入历史记录")
                yield {
                    "type": "content_blocked",
                    "data": {"error": error_msg}
                }
            else:
                yield {
                    "type": "error",
                    "data": {"error": error_msg}
                }
    
    async def run(
        self,
        input_message: str,
        session_state: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        异步非流式执行（兼容原接口）
        
        收集所有流式输出后一次性返回
        """
        messages = []
        full_response = ""
        inner_monologue = ""
        
        async for event in self.run_stream(input_message, session_state):
            if event["type"] == "message":
                messages.append(event["data"])
            elif event["type"] == "done":
                full_response = event["data"].get("full_response", "")
                inner_monologue = event["data"].get("inner_monologue", "")
        
        # 转换为原 ChatWorkflow 的返回格式（精简版）
        # V2 重构：不再包含 RelationChange 和 FutureResponse，这些移至 PostAnalyzeWorkflow
        multimodal_responses = []
        for msg in messages:
            multimodal_responses.append({
                "type": msg.get("type", "text"),
                "content": msg.get("content", ""),
                "emotion": msg.get("emotion")
            })
        
        return {
            "content": {
                "InnerMonologue": inner_monologue,
                "MultiModalResponses": multimodal_responses,
                "ChatCatelogue": "",
            },
            "session_state": session_state
        }
    
    def _render_template(self, template: str, context: Dict[str, Any]) -> str:
        """渲染模板字符串"""
        try:
            return template.format(**context)
        except KeyError as e:
            logger.warning(f"模板渲染缺少字段: {e}")
            return template
    
    def _extract_chunk_text(self, chunk) -> str:
        """从流式 chunk 中提取文本内容"""
        if hasattr(chunk, 'content') and chunk.content:
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
            inner_monologue = inner_monologue.replace('\\n', '\n').replace('\\"', '"').replace('\\\\', '\\')
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
            content = content.replace('\\n', '\n').replace('\\"', '"').replace('\\\\', '\\')
            
            if content:
                msg = {
                    "type": msg_type,
                    "content": content
                }
                if emotion:
                    msg["emotion"] = emotion
                messages.append(msg)
        
        return messages
