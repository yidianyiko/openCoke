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

from framework.agent.base_agent import AgentStatus
from framework.agent.llmagent.doubao_llmagent import DouBaoLLMAgent
from conf.config import CONF
from volcenginesdkarkruntime import Ark

from dao.mongo import MongoDBBase
from util.embedding_util import upsert_one

from qiaoyun.prompt.system_prompt import *
from qiaoyun.prompt.chat_taskprompt import *
from qiaoyun.prompt.chat_contextprompt import *
from qiaoyun.prompt.chat_noticeprompt import *

doubao_client = Ark(
    base_url="https://ark.cn-beijing.volces.com/api/v3",
)

# 需要 export ARK_API_KEY="xxxx"
class QiaoyunPostAnalyzeAgent(DouBaoLLMAgent):
    default_systemp_template = SYSTEMPROMPT_小说越狱

    default_userp_template = \
    "## 你的任务" + "\n" + \
    TASKPROMPT_小说书写任务 + "\n" + \
    "\n" + \
    TASKPROMPT_总结 + "\n" + \
    TASKPROMPT_总结_推理要求 + "\n" + \
    "\n" + \
    "## 参考上下文" + "\n" + \
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
    CONTEXTPROMPT_最新聊天消息_双方

    default_output_schema = {
        "type": "object",
        "properties": {
            "InnerMonologue": {
                "type": "string",
                "description": "角色的内心独白"
            },
            "CharacterPublicSettings": {
                "type": "string",
                "description": "总结最新聊天消息中，针对角色所新增的人物设定。你可以总结出1条或者多条信息，每条消息为一行；使用'key：value'的形式，例如 xxx-xxx-xxx：xxxxxx。"
            },
            "CharacterPrivateSettings": {
                "type": "string",
                "description": "总结最新聊天消息中，针对角色所新增的不可公开人物设定。你可以总结出1条或者多条信息，每条消息为一行；使用'key：value'的形式，例如 xxx-xxx-xxx：xxxxxx。"
            },
            "CharacterKnowledges": {
                "type": "string",
                "description": "总结最新聊天消息中，角色所新增的知识或技能点。你可以总结出1条或者多条信息，每条消息为一行；使用'key：value'的形式，例如 xxx-xxx-xxx：xxxxxx。"
            },
            "UserSettings": {
                "type": "string",
                "description": "总结最新聊天消息中，针对用户所新增的人物设定。你可以总结出1条或者多条信息，每条消息为一行；使用'key：value'的形式，例如 xxx-xxx-xxx：xxxxxx。"
            },
            "UserRealName": {
                "type": "string",
                "description": "总结最新聊天消息中，角色所了解到的用户的真名。如果没有，你需要输出”无“。"
            },
            "UserHobbyName": {
                "type": "string",
                "description": "总结最新聊天消息中，双方约定的给用户的昵称。如果没有，你需要输出”无“。"
            },
            "UserDescription": {
                "type": "string",
                "description": "总结最新聊天消息中，角色对用户的印象描述。你需要结合”参考上下文“中的印象描述，进行更新。最多不超过100字。"
            },
            "CharacterPurpose": {
                "type": "string",
                "description": "总结最新聊天消息中，角色的短期目标，可能跟多轮聊天有关，也可能无关。"
            },
            "CharacterAttitude": {
                "type": "string",
                "description": "总结最新聊天消息中，角色对用户的态度。"
            },
            "RelationDescription": {
                "type": "string",
                "description": "总结最新聊天消息中，角色和用户的关系变化。如果没有变化，你应该输出原关系。"
            },
            "Dislike": {
                "type": "integer",
                "description": "总结最新聊天消息中，角色对用户的的反感度数值变化。如果更加反感了，应该输出正整数。"
            },
        }
    }

    def __init__(self, context=None, client=doubao_client, systemp_template=default_systemp_template, userp_template=default_userp_template, output_schema=default_output_schema, default_input=None, max_retries=3, name=None, stream=False, model="doubao_1.5_pro", extra_args=None):
        super().__init__(context, client, systemp_template, userp_template, output_schema, default_input, max_retries, name, stream, model, extra_args)

    def _posthandle(self):
        def upsert_vector(kv_str, embedding_type):
            splits = kv_str.split("：")
            if len(splits) < 2:
                return None
            
            key = splits[0]
            value = splits[1]

            char_id = str(self.context["character"]["_id"])

            metadata = {
                "type": embedding_type,
                "cid": char_id,
                "url": None,
                "file": None
            }

            if embedding_type in ["character_private", "user"]:
                metadata["uid"] = str(self.context["user"]["_id"])

            return upsert_one(key, value, metadata)
        
        cps = self.resp.get("CharacterPublicSettings", "无")
        if cps and cps != "无":
            splits = cps.split("<换行>")
            for split in splits:
                upsert_vector(split, "character_global")

        cprs = self.resp.get("CharacterPrivateSettings", "无")
        if cprs and cprs != "无":
            splits = cprs.split("<换行>")
            for split in splits:
                upsert_vector(split, "character_private")

        cks = self.resp.get("CharacterKnowledges", "无")
        if cks and cks != "无":
            splits = cks.split("<换行>")
            for split in splits:
                upsert_vector(split, "chatacter_knowledge")

        us = self.resp.get("UserSettings", "无")
        if us and us != "无":
            splits = us.split("<换行>")
            for split in splits:
                upsert_vector(split, "user")

        urn = self.resp.get("UserRealName", "无")
        if urn and urn != "无":
            self.context["relation"]["user_info"]["realname"] = urn

        uhn = self.resp.get("UserHobbyName", "无")
        if uhn and uhn != "无":
            self.context["relation"]["user_info"]["hobbyname"] = uhn

        ud = self.resp.get("UserDescription", "无")
        if ud and ud != "无":
            self.context["relation"]["user_info"]["description"] = ud

        cp = self.resp.get("CharacterPurpose", "无")
        if cp and cp != "无":
            self.context["relation"]["character_info"]["shortterm_purpose"] = cp

        ca = self.resp.get("CharacterAttitude", "无")
        if ca and ca != "无":
            self.context["relation"]["character_info"]["attitude"] = ca

        rd = self.resp.get("RelationDescription", "无")
        if rd and rd != "无":
            self.context["relation"]["relationship"]["description"] = rd

        dislike_raw = self.resp.get("Dislike", None)
        try:
            dislike_delta = int(dislike_raw) if dislike_raw is not None else None
        except (ValueError, TypeError):
            dislike_delta = None

        if dislike_delta is not None:
            if dislike_delta >= 0:
                self.context["relation"]["relationship"]["dislike"] = self.context["relation"]["relationship"]["dislike"] + dislike_delta - 5
            else:
                self.context["relation"]["relationship"]["dislike"] = self.context["relation"]["relationship"]["dislike"] + dislike_delta
            if self.context["relation"]["relationship"]["dislike"] < 0:
                self.context["relation"]["relationship"]["dislike"] = 0
            if self.context["relation"]["relationship"]["dislike"] > 100:
                self.context["relation"]["relationship"]["dislike"] = 100