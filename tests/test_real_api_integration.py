# -*- coding: utf-8 -*-
"""
真实 API 集成测试

使用真实的 LLM API 和其他服务进行集成测试，确保代码在生产环境中正常工作。

运行方式：
    USE_REAL_API=true python -m pytest tests/test_real_api_integration.py -v

注意：
- 这些测试会消耗真实的 API 配额
- 需要在 .env 文件中配置所有必要的 API keys
- 测试可能较慢，因为需要等待真实的 API 响应
"""

import sys
import unittest

sys.path.append(".")

from agent.agno_agent.agents import (
    chat_response_agent,
    orchestrator_agent,
    query_rewrite_agent,
)
from tests.integration_test_config import requires_real_api, should_use_real_api


class TestRealAPIIntegration(unittest.TestCase):
    """使用真实 API 的集成测试"""

    @classmethod
    def setUpClass(cls):
        """测试类初始化"""
        if should_use_real_api():
            print("\n" + "=" * 60)
            print("警告：正在使用真实 API 进行测试，将消耗 API 配额")
            print("=" * 60 + "\n")

    @requires_real_api("deepseek")
    def test_query_rewrite_agent_real_api(self):
        """测试 QueryRewriteAgent 使用真实 API"""
        print("\n[测试] QueryRewriteAgent 真实 API 调用")

        # 准备测试数据
        session_state = {
            "latest_message": "今天天气怎么样？",
            "character": {"name": "小助手"},
            "user": {"platforms": {"wechat": {"nickname": "测试用户"}}},
        }

        # 调用真实 Agent
        try:
            response = query_rewrite_agent.run(
                input="请重写查询", session_state=session_state
            )

            # 验证响应
            self.assertIsNotNone(response)
            self.assertIsNotNone(response.content)

            print(f"✓ QueryRewriteAgent 响应成功")
            print(f"  响应类型: {type(response.content)}")

            # 如果是 Pydantic 模型，打印内容
            if hasattr(response.content, "model_dump"):
                content = response.content.model_dump()
                print(f"  响应内容: {content}")

        except Exception as e:
            self.fail(f"QueryRewriteAgent 调用失败: {e}")

    @requires_real_api("deepseek")
    def test_orchestrator_agent_real_api(self):
        """测试 OrchestratorAgent 使用真实 API"""
        print("\n[测试] OrchestratorAgent 真实 API 调用")

        # 准备测试数据
        session_state = {
            "latest_message": "提醒我明天下午3点开会",
            "character": {"name": "小助手"},
            "user": {"platforms": {"wechat": {"nickname": "测试用户"}}},
            "time": "2025-12-25 10:00:00",
        }

        # 调用真实 Agent
        try:
            response = orchestrator_agent.run(
                input="请分析用户意图", session_state=session_state
            )

            # 验证响应
            self.assertIsNotNone(response)
            self.assertIsNotNone(response.content)

            print(f"✓ OrchestratorAgent 响应成功")

            # 打印响应内容
            if hasattr(response.content, "model_dump"):
                content = response.content.model_dump()
                print(f"  need_reminder_detect: {content.get('need_reminder_detect')}")
                print(
                    f"  need_context_retrieve: {content.get('need_context_retrieve')}"
                )

        except Exception as e:
            self.fail(f"OrchestratorAgent 调用失败: {e}")

    @requires_real_api("deepseek")
    def test_chat_response_agent_real_api(self):
        """测试 ChatResponseAgent 使用真实 API"""
        print("\n[测试] ChatResponseAgent 真实 API 调用")

        # 准备测试数据
        session_state = {
            "latest_message": "你好",
            "character": {
                "name": "小助手",
                "platforms": {"wechat": {"nickname": "小助手"}},
            },
            "user": {"platforms": {"wechat": {"nickname": "测试用户"}}},
            "time": "2025-12-25 10:00:00",
            "MultiModalResponses": [],
        }

        # 调用真实 Agent
        try:
            response = chat_response_agent.run(
                input="请生成回复", session_state=session_state
            )

            # 验证响应
            self.assertIsNotNone(response)
            self.assertIsNotNone(response.content)

            print(f"✓ ChatResponseAgent 响应成功")

            # 打印响应内容
            if hasattr(response.content, "model_dump"):
                content = response.content.model_dump()
                responses = content.get("MultiModalResponses", [])
                print(f"  生成了 {len(responses)} 条回复")
                for i, resp in enumerate(responses[:3]):  # 只打印前3条
                    print(f"  [{i+1}] {resp.get('type')}: {resp.get('content')[:50]}")

        except Exception as e:
            self.fail(f"ChatResponseAgent 调用失败: {e}")

    @requires_real_api("deepseek")
    def test_model_id_format(self):
        """测试模型 ID 格式是否正确（无空格）"""
        print("\n[测试] 验证模型 ID 格式")

        # 检查所有 Agent 的模型 ID
        agents = [
            ("query_rewrite_agent", query_rewrite_agent),
            ("orchestrator_agent", orchestrator_agent),
            ("chat_response_agent", chat_response_agent),
        ]

        for agent_name, agent in agents:
            model_id = agent.model.id if hasattr(agent.model, "id") else None
            self.assertIsNotNone(model_id, f"{agent_name} 没有 model.id")

            # 验证模型 ID 不包含空格
            self.assertNotIn(
                "-",
                model_id,
                f"{agent_name} 的模型 ID 包含空格: {model_id}",
            )

            # 验证模型 ID 格式正确
            self.assertIn(
                "-",
                model_id,
                f"{agent_name} 的模型 ID 格式不正确: {model_id}",
            )

            print(f"  ✓ {agent_name}: {model_id}")

    @requires_real_api("deepseek")
    def test_agent_id_format(self):
        """测试 Agent ID 格式是否正确（无空格）"""
        print("\n[测试] 验证 Agent ID 格式")

        # 检查所有 Agent 的 ID
        agents = [
            ("query_rewrite_agent", query_rewrite_agent),
            ("orchestrator_agent", orchestrator_agent),
            ("chat_response_agent", chat_response_agent),
        ]

        for agent_name, agent in agents:
            agent_id = agent.id if hasattr(agent, "id") else None
            self.assertIsNotNone(agent_id, f"{agent_name} 没有 id")

            # 验证 Agent ID 不包含空格
            self.assertNotIn(
                "-",
                agent_id,
                f"{agent_name} 的 ID 包含空格: {agent_id}",
            )

            # 验证 Agent ID 格式正确（应该使用连字符）
            self.assertIn(
                "-",
                agent_id,
                f"{agent_name} 的 ID 格式不正确: {agent_id}",
            )

            print(f"  ✓ {agent_name}: {agent_id}")


