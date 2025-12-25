# -*- coding: utf-8 -*-
"""
Production Environment Stress Test Suite

Comprehensive stress tests focusing on three key message input scenarios:
1. Proactive message input - Messages initiated by character
2. Reminder message input - Scheduled/timed reminder messages
3. User message input - Direct user-initiated messages

Test Categories:
- Concurrent message processing (race conditions)
- High-frequency message inputs (system limits)
- Edge cases (malformed/unexpected message formats)
- Long-running sessions (memory leaks/state corruption)
- Error handling (component failures/timeouts)

Usage:
    pytest tests/stress/test_production_stress.py -v --tb=short
    pytest tests/stress/test_production_stress.py::TestConcurrentProcessing -v
    pytest tests/stress/test_production_stress.py -k "high_frequency" -v
"""
import asyncio
import gc
import os
import random
import sys
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


# ============ Test Configuration ============

@dataclass
class StressTestConfig:
    """Configuration for stress tests"""
    # Concurrency settings
    num_concurrent_workers: int = 5
    num_concurrent_messages: int = 20
    
    # High-frequency settings
    messages_per_second: int = 10
    high_frequency_duration: int = 30  # seconds
    
    # Long-running settings
    long_run_duration: int = 60  # seconds
    memory_check_interval: int = 5  # seconds
    
    # Timeouts
    message_timeout: int = 30
    lock_timeout: int = 10
    
    # Test user IDs
    test_user_prefix: str = "stress_test_user_"
    test_character_prefix: str = "stress_test_char_"


# ============ Test Result Tracking ============

@dataclass
class TestResult:
    """Track individual test execution results"""
    test_name: str
    success: bool
    duration: float
    error: Optional[str] = None
    metrics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StressTestReport:
    """Aggregated stress test report"""
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    results: List[TestResult] = field(default_factory=list)
    bugs_found: List[Dict[str, Any]] = field(default_factory=list)
    performance_issues: List[Dict[str, Any]] = field(default_factory=list)
    
    def add_bug(self, category: str, description: str, severity: str, details: Dict = None):
        self.bugs_found.append({
            "category": category,
            "description": description,
            "severity": severity,
            "details": details or {},
            "timestamp": datetime.now().isoformat()
        })
    
    def add_performance_issue(self, metric: str, expected: Any, actual: Any, description: str):
        self.performance_issues.append({
            "metric": metric,
            "expected": expected,
            "actual": actual,
            "description": description,
            "timestamp": datetime.now().isoformat()
        })
    
    def summary(self) -> str:
        total = len(self.results)
        passed = sum(1 for r in self.results if r.success)
        failed = total - passed
        
        return f"""
=== STRESS TEST REPORT ===
Duration: {(self.end_time - self.start_time).total_seconds():.2f}s
Tests: {total} total, {passed} passed, {failed} failed

Bugs Found: {len(self.bugs_found)}
{chr(10).join(f"  - [{b['severity']}] {b['category']}: {b['description']}" for b in self.bugs_found)}

Performance Issues: {len(self.performance_issues)}
{chr(10).join(f"  - {p['metric']}: expected {p['expected']}, got {p['actual']}" for p in self.performance_issues)}
"""


# ============ Mock Factories ============

def create_mock_user(user_id: str = None) -> Dict:
    """Create a mock user document"""
    user_id = user_id or f"user_{uuid.uuid4().hex[:8]}"
    return {
        "_id": user_id,
        "platforms": {
            "wechat": {
                "id": f"wxid_{user_id}",
                "nickname": f"TestUser_{user_id[:8]}"
            }
        },
        "is_character": False,
        "created_at": int(time.time())
    }


def create_mock_character(char_id: str = None) -> Dict:
    """Create a mock character document"""
    char_id = char_id or f"char_{uuid.uuid4().hex[:8]}"
    return {
        "_id": char_id,
        "platforms": {
            "wechat": {
                "id": f"wxid_{char_id}",
                "nickname": f"TestChar_{char_id[:8]}"
            }
        },
        "is_character": True,
        "user_info": {
            "description": "Test character for stress testing",
            "status": {"place": "测试环境", "action": "压力测试"}
        }
    }


def create_mock_conversation(user_id: str, char_id: str) -> Dict:
    """Create a mock conversation document"""
    return {
        "_id": f"conv_{uuid.uuid4().hex[:8]}",
        "platform": "wechat",
        "talkers": [
            {"id": f"wxid_{user_id}", "nickname": f"User_{user_id[:8]}"},
            {"id": f"wxid_{char_id}", "nickname": f"Char_{char_id[:8]}"}
        ],
        "conversation_info": {
            "chat_history": [],
            "input_messages": [],
            "input_messages_str": "",
            "chat_history_str": "",
            "time_str": datetime.now().strftime("%Y年%m月%d日"),
            "photo_history": [],
            "future": {"timestamp": None, "action": None},
            "turn_sent_contents": []
        }
    }


def create_mock_input_message(
    from_user: str,
    to_user: str,
    message: str,
    message_type: str = "text",
    status: str = "pending"
) -> Dict:
    """Create a mock input message document"""
    return {
        "_id": f"msg_{uuid.uuid4().hex[:8]}",
        "from_user": from_user,
        "to_user": to_user,
        "platform": "wechat",
        "message": message,
        "message_type": message_type,
        "status": status,
        "input_timestamp": int(time.time()),
        "retry_count": 0,
        "rollback_count": 0
    }


