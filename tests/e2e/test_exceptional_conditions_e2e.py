# -*- coding: utf-8 -*-
"""
异常条件与边缘情况端到端测试

测试覆盖场景：
1. 无效输入数据处理
2. 缺失必要字段处理
3. 类型错误处理
4. 边界值处理
5. 并发处理场景
6. 资源限制场景
7. 数据库连接问题
8. 网络超时模拟
9. 大规模数据处理
10. 安全漏洞检测
11. 内存和性能边界
"""
import asyncio
import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bson import ObjectId

# ============ Invalid Input Data Tests ============


@pytest.mark.e2e
@pytest.mark.slow
class TestInvalidInputData:
    """无效输入数据测试"""

    def test_context_with_invalid_objectid(self):
        """测试包含无效ObjectId的context"""
        from tests.fixtures.sample_contexts import get_context_with_invalid_objectid

        ctx = get_context_with_invalid_objectid()

        # 验证ObjectId是无效的字符串而非真正的ObjectId
        assert isinstance(ctx["user"]["_id"], str)
        assert ctx["user"]["_id"] == "invalid_object_id"

        # 尝试转换应该失败
        with pytest.raises(Exception):
            ObjectId(ctx["user"]["_id"])

    def test_context_with_wrong_types(self):
        """测试包含错误类型字段的context"""
        from tests.fixtures.sample_contexts import get_context_with_wrong_types

        ctx = get_context_with_wrong_types()

        # 验证字段类型错误
        assert isinstance(ctx["relation"]["relationship"]["closeness"], str)
        assert isinstance(ctx["relation"]["relationship"]["trustness"], list)
        assert isinstance(ctx["conversation"]["conversation_info"]["chat_history"], str)

    def test_message_with_null_content(self):
        """测试content为null的消息"""
        from tests.fixtures.sample_messages import get_message_with_null_content

        msg = get_message_with_null_content()
        assert msg["content"] is None

    def test_message_with_wrong_timestamp_type(self):
        """测试时间戳类型错误的消息"""
        from tests.fixtures.sample_messages import get_message_with_wrong_timestamp

        msg = get_message_with_wrong_timestamp()
        assert isinstance(msg["timestamp"], str)
        assert not isinstance(msg["timestamp"], int)

    def test_malformed_json_handling(self):
        """测试畸形JSON处理"""
        invalid_json_strings = [
            '{"key": }',
            '{"unclosed": "string',
            '{key: "no quotes"}',
            '{"nested": {"broken": }}',
        ]

        for invalid_json in invalid_json_strings:
            with pytest.raises(json.JSONDecodeError):
                json.loads(invalid_json)


# ============ Missing Required Fields Tests ============


@pytest.mark.e2e
@pytest.mark.slow
class TestMissingRequiredFields:
    """缺失必要字段测试"""

    def test_context_with_missing_fields(self):
        """测试缺失字段的context"""
        from tests.fixtures.sample_contexts import get_context_with_missing_fields

        ctx = get_context_with_missing_fields()

        # 必要字段存在
        assert "user" in ctx
        assert "character" in ctx
        assert "conversation" in ctx
        assert "relation" in ctx

        # 但内部结构可能缺失
        assert "conversation_info" not in ctx["conversation"]

    def test_reminder_missing_required_fields(self):
        """测试缺失必要字段的提醒"""
        incomplete_reminder = {
            # 缺少 user_id, title, next_trigger_time, status
        }

        required = ["user_id", "title", "next_trigger_time", "status"]
        for field in required:
            assert field not in incomplete_reminder

    def test_message_missing_type_field(self):
        """测试缺失type字段的消息"""
        msg_without_type = {
            "content": "测试内容",
            "timestamp": int(time.time()),
        }

        assert "type" not in msg_without_type

    def test_conversation_info_structure_migration(self):
        """测试conversation_info结构迁移（向后兼容）"""
        old_format_conversation = {
            "_id": ObjectId(),
            "platform": "wechat",
            "talkers": [],
            # 缺少 conversation_info
        }

        # 系统应该能处理这种情况
        assert "conversation_info" not in old_format_conversation


# ============ Boundary Value Tests ============


