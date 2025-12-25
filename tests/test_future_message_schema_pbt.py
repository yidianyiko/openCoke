# -*- coding: utf-8 -*-
"""
FutureMessageResponse Schema 属性测试 (Property-Based Testing)

Property 1: Schema 结构完整性
- FutureMessageResponse 包含所有必需字段（InnerMonologue、MultiModalResponses、RelationChange、FutureResponse）
- FutureResponse 包含 FutureResponseTime 和 FutureResponseAction 子字段
- MultiModalResponse 的 type 字段只接受 "text"、"voice"、"photo" 三种值

Validates: Requirements 1.1, 1.2, 1.3
"""
import sys

sys.path.append(".")

import unittest

from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from agent.agno_agent.schemas.chat_response_schema import (
    FutureResponseModel,
    MultiModalResponse,
    RelationChangeModel,
)
from agent.agno_agent.schemas.future_message_schema import FutureMessageResponse

# ============================================================================
# Hypothesis Strategies for generating test data
# ============================================================================

# Valid message types as per Requirement 1.3
VALID_MESSAGE_TYPES = ["text", "voice", "photo"]

# Valid emotions for voice messages
VALID_EMOTIONS = ["无", "高兴", "悲伤", "愤怒", "害怕", "惊讶", "厌恶", None]


# Strategy for generating valid MultiModalResponse
@st.composite
def multimodal_response_strategy(draw):
    """Generate valid MultiModalResponse objects"""
    msg_type = draw(st.sampled_from(VALID_MESSAGE_TYPES))
    content = draw(st.text(min_size=0, max_size=500))

    # emotion is only meaningful for voice type, but can be set for any type
    emotion = draw(st.sampled_from(VALID_EMOTIONS))

    return MultiModalResponse(type=msg_type, content=content, emotion=emotion)


# Strategy for generating RelationChangeModel
@st.composite
def relation_change_strategy(draw):
    """Generate valid RelationChangeModel objects"""
    closeness = draw(
        st.floats(min_value=-100, max_value=100, allow_nan=False, allow_infinity=False)
    )
    trustness = draw(
        st.floats(min_value=-100, max_value=100, allow_nan=False, allow_infinity=False)
    )
    return RelationChangeModel(Closeness=closeness, Trustness=trustness)


# Strategy for generating FutureResponseModel
@st.composite
def future_response_strategy(draw):
    """Generate valid FutureResponseModel objects"""
    time_str = draw(st.text(min_size=0, max_size=50))
    action_str = draw(st.text(min_size=0, max_size=100))
    return FutureResponseModel(
        FutureResponseTime=time_str, FutureResponseAction=action_str
    )


# Strategy for generating complete FutureMessageResponse
@st.composite
def future_message_response_strategy(draw):
    """Generate valid FutureMessageResponse objects"""
    inner_monologue = draw(st.text(min_size=0, max_size=500))
    multimodal_responses = draw(
        st.lists(multimodal_response_strategy(), min_size=0, max_size=5)
    )
    chat_catelogue = draw(st.sampled_from(["是", "否", ""]))
    relation_change = draw(relation_change_strategy())
    future_response = draw(future_response_strategy())

    return FutureMessageResponse(
        InnerMonologue=inner_monologue,
        MultiModalResponses=multimodal_responses,
        ChatCatelogue=chat_catelogue,
        RelationChange=relation_change,
        FutureResponse=future_response,
    )


# ============================================================================
# Property-Based Tests
# ============================================================================


