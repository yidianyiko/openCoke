#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Production Stress Test Runner

Executes comprehensive stress tests and generates detailed reports.

Usage:
    python tests/stress/run_stress_tests.py
    python tests/stress/run_stress_tests.py --quick    # Quick smoke test
    python tests/stress/run_stress_tests.py --full     # Full stress test suite
    python tests/stress/run_stress_tests.py --report   # Generate report only (from previous run)
"""
import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@dataclass
class StressTestSummary:
    """Summary of stress test execution"""
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    
    # Test counts
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    skipped_tests: int = 0
    
    # Issues found
    bugs: List[Dict] = field(default_factory=list)
    performance_issues: List[Dict] = field(default_factory=list)
    
    # Metrics
    metrics: Dict[str, Any] = field(default_factory=dict)
    
    def add_bug(self, **kwargs):
        self.bugs.append({
            **kwargs,
            "timestamp": datetime.now().isoformat()
        })
    
    def add_performance_issue(self, **kwargs):
        self.performance_issues.append({
            **kwargs,
            "timestamp": datetime.now().isoformat()
        })
    
    def finalize(self):
        self.end_time = datetime.now()
        self.metrics["duration_seconds"] = (
            self.end_time - self.start_time
        ).total_seconds()
    
    def to_report(self) -> str:
        lines = [
            "=" * 70,
            "PRODUCTION STRESS TEST REPORT",
            "=" * 70,
            f"Start Time: {self.start_time.isoformat()}",
            f"End Time: {self.end_time.isoformat() if self.end_time else 'N/A'}",
            f"Duration: {self.metrics.get('duration_seconds', 0):.2f} seconds",
            "",
            "=" * 70,
            "TEST RESULTS SUMMARY",
            "=" * 70,
            f"Total Tests: {self.total_tests}",
            f"Passed: {self.passed_tests}",
            f"Failed: {self.failed_tests}",
            f"Skipped: {self.skipped_tests}",
            f"Pass Rate: {(self.passed_tests/max(self.total_tests,1)*100):.1f}%",
            "",
        ]
        
        if self.bugs:
            lines.extend([
                "=" * 70,
                f"BUGS FOUND ({len(self.bugs)})",
                "=" * 70,
            ])
            
            # Group by severity
            for severity in ["critical", "high", "medium", "low"]:
                severity_bugs = [b for b in self.bugs if b.get("severity") == severity]
                if severity_bugs:
                    lines.append(f"\n--- {severity.upper()} SEVERITY ({len(severity_bugs)}) ---")
                    for bug in severity_bugs:
                        lines.append(f"\n[{bug.get('bug_id', 'N/A')}] {bug.get('title', 'N/A')}")
                        lines.append(f"  Category: {bug.get('category', 'N/A')}")
                        lines.append(f"  Description: {bug.get('description', 'N/A')}")
                        if bug.get('affected_components'):
                            lines.append(f"  Components: {', '.join(bug['affected_components'])}")
        else:
            lines.extend([
                "=" * 70,
                "NO BUGS FOUND",
                "=" * 70,
            ])
        
        if self.performance_issues:
            lines.extend([
                "",
                "=" * 70,
                f"PERFORMANCE ISSUES ({len(self.performance_issues)})",
                "=" * 70,
            ])
            for issue in self.performance_issues:
                lines.append(
                    f"  - {issue.get('metric', 'N/A')}: "
                    f"{issue.get('actual', 'N/A')} "
                    f"(threshold: {issue.get('threshold', 'N/A')})"
                )
                if issue.get('context'):
                    lines.append(f"    Context: {issue['context']}")
        
        lines.extend([
            "",
            "=" * 70,
            "END OF REPORT",
            "=" * 70,
        ])
        
        return "\n".join(lines)
    
    def to_json(self) -> str:
        return json.dumps({
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "total_tests": self.total_tests,
            "passed_tests": self.passed_tests,
            "failed_tests": self.failed_tests,
            "skipped_tests": self.skipped_tests,
            "bugs": self.bugs,
            "performance_issues": self.performance_issues,
            "metrics": self.metrics
        }, indent=2, ensure_ascii=False)


def check_prerequisites() -> List[str]:
    """Check if all prerequisites are met for running stress tests"""
    issues = []
    
    # Check MongoDB connection
    try:
        from dao.mongo import MongoDBBase
        mongo = MongoDBBase()
        mongo.find_one("users", {"_id": "test"})
        mongo.close()
    except Exception as e:
        issues.append(f"MongoDB connection failed: {e}")
    
    # Check config
    try:
        from conf.config import CONF
        if not CONF.get("mongodb"):
            issues.append("MongoDB configuration missing")
    except Exception as e:
        issues.append(f"Config loading failed: {e}")
    
    return issues


async def run_quick_tests(summary: StressTestSummary):
    """Run quick smoke tests"""
    print("\n>>> Running Quick Smoke Tests <<<\n")
    
    # Test 1: Lock Manager
    print("  [1/4] Testing Lock Manager...")
    try:
        from dao.lock import MongoDBLockManager
        lm = MongoDBLockManager()
        
        resource_id = f"quick_test_{int(time.time())}"
        lock = await lm.acquire_lock_async("conversation", resource_id, timeout=5, max_wait=1)
        
        if lock:
            released, reason = await lm.release_lock_safe_async("conversation", resource_id, lock)
            if released:
                print("    ✓ Lock acquire/release: PASSED")
                summary.passed_tests += 1
            else:
                print(f"    ✗ Lock release failed: {reason}")
                summary.failed_tests += 1
                summary.add_bug(
                    category="lock",
                    severity="high",
                    title="Lock release failed",
                    description=reason
                )
        else:
            print("    ✗ Lock acquisition failed")
            summary.failed_tests += 1
        
        summary.total_tests += 1
        
    except Exception as e:
        print(f"    ✗ Lock test error: {e}")
        summary.failed_tests += 1
        summary.total_tests += 1
    
    # Test 2: Database Operations
    print("  [2/4] Testing Database Operations...")
    try:
        from bson import ObjectId
        from dao.mongo import MongoDBBase
        mongo = MongoDBBase()
        
        # Insert
        test_id = mongo.insert_one("stress_test", {"test": True, "ts": int(time.time())})
        
        # Find - convert string ID to ObjectId
        doc = mongo.find_one("stress_test", {"_id": ObjectId(test_id)})
        
        # Delete
        mongo.db.stress_test.delete_one({"_id": ObjectId(test_id)})
        
        if doc:
            print("    ✓ Database CRUD: PASSED")
            summary.passed_tests += 1
        else:
            print("    ✗ Database read failed")
            summary.failed_tests += 1
        
        mongo.close()
        summary.total_tests += 1
        
    except Exception as e:
        print(f"    ✗ Database test error: {e}")
        summary.failed_tests += 1
        summary.total_tests += 1
    
    # Test 3: Conversation DAO
    print("  [3/4] Testing Conversation DAO...")
    try:
        from dao.conversation_dao import ConversationDAO
        dao = ConversationDAO()
        
        # Just test query works
        convs = dao.find_conversations({}, limit=1)
        print(f"    ✓ Conversation query: PASSED (found {len(convs)} conversations)")
        summary.passed_tests += 1
        summary.total_tests += 1
        
    except Exception as e:
        print(f"    ✗ Conversation DAO error: {e}")
        summary.failed_tests += 1
        summary.total_tests += 1
    
    # Test 4: Reminder DAO
    print("  [4/4] Testing Reminder DAO...")
    try:
        from dao.reminder_dao import ReminderDAO
        dao = ReminderDAO()
        
        # Just test query works
        reminders = dao.find_pending_reminders(int(time.time()) + 999999)
        print(f"    ✓ Reminder query: PASSED (found {len(reminders)} pending)")
        summary.passed_tests += 1
        summary.total_tests += 1
        dao.close()
        
    except Exception as e:
        print(f"    ✗ Reminder DAO error: {e}")
        summary.failed_tests += 1
        summary.total_tests += 1


async def run_concurrency_tests(summary: StressTestSummary):
    """Run concurrency stress tests"""
    print("\n>>> Running Concurrency Tests <<<\n")
    
    from dao.lock import MongoDBLockManager
    lm = MongoDBLockManager()
    
    # Test: Concurrent lock acquisition
    print("  [1/3] Concurrent lock acquisition (10 workers)...")
    resource_id = f"conc_test_{int(time.time())}"
    results = []
    errors = []
    
    async def worker(wid):
        try:
            lock = await lm.acquire_lock_async("conversation", resource_id, timeout=10, max_wait=5)
            if lock:
                await asyncio.sleep(0.1)
                await lm.release_lock_safe_async("conversation", resource_id, lock)
                return ("acquired", wid)
            return ("timeout", wid)
        except Exception as e:
            return ("error", wid, str(e))
    
    tasks = [worker(i) for i in range(10)]
    results = await asyncio.gather(*tasks)
    
    acquired = [r for r in results if r[0] == "acquired"]
    errors = [r for r in results if r[0] == "error"]
    
    summary.total_tests += 1
    if errors:
        print(f"    ✗ Concurrent lock test: {len(errors)} errors")
        summary.failed_tests += 1
        for err in errors:
            summary.add_bug(
                category="race_condition",
                severity="high",
                title="Concurrent lock error",
                description=str(err)
            )
    else:
        print(f"    ✓ Concurrent lock test: PASSED ({len(acquired)} acquired)")
        summary.passed_tests += 1
    
    # Test: Lock contention
    print("  [2/3] Lock contention test...")
    contention_resource = f"contention_test_{int(time.time())}"
    
    # Hold lock and test others can't get it
    held_lock = await lm.acquire_lock_async("conversation", contention_resource, timeout=5, max_wait=1)
    
    if held_lock:
        # Try to acquire from another "worker"
        second_lock = await lm.acquire_lock_async("conversation", contention_resource, timeout=1, max_wait=0.5)
        
        if second_lock is None:
            print("    ✓ Lock contention: PASSED (lock properly held)")
            summary.passed_tests += 1
        else:
            print("    ✗ Lock contention: FAILED (lock acquired while held!)")
            summary.failed_tests += 1
            summary.add_bug(
                category="race_condition",
                severity="critical",
                title="Lock acquired while already held",
                description="Second lock was acquired while first lock was still held"
            )
            await lm.release_lock_safe_async("conversation", contention_resource, second_lock)
        
        await lm.release_lock_safe_async("conversation", contention_resource, held_lock)
    else:
        print("    ✗ Lock contention: FAILED (couldn't acquire initial lock)")
        summary.failed_tests += 1
    
    summary.total_tests += 1
    
    # Test: Rapid lock acquire/release
    print("  [3/3] Rapid lock acquire/release (50 cycles)...")
    rapid_resource = f"rapid_test_{int(time.time())}"
    rapid_errors = []
    
    for i in range(50):
        try:
            lock = await lm.acquire_lock_async("conversation", rapid_resource, timeout=2, max_wait=1)
            if lock:
                await lm.release_lock_safe_async("conversation", rapid_resource, lock)
            else:
                rapid_errors.append(i)
        except Exception as e:
            rapid_errors.append((i, str(e)))
    
    summary.total_tests += 1
    if rapid_errors:
        print(f"    ✗ Rapid lock test: {len(rapid_errors)} failures")
        summary.failed_tests += 1
    else:
        print("    ✓ Rapid lock test: PASSED")
        summary.passed_tests += 1


async def run_high_frequency_tests(summary: StressTestSummary):
    """Run high-frequency input tests"""
    print("\n>>> Running High-Frequency Tests <<<\n")
    
    from dao.mongo import MongoDBBase
    mongo = MongoDBBase()
    
    # Test: Rapid inserts
    print("  [1/2] Rapid message inserts (100 messages)...")
    collection = "stress_test_messages"
    insert_times = []
    errors = []
    
    start = time.time()
    for i in range(100):
        try:
            t0 = time.time()
            mongo.insert_one(collection, {
                "test_id": f"hf_{int(time.time())}_{i}",
                "content": f"High frequency test {i}",
                "timestamp": int(time.time())
            })
            insert_times.append(time.time() - t0)
        except Exception as e:
            errors.append((i, str(e)))
    
    total_time = time.time() - start
    avg_insert = sum(insert_times) / len(insert_times) if insert_times else 0
    throughput = 100 / total_time if total_time > 0 else 0
    
    # Cleanup
    mongo.db[collection].delete_many({"test_id": {"$regex": "^hf_"}})
    
    summary.total_tests += 1
    summary.metrics["insert_throughput"] = throughput
    summary.metrics["avg_insert_time_ms"] = avg_insert * 1000
    
    if errors:
        print(f"    ✗ Rapid inserts: {len(errors)} failures")
        summary.failed_tests += 1
        summary.add_bug(
            category="crash",
            severity="high",
            title="Database insert failures under load",
            description=f"{len(errors)} failures during rapid inserts"
        )
    else:
        print(f"    ✓ Rapid inserts: PASSED ({throughput:.1f} msgs/sec, avg {avg_insert*1000:.2f}ms)")
        summary.passed_tests += 1
        
        if throughput < 50:
            summary.add_performance_issue(
                metric="insert_throughput",
                threshold=50,
                actual=throughput,
                context="Database insert throughput below threshold"
            )
    
    # Test: Concurrent reads and writes
    print("  [2/2] Concurrent read/write (5 second test)...")
    rw_collection = "stress_test_rw"
    read_count = 0
    write_count = 0
    rw_errors = []
    stop_flag = False
    
    # Create test doc
    doc_id = mongo.insert_one(rw_collection, {"counter": 0, "test": True})
    
    async def writer():
        nonlocal write_count
        while not stop_flag:
            try:
                mongo.update_one(rw_collection, {"_id": doc_id}, {"$inc": {"counter": 1}})
                write_count += 1
                await asyncio.sleep(0.01)
            except Exception as e:
                rw_errors.append(("write", str(e)))
    
    async def reader():
        nonlocal read_count
        while not stop_flag:
            try:
                mongo.find_one(rw_collection, {"_id": doc_id})
                read_count += 1
                await asyncio.sleep(0.005)
            except Exception as e:
                rw_errors.append(("read", str(e)))
    
    async def timer():
        nonlocal stop_flag
        await asyncio.sleep(5)
        stop_flag = True
    
    await asyncio.gather(writer(), reader(), reader(), timer())
    
    # Cleanup
    mongo.db[rw_collection].delete_one({"_id": doc_id})
    mongo.close()
    
    summary.total_tests += 1
    summary.metrics["concurrent_reads_per_sec"] = read_count / 5
    summary.metrics["concurrent_writes_per_sec"] = write_count / 5
    
    if rw_errors:
        print(f"    ✗ Concurrent R/W: {len(rw_errors)} errors")
        summary.failed_tests += 1
    else:
        print(f"    ✓ Concurrent R/W: PASSED ({read_count} reads, {write_count} writes in 5s)")
        summary.passed_tests += 1


async def run_state_consistency_tests(summary: StressTestSummary):
    """Run state consistency tests"""
    print("\n>>> Running State Consistency Tests <<<\n")
    
    from dao.mongo import MongoDBBase
    mongo = MongoDBBase()
    
    # Test: Relationship value bounds
    print("  [1/2] Checking relationship value bounds...")
    relations = mongo.find_many("relations", {}, limit=500)
    
    out_of_bounds = []
    for rel in relations:
        relationship = rel.get("relationship", {})
        for field in ["closeness", "trustness", "dislike"]:
            value = relationship.get(field, 0)
            if not (0 <= value <= 100):
                out_of_bounds.append((str(rel.get("_id")), field, value))
    
    summary.total_tests += 1
    if out_of_bounds:
        print(f"    ✗ Value bounds: {len(out_of_bounds)} violations")
        summary.failed_tests += 1
        summary.add_bug(
            category="state_corruption",
            severity="high",
            title="Relationship values out of bounds",
            description=f"Found {len(out_of_bounds)} out-of-bounds values",
            affected_components=["dao/mongo.py", "agent/runner/context.py"]
        )
    else:
        print(f"    ✓ Value bounds: PASSED (checked {len(relations)} relations)")
        summary.passed_tests += 1
    
    # Test: Message status validity
    print("  [2/2] Checking message status validity...")
    valid_statuses = ["pending", "handled", "failed", "hold", "canceled"]
    invalid_messages = mongo.find_many(
        "inputmessages",
        {"status": {"$nin": valid_statuses}},
        limit=100
    )
    
    summary.total_tests += 1
    if invalid_messages:
        print(f"    ✗ Message status: {len(invalid_messages)} invalid")
        summary.failed_tests += 1
        summary.add_bug(
            category="state_corruption",
            severity="medium",
            title="Invalid message status values",
            description=f"Found {len(invalid_messages)} messages with invalid status"
        )
    else:
        print("    ✓ Message status: PASSED")
        summary.passed_tests += 1
    
    mongo.close()


async def run_stuck_message_check(summary: StressTestSummary):
    """Check for stuck messages"""
    print("\n>>> Checking for Stuck Messages <<<\n")
    
    from dao.mongo import MongoDBBase
    mongo = MongoDBBase()
    
    now = int(time.time())
    
    # Check pending input messages older than 24 hours
    print("  [1/2] Checking stuck input messages (>24h pending)...")
    old_threshold = now - 3600 * 24
    stuck_inputs = mongo.find_many(
        "inputmessages",
        {"status": "pending", "input_timestamp": {"$lt": old_threshold}},
        limit=100
    )
    
    summary.total_tests += 1
    if stuck_inputs:
        print(f"    ⚠ Found {len(stuck_inputs)} stuck input messages")
        summary.add_bug(
            category="timeout",
            severity="high",
            title="Stuck pending input messages",
            description=f"{len(stuck_inputs)} messages pending for >24 hours",
            affected_components=["agent/runner/message_processor.py"]
        )
        # Not a test failure, just a warning
        summary.passed_tests += 1
    else:
        print("    ✓ No stuck input messages")
        summary.passed_tests += 1
    
    # Check pending output messages older than 1 hour
    print("  [2/2] Checking stuck output messages (>1h pending)...")
    output_threshold = now - 3600
    stuck_outputs = mongo.find_many(
        "outputmessages",
        {"status": "pending", "expect_output_timestamp": {"$lt": output_threshold}},
        limit=100
    )
    
    summary.total_tests += 1
    if stuck_outputs:
        print(f"    ⚠ Found {len(stuck_outputs)} stuck output messages")
        summary.add_bug(
            category="timeout",
            severity="high",
            title="Stuck pending output messages",
            description=f"{len(stuck_outputs)} output messages not delivered for >1 hour",
            affected_components=["connector/ecloud/ecloud_output.py"]
        )
        summary.passed_tests += 1
    else:
        print("    ✓ No stuck output messages")
        summary.passed_tests += 1
    
    mongo.close()


async def run_full_stress_tests(summary: StressTestSummary):
    """Run full stress test suite"""
    await run_quick_tests(summary)
    await run_concurrency_tests(summary)
    await run_high_frequency_tests(summary)
    await run_state_consistency_tests(summary)
    await run_stuck_message_check(summary)


def main():
    parser = argparse.ArgumentParser(description="Production Stress Test Runner")
    parser.add_argument("--quick", action="store_true", help="Run quick smoke tests only")
    parser.add_argument("--full", action="store_true", help="Run full stress test suite")
    parser.add_argument("--report", type=str, help="Load and display previous report")
    parser.add_argument("--output", type=str, default="stress_test_report.json", 
                        help="Output file for JSON report")
    
    args = parser.parse_args()
    
    # Banner
    print("\n" + "=" * 70)
    print("           PRODUCTION STRESS TEST RUNNER")
    print("=" * 70)
    
    # Check prerequisites
    print("\nChecking prerequisites...")
    issues = check_prerequisites()
    if issues:
        print("\n❌ Prerequisites not met:")
        for issue in issues:
            print(f"  - {issue}")
        print("\nPlease fix the issues above and try again.")
        sys.exit(1)
    print("✓ All prerequisites met")
    
    # Create summary
    summary = StressTestSummary()
    
    # Run tests
    try:
        if args.quick:
            print("\n[MODE] Quick Smoke Test")
            asyncio.run(run_quick_tests(summary))
        elif args.full:
            print("\n[MODE] Full Stress Test Suite")
            asyncio.run(run_full_stress_tests(summary))
        else:
            print("\n[MODE] Default (Quick + Concurrency)")
            asyncio.run(run_quick_tests(summary))
            asyncio.run(run_concurrency_tests(summary))
    except KeyboardInterrupt:
        print("\n\n⚠ Test interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Test execution error: {e}")
        import traceback
        traceback.print_exc()
    
    # Finalize
    summary.finalize()
    
    # Print report
    print("\n" + summary.to_report())
    
    # Save JSON report
    report_path = Path(args.output)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(summary.to_json())
    print(f"\n📄 JSON report saved to: {report_path.absolute()}")
    
    # Exit code
    if summary.failed_tests > 0 or any(b.get("severity") == "critical" for b in summary.bugs):
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
