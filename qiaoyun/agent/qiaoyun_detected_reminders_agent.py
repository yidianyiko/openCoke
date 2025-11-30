# -*- coding: utf-8 -*-
import sys
sys.path.append(".")

import re
import traceback
import logging
from logging import getLogger
logging.basicConfig(level=logging.INFO)
logger = getLogger(__name__)

from framework.agent.base_agent import BaseAgent, AgentStatus
from dao.reminder_dao import ReminderDAO
from util.time_util import str2timestamp, parse_relative_time, is_time_in_past, format_time_friendly
from framework.agent.llmagent.doubao_llmagent import DouBaoLLMAgent
from volcenginesdkarkruntime import Ark
from qiaoyun.prompt.chat_taskprompt import TASKPROMPT_提醒识别
from qiaoyun.prompt.chat_contextprompt import CONTEXTPROMPT_时间


class DetectedRemindersAgent(BaseAgent):
    def __init__(self, context=None, max_retries=2, name=None):
        super().__init__(context=context, max_retries=max_retries, name=name)

    def _prehandle(self):
        if "reminders" not in self.context:
            self.context["reminders"] = {
                "detected": [],
                "executed": [],
                "ui_messages": [],
                "needs_confirmation": []
            }

    def _execute(self):
        try:
            conv = self.context.get("conversation", {}).get("conversation_info", {})
            messages_str = str(conv.get("input_messages_str", ""))
            user_id = str(self.context.get("user", {}).get("_id", ""))
            conversation_id = str(self.context.get("conversation", {}).get("_id", ""))
            character_id = str(self.context.get("character", {}).get("_id", ""))

            last_msg = self._extract_last_message_content(messages_str)
            logger.info(f"[DetectedRemindersAgent] last_msg={last_msg}")
            if not last_msg:
                yield {"ok": True, "note": "no_input"}
                return

            lowered = last_msg.lower()
            delete_hit = self._has_any(last_msg, ["取消", "删除", "不提醒", "忽略"]) or self._has_any(lowered, ["cancel"]) 
            logger.info(f"[DetectedRemindersAgent] delete_hit={delete_hit}")
            update_hit = self._has_any(last_msg, ["修改", "变更", "调整", "改到", "改成"]) or self._has_any(lowered, ["update"]) 
            list_hit = self._has_any(last_msg, ["查看提醒", "列出提醒", "有哪些提醒", "看看提醒"]) or self._has_any(lowered, ["list reminders"]) 

            reminder_dao = ReminderDAO()
            if delete_hit:
                detected_obj = {"operation": "delete"}
                title = self._guess_title_from_message(last_msg, reminder_dao, user_id)
                logger.info(f"[DetectedRemindersAgent] detected delete intent, title_guess={title}")
                if title:
                    detected_obj["target"] = {"by_title": title, "by_status": "confirmed"}
                else:
                    detected_obj["requires_confirmation"] = True
                    detected_obj["confirmation_prompt"] = "要删除哪个提醒？请补充标题中的关键字。"
                pass

                if title:
                    # 解析唯一目标
                    candidates = reminder_dao.find_reminders_by_user(user_id, status="confirmed")
                    matched = [c for c in candidates if title.lower() in str(c.get("title", "")).lower()]
                    logger.info(f"[DetectedRemindersAgent] candidates={len(candidates)} matched={len(matched)} title={title}")
                    if len(matched) == 1:
                        rid = matched[0].get("reminder_id")
                        ok = reminder_dao.delete_reminder(rid)
                        if ok:
                            logger.info(f"[DetectedRemindersAgent] 删除提醒成功: title={matched[0].get('title')} rid={rid}")
                        else:
                            logger.warning(f"[DetectedRemindersAgent] 删除提醒失败或不存在: title={matched[0].get('title')} rid={rid}")
                        self.context["reminders"]["executed"].append({
                            "operation": "delete",
                            "target": {"by_title": title},
                            "resolved_target": {"reminder_id": rid, "title": matched[0].get("title")},
                            "ok": ok,
                            "effect": "deleted" if ok else "not_found_or_failed"
                        })
                        msg = ("已删除提醒：" + str(matched[0].get("title", ""))) if ok else ("未找到或删除失败：" + str(matched[0].get("title", "")))
                        self.context["reminders"]["ui_messages"].append(msg)
                    elif len(matched) > 1:
                        logger.info("[DetectedRemindersAgent] 多个匹配，需要确认")
                        self.context["reminders"]["needs_confirmation"].append("有多个匹配的提醒，请指明更具体的标题或时间。")
                    else:
                        logger.info("[DetectedRemindersAgent] 未匹配到任何提醒，需要确认")
                        self.context["reminders"]["needs_confirmation"].append("要删除哪个提醒？未匹配到任何提醒，请补充标题中的关键字。")
                else:
                    # 没有标题，直接进入确认
                    logger.info("[DetectedRemindersAgent] 未识别到标题，需要确认")
                    self.context["reminders"]["needs_confirmation"].append("要删除哪个提醒？请补充标题中的关键字。")

            

            if update_hit:
                target_title = self._guess_title_from_message(last_msg, reminder_dao, user_id) or self._guess_title_from_patterns(last_msg)
                candidates = reminder_dao.find_reminders_by_user(user_id)
                matched = [c for c in candidates if target_title and target_title.lower() in str(c.get("title", "")).lower()]
                if len(matched) == 1:
                    update_fields = {}
                    ts2, time_original2, rec2 = self._parse_time_and_recurrence(last_msg)
                    if ts2 is not None:
                        if is_time_in_past(ts2):
                            self.context["reminders"]["needs_confirmation"].append("新的时间已过期，请确认是否更新。")
                        else:
                            update_fields["next_trigger_time"] = ts2
                    if rec2:
                        update_fields["recurrence"] = self._normalize_recurrence(rec2)
                    if not update_fields:
                        self.context["reminders"]["needs_confirmation"].append("请说明要更新哪些内容（标题/文案/周期/时间/状态）。")
                    else:
                        ok2 = reminder_dao.update_reminder(matched[0]["reminder_id"], update_fields)
                        self.context["reminders"]["executed"].append({
                            "operation": "update",
                            "target": {"by_title": target_title},
                            "resolved_target": {"reminder_id": matched[0]["reminder_id"], "title": matched[0].get("title")},
                            "ok": ok2,
                            "effect": "updated" if ok2 else "failed"
                        })
                        if ok2:
                            self.context["reminders"]["ui_messages"].append("已更新提醒：" + str(matched[0].get("title", "")))
                        else:
                            self.context["reminders"]["ui_messages"].append("更新失败：" + str(matched[0].get("title", "")))
                elif len(matched) > 1:
                    self.context["reminders"]["needs_confirmation"].append("有多个匹配的提醒，请指明更具体的标题或时间。")
                else:
                    self.context["reminders"]["needs_confirmation"].append("要更新哪个提醒？请补充标题或时间。")

            if list_hit:
                items = reminder_dao.find_reminders_by_user(user_id)
                lines = ["提醒列表："]
                for c in items[:50]:
                    t = str(c.get("title", ""))
                    st = str(c.get("status", ""))
                    ts3 = int(c.get("next_trigger_time", 0))
                    lines.append("- " + t + " · " + st + " · " + format_time_friendly(ts3))
                msg3 = "\n".join(lines) if len(lines) > 1 else "暂无提醒"
                self.context["reminders"]["ui_messages"].append(msg3)

            # 始终运行 LLM 检测并统一处理
            llm_results = self._llm_detect()
            if isinstance(llm_results, list) and llm_results:
                self.context["reminders"]["detected"].extend(llm_results)
            self._handle_reminders()

            reminder_dao.close()
            yield {"ok": True}
        except Exception:
            logger.error(f"DetectedRemindersAgent failed: {traceback.format_exc()}")
            yield {"ok": False}

    def _posthandle(self):
        pass

    def _llm_detect(self):
        try:
            client = Ark(base_url="https://ark.cn-beijing.volces.com/api/v3")
            # 仅提取 DetectedReminders 字段
            schema = {
                "type": "object",
                "properties": {
                    "DetectedReminders": {
                        "type": "array",
                        "items": {"type": "object", "additionalProperties": True}
                    }
                },
                "required": ["DetectedReminders"]
            }
            systemp = ""
            userp = (
                "## 你的任务\n" + TASKPROMPT_提醒识别 + "\n\n" +
                "## 上下文\n" + CONTEXTPROMPT_时间 + "\n\n" +
                "### 最新聊天消息\n" + "{conversation[conversation_info][input_messages_str]}"
            )
            agent = DouBaoLLMAgent(
                context=self.context,
                client=client,
                systemp_template=systemp,
                userp_template=userp,
                output_schema=schema,
                model="deepseek-v3-250324"
            )
            results = agent.run()
            llm_resp = None
            for r in results:
                if r.get("status") == "finished":
                    llm_resp = r.get("resp")
            if isinstance(llm_resp, dict):
                return llm_resp.get("DetectedReminders", [])
            return []
        except Exception:
            return []

    def _handle_reminders(self):
        import uuid
        reminders = self.context.get("reminders", {}).get("detected", [])
        if not reminders:
            return
        reminder_dao = ReminderDAO()
        conversation_id = str(self.context.get("conversation", {}).get("_id", ""))
        user_id = str(self.context.get("user", {}).get("_id", ""))
        character_id = str(self.context.get("character", {}).get("_id", ""))
        needs_confirmation = []
        for reminder in reminders:
            try:
                op = reminder.get("operation", "create")
                if op == "create":
                    timestamp = self._parse_reminder_time(reminder)
                    if reminder.get("requires_confirmation") or timestamp is None or is_time_in_past(timestamp):
                        needs_confirmation.append(reminder.get("confirmation_prompt") or "时间不明确或已过期，是否继续创建？")
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
                    rid = reminder_dao.create_reminder(reminder_doc)
                    if rid:
                        logger.info("创建提醒成功:" + str(reminder.get("title")) + " id=" + str(rid) + " at " + str(timestamp))
                        self.context["reminders"]["executed"].append({
                            "operation": "create",
                            "target": {"by_title": reminder_doc["title"]},
                            "resolved_target": {"reminder_id": rid, "title": reminder_doc["title"]},
                            "ok": True,
                            "effect": "created"
                        })
                        from util.time_util import format_time_friendly
                        self.context["reminders"]["ui_messages"].append("已创建提醒：" + reminder_doc["title"] + " · " + format_time_friendly(timestamp))
                    else:
                        logger.warning("创建提醒失败:" + str(reminder.get("title")) + " at " + str(timestamp))
                        self.context["reminders"]["ui_messages"].append("创建提醒失败：" + str(reminder.get("title", "提醒")))
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
                        by_status = target.get("by_status") or "confirmed"
                        filtered = []
                        by_title_lower = str(by_title).lower() if by_title else None
                        for c in candidates:
                            if by_status and c.get("status") != by_status:
                                continue
                            ok = True
                            if by_title_lower is not None:
                                t = str(c.get("title", ""))
                                if by_title_lower not in t.lower():
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
                            needs_confirmation.append(reminder.get("confirmation_prompt") or "有多个匹配的提醒，请指明更具体的标题或时间。")
                            matched = None
                        else:
                            matched = None
                    if matched is None:
                        needs_confirmation.append(reminder.get("confirmation_prompt") or "要删除哪个提醒？请补充标题中的关键字。")
                        continue
                    ok = reminder_dao.delete_reminder(matched["reminder_id"])
                    self.context["reminders"]["executed"].append({
                        "operation": "delete",
                        "target": {"by_title": reminder.get("title", "")},
                        "resolved_target": {"reminder_id": matched["reminder_id"], "title": matched.get("title")},
                        "ok": ok,
                        "effect": "deleted" if ok else "not_found_or_failed"
                    })
                    if ok:
                        logger.info("删除提醒成功:" + str(matched.get("title", "")))
                        msg = "已删除提醒：" + str(matched.get("title", ""))
                    else:
                        logger.warning("删除提醒失败或不存在:" + str(matched.get("title", "")))
                        msg = "未找到或删除失败：" + str(matched.get("title", ""))
                    self.context["reminders"]["ui_messages"].append(msg)
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
                        by_status = target.get("by_status") or "confirmed"
                        filtered = []
                        by_title_lower = str(by_title).lower() if by_title else None
                        for c in candidates:
                            if by_status and c.get("status") != by_status:
                                continue
                            ok = True
                            if by_title_lower is not None:
                                t = str(c.get("title", ""))
                                if by_title_lower not in t.lower():
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
                            needs_confirmation.append(reminder.get("confirmation_prompt") or "有多个匹配的提醒，请指明更具体的标题或时间。")
                            matched = None
                        else:
                            matched = None
                    if matched is None:
                        needs_confirmation.append(reminder.get("confirmation_prompt") or "要更新哪个提醒？请补充标题或时间。")
                        continue
                    update_fields = reminder.get("update_fields", {})
                    update_data = {}
                    if "title" in update_fields:
                        update_data["title"] = update_fields.get("title")
                    if "action_template" in update_fields:
                        update_data["action_template"] = update_fields.get("action_template")
                    if "recurrence" in update_fields:
                        update_data["recurrence"] = self._normalize_recurrence(update_fields.get("recurrence", {}))
                    if "status" in update_fields:
                        update_data["status"] = update_fields.get("status")
                    ts_candidate = None
                    if update_fields.get("time_resolved"):
                        ts_candidate = str2timestamp(update_fields.get("time_resolved"))
                    if ts_candidate is None and update_fields.get("time_original"):
                        ts_candidate = parse_relative_time(update_fields.get("time_original")) or str2timestamp(update_fields.get("time_original"))
                    if ts_candidate is not None:
                        if is_time_in_past(ts_candidate):
                            needs_confirmation.append(reminder.get("confirmation_prompt") or "新的时间已过期，请确认是否更新。")
                            continue
                        update_data["next_trigger_time"] = ts_candidate
                    if not update_data:
                        needs_confirmation.append(reminder.get("confirmation_prompt") or "请说明要更新哪些内容（标题/文案/周期/时间/状态）。")
                        continue
                    ok = reminder_dao.update_reminder(matched["reminder_id"], update_data)
                    self.context["reminders"]["executed"].append({
                        "operation": "update",
                        "target": {"by_title": reminder.get("title", "")},
                        "resolved_target": {"reminder_id": matched["reminder_id"], "title": matched.get("title")},
                        "ok": ok,
                        "effect": "updated" if ok else "failed"
                    })
                    msg = "已更新提醒：" + str(matched.get("title", "")) if ok else "更新失败：" + str(matched.get("title", ""))
                    self.context["reminders"]["ui_messages"].append(msg)
                elif op == "list":
                    list_filter = reminder.get("list_filter", {})
                    status = list_filter.get("by_status")
                    items = reminder_dao.find_reminders_by_user(user_id, status=status)
                    by_title = list_filter.get("by_title")
                    if by_title:
                        by_title_lower = str(by_title).lower()
                        items = [c for c in items if by_title_lower in str(c.get("title", "")).lower()]
                    logger.info("提醒列表查询: count=" + str(len(items)) + " status=" + str(status or "all") + (" title_like=" + by_title if by_title else ""))
                    msg_lines = ["提醒列表："]
                    for c in items[:50]:
                        t = str(c.get("title", ""))
                        st = str(c.get("status", ""))
                        ts = int(c.get("next_trigger_time", 0))
                        from util.time_util import format_time_friendly
                        msg_lines.append(f"- {t} · {st} · {format_time_friendly(ts)}")
                    msg = "\n".join(msg_lines) if len(msg_lines) > 1 else "暂无提醒"
                    self.context["reminders"]["ui_messages"].append(msg)
            except Exception as e:
                logger.error(f"处理提醒失败: {traceback.format_exc()}")
        if needs_confirmation:
            for r in needs_confirmation:
                self.context["reminders"]["needs_confirmation"].append(str(r))
        reminder_dao.close()

    def _parse_reminder_time(self, reminder):
        if reminder.get("time_resolved"):
            timestamp = str2timestamp(reminder["time_resolved"])
            if timestamp:
                return timestamp
        time_original = reminder.get("time_original", "")
        timestamp = parse_relative_time(time_original)
        if timestamp:
            return timestamp
        timestamp = str2timestamp(time_original)
        if timestamp:
            return timestamp
        return None

    def _has_any(self, text: str, keywords):
        return any(k in text for k in keywords)

    def _extract_last_message_content(self, messages_str: str) -> str:
        lines = [l for l in str(messages_str).splitlines() if l.strip()]
        if not lines:
            return ""
        last = lines[-1]
        # 格式可能为：（时间 角色 发来了文本消息）内容
        # 提取右括号后的内容
        m = re.search(r"\)\s*(.*)$", last)
        return (m.group(1).strip() if m else last.strip())

    def _guess_title_from_message(self, message: str, reminder_dao: ReminderDAO, user_id: str) -> str:
        # 从用户当前提醒中做模糊匹配，选择最佳候选
        candidates = reminder_dao.find_reminders_by_user(user_id)
        if not candidates:
            return ""
        message_lower = message.lower()
        # 优先用中文标题匹配
        ranked = []
        for c in candidates:
            t = str(c.get("title", ""))
            if not t:
                continue
            tl = t.lower()
            if (t in message) or (tl in message_lower):
                ranked.append((len(t), t))
        # 选择最长匹配（更具体）
        if ranked:
            ranked.sort(reverse=True)
            return ranked[0][1]
        # 兜底：如果消息中包含“提醒”且只有一个候选，返回该候选标题
        if "提醒" in message and len(candidates) == 1:
            return str(candidates[0].get("title", ""))
        return ""

    def _guess_title_from_patterns(self, message: str) -> str:
        patterns = ["喝水", "拉伸", "晒太阳", "跑步", "出门", "吃午饭", "午饭", "散步", "洗澡", "跳舞"]
        for p in patterns:
            if p in message:
                return p
        m = re.search(r"提醒我(.*)$", message)
        if m:
            return m.group(1).strip()
        return ""

    def _parse_time_and_recurrence(self, message: str):
        ts = parse_relative_time(message) or str2timestamp(message)
        time_original = None
        rec = None
        m_min = re.search(r"每(\d+)分钟", message)
        if m_min:
            try:
                iv = int(m_min.group(1))
                rec = {"enabled": True, "type": "minute", "interval": iv}
            except:
                pass
        if "每天" in message and rec is None:
            rec = {"enabled": True, "type": "daily", "interval": 1}
        m_hm = re.search(r"(\d{1,2})[:：](\d{2})", message)
        if m_hm:
            try:
                from datetime import datetime, timedelta
                now = datetime.now()
                hh = int(m_hm.group(1))
                mm = int(m_hm.group(2))
                cand = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
                if cand.timestamp() <= now.timestamp():
                    cand = cand + timedelta(days=1)
                ts = int(cand.timestamp())
                time_original = f"{cand.year}年{cand.month:02d}月{cand.day:02d}日{hh}时{mm}分"
            except:
                pass
        if ts and not time_original:
            time_original = message
        return ts, time_original, rec

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
