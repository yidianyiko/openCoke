# -*- coding: utf-8 -*-
"""
Album and Moments Tools for Agno Agent

This module provides album and moments management capabilities:
- moments_tool: 发布朋友圈
- photo_delete_tool: 删除照片

Requirements: FR-063, FR-064
"""

import logging
from typing import Optional

from agno.tools import tool

from conf.config import CONF
from dao.mongo import MongoDBBase

logger = logging.getLogger(__name__)


@tool(description="发布照片到微信朋友圈")
def moments_tool(photo_id: str, content: Optional[str] = None) -> dict:
    """
    朋友圈发布工具

    将指定照片发布到微信朋友圈，可以使用照片自带的文案或自定义文案.

    Args:
        photo_id: 照片ID（embeddings 表中的 _id）
        content: 朋友圈文案（可选，不提供则使用照片自带的 pyqpost）

    Returns:
        dict: {
            "ok": bool,  # 是否成功
            "message": str,  # 结果消息
            "error": str  # 错误信息（如果失败）
        }
    """
    try:
        from agent.tool.image import upload_image
        from connector.ecloud.ecloud_api import Ecloud_API

        mongo = MongoDBBase()

        # 获取照片信息
        photo = mongo.get_vector_by_id("embeddings", photo_id)
        if photo is None:
            return {"ok": False, "message": "", "error": f"找不到照片: {photo_id}"}

        # 获取朋友圈文案
        pyq_post = content
        if not pyq_post:
            pyq_post = photo.get("metadata", {}).get("pyqpost", "")

        if not pyq_post:
            return {
                "ok": False,
                "message": "",
                "error": "照片没有朋友圈文案，请提供 content 参数",
            }

        # 上传图片获取URL
        image_url = upload_image(photo_id)
        if not image_url:
            return {"ok": False, "message": "", "error": "图片上传失败"}

        # 发布朋友圈
        target_user_alias = CONF.get("default_character_alias", "default")
        data = {
            "wId": CONF["ecloud"]["wId"][target_user_alias],
            "content": pyq_post,
            "paths": image_url,
        }

        resp_json = Ecloud_API.snsSendImage(data)
        logger.info(f"朋友圈发布结果: {resp_json}")

        if resp_json and resp_json.get("code") == 200:
            return {"ok": True, "message": f"朋友圈发布成功: {pyq_post[:50]}..."}
        else:
            return {"ok": False, "message": "", "error": f"朋友圈发布失败: {resp_json}"}
    except Exception as e:
        logger.error(f"moments_tool error: {e}")
        return {"ok": False, "message": "", "error": str(e)}


@tool(description="删除指定照片")
def photo_delete_tool(photo_id: str) -> dict:
    """
    照片删除工具

    从数据库中删除指定的照片记录.

    Args:
        photo_id: 照片ID（embeddings 表中的 _id）

    Returns:
        dict: {
            "ok": bool,  # 是否成功
            "message": str,  # 结果消息
            "error": str  # 错误信息（如果失败）
        }
    """
    try:
        mongo = MongoDBBase()

        # 检查照片是否存在
        photo = mongo.get_vector_by_id("embeddings", photo_id)
        if photo is None:
            return {"ok": False, "message": "", "error": f"找不到照片: {photo_id}"}

        # 删除照片
        mongo.delete_vector("embeddings", photo_id)

        logger.info(f"照片已删除: {photo_id}")

        return {"ok": True, "message": f"照片已删除: {photo_id}"}
    except Exception as e:
        logger.error(f"photo_delete_tool error: {e}")
        return {"ok": False, "message": "", "error": str(e)}


__all__ = [
    "moments_tool",
    "photo_delete_tool",
]
