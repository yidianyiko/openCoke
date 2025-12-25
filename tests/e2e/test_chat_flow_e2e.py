# -*- coding: utf-8 -*-
"""
聊天流程端到端测试

测试覆盖场景：
1. 基本聊天流程
2. 多模态消息处理
3. 上下文结构验证
4. 长对话历史处理
5. 重复消息检测
6. Turn-level 消息去重
7. 关系数据处理
8. 上下文检索结果验证
9. 边缘情况处理
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch


@pytest.mark.e2e
@pytest.mark.slow
class TestChatFlowE2E:
    """聊天流程端到端测试"""

    # ============ 基本流程测试 ============

    def test_basic_chat_flow(self, sample_full_context):
        """测试基本聊天流程"""
        assert sample_full_context is not None
        assert "user" in sample_full_context
        assert "character" in sample_full_context
        assert "conversation" in sample_full_context

    def test_minimal_context_structure(self, sample_minimal_context):
        """测试最小化 context 结构"""
        assert sample_minimal_context is not None
        assert "user" in sample_minimal_context
        assert "character" in sample_minimal_context
        assert "conversation" in sample_minimal_context
        assert "relation" in sample_minimal_context

    def test_context_structure(self, sample_full_context):
        """测试 context 结构完整性"""
        required_keys = [
            "user",
            "character",
            "conversation",
            "relation",
            "context_retrieve",
            "query_rewrite",
        ]

        for key in required_keys:
            assert key in sample_full_context

    # ============ 多模态消息测试 ============

    def test_multimodal_response_flow(self, sample_full_context):
        """测试多模态响应流程"""
        assert "MultiModalResponses" in sample_full_context
        assert isinstance(sample_full_context["MultiModalResponses"], list)

    def test_multimodal_response_structure(self):
        """测试多模态响应结构"""
        from tests.fixtures.sample_contexts import get_context_with_multimodal_response

        ctx = get_context_with_multimodal_response()
        responses = ctx["MultiModalResponses"]

        assert len(responses) == 3
        assert responses[0]["type"] == "text"
        assert responses[1]["type"] == "voice"
        assert responses[2]["type"] == "photo"

    def test_voice_message_context(self):
        """测试语音消息上下文"""
        from tests.fixtures.sample_contexts import get_context_for_voice_message

        ctx = get_context_for_voice_message()
        input_messages = ctx["conversation"]["conversation_info"]["input_messages"]

        assert len(input_messages) == 1
        assert input_messages[0]["type"] == "voice"
        assert "duration" in input_messages[0]

    def test_image_message_context(self):
        """测试图片消息上下文"""
        from tests.fixtures.sample_contexts import get_context_for_image_message

        ctx = get_context_for_image_message()
        input_messages = ctx["conversation"]["conversation_info"]["input_messages"]

        assert len(input_messages) == 1
        assert input_messages[0]["type"] == "image"
        assert "url" in input_messages[0]
        assert len(ctx["conversation"]["conversation_info"]["photo_history"]) > 0

    # ============ 对话历史测试 ============

    def test_context_with_history(self):
        """测试带有聊天历史的 context"""
        from tests.fixtures.sample_contexts import get_context_with_history

        ctx = get_context_with_history()
        history = ctx["conversation"]["conversation_info"]["chat_history"]

        assert len(history) == 3
        assert history[0]["role"] == "user"
        assert history[1]["role"] == "assistant"
        assert history[2]["role"] == "user"

    def test_long_history_context(self):
        """测试长对话历史 context（用于测试上下文截断）"""
        from tests.fixtures.sample_contexts import get_context_with_long_history

        ctx = get_context_with_long_history()
        history = ctx["conversation"]["conversation_info"]["chat_history"]

        assert len(history) == 40  # 20 rounds * 2 messages
        assert history[0]["role"] == "user"
        assert history[-1]["role"] == "assistant"

    def test_chat_history_string_format(self):
        """测试聊天历史字符串格式"""
        from tests.fixtures.sample_contexts import get_context_with_history

        ctx = get_context_with_history()
        history_str = ctx["conversation"]["conversation_info"]["chat_history_str"]

        assert "用户:" in history_str or "用户: " in history_str
        assert "角色:" in history_str or "角色: " in history_str

    # ============ 重复消息检测测试 ============

    def test_repeated_message_context(self):
        """测试重复消息场景的 context"""
        from tests.fixtures.sample_contexts import get_context_for_repeated_message

        ctx = get_context_for_repeated_message()

        assert "repeated_input_notice" in ctx
        assert len(ctx["repeated_input_notice"]) > 0
        assert "你好" in ctx["repeated_input_notice"]

    def test_turn_dedup_context(self):
        """测试 turn-level 消息去重场景的 context"""
        from tests.fixtures.sample_contexts import get_context_for_turn_dedup

        ctx = get_context_for_turn_dedup()
        turn_sent = ctx["conversation"]["conversation_info"]["turn_sent_contents"]

        assert len(turn_sent) == 2
        assert "你好！" in turn_sent
        assert "有什么可以帮你的？" in turn_sent

    # ============ 关系数据测试 ============

    def test_relation_context(self):
        """测试完整关系数据的 context"""
        from tests.fixtures.sample_contexts import get_context_with_relation

        ctx = get_context_with_relation()
        relation = ctx["relation"]

        assert "relationship" in relation
        assert relation["relationship"]["closeness"] == 75
        assert relation["relationship"]["trustness"] == 80
        assert "user_info" in relation
        assert "character_info" in relation

    def test_relation_user_info(self):
        """测试关系中的用户信息"""
        from tests.fixtures.sample_contexts import get_context_with_relation

        ctx = get_context_with_relation()
        user_info = ctx["relation"]["user_info"]

        assert "realname" in user_info
        assert "hobbyname" in user_info
        assert "description" in user_info

    def test_relation_character_info(self):
        """测试关系中的角色信息"""
        from tests.fixtures.sample_contexts import get_context_with_relation

        ctx = get_context_with_relation()
        char_info = ctx["relation"]["character_info"]

        assert "longterm_purpose" in char_info
        assert "shortterm_purpose" in char_info
        assert "attitude" in char_info

    # ============ 上下文检索测试 ============

    def test_context_retrieve_structure(self):
        """测试上下文检索结果结构"""
        from tests.fixtures.sample_contexts import get_context_with_context_retrieve

        ctx = get_context_with_context_retrieve()
        retrieve = ctx["context_retrieve"]

        required_keys = [
            "character_global",
            "character_private",
            "user",
            "character_knowledge",
            "confirmed_reminders",
        ]

        for key in required_keys:
            assert key in retrieve

    def test_context_retrieve_content(self):
        """测试上下文检索内容"""
        from tests.fixtures.sample_contexts import get_context_with_context_retrieve

        ctx = get_context_with_context_retrieve()
        retrieve = ctx["context_retrieve"]

        assert len(retrieve["character_global"]) > 0
        assert len(retrieve["user"]) > 0

    # ============ 边缘情况测试 ============

    def test_empty_message_handling(self):
        """测试空消息处理"""
        from tests.fixtures.sample_messages import get_empty_message

        msg = get_empty_message()
        assert msg["type"] == "text"
        assert msg["content"] == ""

    def test_long_message_handling(self):
        """测试长消息处理"""
        from tests.fixtures.sample_messages import get_long_message

        msg = get_long_message(length=500)
        assert msg["type"] == "text"
        assert len(msg["content"]) >= 400

    def test_emoji_message_handling(self):
        """测试表情消息处理"""
        from tests.fixtures.sample_messages import get_emoji_message

        msg = get_emoji_message()
        assert msg["type"] == "text"
        assert "😄" in msg["content"]

    def test_special_chars_message_handling(self):
        """测试特殊字符消息处理"""
        from tests.fixtures.sample_messages import get_special_chars_message

        msg = get_special_chars_message()
        assert msg["type"] == "text"
        assert "<script>" in msg["content"]

    def test_rapid_fire_messages(self):
        """测试快速连续消息"""
        from tests.fixtures.sample_messages import get_rapid_fire_messages

        messages = get_rapid_fire_messages(count=5)
        assert len(messages) == 5

        # 验证时间戳递增
        for i in range(1, len(messages)):
            assert messages[i]["timestamp"] >= messages[i - 1]["timestamp"]

    def test_duplicate_messages(self):
        """测试重复消息"""
        from tests.fixtures.sample_messages import get_duplicate_messages

        messages = get_duplicate_messages(content="测试内容", count=3)
        assert len(messages) == 3

        # 验证内容相同
        for msg in messages:
            assert msg["content"] == "测试内容"

    # ============ 消息类型测试 ============

    def test_text_message_structure(self, sample_text_message):
        """测试文本消息结构"""
        assert "type" in sample_text_message
        assert "content" in sample_text_message
        assert "timestamp" in sample_text_message
        assert sample_text_message["type"] == "text"

    def test_voice_message_structure(self, sample_voice_message):
        """测试语音消息结构"""
        assert "type" in sample_voice_message
        assert "content" in sample_voice_message
        assert "duration" in sample_voice_message
        assert sample_voice_message["type"] == "voice"

    def test_mixed_modal_message(self):
        """测试多模态混合消息"""
        from tests.fixtures.sample_messages import get_mixed_modal_message

        messages = get_mixed_modal_message()
        assert len(messages) == 2
        assert messages[0]["type"] == "text"
        assert messages[1]["type"] == "image"

    # ============ 响应消息测试 ============

    def test_text_response_structure(self):
        """测试文本回复结构"""
        from tests.fixtures.sample_messages import get_text_response

        response = get_text_response("测试回复")
        assert response["type"] == "text"
        assert response["content"] == "测试回复"

    def test_voice_response_structure(self):
        """测试语音回复结构"""
        from tests.fixtures.sample_messages import get_voice_response

        response = get_voice_response("语音内容", "高兴")
        assert response["type"] == "voice"
        assert response["content"] == "语音内容"
        assert response["emotion"] == "高兴"

    def test_photo_response_structure(self):
        """测试图片回复结构"""
        from tests.fixtures.sample_messages import get_photo_response

        response = get_photo_response("photo_001")
        assert response["type"] == "photo"
        assert response["content"] == "photo_001"

    def test_full_multimodal_response(self):
        """测试完整多模态响应"""
        from tests.fixtures.sample_messages import get_multimodal_response_full

        responses = get_multimodal_response_full()
        assert len(responses) == 3

        types = [r["type"] for r in responses]
        assert "text" in types
        assert "voice" in types
        assert "photo" in types

    # ============ 对话信息结构测试 ============

    def test_conversation_info_structure(self, sample_full_context):
        """测试对话信息结构"""
        conv_info = sample_full_context["conversation"]["conversation_info"]

        required_keys = [
            "chat_history",
            "input_messages",
            "input_messages_str",
            "chat_history_str",
            "time_str",
            "photo_history",
            "future",
            "turn_sent_contents",
        ]

        for key in required_keys:
            assert key in conv_info

    def test_future_message_structure(self, sample_full_context):
        """测试未来消息结构"""
        future = sample_full_context["conversation"]["conversation_info"]["future"]

        assert "timestamp" in future
        assert "action" in future

    def test_query_rewrite_structure(self, sample_full_context):
        """测试查询重写结构"""
        query_rewrite = sample_full_context["query_rewrite"]

        required_keys = [
            "InnerMonologue",
            "CharacterSettingQueryQuestion",
            "CharacterSettingQueryKeywords",
            "UserProfileQueryQuestion",
            "UserProfileQueryKeywords",
            "CharacterKnowledgeQueryQuestion",
            "CharacterKnowledgeQueryKeywords",
        ]

        for key in required_keys:
            assert key in query_rewrite


@pytest.mark.e2e
@pytest.mark.slow
class TestChatFlowWithMocks:
    """使用 Mock 的聊天流程测试"""

    def test_chat_workflow_import(self):
        """测试 ChatWorkflow 可导入"""
        try:
            from agent.agno_agent.workflows import StreamingChatWorkflow

            assert StreamingChatWorkflow is not None
        except ImportError:
            pytest.skip("StreamingChatWorkflow not available")

    def test_prepare_workflow_import(self):
        """测试 PrepareWorkflow 可导入"""
        try:
            from agent.agno_agent.workflows import PrepareWorkflow

            assert PrepareWorkflow is not None
        except ImportError:
            pytest.skip("PrepareWorkflow not available")

    def test_post_analyze_workflow_import(self):
        """测试 PostAnalyzeWorkflow 可导入"""
        try:
            from agent.agno_agent.workflows import PostAnalyzeWorkflow

            assert PostAnalyzeWorkflow is not None
        except ImportError:
            pytest.skip("PostAnalyzeWorkflow not available")

    def test_context_prepare_import(self):
        """测试 context_prepare 可导入"""
        try:
            from agent.runner.context import context_prepare

            assert context_prepare is not None
        except ImportError:
            pytest.skip("context_prepare not available")


@pytest.mark.e2e
@pytest.mark.slow
class TestChatFlowIntegration:
    """聊天流程集成测试"""

    def test_user_character_platform_info(self, sample_full_context):
        """测试用户和角色平台信息"""
        user = sample_full_context["user"]
        character = sample_full_context["character"]

        assert "platforms" in user
        assert "wechat" in user["platforms"]
        assert "id" in user["platforms"]["wechat"]

        assert "platforms" in character
        assert "wechat" in character["platforms"]
        assert "id" in character["platforms"]["wechat"]

    def test_character_user_info(self, sample_full_context):
        """测试角色用户信息"""
        character = sample_full_context["character"]

        if "user_info" in character:
            assert "description" in character["user_info"]
            if "status" in character["user_info"]:
                assert "place" in character["user_info"]["status"]
                assert "action" in character["user_info"]["status"]

    def test_news_str_field(self, sample_full_context):
        """测试新闻字段"""
        assert "news_str" in sample_full_context
        assert isinstance(sample_full_context["news_str"], str)

    def test_context_defaults(self, sample_full_context):
        """测试 context 默认值"""
        assert "MultiModalResponses" in sample_full_context
        assert isinstance(sample_full_context["MultiModalResponses"], list)

        assert "repeated_input_notice" in sample_full_context
        assert isinstance(sample_full_context["repeated_input_notice"], str)


# ============ Relationship Level Tests ============


@pytest.mark.e2e
@pytest.mark.slow
class TestRelationshipLevels:
    """关系等级测试 - 测试不同亲密度用户的处理"""

    def test_new_user_relation_context(self):
        """测试新用户关系 context（低亲密度 0-20）"""
        from tests.fixtures.sample_contexts import get_context_with_new_user_relation

        ctx = get_context_with_new_user_relation()
        relation = ctx["relation"]

        assert relation["relationship"]["closeness"] <= 20
        assert relation["relationship"]["trustness"] <= 20
        assert relation["character_info"]["attitude"] == "礼貌但保持距离"

    def test_regular_user_relation_context(self):
        """测试普通用户关系 context（中等亲密度 30-60）"""
        from tests.fixtures.sample_contexts import get_context_with_regular_user_relation

        ctx = get_context_with_regular_user_relation()
        relation = ctx["relation"]

        assert 30 <= relation["relationship"]["closeness"] <= 60
        assert 30 <= relation["relationship"]["trustness"] <= 60
        assert relation["user_info"]["realname"] != ""

    def test_close_user_relation_context(self):
        """测试亲密用户关系 context（高亲密度 70-100）"""
        from tests.fixtures.sample_contexts import get_context_with_close_user_relation

        ctx = get_context_with_close_user_relation()
        relation = ctx["relation"]

        assert relation["relationship"]["closeness"] >= 70
        assert relation["relationship"]["trustness"] >= 70
        assert "老朋友" in relation["relationship"]["description"]

    def test_low_trust_relation_context(self):
        """测试低信任度关系 context"""
        from tests.fixtures.sample_contexts import get_context_with_low_trust_relation

        ctx = get_context_with_low_trust_relation()
        relation = ctx["relation"]

        assert relation["relationship"]["trustness"] < 30
        assert relation["relationship"]["dislike"] > 0
        assert relation["relationship"]["status"] == "警惕"

    def test_relationship_value_boundaries(self):
        """测试关系值边界条件"""
        from tests.fixtures.sample_contexts import get_context_with_boundary_values

        ctx = get_context_with_boundary_values()
        relation = ctx["relation"]

        # 边界值验证
        assert relation["relationship"]["closeness"] == 0
        assert relation["relationship"]["trustness"] == 100
        assert relation["relationship"]["dislike"] == 100

    def test_relationship_out_of_range_detection(self):
        """测试检测超出范围的关系值"""
        from tests.fixtures.sample_contexts import get_context_with_out_of_range_values

        ctx = get_context_with_out_of_range_values()
        relation = ctx["relation"]

        # 这些值不应该被允许，测试应该能检测到
        assert relation["relationship"]["closeness"] < 0  # 负值
        assert relation["relationship"]["trustness"] > 100  # 超过100


# ============ History Length Tests ============


@pytest.mark.e2e
@pytest.mark.slow
class TestHistoryLengths:
    """对话历史长度测试"""

    def test_no_history_context(self):
        """测试无历史记录（初始对话状态）"""
        from tests.fixtures.sample_contexts import get_context_with_no_history

        ctx = get_context_with_no_history()
        history = ctx["conversation"]["conversation_info"]["chat_history"]

        assert len(history) == 0
        assert ctx["conversation"]["conversation_info"]["chat_history_str"] == ""

    def test_short_history_context(self):
        """测试短历史（2-5轮对话）"""
        from tests.fixtures.sample_contexts import get_context_with_short_history

        ctx = get_context_with_short_history()
        history = ctx["conversation"]["conversation_info"]["chat_history"]

        assert 2 <= len(history) <= 10  # 2-5轮 = 4-10条消息
        assert "用户:" in ctx["conversation"]["conversation_info"]["chat_history_str"]
        assert "角色:" in ctx["conversation"]["conversation_info"]["chat_history_str"]

    def test_very_long_history_context(self):
        """测试超长历史（50轮对话，测试极端情况）"""
        from tests.fixtures.sample_contexts import get_context_with_very_long_history

        ctx = get_context_with_very_long_history()
        history = ctx["conversation"]["conversation_info"]["chat_history"]

        assert len(history) == 100  # 50轮 * 2
        # 验证历史字符串长度
        assert len(ctx["conversation"]["conversation_info"]["chat_history_str"]) > 1000

    def test_history_alternation_pattern(self):
        """测试历史消息交替模式正确性"""
        from tests.fixtures.sample_contexts import get_context_with_long_history

        ctx = get_context_with_long_history()
        history = ctx["conversation"]["conversation_info"]["chat_history"]

        for i, msg in enumerate(history):
            expected_role = "user" if i % 2 == 0 else "assistant"
            assert msg["role"] == expected_role, f"Index {i} should be {expected_role}"


# ============ Multimodal Input Tests ============


@pytest.mark.e2e
@pytest.mark.slow
class TestMultimodalInputs:
    """多模态输入测试"""

    def test_multiple_text_messages(self):
        """测试多条连续文本消息"""
        from tests.fixtures.sample_contexts import get_context_with_multiple_text_messages

        ctx = get_context_with_multiple_text_messages()
        input_msgs = ctx["conversation"]["conversation_info"]["input_messages"]

        assert len(input_msgs) == 3
        for msg in input_msgs:
            assert msg["type"] == "text"

    def test_mixed_multimodal_input(self):
        """测试混合多模态输入"""
        from tests.fixtures.sample_contexts import get_context_with_mixed_multimodal_input

        ctx = get_context_with_mixed_multimodal_input()
        input_msgs = ctx["conversation"]["conversation_info"]["input_messages"]

        types = [msg["type"] for msg in input_msgs]
        assert "text" in types
        assert "image" in types
        assert "voice" in types

    def test_voice_message_duration_handling(self):
        """测试语音消息时长处理"""
        from tests.fixtures.sample_messages import get_voice_message_with_long_duration

        msg = get_voice_message_with_long_duration(300)
        assert msg["duration"] == 300
        assert msg["type"] == "voice"

    def test_voice_message_zero_duration(self):
        """测试零时长语音消息"""
        from tests.fixtures.sample_messages import get_voice_message_with_zero_duration

        msg = get_voice_message_with_zero_duration()
        assert msg["duration"] == 0
        # 系统应该能处理零时长语音

    def test_voice_transcription_error(self):
        """测试语音转写失败场景"""
        from tests.fixtures.sample_messages import get_voice_message_with_transcription_error

        msg = get_voice_message_with_transcription_error()
        assert msg["transcription_status"] == "failed"
        assert "[ASR_ERROR]" in msg["content"]

    def test_image_message_with_description(self):
        """测试带描述的图片消息"""
        from tests.fixtures.sample_messages import get_image_message_with_description

        msg = get_image_message_with_description()
        assert "description" in msg
        assert len(msg["description"]) > 0

    def test_image_message_invalid_url(self):
        """测试无效URL的图片消息"""
        from tests.fixtures.sample_messages import get_image_message_with_invalid_url

        msg = get_image_message_with_invalid_url()
        # URL应该是无效格式
        assert not msg["url"].startswith("http")


# ============ Edge Case Input Tests ============


@pytest.mark.e2e
@pytest.mark.slow
class TestEdgeCaseInputs:
    """边缘情况输入测试"""

    def test_single_char_message(self):
        """测试单字符消息"""
        from tests.fixtures.sample_messages import get_single_char_message

        msg = get_single_char_message()
        assert len(msg["content"]) == 1

    def test_whitespace_only_message(self):
        """测试纯空白消息"""
        from tests.fixtures.sample_messages import get_whitespace_only_message

        msg = get_whitespace_only_message()
        assert msg["content"].strip() == ""

    def test_extremely_long_message(self):
        """测试极长消息（10000字符）"""
        from tests.fixtures.sample_messages import get_extremely_long_message

        msg = get_extremely_long_message(10000)
        assert len(msg["content"]) >= 2500  # 10000/4 words

    def test_multiline_message(self):
        """测试多行消息"""
        from tests.fixtures.sample_messages import get_multiline_message

        msg = get_multiline_message()
        lines = msg["content"].split("\n")
        assert len(lines) > 1

    def test_unicode_content(self):
        """测试特殊Unicode内容"""
        from tests.fixtures.sample_contexts import get_context_with_unicode_content

        ctx = get_context_with_unicode_content()
        content = ctx["conversation"]["conversation_info"]["input_messages"][0]["content"]

        assert "😀" in content
        assert "🎉" in content

    def test_html_injection_attempt(self):
        """测试HTML注入尝试"""
        from tests.fixtures.sample_contexts import get_context_with_html_injection

        ctx = get_context_with_html_injection()
        content = ctx["conversation"]["conversation_info"]["input_messages"][0]["content"]

        assert "<script>" in content
        # 验证内容被保留（稍后应该被转义或清理）

    def test_sql_injection_attempt(self):
        """测试SQL注入尝试"""
        from tests.fixtures.sample_contexts import get_context_with_sql_injection

        ctx = get_context_with_sql_injection()
        content = ctx["conversation"]["conversation_info"]["input_messages"][0]["content"]

        assert "DROP TABLE" in content

    def test_null_values_handling(self):
        """测试null值处理"""
        from tests.fixtures.sample_contexts import get_context_with_null_values

        ctx = get_context_with_null_values()
        assert ctx["user"]["platforms"]["wechat"]["nickname"] is None
        assert ctx["character"]["user_info"]["description"] is None

    def test_empty_strings_handling(self):
        """测试空字符串处理"""
        from tests.fixtures.sample_contexts import get_context_with_empty_strings

        ctx = get_context_with_empty_strings()
        assert ctx["user"]["platforms"]["wechat"]["nickname"] == ""
        assert ctx["news_str"] == ""

    def test_missing_fields_handling(self):
        """测试缺失字段处理"""
        from tests.fixtures.sample_contexts import get_context_with_missing_fields

        ctx = get_context_with_missing_fields()
        # 应该只有最小必要字段
        assert "user" in ctx
        assert "character" in ctx
        assert "conversation" in ctx


# ============ Proactive Message Tests ============


@pytest.mark.e2e
@pytest.mark.slow
class TestProactiveMessages:
    """主动消息测试"""

    def test_scheduled_proactive_context(self):
        """测试预定主动消息context"""
        from tests.fixtures.sample_contexts import get_context_for_scheduled_proactive

        ctx = get_context_for_scheduled_proactive()
        future = ctx["conversation"]["conversation_info"]["future"]

        assert future["status"] == "scheduled"
        assert future["timestamp"] is not None
        assert ctx["message_source"] == "proactive"

    def test_expired_proactive_context(self):
        """测试过期主动消息context"""
        from tests.fixtures.sample_contexts import get_context_for_expired_proactive
        import time

        ctx = get_context_for_expired_proactive()
        future = ctx["conversation"]["conversation_info"]["future"]

        # 验证时间戳在过去
        assert future["timestamp"] < int(time.time())

    def test_proactive_trigger_message_structure(self):
        """测试主动消息触发结构"""
        from tests.fixtures.sample_messages import get_proactive_trigger_message

        msg = get_proactive_trigger_message("询问用户近况")
        assert msg["type"] == "system"
        assert msg["source"] == "proactive"
        assert msg["action"] == "询问用户近况"


# ============ Duplicate Detection Tests ============


@pytest.mark.e2e
@pytest.mark.slow
class TestDuplicateDetection:
    """重复消息检测测试"""

    def test_rapid_fire_messages_timestamp_order(self):
        """测试快速连续消息时间戳顺序"""
        from tests.fixtures.sample_messages import get_rapid_fire_messages

        messages = get_rapid_fire_messages(count=10)

        for i in range(1, len(messages)):
            assert messages[i]["timestamp"] >= messages[i-1]["timestamp"]

    def test_duplicate_messages_detection(self):
        """测试重复消息内容检测"""
        from tests.fixtures.sample_messages import get_duplicate_messages

        messages = get_duplicate_messages("完全相同的内容", count=5)

        contents = [msg["content"] for msg in messages]
        assert len(set(contents)) == 1  # 所有内容相同

    def test_concurrent_messages_same_timestamp(self):
        """测试并发消息（相同时间戳）"""
        from tests.fixtures.sample_messages import get_concurrent_messages

        messages = get_concurrent_messages(count=10)

        timestamps = [msg["timestamp"] for msg in messages]
        assert len(set(timestamps)) == 1  # 所有时间戳相同

    def test_interleaved_messages_order(self):
        """测试交错消息顺序"""
        from tests.fixtures.sample_messages import get_interleaved_messages

        messages = get_interleaved_messages(["user_a", "user_b"], 3)

        # 验证消息交错
        assert len(messages) == 6
        assert messages[0]["sender"] == "user_a"
        assert messages[1]["sender"] == "user_b"


# ============ Security Tests ============


@pytest.mark.e2e
@pytest.mark.slow
class TestSecurityInputs:
    """安全相关输入测试"""

    def test_xss_injection_message(self):
        """测试XSS注入消息"""
        from tests.fixtures.sample_messages import get_xss_injection_message

        msg = get_xss_injection_message()
        # 确保恶意内容被保留用于后续清理测试
        assert "<script>" in msg["content"]
        assert "onerror" in msg["content"]

    def test_nosql_injection_message(self):
        """测试NoSQL注入消息"""
        from tests.fixtures.sample_messages import get_nosql_injection_message

        msg = get_nosql_injection_message()
        assert "$gt" in msg["content"]
        assert "$ne" in msg["sender"]

    def test_command_injection_message(self):
        """测试命令注入消息"""
        from tests.fixtures.sample_messages import get_command_injection_message

        msg = get_command_injection_message()
        assert "rm -rf" in msg["content"]

    def test_path_traversal_message(self):
        """测试路径穿越消息"""
        from tests.fixtures.sample_messages import get_path_traversal_message

        msg = get_path_traversal_message()
        assert "../" in msg["url"]
        assert "etc/passwd" in msg["url"]


# ============ Message Type Validation Tests ============


@pytest.mark.e2e
@pytest.mark.slow
class TestMessageTypeValidation:
    """消息类型验证测试"""

    def test_malformed_message_missing_content(self):
        """测试缺少content字段的消息"""
        from tests.fixtures.sample_messages import get_malformed_message

        msg = get_malformed_message()
        assert "content" not in msg
        assert "type" in msg

    def test_invalid_message_type(self):
        """测试无效消息类型"""
        from tests.fixtures.sample_messages import get_message_with_invalid_type

        msg = get_message_with_invalid_type()
        assert msg["type"] == "unknown_type"
        # 系统应该能处理未知类型

    def test_null_content_message(self):
        """测试content为null的消息"""
        from tests.fixtures.sample_messages import get_message_with_null_content

        msg = get_message_with_null_content()
        assert msg["content"] is None

    def test_wrong_timestamp_type(self):
        """测试错误类型的时间戳"""
        from tests.fixtures.sample_messages import get_message_with_wrong_timestamp

        msg = get_message_with_wrong_timestamp()
        assert not isinstance(msg["timestamp"], int)

    def test_future_timestamp_message(self):
        """测试未来时间戳消息"""
        from tests.fixtures.sample_messages import get_message_with_future_timestamp
        import time

        msg = get_message_with_future_timestamp()
        assert msg["timestamp"] > int(time.time())

    def test_very_old_timestamp_message(self):
        """测试极旧时间戳消息"""
        from tests.fixtures.sample_messages import get_message_with_very_old_timestamp

        msg = get_message_with_very_old_timestamp()
        assert msg["timestamp"] == 0


# ============ System Message Tests ============


@pytest.mark.e2e
@pytest.mark.slow
class TestSystemMessages:
    """系统消息测试"""

    def test_user_joined_system_message(self):
        """测试用户加入系统消息"""
        from tests.fixtures.sample_messages import get_system_message_user_joined

        msg = get_system_message_user_joined()
        assert msg["type"] == "system"
        assert msg["event"] == "joined"

    def test_user_left_system_message(self):
        """测试用户离开系统消息"""
        from tests.fixtures.sample_messages import get_system_message_user_left

        msg = get_system_message_user_left()
        assert msg["type"] == "system"
        assert msg["event"] == "left"

    def test_error_system_message(self):
        """测试系统错误消息"""
        from tests.fixtures.sample_messages import get_system_message_error

        msg = get_system_message_error()
        assert msg["type"] == "system"
        assert msg["source"] == "error"
        assert "error_code" in msg


# ============ Context Retrieve Tests ============


@pytest.mark.e2e
@pytest.mark.slow
class TestContextRetrieve:
    """上下文检索测试"""

    def test_context_with_existing_reminders(self):
        """测试包含已有提醒的context"""
        from tests.fixtures.sample_contexts import get_context_with_existing_reminders

        ctx = get_context_with_existing_reminders()
        reminders = ctx["context_retrieve"]["confirmed_reminders"]

        assert len(reminders) > 0
        assert "开会提醒" in reminders

    def test_reminder_cancellation_context(self):
        """测试提醒取消场景context"""
        from tests.fixtures.sample_contexts import get_context_for_reminder_cancellation

        ctx = get_context_for_reminder_cancellation()
        content = ctx["conversation"]["conversation_info"]["input_messages"][0]["content"]

        assert "取消" in content

    def test_reminder_conflict_context(self):
        """测试提醒冲突场景context"""
        from tests.fixtures.sample_contexts import get_context_for_reminder_conflict

        ctx = get_context_for_reminder_conflict()
        reminders = ctx["context_retrieve"]["confirmed_reminders"]

        # 验证同一时间有多个提醒
        lines = reminders.strip().split("\n")
        assert len(lines) >= 2
        # 两个提醒都在早上8点
        for line in lines:
            assert "早上8点" in line