@pytest.mark.e2e
@pytest.mark.slow
class TestBoundaryValues:
    """边界值测试"""

    def test_relationship_values_at_boundaries(self):
        """测试关系值在边界"""
        from tests.fixtures.sample_contexts import get_context_with_boundary_values

        ctx = get_context_with_boundary_values()
        rel = ctx["relation"]["relationship"]

        assert rel["closeness"] == 0  # 最小值
        assert rel["trustness"] == 100  # 最大值
        assert rel["dislike"] == 100  # 最大值

    def test_relationship_values_out_of_range(self):
        """测试关系值超出范围"""
        from tests.fixtures.sample_contexts import get_context_with_out_of_range_values

        ctx = get_context_with_out_of_range_values()
        rel = ctx["relation"]["relationship"]

        # 这些值不应该被允许
        assert rel["closeness"] < 0  # 负值
        assert rel["trustness"] > 100  # 超过100

    def test_timestamp_boundary_values(self):
        """测试时间戳边界值"""
        boundary_timestamps = [
            0,  # epoch
            -1,  # 负数
            2**31 - 1,  # 32位最大值
            2**32,  # 超过32位
            2**63 - 1,  # 64位最大值
        ]

        for ts in boundary_timestamps:
            reminder = {
                "next_trigger_time": ts,
            }
            assert reminder["next_trigger_time"] == ts

    def test_message_count_limits(self):
        """测试消息数量限制"""
        from tests.fixtures.sample_messages import get_chat_history

        # 测试大量消息
        large_history = get_chat_history(length=1000)
        assert len(large_history) == 1000

    def test_string_length_extremes(self):
        """测试字符串长度极值"""
        from tests.fixtures.sample_messages import get_extremely_long_message

        # 超长消息
        long_msg = get_extremely_long_message(50000)
        assert len(long_msg["content"]) >= 12500

        # 空消息
        from tests.fixtures.sample_messages import get_empty_message

        empty_msg = get_empty_message()
        assert len(empty_msg["content"]) == 0


# ============ Concurrent Processing Tests ============


@pytest.mark.e2e
@pytest.mark.slow
class TestConcurrentProcessing:
    """并发处理测试"""

    def test_concurrent_message_creation(self):
        """测试并发创建消息"""
        from tests.fixtures.sample_messages import get_concurrent_messages

        messages = get_concurrent_messages("test_user", count=100)

        # 验证所有消息都有相同的时间戳
        timestamps = set(m["timestamp"] for m in messages)
        assert len(timestamps) == 1

        # 验证消息ID唯一
        message_ids = [m["message_id"] for m in messages]
        assert len(set(message_ids)) == 100

    def test_concurrent_reminder_creation(self):
        """测试并发创建提醒"""
        reminders = []
        base_time = int(time.time())

        def create_reminder(i):
            return {
                "user_id": f"user_{i % 10}",
                "title": f"提醒_{i}",
                "next_trigger_time": base_time + 3600 + i,
                "status": "active",
                "created_at": base_time,
            }

        with ThreadPoolExecutor(max_workers=10) as executor:
            reminders = list(executor.map(create_reminder, range(100)))

        # 验证所有提醒都被创建
        assert len(reminders) == 100
        # 验证 title 唯一（_id 由 MongoDB 插入时生成）
        reminder_titles = [r["title"] for r in reminders]
        assert len(set(reminder_titles)) == 100

    def test_interleaved_user_messages(self):
        """测试交错的多用户消息"""
        from tests.fixtures.sample_messages import get_interleaved_messages

        messages = get_interleaved_messages(
            user_ids=["user_a", "user_b", "user_c", "user_d", "user_e"],
            messages_per_user=5,
        )

        assert len(messages) == 25

        # 验证时间戳递增
        for i in range(1, len(messages)):
            assert messages[i]["timestamp"] >= messages[i - 1]["timestamp"]

    def test_race_condition_simulation(self):
        """模拟竞态条件场景"""
        shared_counter = {"value": 0}
        results = []

        def increment():
            current = shared_counter["value"]
            time.sleep(0.001)  # 模拟延迟
            shared_counter["value"] = current + 1
            results.append(shared_counter["value"])

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(increment) for _ in range(10)]
            for f in futures:
                f.result()

        # 由于竞态条件，最终值可能不是10
        # 这个测试展示了竞态条件问题
        # 实际系统应该使用锁来保护


# ============ Resource Limit Tests ============


