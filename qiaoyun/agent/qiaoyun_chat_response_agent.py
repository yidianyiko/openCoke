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
            "DetectedReminders": {
                "type": "array",
                "description": "从用户消息中识别到的提醒任务列表，如果没有识别到则为空数组",
                "items": {
                    "type": "object",
                    "properties": {
                        "operation": {
                            "type": "string",
                            "enum": ["create", "update", "delete", "list"],
                            "description": "提醒操作类型"
                        },
                        "target": {
                            "type": "object",
                            "description": "用于定位既有提醒的目标（update/delete）",
                            "properties": {
                                "reminder_id": {"type": "string"},
                                "by_title": {"type": "string"},
                                "by_time_hint": {"type": "string"}
                            }
                        },
                        "title": {"type": "string"},
                        "time_original": {"type": "string"},
                        "time_resolved": {"type": "string"},
                        "requires_confirmation": {"type": "boolean"},
                        "confirmation_prompt": {"type": "string"},
                        "recurrence": {
                            "type": "object",
                            "properties": {
                                "enabled": {"type": "boolean"},
                                "type": {"type": "string", "enum": ["daily", "weekly", "monthly", "yearly", "interval"]},
                                "interval": {"type": "number"}
                            }
                        },
                        "action_template": {"type": "string"},
                        "update_fields": {
                            "type": "object",
                            "description": "当operation为update时的更新内容",
                            "additionalProperties": True
                        },
                        "list_filter": {
                            "type": "object",
                            "description": "当operation为list时的过滤条件",
                            "additionalProperties": True
                        }
                    },
                    "required": ["operation"]
                }
            },
        },
        "required": [
            "InnerMonologue",
            "MultiModalResponses",
            "ChatCatelogue",
            "RelationChange",
            "FutureResponse",
            "DetectedReminders"
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
                op = reminder.get("operation", "create")
                if op == "create":
                    timestamp = self._parse_reminder_time(reminder)
                    if reminder.get("requires_confirmation") or timestamp is None or is_time_in_past(timestamp):
                        needs_confirmation.append(reminder)
                        continue
                    rec = reminder.get("recurrence", {"enabled": False})
                    rec = self._normalize_recurrence(rec)
                    reminder_doc = {
                        "conversation_id": conversation_id,
                        "user_id": user_id,
                        "character_id": character_id,
                        "reminder_id": str(uuid.uuid4()),
                        "title": reminder.get("title", "提醒"),
                        "action_template": reminder.get("action_template", f"提醒：{reminder.get('title')}") ,
                        "next_trigger_time": timestamp,
                        "time_original": reminder.get("time_original", ""),
                        "timezone": "Asia/Shanghai",
                        "recurrence": rec,
                        "status": "confirmed",
                        "requires_confirmation": False
                    }
                    reminder_dao.create_reminder(reminder_doc)
                    confirmed_reminders.append(reminder)
                    logger.info("创建提醒:" + str(reminder.get("title")) + " at " + str(timestamp))
                elif op == "delete":
                    target = reminder.get("target", {})
                    target_id = target.get("reminder_id")
                    matched = None
                    if target_id:
                        matched = reminder_dao.get_reminder_by_id(target_id)
                    if matched is None:
                        candidates = reminder_dao.find_reminders_by_user(user_id)
                        by_title = target.get("by_title")
                        by_time_hint = target.get("by_time_hint")
                        by_status = target.get("by_status")
                        filtered = []
                        for c in candidates:
                            if by_status and c.get("status") != by_status:
                                continue
                            ok = True
                            if by_title:
                                t = str(c.get("title", ""))
                                if by_title not in t:
                                    ok = False
                            if ok and by_time_hint:
                                hint_ts = str2timestamp(by_time_hint) or parse_relative_time(by_time_hint)
                                if hint_ts:
                                    if abs(int(c.get("next_trigger_time", 0)) - int(hint_ts)) > 1800:
                                        ok = False
                            if ok:
                                filtered.append(c)
                        if len(filtered) == 1:
                            matched = filtered[0]
                        elif len(filtered) > 1:
                            needs_confirmation.append({
                                "confirmation_prompt": reminder.get("confirmation_prompt") or "有多个匹配的提醒，请指明更具体的标题或时间。",
                                "title": reminder.get("title", ""),
                                "time_original": reminder.get("time_original", "")
                            })
                            matched = None
                        else:
                            matched = None
                    if matched is None:
                        needs_confirmation.append({
                            "confirmation_prompt": reminder.get("confirmation_prompt") or "要删除哪个提醒？请补充标题或时间。",
                            "title": reminder.get("title", ""),
                            "time_original": reminder.get("time_original", "")
                        })
                        continue
                    reminder_dao.delete_reminder(matched["reminder_id"])
                    msg = "已删除提醒：" + str(matched.get("title", ""))
                    confirmed_reminders.append(reminder)
                    if self.resp.get("MultiModalResponses"):
                        for response in reversed(self.resp["MultiModalResponses"]):
                            if response.get("type") == "text":
                                response["content"] += "\n\n" + msg
                                break
                elif op == "update":
                    target = reminder.get("target", {})
                    target_id = target.get("reminder_id")
                    matched = None
                    if target_id:
                        matched = reminder_dao.get_reminder_by_id(target_id)
                    if matched is None:
                        candidates = reminder_dao.find_reminders_by_user(user_id)
                        by_title = target.get("by_title")
                        by_time_hint = target.get("by_time_hint")
                        by_status = target.get("by_status")
                        filtered = []
                        for c in candidates:
                            if by_status and c.get("status") != by_status:
                                continue
                            ok = True
                            if by_title:
                                t = str(c.get("title", ""))
                                if by_title not in t:
                                    ok = False
                            if ok and by_time_hint:
                                hint_ts = str2timestamp(by_time_hint) or parse_relative_time(by_time_hint)
                                if hint_ts:
                                    if abs(int(c.get("next_trigger_time", 0)) - int(hint_ts)) > 1800:
                                        ok = False
                            if ok:
                                filtered.append(c)
                        if len(filtered) == 1:
                            matched = filtered[0]
                        elif len(filtered) > 1:
                            needs_confirmation.append({
                                "confirmation_prompt": reminder.get("confirmation_prompt") or "有多个匹配的提醒，请指明更具体的标题或时间。",
                                "title": reminder.get("title", ""),
                                "time_original": reminder.get("time_original", "")
                            })
                            matched = None
                        else:
                            matched = None
                    update_fields = reminder.get("update_fields", {})
                    update_data = {}
                    # 支持标题/文案/周期/状态
                    if "title" in update_fields:
                        update_data["title"] = update_fields.get("title")
                    if "action_template" in update_fields:
                        update_data["action_template"] = update_fields.get("action_template")
                    if "recurrence" in update_fields:
                        update_data["recurrence"] = self._normalize_recurrence(update_fields.get("recurrence", {}))
                    if "status" in update_fields:
                        update_data["status"] = update_fields.get("status")
                    # 时间更新
                    ts_candidate = None
                    if update_fields.get("time_resolved"):
                        ts_candidate = str2timestamp(update_fields.get("time_resolved"))
                    if ts_candidate is None and update_fields.get("time_original"):
                        ts_candidate = parse_relative_time(update_fields.get("time_original")) or str2timestamp(update_fields.get("time_original"))
                    if ts_candidate is not None:
                        if is_time_in_past(ts_candidate):
                                needs_confirmation.append({
                                    "confirmation_prompt": reminder.get("confirmation_prompt") or "新的时间已过期，请确认是否更新。",
                                    "title": matched.get("title", ""),
                                    "time_original": update_fields.get("time_original", "")
                                })
                                continue
                        update_data["next_trigger_time"] = ts_candidate
                    if not update_data:
                        needs_confirmation.append({
                            "confirmation_prompt": reminder.get("confirmation_prompt") or "请说明要更新哪些内容（标题/文案/周期/时间/状态）。",
                            "title": matched.get("title", ""),
                            "time_original": reminder.get("time_original", "")
                        })
                        continue
                    reminder_dao.update_reminder(matched["reminder_id"], update_data)
                    confirmed_reminders.append(reminder)
                    msg = "已更新提醒：" + str(matched.get("title", ""))
                    if self.resp.get("MultiModalResponses"):
                        for response in reversed(self.resp["MultiModalResponses"]):
                            if response.get("type") == "text":
                                response["content"] += "\n\n" + msg
                                break
                elif op == "list":
                    list_filter = reminder.get("list_filter", {})
                    status = list_filter.get("by_status")
                    items = reminder_dao.find_reminders_by_user(user_id, status=status)
                    by_title = list_filter.get("by_title")
                    if by_title:
                        items = [c for c in items if by_title in str(c.get("title", ""))]
                    msg_lines = ["提醒列表："]
                    for c in items[:50]:
                        t = str(c.get("title", ""))
                        st = str(c.get("status", ""))
                        ts = int(c.get("next_trigger_time", 0))
                        from util.time_util import format_time_friendly
                        msg_lines.append(f"- {t} · {st} · {format_time_friendly(ts)}")
                    msg = "\n".join(msg_lines) if len(msg_lines) > 1 else "暂无提醒"
                    if self.resp.get("MultiModalResponses"):
                        for response in reversed(self.resp["MultiModalResponses"]):
                            if response.get("type") == "text":
                                response["content"] += "\n\n" + msg
                                break
                
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
        unit = rec.get("unit")
        time_of_day = rec.get("time_of_day")
        weekdays = rec.get("weekdays")
        month_days = rec.get("month_days")
        norm = {"enabled": enabled}
        if rtype:
            norm["type"] = rtype
        if interval is not None:
            norm["interval"] = interval
        if unit:
            norm["unit"] = unit
        if time_of_day:
            norm["time_of_day"] = time_of_day
        if weekdays:
            norm["weekdays"] = weekdays
        if month_days:
            norm["month_days"] = month_days
        return norm
