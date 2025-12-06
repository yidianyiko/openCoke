# -*- coding: utf-8 -*-
"""
Agno Workflow 端到端测试脚本

直接测试 Workflow 链，不依赖完整的 handler 和 OSS。

Usage:
    python scripts/test_agno_workflow_e2e.py
    
    # 使用真实 LLM（需要 DEEPSEEK_API_KEY）
    python scripts/test_agno_workflow_e2e.py --real
"""
import sys
sys.path.append(".")

# 加载 .env 文件
from dotenv import load_dotenv
load_dotenv()

import os
import time
import logging
import argparse
from unittest.mock import Mock, patch

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_mock_context():
    """创建模拟的 context/session_state"""
    now = time.strftime("%Y年%m月%d日 %H时%M分")
    return {
        "user": {
            "_id": "test_user_id",
            "platforms": {"wechat": {"id": "wx_user", "nickname": "测试用户"}}
        },
        "character": {
            "_id": "test_char_id",
            "name": "小云",
            "platforms": {"wechat": {"id": "wx_char", "nickname": "小云"}},
            "user_info": {
                "description": "一个友好、活泼的AI助手，喜欢聊天和帮助别人。",
                "status": {"place": "家里", "action": "休息"}
            }
        },
        "conversation": {
            "_id": "test_conv_id",
            "conversation_info": {
                "chat_history": [],
                "chat_history_str": "",
                "input_messages": [{"message": "你好", "timestamp": int(time.time())}],
                "input_messages_str": "用户: 你好",
                "time_str": now,
                "photo_history": [],
                "future": {"timestamp": None, "action": None}
            }
        },
        "relation": {
            "uid": "test_user_id",
            "cid": "test_char_id",
            "relationship": {
                "closeness": 50,
                "trustness": 50,
                "dislike": 0,
                "status": "空闲",
                "description": "朋友"
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
        },
        "context_retrieve": {
            "character_global": "小云是一个友好的AI助手",
            "character_private": "",
            "user": "",
            "character_knowledge": "",
            "confirmed_reminders": ""
        },
        "query_rewrite": {
            "InnerMonologue": "",
            "CharacterSettingQueryQuestion": "",
            "CharacterSettingQueryKeywords": "",
            "UserProfileQueryQuestion": "",
            "UserProfileQueryKeywords": "",
            "CharacterKnowledgeQueryQuestion": "",
            "CharacterKnowledgeQueryKeywords": ""
        },
        "news_str": "",
        "repeated_input_notice": ""
    }


def test_workflow_chain_mock():
    """使用 mock 测试 Workflow 链"""
    logger.info("=" * 60)
    logger.info("测试 Workflow 链（Mock 模式）")
    logger.info("=" * 60)
    
    # 需要在导入 Workflow 之前 patch Agent
    import qiaoyun.agno_agent.agents as agents_module
    
    # 创建 mock 响应
    mock_qr_response = Mock()
    mock_qr_response.content = {
        "InnerMonologue": "用户在打招呼，我应该友好地回应",
        "CharacterSettingQueryQuestion": "如何友好地回应问候？",
        "CharacterSettingQueryKeywords": "问候,打招呼,你好",
        "UserProfileQueryQuestion": "",
        "UserProfileQueryKeywords": "",
        "CharacterKnowledgeQueryQuestion": "",
        "CharacterKnowledgeQueryKeywords": ""
    }
    
    mock_cr_response = Mock()
    mock_cr_response.content = {
        "character_global": "小云是一个友好的AI助手",
        "character_private": "",
        "user": "",
        "character_knowledge": ""
    }
    
    mock_chat_response = Mock()
    mock_chat_response.content = {
        "InnerMonologue": "用户在打招呼，我要热情回应",
        "MultiModalResponses": [
            {"type": "text", "content": "你好呀！很高兴见到你！"}
        ],
        "ChatCatelogue": "",
        "RelationChange": {"Closeness": 1, "Trustness": 0},
        "FutureResponse": {"FutureResponseTime": "", "FutureResponseAction": "无"}
    }
    
    mock_post_response = Mock()
    mock_post_response.content = {
        "CharacterPublicSettings": "无",
        "CharacterPrivateSettings": "无",
        "UserSettings": "无",
        "UserRealName": "无",
        "RelationDescription": "朋友"
    }
    
    # 直接替换模块中的 Agent 的 run 方法
    agents_module.query_rewrite_agent.run = Mock(return_value=mock_qr_response)
    agents_module.reminder_detect_agent.run = Mock(return_value=Mock())
    agents_module.context_retrieve_agent.run = Mock(return_value=mock_cr_response)
    agents_module.chat_response_agent.run = Mock(return_value=mock_chat_response)
    agents_module.post_analyze_agent.run = Mock(return_value=mock_post_response)
    
    from qiaoyun.agno_agent.workflows import PrepareWorkflow, ChatWorkflow, PostAnalyzeWorkflow
    
    context = create_mock_context()
    input_message = "你好"
    
    # 创建 Workflow 实例
    prepare_workflow = PrepareWorkflow()
    chat_workflow = ChatWorkflow()
    post_analyze_workflow = PostAnalyzeWorkflow()
    
    # Phase 1: PrepareWorkflow
    logger.info("\n--- Phase 1: PrepareWorkflow ---")
    prepare_result = prepare_workflow.run(
        input_message=input_message,
        session_state=context
    )
    context = prepare_result.get("session_state", context)
    logger.info(f"query_rewrite: {context.get('query_rewrite', {}).get('InnerMonologue', 'N/A')}")
    
    # Phase 2: ChatWorkflow
    logger.info("\n--- Phase 2: ChatWorkflow ---")
    chat_result = chat_workflow.run(
        input_message=input_message,
        session_state=context
    )
    context = chat_result.get("session_state", context)
    content = chat_result.get("content", {})
    
    multimodal_responses = content.get("MultiModalResponses", [])
    logger.info(f"生成了 {len(multimodal_responses)} 条回复")
    for resp in multimodal_responses:
        logger.info(f"  [{resp.get('type')}] {resp.get('content')}")
    
    # Phase 3: PostAnalyzeWorkflow
    logger.info("\n--- Phase 3: PostAnalyzeWorkflow ---")
    context["MultiModalResponses"] = multimodal_responses
    post_result = post_analyze_workflow.run(session_state=context)
    logger.info(f"后处理完成: {post_result.get('RelationDescription', 'N/A')}")
    
    logger.info("\n" + "=" * 60)
    logger.info("Mock 测试完成！")
    logger.info("=" * 60)


def test_workflow_chain_real():
    """使用真实 LLM 测试 Workflow 链"""
    logger.info("=" * 60)
    logger.info("测试 Workflow 链（Real LLM 模式）")
    logger.info("=" * 60)
    
    # 检查 API Key
    if not os.getenv("DEEPSEEK_API_KEY"):
        logger.error("请设置 DEEPSEEK_API_KEY 环境变量")
        return
    
    from qiaoyun.agno_agent.workflows import PrepareWorkflow, ChatWorkflow, PostAnalyzeWorkflow
    
    context = create_mock_context()
    input_message = "你好，今天天气怎么样？"
    context["conversation"]["conversation_info"]["input_messages_str"] = f"用户: {input_message}"
    
    prepare_workflow = PrepareWorkflow()
    chat_workflow = ChatWorkflow()
    post_analyze_workflow = PostAnalyzeWorkflow()
    
    try:
        # Phase 1
        logger.info("\n--- Phase 1: PrepareWorkflow ---")
        prepare_result = prepare_workflow.run(
            input_message=input_message,
            session_state=context
        )
        context = prepare_result.get("session_state", context)
        logger.info(f"query_rewrite 完成")
        
        # Phase 2
        logger.info("\n--- Phase 2: ChatWorkflow ---")
        chat_result = chat_workflow.run(
            input_message=input_message,
            session_state=context
        )
        content = chat_result.get("content", {})
        
        multimodal_responses = content.get("MultiModalResponses", [])
        logger.info(f"生成了 {len(multimodal_responses)} 条回复:")
        for resp in multimodal_responses:
            logger.info(f"  [{resp.get('type')}] {resp.get('content')}")
        
        # Phase 3
        logger.info("\n--- Phase 3: PostAnalyzeWorkflow ---")
        context["MultiModalResponses"] = multimodal_responses
        post_result = post_analyze_workflow.run(session_state=context)
        logger.info(f"后处理完成")
        
    except Exception as e:
        logger.error(f"测试失败: {e}")
        import traceback
        traceback.print_exc()
    
    logger.info("\n" + "=" * 60)
    logger.info("Real LLM 测试完成！")
    logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(description='Agno Workflow 端到端测试')
    parser.add_argument('--real', action='store_true', help='使用真实 LLM（需要 DEEPSEEK_API_KEY）')
    args = parser.parse_args()
    
    if args.real:
        test_workflow_chain_real()
    else:
        test_workflow_chain_mock()


if __name__ == "__main__":
    main()
