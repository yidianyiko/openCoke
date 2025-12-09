# -*- coding: utf-8 -*-
"""
PrepareWorkflow - 准备阶段 Workflow (V2 架构)

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
from typing import Any, Dict, Optional

from agent.agno_agent.agents import (
    orchestrator_agent,
    reminder_detect_agent,
)
from agent.agno_agent.tools.reminder_tools import set_reminder_session_state
from agent.agno_agent.tools.context_retrieve_tool import context_retrieve_tool
from agent.prompt.chat_taskprompt import (
    TASKPROMPT_语义理解,
)
from agent.prompt.chat_contextprompt import (
    CONTEXTPROMPT_时间,
    CONTEXTPROMPT_历史对话,
    CONTEXTPROMPT_最新聊天消息,
)

logger = logging.getLogger(__name__)


class PrepareWorkflow:
    """
    准备阶段 Workflow (V2 架构)
    
    注意：这是自定义 Workflow 类，不继承 Agno Workflow，
    因为需要 Runner 层控制分段执行和打断检测。
    
    执行流程：
    1. OrchestratorAgent - 语义理解 + 调度决策 (1次 LLM)
    2. context_retrieve_tool - 直接函数调用 (0次 LLM)
    3. ReminderDetectAgent - 按需调用 (0-1次 LLM)
    
    输出：
    - session_state["orchestrator"] - OrchestratorAgent 的输出
    - session_state["context_retrieve"] - context_retrieve_tool 的输出
    - session_state["reminder_result"] - ReminderDetectAgent 的输出 (如果有)
    
    兼容性：
    - session_state["query_rewrite"] - 保留旧字段，从 orchestrator 映射
    """

    # User prompt 模板：Orchestrator 任务
    orchestrator_template = (
        TASKPROMPT_语义理解 +
        CONTEXTPROMPT_时间 +
        CONTEXTPROMPT_历史对话 +
        CONTEXTPROMPT_最新聊天消息
    )
    
    async def run(
        self,
        input_message: str,
        session_state: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        异步执行准备阶段 (V2 架构)
        
        Args:
            input_message: 用户输入消息
            session_state: 上下文状态
            
        Returns:
            包含 session_state 的结果字典
        """
        session_state = session_state or {}
        
        # ========== Step 1: Orchestrator 决策 (1次 LLM) ==========
        try:
            rendered_prompt = self._render_template(self.orchestrator_template, session_state)
        except Exception as e:
            logger.warning(f"Orchestrator prompt 渲染失败: {e}")
            rendered_prompt = input_message
        
        try:
            orchestrator_response = await orchestrator_agent.arun(
                input=rendered_prompt,
                session_state=session_state
            )
            
            # 提取 OrchestratorResponse 内容
            if orchestrator_response and orchestrator_response.content:
                if hasattr(orchestrator_response.content, 'model_dump'):
                    orchestrator_result = orchestrator_response.content.model_dump()
                elif isinstance(orchestrator_response.content, dict):
                    orchestrator_result = orchestrator_response.content
                else:
                    orchestrator_result = self._get_default_orchestrator()
                
                session_state["orchestrator"] = orchestrator_result
                
                # 兼容旧字段：映射到 query_rewrite
                self._map_to_query_rewrite(session_state, orchestrator_result)
                
                logger.info("OrchestratorAgent 执行完成")
            else:
                logger.warning("OrchestratorAgent 返回空内容")
                session_state["orchestrator"] = self._get_default_orchestrator()
                session_state["query_rewrite"] = self._get_default_query_rewrite()
                
        except Exception as e:
            logger.error(f"OrchestratorAgent 执行失败: {e}")
            session_state["orchestrator"] = self._get_default_orchestrator()
            session_state["query_rewrite"] = self._get_default_query_rewrite()
        
        # 获取调度决策
        orchestrator = session_state.get("orchestrator", {})
        need_context = orchestrator.get("need_context_retrieve", True)
        need_reminder = orchestrator.get("need_reminder_detect", False)
        
        # 系统消息（提醒、主动消息）跳过提醒检测
        message_source = session_state.get("message_source", "user")
        if message_source in ["reminder", "future"]:
            need_reminder = False
            logger.info(f"系统消息 (source={message_source})，跳过提醒检测")
        
        # ========== Step 2: 上下文检索 (直接调用 Tool，0次 LLM) ==========
        if need_context:
            try:
                params = orchestrator.get("context_retrieve_params", {})
                character_id = str(session_state.get("character", {}).get("_id", ""))
                user_id = str(session_state.get("user", {}).get("_id", ""))
                
                context_result = context_retrieve_tool(
                    character_setting_query=params.get("character_setting_query", ""),
                    character_setting_keywords=params.get("character_setting_keywords", ""),
                    user_profile_query=params.get("user_profile_query", ""),
                    user_profile_keywords=params.get("user_profile_keywords", ""),
                    character_knowledge_query=params.get("character_knowledge_query", ""),
                    character_knowledge_keywords=params.get("character_knowledge_keywords", ""),
                    character_id=character_id,
                    user_id=user_id
                )
                session_state["context_retrieve"] = context_result
                logger.info("context_retrieve_tool 执行完成")
            except Exception as e:
                logger.error(f"context_retrieve_tool 执行失败: {e}")
                session_state["context_retrieve"] = self._get_default_context_retrieve()
        else:
            logger.info("跳过上下文检索 (need_context_retrieve=False)")
            session_state["context_retrieve"] = self._get_default_context_retrieve()
        
        # ========== Step 3: 提醒检测 (按需调用 Agent，0-1次 LLM) ==========
        if need_reminder:
            try:
                # 设置 session_state 供 reminder_tool 使用
                set_reminder_session_state(session_state)
                
                await reminder_detect_agent.arun(
                    input=input_message,
                    session_state=session_state
                )
                logger.info("ReminderDetectAgent 执行完成")
            except Exception as e:
                logger.error(f"ReminderDetectAgent 执行失败: {e}")
                # 提醒检测失败不影响主流程
        else:
            logger.info("跳过提醒检测 (need_reminder_detect=False)")
        
        return {
            "session_state": session_state
        }
    
    def _render_template(self, template: str, context: Dict[str, Any]) -> str:
        """渲染模板字符串"""
        try:
            return template.format(**context)
        except KeyError as e:
            logger.warning(f"模板渲染缺少字段: {e}")
            return template
    
    def _map_to_query_rewrite(self, session_state: Dict[str, Any], orchestrator: Dict[str, Any]) -> None:
        """
        将 Orchestrator 输出映射到旧的 query_rewrite 字段，保持兼容性
        """
        params = orchestrator.get("context_retrieve_params", {})
        session_state["query_rewrite"] = {
            "InnerMonologue": orchestrator.get("inner_monologue", ""),
            "CharacterSettingQueryQuestion": params.get("character_setting_query", ""),
            "CharacterSettingQueryKeywords": params.get("character_setting_keywords", ""),
            "UserProfileQueryQuestion": params.get("user_profile_query", ""),
            "UserProfileQueryKeywords": params.get("user_profile_keywords", ""),
            "CharacterKnowledgeQueryQuestion": params.get("character_knowledge_query", ""),
            "CharacterKnowledgeQueryKeywords": params.get("character_knowledge_keywords", ""),
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
        }
