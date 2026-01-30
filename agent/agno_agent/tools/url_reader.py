# -*- coding: utf-8 -*-
"""
URL Reader - 链接内容读取工具

使用 Jina Reader API 从 URL 提取 LLM 友好的 Markdown 内容。
Jina Reader: https://r.jina.ai/{url}
"""

import re
from dataclasses import dataclass
from typing import List, Optional

import httpx

from conf.config import CONF
from util.log_util import get_logger

logger = get_logger(__name__)

# URL 检测正则
URL_PATTERN = re.compile(r"https?://[^\s<>\"{}|\\^`\[\]]+")

# Jina Reader API
JINA_READER_BASE = "https://r.jina.ai/"

# 默认配置
DEFAULT_TIMEOUT = 15.0
DEFAULT_MAX_URLS = 3
DEFAULT_MAX_CONTENT_LENGTH = 2000


@dataclass
class UrlContent:
    """URL 内容数据类"""

    url: str
    title: Optional[str] = None
    content: str = ""
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "title": self.title,
            "content": self.content,
            "error": self.error,
        }


def extract_urls(text: str) -> List[str]:
    """
    从文本中提取 URL

    Args:
        text: 输入文本

    Returns:
        URL 列表（去重）
    """
    urls = URL_PATTERN.findall(text)
    # 去重并保持顺序
    seen = set()
    unique_urls = []
    for url in urls:
        # 清理 URL 末尾的标点符号
        url = url.rstrip(".,;:!?\"'")
        if url not in seen:
            seen.add(url)
            unique_urls.append(url)
    return unique_urls


def _extract_title_from_markdown(content: str) -> Optional[str]:
    """
    从 Jina Reader 返回的 Markdown 中提取标题

    Jina Reader 返回格式通常是:
    Title: xxx

    或者第一行是 # 标题

    Args:
        content: Markdown 内容

    Returns:
        标题或 None
    """
    lines = content.strip().split("\n")
    if not lines:
        return None

    first_line = lines[0].strip()

    # 检查 "Title: xxx" 格式
    if first_line.startswith("Title:"):
        return first_line[6:].strip()

    # 检查 "# xxx" 格式
    if first_line.startswith("# "):
        return first_line[2:].strip()

    return None


def fetch_url_content(
    url: str,
    timeout: float = DEFAULT_TIMEOUT,
    max_length: int = DEFAULT_MAX_CONTENT_LENGTH,
) -> UrlContent:
    """
    使用 Jina Reader 获取 URL 内容

    Jina Reader 返回干净的 Markdown 格式，非常适合 LLM 理解。

    Args:
        url: 目标 URL
        timeout: 请求超时时间（秒）
        max_length: 最大内容长度

    Returns:
        UrlContent 对象
    """
    jina_url = f"{JINA_READER_BASE}{url}"

    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.get(jina_url)
            response.raise_for_status()

            content = response.text.strip()
            title = _extract_title_from_markdown(content)

            # 截断过长内容
            if len(content) > max_length:
                content = content[:max_length] + "\n\n[内容已截断...]"

            return UrlContent(url=url, title=title, content=content)

    except httpx.TimeoutException:
        logger.warning(f"[URLReader] Timeout fetching {url} via Jina Reader")
        return UrlContent(url=url, error="Request timeout")
    except httpx.HTTPStatusError as e:
        logger.warning(
            f"[URLReader] HTTP error {e.response.status_code} for {url} via Jina Reader"
        )
        return UrlContent(url=url, error=f"HTTP {e.response.status_code}")
    except Exception as e:
        logger.warning(f"[URLReader] Error fetching {url} via Jina Reader: {e}")
        return UrlContent(url=url, error=str(e))


def extract_urls_content(
    message: str,
    max_urls: int = None,
    max_content_length: int = None,
) -> List[UrlContent]:
    """
    从消息中提取 URL 并获取内容

    Args:
        message: 用户消息
        max_urls: 最大处理 URL 数量
        max_content_length: 最大内容长度

    Returns:
        UrlContent 列表
    """
    # 获取配置
    config = CONF.get("features", {}).get("link_understanding", {})
    if not config.get("enabled", True):
        return []

    max_urls = max_urls or config.get("max_urls", DEFAULT_MAX_URLS)
    max_content_length = max_content_length or config.get(
        "max_content_length", DEFAULT_MAX_CONTENT_LENGTH
    )

    urls = extract_urls(message)
    if not urls:
        return []

    logger.info(f"[URLReader] Found {len(urls)} URLs, processing up to {max_urls}")

    results = []
    for url in urls[:max_urls]:
        result = fetch_url_content(url, max_length=max_content_length)
        if result.content or result.error:
            results.append(result)
            if result.content:
                logger.info(f"[URLReader] Fetched {url}: {len(result.content)} chars")

    return results


def format_url_context(url_contents: List[UrlContent]) -> str:
    """
    将 URL 内容格式化为上下文字符串

    Args:
        url_contents: UrlContent 列表

    Returns:
        格式化的上下文字符串
    """
    if not url_contents:
        return ""

    lines = ["### 链接内容"]
    for uc in url_contents:
        if uc.error:
            lines.append(f"[链接: {uc.url}]\n（无法获取: {uc.error}）")
        else:
            title_str = f"标题: {uc.title}\n" if uc.title else ""
            lines.append(f"[链接: {uc.url}]\n{title_str}{uc.content}")

    return "\n\n".join(lines)