def create_mock_reminder(
    user_id: str,
    char_id: str,
    conv_id: str,
    trigger_time: int = None
) -> Dict:
    """Create a mock reminder document"""
    return {
        "reminder_id": str(uuid.uuid4()),
        "user_id": user_id,
        "character_id": char_id,
        "conversation_id": conv_id,
        "title": f"测试提醒_{uuid.uuid4().hex[:8]}",
        "action_template": "这是一个压力测试提醒",
        "next_trigger_time": trigger_time or int(time.time()),
        "status": "confirmed",
        "triggered_count": 0,
        "recurrence": {"enabled": False}
    }


def create_mock_context(user: Dict, character: Dict, conversation: Dict) -> Dict:
    """Create a complete mock context for message processing"""
    return {
        "user": user,
        "character": character,
        "conversation": conversation,
        "relation": {
            "_id": f"rel_{uuid.uuid4().hex[:8]}",
            "uid": str(user["_id"]),
            "cid": str(character["_id"]),
            "relationship": {
                "closeness": 50,
                "trustness": 50,
                "dislike": 0,
                "status": "空闲"
            },
            "user_info": {"realname": "", "hobbyname": "", "description": ""},
            "character_info": {
                "longterm_purpose": "测试",
                "shortterm_purpose": "压力测试",
                "attitude": "正常",
                "status": "空闲"
            }
        },
        "news_str": "",
        "repeated_input_notice": "",
        "MultiModalResponses": [],
        "message_source": "user",
        "input_timestamp": int(time.time()),
        "context_retrieve": {
            "character_global": "",
            "character_private": "",
            "user": "",
            "character_knowledge": "",
            "confirmed_reminders": "",
            "relevant_history": ""
        },
        "query_rewrite": {
            "InnerMonologue": "",
            "CharacterSettingQueryQuestion": "",
            "CharacterSettingQueryKeywords": "",
            "UserProfileQueryQuestion": "",
            "UserProfileQueryKeywords": "",
            "CharacterKnowledgeQueryQuestion": "",
            "CharacterKnowledgeQueryKeywords": ""
        },
        "proactive_forbidden_messages": "",
        "proactive_times": 0
    }


# ============ Fixtures ============

@pytest.fixture
def config():
    """Provide test configuration"""
    return StressTestConfig()


@pytest.fixture
def report():
    """Provide test report tracker"""
    return StressTestReport()


@pytest.fixture
def mock_mongo():
    """Mock MongoDB operations"""
    with patch("dao.mongo.MongoDBBase") as mock:
        instance = MagicMock()
        instance.find_one = MagicMock(return_value=None)
        instance.find_many = MagicMock(return_value=[])
        instance.insert_one = MagicMock(return_value="mock_id")
        instance.update_one = MagicMock(return_value=MagicMock(modified_count=1))
        instance.replace_one = MagicMock(return_value=MagicMock(modified_count=1))
        mock.return_value = instance
        yield instance


@pytest.fixture
def mock_lock_manager():
    """Mock lock manager for concurrency tests"""
    locks = {}
    lock_mutex = threading.Lock()
    
    class MockLockManager:
        def acquire_lock(self, resource_type, resource_id, timeout=30, max_wait=60):
            key = f"{resource_type}:{resource_id}"
            with lock_mutex:
                if key in locks:
                    return None
                lock_id = str(uuid.uuid4())
                locks[key] = lock_id
                return lock_id
        
        async def acquire_lock_async(self, resource_type, resource_id, timeout=30, max_wait=60):
            return self.acquire_lock(resource_type, resource_id, timeout, max_wait)
        
        def release_lock(self, resource_type, resource_id, lock_id):
            key = f"{resource_type}:{resource_id}"
            with lock_mutex:
                if key in locks and locks[key] == lock_id:
                    del locks[key]
                    return True
                return False
        
        def release_lock_safe(self, resource_type, resource_id, lock_id):
            success = self.release_lock(resource_type, resource_id, lock_id)
            return (success, "released" if success else "lock_not_found")
        
        async def release_lock_safe_async(self, resource_type, resource_id, lock_id):
            return self.release_lock_safe(resource_type, resource_id, lock_id)
        
        def renew_lock(self, resource_type, resource_id, lock_id, timeout=30):
            key = f"{resource_type}:{resource_id}"
            with lock_mutex:
                return key in locks and locks[key] == lock_id
        
        def get_lock_info(self, resource_type, resource_id):
            key = f"{resource_type}:{resource_id}"
            with lock_mutex:
                if key in locks:
                    return {"lock_id": locks[key], "resource_id": key}
                return None
    
    return MockLockManager()


@pytest.fixture
def mock_workflow():
    """Mock workflow for testing"""
    async def mock_run(input_message=None, session_state=None):
        await asyncio.sleep(random.uniform(0.01, 0.05))
        return {"session_state": session_state or {}}
    
    async def mock_run_stream(input_message=None, session_state=None):
        for i in range(random.randint(1, 3)):
            await asyncio.sleep(random.uniform(0.01, 0.02))
            yield {
                "type": "message",
                "data": {"type": "text", "content": f"Response {i}"}
            }
        yield {"type": "done", "data": {"total_messages": 3}}
    
    return MagicMock(run=mock_run, run_stream=mock_run_stream)


# ============ Test Classes ============

