# -*- coding: utf-8 -*-
"""
PrepareWorkflow - 准备阶段 Workflow

执行顺序：QueryRewrite → ReminderDetect → ContextRetrieve
更新 session_state 中的 query_rewrite 和 context_retrieve 字段

Requirements: 5.1
"""

import logging
from typing import Any, Dict, Optional

from agent.agno_agent.agents import (
    query_rewrite_agent,
    reminder_detect_agent,
    context_retrieve_agent,
)
from agent.agno_agent.tools.reminder_tools import set_reminder_session_state
from agent.prompt.chat_taskprompt import (
    TASKPROMPT_语义理解,
    TASKPROMPT_语义理解_推理要求,
)
from agent.prompt.chat_contextprompt import (
    CONTEXTPROMPT_时间,
    CONTEXTPROMPT_历史对话,
    CONTEXTPROMPT_最新聊天消息,
)

logger = logging.getLogger(__name__)


class PrepareWorkflow:
    """
    准备阶段 Workflow：问题重写 + 提醒检测 + 上下文检索
    
    注意：这是自定义 Workflow 类，不继承 Agno Workflow，
    因为需要 Runner 层控制分段执行和打断检测。
    
    执行流程：
    1. QueryRewriteAgent - 对用户输入进行语义理解，生成检索查询词
    2. ReminderDetectAgent - 检测提醒意图并创建提醒
    3. ContextRetrieveAgent - 根据查询词检索相关上下文
    
    输出：
    - session_state["query_rewrite"] - QueryRewriteAgent 的输出
    - session_state["context_retrieve"] - ContextRetrieveAgent 的输出
    """
    
    # User prompt 模板：语义理解任务
    userp_template = (
        TASKPROMPT_语义理解 +
        CONTEXTPROMPT_时间 +
        CONTEXTPROMPT_历史对话 +
        CONTEXTPROMPT_最新聊天消息 +
        TASKPROMPT_语义理解_推理要求
    )
    
    def run(
        self,
        input_message: str,
        session_state: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        执行准备阶段
        
        Args:
            input_message: 用户输入消息
            session_state: 上下文状态
            
        Returns:
            包含 session_state 的结果字典
        """
        session_state = session_state or {}
        
        # ========== Step 1: 问题重写 ==========
        try:
            rendered_userp = self._render_template(self.userp_template, session_state)
        except Exception as e:
            logger.warning(f"User prompt 渲染失败: {e}")
            rendered_userp = input_message
        
        try:
            qr_response = query_rewrite_agent.run(
                input=rendered_userp,
                session_state=session_state
            )
            
            # 提取 QueryRewriteResponse 内容
            if qr_response and qr_response.content:
                # 如果是 Pydantic 模型，转换为 dict
                if hasattr(qr_response.content, 'model_dump'):
                    session_state["query_rewrite"] = qr_response.content.model_dump()
                elif isinstance(qr_response.content, dict):
                    session_state["query_rewrite"] = qr_response.content
                else:
                    session_state["query_rewrite"] = {
                        "InnerMonologue": "",
                        "CharacterSettingQueryQuestion": "",
                        "CharacterSettingQueryKeywords": "",
                        "UserProfileQueryQuestion": "",
                        "UserProfileQueryKeywords": "",
                        "CharacterKnowledgeQueryQuestion": "",
                        "CharacterKnowledgeQueryKeywords": "",
                    }
                logger.info("QueryRewriteAgent 执行完成")
            else:
                logger.warning("QueryRewriteAgent 返回空内容")
                session_state["query_rewrite"] = self._get_default_query_rewrite()
                
        except Exception as e:
            logger.error(f"QueryRewriteAgent 执行失败: {e}")
            session_state["query_rewrite"] = self._get_default_query_rewrite()
        
        # ========== Step 2: 提醒检测 ==========
        try:
            # 设置 session_state 供 reminder_tool 使用
            set_reminder_session_state(session_state)
            
            reminder_detect_agent.run(
                input=input_message,
                session_state=session_state
            )
            logger.info("ReminderDetectAgent 执行完成")
        except Exception as e:
            logger.error(f"ReminderDetectAgent 执行失败: {e}")
            # 提醒检测失败不影响主流程
        
        # ========== Step 3: 上下文检索 ==========
        try:
            # 构建检索参数
            query_rewrite = session_state.get("query_rewrite", {})
            character_id = session_state.get("character", {}).get("_id", "")
            user_id = session_state.get("user", {}).get("_id", "")
            
            # 构建检索消息
            retrieve_message = self._build_retrieve_message(
                query_rewrite=query_rewrite,
                character_id=character_id,
                user_id=user_id
            )
            
            cr_response = context_retrieve_agent.run(
                input=retrieve_message,
                session_state=session_state
            )
            
            # 提取检索结果
            if cr_response and cr_response.content:
                if isinstance(cr_response.content, dict):
                    session_state["context_retrieve"] = cr_response.content
                else:
                    session_state["context_retrieve"] = self._get_default_context_retrieve()
                logger.info("ContextRetrieveAgent 执行完成")
            else:
                logger.warning("ContextRetrieveAgent 返回空内容")
                session_state["context_retrieve"] = self._get_default_context_retrieve()
                
        except Exception as e:
            logger.error(f"ContextRetrieveAgent 执行失败: {e}")
            session_state["context_retrieve"] = self._get_default_context_retrieve()
        
        return {
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
    
    def _build_retrieve_message(
        self,
        query_rewrite: Dict[str, Any],
        character_id: str,
        user_id: str
    ) -> str:
        """
        构建上下文检索的消息
        
        Args:
            query_rewrite: 问题重写结果
            character_id: 角色ID
            user_id: 用户ID
            
        Returns:
            检索消息字符串
        """
        return f"""请根据以下查询信息检索相关上下文：

角色设定查询：{query_rewrite.get('CharacterSettingQueryQuestion', '')}
角色设定关键词：{query_rewrite.get('CharacterSettingQueryKeywords', '')}
用户资料查询：{query_rewrite.get('UserProfileQueryQuestion', '')}
用户资料关键词：{query_rewrite.get('UserProfileQueryKeywords', '')}
角色知识查询：{query_rewrite.get('CharacterKnowledgeQueryQuestion', '')}
角色知识关键词：{query_rewrite.get('CharacterKnowledgeQueryKeywords', '')}

角色ID：{character_id}
用户ID：{user_id}
"""
    
    def _get_default_query_rewrite(self) -> Dict[str, str]:
        """获取默认的 query_rewrite 结构"""
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
