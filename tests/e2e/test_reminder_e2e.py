# -*- coding: utf-8 -*-
"""
提醒功能 E2E 测试执行器

基于 terminal_chat.py 的完整 LLM 链路测试
"""
import json
import sys
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

sys.path.append(".")

from dao.mongo import MongoDBBase
from dao.reminder_dao import ReminderDAO
from dao.user_dao import UserDAO
from util.log_util import get_logger

logger = get_logger(__name__)


class ReminderE2ETestRunner:
    """提醒功能 E2E 测试执行器"""

    def __init__(
        self,
        test_cases_path: str = "tests/e2e/reminder_e2e_cases.json",
        test_cases_path_part2: str = "tests/e2e/reminder_e2e_cases_part2.json",
    ):
        self.mongo = MongoDBBase()
        self.reminder_dao = ReminderDAO()
        self.user_dao = UserDAO()

        # 加载测试用例
        self.test_cases = self._load_test_cases(test_cases_path, test_cases_path_part2)
        self.config = self.test_cases.get("config", {})
        self.user_id = self.test_cases.get("test_user_id")
        self.character_id = self.test_cases.get("character_id")

        # 配置
        self.time_tolerance = self.config.get("time_tolerance_minutes", 1) * 60
        self.response_timeout = self.config.get("response_timeout_seconds", 30)
        self.poll_interval = self.config.get("poll_interval_seconds", 0.5)

        # 测试结果
        self.results: List[Dict] = []
        self.passed = 0
        self.failed = 0
        self.skipped = 0

    def _load_test_cases(self, path1: str, path2: str) -> Dict:
        """加载并合并测试用例"""
        with open(path1, "r", encoding="utf-8") as f:
            data1 = json.load(f)

        try:
            with open(path2, "r", encoding="utf-8") as f:
                data2 = json.load(f)
            # 合并 test_cases
            if "test_cases_continued" in data2:
                data1["test_cases"].extend(data2["test_cases_continued"])
        except FileNotFoundError:
            pass

        return data1

    def send_message(self, text: str) -> int:
        """发送消息到 inputmessages"""
        now = int(time.time())
        message = {
            "input_timestamp": now,
            "handled_timestamp": now,
            "status": "pending",
            "from_user": self.user_id,
            "platform": "wechat",
            "chatroom_name": None,
            "to_user": self.character_id,
            "message_type": "text",
            "message": text,
            "metadata": {},
        }
        self.mongo.insert_one("inputmessages", message)
        logger.info(f"[E2E] Sent message: {text}")
        return now

    def wait_for_response(self, after_timestamp: int) -> Optional[str]:
        """等待 AI 回复"""
        start_time = time.time()
        while time.time() - start_time < self.response_timeout:
            messages = self.mongo.find_many(
                "outputmessages",
                {
                    "from_user": self.character_id,
                    "to_user": self.user_id,
                    "status": "pending",
                    "expect_output_timestamp": {"$gte": after_timestamp - 5},
                },
            )
            for msg in messages:
                content = msg.get("message", "")
                if content:
                    # 标记为已处理
                    msg["status"] = "handled"
                    msg["handled_timestamp"] = int(time.time())
                    self.mongo.update_one(
                        "outputmessages", {"_id": msg["_id"]}, {"$set": msg}
                    )
                    logger.info(f"[E2E] Got response: {content[:100]}...")
                    return content
            time.sleep(self.poll_interval)
        logger.warning("[E2E] Response timeout")
        return None

    def verify_response(self, response: str, expect: Dict) -> bool:
        """验证 AI 回复是否符合预期"""
        if not response:
            return False

        contains_any = expect.get("contains_any", [])
        if contains_any:
            for keyword in contains_any:
                if keyword.lower() in response.lower():
                    return True
            logger.warning(
                f"[E2E] Response doesn't contain any of: {contains_any}"
            )
            return False
        return True

    def verify_db_state(self, expected: Dict, test_start_time: int) -> bool:
        """验证数据库状态"""
        if not expected:
            return True

        # 查询用户的提醒
        reminders = self.reminder_dao.find_reminders_by_user(
            self.user_id, status_list=["active"]
        )

        # 验证提醒是否存在
        if expected.get("reminder_exists"):
            title_contains = expected.get("title_contains", "")
            matching = [r for r in reminders if title_contains in r.get("title", "")]
            if not matching:
                logger.warning(
                    f"[E2E] No reminder found containing '{title_contains}'"
                )
                return False

            # 验证触发时间
            trigger_time_spec = expected.get("trigger_time", {})
            if trigger_time_spec:
                reminder = matching[0]
                trigger_ts = reminder.get("next_trigger_time", 0)
                if not self._verify_trigger_time(trigger_ts, trigger_time_spec, test_start_time):
                    return False

            # 验证周期设置
            recurrence_spec = expected.get("recurrence", {})
            if recurrence_spec:
                reminder = matching[0]
                rec = reminder.get("recurrence", {})
                if recurrence_spec.get("enabled") is not None:
                    if rec.get("enabled") != recurrence_spec["enabled"]:
                        logger.warning(
                            f"[E2E] Recurrence enabled mismatch: expected {recurrence_spec['enabled']}, got {rec.get('enabled')}"
                        )
                        return False
                if recurrence_spec.get("type"):
                    if rec.get("type") != recurrence_spec["type"]:
                        logger.warning(
                            f"[E2E] Recurrence type mismatch: expected {recurrence_spec['type']}, got {rec.get('type')}"
                        )
                        return False

        # 验证提醒不存在
        if expected.get("reminder_not_exists"):
            title_contains = expected.get("title_contains", "")
            matching = [r for r in reminders if title_contains in r.get("title", "")]
            if matching:
                logger.warning(
                    f"[E2E] Reminder still exists containing '{title_contains}'"
                )
                return False

        # 验证没有活跃提醒
        if expected.get("no_active_reminders"):
            if reminders:
                logger.warning(f"[E2E] Still have {len(reminders)} active reminders")
                return False

        # 验证提醒数量
        if expected.get("reminders_count_gte"):
            if len(reminders) < expected["reminders_count_gte"]:
                logger.warning(
                    f"[E2E] Expected at least {expected['reminders_count_gte']} reminders, got {len(reminders)}"
                )
                return False

        return True

    def _verify_trigger_time(
        self, trigger_ts: int, spec: Dict, test_start_time: int
    ) -> bool:
        """验证触发时间"""
        trigger_dt = datetime.fromtimestamp(trigger_ts)
        now = datetime.now()

        # 相对时间验证
        if "relative_minutes" in spec:
            expected_ts = test_start_time + spec["relative_minutes"] * 60
            if abs(trigger_ts - expected_ts) > self.time_tolerance:
                logger.warning(
                    f"[E2E] Trigger time mismatch: expected ~{expected_ts}, got {trigger_ts}"
                )
                return False

        # 相对天数验证
        if "relative_days" in spec:
            expected_date = (now + timedelta(days=spec["relative_days"])).date()
            if trigger_dt.date() != expected_date:
                logger.warning(
                    f"[E2E] Trigger date mismatch: expected {expected_date}, got {trigger_dt.date()}"
                )
                return False

        # 小时验证
        if "hour" in spec:
            if trigger_dt.hour != spec["hour"]:
                logger.warning(
                    f"[E2E] Trigger hour mismatch: expected {spec['hour']}, got {trigger_dt.hour}"
                )
                return False

        # 分钟验证
        if "minute" in spec:
            if abs(trigger_dt.minute - spec["minute"]) > 1:
                logger.warning(
                    f"[E2E] Trigger minute mismatch: expected {spec['minute']}, got {trigger_dt.minute}"
                )
                return False

        # 星期验证 (1=周一, 7=周日)
        if "weekday" in spec:
            # Python weekday: 0=周一, 6=周日
            expected_weekday = spec["weekday"]
            actual_weekday = trigger_dt.weekday() + 1
            if actual_weekday != expected_weekday:
                logger.warning(
                    f"[E2E] Trigger weekday mismatch: expected {expected_weekday}, got {actual_weekday}"
                )
                return False

        return True

    def setup_test(self, setup_config: Optional[Dict]) -> None:
        """测试前置操作"""
        if not setup_config:
            return

        # 创建单个提醒
        if "create_reminder" in setup_config:
            self._create_setup_reminder(setup_config["create_reminder"])

        # 创建多个提醒
        if "create_reminders" in setup_config:
            for reminder_config in setup_config["create_reminders"]:
                self._create_setup_reminder(reminder_config)

    def _create_setup_reminder(self, config: Dict) -> None:
        """创建测试前置提醒"""
        now = int(time.time())
        trigger_time = now

        if "relative_minutes" in config:
            trigger_time = now + config["relative_minutes"] * 60
        elif "hour" in config:
            dt = datetime.now().replace(
                hour=config["hour"],
                minute=config.get("minute", 0),
                second=0,
                microsecond=0,
            )
            if dt.timestamp() <= now:
                dt += timedelta(days=1)
            trigger_time = int(dt.timestamp())

        reminder_data = {
            "user_id": self.user_id,
            "character_id": self.character_id,
            "title": config["title"],
            "next_trigger_time": trigger_time,
            "timezone": "Asia/Shanghai",
            "recurrence": {"enabled": False, "type": None, "interval": 1},
            "status": "active",
            "created_at": now,
            "updated_at": now,
            "triggered_count": 0,
        }
        self.reminder_dao.create_reminder(reminder_data)
        logger.info(f"[E2E] Setup: Created reminder '{config['title']}'")

    def cleanup_user_reminders(self) -> None:
        """清理用户的所有提醒"""
        deleted = self.reminder_dao.delete_all_by_user(self.user_id)
        logger.info(f"[E2E] Cleanup: Deleted {deleted} reminders")

    def run_single_test(self, test_case: Dict) -> Dict:
        """运行单个测试用例"""
        test_id = test_case["id"]
        test_name = test_case["name"]
        logger.info(f"\n{'='*60}")
        logger.info(f"[E2E] Running test: {test_id} - {test_name}")
        logger.info(f"{'='*60}")

        result = {
            "id": test_id,
            "name": test_name,
            "status": "unknown",
            "errors": [],
            "conversation_log": [],
        }

        try:
            # 清理并设置
            self.cleanup_user_reminders()
            self.setup_test(test_case.get("setup"))

            test_start_time = int(time.time())

            # 处理组合测试
            if "steps" in test_case:
                for i, step in enumerate(test_case["steps"]):
                    logger.info(f"[E2E] Step {i+1}/{len(test_case['steps'])}")
                    step_result = self._run_conversation(
                        step["conversation"], test_start_time
                    )
                    result["conversation_log"].extend(step_result["log"])
                    if not step_result["success"]:
                        result["status"] = "failed"
                        result["errors"].append(f"Step {i+1} conversation failed")
                        return result

                    # 验证步骤结果
                    if step.get("verify"):
                        if not self.verify_db_state(step["verify"], test_start_time):
                            result["status"] = "failed"
                            result["errors"].append(f"Step {i+1} DB verification failed")
                            return result
            else:
                # 普通测试
                conv_result = self._run_conversation(
                    test_case["conversation"], test_start_time
                )
                result["conversation_log"] = conv_result["log"]
                if not conv_result["success"]:
                    result["status"] = "failed"
                    result["errors"].append("Conversation failed")
                    return result

                # 验证最终数据库状态
                if test_case.get("final_db_state"):
                    if not self.verify_db_state(
                        test_case["final_db_state"], test_start_time
                    ):
                        result["status"] = "failed"
                        result["errors"].append("Final DB state verification failed")
                        return result

            result["status"] = "passed"

        except Exception as e:
            logger.exception(f"[E2E] Test error: {e}")
            result["status"] = "error"
            result["errors"].append(str(e))

        return result

    def _run_conversation(
        self, conversation: List[Dict], test_start_time: int
    ) -> Dict:
        """执行对话流程"""
        log = []
        for i, turn in enumerate(conversation):
            role = turn["role"]
            if role == "user":
                content = turn["content"]
                send_time = self.send_message(content)
                log.append({"role": "user", "content": content, "timestamp": send_time})
            elif role == "assistant":
                expect = turn.get("expect", {})
                response = self.wait_for_response(test_start_time)
                log.append(
                    {
                        "role": "assistant",
                        "content": response,
                        "timestamp": int(time.time()),
                    }
                )
                if not self.verify_response(response, expect):
                    return {"success": False, "log": log}
        return {"success": True, "log": log}

    def run_all_tests(
        self,
        filter_tags: Optional[List[str]] = None,
        filter_ids: Optional[List[str]] = None,
    ) -> None:
        """运行所有测试"""
        test_cases = self.test_cases.get("test_cases", [])

        # 过滤测试用例
        if filter_ids:
            test_cases = [tc for tc in test_cases if tc["id"] in filter_ids]
        elif filter_tags:
            test_cases = [
                tc
                for tc in test_cases
                if any(tag in tc.get("tags", []) for tag in filter_tags)
            ]

        logger.info(f"\n[E2E] Running {len(test_cases)} test cases")
        logger.info(f"[E2E] User ID: {self.user_id}")
        logger.info(f"[E2E] Character ID: {self.character_id}")

        for test_case in test_cases:
            result = self.run_single_test(test_case)
            self.results.append(result)

            if result["status"] == "passed":
                self.passed += 1
                logger.info(f"[E2E] ✓ PASSED: {test_case['id']}")
            elif result["status"] == "failed":
                self.failed += 1
                logger.error(
                    f"[E2E] ✗ FAILED: {test_case['id']} - {result['errors']}"
                )
            else:
                self.skipped += 1
                logger.warning(f"[E2E] ? SKIPPED/ERROR: {test_case['id']}")

            # 测试间隔，避免消息混淆
            time.sleep(2)

        self._print_summary()

    def _print_summary(self) -> None:
        """打印测试摘要"""
        total = len(self.results)
        logger.info(f"\n{'='*60}")
        logger.info("[E2E] TEST SUMMARY")
        logger.info(f"{'='*60}")
        logger.info(f"Total: {total}")
        logger.info(f"Passed: {self.passed} ({self.passed/total*100:.1f}%)")
        logger.info(f"Failed: {self.failed}")
        logger.info(f"Skipped/Error: {self.skipped}")

        if self.failed > 0:
            logger.info("\nFailed tests:")
            for result in self.results:
                if result["status"] == "failed":
                    logger.info(f"  - {result['id']}: {result['errors']}")

    def save_results(self, output_path: str = "tests/e2e/e2e_results.json") -> None:
        """保存测试结果"""
        output = {
            "run_time": datetime.now().isoformat(),
            "summary": {
                "total": len(self.results),
                "passed": self.passed,
                "failed": self.failed,
                "skipped": self.skipped,
            },
            "results": self.results,
        }
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        logger.info(f"[E2E] Results saved to {output_path}")

    def close(self) -> None:
        """关闭连接"""
        self.mongo.close()
        self.reminder_dao.close()
        self.user_dao.close()


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="Reminder E2E Test Runner")
    parser.add_argument(
        "--tags", nargs="+", help="Filter tests by tags (e.g., --tags 24hour single)"
    )
    parser.add_argument(
        "--ids", nargs="+", help="Filter tests by IDs (e.g., --ids time_24h_001)"
    )
    parser.add_argument(
        "--output", default="tests/e2e/e2e_results.json", help="Output file path"
    )
    args = parser.parse_args()

    runner = ReminderE2ETestRunner()
    try:
        runner.run_all_tests(filter_tags=args.tags, filter_ids=args.ids)
        runner.save_results(args.output)
    finally:
        runner.close()


if __name__ == "__main__":
    main()
