# -*- coding: utf-8 -*-
"""
异步 Workflow 测试

验证 Workflow 异步化改造是否正确
"""
import sys

sys.path.append(".")
import inspect
import unittest


class TestAsyncWorkflows(unittest.TestCase):
    """测试 Workflow 异步化"""

    def test_prepare_workflow_run_is_async(self):
        """测试 PrepareWorkflow.run 是异步方法"""
        from agent.agno_agent.workflows import PrepareWorkflow

        workflow = PrepareWorkflow()
        self.assertTrue(inspect.iscoroutinefunction(workflow.run))

    def test_streaming_chat_workflow_run_is_async(self):
        """测试 StreamingChatWorkflow.run 是异步方法"""
        from agent.agno_agent.workflows import StreamingChatWorkflow

        workflow = StreamingChatWorkflow()
        self.assertTrue(inspect.iscoroutinefunction(workflow.run))

    def test_post_analyze_workflow_run_is_async(self):
        """测试 PostAnalyzeWorkflow.run 是异步方法"""
        from agent.agno_agent.workflows import PostAnalyzeWorkflow

        workflow = PostAnalyzeWorkflow()
        self.assertTrue(inspect.iscoroutinefunction(workflow.run))

    def test_future_message_workflow_run_is_async(self):
        """测试 FutureMessageWorkflow.run 是异步方法"""
        from agent.agno_agent.workflows import FutureMessageWorkflow

        workflow = FutureMessageWorkflow()
        self.assertTrue(inspect.iscoroutinefunction(workflow.run))

    def test_streaming_chat_workflow_run_stream_is_async(self):
        """测试 StreamingChatWorkflow.run_stream 是异步生成器"""
        from agent.agno_agent.workflows import StreamingChatWorkflow

        workflow = StreamingChatWorkflow()
        self.assertTrue(inspect.isasyncgenfunction(workflow.run_stream))


class TestAsyncLockManager(unittest.TestCase):
    """测试锁管理器异步方法"""

    def test_lock_manager_has_async_methods(self):
        """测试 MongoDBLockManager 有异步方法"""
        from dao.lock import MongoDBLockManager

        # 检查异步方法存在
        self.assertTrue(hasattr(MongoDBLockManager, "acquire_lock_async"))
        self.assertTrue(hasattr(MongoDBLockManager, "release_lock_async"))
        self.assertTrue(hasattr(MongoDBLockManager, "lock_async"))

    def test_acquire_lock_async_is_coroutine(self):
        """测试 acquire_lock_async 是协程函数"""
        from dao.lock import MongoDBLockManager

        lock_manager = MongoDBLockManager()
        self.assertTrue(inspect.iscoroutinefunction(lock_manager.acquire_lock_async))

    def test_release_lock_async_is_coroutine(self):
        """测试 release_lock_async 是协程函数"""
        from dao.lock import MongoDBLockManager

        lock_manager = MongoDBLockManager()
        self.assertTrue(inspect.iscoroutinefunction(lock_manager.release_lock_async))


class TestHandlerIsAsync(unittest.TestCase):
    """测试 Handler 是异步的"""

    @unittest.skipUnless(
        __import__("os").environ.get("OSS_ACCESS_KEY_ID"), "需要 OSS 环境变量"
    )
    def test_create_handler_returns_async_function(self):
        """测试 create_handler 返回异步函数"""
        from agent.runner.agent_handler import create_handler

        handler = create_handler(0)
        self.assertTrue(inspect.iscoroutinefunction(handler))


if __name__ == "__main__":
    unittest.main()
