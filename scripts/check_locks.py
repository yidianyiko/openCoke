#!/usr/bin/env python3
"""检查和清理 MongoDB 中的锁"""
import sys
sys.path.append(".")

from dao.lock import MongoDBLockManager
from datetime import datetime

lock_manager = MongoDBLockManager()

print("=== 当前所有锁 ===")
locks = list(lock_manager.locks.find({}))

if not locks:
    print("没有任何锁")
else:
    now = datetime.utcnow()
    for lock in locks:
        expires_at = lock.get("expires_at")
        is_expired = expires_at < now if expires_at else "未知"
        print(f"资源: {lock.get('resource_id')}")
        print(f"  锁ID: {lock.get('lock_id')}")
        print(f"  创建时间: {lock.get('created_at')}")
        print(f"  过期时间: {expires_at}")
        print(f"  已过期: {is_expired}")
        print()

# 询问是否清理
if locks:
    answer = input("是否清理所有锁? (y/N): ")
    if answer.lower() == 'y':
        result = lock_manager.locks.delete_many({})
        print(f"已删除 {result.deleted_count} 个锁")
