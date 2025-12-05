# -*- coding: utf-8 -*-
"""
PostAnalyzeWorkflow - 后处理分析 Workflow

总结对话，更新用户/角色记忆

Requirements: 5.3
"""

import logging
from typing import Any, Dict, Optional

from qiaoyun.agno_agent.agents import post_analyze_agent
from qiaoyun.prompt.chat_taskprompt import (
    TASKPROMPT_总结,
    TASKPROMPT_总结_推理要求,
)
from qiaoyun.prompt.chat_contextprompt import (
    CONTEXTPROMPT_时间,
    CONTEXTPROMPT_人物资料,
    CONTEXTPROMPT_用户资料,
    CONTEXTPROMPT_当前的人物关系,
    CONTEXTPROMPT_最新聊天消息_双方,
)

logger = logging.getLogger(__name__)


class PostAnalyzeWorkflow:
    """
    后处理 Workflow：总结对话，更新记忆
    
    注意：这是自定义 Workflow 类，不继承 Agno Workflow。
    
    执行流程：
    1. 渲染 user prompt（包含最新聊天消息和回复）
    2. 调用 PostAnalyzeAgent 进行后处理分析
    3. 返回分析结果（用于更新用户/角色记忆）
    
    输入：
    - session_state["MultiModalResponses"] - 来自 ChatWorkflow 的回复
    - session_state["context_retrieve"] - 来自 PrepareWorkflow
    
    输出：
    - CharacterPublicSettings - 角色公开设定更新
    - CharacterPrivateSettings - 角色私有设定更新
    - UserSettings - 用户资料更新
    - UserRealName - 用户真名
    - RelationDescription - 关系描述更新
    """
    
    # User prompt 模板组合
    userp_template = (
        TASKPROMPT_总结 +
        CONTEXTPROMPT_时间 +
        CONTEXTPROMPT_人物资料 +
        CONTEXTPROMPT_用户资料 +
        CONTEXTPROMPT_当前的人物关系 +
        CONTEXTPROMPT_最新聊天消息_双方 +
        TASKPROMPT_总结_推理要求
    )
    
    def run(
        self,
        session_state: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        执行后处理分析
        
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
        
        # 渲染 user prompt
        try:
            rendered_userp = self._render_template(self.userp_template, session_state)
        except Exception as e:
            logger.warning(f"User prompt 渲染失败: {e}")
            rendered_userp = "请分析本次对话"
        
        # 调用 Agent 进行后处理分析
        try:
            response = post_analyze_agent.run(
                message=rendered_userp,
                session_state=session_state
            )
            
            # 提取分析结果
            content = self._extract_content(response)
            logger.info("PostAnalyzeAgent 执行完成")
            
        except Exception as e:
            logger.error(f"PostAnalyzeAgent 执行失败: {e}")
            content = self._get_default_content()
        
        return content
    
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
                    lines.append(f"[发送了一条语音]")
                else:
                    lines.append(str(content))
            else:
                lines.append(str(resp))
        
        return "\n".join(lines)
    
    def _extract_content(self, response) -> Dict[str, Any]:
        """
        从 Agent 响应中提取内容
        
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
        
        # 确保必要字段存在
        result = {
            "CharacterPublicSettings": content.get("CharacterPublicSettings", "无"),
            "CharacterPrivateSettings": content.get("CharacterPrivateSettings", "无"),
            "UserSettings": content.get("UserSettings", "无"),
            "CharacterKnowledges": content.get("CharacterKnowledges", "无"),
            "UserRealName": content.get("UserRealName", "无"),
            "UserHobbyName": content.get("UserHobbyName", "无"),
            "UserDescription": content.get("UserDescription", ""),
            "CharacterPurpose": content.get("CharacterPurpose", ""),
            "CharacterAttitude": content.get("CharacterAttitude", ""),
            "RelationDescription": content.get("RelationDescription", ""),
            "Dislike": content.get("Dislike", 0),
        }
        
        return result
    
    def _get_default_content(self) -> Dict[str, Any]:
        """获取默认的内容结构"""
        return {
            "CharacterPublicSettings": "无",
            "CharacterPrivateSettings": "无",
            "UserSettings": "无",
            "CharacterKnowledges": "无",
            "UserRealName": "无",
            "UserHobbyName": "无",
            "UserDescription": "",
            "CharacterPurpose": "",
            "CharacterAttitude": "",
            "RelationDescription": "",
            "Dislike": 0,
        }
