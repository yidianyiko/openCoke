# -*- coding: utf-8 -*-
import os
import time

import sys
sys.path.append(".")

import traceback
import logging
from logging import getLogger
logging.basicConfig(level=logging.INFO)
logger = getLogger(__name__)
import random

from framework.agent.base_agent import AgentStatus
from framework.agent.llmagent.doubao_llmagent import DouBaoLLMAgent
from conf.config import CONF
from volcenginesdkarkruntime import Ark

from qiaoyun.prompt.system_prompt import *
from qiaoyun.prompt.chat_taskprompt import *
from qiaoyun.prompt.chat_contextprompt import *
from qiaoyun.prompt.chat_noticeprompt import *

from util.time_util import str2timestamp, parse_relative_time, is_time_in_past
from dao.reminder_dao import ReminderDAO

doubao_client = Ark(
    base_url="https://ark.cn-beijing.volces.com/api/v3",
)

# 需要 export ARK_API_KEY="xxxx"
class QiaoyunChatResponseAgent(DouBaoLLMAgent):
    default_systemp_template = SYSTEMPROMPT_小说越狱

    default_userp_template = \
    "## 你的任务" + "\n" + \
    TASKPROMPT_小说书写任务 + "\n" + \
    "\n" + \
    TASKPROMPT_微信对话 + "\n" + \
    TASKPROMPT_微信对话_推理要求_纯文本 + "\n" + \
    TASKPROMPT_提醒识别 + "\n" + \
    "\n" + \
    "## 上下文" + "\n" + \
    CONTEXTPROMPT_时间 + "\n" + \
    "\n" + \
    CONTEXTPROMPT_人物信息 + "\n" + \
    "\n" + \
    CONTEXTPROMPT_人物资料 + "\n" + \
    "\n" + \
    CONTEXTPROMPT_用户资料 + "\n" + \
    "\n" + \
    CONTEXTPROMPT_待办提醒 + "\n" + \
    "\n" + \
    CONTEXTPROMPT_人物知识和技能 + "\n" + \
    "\n" + \
    CONTEXTPROMPT_人物状态 + "\n" + \
    "\n" + \
    CONTEXTPROMPT_当前目标 + "\n" + \
    "\n" + \
    CONTEXTPROMPT_当前的人物关系 + "\n" + \
    "\n" + \
    CONTEXTPROMPT_历史对话 + "\n" + \
    "\n" + \
    CONTEXTPROMPT_最新聊天消息 + "\n" + \
    "\n" + \
    "## 注意事项" + "\n" + \
    NOTICE_常规注意事项_分段消息 + "\n" + \
    NOTICE_常规注意事项_生成优化 + "\n" + \
    NOTICE_常规注意事项_空输入处理

    default_output_schema = {
        "type": "object",
        "properties": {
            "InnerMonologue": {
                "type": "string",
                "description": "角色的内心独白"
            },
            "ChatResponse": {
                "type": "string",
                "description": "像发微信一样，一句话分成多条发送。"
            },
            # "RefinedChatResponse": {
            #     "type": "string",
            #     "description": "重新审视之后的改良回复。你可以在句子之间使用<换行>来表示分段，用来表示多段消息。"
            # },
            "MultiModalResponses": {
                "type": "array",
                "description": "角色的回复，可能包含多种类型。",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {
                            "type": "string",
                            "enum": ["text", "voice"],
                            "description": "消息的类型"
                        },
                        "content": {
                            "type": "string",
                            "description": "根据消息类型的不同，包含不同的内容"
                        },
                        "emotion": {
                            "type": "string",
                            "enum": ["无", "高兴","悲伤","愤怒","害怕","惊讶","厌恶","魅惑"],
                            "description": "仅对语音消息有效，表示语音的感情色彩"
                        },
                    },
                    "required": ["type", "content"],
                    "additionalProperties": True
                }
            },
            "ChatCatelogue": {
                "type": "string",
                "description": "在MultiModalResponses当中是否涉及角色所熟悉的知识，或者涉及她的专业知识，或者她的一些人设和故事。"
            },
            "RelationChange": {
                "type": "object",
                "description": "当下的关系变化",
                "properties": {
                    "Closeness": {
                        "type": "number",
                        "description": "亲密度数值变化",
                    },
                    "Trustness": {
                        "type": "number",
                        "description": "信任度数值变化",
                    },
                }
            },
            "FutureResponse": {
                "type": "object",
                "description": "假设用户在此之后一直没有任何回复，角色在未来什么时间可能进行再次的未来主动消息",
                "properties": {
                    "FutureResponseTime": {
                        "type": "string",
                        "description": "未来主动的消息时间，格式为xxxx年xx月xx日xx时xx分。",
                    },
                    "FutureResponseAction": {
                        "type": "string",
                        "description": "未来主动消息的大致内容，大约10-20个字。",
                    },
                }
            },
            
        },
        "required": [
            "InnerMonologue",
            "MultiModalResponses",
            "ChatCatelogue",
            "RelationChange",
            "FutureResponse",
            
        ]
    }

    def __init__(self, context=None, client=doubao_client, systemp_template=default_systemp_template, userp_template=default_userp_template, output_schema=default_output_schema, default_input=None, max_retries=3, name=None, stream=False, model="doubao_1.5_pro", extra_args=None):
        super().__init__(context, client, systemp_template, userp_template, output_schema, default_input, max_retries, name, stream, model, extra_args)

    def _posthandle(self):
        # 关系变化
        relation_change = self.resp.get("RelationChange", {"Closeness": 0, "Trustness": 0})
        if isinstance(relation_change, str):
            try:
                import json
                relation_change = json.loads(relation_change)
            except Exception:
                relation_change = {"Closeness": 0, "Trustness": 0}
        Closeness_Change = relation_change.get("Closeness", 0)
        Trustness_Change = relation_change.get("Trustness", 0)

        self.context["relation"]["relationship"]["closeness"] = self.context["relation"]["relationship"]["closeness"] + Closeness_Change
        if self.context["relation"]["relationship"]["closeness"] > 100:
            self.context["relation"]["relationship"]["closeness"] = 100
        if self.context["relation"]["relationship"]["closeness"] < 0:
            self.context["relation"]["relationship"]["closeness"] = 0
        
        self.context["relation"]["relationship"]["trustness"] = self.context["relation"]["relationship"]["trustness"] + Trustness_Change
        if self.context["relation"]["relationship"]["trustness"] > 100:
            self.context["relation"]["relationship"]["trustness"] = 100
        if self.context["relation"]["relationship"]["trustness"] < 0:
            self.context["relation"]["relationship"]["trustness"] = 0
            
        # 禁用提醒处理，改为消费前置代理输出
        # 消费前置提醒代理的输出，附加用户文案与确认提示
        try:
            rem_ctx = self.context.get("reminders", {})
            ui_msgs = rem_ctx.get("ui_messages", []) or []
            needs_conf = rem_ctx.get("needs_confirmation", []) or []
            append_text = ""
            for m in ui_msgs:
                append_text += "\n\n" + str(m)
            if needs_conf:
                append_text += "\n\n" + "\n".join(needs_conf)
            if append_text and self.resp.get("MultiModalResponses"):
                for response in reversed(self.resp["MultiModalResponses"]):
                    if response.get("type") == "text":
                        response["content"] += append_text
                        break
        except Exception:
            logger.warning("append reminders ui_messages failed")

        # Future Response
        if "proactive_times" not in self.context["conversation"]["conversation_info"]["future"]:
            self.context["conversation"]["conversation_info"]["future"]["proactive_times"] = 0
        future_proactive_times = self.context["conversation"]["conversation_info"]["future"]["proactive_times"]

        future_resp = self.resp.get("FutureResponse", {"FutureResponseTime": "", "FutureResponseAction": "无"})
        if isinstance(future_resp, str):
            try:
                import json
                future_resp = json.loads(future_resp)
            except Exception:
                future_resp = {"FutureResponseTime": "", "FutureResponseAction": "无"}
        if future_resp.get("FutureResponseAction", "无") != "无":
            if random.random() < (0.25 ** (future_proactive_times + 1) + 0.05):
                self.context["conversation"]["conversation_info"]["future"]["timestamp"] = str2timestamp(future_resp.get("FutureResponseTime", ""))
                self.context["conversation"]["conversation_info"]["future"]["action"] = future_resp.get("FutureResponseAction", "无")
                # self.context["conversation"]["conversation_info"]["proactive_times"] = self.context["conversation"]["conversation_info"]["proactive_times"] + 1
                logger.info("Book a new future action:" + str(self.context["conversation"]["conversation_info"]["future"]))
            else:
                self.context["conversation"]["conversation_info"]["future"]["timestamp"] = None
                self.context["conversation"]["conversation_info"]["future"]["action"] = None
    
    def _handle_reminders(self):
        return
    
    def _parse_reminder_time(self, reminder):
        """
        解析提醒时间
        
        Args:
            reminder: 提醒对象
            
        Returns:
            int: 时间戳，失败返回 None
        """
        # 优先使用已解析的时间
        if reminder.get("time_resolved"):
            timestamp = str2timestamp(reminder["time_resolved"])
            if timestamp:
                return timestamp
        
        # 尝试解析时间（不依赖 time_type）
        time_original = reminder.get("time_original", "")
        timestamp = parse_relative_time(time_original)
        if timestamp:
            return timestamp
        timestamp = str2timestamp(time_original)
        if timestamp:
            return timestamp
        
        return None

    def _normalize_recurrence(self, rec):
        if not isinstance(rec, dict):
            return {"enabled": False}
        enabled = bool(rec.get("enabled", False))
        rtype = rec.get("type") or rec.get("frequency")
        interval = rec.get("interval", 1)
        time_of_day = rec.get("time_of_day")
        weekdays = rec.get("weekdays")
        month_days = rec.get("month_days")
        norm = {"enabled": enabled}
        if rtype:
            # 将 minute 统一映射为 interval（分钟），便于后端计算
            if rtype == "minute":
                norm["type"] = "interval"
            else:
                norm["type"] = rtype
        if interval is not None:
            norm["interval"] = interval
        if time_of_day:
            norm["time_of_day"] = time_of_day
        if weekdays:
            norm["weekdays"] = weekdays
        if month_days:
            norm["month_days"] = month_days
        return norm
