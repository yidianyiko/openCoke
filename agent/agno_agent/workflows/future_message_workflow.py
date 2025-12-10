# -*- coding: utf-8 -*-
"""
主动消息（Future Message）Workflow

用于处理角色主动发起的消息，包括：
1. 问题重写（基于规划行动）
2. 上下文检索
3. 消息生成
4. 后处理分析

Requirements: FR-036, FR-038
"""

import logging
import random
from typing import Any, Dict, Optional

from agent.agno_agent.agents.future_message_agents import (
    future_message_query_rewrite_agent,
    future_message_context_retrieve_agent,
    future_message_chat_agent,
)
from agent.agno_agent.agents import post_analyze_agent
from agent.prompt.system_prompt import SYSTEMPROMPT_小说越狱
from agent.prompt.chat_taskprompt import (
    TASKPROMPT_小说书写任务,
    TASKPROMPT_未来_语义理解,
    TASKPROMPT_语义理解_推理要求,
    TASKPROMPT_未来_微信对话,
    TASKPROMPT_微信对话_推理要求_纯文本,
)
from agent.prompt.chat_contextprompt import (
    CONTEXTPROMPT_时间,
    CONTEXTPROMPT_新闻,
    CONTEXTPROMPT_人物信息,
    CONTEXTPROMPT_人物资料,
    CONTEXTPROMPT_用户资料,
    CONTEXTPROMPT_人物知识和技能,
    CONTEXTPROMPT_人物状态,
    CONTEXTPROMPT_当前目标,
    CONTEXTPROMPT_当前的人物关系,
    CONTEXTPROMPT_历史对话,
    CONTEXTPROMPT_规划行动,
)
from agent.prompt.chat_noticeprompt import (
    NOTICE_常规注意事项_分段消息,
    NOTICE_常规注意事项_生成优化,
    NOTICE_常规注意事项_空输入处理,
)
from agent.prompt.personality_prompt import FUTURE_MESSAGE_AGENT_PERSONALITY
from util.time_util import str2timestamp

logger = logging.getLogger(__name__)