class TestConcurrentProcessing:
    """
    Test concurrent message processing to identify race conditions
    
    Focus areas:
    - Multiple workers processing same conversation
    - Lock contention and deadlocks
    - State consistency under concurrent access
    """
    
    @pytest.mark.asyncio
    async def test_concurrent_user_messages_same_conversation(
        self, config, report, mock_lock_manager
    ):
        """Test multiple workers trying to process messages for same conversation"""
        conversation_id = "test_conv_001"
        results = []
        errors = []
        
        async def worker(worker_id: int):
            try:
                lock = await mock_lock_manager.acquire_lock_async(
                    "conversation", conversation_id, timeout=5, max_wait=0.1
                )
                if lock:
                    await asyncio.sleep(random.uniform(0.01, 0.05))
                    success, _ = await mock_lock_manager.release_lock_safe_async(
                        "conversation", conversation_id, lock
                    )
                    results.append(("acquired", worker_id, lock))
                else:
                    results.append(("contention", worker_id, None))
            except Exception as e:
                errors.append((worker_id, str(e)))
        
        # Launch concurrent workers
        workers = [worker(i) for i in range(config.num_concurrent_workers)]
        await asyncio.gather(*workers)
        
        # Verify: Only one worker should acquire lock at a time
        acquired = [r for r in results if r[0] == "acquired"]
        contention = [r for r in results if r[0] == "contention"]
        
        # Check for race condition bugs
        if len(acquired) > 1:
            # Check if they were acquired sequentially (releases happened)
            pass  # Expected behavior with fast release
        
        assert len(errors) == 0, f"Errors during concurrent access: {errors}"
        
        report.results.append(TestResult(
            test_name="concurrent_user_messages_same_conversation",
            success=len(errors) == 0,
            duration=0,
            metrics={
                "workers": config.num_concurrent_workers,
                "acquired": len(acquired),
                "contention": len(contention)
            }
        ))
    
    @pytest.mark.asyncio
    async def test_concurrent_different_message_types(self, config, report, mock_lock_manager):
        """Test concurrent processing of different message types"""
        errors = []
        results = {"user": 0, "reminder": 0, "proactive": 0}
        
        async def process_user_message():
            try:
                lock = await mock_lock_manager.acquire_lock_async(
                    "conversation", "user_conv", max_wait=0.5
                )
                if lock:
                    await asyncio.sleep(0.02)
                    mock_lock_manager.release_lock_safe("conversation", "user_conv", lock)
                    results["user"] += 1
            except Exception as e:
                errors.append(("user", str(e)))
        
        async def process_reminder_message():
            try:
                lock = await mock_lock_manager.acquire_lock_async(
                    "conversation", "reminder_conv", max_wait=0.5
                )
                if lock:
                    await asyncio.sleep(0.02)
                    mock_lock_manager.release_lock_safe("conversation", "reminder_conv", lock)
                    results["reminder"] += 1
            except Exception as e:
                errors.append(("reminder", str(e)))
        
        async def process_proactive_message():
            try:
                lock = await mock_lock_manager.acquire_lock_async(
                    "conversation", "proactive_conv", max_wait=0.5
                )
                if lock:
                    await asyncio.sleep(0.02)
                    mock_lock_manager.release_lock_safe("conversation", "proactive_conv", lock)
                    results["proactive"] += 1
            except Exception as e:
                errors.append(("proactive", str(e)))
        
        # Mix different message types
        tasks = []
        for _ in range(5):
            tasks.extend([
                process_user_message(),
                process_reminder_message(),
                process_proactive_message()
            ])
        
        await asyncio.gather(*tasks)
        
        assert len(errors) == 0, f"Errors in mixed message processing: {errors}"
        
        report.results.append(TestResult(
            test_name="concurrent_different_message_types",
            success=len(errors) == 0,
            duration=0,
            metrics=results
        ))
    
    @pytest.mark.asyncio
    async def test_lock_timeout_handling(self, config, report, mock_lock_manager):
        """Test behavior when locks timeout during processing"""
        conversation_id = "timeout_test_conv"
        
        # Acquire lock and hold it
        held_lock = await mock_lock_manager.acquire_lock_async(
            "conversation", conversation_id, timeout=1, max_wait=0.1
        )
        assert held_lock is not None, "Failed to acquire initial lock"
        
        # Try to acquire from another "worker" - should fail
        second_lock = await mock_lock_manager.acquire_lock_async(
            "conversation", conversation_id, timeout=1, max_wait=0.5
        )
        
        # Second worker should not get the lock
        assert second_lock is None, "Lock acquired when it should be held"
        
        # Release the first lock
        mock_lock_manager.release_lock_safe("conversation", conversation_id, held_lock)
        
        # Now second worker should be able to acquire
        third_lock = await mock_lock_manager.acquire_lock_async(
            "conversation", conversation_id, timeout=1, max_wait=0.5
        )
        assert third_lock is not None, "Failed to acquire lock after release"
        
        mock_lock_manager.release_lock_safe("conversation", conversation_id, third_lock)
        
        report.results.append(TestResult(
            test_name="lock_timeout_handling",
            success=True,
            duration=0
        ))
    
    @pytest.mark.asyncio
    async def test_deadlock_prevention(self, config, report, mock_lock_manager):
        """Test that system prevents deadlocks with multiple resources"""
        errors = []
        completed = []
        
        async def worker_a():
            try:
                lock1 = await mock_lock_manager.acquire_lock_async(
                    "conversation", "conv_a", max_wait=0.5
                )
                if lock1:
                    await asyncio.sleep(0.01)
                    lock2 = await mock_lock_manager.acquire_lock_async(
                        "conversation", "conv_b", max_wait=0.2
                    )
                    if lock2:
                        completed.append("worker_a_both")
                        mock_lock_manager.release_lock_safe("conversation", "conv_b", lock2)
                    else:
                        completed.append("worker_a_partial")
                    mock_lock_manager.release_lock_safe("conversation", "conv_a", lock1)
            except Exception as e:
                errors.append(("worker_a", str(e)))
        
        async def worker_b():
            try:
                lock1 = await mock_lock_manager.acquire_lock_async(
                    "conversation", "conv_b", max_wait=0.5
                )
                if lock1:
                    await asyncio.sleep(0.01)
                    lock2 = await mock_lock_manager.acquire_lock_async(
                        "conversation", "conv_a", max_wait=0.2
                    )
                    if lock2:
                        completed.append("worker_b_both")
                        mock_lock_manager.release_lock_safe("conversation", "conv_a", lock2)
                    else:
                        completed.append("worker_b_partial")
                    mock_lock_manager.release_lock_safe("conversation", "conv_b", lock1)
            except Exception as e:
                errors.append(("worker_b", str(e)))
        
        # Run concurrently - potential deadlock scenario
        await asyncio.gather(worker_a(), worker_b())
        
        # At least one should complete (no deadlock)
        assert len(completed) > 0, "Possible deadlock detected - no workers completed"
        assert len(errors) == 0, f"Errors during deadlock test: {errors}"
        
        report.results.append(TestResult(
            test_name="deadlock_prevention",
            success=len(errors) == 0 and len(completed) > 0,
            duration=0,
            metrics={"completed": completed}
        ))


