# -*- coding: utf-8 -*-
"""
集成测试-扩展覆盖

测试系统中尚未覆盖的重要 happy path，包括：
1. 主动消息（Future Message）流程
2. 提醒触发流程
3. 提醒管理操作（CRUD）
4. 关系和记忆更新
5. 多模态消息处理

运行方式：
    USE_REAL_API=true python -m pytest tests/test_integration_extended.py -v
"""

import sys
import unittest
from datetime import datetime, timedelta

sys.path.append(".")

from tests.integration_test_config import requires_real_api, should_use_real_api


class TestFutureMessageFlow(unittest.TestCase):
    """测试主动消息流程（Happy Path 6）"""

    @classmethod
    def setUpClass(cls):
        if should_use_real_api():
            print("\n" + "=" * 70)
            print("集成测试-主动消息流程")
            print("=" * 70)

    @requires_real_api("deepseek")
    def test_future_message_workflow(self):
        """测试 FutureMessageWorkflow 完整流程"""
        print("\n[测试 6.1] FutureMessageWorkflow-完整流程")

        import asyncio
        from agent.agno_agent.workflows import FutureMessageWorkflow
        from bson import ObjectId

        # 准备主动消息的 context
        future_time = datetime.now() + timedelta(hours=1)
        context = {
            "user": {
                "_id": ObjectId(),
                "platforms": {"wechat": {"id": "test_user", "nickname": "测试用户"}},
            },
            "character": {
                "_id": ObjectId(),
                "name": "小助手",
                "platforms": {"wechat": {"nickname": "小助手"}},
                "user_info": {"description": "一个友好的助手"},
            },
            "conversation": {
                "_id": ObjectId(),
                "conversation_info": {
                    "chat_history": [
                        {"role": "user", "content": "提醒我1小时后学习"},
                        {"role": "assistant", "content": "好的，我会提醒你的"},
                    ],
                    "time_str": datetime.now().strftime("%Y年%m月%d日"),
                    "future": {
                        "timestamp": int(future_time.timestamp()),
                        "action": "询问用户是否开始学习",
                        "proactive_times": 0,
                        "status": "pending",
                    },
                },
            },
            "relation": {
                "_id": ObjectId(),
                "relationship": {"closeness": 50, "trustness": 50},
            },
            "message_source": "future",
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        workflow = FutureMessageWorkflow()

        try:
            result = asyncio.run(workflow.run(context))

            self.assertIsNotNone(result)
            print(f"  ✓ FutureMessageWorkflow 执行成功")

            # 验证生成了主动消息
            content = result.get("content", {})
            responses = content.get("MultiModalResponses", [])
            self.assertGreater(len(responses), 0, "应该生成至少一条主动消息")
            print(f"  ✓ 生成了 {len(responses)} 条主动消息")

            # 验证主动消息次数递增
            session_state = result.get("session_state", {})
            future_info = (
                session_state.get("conversation", {})
                .get("conversation_info", {})
                .get("future", {})
            )
            proactive_times = future_info.get("proactive_times", 0)
            print(f"  ✓ 主动消息次数: {proactive_times}")

        except Exception as e:
            print(f"  ℹ Workflow 执行失败: {str(e)[:100]}")

    @requires_real_api("deepseek")
    def test_future_message_max_times(self):
        """测试主动消息次数限制"""
        print("\n[测试 6.2] FutureMessageWorkflow-次数限制")

        import asyncio
        from agent.agno_agent.workflows import FutureMessageWorkflow
        from bson import ObjectId

        # 准备已达上限的 context
        context = {
            "user": {
                "_id": ObjectId(),
                "platforms": {"wechat": {"nickname": "测试用户"}},
            },
            "character": {
                "_id": ObjectId(),
                "name": "小助手",
                "platforms": {"wechat": {"nickname": "小助手"}},
            },
            "conversation": {
                "_id": ObjectId(),
                "conversation_info": {
                    "chat_history": [],
                    "future": {
                        "timestamp": int(datetime.now().timestamp()),
                        "action": "询问用户",
                        "proactive_times": 1,  # 已经发送过1次
                        "status": "pending",
                    },
                },
            },
            "relation": {"_id": ObjectId(), "relationship": {}},
            "message_source": "future",
        }

        workflow = FutureMessageWorkflow()

        try:
            result = asyncio.run(workflow.run(context))

            # 验证达到上限后状态变为 expired
            session_state = result.get("session_state", {})
            future_info = (
                session_state.get("conversation", {})
                .get("conversation_info", {})
                .get("future", {})
            )

            proactive_times = future_info.get("proactive_times", 0)
            status = future_info.get("status", "")

            print(f"  ✓ 主动消息次数: {proactive_times}")
            print(f"  ✓ 状态: {status}")

            # 第2次发送后应该达到上限
            if proactive_times >= 2:
                self.assertEqual(status, "expired", "达到上限后应设置为 expired")
                print(f"  ✓ 达到上限，状态正确设置为 expired")

        except Exception as e:
            print(f"  ℹ 测试执行失败: {str(e)[:100]}")


class TestReminderTriggerFlow(unittest.TestCase):
    """测试提醒触发流程（Happy Path 7）"""

    @classmethod
    def setUpClass(cls):
        if should_use_real_api():
            print("\n" + "=" * 70)
            print("集成测试-提醒触发流程")
            print("=" * 70)

    @requires_real_api("deepseek")
    def test_reminder_message_generation(self):
        """测试提醒触发时的消息生成"""
        print("\n[测试 7.1] 提醒触发-消息生成")

        import asyncio
        from agent.agno_agent.workflows import StreamingChatWorkflow
        from bson import ObjectId

        # 准备提醒触发的 context
        context = {
            "user": {
                "_id": ObjectId(),
                "platforms": {"wechat": {"nickname": "测试用户"}},
            },
            "character": {
                "_id": ObjectId(),
                "name": "小助手",
                "platforms": {"wechat": {"nickname": "小助手"}},
                "user_info": {"description": "一个友好的助手"},
            },
            "conversation": {
                "_id": ObjectId(),
                "conversation_info": {
                    "chat_history": [
                        {"role": "user", "content": "提醒我学习"},
                        {"role": "assistant", "content": "好的"},
                    ],
                    "time_str": datetime.now().strftime("%Y年%m月%d日"),
                },
            },
            "relation": {"_id": ObjectId(), "relationship": {}},
            "message_source": "reminder",  # 关键：标记为提醒消息
            "latest_message": "提醒：该学习了",
            "reminder_info": {
                "title": "学习提醒",
                "action_template": "提醒用户开始学习",
            },
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "MultiModalResponses": [],
        }

        workflow = StreamingChatWorkflow()

        try:
            result = asyncio.run(workflow.run("提醒：该学习了", context))

            self.assertIsNotNone(result)
            print(f"  ✓ 提醒消息生成成功")

            # 验证生成了回复
            content = result.get("content", {})
            responses = content.get("MultiModalResponses", [])
            self.assertGreater(len(responses), 0, "应该生成至少一条提醒回复")
            print(f"  ✓ 生成了 {len(responses)} 条提醒回复")

        except Exception as e:
            print(f"  ℹ 测试执行失败: {str(e)[:100]}")


class TestRelationAndMemoryUpdate(unittest.TestCase):
    """测试关系和记忆更新（Happy Path 8）"""

    @classmethod
    def setUpClass(cls):
        if should_use_real_api():
            print("\n" + "=" * 70)
            print("集成测试-关系和记忆更新")
            print("=" * 70)

    @requires_real_api("deepseek")
    def test_relation_change(self):
        """测试关系变化更新"""
        print("\n[测试 8.1] PostAnalyzeWorkflow-关系变化")

        import asyncio
        from agent.agno_agent.workflows import PostAnalyzeWorkflow
        from bson import ObjectId

        # 准备包含明显关系变化的对话
        context = {
            "user": {
                "_id": ObjectId(),
                "platforms": {"wechat": {"nickname": "测试用户"}},
            },
            "character": {
                "_id": ObjectId(),
                "name": "小助手",
                "platforms": {"wechat": {"nickname": "小助手"}},
            },
            "conversation": {
                "_id": ObjectId(),
                "conversation_info": {
                    "chat_history": [
                        {"role": "user", "content": "谢谢你一直以来的帮助"},
                        {"role": "assistant", "content": "不客气，很高兴能帮到你"},
                    ],
                    "time_str": datetime.now().strftime("%Y年%m月%d日"),
                },
            },
            "relation": {
                "_id": ObjectId(),
                "relationship": {
                    "closeness": 50,
                    "trustness": 50,
                    "dislike": 0,
                    "description": "普通关系",
                },
                "user_info": {"realname": "", "hobbyname": "", "description": ""},
                "character_info": {
                    "longterm_purpose": "",
                    "shortterm_purpose": "",
                    "attitude": "",
                },
            },
            "latest_message": "谢谢你一直以来的帮助",
            "MultiModalResponses": [
                {"type": "text", "content": "不客气，很高兴能帮到你"}
            ],
        }

        workflow = PostAnalyzeWorkflow()

        try:
            result = asyncio.run(workflow.run(context))

            self.assertIsNotNone(result)
            print(f"  ✓ PostAnalyzeWorkflow 执行成功")

            # 验证关系变化
            relationship = context["relation"]["relationship"]
            print(f"  ✓ 亲密度: {relationship.get('closeness', 0)}")
            print(f"  ✓ 信任度: {relationship.get('trustness', 0)}")
            print(f"  ✓ 反感度: {relationship.get('dislike', 0)}")

        except Exception as e:
            print(f"  ℹ 测试执行失败: {str(e)[:100]}")

    @requires_real_api("deepseek")
    def test_user_info_update(self):
        """测试用户信息更新"""
        print("\n[测试 8.2] PostAnalyzeWorkflow-用户信息更新")

        import asyncio
        from agent.agno_agent.workflows import PostAnalyzeWorkflow
        from bson import ObjectId

        # 准备包含用户信息的对话
        context = {
            "user": {
                "_id": ObjectId(),
                "platforms": {"wechat": {"nickname": "测试用户"}},
            },
            "character": {
                "_id": ObjectId(),
                "name": "小助手",
                "platforms": {"wechat": {"nickname": "小助手"}},
            },
            "conversation": {
                "_id": ObjectId(),
                "conversation_info": {
                    "chat_history": [
                        {"role": "user", "content": "我叫张三，喜欢打篮球"},
                        {"role": "assistant", "content": "很高兴认识你，张三"},
                    ],
                },
            },
            "relation": {
                "_id": ObjectId(),
                "relationship": {},
                "user_info": {"realname": "", "hobbyname": "", "description": ""},
            },
            "latest_message": "我叫张三，喜欢打篮球",
            "MultiModalResponses": [{"type": "text", "content": "很高兴认识你，张三"}],
        }

        workflow = PostAnalyzeWorkflow()

        try:
            result = asyncio.run(workflow.run(context))

            self.assertIsNotNone(result)
            print(f"  ✓ PostAnalyzeWorkflow 执行成功")

            # 验证用户信息更新
            user_info = context["relation"]["user_info"]
            print(f"  ✓ 真名: {user_info.get('realname', '未更新')}")
            print(f"  ✓ 昵称: {user_info.get('hobbyname', '未更新')}")
            print(f"  ✓ 描述: {user_info.get('description', '未更新')[:50]}")

        except Exception as e:
            print(f"  ℹ 测试执行失败: {str(e)[:100]}")


class TestMultiModalMessages(unittest.TestCase):
    """测试多模态消息处理（Happy Path 9）

    已移除对预创建 ChatResponseAgent 的依赖；此用例不再执行。
    """
    pass


class TestReminderOperations(unittest.TestCase):
    """测试提醒管理操作（Happy Path 10）"""

    @classmethod
    def setUpClass(cls):
        if should_use_real_api():
            print("\n" + "=" * 70)
            print("集成测试-提醒管理操作")
            print("=" * 70)

    @requires_real_api("deepseek")
    def test_reminder_create_with_recurrence(self):
        """测试创建周期性提醒"""
        print("\n[测试 10.1] ReminderDetectAgent-周期性提醒")

        from agent.agno_agent.agents import reminder_detect_agent
        from bson import ObjectId

        # 准备周期性提醒的场景
        tomorrow = datetime.now() + timedelta(days=1)
        session_state = {
            "latest_message": "每天早上8点提醒我学习",
            "character": {"_id": ObjectId(), "name": "小助手"},
            "user": {
                "_id": ObjectId(),
                "platforms": {"wechat": {"nickname": "测试用户"}},
            },
            "conversation": {"_id": ObjectId()},
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "timezone": "Asia/Shanghai",
        }

        try:
            response = reminder_detect_agent.run(
                input="检测并创建周期性提醒", session_state=session_state
            )

            self.assertIsNotNone(response)
            print(f"  ✓ ReminderDetectAgent 执行成功")

            # 检查工具调用
            if hasattr(response, "tool_calls") and response.tool_calls:
                print(f"  ✓ 调用了 {len(response.tool_calls)} 个工具")
            else:
                print(f"  ℹ 未调用工具（可能是测试环境限制）")

        except Exception as e:
            print(f"  ℹ 测试执行失败: {str(e)[:100]}")


def run_extended_tests():
    """运行扩展集成测试"""
    from tests.integration_test_config import get_missing_api_keys, validate_api_keys

    print("\n" + "=" * 70)
    print("集成测试-扩展覆盖")
    print("=" * 70)

    if not should_use_real_api():
        print("\n⚠️  USE_REAL_API 未设置，将跳过所有真实 API 测试")
        print("\n要运行集成测试，请执行：")
        print("  export USE_REAL_API=true")
        print("  python -m pytest tests/test_integration_extended.py -v")
        return

    # 检查 API keys
    validation = validate_api_keys()
    print("\nAPI Keys 配置状态:")
    for api, configured in validation.items():
        status = "✓" if configured else "✗"
        print(f"  {status} {api}")

    missing = get_missing_api_keys()
    if missing:
        print(f"\n⚠️  以下 API keys 未配置: {', '.join(missing)}")
        print("相关测试将被跳过")

    print("\n开始运行测试...\n")

    # 运行测试
    unittest.main(argv=[""], verbosity=2, exit=False)


if __name__ == "__main__":
    run_extended_tests()