class TestFutureMessageResponseSchemaProperty(unittest.TestCase):
    """
    Property 1: Schema 结构完整性

    For any FutureMessageResponse 对象，该对象应包含所有必需字段
    （InnerMonologue、MultiModalResponses、RelationChange、FutureResponse），
    且 FutureResponse 应包含 FutureResponseTime 和 FutureResponseAction 子字段，
    MultiModalResponse 的 type 字段只接受 "text"、"voice"、"photo" 三种值.

    Validates: Requirements 1.1, 1.2, 1.3
    """

    @given(future_message_response_strategy())
    @settings(max_examples=100)
    def test_property_1_1_required_fields_exist(self, response: FutureMessageResponse):
        """
        Property 1.1: FutureMessageResponse 包含所有必需字段

        Validates: Requirement 1.1
        """
        # Verify all required fields exist
        self.assertTrue(hasattr(response, "InnerMonologue"))
        self.assertTrue(hasattr(response, "MultiModalResponses"))
        self.assertTrue(hasattr(response, "RelationChange"))
        self.assertTrue(hasattr(response, "FutureResponse"))

        # Verify field types
        self.assertIsInstance(response.InnerMonologue, str)
        self.assertIsInstance(response.MultiModalResponses, list)
        self.assertIsInstance(response.RelationChange, RelationChangeModel)
        self.assertIsInstance(response.FutureResponse, FutureResponseModel)

    @given(future_message_response_strategy())
    @settings(max_examples=100)
    def test_property_1_2_future_response_subfields(
        self, response: FutureMessageResponse
    ):
        """
        Property 1.2: FutureResponse 包含 FutureResponseTime 和 FutureResponseAction 子字段

        Validates: Requirement 1.2
        """
        future_response = response.FutureResponse

        # Verify FutureResponse has required subfields
        self.assertTrue(hasattr(future_response, "FutureResponseTime"))
        self.assertTrue(hasattr(future_response, "FutureResponseAction"))

        # Verify subfield types
        self.assertIsInstance(future_response.FutureResponseTime, str)
        self.assertIsInstance(future_response.FutureResponseAction, str)

    @given(future_message_response_strategy())
    @settings(max_examples=100)
    def test_property_1_3_multimodal_response_types(
        self, response: FutureMessageResponse
    ):
        """
        Property 1.3: MultiModalResponse 的 type 字段只接受 "text"、"voice"、"photo" 三种值

        Validates: Requirement 1.3
        """
        for mm_response in response.MultiModalResponses:
            self.assertIn(mm_response.type, VALID_MESSAGE_TYPES)

    @given(st.sampled_from(["invalid", "audio", "video", "image", "file", "123"]))
    @settings(max_examples=20)
    def test_property_1_3_invalid_type_rejected(self, invalid_type: str):
        """
        Property 1.3 (negative): Invalid type values should be rejected

        Validates: Requirement 1.3
        """
        with self.assertRaises(ValidationError):
            MultiModalResponse(type=invalid_type, content="test")

    @given(future_message_response_strategy())
    @settings(max_examples=100)
    def test_property_schema_serialization(self, response: FutureMessageResponse):
        """
        Property: Schema can be serialized to dict and JSON

        Validates: Schema usability
        """
        # Test model_dump
        data = response.model_dump()
        self.assertIsInstance(data, dict)
        self.assertIn("InnerMonologue", data)
        self.assertIn("MultiModalResponses", data)
        self.assertIn("RelationChange", data)
        self.assertIn("FutureResponse", data)

        # Test JSON serialization
        json_str = response.model_dump_json()
        self.assertIsInstance(json_str, str)

    @given(future_message_response_strategy())
    @settings(max_examples=100)
    def test_property_relation_change_structure(self, response: FutureMessageResponse):
        """
        Property: RelationChange contains Closeness and Trustness fields

        Validates: Requirement 1.1 (RelationChange structure)
        """
        relation_change = response.RelationChange

        self.assertTrue(hasattr(relation_change, "Closeness"))
        self.assertTrue(hasattr(relation_change, "Trustness"))
        self.assertIsInstance(relation_change.Closeness, (int, float))
        self.assertIsInstance(relation_change.Trustness, (int, float))


class TestFutureMessageResponseDefaults(unittest.TestCase):
    """Test default values for FutureMessageResponse"""

    def test_default_values(self):
        """Test that default values are correctly set"""
        response = FutureMessageResponse()

        self.assertEqual(response.InnerMonologue, "")
        self.assertEqual(response.MultiModalResponses, [])
        self.assertEqual(response.ChatCatelogue, "否")
        self.assertIsInstance(response.RelationChange, RelationChangeModel)
        self.assertIsInstance(response.FutureResponse, FutureResponseModel)

        # Check nested defaults
        self.assertEqual(response.RelationChange.Closeness, 0)
        self.assertEqual(response.RelationChange.Trustness, 0)
        self.assertEqual(response.FutureResponse.FutureResponseTime, "")
        self.assertEqual(response.FutureResponse.FutureResponseAction, "无")

    def test_none_values_handled(self):
        """Test that None values are converted to defaults"""
        response = FutureMessageResponse(
            MultiModalResponses=None, RelationChange=None, FutureResponse=None
        )

        self.assertEqual(response.MultiModalResponses, [])
        self.assertIsInstance(response.RelationChange, RelationChangeModel)
        self.assertIsInstance(response.FutureResponse, FutureResponseModel)


class TestMultiModalResponseTypes(unittest.TestCase):
    """Test MultiModalResponse type validation"""

    def test_text_type(self):
        """Test text type is valid"""
        mm = MultiModalResponse(type="text", content="Hello")
        self.assertEqual(mm.type, "text")

    def test_voice_type(self):
        """Test voice type is valid"""
        mm = MultiModalResponse(type="voice", content="Hello", emotion="高兴")
        self.assertEqual(mm.type, "voice")
        self.assertEqual(mm.emotion, "高兴")

    def test_photo_type(self):
        """Test photo type is valid (Requirement 1.3)"""
        mm = MultiModalResponse(type="photo", content="image_url")
        self.assertEqual(mm.type, "photo")

    def test_all_valid_types(self):
        """Test all three valid types work"""
        for msg_type in VALID_MESSAGE_TYPES:
            mm = MultiModalResponse(type=msg_type, content="test")
            self.assertEqual(mm.type, msg_type)


if __name__ == "__main__":
    unittest.main()
