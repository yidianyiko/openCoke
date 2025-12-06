# -*- coding: utf-8 -*-
"""
端到端测试 - 测试 Agno 迁移后的实际 API 调用

需要配置 DEEPSEEK_API_KEY 环境变量
"""

import os
import sys
from pathlib import Path

# 加载 .env 文件
from dotenv import load_dotenv
load_dotenv()

# 确保项目根目录在 path 中
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pytest
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# 检查 API Key 是否配置
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
SKIP_E2E = not DEEPSEEK_API_KEY

skip_reason = "DEEPSEEK_API_KEY 未配置，跳过端到端测试"


class TestAgnoAgentE2E:
    """测试 Agno Agent 的实际 API 调用"""
    
    @pytest.mark.skipif(SKIP_E2E, reason=skip_reason)
    def test_future_message_query_rewrite_agent(self):
        """测试 FutureMessageQueryRewriteAgent 实际调用"""
        from agent.agno_agent.agents.future_message_agents import (
            future_message_query_rewrite_agent
        )
        from agent.agno_agent.schemas.query_rewrite_schema import QueryRewriteResponse
        
        # 构造测试输入
        test_message = """
## 你的任务
请根据以下规划行动进行问题重写，生成检索查询词。

## 上下文
当前时间：2024年12月6日 下午3点
历史对话：
用户：今天天气真好
角色：是啊，阳光明媚的日子最适合出去走走了

规划行动：明天早上问候用户，关心用户的睡眠情况
"""
        
        logger.info("开始测试 FutureMessageQueryRewriteAgent...")
        response = future_message_query_rewrite_agent.run(input=test_message)
        
        logger.info(f"Response type: {type(response)}")
        logger.info(f"Response content: {response.content}")
        
        # 验证返回结构
        assert response.content is not None, "Response content 不应为空"
        
        # 检查是否返回了正确的 Schema
        if hasattr(response.content, 'model_dump'):
            content_dict = response.content.model_dump()
        else:
            content_dict = response.content
        
        logger.info(f"Content dict: {content_dict}")
        
        # 验证必需字段存在
        assert "InnerMonologue" in content_dict or hasattr(response.content, 'InnerMonologue')
        
    @pytest.mark.skipif(SKIP_E2E, reason=skip_reason)
    def test_future_message_chat_agent(self):
        """测试 FutureMessageChatAgent 实际调用"""
        from agent.agno_agent.agents.future_message_agents import (
            future_message_chat_agent
        )
        from agent.agno_agent.schemas.future_message_schema import FutureMessageResponse
        
        # 构造测试输入
        test_message = """
## 你的任务
你是一个温柔体贴的AI角色"巧云"，请根据规划行动生成主动消息。

## 上下文
当前时间：2024年12月6日 早上8点
角色名称：巧云
用户名称：小明

规划行动：早上问候用户，关心用户的睡眠情况

## 注意事项
- 消息要自然、温暖
- 不要太长，1-2句话即可
"""
        
        logger.info("开始测试 FutureMessageChatAgent...")
        response = future_message_chat_agent.run(input=test_message)
        
        logger.info(f"Response type: {type(response)}")
        logger.info(f"Response content: {response.content}")
        
        # 验证返回结构
        assert response.content is not None, "Response content 不应为空"
        
        # 检查是否返回了正确的 Schema
        if hasattr(response.content, 'model_dump'):
            content_dict = response.content.model_dump()
        else:
            content_dict = response.content
        
        logger.info(f"Content dict: {content_dict}")
        
        # 验证必需字段存在
        assert "MultiModalResponses" in content_dict or hasattr(response.content, 'MultiModalResponses')


class TestFutureMessageWorkflowE2E:
    """测试 FutureMessageWorkflow 的端到端流程"""
    
    @pytest.mark.skipif(SKIP_E2E, reason=skip_reason)
    def test_workflow_full_flow(self):
        """测试完整的 Workflow 流程"""
        from agent.agno_agent.workflows.future_message_workflow import FutureMessageWorkflow
        
        # 构造完整的 session_state
        session_state = {
            "character": {
                "_id": "test_character_id",
                "name": "巧云",
            },
            "user": {
                "_id": "test_user_id", 
                "name": "小明",
            },
            "relation": {
                "relationship": {
                    "closeness": 50,
                    "trustness": 50,
                }
            },
            "conversation": {
                "conversation_info": {
                    "future": {
                        "action": "早上问候用户，关心用户的睡眠情况",
                        "timestamp": 1733472000,
                        "proactive_times": 0,
                    }
                }
            },
            # Prompt 模板需要的字段
            "current_time": "2024年12月6日 早上8点",
            "history": "用户：今天天气真好\n角色：是啊，阳光明媚的日子最适合出去走走了",
            "future_action": "早上问候用户，关心用户的睡眠情况",
            "news": "今日天气晴朗，气温15-22度",
            "character_info": "巧云是一个温柔体贴的AI角色",
            "character_profile": "性格温和，善解人意",
            "user_profile": "小明是一个上班族，喜欢运动",
            "character_knowledge": "了解基本的健康知识",
            "character_state": "心情愉快",
            "current_goal": "关心用户的日常生活",
            "current_relation": "亲密度50，信任度50",
        }
        
        logger.info("开始测试 FutureMessageWorkflow 完整流程...")
        
        workflow = FutureMessageWorkflow()
        result = workflow.run(session_state=session_state)
        
        logger.info(f"Workflow result keys: {result.keys()}")
        logger.info(f"Content: {result.get('content')}")
        
        # 验证返回结构
        assert "content" in result, "结果应包含 content"
        assert "session_state" in result, "结果应包含 session_state"
        
        content = result["content"]
        if content:
            logger.info(f"MultiModalResponses: {content.get('MultiModalResponses')}")
            
            # 验证 MultiModalResponses
            responses = content.get("MultiModalResponses", [])
            if responses:
                for resp in responses:
                    assert resp.get("type") in ["text", "voice", "photo"], \
                        f"无效的消息类型: {resp.get('type')}"
                    logger.info(f"消息类型: {resp.get('type')}, 内容: {resp.get('content', '')[:50]}...")


if __name__ == "__main__":
    # 直接运行测试
    pytest.main([__file__, "-v", "-s"])