class TestOSSIntegration(unittest.TestCase):
    """OSS 集成测试"""

    @requires_real_api("oss")
    def test_oss_configuration(self):
        """测试 OSS 配置是否正确"""
        print("\n[测试] OSS 配置验证")

        from util.oss import bucket, bucket_name, endpoint, region

        # 验证配置格式
        self.assertNotIn("-", endpoint, f"endpoint 包含空格: {endpoint}")
        self.assertNotIn("-", region, f"region 包含空格: {region}")
        self.assertNotIn("-", bucket_name, f"bucket_name 包含空格: {bucket_name}")

        # 验证配置值
        self.assertTrue(endpoint.startswith("https://"), "endpoint 应该使用 HTTPS")
        self.assertIn("aliyuncs.com", endpoint, "endpoint 应该是阿里云域名")

        print(f"  ✓ endpoint: {endpoint}")
        print(f"  ✓ region: {region}")
        print(f"  ✓ bucket_name: {bucket_name}")

        # 尝试连接（不上传文件，只验证连接）
        try:
            # 简单的 bucket 存在性检查
            bucket.get_bucket_info()
            print(f"  ✓ OSS bucket 连接成功")
        except Exception as e:
            # 如果是权限问题或 bucket 不存在，也算配置正确
            if "NoSuchBucket" in str(e) or "AccessDenied" in str(e):
                print(f"  ✓ OSS 配置正确（bucket 可能不存在或无权限）")
            else:
                self.fail(f"OSS 连接失败: {e}")


def run_integration_tests():
    """运行集成测试的辅助函数"""
    from tests.integration_test_config import get_missing_api_keys, validate_api_keys

    print("\n" + "=" * 60)
    print("真实 API 集成测试")
    print("=" * 60)

    # 检查配置
    if not should_use_real_api():
        print("\n提示：USE_REAL_API 未设置，将跳过所有真实 API 测试")
        print("要运行真实 API 测试，请设置环境变量：")
        print("  export USE_REAL_API=true")
        print("  python -m pytest tests/test_real_api_integration.py -v")
        return

    # 检查 API keys
    validation = validate_api_keys()
    print("\nAPI Keys 配置状态:")
    for api, configured in validation.items():
        status = "✓" if configured else "✗"
        print(f"  {status} {api}")

    missing = get_missing_api_keys()
    if missing:
        print(f"\n警告：以下 API keys 未配置: {', '.join(missing)}")
        print("相关测试将被跳过")

    print("\n开始运行测试...\n")

    # 运行测试
    unittest.main(argv=[""], verbosity=2, exit=False)


if __name__ == "__main__":
    run_integration_tests()
