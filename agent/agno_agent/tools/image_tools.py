# -*- coding: utf-8 -*-
"""
Image Tools for Agno Agent

This module provides image processing capabilities:
- image2text_tool: 图片识别 (豆包视觉模型)
- image_send_tool: 发送图片消息
- image_generate_tool: 文生图 (LibLib API)

Requirements: FR-006, FR-007, FR-045, FR-046
"""

import logging
from typing import Optional, Literal
from agno.tools import tool

logger = logging.getLogger(__name__)


@tool(description="识别图片内容，返回图片描述")
def image2text_tool(
    prompt: str = "请详细描述图片中有什么",
    image_url: Optional[str] = None,
    image_path: Optional[str] = None,
    image_format: str = "png"
) -> dict:
    """
    图片识别工具
    
    使用豆包视觉模型识别图片内容，返回图片描述.
    
    Args:
        prompt: 提示词，告诉模型如何描述图片
        image_url: 图片URL（与 image_path 二选一）
        image_path: 本地图片路径（与 image_url 二选一）
        image_format: 图片格式，默认 png
    
    Returns:
        dict: {
            "ok": bool,  # 是否成功
            "description": str,  # 图片描述
            "error": str  # 错误信息（如果失败）
        }
    """
    try:
        from framework.tool.image2text.ark import ark_image2text
        
        if not image_url and not image_path:
            return {
                "ok": False,
                "description": "",
                "error": "必须提供 image_url 或 image_path"
            }
        
        result = ark_image2text(
            prompt=prompt,
            image_url=image_url,
            image_path=image_path,
            image_format=image_format
        )
        
        if result:
            return {
                "ok": True,
                "description": result
            }
        else:
            return {
                "ok": False,
                "description": "",
                "error": "图片识别失败"
            }
    except Exception as e:
        logger.error(f"image2text_tool error: {e}")
        return {
            "ok": False,
            "description": "",
            "error": str(e)
        }


@tool(description="上传照片并获取可发送的URL")
def image_send_tool(photo_id: str) -> dict:
    """
    图片发送工具
    
    根据照片ID从数据库获取照片，上传到 OSS 并返回签名URL.
    
    Args:
        photo_id: 照片ID（embeddings 表中的 _id）
    
    Returns:
        dict: {
            "ok": bool,  # 是否成功
            "url": str,  # 图片的签名URL
            "error": str  # 错误信息（如果失败）
        }
    """
    try:
        from agent.tool.image import upload_image
        
        url = upload_image(photo_id)
        
        if url:
            return {
                "ok": True,
                "url": url
            }
        else:
            return {
                "ok": False,
                "url": "",
                "error": f"找不到照片或上传失败: {photo_id}"
            }
    except Exception as e:
        logger.error(f"image_send_tool error: {e}")
        return {
            "ok": False,
            "url": "",
            "error": str(e)
        }


@tool(description="根据描述生成角色照片")
def image_generate_tool(
    prompt: str,
    img_count: int = 1,
    sub_mode: Literal["半身照", "全身照"] = "半身照",
    width: int = 768,
    height: int = 1024
) -> dict:
    """
    文生图工具
    
    使用 LibLib API 根据描述生成角色照片.
    
    Args:
        prompt: 图片描述/提示词
        img_count: 生成数量，默认1张
        sub_mode: 照片类型
            - "半身照": 上半身照片（默认）
            - "全身照": 全身照片
        width: 图片宽度，默认768
        height: 图片高度，默认1024
    
    Returns:
        dict: {
            "ok": bool,  # 是否成功
            "images": list,  # 生成的图片路径列表
            "origin_urls": list,  # 原始图片URL列表
            "error": str  # 错误信息（如果失败）
        }
    """
    try:
        from agent.tool.image import generate_character_image, generate_character_image_save
        
        # 生成图片任务
        task_id = generate_character_image(
            prompt=prompt,
            imgCount=img_count,
            mode=0,  # 人物照模式
            sub_mode=sub_mode,
            resizedWidth=width,
            resizedHeight=height
        )
        
        if not task_id:
            return {
                "ok": False,
                "images": [],
                "origin_urls": [],
                "error": "创建图片生成任务失败"
            }
        
        # 等待并获取结果
        origin_paths, saved_paths = generate_character_image_save(task_id)
        
        if saved_paths:
            return {
                "ok": True,
                "images": saved_paths,
                "origin_urls": origin_paths or []
            }
        else:
            return {
                "ok": False,
                "images": [],
                "origin_urls": [],
                "error": "图片生成超时或失败"
            }
    except Exception as e:
        logger.error(f"image_generate_tool error: {e}")
        return {
            "ok": False,
            "images": [],
            "origin_urls": [],
            "error": str(e)
        }


__all__ = [
    "image2text_tool",
    "image_send_tool",
    "image_generate_tool",
]
