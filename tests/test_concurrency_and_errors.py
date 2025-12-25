# -*- coding: utf-8 -*-
"""
并发和异常处理测试

测试锁机制、并发处理、错误重试等场景

Requirements:
- 锁机制测试
- 并发处理测试
- 错误重试机制
"""

import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest

from dao.lock import MongoDBLockManager
from dao.mongo import MongoDBBase
from entity.message import (
    increment_retry_count,
    increment_rollback_count,
    update_message_status_safe,
)

logger = logging.getLogger(__name__)


class TestLockMechanism:
    """锁机制测试"""
    
    def test_lock_acquire_and_release(self, mongo_client):
        """测试锁的获取和释放"""
        lock_manager = MongoDBLockManager()
        resource_id = f"test_resource_{uuid.uuid4().hex[:8]}"
        
        # 获取锁
        lock_id = lock_manager.acquire_lock("test", resource_id, timeout=60)
        assert lock_id is not None
        logger.info(f"✓ 获取锁成功: {lock_id}")
        
        # 验证锁存在
        lock_doc = mongo_client.find_one("locks", {
            "resource_type": "test",
            "resource_id": f"test:{resource_id}"
        })
        assert lock_doc is not None
        assert lock_doc["lock_id"] == lock_id
        
        # 释放锁
        released, reason = lock_manager.release_lock_safe("test", resource_id, lock_id)
        assert released
        logger.info("✓ 释放锁成功")
        
        # 验证锁已删除
        lock_doc = mongo_client.find_one("locks", {
            "resource_type": "test",
            "resource_id": f"test:{resource_id}"
        })
        assert lock_doc is None
    
    def test_lock_prevents_duplicate_acquisition(self, mongo_client):
        """测试锁防止重复获取"""
        lock_manager = MongoDBLockManager()
        resource_id = f"test_resource_{uuid.uuid4().hex[:8]}"
        
        # 第一个 worker 获取锁
        lock_id_1 = lock_manager.acquire_lock("test", resource_id, timeout=60)
        assert lock_id_1 is not None
        logger.info(f"✓ Worker 1 获取锁: {lock_id_1}")
        
        # 第二个 worker 尝试获取同一个锁（应该失败）
        lock_id_2 = lock_manager.acquire_lock(
            "test", resource_id, timeout=60, max_wait=0.1
        )
        assert lock_id_2 is None
        logger.info("✓ Worker 2 无法获取锁（符合预期）")
        
        # 释放锁
        lock_manager.release_lock_safe("test", resource_id, lock_id_1)
        
        # 第二个 worker 再次尝试（应该成功）
        lock_id_3 = lock_manager.acquire_lock("test", resource_id, timeout=60)
        assert lock_id_3 is not None
        logger.info(f"✓ Worker 2 成功获取锁: {lock_id_3}")
        
        # 清理
        lock_manager.release_lock_safe("test", resource_id, lock_id_3)
    
    def test_lock_renewal(self, mongo_client):
        """测试锁的续期"""
        lock_manager = MongoDBLockManager()
        resource_id = f"test_resource_{uuid.uuid4().hex[:8]}"
        
        # 获取锁（短超时）
        lock_id = lock_manager.acquire_lock("test", resource_id, timeout=5)
        assert lock_id is not None
        logger.info(f"✓ 获取锁: {lock_id}, timeout=5s")
        
        # 获取初始过期时间
        lock_doc = mongo_client.find_one("locks", {
            "resource_type": "test",
            "resource_id": f"test:{resource_id}"
        })
        initial_expires = lock_doc["expires_at"]
        
        # 等待2秒
        time.sleep(2)
        
        # 续期锁
        lock_manager.renew_lock("test", resource_id, lock_id, timeout=10)
        logger.info("✓ 续期锁成功")
        
        # 验证过期时间已更新
        lock_doc = mongo_client.find_one("locks", {
            "resource_type": "test",
            "resource_id": f"test:{resource_id}"
        })
        new_expires = lock_doc["expires_at"]
        assert new_expires > initial_expires
        logger.info(f"✓ 过期时间已更新: {initial_expires} -> {new_expires}")
        
        # 清理
        lock_manager.release_lock_safe("test", resource_id, lock_id)
    
    def test_lock_timeout_auto_release(self, mongo_client):
        """测试锁超时自动释放"""
        lock_manager = MongoDBLockManager()
        resource_id = f"test_resource_{uuid.uuid4().hex[:8]}"
        
        # 获取锁（1秒超时）
        lock_id = lock_manager.acquire_lock("test", resource_id, timeout=1)
        assert lock_id is not None
        logger.info(f"✓ 获取锁: {lock_id}, timeout=1s")
        
        # 等待锁过期
        time.sleep(2)
        
        # 另一个 worker 应该能获取锁（因为原锁已过期）
        lock_id_2 = lock_manager.acquire_lock("test", resource_id, timeout=60)
        assert lock_id_2 is not None
        logger.info(f"✓ 锁超时后，新 worker 成功获取锁: {lock_id_2}")
        
        # 清理
        lock_manager.release_lock_safe("test", resource_id, lock_id_2)


