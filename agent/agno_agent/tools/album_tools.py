# -*- coding: utf-8 -*-
"""
Album Tools for Agno Agent

This module currently provides:
- photo_delete_tool: 删除照片
"""

import logging

from agno.tools import tool

from dao.mongo import MongoDBBase

logger = logging.getLogger(__name__)


@tool(description="删除指定照片")
def photo_delete_tool(photo_id: str) -> dict:
    """
    照片删除工具

    从数据库中删除指定的照片记录.

    Args:
        photo_id: 照片ID（embeddings 表中的 _id）

    Returns:
        dict: {
            "ok": bool,
            "message": str,
            "error": str
        }
    """
    try:
        mongo = MongoDBBase()

        photo = mongo.get_vector_by_id("embeddings", photo_id)
        if photo is None:
            return {"ok": False, "message": "", "error": f"找不到照片: {photo_id}"}

        mongo.delete_vector("embeddings", photo_id)
        logger.info(f"照片已删除: {photo_id}")

        return {"ok": True, "message": f"照片已删除: {photo_id}"}
    except Exception as e:
        logger.error(f"photo_delete_tool error: {e}")
        return {"ok": False, "message": "", "error": str(e)}


__all__ = ["photo_delete_tool"]
