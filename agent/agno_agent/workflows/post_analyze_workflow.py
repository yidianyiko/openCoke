# -*- coding: utf-8 -*-
"""
PostAnalyzeWorkflow - 后处理分析 Workflow

总结对话，更新用户/角色记忆

V2 重构：
- 新增 RelationChange 处理：关系变化（亲密度/信任度），从 ChatWorkflow 移入
- 新增 FutureResponse 处理：未来消息规划，从 ChatWorkflow 移入
- 基于完整对话结果（包括角色回复）进行分析，数据更准确

V2.5 更新：
- 新增 character_info 更新：CharacterPurpose → shortterm_purpose, CharacterAttitude → attitude
- 新增 user_info 更新：UserRealName → realname, UserHobbyName → hobbyname, UserDescription → description
- 新增 relationship 更新：RelationDescription → description, Dislike → dislike
- 修复了 PostAnalyze 输出字段与 relation 存储字段之间的映射缺失问题

Requirements: 5.3
"""

import logging
import random
from typing import Any, Dict, Optional

from agent.agno_agent.agents import post_analyze_agent
from agent.prompt.chat_taskprompt import (
    TASKPROMPT_总结,
    TASKPROMPT_总结_推理要求,
)
from agent.prompt.chat_contextprompt import (
    CONTEXTPROMPT_时间,
    CONTEXTPROMPT_人物资料,
    CONTEXTPROMPT_用户资料,
    CONTEXTPROMPT_当前的人物关系,
    CONTEXTPROMPT_最新聊天消息_双方,
)
from util.time_util import str2timestamp

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
    
    async def run(
        self,
        session_state: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        异步执行后处理分析
        
        V2 重构：新增 RelationChange 和 FutureResponse 处理
        
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
        
        # 打印发送给 PostAnalyzeAgent 的 prompt（便于调试）
        logger.info(f"[PostAnalyzeWorkflow] PostAnalyzeAgent LLM INPUT (len={len(rendered_userp)}):\n{'='*50}\n{rendered_userp}\n{'='*50}")
        
        # 异步调用 Agent 进行后处理分析
        try:
            response = await post_analyze_agent.arun(
                input=rendered_userp,
                session_state=session_state
            )
            
            # 提取分析结果
            content = self._extract_content(response)
            logger.info("PostAnalyzeAgent 执行完成")
            
            # V2 新增：处理关系变化
            self._handle_relation_change(content, session_state)
            
            # V2 新增：处理未来消息规划
            self._handle_future_response(content, session_state)
            
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
            rel["closeness"] = max(0, min(100, rel.get("closeness", 0) + closeness_change))
            rel["trustness"] = max(0, min(100, rel.get("trustness", 0) + trustness_change))
            
            logger.info(f"关系变化: closeness={closeness_change}, trustness={trustness_change}")
    
    def _handle_future_response(self, content: Dict, session_state: Dict) -> None:
        """
        处理未来消息规划（V2 新增，从 ChatWorkflow 移入）
        
        Args:
            content: PostAnalyze 返回的内容
            session_state: 会话状态
        """
        # 获取 conversation 中的 future 信息
        conversation = session_state.get("conversation", {})
        conversation_info = conversation.get("conversation_info", {})
        future_info = conversation_info.get("future", {})
        
        # 初始化 proactive_times
        if "proactive_times" not in future_info:
            future_info["proactive_times"] = 0
        
        # 获取未来消息规划
        future_resp = content.get("FutureResponse", {})
        if isinstance(future_resp, str):
            try:
                import json
                future_resp = json.loads(future_resp)
            except Exception:
                future_resp = {}
        
        future_time_str = future_resp.get("FutureResponseTime", "")
        future_action = future_resp.get("FutureResponseAction", "无")
        
        # 设置未来消息规划
        if future_time_str and future_action and future_action != "无":
            future_info["timestamp"] = str2timestamp(future_time_str) if future_time_str else None
            future_info["action"] = future_action
            
            # 根据消息来源决定是否重置 proactive_times
            message_source = session_state.get("message_source", "user")
            if message_source == "user":
                # 用户消息：重置主动消息次数
                future_info["proactive_times"] = 0
            else:
                # 主动消息/提醒消息：递增次数
                future_info["proactive_times"] = future_info.get("proactive_times", 0) + 1
            
            logger.info(f"设置未来消息规划: time={future_time_str}, action={future_action}, proactive_times={future_info['proactive_times']}")
        else:
            # 清除未来消息规划
            future_info["timestamp"] = None
            future_info["action"] = None
            logger.info("未设置未来消息规划")
        
        # 更新回 session_state
        if "future" not in conversation_info:
            conversation_info["future"] = {}
        conversation_info["future"] = future_info
    
    def _handle_character_info_update(self, content: Dict, session_state: Dict) -> None:
        """
        处理角色信息更新（V2.5 新增）
        
        将 PostAnalyze 输出的字段映射到 relation.character_info：
        - CharacterLongtermPurpose → longterm_purpose
        - CharacterPurpose → shortterm_purpose
        - CharacterAttitude → attitude
        
        Args:
            content: PostAnalyze 返回的内容
            session_state: 会话状态
        """
        if "relation" not in session_state or "character_info" not in session_state["relation"]:
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
        if "relation" not in session_state or "user_info" not in session_state["relation"]:
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
            user_info["description"] = user_description
            logger.info(f"[用户信息更新] 描述: {user_description[:50]}...")
    
    def _handle_relationship_update(self, content: Dict, session_state: Dict) -> None:
        """
        处理关系描述和反感度更新（V2.5 新增）
        
        将 PostAnalyze 输出的 RelationDescription 和 Dislike
        映射到 relation.relationship
        
        Args:
            content: PostAnalyze 返回的内容
            session_state: 会话状态
        """
        if "relation" not in session_state or "relationship" not in session_state["relation"]:
            return
        
        relationship = session_state["relation"]["relationship"]
        
        # 更新关系描述
        relation_description = content.get("RelationDescription", "")
        if relation_description and relation_description != "无":
            relationship["description"] = relation_description
            logger.info(f"[关系更新] 描述: {relation_description}")
        
        # 更新反感度
        dislike_change = content.get("Dislike", 0) or 0
        if dislike_change != 0:
            current_dislike = relationship.get("dislike", 0)
            new_dislike = max(0, min(100, current_dislike + dislike_change))
            relationship["dislike"] = new_dislike
            logger.info(f"[关系更新] 反感度变化: {dislike_change}, 当前值: {new_dislike}")
    
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
        
        V2 重构：新增 RelationChange 和 FutureResponse 字段
        
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
        
        # 确保必要字段存在（V2：新增 RelationChange 和 FutureResponse；V2.5：新增 CharacterLongtermPurpose）
        result = {
            # 新增：关系变化
            "RelationChange": content.get("RelationChange", {"Closeness": 0, "Trustness": 0}),
            # 新增：未来消息规划
            "FutureResponse": content.get("FutureResponse", {"FutureResponseTime": "", "FutureResponseAction": "无"}),
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
        """获取默认的内容结构（V2：新增 RelationChange 和 FutureResponse；V2.5：新增 CharacterLongtermPurpose）"""
        return {
            "RelationChange": {"Closeness": 0, "Trustness": 0},
            "FutureResponse": {"FutureResponseTime": "", "FutureResponseAction": "无"},
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