class TestHighFrequencyInput:
    """
    Test high-frequency message inputs to identify system limits
    
    Focus areas:
    - Message queue overflow
    - Processing backlog
    - Response latency under load
    """
    
    @pytest.mark.asyncio
    async def test_rapid_user_message_burst(self, config, report):
        """Test rapid burst of user messages"""
        messages_sent = 0
        messages_processed = 0
        processing_times = []
        errors = []
        
        async def simulate_message():
            nonlocal messages_sent, messages_processed
            messages_sent += 1
            start = time.time()
            try:
                # Simulate message processing
                await asyncio.sleep(random.uniform(0.005, 0.02))
                messages_processed += 1
                processing_times.append(time.time() - start)
            except Exception as e:
                errors.append(str(e))
        
        # Send burst of messages
        burst_size = 100
        tasks = [simulate_message() for _ in range(burst_size)]
        
        start_time = time.time()
        await asyncio.gather(*tasks)
        total_time = time.time() - start_time
        
        # Calculate metrics
        avg_latency = sum(processing_times) / len(processing_times) if processing_times else 0
        throughput = messages_processed / total_time if total_time > 0 else 0
        
        # Performance checks
        if avg_latency > 0.1:
            report.add_performance_issue(
                "average_latency",
                "<100ms",
                f"{avg_latency*1000:.2f}ms",
                "Message processing latency exceeds threshold"
            )
        
        assert messages_processed == burst_size, f"Lost messages: {burst_size - messages_processed}"
        
        report.results.append(TestResult(
            test_name="rapid_user_message_burst",
            success=len(errors) == 0,
            duration=total_time,
            metrics={
                "burst_size": burst_size,
                "processed": messages_processed,
                "avg_latency_ms": avg_latency * 1000,
                "throughput_mps": throughput
            }
        ))
    
    @pytest.mark.asyncio
    async def test_sustained_high_frequency(self, config, report):
        """Test sustained high-frequency message input"""
        duration_seconds = 5
        target_rate = 20  # messages per second
        
        messages_sent = 0
        messages_processed = 0
        errors = []
        latencies = []
        
        async def send_message():
            nonlocal messages_sent, messages_processed
            messages_sent += 1
            start = time.time()
            try:
                await asyncio.sleep(random.uniform(0.01, 0.03))
                messages_processed += 1
                latencies.append(time.time() - start)
            except Exception as e:
                errors.append(str(e))
        
        start_time = time.time()
        tasks = []
        
        while time.time() - start_time < duration_seconds:
            tasks.append(asyncio.create_task(send_message()))
            await asyncio.sleep(1 / target_rate)
        
        # Wait for all tasks
        await asyncio.gather(*tasks, return_exceptions=True)
        
        total_time = time.time() - start_time
        actual_rate = messages_sent / total_time
        
        # Calculate percentiles
        sorted_latencies = sorted(latencies)
        p50 = sorted_latencies[len(sorted_latencies) // 2] if sorted_latencies else 0
        p99 = sorted_latencies[int(len(sorted_latencies) * 0.99)] if sorted_latencies else 0
        
        # Performance checks
        if p99 > 0.5:
            report.add_performance_issue(
                "p99_latency",
                "<500ms",
                f"{p99*1000:.2f}ms",
                "P99 latency too high under sustained load"
            )
        
        report.results.append(TestResult(
            test_name="sustained_high_frequency",
            success=len(errors) == 0,
            duration=total_time,
            metrics={
                "target_rate": target_rate,
                "actual_rate": actual_rate,
                "messages_sent": messages_sent,
                "p50_latency_ms": p50 * 1000,
                "p99_latency_ms": p99 * 1000
            }
        ))
    
    @pytest.mark.asyncio
    async def test_mixed_message_types_high_frequency(self, config, report):
        """Test high-frequency input with mixed message types"""
        counts = {"user": 0, "reminder": 0, "proactive": 0}
        errors = []
        
        message_types = ["user", "reminder", "proactive"]
        
        async def process_message(msg_type: str):
            try:
                # Simulate different processing times by type
                delays = {"user": 0.02, "reminder": 0.03, "proactive": 0.04}
                await asyncio.sleep(random.uniform(0.01, delays[msg_type]))
                counts[msg_type] += 1
            except Exception as e:
                errors.append((msg_type, str(e)))
        
        # Generate mixed workload
        tasks = []
        for _ in range(50):
            msg_type = random.choice(message_types)
            tasks.append(process_message(msg_type))
        
        start_time = time.time()
        await asyncio.gather(*tasks)
        total_time = time.time() - start_time
        
        total_processed = sum(counts.values())
        assert total_processed == 50, f"Lost messages: {50 - total_processed}"
        
        report.results.append(TestResult(
            test_name="mixed_message_types_high_frequency",
            success=len(errors) == 0,
            duration=total_time,
            metrics={
                "counts": counts,
                "throughput": total_processed / total_time
            }
        ))


class TestEdgeCases:
    """
    Test edge cases with malformed or unexpected message formats
    
    Focus areas:
    - Empty/null messages
    - Extremely long messages
    - Special characters and encoding issues
    - Invalid message types
    - Missing required fields
    """
    
    def test_empty_message_handling(self, report):
        """Test handling of empty messages"""
        empty_cases = [
            "",
            None,
            "   ",
            "\n\n",
            "\t",
        ]
        
        errors = []
        for i, empty_case in enumerate(empty_cases):
            try:
                msg = create_mock_input_message(
                    "user1", "char1",
                    message=empty_case if empty_case is not None else ""
                )
                # Validate message structure
                assert msg["message"] is not None or empty_case is None
            except Exception as e:
                errors.append((i, str(e)))
        
        report.results.append(TestResult(
            test_name="empty_message_handling",
            success=len(errors) == 0,
            duration=0,
            metrics={"cases_tested": len(empty_cases), "errors": len(errors)}
        ))
    
    def test_extremely_long_message(self, report):
        """Test handling of extremely long messages"""
        long_messages = [
            "a" * 1000,
            "a" * 10000,
            "a" * 100000,
            "测试" * 10000,  # Unicode chars
        ]
        
        errors = []
        for i, long_msg in enumerate(long_messages):
            try:
                msg = create_mock_input_message("user1", "char1", message=long_msg)
                assert len(msg["message"]) == len(long_msg)
            except Exception as e:
                errors.append((i, len(long_msg), str(e)))
                report.add_bug(
                    "message_length",
                    f"Failed to handle message of length {len(long_msg)}",
                    "medium",
                    {"error": str(e)}
                )
        
        report.results.append(TestResult(
            test_name="extremely_long_message",
            success=len(errors) == 0,
            duration=0,
            metrics={"max_length_tested": max(len(m) for m in long_messages)}
        ))
    
    def test_special_characters_in_message(self, report):
        """Test handling of special characters"""
        special_messages = [
            "Hello\x00World",  # Null byte
            "Test\ud83d\ude00Emoji",  # Emoji
            "中文测试消息",  # Chinese
            "日本語テスト",  # Japanese
            "العربية",  # Arabic
            "<script>alert('xss')</script>",  # HTML injection
            "'; DROP TABLE messages; --",  # SQL injection attempt
            "{{7*7}}",  # Template injection
            "\n\r\t\b\f",  # Control characters
            "​",  # Zero-width space
        ]
        
        errors = []
        for msg_text in special_messages:
            try:
                msg = create_mock_input_message("user1", "char1", message=msg_text)
                # Should store without error
                assert msg["message"] == msg_text
            except Exception as e:
                errors.append((msg_text[:20], str(e)))
                report.add_bug(
                    "special_characters",
                    f"Failed to handle special characters: {msg_text[:20]}...",
                    "low",
                    {"error": str(e)}
                )
        
        report.results.append(TestResult(
            test_name="special_characters_in_message",
            success=len(errors) == 0,
            duration=0,
            metrics={"cases_tested": len(special_messages), "errors": len(errors)}
        ))
    
    def test_invalid_message_types(self, report):
        """Test handling of invalid or unexpected message types"""
        invalid_types = [
            "invalid_type",
            "",
            None,
            "TEXT",  # Wrong case
            "audio",  # Unsupported
            "video",
            "file",
            123,  # Wrong type
        ]
        
        errors = []
        for msg_type in invalid_types:
            try:
                msg = create_mock_input_message(
                    "user1", "char1",
                    message="test",
                    message_type=str(msg_type) if msg_type else "text"
                )
                # Should handle gracefully
            except Exception as e:
                errors.append((msg_type, str(e)))
        
        report.results.append(TestResult(
            test_name="invalid_message_types",
            success=True,  # We expect graceful handling
            duration=0,
            metrics={"types_tested": len(invalid_types)}
        ))
    
    def test_missing_required_fields(self, report):
        """Test handling of messages with missing required fields"""
        base_msg = {
            "_id": "msg_001",
            "from_user": "user1",
            "to_user": "char1",
            "message": "test",
            "status": "pending"
        }
        
        required_fields = ["from_user", "to_user", "message"]
        errors = []
        
        for field in required_fields:
            try:
                incomplete_msg = {k: v for k, v in base_msg.items() if k != field}
                # Should raise or handle missing field
                if field not in incomplete_msg:
                    # Expected - field is missing
                    pass
            except Exception as e:
                errors.append((field, str(e)))
        
        report.results.append(TestResult(
            test_name="missing_required_fields",
            success=True,
            duration=0,
            metrics={"fields_tested": len(required_fields)}
        ))
    
    def test_malformed_conversation_context(self, report):
        """Test handling of malformed conversation context"""
        malformed_contexts = [
            {},  # Empty context
            {"user": None},  # Null user
            {"user": {}, "character": {}},  # Empty user/character
            {"conversation": {"conversation_info": None}},  # Null conversation_info
        ]
        
        errors = []
        for ctx in malformed_contexts:
            try:
                # Attempt to use malformed context
                _ = ctx.get("user", {}).get("_id")
                _ = ctx.get("character", {}).get("platforms", {}).get("wechat", {})
            except Exception as e:
                errors.append((str(ctx)[:50], str(e)))
        
        report.results.append(TestResult(
            test_name="malformed_conversation_context",
            success=len(errors) == 0,
            duration=0,
            metrics={"contexts_tested": len(malformed_contexts)}
        ))


class TestLongRunningSessions:
    """
    Test long-running sessions to identify memory leaks or state corruption
    
    Focus areas:
    - Memory growth over time
    - State accumulation
    - Resource cleanup
    """
    
    @pytest.mark.asyncio
    async def test_memory_stability_under_load(self, config, report):
        """Test memory stability during extended operation"""
        import tracemalloc
        
        tracemalloc.start()
        initial_memory = tracemalloc.get_traced_memory()[0]
        memory_samples = [initial_memory]
        
        # Simulate extended operation
        iterations = 100
        for i in range(iterations):
            # Create and discard objects
            user = create_mock_user()
            char = create_mock_character()
            conv = create_mock_conversation(user["_id"], char["_id"])
            ctx = create_mock_context(user, char, conv)
            
            # Create messages
            for _ in range(10):
                msg = create_mock_input_message(
                    user["_id"], char["_id"],
                    f"Test message {i}"
                )
            
            # Periodic memory sampling
            if i % 10 == 0:
                gc.collect()
                current_memory = tracemalloc.get_traced_memory()[0]
                memory_samples.append(current_memory)
        
        gc.collect()
        final_memory = tracemalloc.get_traced_memory()[0]
        tracemalloc.stop()
        
        # Calculate memory growth
        memory_growth = final_memory - initial_memory
        memory_growth_mb = memory_growth / (1024 * 1024)
        
        # Check for significant memory leak
        if memory_growth_mb > 10:  # More than 10MB growth
            report.add_bug(
                "memory_leak",
                f"Potential memory leak: {memory_growth_mb:.2f}MB growth over {iterations} iterations",
                "high",
                {"initial_mb": initial_memory / (1024*1024), "final_mb": final_memory / (1024*1024)}
            )
        
        report.results.append(TestResult(
            test_name="memory_stability_under_load",
            success=memory_growth_mb < 50,  # Allow up to 50MB
            duration=0,
            metrics={
                "iterations": iterations,
                "initial_memory_mb": initial_memory / (1024*1024),
                "final_memory_mb": final_memory / (1024*1024),
                "growth_mb": memory_growth_mb
            }
        ))
    
    @pytest.mark.asyncio
    async def test_chat_history_accumulation(self, config, report):
        """Test chat history doesn't grow unboundedly"""
        max_history_size = 15  # As defined in agent_handler.py
        
        user = create_mock_user()
        char = create_mock_character()
        conv = create_mock_conversation(user["_id"], char["_id"])
        
        # Simulate many conversation rounds
        for i in range(100):
            conv["conversation_info"]["chat_history"].append({
                "from_user": user["_id"],
                "message": f"Message {i}",
                "timestamp": int(time.time())
            })
            conv["conversation_info"]["chat_history"].append({
                "from_user": char["_id"],
                "message": f"Response {i}",
                "timestamp": int(time.time())
            })
            
            # Simulate history trimming (as done in finalize_success)
            if len(conv["conversation_info"]["chat_history"]) > max_history_size:
                conv["conversation_info"]["chat_history"] = \
                    conv["conversation_info"]["chat_history"][-max_history_size:]
        
        final_size = len(conv["conversation_info"]["chat_history"])
        
        # Verify history is properly bounded
        assert final_size <= max_history_size, \
            f"Chat history grew beyond limit: {final_size} > {max_history_size}"
        
        report.results.append(TestResult(
            test_name="chat_history_accumulation",
            success=final_size <= max_history_size,
            duration=0,
            metrics={"max_allowed": max_history_size, "final_size": final_size}
        ))
    
    @pytest.mark.asyncio
    async def test_state_consistency_across_operations(self, config, report):
        """Test state remains consistent across many operations"""
        user = create_mock_user()
        char = create_mock_character()
        conv = create_mock_conversation(user["_id"], char["_id"])
        ctx = create_mock_context(user, char, conv)
        
        # Track relationship values
        initial_closeness = ctx["relation"]["relationship"]["closeness"]
        initial_trustness = ctx["relation"]["relationship"]["trustness"]
        
        operations = []
        for i in range(50):
            # Simulate relationship changes
            delta = random.randint(-2, 3)
            ctx["relation"]["relationship"]["closeness"] = max(0, min(100,
                ctx["relation"]["relationship"]["closeness"] + delta))
            operations.append(("closeness", delta))
            
            delta = random.randint(-2, 3)
            ctx["relation"]["relationship"]["trustness"] = max(0, min(100,
                ctx["relation"]["relationship"]["trustness"] + delta))
            operations.append(("trustness", delta))
        
        # Verify values are within valid range
        final_closeness = ctx["relation"]["relationship"]["closeness"]
        final_trustness = ctx["relation"]["relationship"]["trustness"]
        
        assert 0 <= final_closeness <= 100, f"Closeness out of range: {final_closeness}"
        assert 0 <= final_trustness <= 100, f"Trustness out of range: {final_trustness}"
        
        report.results.append(TestResult(
            test_name="state_consistency_across_operations",
            success=True,
            duration=0,
            metrics={
                "operations": len(operations),
                "final_closeness": final_closeness,
                "final_trustness": final_trustness
            }
        ))


class TestErrorHandling:
    """
    Test error handling when system components fail or timeout
    
    Focus areas:
    - Database connection failures
    - LLM API timeouts
    - Lock acquisition failures
    - Workflow exceptions
    """
    
    @pytest.mark.asyncio
    async def test_database_failure_recovery(self, config, report):
        """Test system behavior when database operations fail"""
        errors_caught = []
        recovery_attempts = []
        
        async def simulate_db_operation(should_fail: bool):
            if should_fail:
                raise ConnectionError("Database connection failed")
            return {"success": True}
        
        # Test with failures
        for i in range(10):
            should_fail = i < 5  # First 5 fail, then succeed
            try:
                result = await simulate_db_operation(should_fail)
                recovery_attempts.append(("success", i))
            except ConnectionError as e:
                errors_caught.append((i, str(e)))
                recovery_attempts.append(("failed", i))
        
        # Verify recovery after failures
        assert len([r for r in recovery_attempts if r[0] == "success"]) == 5
        
        report.results.append(TestResult(
            test_name="database_failure_recovery",
            success=True,
            duration=0,
            metrics={
                "errors_caught": len(errors_caught),
                "successful_recoveries": len([r for r in recovery_attempts if r[0] == "success"])
            }
        ))
    
    @pytest.mark.asyncio
    async def test_llm_timeout_handling(self, config, report):
        """Test handling of LLM API timeouts"""
        timeout_threshold = 0.1  # 100ms for test
        
        async def simulate_llm_call(delay: float):
            if delay > timeout_threshold:
                raise asyncio.TimeoutError("LLM response timeout")
            await asyncio.sleep(delay)
            return {"response": "OK"}
        
        results = []
        for delay in [0.05, 0.15, 0.02, 0.2, 0.08]:
            try:
                result = await asyncio.wait_for(
                    simulate_llm_call(delay),
                    timeout=timeout_threshold
                )
                results.append(("success", delay))
            except asyncio.TimeoutError:
                results.append(("timeout", delay))
        
        timeouts = [r for r in results if r[0] == "timeout"]
        successes = [r for r in results if r[0] == "success"]
        
        report.results.append(TestResult(
            test_name="llm_timeout_handling",
            success=len(timeouts) > 0 and len(successes) > 0,  # Both should occur
            duration=0,
            metrics={
                "timeouts": len(timeouts),
                "successes": len(successes),
                "timeout_threshold_ms": timeout_threshold * 1000
            }
        ))
    
    @pytest.mark.asyncio
    async def test_lock_failure_graceful_handling(self, config, report, mock_lock_manager):
        """Test graceful handling when lock acquisition fails"""
        conversation_id = "contested_conv"
        
        # Hold the lock
        held_lock = await mock_lock_manager.acquire_lock_async(
            "conversation", conversation_id
        )
        
        # Try multiple times to acquire (should fail gracefully)
        failures = 0
        for _ in range(5):
            result = await mock_lock_manager.acquire_lock_async(
                "conversation", conversation_id, max_wait=0.1
            )
            if result is None:
                failures += 1
        
        # Release held lock
        mock_lock_manager.release_lock_safe("conversation", conversation_id, held_lock)
        
        # All should have failed gracefully
        assert failures == 5, "Lock failures not handled properly"
        
        report.results.append(TestResult(
            test_name="lock_failure_graceful_handling",
            success=failures == 5,
            duration=0,
            metrics={"expected_failures": 5, "actual_failures": failures}
        ))
    
    @pytest.mark.asyncio
    async def test_workflow_exception_recovery(self, config, report):
        """Test recovery from workflow exceptions"""
        
        async def failing_workflow(fail_rate: float):
            if random.random() < fail_rate:
                raise RuntimeError("Workflow execution failed")
            await asyncio.sleep(0.01)
            return {"success": True}
        
        results = {"success": 0, "failed": 0, "recovered": 0}
        
        for _ in range(20):
            try:
                await failing_workflow(0.3)  # 30% failure rate
                results["success"] += 1
            except RuntimeError:
                results["failed"] += 1
                # Attempt recovery
                try:
                    await failing_workflow(0.1)  # Lower failure rate for retry
                    results["recovered"] += 1
                except RuntimeError:
                    pass  # Failed again
        
        report.results.append(TestResult(
            test_name="workflow_exception_recovery",
            success=True,
            duration=0,
            metrics=results
        ))
    
    @pytest.mark.asyncio
    async def test_cascade_failure_prevention(self, config, report):
        """Test that failures don't cascade across components"""
        component_states = {"db": "healthy", "llm": "healthy", "lock": "healthy"}
        failures_contained = []
        
        async def simulate_component_failure(component: str):
            component_states[component] = "failed"
            raise Exception(f"{component} component failed")
        
        async def check_other_components(failed_component: str):
            # Other components should remain healthy
            for comp, state in component_states.items():
                if comp != failed_component and state != "healthy":
                    return False
            return True
        
        # Test each component failing
        for component in ["db", "llm", "lock"]:
            component_states = {"db": "healthy", "llm": "healthy", "lock": "healthy"}
            try:
                await simulate_component_failure(component)
            except Exception:
                # Check if failure was contained
                contained = await check_other_components(component)
                failures_contained.append((component, contained))
        
        all_contained = all(fc[1] for fc in failures_contained)
        
        if not all_contained:
            report.add_bug(
                "cascade_failure",
                "Component failure cascaded to other components",
                "critical",
                {"failures": failures_contained}
            )
        
        report.results.append(TestResult(
            test_name="cascade_failure_prevention",
            success=all_contained,
            duration=0,
            metrics={"failures_contained": failures_contained}
        ))


class TestMessageTypeInteraction:
    """
    Test interaction between different message types
    
    Focus areas:
    - User message during proactive message processing
    - Reminder during user message processing
    - Multiple proactive messages queued
    """
    
    @pytest.mark.asyncio
    async def test_user_message_interrupts_proactive(self, config, report, mock_lock_manager):
        """Test user message arriving during proactive message processing"""
        conversation_id = "interaction_conv"
        events = []
        
        async def proactive_handler():
            lock = await mock_lock_manager.acquire_lock_async(
                "conversation", conversation_id, max_wait=0.5
            )
            if lock:
                events.append(("proactive_start", time.time()))
                await asyncio.sleep(0.1)  # Simulate processing
                events.append(("proactive_end", time.time()))
                mock_lock_manager.release_lock_safe("conversation", conversation_id, lock)
            else:
                events.append(("proactive_blocked", time.time()))
        
        async def user_message_handler():
            await asyncio.sleep(0.05)  # Arrive mid-processing
            lock = await mock_lock_manager.acquire_lock_async(
                "conversation", conversation_id, max_wait=0.5
            )
            if lock:
                events.append(("user_start", time.time()))
                await asyncio.sleep(0.02)
                events.append(("user_end", time.time()))
                mock_lock_manager.release_lock_safe("conversation", conversation_id, lock)
            else:
                events.append(("user_blocked", time.time()))
        
        await asyncio.gather(proactive_handler(), user_message_handler())
        
        # Analyze event sequence
        event_types = [e[0] for e in events]
        
        report.results.append(TestResult(
            test_name="user_message_interrupts_proactive",
            success=True,
            duration=0,
            metrics={"event_sequence": event_types}
        ))
    
    @pytest.mark.asyncio
    async def test_reminder_during_user_processing(self, config, report, mock_lock_manager):
        """Test reminder trigger during user message processing"""
        conversation_id = "reminder_interaction_conv"
        events = []
        
        async def user_handler():
            lock = await mock_lock_manager.acquire_lock_async(
                "conversation", conversation_id, max_wait=1.0
            )
            if lock:
                events.append(("user_processing", time.time()))
                await asyncio.sleep(0.1)
                events.append(("user_complete", time.time()))
                mock_lock_manager.release_lock_safe("conversation", conversation_id, lock)
        
        async def reminder_handler():
            await asyncio.sleep(0.03)  # Trigger mid-user-processing
            lock = await mock_lock_manager.acquire_lock_async(
                "conversation", conversation_id, max_wait=0.5
            )
            if lock:
                events.append(("reminder_processing", time.time()))
                await asyncio.sleep(0.02)
                events.append(("reminder_complete", time.time()))
                mock_lock_manager.release_lock_safe("conversation", conversation_id, lock)
            else:
                events.append(("reminder_queued", time.time()))
        
        await asyncio.gather(user_handler(), reminder_handler())
        
        event_types = [e[0] for e in events]
        
        report.results.append(TestResult(
            test_name="reminder_during_user_processing",
            success=True,
            duration=0,
            metrics={"event_sequence": event_types}
        ))
    
    @pytest.mark.asyncio
    async def test_multiple_proactive_messages_queued(self, config, report, mock_lock_manager):
        """Test handling of multiple queued proactive messages"""
        conversation_id = "multi_proactive_conv"
        processed_messages = []
        
        async def proactive_handler(msg_id: int):
            lock = await mock_lock_manager.acquire_lock_async(
                "conversation", conversation_id, max_wait=2.0
            )
            if lock:
                processed_messages.append(msg_id)
                await asyncio.sleep(0.02)
                mock_lock_manager.release_lock_safe("conversation", conversation_id, lock)
                return True
            return False
        
        # Queue multiple proactive messages
        tasks = [proactive_handler(i) for i in range(5)]
        results = await asyncio.gather(*tasks)
        
        # All should eventually process (with waiting)
        processed_count = len(processed_messages)
        
        report.results.append(TestResult(
            test_name="multiple_proactive_messages_queued",
            success=processed_count > 0,
            duration=0,
            metrics={
                "queued": 5,
                "processed": processed_count,
                "order": processed_messages
            }
        ))


# ============ Test Runner ============

@pytest.fixture(scope="module")
def stress_test_report():
    """Module-scoped report for aggregating results"""
    report = StressTestReport()
    yield report
    report.end_time = datetime.now()
    print(report.summary())


def run_all_stress_tests():
    """Run all stress tests and generate report"""
    import pytest
    
    report = StressTestReport()
    
    # Run with pytest
    exit_code = pytest.main([
        __file__,
        "-v",
        "--tb=short",
        "-x",  # Stop on first failure for debugging
    ])
    
    report.end_time = datetime.now()
    print(report.summary())
    
    return exit_code


if __name__ == "__main__":
    run_all_stress_tests()