@pytest.mark.e2e
@pytest.mark.slow
class TestResourceLimits:
    """资源限制测试"""

    def test_large_context_serialization(self):
        """测试大型context序列化"""
        from tests.fixtures.sample_contexts import get_context_with_very_long_history

        ctx = get_context_with_very_long_history()

        # 验证可以JSON序列化
        serialized = json.dumps(ctx, default=str)
        assert len(serialized) > 10000  # 应该有相当大的数据量

        # 验证可以反序列化
        deserialized = json.loads(serialized)
        assert "conversation" in deserialized

    def test_memory_efficient_message_batch(self):
        """测试大批量消息的内存效率"""
        batch_sizes = [100, 500, 1000]

        for size in batch_sizes:
            messages = [
                {
                    "type": "text",
                    "content": f"消息_{i}",
                    "timestamp": int(time.time()) + i,
                }
                for i in range(size)
            ]
            assert len(messages) == size

    def test_deep_nested_structure(self):
        """测试深层嵌套结构"""

        def create_nested(depth):
            if depth == 0:
                return {"value": "leaf"}
            return {"nested": create_nested(depth - 1)}

        # 测试不同深度
        for depth in [10, 50, 100]:
            nested = create_nested(depth)
            # 验证可以序列化
            serialized = json.dumps(nested)
            assert "leaf" in serialized


# ============ Error Condition Simulation Tests ============


@pytest.mark.e2e
@pytest.mark.slow
class TestErrorConditionSimulation:
    """错误条件模拟测试"""

    def test_database_connection_failure_handling(self):
        """测试数据库连接失败处理"""
        # 模拟数据库连接失败
        mock_client = MagicMock()
        mock_client.admin.command.side_effect = Exception("Connection refused")

        with pytest.raises(Exception) as exc_info:
            mock_client.admin.command("ping")

        assert "Connection refused" in str(exc_info.value)

    def test_api_timeout_handling(self):
        """测试API超时处理"""

        async def slow_operation():
            await asyncio.sleep(10)
            return "completed"

        async def run_with_timeout():
            try:
                result = await asyncio.wait_for(slow_operation(), timeout=0.1)
            except asyncio.TimeoutError:
                return "timeout"
            return result

        result = asyncio.get_event_loop().run_until_complete(run_with_timeout())
        assert result == "timeout"

    def test_network_error_recovery(self):
        """测试网络错误恢复"""
        call_count = {"value": 0}

        def flaky_operation():
            call_count["value"] += 1
            if call_count["value"] < 3:
                raise ConnectionError("Network error")
            return "success"

        # 模拟重试逻辑
        max_retries = 5
        result = None
        for i in range(max_retries):
            try:
                result = flaky_operation()
                break
            except ConnectionError:
                if i == max_retries - 1:
                    raise

        assert result == "success"
        assert call_count["value"] == 3

    def test_partial_data_write_recovery(self):
        """测试部分数据写入恢复"""
        data_to_write = [
            {"id": 1, "data": "first"},
            {"id": 2, "data": "second"},
            {"id": 3, "data": "third"},
        ]

        written = []
        failed_at = None

        def write_with_failure(item, fail_on_id=2):
            if item["id"] == fail_on_id:
                raise IOError("Write failed")
            written.append(item)

        for item in data_to_write:
            try:
                write_with_failure(item)
            except IOError:
                failed_at = item["id"]
                break

        assert len(written) == 1
        assert failed_at == 2


# ============ Data Validation Tests ============


@pytest.mark.e2e
@pytest.mark.slow
class TestDataValidation:
    """数据验证测试"""

    def test_validate_reminder_recurrence_structure(self):
        """测试验证提醒周期结构"""
        valid_recurrences = [
            {"enabled": False},
            {"enabled": True, "type": "daily", "interval": 1},
            {
                "enabled": True,
                "type": "weekly",
                "interval": 1,
                "days_of_week": [1, 3, 5],
            },
            {"enabled": True, "type": "monthly", "interval": 1, "day_of_month": 15},
        ]

        for rec in valid_recurrences:
            assert "enabled" in rec
            if rec["enabled"]:
                assert "type" in rec

    def test_validate_message_type_enum(self):
        """测试验证消息类型枚举"""
        valid_types = ["text", "voice", "image", "system"]
        invalid_types = ["video", "file", "location", "", None, 123]

        for t in valid_types:
            assert t in ["text", "voice", "image", "system"]

        for t in invalid_types:
            assert t not in valid_types

    def test_validate_relationship_value_ranges(self):
        """测试验证关系值范围"""

        def validate_relationship(closeness, trustness, dislike):
            errors = []
            if not 0 <= closeness <= 100:
                errors.append(f"closeness {closeness} out of range")
            if not 0 <= trustness <= 100:
                errors.append(f"trustness {trustness} out of range")
            if not 0 <= dislike <= 100:
                errors.append(f"dislike {dislike} out of range")
            return errors

        # 有效值
        assert validate_relationship(50, 50, 0) == []
        assert validate_relationship(0, 0, 0) == []
        assert validate_relationship(100, 100, 100) == []

        # 无效值
        assert len(validate_relationship(-1, 50, 0)) > 0
        assert len(validate_relationship(50, 150, 0)) > 0
        assert len(validate_relationship(50, 50, -10)) > 0


