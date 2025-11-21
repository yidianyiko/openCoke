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
    "\n" + \
    "## 上下文" + "\n" + \
    CONTEXTPROMPT_时间 + "\n" + \
    "\n" + \
    CONTEXTPROMPT_新闻 + "\n" + \
    "\n" + \
    CONTEXTPROMPT_人物信息 + "\n" + \
    "\n" + \
    CONTEXTPROMPT_人物资料 + "\n" + \
    "\n" + \
    CONTEXTPROMPT_用户资料 + "\n" + \
    "\n" + \
    CONTEXTPROMPT_人物知识和技能 + "\n" + \
    "\n" + \
    CONTEXTPROMPT_人物手机相册 + "\n" + \
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
                "description": "角色的回复，你可以在句子之间使用<换行>来表示分段，用来表示换行。"
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
            "DetectedReminders": {
                "type": "array",
                "description": "从用户消息中识别到的提醒任务列表，如果没有识别到则为空数组",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "提醒的简短标题，如'开会'、'吃药'、'写报告'"
                        },
                        "time_original": {
                            "type": "string",
                            "description": "用户原始的时间表达，如'明天下午3点'、'30分钟后'、'每天早上8点'"
                        },
                        "time_resolved": {
                            "type": "string",
                            "description": "解析后的绝对时间，格式：xxxx年xx月xx日xx时xx分，如果无法确定则留空"
                        },
                        "time_type": {
                            "type": "string",
                            "enum": ["absolute", "relative", "ambiguous"],
                            "description": "时间类型：absolute=绝对时间(2024年12月1日)，relative=相对时间(30分钟后)，ambiguous=模糊时间(1:43)"
                        },
                        "requires_confirmation": {
                            "type": "boolean",
                            "description": "是否需要用户确认，如'1:43'不确定上午下午，或时间已过期"
                        },
                        "confirmation_prompt": {
                            "type": "string",
                            "description": "需要确认时的提示语，如'你是说明天下午1点43分吗？'"
                        },
                        "recurrence": {
                            "type": "object",
                            "description": "周期信息，如果不是周期提醒则为null或enabled=false",
                            "properties": {
                                "enabled": {
                                    "type": "boolean",
                                    "description": "是否启用周期"
                                },
                                "type": {
                                    "type": "string",
                                    "enum": ["daily", "weekly", "monthly", "yearly"],
                                    "description": "周期类型：每天/每周/每月/每年"
                                },
                                "interval": {
                                    "type": "number",
                                    "description": "间隔数，如每2天则为2，默认为1"
                                }
                            }
                        },
                        "action_template": {
                            "type": "string",
                            "description": "到期时要说的话，如'该开会了'、'记得吃药哦'"
                        }
                    },
                    "required": ["title", "time_original", "action_template"]
                }
            },
        }
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

        # 处理提醒任务
        self._handle_reminders()

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
        """处理识别到的提醒任务"""
        import uuid
        
        reminders = self.resp.get("DetectedReminders", [])
        if not reminders:
            return
        
        reminder_dao = ReminderDAO()
        conversation_id = str(self.context["conversation"]["_id"])
        user_id = str(self.context["user"]["_id"])
        character_id = str(self.context["character"]["_id"])
        
        confirmed_reminders = []
        needs_confirmation = []
        
        for reminder in reminders:
            try:
                # 解析时间
                timestamp = self._parse_reminder_time(reminder)
                
                # 判断是否需要确认
                if reminder.get("requires_confirmation") or timestamp is None or is_time_in_past(timestamp):
                    needs_confirmation.append(reminder)
                    continue
                
                # 创建提醒记录
                reminder_doc = {
                    "conversation_id": conversation_id,
                    "user_id": user_id,
                    "character_id": character_id,
                    "reminder_id": str(uuid.uuid4()),
                    "title": reminder.get("title", "提醒"),
                    "action_template": reminder.get("action_template", f"提醒：{reminder.get('title')}"),
                    "next_trigger_time": timestamp,
                    "time_original": reminder.get("time_original", ""),
                    "timezone": "Asia/Shanghai",
                    "recurrence": reminder.get("recurrence", {"enabled": False}),
                    "status": "confirmed",
                    "requires_confirmation": False
                }
                
                # 保存到数据库
                reminder_dao.create_reminder(reminder_doc)
                confirmed_reminders.append(reminder)
                logger.info(f"创建提醒: {reminder['title']} at {timestamp}")
                
            except Exception as e:
                logger.error(f"处理提醒失败: {traceback.format_exc()}")
        
        # 追加确认问题到回复
        if needs_confirmation:
            confirmation_text = "\n\n"
            for r in needs_confirmation:
                prompt = r.get("confirmation_prompt", f"你是说{r.get('time_original')}提醒你{r.get('title')}吗？")
                confirmation_text += prompt + "\n"
            
            # 追加到最后一条文本消息
            if self.resp.get("MultiModalResponses"):
                for response in reversed(self.resp["MultiModalResponses"]):
                    if response.get("type") == "text":
                        response["content"] += confirmation_text
                        break
        
        reminder_dao.close()
    
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
        
        # 尝试解析相对时间
        time_original = reminder.get("time_original", "")
        if reminder.get("time_type") == "relative":
            timestamp = parse_relative_time(time_original)
            if timestamp:
                return timestamp
        
        # 尝试直接解析
        timestamp = str2timestamp(time_original)
        if timestamp:
            return timestamp
        
        return None