class FutureMessageWorkflow:
    """
    主动消息 Workflow
    
    执行流程：
    1. QueryRewrite - 基于规划行动进行问题重写
    2. ContextRetrieve - 检索相关上下文
    3. ChatResponse - 生成主动消息
    4. PostAnalyze - 后处理分析（可选）
    
    注意：这是自定义 Workflow 类，不继承 Agno Workflow，
    因为需要与 Runner 层配合控制执行流程。
    """
    
    # 问题重写的 user prompt 模板
    query_rewrite_userp_template = (
        TASKPROMPT_小说书写任务 + "\n" +
        TASKPROMPT_未来_语义理解 + "\n" +
        TASKPROMPT_语义理解_推理要求 + "\n\n" +
        "## 上下文\n" +
        CONTEXTPROMPT_时间 + "\n" +
        CONTEXTPROMPT_历史对话 + "\n" +
        CONTEXTPROMPT_规划行动
    )
    
    # 消息生成的 user prompt 模板
    chat_userp_template = (
        "## 你的任务\n" +
        TASKPROMPT_小说书写任务 + "\n\n" +
        TASKPROMPT_未来_微信对话 + "\n" +
        TASKPROMPT_微信对话_推理要求_纯文本 + "\n\n" +
        FUTURE_MESSAGE_AGENT_PERSONALITY + "\n\n" +  # 人格与行为规范（含错误触发处理）
        "## 上下文\n" +
        CONTEXTPROMPT_时间 + "\n\n" +
        CONTEXTPROMPT_新闻 + "\n\n" +
        CONTEXTPROMPT_人物信息 + "\n\n" +
        CONTEXTPROMPT_人物资料 + "\n\n" +
        CONTEXTPROMPT_用户资料 + "\n\n" +
        CONTEXTPROMPT_人物知识和技能 + "\n\n" +
        CONTEXTPROMPT_人物状态 + "\n\n" +
        CONTEXTPROMPT_当前目标 + "\n\n" +
        CONTEXTPROMPT_当前的人物关系 + "\n\n" +
        CONTEXTPROMPT_历史对话 + "\n\n" +
        CONTEXTPROMPT_规划行动 + "\n\n" +
        "## 注意事项\n" +
        NOTICE_常规注意事项_分段消息 + "\n" +
        NOTICE_常规注意事项_生成优化 + "\n" +
        "在生成content字段内容时，一定需要注意避免跟历史对话中已有的内容重复或者相同，可以停止话题，或者换一个话题。\n" +
        NOTICE_常规注意事项_空输入处理
    )
    
    def _safe_render_template(self, template: str, session_state: Dict[str, Any]) -> str:
        """
        安全地渲染模板字符串
        
        将 session_state 中的嵌套对象展平为字符串，避免格式化错误
        """
        # 创建一个扁平化的上下文字典，只包含字符串值
        flat_context = {}
        
        for key, value in session_state.items():
            if isinstance(value, str):
                flat_context[key] = value
            elif isinstance(value, (int, float, bool)):
                flat_context[key] = str(value)
            elif isinstance(value, dict):
                # 对于字典，尝试提取常用字段
                if key == "conversation":
                    conv_info = value.get("conversation_info", {})
                    flat_context["chat_history"] = str(conv_info.get("chat_history", []))
                    flat_context["input_messages_str"] = conv_info.get("input_messages_str", "")
                    future = conv_info.get("future", {})
                    flat_context["future_action"] = future.get("action", "")
                    flat_context["future_timestamp"] = str(future.get("timestamp", ""))
                elif key == "character":
                    flat_context["character_name"] = value.get("platforms", {}).get("wechat", {}).get("nickname", "")
                elif key == "user":
                    flat_context["user_name"] = value.get("platforms", {}).get("wechat", {}).get("nickname", "")
                elif key == "relation":
                    rel = value.get("relationship", {})
                    flat_context["closeness"] = str(rel.get("closeness", 0))
                    flat_context["trustness"] = str(rel.get("trustness", 0))
                elif key == "query_rewrite":
                    flat_context["inner_monologue"] = value.get("InnerMonologue", "")
                elif key == "context_retrieve":
                    flat_context["character_global"] = value.get("character_global", "")
                    flat_context["character_private"] = value.get("character_private", "")
                    flat_context["user_profile"] = value.get("user", "")
                    flat_context["character_knowledge"] = value.get("character_knowledge", "")
                else:
                    # 其他字典转为 JSON 字符串
                    try:
                        import json
                        flat_context[key] = json.dumps(value, ensure_ascii=False, default=str)
                    except Exception:
                        flat_context[key] = str(value)
            elif value is None:
                flat_context[key] = ""
            else:
                flat_context[key] = str(value)
        
        try:
            return template.format(**flat_context)
        except KeyError as e:
            logger.warning(f"模板渲染缺少字段: {e}")
            # 返回原始模板，让 LLM 自己处理
            return template
        except Exception as e:
            logger.error(f"模板渲染失败: {e}")
            return template
    
    async def run(self, session_state: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        异步执行主动消息生成流程
        
        Args:
            session_state: 上下文状态，需包含：
                - conversation.conversation_info.future.action: 规划行动
                - character: 角色信息
                - user: 用户信息
                - relation: 关系信息
                
        Returns:
            包含 content 和 session_state 的结果字典
        """
        session_state = session_state or {}
        
        # ========== Step 1: 问题重写 ==========
        logger.info("FutureMessageWorkflow Step 1: QueryRewrite")
        try:
            rendered_qr_userp = self._safe_render_template(self.query_rewrite_userp_template, session_state)
        except Exception as e:
            logger.warning(f"QueryRewrite user prompt 渲染失败: {e}")
            rendered_qr_userp = "请根据规划行动进行问题重写"
        
        # 打印发送给 QueryRewriteAgent 的 prompt（便于调试）
        logger.info(f"[FutureMessageWorkflow] QueryRewriteAgent LLM INPUT (len={len(rendered_qr_userp)}):\n{'='*50}\n{rendered_qr_userp}\n{'='*50}")
        
        qr_response = await future_message_query_rewrite_agent.arun(
            input=rendered_qr_userp,
            session_state=session_state
        )
        
        if qr_response.content:
            # 处理 Pydantic 模型或字典
            if hasattr(qr_response.content, 'model_dump'):
                session_state["query_rewrite"] = qr_response.content.model_dump()
            else:
                session_state["query_rewrite"] = qr_response.content
            logger.info(f"QueryRewrite 结果: {session_state['query_rewrite']}")
        
        # ========== Step 2: 上下文检索 ==========
        logger.info("FutureMessageWorkflow Step 2: ContextRetrieve")
        query_rewrite = session_state.get("query_rewrite", {})
        retrieve_message = self._build_retrieve_message(query_rewrite, session_state)
        
        cr_response = await future_message_context_retrieve_agent.arun(
            input=retrieve_message,
            session_state=session_state
        )
        
        if cr_response.content:
            session_state["context_retrieve"] = cr_response.content
            logger.info("ContextRetrieve 完成")
        
        # ========== Step 3: 消息生成 ==========
        logger.info("FutureMessageWorkflow Step 3: ChatResponse")
        try:
            rendered_chat_userp = self._safe_render_template(self.chat_userp_template, session_state)
        except Exception as e:
            logger.warning(f"Chat user prompt 渲染失败: {e}")
            rendered_chat_userp = "请根据规划行动生成主动消息"
        
        # 打印发送给 FutureMessageChatAgent 的 prompt（便于调试）
        logger.info(f"[FutureMessageWorkflow] FutureMessageChatAgent LLM INPUT (len={len(rendered_chat_userp)}):\n{'='*50}\n{rendered_chat_userp}\n{'='*50}")
        
        chat_response = await future_message_chat_agent.arun(
            input=rendered_chat_userp,
            session_state=session_state
        )
        
        content = {}
        if chat_response.content:
            # 处理 Pydantic 模型或字典
            if hasattr(chat_response.content, 'model_dump'):
                content = chat_response.content.model_dump()
            else:
                content = chat_response.content
            
            # 保存到 session_state 供后续使用
            session_state["MultiModalResponses"] = content.get("MultiModalResponses", [])
            
            # 处理关系变化
            self._handle_relation_change(content, session_state)
            
            # 处理未来消息规划
            self._handle_future_response(content, session_state)
            
            logger.info(f"ChatResponse 结果: {content}")
        
        return {
            "content": content,
            "session_state": session_state
        }
    
    def _build_retrieve_message(self, query_rewrite: Dict, session_state: Dict) -> str:
        """构建上下文检索的消息"""
        character_id = session_state.get("character", {}).get("_id", "")
        user_id = session_state.get("user", {}).get("_id", "")
        
        # 获取规划行动
        future_action = session_state.get("conversation", {}).get(
            "conversation_info", {}
        ).get("future", {}).get("action", "")
        
        message = f"""请根据以下信息检索相关上下文：

规划行动：{future_action}

角色设定查询：{query_rewrite.get('CharacterSettingQueryQuestion', '')}
角色设定关键词：{query_rewrite.get('CharacterSettingQueryKeywords', '')}

用户资料查询：{query_rewrite.get('UserProfileQueryQuestion', '')}
用户资料关键词：{query_rewrite.get('UserProfileQueryKeywords', '')}

角色知识查询：{query_rewrite.get('CharacterKnowledgeQueryQuestion', '')}
角色知识关键词：{query_rewrite.get('CharacterKnowledgeQueryKeywords', '')}

character_id: {character_id}
user_id: {user_id}
"""
        return message
    
    def _handle_relation_change(self, content: Dict, session_state: Dict) -> None:
        """处理关系变化"""
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
            
            rel["closeness"] = max(0, min(100, rel.get("closeness", 0) + closeness_change))
            rel["trustness"] = max(0, min(100, rel.get("trustness", 0) + trustness_change))
    
    def _handle_future_response(self, content: Dict, session_state: Dict) -> None:
        """处理未来消息规划"""
        # 初始化 proactive_times
        future_info = session_state.get("conversation", {}).get(
            "conversation_info", {}
        ).get("future", {})
        
        if "proactive_times" not in future_info:
            future_info["proactive_times"] = 0
        
        proactive_times = future_info.get("proactive_times", 0)
        
        # 增加主动消息次数
        future_info["proactive_times"] = proactive_times + 1
        
        # 获取未来消息规划
        future_resp = content.get("FutureResponse", {})
        if isinstance(future_resp, str):
            try:
                import json
                future_resp = json.loads(future_resp)
            except Exception:
                future_resp = {}
        
        # 根据概率决定是否设置下一次主动消息
        # 概率随主动消息次数指数衰减：0.15^(n+1)
        if random.random() < (0.15 ** (proactive_times + 1)):
            future_time_str = future_resp.get("FutureResponseTime", "")
            future_action = future_resp.get("FutureResponseAction", "无")
            
            future_info["timestamp"] = str2timestamp(future_time_str) if future_time_str else None
            future_info["action"] = future_action if future_action != "无" else None
            
            logger.info(f"设置下一次主动消息: {future_info}")
        else:
            # 清除未来消息规划
            future_info["timestamp"] = None
            future_info["action"] = None
            logger.info("不设置下一次主动消息（概率未命中）")


__all__ = [
    "FutureMessageWorkflow",
]