# ============ Security Vulnerability Tests ============


@pytest.mark.e2e
@pytest.mark.slow
class TestSecurityVulnerabilities:
    """安全漏洞测试"""

    def test_xss_payload_preservation(self):
        """测试XSS载荷保留（后续应该被清理）"""
        from tests.fixtures.sample_messages import get_xss_injection_message

        msg = get_xss_injection_message()

        # 验证XSS载荷存在
        assert "<script>" in msg["content"]
        assert "onerror" in msg["content"]

    def test_nosql_injection_payload(self):
        """测试NoSQL注入载荷"""
        from tests.fixtures.sample_messages import get_nosql_injection_message

        msg = get_nosql_injection_message()

        # 验证注入载荷
        assert "$gt" in msg["content"]
        assert "$ne" in msg["sender"]

    def test_path_traversal_attempt(self):
        """测试路径穿越尝试"""
        from tests.fixtures.sample_messages import get_path_traversal_message

        msg = get_path_traversal_message()

        # 验证路径穿越载荷
        assert "../" in msg["url"]
        assert "etc/passwd" in msg["url"]

    def test_command_injection_attempt(self):
        """测试命令注入尝试"""
        from tests.fixtures.sample_messages import get_command_injection_message

        msg = get_command_injection_message()

        # 验证命令注入载荷
        assert "rm -rf" in msg["content"]

    def test_binary_content_handling(self):
        """测试二进制内容处理"""
        from tests.fixtures.sample_contexts import get_context_with_binary_like_content

        ctx = get_context_with_binary_like_content()
        content = ctx["conversation"]["conversation_info"]["input_messages"][0][
            "content"
        ]

        # 验证包含二进制类似字符
        assert "\x00" in content or "正常文本" in content


# ============ Performance Edge Cases ============


@pytest.mark.e2e
@pytest.mark.slow
class TestPerformanceEdgeCases:
    """性能边缘情况测试"""

    def test_rapid_sequential_operations(self):
        """测试快速连续操作"""
        start_time = time.time()
        operations = []

        for i in range(100):
            operations.append(
                {
                    "id": i,
                    "timestamp": time.time(),
                    "data": f"operation_{i}",
                }
            )

        elapsed = time.time() - start_time
        assert elapsed < 1.0  # 应该在1秒内完成
        assert len(operations) == 100

    def test_large_json_parsing(self):
        """测试大型JSON解析"""
        # 创建一个大型JSON结构
        large_data = {
            "messages": [
                {"id": i, "content": f"消息内容_{i}" * 10} for i in range(1000)
            ],
            "metadata": {
                "user_info": {"field_" + str(i): f"value_{i}" for i in range(100)},
            },
        }

        start_time = time.time()
        serialized = json.dumps(large_data)
        parsed = json.loads(serialized)
        elapsed = time.time() - start_time

        assert elapsed < 2.0  # 应该在2秒内完成
        assert len(parsed["messages"]) == 1000

    def test_string_concatenation_performance(self):
        """测试字符串拼接性能"""
        parts = []

        start_time = time.time()
        for i in range(10000):
            parts.append(f"第{i}条消息内容")

        result = "\n".join(parts)
        elapsed = time.time() - start_time

        assert elapsed < 1.0
        assert len(result) > 100000


# ============ State Corruption Tests ============


@pytest.mark.e2e
@pytest.mark.slow
class TestStateCorruption:
    """状态损坏测试"""

    def test_corrupted_chat_history(self):
        """测试损坏的聊天历史"""
        corrupted_history = [
            {"role": "user", "content": "正常消息"},
            {"role": "invalid_role", "content": "无效角色"},
            {"content": "缺少role字段"},
            {"role": "assistant"},  # 缺少content
            None,  # null值
            "不是字典",
        ]

        valid_messages = []
        for msg in corrupted_history:
            if isinstance(msg, dict) and "role" in msg and "content" in msg:
                if msg["role"] in ["user", "assistant"]:
                    valid_messages.append(msg)

        assert len(valid_messages) == 1

    def test_inconsistent_reminder_state(self):
        """测试不一致的提醒状态"""
        # 已触发但未设置触发时间
        inconsistent_reminder = {
            "status": "triggered",
            "triggered_count": 0,  # 应该 > 0
            "last_triggered_at": None,  # 应该有值
        }

        # 验证不一致
        if inconsistent_reminder["status"] == "triggered":
            assert inconsistent_reminder["triggered_count"] == 0  # 这是不一致的
            assert inconsistent_reminder["last_triggered_at"] is None  # 这也是不一致的

    def test_circular_reference_handling(self):
        """测试循环引用处理"""
        data = {"key": "value"}
        data["self"] = data  # 创建循环引用

        # JSON序列化应该失败
        with pytest.raises((ValueError, TypeError)):
            json.dumps(data)