class TestConcurrency:
    """并发处理测试"""
    
    def test_concurrent_lock_acquisition(self, mongo_client):
        """测试并发获取锁"""
        lock_manager = MongoDBLockManager()
        resource_id = f"test_resource_{uuid.uuid4().hex[:8]}"
        
        results = []
        
        def try_acquire_lock(worker_id):
            """Worker 尝试获取锁"""
            lock_id = lock_manager.acquire_lock(
                "test", resource_id, timeout=60, max_wait=0.5
            )
            if lock_id:
                results.append({"worker_id": worker_id, "lock_id": lock_id})
                time.sleep(0.1)  # 模拟工作
                lock_manager.release_lock_safe("test", resource_id, lock_id)
                return True
            return False
        
        # 启动10个并发 worker
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [
                executor.submit(try_acquire_lock, i) for i in range(10)
            ]
            
            for future in as_completed(futures):
                future.result()
        
        # 验证只有部分 worker 成功获取锁（因为有竞争）
        logger.info(f"✓ {len(results)} 个 worker 成功获取锁")
        assert len(results) > 0
        
        # 验证所有成功的 worker 都有不同的 lock_id
        lock_ids = [r["lock_id"] for r in results]
        assert len(lock_ids) == len(set(lock_ids))
    
    def test_concurrent_message_status_update(self, mongo_client):
        """测试并发更新消息状态（乐观锁）"""
        message_id = str(uuid.uuid4())
        
        # 创建测试消息
        message_data = {
            "_id": message_id,
            "status": "pending",
            "message": "测试消息",
            "input_timestamp": int(time.time()),
        }
        mongo_client.insert_one("inputmessages", message_data)
        
        results = []
        
        def try_update_status(worker_id):
            """Worker 尝试更新状态"""
            success = update_message_status_safe(message_id, "handled", "pending")
            results.append({"worker_id": worker_id, "success": success})
            return success
        
        # 启动5个并发 worker 尝试更新同一条消息
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(try_update_status, i) for i in range(5)
            ]
            
            for future in as_completed(futures):
                future.result()
        
        # 验证只有一个 worker 成功更新
        successful_updates = [r for r in results if r["success"]]
        assert len(successful_updates) == 1
        logger.info(f"✓ 只有 1 个 worker 成功更新（乐观锁生效）")
        
        # 清理
        mongo_client.delete_one("inputmessages", {"_id": message_id})


class TestErrorHandling:
    """错误处理测试"""
    
    def test_retry_count_increment(self, mongo_client):
        """测试重试计数递增"""
        message_id = str(uuid.uuid4())
        
        # 创建测试消息
        message_data = {
            "_id": message_id,
            "status": "pending",
            "message": "测试消息",
            "input_timestamp": int(time.time()),
            "retry_count": 0,
        }
        mongo_client.insert_one("inputmessages", message_data)
        
        # 第一次重试
        retry_count = increment_retry_count(message_id, "错误1")
        assert retry_count == 1
        logger.info(f"✓ 第1次重试: retry_count={retry_count}")
        
        # 第二次重试
        retry_count = increment_retry_count(message_id, "错误2")
        assert retry_count == 2
        logger.info(f"✓ 第2次重试: retry_count={retry_count}")
        
        # 第三次重试
        retry_count = increment_retry_count(message_id, "错误3")
        assert retry_count == 3
        logger.info(f"✓ 第3次重试: retry_count={retry_count}")
        
        # 验证错误信息已保存
        msg = mongo_client.find_one("inputmessages", {"_id": message_id})
        assert msg["retry_count"] == 3
        assert "错误3" in msg.get("last_error", "")
        
        # 清理
        mongo_client.delete_one("inputmessages", {"_id": message_id})
    
    def test_rollback_count_increment(self, mongo_client):
        """测试回滚计数递增"""
        message_id = str(uuid.uuid4())
        
        # 创建测试消息
        message_data = {
            "_id": message_id,
            "status": "pending",
            "message": "测试消息",
            "input_timestamp": int(time.time()),
            "rollback_count": 0,
        }
        mongo_client.insert_one("inputmessages", message_data)
        
        # 第一次回滚
        rollback_count = increment_rollback_count(message_id)
        assert rollback_count == 1
        logger.info(f"✓ 第1次回滚: rollback_count={rollback_count}")
        
        # 第二次回滚
        rollback_count = increment_rollback_count(message_id)
        assert rollback_count == 2
        logger.info(f"✓ 第2次回滚: rollback_count={rollback_count}")
        
        # 第三次回滚
        rollback_count = increment_rollback_count(message_id)
        assert rollback_count == 3
        logger.info(f"✓ 第3次回滚: rollback_count={rollback_count}")
        
        # 验证回滚计数
        msg = mongo_client.find_one("inputmessages", {"_id": message_id})
        assert msg["rollback_count"] == 3
        
        # 清理
        mongo_client.delete_one("inputmessages", {"_id": message_id})
    
    def test_max_retry_limit(self, mongo_client):
        """测试最大重试次数限制"""
        message_id = str(uuid.uuid4())
        MAX_RETRIES = 3
        
        # 创建测试消息
        message_data = {
            "_id": message_id,
            "status": "pending",
            "message": "测试消息",
            "input_timestamp": int(time.time()),
            "retry_count": 0,
        }
        mongo_client.insert_one("inputmessages", message_data)
        
        # 重试到达上限
        for i in range(MAX_RETRIES):
            increment_retry_count(message_id, f"错误{i+1}")
        
        # 验证重试次数
        msg = mongo_client.find_one("inputmessages", {"_id": message_id})
        assert msg["retry_count"] == MAX_RETRIES
        logger.info(f"✓ 达到最大重试次数: {MAX_RETRIES}")
        
        # 模拟达到上限后标记为失败
        update_message_status_safe(message_id, "failed", "pending")
        
        # 验证状态
        msg = mongo_client.find_one("inputmessages", {"_id": message_id})
        assert msg["status"] == "failed"
        logger.info("✓ 达到上限后标记为 failed")
        
        # 清理
        mongo_client.delete_one("inputmessages", {"_id": message_id})


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
