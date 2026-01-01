# -*- coding: utf-8 -*-
"""
主动消息相关的保留测试

保留与 Schema 有效性相关的属性测试，移除对已废弃 FutureMessageWorkflow
与 ProactiveMessageTriggerService 的集成测试。
"""
import sys
sys.path.append(".")

import unittest
from hypothesis import given, settings, strategies as st

from agent.agno_agent.schemas.chat_response_schema import MultiModalResponse
from agent.agno_agent.schemas.future_message_schema import FutureMessageResponse


@st.composite
def multimodal_response_strategy(draw):
    msg_type = draw(st.sampled_from(["text", "voice", "photo"]))
    content = draw(
        st.text(
            min_size=1,
            max_size=100,
            alphabet=st.characters(
                whitelist_categories=("L", "N", "P", "Z"),
                whitelist_characters="，.！？、",
            ),
        )
    )
    if msg_type == "voice":
        emotion = draw(st.sampled_from([None, "无", "高兴", "悲伤", "愤怒"]))
        return {"type": msg_type, "content": content, "emotion": emotion}
    else:
        return {"type": msg_type, "content": content}


@st.composite
def future_message_response_strategy(draw):
    num_responses = draw(st.integers(min_value=1, max_value=3))
    responses = [draw(multimodal_response_strategy()) for _ in range(num_responses)]
    return {
        "InnerMonologue": draw(st.text(min_size=0, max_size=200)),
        "MultiModalResponses": responses,
        "ChatCatelogue": draw(st.sampled_from(["是", "否"])),
        "RelationChange": {
            "Closeness": draw(st.floats(min_value=-10, max_value=10, allow_nan=False, allow_infinity=False)),
            "Trustness": draw(st.floats(min_value=-10, max_value=10, allow_nan=False, allow_infinity=False)),
        },
        "FutureResponse": {
            "FutureResponseTime": draw(st.sampled_from(["2025年12月25日09时00分", "2025年01月01日10时30分", ""])),
            "FutureResponseAction": draw(st.sampled_from(["发送问候", "检查进度", "无"])),
        },
    }


class TestOutputValidityProperty(unittest.TestCase):
    """
    Property 9: 主动消息输出有效性
    """

    @given(response_data=future_message_response_strategy())
    @settings(max_examples=100)
    def test_property_9_multimodal_responses_valid_types(self, response_data):
        valid_types = {"text", "voice", "photo"}
        multimodal_responses = response_data.get("MultiModalResponses", [])
        self.assertGreater(len(multimodal_responses), 0)
        for response in multimodal_responses:
            self.assertIn(response.get("type"), valid_types)

    @given(response_data=future_message_response_strategy())
    @settings(max_examples=100)
    def test_property_9_multimodal_responses_have_content(self, response_data):
        multimodal_responses = response_data.get("MultiModalResponses", [])
        for response in multimodal_responses:
            content = response.get("content", "")
            self.assertTrue(str(content).strip())

    def test_future_message_response_schema_validation(self):
        valid_data = {
            "InnerMonologue": "思考中",
            "MultiModalResponses": [
                {"type": "text", "content": "你好！"},
                {"type": "voice", "content": "语音内容", "emotion": "高兴"},
            ],
            "ChatCatelogue": "否",
            "RelationChange": {"Closeness": 1, "Trustness": 0},
            "FutureResponse": {
                "FutureResponseTime": "2025年12月25日09时00分",
                "FutureResponseAction": "继续关心",
            },
        }
        response = FutureMessageResponse(**valid_data)
        self.assertEqual(len(response.MultiModalResponses), 2)
        self.assertEqual(response.MultiModalResponses[0].type, "text")
        self.assertEqual(response.MultiModalResponses[1].type, "voice")

    def test_multimodal_response_type_validation(self):
        for valid_type in ["text", "voice", "photo"]:
            response = MultiModalResponse(type=valid_type, content="测试内容")
            self.assertEqual(response.type, valid_type)
        with self.assertRaises(Exception):
            MultiModalResponse(type="invalid", content="测试内容")


if __name__ == "__main__":
    unittest.main()