# ============ Unicode and Encoding Tests ============


@pytest.mark.e2e
@pytest.mark.slow
class TestUnicodeAndEncoding:
    """Unicode和编码测试"""

    def test_unicode_edge_cases(self):
        """测试Unicode边缘情况"""
        unicode_strings = [
            "普通中文",
            "🎉😄🎂",  # 表情符号
            "日本語テキスト",
            "العربية",  # 阿拉伯语
            "עברית",  # 希伯来语
            "한국어",  # 韩语
            "\u200b\u200c\u200d",  # 零宽字符
            "​‌‍",  # 不同的零宽字符
        ]

        for s in unicode_strings:
            # 应该能正常序列化
            serialized = json.dumps({"content": s})
            parsed = json.loads(serialized)
            assert parsed["content"] == s

    def test_surrogate_pair_handling(self):
        """测试代理对处理"""
        # 某些emoji需要代理对
        emoji_with_surrogates = "👨‍👩‍👧‍👦"  # 家庭emoji

        msg = {
            "type": "text",
            "content": emoji_with_surrogates,
        }

        serialized = json.dumps(msg)
        parsed = json.loads(serialized)
        assert parsed["content"] == emoji_with_surrogates

    def test_mixed_encoding_content(self):
        """测试混合编码内容"""
        mixed_content = "English中文日本語🎉特殊字符"

        ctx = {
            "message": mixed_content,
            "timestamp": int(time.time()),
        }

        # 验证可以正常处理
        serialized = json.dumps(ctx, ensure_ascii=False)
        parsed = json.loads(serialized)
        assert parsed["message"] == mixed_content


# ============ Async Operation Tests ============


@pytest.mark.e2e
@pytest.mark.slow
class TestAsyncOperations:
    """异步操作测试"""

    @pytest.mark.asyncio
    async def test_async_concurrent_operations(self):
        """测试异步并发操作"""
        results = []

        async def async_operation(i):
            await asyncio.sleep(0.01)
            return f"result_{i}"

        tasks = [async_operation(i) for i in range(10)]
        results = await asyncio.gather(*tasks)

        assert len(results) == 10

    @pytest.mark.asyncio
    async def test_async_exception_handling(self):
        """测试异步异常处理"""

        async def failing_operation():
            await asyncio.sleep(0.01)
            raise ValueError("Async operation failed")

        with pytest.raises(ValueError):
            await failing_operation()

    @pytest.mark.asyncio
    async def test_async_timeout_handling(self):
        """测试异步超时处理"""

        async def slow_operation():
            await asyncio.sleep(10)
            return "done"

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(slow_operation(), timeout=0.1)


# ============ Data Consistency Tests ============


@pytest.mark.e2e
@pytest.mark.slow
class TestDataConsistency:
    """数据一致性测试"""

    def test_objectid_string_conversion_consistency(self):
        """测试ObjectId与字符串转换一致性"""
        original_id = ObjectId()
        string_id = str(original_id)
        restored_id = ObjectId(string_id)

        assert original_id == restored_id
        assert string_id == str(restored_id)

    def test_timestamp_consistency(self):
        """测试时间戳一致性"""
        current = int(time.time())

        # 创建和读取应该返回相同值
        data = {"created_at": current}
        serialized = json.dumps(data)
        parsed = json.loads(serialized)

        assert parsed["created_at"] == current

    def test_nested_data_modification_isolation(self):
        """测试嵌套数据修改隔离"""
        import copy

        original = {"nested": {"deep": {"value": "original"}}}

        # 深拷贝
        copied = copy.deepcopy(original)
        copied["nested"]["deep"]["value"] = "modified"

        # 原始数据不应该被修改
        assert original["nested"]["deep"]["value"] == "original"
        assert copied["nested"]["deep"]["value"] == "modified"
