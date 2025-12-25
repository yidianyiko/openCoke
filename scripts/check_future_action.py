#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
查询数据库中是否有 FutureResponseAction 相关数据
"""

import sys

sys.path.append(".")

from dao.mongo import MongoDBBase


def main():
    mongo = MongoDBBase()

    # 1. 查询 conversations 中有 future.action 的记录
    print("=" * 60)
    print("1. 查询 conversations 中有 future.action 的记录")
    print("=" * 60)

    results = mongo.find_many(
        "conversations",
        {"conversation_info.future.action": {"$exists": True, "$ne": None}},
        limit=10,
    )

    print(f"找到 {len(results)} 条记录")
    for r in results:
        future = r.get("conversation_info", {}).get("future", {})
        print(f" -_id: {r.get('_id')}")
        print(f"    future: {future}")
        print()

    # 2. 查询 conversations 中有 future 字段的记录（不管是否为空）
    print("=" * 60)
    print("2. 查询 conversations 中有 future 字段的记录")
    print("=" * 60)

    results = mongo.find_many(
        "conversations", {"conversation_info.future": {"$exists": True}}, limit=10
    )

    print(f"找到 {len(results)} 条记录")
    for r in results:
        future = r.get("conversation_info", {}).get("future", {})
        if future:
            print(f" -_id: {r.get('_id')}")
            print(f"    future: {future}")
            print()

    # 3. 查询所有 conversations 的 future 字段统计
    print("=" * 60)
    print("3. 统计 future 字段情况")
    print("=" * 60)

    all_convs = mongo.find_many("conversations", {}, limit=100)
    has_future = 0
    has_action = 0

    for conv in all_convs:
        future = conv.get("conversation_info", {}).get("future", {})
        if future:
            has_future += 1
            if future.get("action"):
                has_action += 1
                print(f"  有 action: {conv.get('_id')} -> {future}")

    print(f"\n总计: {len(all_convs)} 条 conversations")
    print(f"有 future 字段: {has_future} 条")
    print(f"有 future.action: {has_action} 条")


if __name__ == "__main__":
    main()
