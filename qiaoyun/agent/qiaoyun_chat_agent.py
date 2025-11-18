# -*- coding: utf-8 -*-
import os
import time

import sys
sys.path.append(".")
import random
import json
import traceback
import logging
from logging import getLogger
logging.basicConfig(level=logging.INFO)
logger = getLogger(__name__)

from framework.agent.base_agent import AgentStatus, BaseAgent
from conf.config import CONF
from volcenginesdkarkruntime import Ark

from qiaoyun.agent.qiaoyun_query_rewrite_agent import QiaoyunQueryRewriteAgent
from qiaoyun.agent.qiaoyun_context_retrieve_agent import QiaoyunContextRetrieveAgent
from qiaoyun.agent.qiaoyun_chat_response_agent import QiaoyunChatResponseAgent
from qiaoyun.agent.qiaoyun_post_analyze_agent import QiaoyunPostAnalyzeAgent
from qiaoyun.agent.qiaoyun_chat_response_refine_agent import QiaoyunChatResponseRefineAgent

# 触发r1做优化的概率
default_refine_chance = 0.12
refine_chance = 0.5

class QiaoyunChatAgent(BaseAgent):
    def __init__(self, context = None, max_retries = 3, name = None):
        super().__init__(context, max_retries, name)
    
    def _normalize_mm(self, mm):
        if not isinstance(mm, list) or len(mm) == 0:
            return [{"type": "text", "content": "我现在网有点卡，晚点回你哈"}]
        normalized = []
        for item in mm:
            if isinstance(item, dict):
                content = str(item.get("content", ""))
            else:
                content = str(item)
            normalized.append({"type": "text", "content": content})
        return normalized
    
    def _execute(self):
        # 清零
        self.context["conversation"]["conversation_info"]["future"]["proactive_times"] = 0
        
        # 问题重写
        c = QiaoyunQueryRewriteAgent(self.context)
        results = c.run()
        for result in results:
            if result["status"] != AgentStatus.FINISHED.value:
                continue
            self.context["query_rewrite"] = result["resp"]
        
        # 上下文拉取
        c = QiaoyunContextRetrieveAgent(self.context)
        results = c.run()
        for result in results:
            if result["status"] != AgentStatus.FINISHED.value:
                continue
            self.context["context_retrieve"] = result["resp"]

        # 回复生成
        c = QiaoyunChatResponseAgent(self.context)
        results = c.run()
        for result in results:
            if result["status"] != AgentStatus.FINISHED.value:
                continue
            logger.info(result["resp"])
            self.resp = result["resp"] if result["resp"] else {}
            mm = self.resp.get("MultiModalResponses")
            mm = self._normalize_mm(mm)
            self.resp["MultiModalResponses"] = mm
            self.context["MultiModalResponses"] = mm
        
        # 如果涉及到可扩展内容，有概率调用细化链路
        is_refine = False
        if random.random() < default_refine_chance:
            is_refine = True
        if 'ChatCatelogue' in self.resp:
            if self.resp["ChatCatelogue"] == "是" and random.random() < refine_chance:
                is_refine = True
        
        if is_refine and isinstance(self.resp, dict):
            logger.info("refining with r1...")
            c = QiaoyunChatResponseRefineAgent(self.context)
            results = c.run()
            for result in results:
                if result["status"] != AgentStatus.FINISHED.value:
                    continue
                logger.info(result["resp"])
                refine_mm = result["resp"] if isinstance(result["resp"], list) else None
                if not refine_mm:
                    refine_mm = [{"type": "text", "content": "我现在网有点卡，晚点回你哈"}]
                refine_mm = self._normalize_mm(refine_mm)
                self.resp["MultiModalResponses"] = refine_mm
                self.context["MultiModalResponses"] = refine_mm
        
        self.status = AgentStatus.MESSAGE
        yield self.resp
        self.status = AgentStatus.RUNNING

        c = QiaoyunPostAnalyzeAgent(self.context)
        results = c.run()
        for result in results:
            if result["status"] != AgentStatus.FINISHED.value:
                continue
            logger.info(result["resp"])



        

        