# -*- coding: utf-8 -*-
"""
Web Search Tool - 博查搜索工具

使用博查 Search API 实现联网搜索功能，让 Agent 能够获取实时互联网信息。

API 文档: https://open.bochaai.com/
"""

import os
from typing import Optional

import httpx
from agno.tools import tool

from util.log_util import get_logger

logger = get_logger(__name__)

# 配置
BOCHA_API_KEY = os.getenv("BOCHA_API_KEY", "")
BOCHA_BASE_URL = "https://api.bochaai.com/v1/web-search"
DEFAULT_TIMEOUT = 10
DEFAULT_COUNT = 5


@tool(
    description="联网搜索工具，用于搜索互联网上的实时信息。适用于查询新闻、天气、事件、人物等需要最新数据的场景。",
)
def web_search_tool(
    query: str,
    count: int = DEFAULT_COUNT,
    freshness: str = "noLimit",
    session_state: Optional[dict] = None,
) -> dict:
    """
    使用博查 Search API 搜索互联网信息

    Args:
        query: 搜索关键词，支持自然语言
        count: 返回结果数量，1-10，默认5
        freshness: 时间范围过滤
            - "noLimit": 不限时间（默认）
            - "oneDay": 最近一天
            - "oneWeek": 最近一周
            - "oneMonth": 最近一个月
            - "oneYear": 最近一年
        session_state: Agno 框架自动注入的会话状态

    Returns:
        dict: 搜索结果
            - ok: bool, 是否成功
            - results: list, 搜索结果列表（成功时）
                - title: 标题
                - url: 链接
                - snippet: 摘要
                - site_name: 来源网站
            - formatted: str, 格式化的搜索结果文本（成功时）
            - error: str, 错误信息（失败时）
    """
    # 参数校验
    if not query or not query.strip():
        return {"ok": False, "error": "搜索关键词不能为空"}

    if not BOCHA_API_KEY:
        logger.error("BOCHA_API_KEY 未配置")
        return {"ok": False, "error": "搜索服务未配置"}

    # 限制 count 范围
    count = max(1, min(10, count))

    try:
        with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
            response = client.post(
                BOCHA_BASE_URL,
                headers={
                    "Authorization": f"Bearer {BOCHA_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "query": query.strip(),
                    "count": count,
                    "freshness": freshness,
                    "summary": True,
                },
            )

            if response.status_code != 200:
                logger.error(f"博查 API 返回错误: {response.status_code} - {response.text}")
                return {"ok": False, "error": f"搜索服务返回错误: {response.status_code}"}

            data = response.json()

            # 解析搜索结果
            web_pages = data.get("webPages", {}).get("value", [])
            if not web_pages:
                return {
                    "ok": True,
                    "results": [],
                    "formatted": "未找到相关搜索结果。",
                }

            # 格式化结果
            results = []
            formatted_lines = ["【联网搜索结果】"]

            for i, page in enumerate(web_pages, 1):
                result = {
                    "title": page.get("name", ""),
                    "url": page.get("url", ""),
                    "snippet": page.get("snippet", "") or page.get("summary", ""),
                    "site_name": page.get("siteName", ""),
                }
                results.append(result)

                # 格式化为可读文本
                formatted_lines.append(
                    f"{i}. [{result['title']}] - {result['site_name'] or '未知来源'}"
                )
                if result["snippet"]:
                    formatted_lines.append(f"   {result['snippet'][:200]}")
                formatted_lines.append(f"   链接: {result['url']}")
                formatted_lines.append("")

            logger.info(f"博查搜索完成: query='{query}', 结果数={len(results)}")

            return {
                "ok": True,
                "results": results,
                "formatted": "\n".join(formatted_lines),
            }

    except httpx.TimeoutException:
        logger.error(f"博查 API 超时: query='{query}'")
        return {"ok": False, "error": "搜索服务超时，请稍后重试"}
    except Exception as e:
        logger.error(f"博查搜索失败: {e}")
        return {"ok": False, "error": f"搜索失败: {str(e)}"}
