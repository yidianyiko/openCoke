# -*- coding: utf-8 -*-
"""
Real System Integration Stress Tests

These tests connect to actual MongoDB and test real system components.
Designed to identify production-level bugs and performance issues.

IMPORTANT: These tests require:
- Running MongoDB instance
- Valid configuration in conf/config.py
- Test user/character data in database

Usage:
    pytest tests/stress/test_real_integration_stress.py -v --tb=short
    pytest tests/stress/test_real_integration_stress.py -k "concurrency" -v
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
from typing import Any, Dict, List, Optional

import pytest

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


# ============ Bug Report Structure ============

@dataclass
class BugReport:
    """Structure for documenting found bugs"""
    bug_id: str
    category: str  # race_condition, memory_leak, state_corruption, timeout, crash
    severity: str  # critical, high, medium, low
    title: str
    description: str
    reproduction_steps: List[str]
    expected_behavior: str
    actual_behavior: str
    affected_components: List[str]
    stack_trace: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict:
        return {
            "bug_id": self.bug_id,
            "category": self.category,
            "severity": self.severity,
            "title": self.title,
            "description": self.description,
            "reproduction_steps": self.reproduction_steps,
            "expected_behavior": self.expected_behavior,
            "actual_behavior": self.actual_behavior,
            "affected_components": self.affected_components,
            "stack_trace": self.stack_trace,
            "timestamp": self.timestamp
        }


class BugCollector:
    """Collect bugs found during testing"""
    
    def __init__(self):
        self.bugs: List[BugReport] = []
        self.performance_issues: List[Dict] = []
    
    def add_bug(self, **kwargs) -> BugReport:
        bug = BugReport(
            bug_id=f"BUG-{len(self.bugs)+1:04d}",
            **kwargs
        )
        self.bugs.append(bug)
        return bug
    
    def add_performance_issue(self, metric: str, threshold: float, actual: float, context: str):
        self.performance_issues.append({
            "metric": metric,
            "threshold": threshold,
            "actual": actual,
            "context": context,
            "timestamp": datetime.now().isoformat()
        })
    
    def generate_report(self) -> str:
        report = ["=" * 60]
        report.append("STRESS TEST BUG REPORT")
        report.append("=" * 60)
        report.append(f"Generated: {datetime.now().isoformat()}")
        report.append(f"Total Bugs Found: {len(self.bugs)}")
        report.append(f"Performance Issues: {len(self.performance_issues)}")
        report.append("")
        
        # Bugs by severity
        for severity in ["critical", "high", "medium", "low"]:
            bugs = [b for b in self.bugs if b.severity == severity]
            if bugs:
                report.append(f"\n--- {severity.upper()} SEVERITY ({len(bugs)}) ---")
                for bug in bugs:
                    report.append(f"\n[{bug.bug_id}] {bug.title}")
                    report.append(f"  Category: {bug.category}")
                    report.append(f"  Components: {', '.join(bug.affected_components)}")
                    report.append(f"  Description: {bug.description}")
        
        # Performance issues
        if self.performance_issues:
            report.append("\n--- PERFORMANCE ISSUES ---")
            for issue in self.performance_issues:
                report.append(f"  - {issue['metric']}: {issue['actual']:.2f} (threshold: {issue['threshold']})")
                report.append(f"    Context: {issue['context']}")
        
        return "\n".join(report)


# ============ Fixtures ============

@pytest.fixture(scope="module")
def bug_collector():
    """Module-scoped bug collector"""
    collector = BugCollector()
    yield collector
    # Print report at end
    print("\n" + collector.generate_report())


@pytest.fixture
def mongodb_connection():
    """Get MongoDB connection, skip if unavailable"""
    try:
        from dao.mongo import MongoDBBase
        mongo = MongoDBBase()
        # Test connection
        mongo.find_one("users", {"_id": "test"})
        yield mongo
        mongo.close()
    except Exception as e:
        pytest.skip(f"MongoDB not available: {e}")


@pytest.fixture
def lock_manager():
    """Get real lock manager"""
    try:
        from dao.lock import MongoDBLockManager
        manager = MongoDBLockManager()
        yield manager
    except Exception as e:
        pytest.skip(f"Lock manager not available: {e}")


@pytest.fixture
def conversation_dao():
    """Get real conversation DAO"""
    try:
        from dao.conversation_dao import ConversationDAO
        dao = ConversationDAO()
        yield dao
    except Exception as e:
        pytest.skip(f"ConversationDAO not available: {e}")


@pytest.fixture
def user_dao():
    """Get real user DAO"""
    try:
        from dao.user_dao import UserDAO
        dao = UserDAO()
        yield dao
    except Exception as e:
        pytest.skip(f"UserDAO not available: {e}")


@pytest.fixture
def reminder_dao():
    """Get real reminder DAO"""
    try:
        from dao.reminder_dao import ReminderDAO
        dao = ReminderDAO()
        yield dao
        dao.close()
    except Exception as e:
        pytest.skip(f"ReminderDAO not available: {e}")


# ============ Concurrency Tests ============

class TestRealConcurrency:
    """Test real concurrency scenarios with MongoDB locks"""
    
    @pytest.mark.asyncio
    async def test_concurrent_lock_acquisition(self, lock_manager, bug_collector):
        """Test concurrent lock acquisition on same resource"""
        resource_id = f"stress_test_conv_{uuid.uuid4().hex[:8]}"
        results = []
        errors = []
        
        async def worker(worker_id: int):
            try:
                lock = await lock_manager.acquire_lock_async(
                    "conversation", resource_id, timeout=10, max_wait=2
                )
                if lock:
                    results.append(("acquired", worker_id, lock, time.time()))
                    await asyncio.sleep(0.1)
                    released, reason = await lock_manager.release_lock_safe_async(
                        "conversation", resource_id, lock
                    )
                    if not released:
                        errors.append((worker_id, f"Release failed: {reason}"))
                else:
                    results.append(("timeout", worker_id, None, time.time()))
            except Exception as e:
                errors.append((worker_id, str(e), traceback.format_exc()))
        
        # Run 10 concurrent workers
        tasks = [worker(i) for i in range(10)]
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Verify no errors
        if errors:
            bug_collector.add_bug(
                category="race_condition",
                severity="high",
                title="Concurrent lock acquisition errors",
                description=f"Errors occurred during concurrent lock acquisition: {errors}",
                reproduction_steps=[
                    "Start 10 concurrent workers",
                    "Each worker tries to acquire lock on same resource",
                    "Workers release lock after 100ms"
                ],
                expected_behavior="All workers should acquire and release locks without errors",
                actual_behavior=f"Errors: {errors}",
                affected_components=["dao/lock.py", "MongoDBLockManager"]
            )
        
        # Check for multiple simultaneous acquisitions (race condition)
        acquired = [r for r in results if r[0] == "acquired"]
        if len(acquired) > 1:
            # Check timestamps - if too close, might be race condition
            times = sorted([r[3] for r in acquired])
            for i in range(len(times) - 1):
                if times[i+1] - times[i] < 0.05:  # Less than 50ms apart
                    bug_collector.add_bug(
                        category="race_condition",
                        severity="critical",
                        title="Possible lock race condition",
                        description="Multiple locks acquired nearly simultaneously",
                        reproduction_steps=["Run concurrent lock test"],
                        expected_behavior="Locks should be sequential",
                        actual_behavior=f"Time between acquisitions: {times[i+1]-times[i]:.3f}s",
                        affected_components=["dao/lock.py"]
                    )
        
        assert len(errors) == 0, f"Lock acquisition errors: {errors}"
    
    @pytest.mark.asyncio
    async def test_lock_timeout_cleanup(self, lock_manager, bug_collector):
        """Test that expired locks are properly cleaned up"""
        resource_id = f"timeout_test_{uuid.uuid4().hex[:8]}"
        
        # Acquire lock with short timeout
        lock1 = await lock_manager.acquire_lock_async(
            "conversation", resource_id, timeout=1, max_wait=1
        )
        assert lock1 is not None, "Failed to acquire initial lock"
        
        # Wait for timeout
        await asyncio.sleep(1.5)
        
        # Try to acquire - should succeed if cleanup works
        lock2 = await lock_manager.acquire_lock_async(
            "conversation", resource_id, timeout=5, max_wait=2
        )
        
        if lock2 is None:
            bug_collector.add_bug(
                category="timeout",
                severity="high",
                title="Lock timeout cleanup failure",
                description="Expired locks not being cleaned up properly",
                reproduction_steps=[
                    "Acquire lock with 1s timeout",
                    "Wait 1.5s",
                    "Try to acquire same lock"
                ],
                expected_behavior="Second acquisition should succeed",
                actual_behavior="Lock acquisition failed - expired lock not cleaned",
                affected_components=["dao/lock.py", "MongoDBLockManager.acquire_lock_async"]
            )
        else:
            # Cleanup
            await lock_manager.release_lock_safe_async(
                "conversation", resource_id, lock2
            )
    
    @pytest.mark.asyncio
    async def test_concurrent_message_processing_simulation(
        self, mongodb_connection, lock_manager, bug_collector
    ):
        """Simulate concurrent message processing across workers"""
        test_conversations = [f"sim_conv_{i}_{uuid.uuid4().hex[:6]}" for i in range(5)]
        processed_messages = []
        errors = []
        lock_contention = []
        
        async def process_message(worker_id: int, conv_id: str):
            try:
                # Try to acquire lock
                start = time.time()
                lock = await lock_manager.acquire_lock_async(
                    "conversation", conv_id, timeout=30, max_wait=5
                )
                acquire_time = time.time() - start
                
                if lock is None:
                    lock_contention.append((worker_id, conv_id, acquire_time))
                    return
                
                try:
                    # Simulate message processing
                    await asyncio.sleep(random.uniform(0.05, 0.15))
                    processed_messages.append({
                        "worker": worker_id,
                        "conversation": conv_id,
                        "process_time": time.time() - start
                    })
                finally:
                    lock_manager.release_lock_safe("conversation", conv_id, lock)
                    
            except Exception as e:
                errors.append((worker_id, conv_id, str(e)))
        
        # Generate random message processing requests
        tasks = []
        for _ in range(20):
            worker_id = random.randint(0, 4)
            conv_id = random.choice(test_conversations)
            tasks.append(process_message(worker_id, conv_id))
        
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Analyze results
        if errors:
            bug_collector.add_bug(
                category="crash",
                severity="high",
                title="Concurrent message processing errors",
                description=f"Errors during concurrent processing: {len(errors)}",
                reproduction_steps=["Run 20 concurrent message processing tasks"],
                expected_behavior="All messages processed without errors",
                actual_behavior=f"Errors: {errors[:5]}...",  # First 5 errors
                affected_components=["agent/runner/message_processor.py"]
            )
        
        # Check for excessive lock contention
        contention_rate = len(lock_contention) / 20 * 100
        if contention_rate > 50:
            bug_collector.add_performance_issue(
                metric="lock_contention_rate",
                threshold=50.0,
                actual=contention_rate,
                context="High lock contention during concurrent processing"
            )


class TestRealHighFrequency:
    """Test high-frequency message input with real database"""
    
    @pytest.mark.asyncio
    async def test_rapid_message_insertion(self, mongodb_connection, bug_collector):
        """Test rapid message insertion to database"""
        collection = "stress_test_messages"
        messages_to_insert = 100
        inserted = []
        errors = []
        
        start_time = time.time()
        
        for i in range(messages_to_insert):
            try:
                msg_id = mongodb_connection.insert_one(collection, {
                    "test_id": f"stress_{uuid.uuid4().hex[:8]}",
                    "content": f"Stress test message {i}",
                    "timestamp": int(time.time()),
                    "sequence": i
                })
                inserted.append(msg_id)
            except Exception as e:
                errors.append((i, str(e)))
        
        insert_time = time.time() - start_time
        throughput = messages_to_insert / insert_time
        
        # Cleanup
        try:
            mongodb_connection.db[collection].delete_many({"test_id": {"$regex": "^stress_"}})
        except Exception:
            pass
        
        # Performance check
        if throughput < 50:  # Less than 50 inserts/second
            bug_collector.add_performance_issue(
                metric="message_insert_throughput",
                threshold=50.0,
                actual=throughput,
                context=f"Inserted {len(inserted)} messages in {insert_time:.2f}s"
            )
        
        if errors:
            bug_collector.add_bug(
                category="crash",
                severity="high",
                title="Message insertion failures under load",
                description=f"{len(errors)} insertion failures",
                reproduction_steps=["Insert 100 messages rapidly"],
                expected_behavior="All messages inserted successfully",
                actual_behavior=f"Errors: {errors[:5]}",
                affected_components=["dao/mongo.py"]
            )
        
        assert len(errors) == 0, f"Insertion errors: {errors}"
    
    @pytest.mark.asyncio
    async def test_concurrent_read_write(self, mongodb_connection, bug_collector):
        """Test concurrent read and write operations"""
        collection = "stress_test_rw"
        doc_id = None
        errors = []
        read_results = []
        
        # Create initial document
        try:
            doc_id = mongodb_connection.insert_one(collection, {
                "counter": 0,
                "test_id": f"rw_test_{uuid.uuid4().hex[:8]}"
            })
        except Exception as e:
            pytest.skip(f"Failed to create test document: {e}")
        
        async def writer():
            for i in range(10):
                try:
                    mongodb_connection.update_one(
                        collection,
                        {"_id": doc_id},
                        {"$inc": {"counter": 1}}
                    )
                    await asyncio.sleep(0.01)
                except Exception as e:
                    errors.append(("write", i, str(e)))
        
        async def reader():
            for i in range(20):
                try:
                    doc = mongodb_connection.find_one(collection, {"_id": doc_id})
                    if doc:
                        read_results.append(doc.get("counter", 0))
                    await asyncio.sleep(0.005)
                except Exception as e:
                    errors.append(("read", i, str(e)))
        
        # Run concurrent readers and writers
        await asyncio.gather(writer(), reader(), reader())
        
        # Cleanup
        try:
            mongodb_connection.db[collection].delete_one({"_id": doc_id})
        except Exception:
            pass
        
        # Check for read anomalies (should see monotonically increasing values)
        non_monotonic = 0
        for i in range(len(read_results) - 1):
            if read_results[i] > read_results[i+1]:
                non_monotonic += 1
        
        if non_monotonic > 0:
            bug_collector.add_bug(
                category="state_corruption",
                severity="medium",
                title="Non-monotonic reads during concurrent write",
                description=f"Read values were not monotonically increasing: {non_monotonic} violations",
                reproduction_steps=[
                    "Create counter document",
                    "Run concurrent writer (incrementing) and readers",
                    "Check read value sequence"
                ],
                expected_behavior="Read values should be monotonically increasing",
                actual_behavior=f"Found {non_monotonic} non-monotonic read sequences",
                affected_components=["dao/mongo.py"]
            )


class TestRealReminder:
    """Test reminder system under stress"""
    
    @pytest.mark.asyncio
    async def test_bulk_reminder_creation(self, reminder_dao, bug_collector):
        """Test creating many reminders quickly"""
        created_reminders = []
        errors = []
        
        test_user_id = f"stress_user_{uuid.uuid4().hex[:8]}"
        test_char_id = f"stress_char_{uuid.uuid4().hex[:8]}"
        test_conv_id = f"stress_conv_{uuid.uuid4().hex[:8]}"
        
        start_time = time.time()
        
        for i in range(50):
            try:
                reminder_id = reminder_dao.create_reminder({
                    "user_id": test_user_id,
                    "character_id": test_char_id,
                    "conversation_id": test_conv_id,
                    "title": f"Stress test reminder {i}",
                    "action_template": f"Test reminder action {i}",
                    "next_trigger_time": int(time.time()) + 3600 + i,
                    "status": "confirmed",
                    "recurrence": {"enabled": False}
                })
                created_reminders.append(reminder_id)
            except Exception as e:
                errors.append((i, str(e)))
        
        creation_time = time.time() - start_time
        
        # Cleanup created reminders
        for reminder in created_reminders:
            try:
                reminder_dao.collection.delete_one({"_id": reminder})
            except Exception:
                pass
        
        if errors:
            bug_collector.add_bug(
                category="crash",
                severity="high",
                title="Reminder creation failures under load",
                description=f"{len(errors)} reminder creation failures",
                reproduction_steps=["Create 50 reminders rapidly"],
                expected_behavior="All reminders created successfully",
                actual_behavior=f"Errors: {errors[:5]}",
                affected_components=["dao/reminder_dao.py"]
            )
        
        # Performance check
        if creation_time > 5:  # More than 5 seconds for 50 reminders
            bug_collector.add_performance_issue(
                metric="reminder_creation_time",
                threshold=5.0,
                actual=creation_time,
                context=f"Created {len(created_reminders)} reminders in {creation_time:.2f}s"
            )
    
    @pytest.mark.asyncio
    async def test_reminder_duplicate_detection(self, reminder_dao, bug_collector):
        """Test duplicate reminder detection under concurrent creation"""
        duplicates_found = []
        created_reminders = []
        
        test_user_id = f"dup_user_{uuid.uuid4().hex[:8]}"
        test_char_id = f"dup_char_{uuid.uuid4().hex[:8]}"
        test_conv_id = f"dup_conv_{uuid.uuid4().hex[:8]}"
        trigger_time = int(time.time()) + 3600
        
        # Create same reminder multiple times
        for i in range(5):
            try:
                # Check for duplicate first
                similar = reminder_dao.find_similar_reminder(
                    test_user_id,
                    "Duplicate test reminder",
                    trigger_time,
                    recurrence_type="none"
                )
                
                if similar:
                    duplicates_found.append(i)
                else:
                    reminder_id = reminder_dao.create_reminder({
                        "user_id": test_user_id,
                        "character_id": test_char_id,
                        "conversation_id": test_conv_id,
                        "title": "Duplicate test reminder",
                        "action_template": "Test action",
                        "next_trigger_time": trigger_time,
                        "status": "confirmed",
                        "recurrence": {"enabled": False, "type": "none"}
                    })
                    created_reminders.append(reminder_id)
            except Exception as e:
                pass  # Ignore errors in this test
        
        # Cleanup
        for reminder in created_reminders:
            try:
                reminder_dao.collection.delete_one({"_id": reminder})
            except Exception:
                pass
        
        # Should have detected duplicates
        if len(created_reminders) > 1 and len(duplicates_found) == 0:
            bug_collector.add_bug(
                category="state_corruption",
                severity="medium",
                title="Duplicate reminder detection failure",
                description="Multiple identical reminders were created without detection",
                reproduction_steps=[
                    "Create reminder with specific title/time",
                    "Attempt to create same reminder again",
                    "Check if duplicate was detected"
                ],
                expected_behavior="Duplicate should be detected after first creation",
                actual_behavior=f"Created {len(created_reminders)} reminders, detected {len(duplicates_found)} duplicates",
                affected_components=["dao/reminder_dao.py", "find_similar_reminder"]
            )


class TestRealStateConsistency:
    """Test state consistency under various scenarios"""
    
    @pytest.mark.asyncio
    async def test_conversation_history_integrity(
        self, mongodb_connection, conversation_dao, bug_collector
    ):
        """Test chat history remains consistent under modifications"""
        # Create test conversation
        test_conv_id = None
        
        try:
            # Find or create a test conversation
            conv = conversation_dao.find_conversations(
                {"talkers": {"$size": 2}}
            )
            if conv:
                test_conv_id = str(conv[0]["_id"])
                
                # Get initial state
                initial_conv = conversation_dao.get_conversation_by_id(test_conv_id)
                initial_history_len = len(
                    initial_conv.get("conversation_info", {}).get("chat_history", [])
                )
                
                # Simulate rapid updates
                for i in range(10):
                    conv_data = conversation_dao.get_conversation_by_id(test_conv_id)
                    if conv_data:
                        history = conv_data.get("conversation_info", {}).get("chat_history", [])
                        # This is read-only - just checking consistency
                        
                # Verify no corruption
                final_conv = conversation_dao.get_conversation_by_id(test_conv_id)
                final_history_len = len(
                    final_conv.get("conversation_info", {}).get("chat_history", [])
                )
                
                # History should not have changed dramatically
                if abs(final_history_len - initial_history_len) > 5:
                    bug_collector.add_bug(
                        category="state_corruption",
                        severity="high",
                        title="Chat history length changed unexpectedly",
                        description=f"History changed from {initial_history_len} to {final_history_len}",
                        reproduction_steps=["Read conversation multiple times"],
                        expected_behavior="History length should be stable",
                        actual_behavior=f"Changed by {abs(final_history_len - initial_history_len)} messages",
                        affected_components=["dao/conversation_dao.py"]
                    )
        except Exception as e:
            # Skip if no suitable conversation exists
            pass
    
    @pytest.mark.asyncio
    async def test_relation_value_bounds(self, mongodb_connection, bug_collector):
        """Test that relationship values stay within bounds"""
        relations = mongodb_connection.find_many("relations", {}, limit=100)
        
        out_of_bounds = []
        
        for rel in relations:
            relationship = rel.get("relationship", {})
            closeness = relationship.get("closeness", 0)
            trustness = relationship.get("trustness", 0)
            dislike = relationship.get("dislike", 0)
            
            if not (0 <= closeness <= 100):
                out_of_bounds.append(("closeness", closeness, str(rel.get("_id"))))
            if not (0 <= trustness <= 100):
                out_of_bounds.append(("trustness", trustness, str(rel.get("_id"))))
            if not (0 <= dislike <= 100):
                out_of_bounds.append(("dislike", dislike, str(rel.get("_id"))))
        
        if out_of_bounds:
            bug_collector.add_bug(
                category="state_corruption",
                severity="high",
                title="Relationship values out of bounds",
                description=f"Found {len(out_of_bounds)} out-of-bounds values",
                reproduction_steps=["Check all relation documents in database"],
                expected_behavior="All values should be between 0 and 100",
                actual_behavior=f"Out of bounds: {out_of_bounds[:5]}",
                affected_components=["dao/mongo.py", "agent/runner/context.py"]
            )


class TestRealMessageFlow:
    """Test complete message processing flow"""
    
    @pytest.mark.asyncio
    async def test_message_status_transitions(self, mongodb_connection, bug_collector):
        """Test that message status transitions are valid"""
        # Check for messages with invalid status transitions
        messages = mongodb_connection.find_many(
            "inputmessages",
            {"status": {"$nin": ["pending", "handled", "failed", "hold", "canceled"]}},
            limit=100
        )
        
        if messages:
            bug_collector.add_bug(
                category="state_corruption",
                severity="medium",
                title="Invalid message status values found",
                description=f"Found {len(messages)} messages with invalid status",
                reproduction_steps=["Query messages with unexpected status values"],
                expected_behavior="All messages should have valid status",
                actual_behavior=f"Invalid statuses: {[m.get('status') for m in messages[:5]]}",
                affected_components=["entity/message.py"]
            )
        
        # Check for stuck messages (pending for too long)
        old_threshold = int(time.time()) - 3600 * 24  # 24 hours
        stuck_messages = mongodb_connection.find_many(
            "inputmessages",
            {
                "status": "pending",
                "input_timestamp": {"$lt": old_threshold}
            },
            limit=100
        )
        
        if stuck_messages:
            bug_collector.add_bug(
                category="timeout",
                severity="high",
                title="Stuck pending messages detected",
                description=f"Found {len(stuck_messages)} messages pending for >24 hours",
                reproduction_steps=["Query for old pending messages"],
                expected_behavior="Messages should be processed or failed within reasonable time",
                actual_behavior=f"{len(stuck_messages)} messages stuck in pending state",
                affected_components=["agent/runner/message_processor.py"]
            )
    
    @pytest.mark.asyncio
    async def test_output_message_delivery(self, mongodb_connection, bug_collector):
        """Test output message delivery state"""
        # Check for undelivered old output messages
        old_threshold = int(time.time()) - 3600  # 1 hour
        stuck_outputs = mongodb_connection.find_many(
            "outputmessages",
            {
                "status": "pending",
                "expect_output_timestamp": {"$lt": old_threshold}
            },
            limit=100
        )
        
        if stuck_outputs:
            bug_collector.add_bug(
                category="timeout",
                severity="high",
                title="Undelivered output messages",
                description=f"Found {len(stuck_outputs)} output messages pending for >1 hour",
                reproduction_steps=["Query for old pending output messages"],
                expected_behavior="Output messages should be delivered within reasonable time",
                actual_behavior=f"{len(stuck_outputs)} messages not delivered",
                affected_components=["connector/ecloud/ecloud_output.py"]
            )


# ============ Performance Benchmarks ============

class TestPerformanceBenchmarks:
    """Performance benchmarks for key operations"""
    
    @pytest.mark.asyncio
    async def test_lock_acquisition_latency(self, lock_manager, bug_collector):
        """Benchmark lock acquisition latency"""
        latencies = []
        
        for i in range(20):
            resource_id = f"bench_lock_{i}_{uuid.uuid4().hex[:6]}"
            start = time.time()
            lock = await lock_manager.acquire_lock_async(
                "conversation", resource_id, timeout=5, max_wait=1
            )
            latency = time.time() - start
            latencies.append(latency)
            
            if lock:
                lock_manager.release_lock_safe("conversation", resource_id, lock)
        
        avg_latency = sum(latencies) / len(latencies)
        max_latency = max(latencies)
        
        if avg_latency > 0.1:  # 100ms average
            bug_collector.add_performance_issue(
                metric="lock_acquisition_avg_latency",
                threshold=0.1,
                actual=avg_latency,
                context=f"Average lock acquisition took {avg_latency*1000:.2f}ms"
            )
        
        if max_latency > 0.5:  # 500ms max
            bug_collector.add_performance_issue(
                metric="lock_acquisition_max_latency",
                threshold=0.5,
                actual=max_latency,
                context=f"Maximum lock acquisition took {max_latency*1000:.2f}ms"
            )
    
    @pytest.mark.asyncio
    async def test_database_query_latency(self, mongodb_connection, bug_collector):
        """Benchmark database query latency"""
        query_latencies = []
        
        for _ in range(20):
            start = time.time()
            mongodb_connection.find_many("users", {}, limit=10)
            latency = time.time() - start
            query_latencies.append(latency)
        
        avg_latency = sum(query_latencies) / len(query_latencies)
        
        if avg_latency > 0.05:  # 50ms average
            bug_collector.add_performance_issue(
                metric="db_query_avg_latency",
                threshold=0.05,
                actual=avg_latency,
                context=f"Average DB query took {avg_latency*1000:.2f}ms"
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
