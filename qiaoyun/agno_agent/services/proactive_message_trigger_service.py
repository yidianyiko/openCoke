# -*- coding: utf-8 -*-
"""
主动消息触发服务 (Proactive Message Trigger Service)

定时检查并触发主动消息，包括：
1. 查询所有 future.timestamp 已到达的会话
2. 调用 FutureMessageWorkflow 生成主动消息
3. 将消息写入 outputmessages 队列
4. 更新会话的 future 状态

Requirements: 6.1, 6.2, 6.3, 6.4
"""

import logging
import time
from typing import Any, Dict, List, Optional

from dao.conversation_dao import ConversationDAO
from dao.user_dao import UserDAO
from dao.mongo import MongoDBBase

logger = logging.getLogger(__name__)


class ProactiveMessageTriggerService:
    """
    主动消息触发服务
    
    负责定时检查并触发主动消息。
    
    Requirements:
    - 6.1: 查询所有 future.timestamp 已到达的会话
    - 6.2: 调用 FutureMessageWorkflow 生成主动消息
    - 6.3: 将消息写入 outputmessages 队列
    - 6.4: 更新会话的 future 状态
    """
    
    def __init__(
        self,
        conversation_dao: Optional[ConversationDAO] = None,
        user_dao: Optional[UserDAO] = None,
        mongo: Optional[MongoDBBase] = None,
    ):
        """
        初始化触发服务
        
        Args:
            conversation_dao: 会话 DAO（可选，用于测试注入）
            user_dao: 用户 DAO（可选，用于测试注入）
            mongo: MongoDB 基础类（可选，用于测试注入）
        """
        self.conversation_dao = conversation_dao or ConversationDAO()
        self.user_dao = user_dao or UserDAO()
        self.mongo = mongo or MongoDBBase()
    
    def check_and_trigger(self) -> List[Dict[str, Any]]:
        """
        检查并触发到期的主动消息
        
        Returns:
            触发结果列表，每个元素包含 conversation_id 和 result
            
        Requirements: 6.1, 6.2
        """
        results = []
        
        # 获取所有到期的会话
        due_conversations = self._get_due_conversations()
        
        logger.info(f"Found {len(due_conversations)} due conversations for proactive messages")
        
        for conversation in due_conversations:
            try:
                result = self._trigger_proactive_message(conversation)
                results.append({
                    "conversation_id": str(conversation.get("_id", "")),
                    "success": True,
                    "result": result
                })
            except Exception as e:
                logger.error(f"Failed to trigger proactive message for conversation {conversation.get('_id')}: {e}")
                results.append({
                    "conversation_id": str(conversation.get("_id", "")),
                    "success": False,
                    "error": str(e)
                })
        
        return results
    
    def _get_due_conversations(self) -> List[Dict[str, Any]]:
        """
        查询 future.timestamp 已到达的会话
        
        Returns:
            到期会话列表
            
        Requirements: 6.1
        """
        current_timestamp = int(time.time())
        
        # 查询条件：future.timestamp 存在且小于等于当前时间
        query = {
            "conversation_info.future.timestamp": {
                "$exists": True,
                "$ne": None,
                "$lte": current_timestamp
            }
        }
        
        try:
            conversations = self.conversation_dao.find_conversations(query)
            return conversations
        except Exception as e:
            logger.error(f"Failed to query due conversations: {e}")
            return []
    
    def _trigger_proactive_message(self, conversation: Dict[str, Any]) -> Dict[str, Any]:
        """
        触发单个会话的主动消息
        
        Args:
            conversation: 会话数据
            
        Returns:
            触发结果
            
        Requirements: 6.2, 6.3, 6.4
        """
        from qiaoyun.agno_agent.workflows.future_message_workflow import FutureMessageWorkflow
        
        conversation_id = str(conversation.get("_id", ""))
        
        # 从 talkers 中获取用户和角色 ID
        # talkers 格式: [{"id": "user_id", "nickname": "xxx"}, {"id": "character_id", "nickname": "xxx"}]
        talkers = conversation.get("talkers", [])
        user_id = None
        character_id = None
        
        for talker in talkers:
            talker_id = talker.get("id", "")
            # 检查是否为角色（通过查询 users 表的 is_character 字段）
            user_doc = self.user_dao.get_user_by_id(talker_id)
            if user_doc:
                if user_doc.get("is_character", False):
                    character_id = talker_id
                else:
                    user_id = talker_id
        
        if not user_id or not character_id:
            raise ValueError(f"Could not identify user and character from conversation {conversation_id}")
        
        logger.info(f"Triggering proactive message for conversation {conversation_id}")
        
        # 获取用户、角色、关系信息
        user = self.user_dao.get_user_by_id(user_id)
        character = self.user_dao.get_user_by_id(character_id)
        relation = self.mongo.find_one("relations", {"uid": user_id, "cid": character_id})
        
        if not user or not character:
            raise ValueError(f"User or character not found: user_id={user_id}, character_id={character_id}")
        
        # 构建 session_state
        session_state = self._build_session_state(user, character, conversation, relation)
        
        # 执行 FutureMessageWorkflow
        workflow = FutureMessageWorkflow()
        result = workflow.run(session_state=session_state)
        
        # 获取生成的消息
        content = result.get("content", {})
        updated_session_state = result.get("session_state", session_state)
        multimodal_responses = content.get("MultiModalResponses", [])
        
        # 写入 outputmessages 队列
        if multimodal_responses:
            self._write_output_messages(
                conversation_id=conversation_id,
                user_id=user_id,
                character_id=character_id,
                multimodal_responses=multimodal_responses
            )
        
        # 更新会话的 future 状态
        self._update_conversation_future(
            conversation_id=conversation_id,
            updated_session_state=updated_session_state
        )
        
        return {
            "multimodal_responses": multimodal_responses,
            "future_updated": True
        }
    
    def _build_session_state(
        self,
        user: Dict[str, Any],
        character: Dict[str, Any],
        conversation: Dict[str, Any],
        relation: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        构建 session_state
        
        Args:
            user: 用户数据
            character: 角色数据
            conversation: 会话数据
            relation: 关系数据
            
        Returns:
            session_state 字典
        """
        # 确保 relation 有默认值
        if relation is None:
            relation = {
                "relationship": {
                    "closeness": 50,
                    "trustness": 50,
                    "dislike": 0,
                    "status": "空闲",
                    "description": "陌生人"
                },
                "user_info": {
                    "realname": "",
                    "hobbyname": "",
                    "description": ""
                },
                "character_info": {
                    "longterm_purpose": "",
                    "shortterm_purpose": "",
                    "attitude": ""
                }
            }
        
        return {
            "user": user,
            "character": character,
            "conversation": conversation,
            "relation": relation,
            "news_str": "",
            "context_retrieve": {
                "character_global": "",
                "character_private": "",
                "user": "",
                "character_knowledge": "",
                "confirmed_reminders": ""
            }
        }
    
    def _write_output_messages(
        self,
        conversation_id: str,
        user_id: str,
        character_id: str,
        multimodal_responses: List[Dict[str, Any]]
    ) -> None:
        """
        将 MultiModalResponses 写入 outputmessages 队列
        
        Args:
            conversation_id: 会话 ID
            user_id: 用户 ID
            character_id: 角色 ID
            multimodal_responses: 多模态响应列表
            
        Requirements: 6.3
        """
        for response in multimodal_responses:
            msg_type = response.get("type", "text")
            content = response.get("content", "")
            emotion = response.get("emotion")
            
            if not content:
                continue
            
            output_message = {
                "conversation_id": conversation_id,
                "uid": user_id,
                "cid": character_id,
                "type": msg_type,
                "content": content,
                "emotion": emotion,
                "timestamp": int(time.time()),
                "source": "proactive_message"
            }
            
            try:
                self.mongo.insert_one("outputmessages", output_message)
                logger.info(f"Written output message: {msg_type} - {content[:50]}...")
            except Exception as e:
                logger.error(f"Failed to write output message: {e}")
    
    def _update_conversation_future(
        self,
        conversation_id: str,
        updated_session_state: Dict[str, Any]
    ) -> None:
        """
        更新会话的 future 状态
        
        Args:
            conversation_id: 会话 ID
            updated_session_state: 更新后的 session_state
            
        Requirements: 6.4
        """
        future_info = updated_session_state.get("conversation", {}).get(
            "conversation_info", {}
        ).get("future", {})
        
        update_data = {
            "conversation_info.future.timestamp": future_info.get("timestamp"),
            "conversation_info.future.action": future_info.get("action"),
            "conversation_info.future.proactive_times": future_info.get("proactive_times", 0)
        }
        
        try:
            self.conversation_dao.update_conversation(conversation_id, update_data)
            logger.info(f"Updated conversation future state: {conversation_id}")
        except Exception as e:
            logger.error(f"Failed to update conversation future state: {e}")


__all__ = [
    "ProactiveMessageTriggerService",
]
