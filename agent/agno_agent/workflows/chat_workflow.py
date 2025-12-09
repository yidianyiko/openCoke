# -*- coding: utf-8 -*-
"""
ChatWorkflow - 回复生成 Workflow

基于 PrepareWorkflow 的结果生成多模态回复

Requirements: 5.2
"""

import logging
from typing import Any, Dict, List, Optional

from agent.agno_agent.agents import chat_response_agent
from agent.prompt.chat_taskprompt import (
    TASKPROMPT_微信对话,
    TASKPROMPT_微信对话_推理要求_纯文本,
    TASKPROMPT_提醒识别,
)
from agent.prompt.chat_contextprompt import (
    CONTEXTPROMPT_时间,
    CONTEXTPROMPT_历史对话,
    CONTEXTPROMPT_最新聊天消息,
    CONTEXTPROMPT_人物资料,
    CONTEXTPROMPT_用户资料,
    CONTEXTPROMPT_待办提醒,
    CONTEXTPROMPT_人物知识和技能,
    CONTEXTPROMPT_人物状态,
    CONTEXTPROMPT_当前目标,
    CONTEXTPROMPT_当前的人物关系,
)

logger = logging.getLogger(__name__)


class ChatWorkflow:
    """
    回复生成 Workflow
    
    注意：这是自定义 Workflow 类，不继承 Agno Workflow。
    
    执行流程：
    1. 渲染 user prompt（包含时间、角色资料、用户资料、历史对话等）
    2. 调用 ChatResponseAgent 生成回复
    3. 返回 MultiModalResponses 和更新后的 session_state
    
    输入：
    - session_state["query_rewrite"] - 来自 PrepareWorkflow
    - session_state["context_retrieve"] - 来自 PrepareWorkflow
    
    输出：
    - content["MultiModalResponses"] - 多模态回复列表
    - content["RelationChange"] - 关系变化
    - content["FutureResponse"] - 未来消息规划
    """
    
    # User prompt 模板组合
    userp_template = (
        TASKPROMPT_微信对话 +
        CONTEXTPROMPT_时间 +
        CONTEXTPROMPT_人物资料 +
        CONTEXTPROMPT_用户资料 +
        CONTEXTPROMPT_待办提醒 +
        CONTEXTPROMPT_人物知识和技能 +
        CONTEXTPROMPT_人物状态 +
        CONTEXTPROMPT_当前目标 +
        CONTEXTPROMPT_当前的人物关系 +
        CONTEXTPROMPT_历史对话 +
        CONTEXTPROMPT_最新聊天消息 +
        TASKPROMPT_微信对话_推理要求_纯文本 +
        TASKPROMPT_提醒识别
    )
    
    def run(
        self,
        input_message: str,
        session_state: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        执行回复生成
        
        Args:
            input_message: 用户输入消息
            session_state: 上下文状态（包含 query_rewrite 和 context_retrieve 结果）
            
        Returns:
            包含 content 和 session_state 的结果字典
        """
        session_state = session_state or {}
        
        # 渲染 user prompt
        try:
            rendered_userp = self._render_template(self.userp_template, session_state)
        except Exception as e:
            logger.warning(f"User prompt 渲染失败: {e}")
            rendered_userp = input_message
        
        # 调用 Agent 生成回复
        try:
            response = chat_response_agent.run(
                input=rendered_userp,
                session_state=session_state
            )
            
            # 提取回复内容
            content = self._extract_content(response)
            logger.info("ChatResponseAgent 执行完成")
            
        except Exception as e:
            logger.error(f"ChatResponseAgent 执行失败: {e}")
            content = self._get_default_content()
        
        return {
            "content": content,
            "session_state": session_state
        }
    
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
            return template.format(**context)
        except KeyError as e:
            logger.warning(f"模板渲染缺少字段: {e}")
            return template
    
    def _extract_content(self, response) -> Dict[str, Any]:
        """
        从 Agent 响应中提取内容
        
        V2 重构：精简版，只提取回复相关字段
        RelationChange 和 FutureResponse 已移至 PostAnalyzeWorkflow
        
        Args:
            response: Agent 响应对象
            
        Returns:
            提取的内容字典
        """
        if not response or not response.content:
            return self._get_default_content()
        
        content = response.content
        
        # 如果是 Pydantic 模型，转换为 dict
        if hasattr(content, 'model_dump'):
            content = content.model_dump()
        elif not isinstance(content, dict):
            return self._get_default_content()
        
        # 确保必要字段存在（精简版，不再包含 RelationChange 和 FutureResponse）
        result = {
            "InnerMonologue": content.get("InnerMonologue", ""),
            "MultiModalResponses": content.get("MultiModalResponses", []),
            "ChatCatelogue": content.get("ChatCatelogue", ""),
            "DetectedReminders": content.get("DetectedReminders", []),
        }
        
        # 确保 MultiModalResponses 是列表
        if not isinstance(result["MultiModalResponses"], list):
            result["MultiModalResponses"] = []
        
        return result
    
    def _get_default_content(self) -> Dict[str, Any]:
        """获取默认的内容结构（精简版）"""
        return {
            "InnerMonologue": "",
            "MultiModalResponses": [],
            "ChatCatelogue": "",
            "DetectedReminders": [],
        }
