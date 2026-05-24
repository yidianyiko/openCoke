# -*- coding: utf-8 -*-
"""
Outbound message delivery helpers for the agent runner.
"""

import random
from typing import Callable, Optional, Tuple

from agent.tool.image import upload_image
from agent.tool.voice import character_voice
from agent.util.message_util import send_message_via_context
from util.log_util import get_logger

logger = get_logger(__name__)

typing_speed = 2.2


class _OutboundSendInterrupted(Exception):
    """Raised when a newer user message arrives between outbound writes."""

    def __init__(self, sent_messages: list[dict] | None = None) -> None:
        super().__init__("outbound send interrupted")
        self.sent_messages = sent_messages or []


def _send_single_message(
    context,
    multimodal_response,
    expect_output_timestamp,
    is_first=False,
    interrupt_check: Callable[[], bool] | None = None,
):
    """发送单条多模态消息"""
    outputmessage = None
    sent_messages = []
    msg_type = multimodal_response.get("type", "text")
    content = multimodal_response.get("content", "")

    # ========== 去重检查：跳过 rollback 恢复场景中已发送的内容 ==========
    turn_sent = (
        context.get("conversation", {})
        .get("conversation_info", {})
        .get("turn_sent_contents", [])
    )
    if turn_sent and content in turn_sent:
        logger.info(f"[去重] 跳过已发送内容: {content[:30]}...")
        return None, expect_output_timestamp

    if msg_type == "voice":
        voice_messages = character_voice(
            content, multimodal_response.get("emotion", "无")
        )
        for voice_url, voice_length in voice_messages:
            if interrupt_check is not None:
                if interrupt_check():
                    raise _OutboundSendInterrupted(sent_messages)
            if not is_first:
                expect_output_timestamp += int(voice_length / 1000) + random.randint(
                    2, 5
                )
            outputmessage = send_message_via_context(
                context,
                message=content,
                message_type="voice",
                expect_output_timestamp=expect_output_timestamp,
                metadata={"url": voice_url, "voice_length": voice_length},
            )
            if outputmessage is not None:
                sent_messages.append(outputmessage)
    elif msg_type == "photo":
        photo_id = (
            str(content).replace("「", "").replace("」", "").replace("照片", "", 1)
        )
        image_url = upload_image(photo_id)
        if image_url is not None:
            context["conversation"]["conversation_info"]["photo_history"].append(
                photo_id
            )
            if len(context["conversation"]["conversation_info"]["photo_history"]) > 12:
                context["conversation"]["conversation_info"]["photo_history"] = context[
                    "conversation"
                ]["conversation_info"]["photo_history"][-12:]
            if not is_first:
                expect_output_timestamp += random.randint(2, 8)
            if interrupt_check is not None:
                if interrupt_check():
                    raise _OutboundSendInterrupted(sent_messages)
            outputmessage = send_message_via_context(
                context,
                message=content,
                message_type="image",
                expect_output_timestamp=expect_output_timestamp,
                metadata={"url": image_url},
            )
    else:  # text
        text_message = str(content).replace("<换行>", "\n")
        if not is_first:
            expect_output_timestamp += int(len(text_message) / typing_speed)
        if interrupt_check is not None:
            if interrupt_check():
                raise _OutboundSendInterrupted(sent_messages)
        outputmessage = send_message_via_context(
            context,
            message=text_message,
            message_type="text",
            expect_output_timestamp=expect_output_timestamp,
        )
    return outputmessage, expect_output_timestamp


def _chat_response_timeout_fallback(
    input_message: str, context: dict | None = None
) -> str:
    context = context or {}
    if (
        context.get("prepare_reminder_intent_hint") == "stop_or_cancel"
        and context.get("orchestrator", {}).get("need_reminder_detect") is True
        and not any(
            result.get("tool_name") == "提醒操作"
            for result in context.get("tool_results") or []
            if isinstance(result, dict)
        )
    ):
        return "你是想停掉哪条提醒？告诉我具体是哪条，我再帮你处理。"
    if "计划" in str(input_message or ""):
        return "我这次没能及时查到昨天那份计划。你把计划内容再发我一遍，我可以继续帮你整理或设置提醒。"
    return "我没接住你刚才的意思。你可以换个说法再说一次吗？"


def _send_chat_response_fallback(
    *,
    context: dict,
    input_message: str,
    expect_output_timestamp: int,
    all_multimodal_responses: list,
) -> Tuple[Optional[dict], int]:
    multimodal_response = {
        "type": "text",
        "content": _chat_response_timeout_fallback(input_message, context),
    }
    all_multimodal_responses.append(multimodal_response)
    return _send_single_message(
        context=context,
        multimodal_response=multimodal_response,
        expect_output_timestamp=expect_output_timestamp,
        is_first=True,
    )


OutboundSendInterrupted = _OutboundSendInterrupted
chat_response_timeout_fallback = _chat_response_timeout_fallback
send_chat_response_fallback = _send_chat_response_fallback
send_single_message = _send_single_message
