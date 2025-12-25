#!/usr/bin/env python3
"""
清理数据库中的敏感关键词，解决 "Content Exists Risk" 问题
"""

import sys

sys.path.append(".")

import re

from dao.mongo import MongoDBBase

mongo = MongoDBBase()

# 需要清理的关键词列表
SENSITIVE_KEYWORDS = [
    "针清",
]


def clean_text(text: str, keywords: list) -> str:
    """从文本中移除敏感关键词"""
    if not text:
        return text

    for keyword in keywords:
        # 使用正则替换，处理各种可能的上下文
        # 例如："去针清一下" -> "去做护理一下"
        text = re.sub(rf"{keyword}", "护理", text)

    return text


def clean_dict_recursive(data, keywords: list):
    """递归清理字典/列表中的所有字符串字段"""
    if isinstance(data, str):
        return clean_text(data, keywords)
    elif isinstance(data, dict):
        return {k: clean_dict_recursive(v, keywords) for k, v in data.items()}
    elif isinstance(data, list):
        return [clean_dict_recursive(item, keywords) for item in data]
    else:
        return data


def contains_keyword(data, keywords: list) -> bool:
    """检查数据中是否包含敏感关键词"""
    if isinstance(data, str):
        return any(kw in data for kw in keywords)
    elif isinstance(data, dict):
        return any(contains_keyword(v, keywords) for v in data.values())
    elif isinstance(data, list):
        return any(contains_keyword(item, keywords) for item in data)
    return False


def cleanup_collection(collection_name: str):
    """清理指定集合中的所有敏感内容"""
    print("=" * 60)
    print(f"开始清理 {collection_name} 集合...")
    print("=" * 60)

    updated_count = 0

    for keyword in SENSITIVE_KEYWORDS:
        print(f"\n搜索包含 '{keyword}' 的记录...")

        # 使用 $regex 在整个文档中搜索 (转换为字符串搜索)
        # 获取所有文档并在 Python 中过滤
        all_docs = mongo.find_many(collection_name, {})
        print(f" -扫描 {len(all_docs)} 条记录...")

        for doc in all_docs:
            doc_id = doc["_id"]

            # 检查文档中是否包含敏感关键词
            if contains_keyword(doc, SENSITIVE_KEYWORDS):
                # 递归清理整个文档
                cleaned_doc = clean_dict_recursive(doc, SENSITIVE_KEYWORDS)

                # 移除 _id 字段（不能更新）
                cleaned_doc.pop("_id", None)

                # 更新文档
                mongo.update_one(
                    collection_name, {"_id": doc_id}, {"$set": cleaned_doc}
                )
                print(f"  ✓ 已清理记录 {doc_id}")
                if "uid" in doc:
                    print(f"    UID: {doc.get('uid', 'N/A')}")
                updated_count += 1

    print(f"\n{collection_name} 集合共清理 {updated_count} 条记录")
    return updated_count


def cleanup_relations():
    """清理 relations 集合中的敏感内容"""
    return cleanup_collection("relations")


def cleanup_conversations():
    """清理 conversations 集合中的敏感内容"""
    return cleanup_collection("conversations")


def cleanup_all_collections():
    """清理数据库中所有集合的敏感内容"""
    print("\n" + "=" * 60)
    print("扫描数据库中的所有集合...")
    print("=" * 60)

    # 获取数据库中所有集合名称
    db = mongo.db
    collection_names = db.list_collection_names()
    print(f"发现 {len(collection_names)} 个集合: {collection_names}")

    total_updated = 0
    for coll_name in collection_names:
        # 跳过系统集合
        if coll_name.startswith("system."):
            continue
        print("\n")
        count = cleanup_collection(coll_name)
        total_updated += count

    return total_updated


def main():
    print("\n" + "=" * 60)
    print("数据库敏感内容清理工具")
    print("目标关键词:", SENSITIVE_KEYWORDS)
    print("=" * 60)

    # 清理数据库中所有集合
    total = cleanup_all_collections()

    print("\n" + "=" * 60)
    print(f"清理完成! 共更新 {total} 条记录")
    print("=" * 60)


if __name__ == "__main__":
    main()
