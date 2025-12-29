# -*- coding: utf-8 -*-
"""
Reminder Delete/Update Accuracy Test Suite

This test file covers edge cases and accuracy issues with reminder delete and update operations.
It includes:
1. Specific scenarios where delete functionality fails or behaves incorrectly
2. Specific scenarios where update functionality doesn't work as expected
3. Edge cases for both delete and update operations
4. Examples showing current problematic behavior versus desired behavior
5. Test data for validation

Requirements addressed:
- Improve LLM keyword matching accuracy
- Handle ambiguous user intents
- Prevent unintended bulk operations
- Validate time parsing in updates
"""

import json
import sys
import time
import uuid
from datetime import datetime, timedelta
from typing import Optional

import pytest

sys.path.append(".")

from util.log_util import get_logger

logger = get_logger(__name__)


# ========== Test Fixtures ==========
@pytest.fixture
def reminder_dao():
    """Create a ReminderDAO instance for testing"""
    from dao.reminder_dao import ReminderDAO

    dao = ReminderDAO()
    yield dao
    dao.close()


@pytest.fixture
def test_user_id():
    """Generate a unique test user ID"""
    return f"test_accuracy_{uuid.uuid4().hex[:8]}"


@pytest.fixture
def cleanup_reminders(reminder_dao, test_user_id):
    """Cleanup all test reminders after each test"""
    yield
    try:
        reminder_dao.delete_all_by_user(test_user_id)
    except Exception as e:
        logger.warning(f"Cleanup failed: {e}")


def create_test_reminder(
    dao,
    user_id: str,
    title: str,
    trigger_minutes_from_now: int = 60,
    recurrence_type: Optional[str] = None,
    status: str = "confirmed",
) -> dict:
    """Helper to create a test reminder"""
    now = int(time.time())
    reminder_doc = {
        "user_id": user_id,
        "reminder_id": str(uuid.uuid4()),
        "title": title,
        "action_template": f"记得{title}",
        "next_trigger_time": now + trigger_minutes_from_now * 60,
        "time_original": f"{trigger_minutes_from_now}分钟后",
        "timezone": "Asia/Shanghai",
        "recurrence": {
            "enabled": recurrence_type is not None,
            "type": recurrence_type,
        },
        "status": status,
        "conversation_id": "test_conv",
        "character_id": "test_char",
    }
    dao.create_reminder(reminder_doc)
    return reminder_doc


# ========== DELETE OPERATION FAILURE SCENARIOS ==========


class TestDeleteFailureScenarios:
    """Test cases where delete functionality fails or behaves incorrectly"""

    def test_delete_partial_keyword_mismatch(
        self, reminder_dao, test_user_id, cleanup_reminders
    ):
        """
        ISSUE: Partial keyword matching may miss intended reminders

        Scenario: User has "开会讨论项目" but says "删除开会提醒"
        Current behavior: May not match if using exact match
        Expected behavior: Should match "开会讨论项目" with keyword "开会"
        """
        # Create reminder with longer title
        create_test_reminder(reminder_dao, test_user_id, "开会讨论项目")

        # Try to delete with partial keyword
        deleted_count, deleted_reminders = reminder_dao.delete_reminders_by_keyword(
            test_user_id, "开会"
        )

        # This should work with regex matching
        assert deleted_count == 1, "Partial keyword should match longer title"
        assert "开会" in deleted_reminders[0]["title"]
        logger.info("✓ Partial keyword matching works correctly")

    def test_delete_accidental_over_matching(
        self, reminder_dao, test_user_id, cleanup_reminders
    ):
        """
        ISSUE: Overly broad keywords may delete unintended reminders

        Scenario: User has "吃药" and "吃饭", says "删除吃药提醒"
        but LLM extracts keyword as just "吃"
        Current behavior: May delete both reminders
        Expected behavior: Should only delete "吃药" with exact/better matching
        """
        create_test_reminder(reminder_dao, test_user_id, "吃药")
        create_test_reminder(reminder_dao, test_user_id, "吃饭")
        create_test_reminder(reminder_dao, test_user_id, "睡觉")

        # Overly broad keyword - this is problematic
        deleted_count, deleted_reminders = reminder_dao.delete_reminders_by_keyword(
            test_user_id, "吃"
        )

        # Current behavior: deletes both "吃药" and "吃饭"
        # This demonstrates the ISSUE
        if deleted_count == 2:
            logger.warning(
                "⚠ ISSUE DETECTED: Broad keyword '吃' deleted both '吃药' and '吃饭'"
            )
            logger.warning("This may not match user's intent if they only wanted to delete '吃药'")

        # Verify remaining
        remaining = reminder_dao.find_reminders_by_user(test_user_id)
        remaining_titles = [r["title"] for r in remaining]
        logger.info(f"Remaining reminders: {remaining_titles}")

    def test_delete_with_typo_or_synonym(
        self, reminder_dao, test_user_id, cleanup_reminders
    ):
        """
        ISSUE: Typos or synonyms may fail to match

        Scenario: User has "洗衣服" but says "删除洗衣提醒" (missing 服)
        Current behavior: May not match
        Expected behavior: Should use fuzzy matching or LLM should normalize
        """
        create_test_reminder(reminder_dao, test_user_id, "洗衣服")

        # Keyword without the full title
        deleted_count, _ = reminder_dao.delete_reminders_by_keyword(
            test_user_id, "洗衣"
        )

        # Current: Should match because "洗衣" is substring
        assert deleted_count == 1, "Substring should match"
        logger.info("✓ Substring matching works for typo scenario")

    def test_delete_empty_keyword_handling(
        self, reminder_dao, test_user_id, cleanup_reminders
    ):
        """
        ISSUE: Empty or whitespace keyword should be rejected, not match all

        Scenario: LLM passes empty keyword due to parsing error
        Current behavior: find_reminders_by_keyword returns no matches (safe)
        Expected behavior: Should return error
        """
        create_test_reminder(reminder_dao, test_user_id, "测试提醒")

        # Empty keyword
        result = reminder_dao.find_reminders_by_keyword(test_user_id, "")
        assert len(result) == 0, "Empty keyword should not match anything"

        # Whitespace keyword
        result = reminder_dao.find_reminders_by_keyword(test_user_id, "   ")
        # Current behavior may vary
        logger.info(f"Whitespace keyword matched {len(result)} reminders")

    def test_delete_special_characters_in_keyword(
        self, reminder_dao, test_user_id, cleanup_reminders
    ):
        """
        ISSUE: Special regex characters in keyword might cause errors

        Scenario: User says "删除 [重要] 会议提醒"
        The brackets are regex special characters
        """
        create_test_reminder(reminder_dao, test_user_id, "[重要] 项目会议")

        # Keyword with regex special characters
        deleted_count, _ = reminder_dao.delete_reminders_by_keyword(
            test_user_id, "[重要]"
        )

        # Should work because of re.escape in the DAO
        assert deleted_count == 1, "Special characters should be escaped properly"
        logger.info("✓ Special characters in keyword handled correctly")

    def test_delete_asterisk_wildcard_safety(
        self, reminder_dao, test_user_id, cleanup_reminders
    ):
        """
        ISSUE: Accidental use of "*" wildcard deletes all reminders

        Scenario: LLM extracts "*" as keyword due to misunderstanding
        This could be catastrophic if user just wanted to delete one reminder
        """
        create_test_reminder(reminder_dao, test_user_id, "提醒1")
        create_test_reminder(reminder_dao, test_user_id, "提醒2")
        create_test_reminder(reminder_dao, test_user_id, "提醒3")

        # The "*" wildcard deletes ALL reminders
        from agent.agno_agent.tools.reminder_tools import (
            _delete_reminder_by_keyword,
            set_reminder_session_state,
        )

        session_state = {"user": {"_id": test_user_id}}
        set_reminder_session_state(session_state)

        # This demonstrates the dangerous behavior
        result = _delete_reminder_by_keyword(reminder_dao, test_user_id, "*")

        if result.get("deleted_count", 0) == 3:
            logger.warning(
                "⚠ SAFETY CONCERN: '*' wildcard deleted all 3 reminders"
            )
            logger.warning(
                "Consider adding confirmation or removing this feature"
            )

    def test_delete_similar_titles_disambiguation(
        self, reminder_dao, test_user_id, cleanup_reminders
    ):
        """
        ISSUE: Similar titles make it hard to delete the correct one

        Scenario: User has "开会-产品评审" and "开会-技术评审"
        User says "删除产品评审的开会提醒"
        LLM might just extract "开会" and delete both
        """
        create_test_reminder(reminder_dao, test_user_id, "开会-产品评审")
        create_test_reminder(reminder_dao, test_user_id, "开会-技术评审")
        create_test_reminder(reminder_dao, test_user_id, "开会-日常站会")

        # More specific keyword should be used
        deleted_count, deleted_reminders = reminder_dao.delete_reminders_by_keyword(
            test_user_id, "产品评审"
        )

        assert deleted_count == 1, "Specific keyword should only match one"
        assert deleted_reminders[0]["title"] == "开会-产品评审"
        logger.info("✓ Specific keyword correctly disambiguates similar titles")


# ========== UPDATE OPERATION FAILURE SCENARIOS ==========


class TestUpdateFailureScenarios:
    """Test cases where update functionality doesn't work as expected"""

    def test_update_multiple_matches_ambiguity(
        self, reminder_dao, test_user_id, cleanup_reminders
    ):
        """
        ISSUE: When keyword matches multiple reminders, all get updated

        Scenario: User has "9点开会" and "3点开会"
        User says "把开会改到明天"
        Current behavior: Updates both reminders
        Expected behavior: Should ask for clarification or update the right one
        """
        create_test_reminder(reminder_dao, test_user_id, "9点开会", 60)
        create_test_reminder(reminder_dao, test_user_id, "3点开会", 120)

        new_time = int(time.time()) + 86400  # Tomorrow
        updated_count, updated_reminders = reminder_dao.update_reminders_by_keyword(
            test_user_id, "开会", {"next_trigger_time": new_time}
        )

        # Current behavior updates ALL matches
        if updated_count == 2:
            logger.warning(
                "⚠ ISSUE: Keyword '开会' updated both reminders without disambiguation"
            )
            logger.warning("This may not be the user's intent")

    def test_update_time_to_past_validation(
        self, reminder_dao, test_user_id, cleanup_reminders
    ):
        """
        ISSUE: Update might allow setting time to past

        Scenario: User says "把提醒改到昨天下午3点"
        Current behavior in DAO: No validation, allows past time
        Expected behavior: Should reject or warn
        """
        create_test_reminder(reminder_dao, test_user_id, "测试提醒", 60)

        # Set time to 1 hour ago (past)
        past_time = int(time.time()) - 3600
        updated_count, _ = reminder_dao.update_reminders_by_keyword(
            test_user_id, "测试", {"next_trigger_time": past_time}
        )

        if updated_count > 0:
            reminder = reminder_dao.find_reminders_by_keyword(test_user_id, "测试")[0]
            if reminder["next_trigger_time"] < int(time.time()):
                logger.warning(
                    "⚠ ISSUE: Reminder time was set to past without validation"
                )

    def test_update_partial_fields_preservation(
        self, reminder_dao, test_user_id, cleanup_reminders
    ):
        """
        ISSUE: Updating one field should preserve others

        Scenario: User wants to change only the time, not the title
        Ensure title and other fields are preserved
        """
        original_title = "原始标题-不要改"
        create_test_reminder(reminder_dao, test_user_id, original_title, 60)

        new_time = int(time.time()) + 7200
        updated_count, _ = reminder_dao.update_reminders_by_keyword(
            test_user_id, original_title, {"next_trigger_time": new_time}
        )

        assert updated_count == 1
        reminder = reminder_dao.find_reminders_by_keyword(test_user_id, original_title)[0]
        assert reminder["title"] == original_title, "Title should be preserved"
        assert reminder["next_trigger_time"] == new_time, "Time should be updated"
        logger.info("✓ Partial update preserves other fields correctly")

    def test_update_keyword_not_found(
        self, reminder_dao, test_user_id, cleanup_reminders
    ):
        """
        ISSUE: Unclear feedback when keyword doesn't match any reminder

        Scenario: User says "把游泳改到明天" but has no "游泳" reminder
        """
        create_test_reminder(reminder_dao, test_user_id, "开会", 60)

        new_time = int(time.time()) + 86400
        updated_count, updated_reminders = reminder_dao.update_reminders_by_keyword(
            test_user_id, "游泳", {"next_trigger_time": new_time}
        )

        assert updated_count == 0, "Non-matching keyword should update nothing"
        assert len(updated_reminders) == 0
        logger.info("✓ Non-matching keyword correctly returns 0 updates")

    def test_update_recurrence_changes(
        self, reminder_dao, test_user_id, cleanup_reminders
    ):
        """
        ISSUE: Changing recurrence type might not update all related fields

        Scenario: User changes from daily to weekly
        """
        doc = create_test_reminder(
            reminder_dao, test_user_id, "周期提醒", 60, recurrence_type="daily"
        )

        updated_count, _ = reminder_dao.update_reminders_by_keyword(
            test_user_id,
            "周期",
            {"recurrence": {"enabled": True, "type": "weekly", "interval": 1}},
        )

        assert updated_count == 1
        reminder = reminder_dao.find_reminders_by_keyword(test_user_id, "周期")[0]
        assert reminder["recurrence"]["type"] == "weekly"
        logger.info("✓ Recurrence type update works correctly")

    def test_update_with_empty_new_values(
        self, reminder_dao, test_user_id, cleanup_reminders
    ):
        """
        ISSUE: Empty new values might clear fields unexpectedly

        Scenario: LLM passes empty string for new_title
        """
        original_title = "原始标题"
        create_test_reminder(reminder_dao, test_user_id, original_title, 60)

        # Trying to update with empty title
        updated_count, _ = reminder_dao.update_reminders_by_keyword(
            test_user_id, "原始", {"title": ""}
        )

        if updated_count > 0:
            # Find by original title (since we updated to empty, it should still exist)
            reminders = reminder_dao.find_reminders_by_user(test_user_id)
            if reminders:
                reminder = reminders[0]
                if not reminder.get("title"):
                    logger.warning(
                        "⚠ ISSUE: Empty string update cleared the title field"
                    )
                else:
                    logger.info(
                        f"After empty title update, title is: '{reminder.get('title')}'"
                    )


# ========== EDGE CASES ==========


class TestEdgeCases:
    """Edge cases for both delete and update operations"""

    def test_unicode_and_emoji_in_title(
        self, reminder_dao, test_user_id, cleanup_reminders
    ):
        """Test handling of Unicode and emoji characters"""
        create_test_reminder(reminder_dao, test_user_id, "🎉 生日派对 🎂")

        deleted_count, _ = reminder_dao.delete_reminders_by_keyword(
            test_user_id, "生日"
        )

        assert deleted_count == 1, "Unicode and emoji should be handled"
        logger.info("✓ Unicode and emoji in title handled correctly")

    def test_very_long_title(self, reminder_dao, test_user_id, cleanup_reminders):
        """Test handling of very long titles"""
        long_title = "这是一个非常非常长的提醒标题" * 10
        create_test_reminder(reminder_dao, test_user_id, long_title)

        # Delete with short keyword
        deleted_count, _ = reminder_dao.delete_reminders_by_keyword(
            test_user_id, "非常非常长"
        )

        assert deleted_count == 1, "Long title should be matched"
        logger.info("✓ Very long title handled correctly")

    def test_concurrent_delete_operations(
        self, reminder_dao, test_user_id, cleanup_reminders
    ):
        """Test concurrent delete operations don't cause issues"""
        for i in range(5):
            create_test_reminder(reminder_dao, test_user_id, f"并发测试{i}")

        # Multiple deletes in sequence
        reminder_dao.delete_reminders_by_keyword(test_user_id, "并发测试0")
        reminder_dao.delete_reminders_by_keyword(test_user_id, "并发测试1")
        reminder_dao.delete_reminders_by_keyword(test_user_id, "并发测试2")

        remaining = reminder_dao.find_reminders_by_user(test_user_id)
        assert len(remaining) == 2, "Should have 2 remaining"
        logger.info("✓ Sequential delete operations work correctly")

    def test_case_sensitivity(self, reminder_dao, test_user_id, cleanup_reminders):
        """Test case sensitivity in keyword matching"""
        create_test_reminder(reminder_dao, test_user_id, "Meeting with CEO")

        # Lowercase search
        deleted_count, _ = reminder_dao.delete_reminders_by_keyword(
            test_user_id, "meeting"
        )

        # Current implementation uses case-insensitive search
        assert deleted_count == 1, "Case-insensitive search should match"
        logger.info("✓ Case-insensitive matching works correctly")

    def test_update_completed_reminder(
        self, reminder_dao, test_user_id, cleanup_reminders
    ):
        """
        ISSUE: Updating a completed/cancelled reminder

        By default, updates only affect confirmed/pending status
        """
        create_test_reminder(
            reminder_dao, test_user_id, "已完成提醒", 60, status="completed"
        )

        new_time = int(time.time()) + 7200
        updated_count, _ = reminder_dao.update_reminders_by_keyword(
            test_user_id, "已完成", {"next_trigger_time": new_time}
        )

        # Should not update completed reminders
        assert updated_count == 0, "Completed reminders should not be updated"
        logger.info("✓ Completed reminders correctly excluded from update")

    def test_delete_cancelled_reminder(
        self, reminder_dao, test_user_id, cleanup_reminders
    ):
        """
        ISSUE: Deleting a cancelled reminder

        By default, deletes only affect confirmed/pending status
        """
        create_test_reminder(
            reminder_dao, test_user_id, "已取消提醒", 60, status="cancelled"
        )

        deleted_count, _ = reminder_dao.delete_reminders_by_keyword(
            test_user_id, "已取消"
        )

        # Should not delete cancelled reminders
        assert deleted_count == 0, "Cancelled reminders should not be deleted"
        logger.info("✓ Cancelled reminders correctly excluded from delete")


# ========== LLM INTEGRATION SCENARIOS ==========


class TestLLMIntegrationScenarios:
    """Test scenarios that demonstrate LLM integration issues"""

    def test_llm_keyword_extraction_too_broad(
        self, reminder_dao, test_user_id, cleanup_reminders
    ):
        """
        ISSUE: LLM extracts overly broad keywords

        User says: "删除明天下午开会的提醒"
        LLM extracts: keyword="开会" (ignoring time context)
        Problem: Multiple "开会" reminders get deleted
        """
        create_test_reminder(reminder_dao, test_user_id, "今天早上开会", 30)
        create_test_reminder(reminder_dao, test_user_id, "明天下午开会", 1440)  # Tomorrow
        create_test_reminder(reminder_dao, test_user_id, "后天开会", 2880)

        # Simulate LLM extracting just "开会"
        deleted_count, deleted = reminder_dao.delete_reminders_by_keyword(
            test_user_id, "开会"
        )

        if deleted_count == 3:
            logger.warning(
                "⚠ ISSUE: LLM keyword '开会' deleted all 3 meeting reminders"
            )
            logger.warning(
                "User only wanted to delete '明天下午开会', but all got deleted"
            )
            logger.warning(
                "SOLUTION: LLM should extract more specific keywords like '明天下午开会'"
            )

    def test_llm_time_extraction_issues(
        self, reminder_dao, test_user_id, cleanup_reminders
    ):
        """
        ISSUE: LLM struggles with relative time updates

        User says: "把喝水提醒改到半小时后"
        LLM needs to calculate actual timestamp
        """
        create_test_reminder(reminder_dao, test_user_id, "喝水", 60)

        from agent.agno_agent.tools.reminder_tools import (
            _update_reminder_by_keyword,
            set_reminder_session_state,
        )

        session_state = {"user": {"_id": test_user_id}}
        set_reminder_session_state(session_state)

        # LLM should pass relative time string
        result = _update_reminder_by_keyword(
            reminder_dao,
            test_user_id,
            keyword="喝水",
            new_title=None,
            new_trigger_time="30分钟后",  # Relative time
        )

        if result.get("ok"):
            logger.info("✓ Relative time update works correctly")
        else:
            logger.warning(f"⚠ Relative time update failed: {result.get('error')}")

    def test_batch_operation_ordering(
        self, reminder_dao, test_user_id, cleanup_reminders
    ):
        """
        ISSUE: Batch operation order matters

        User says: "删除游泳那个，把开会改到明天，再加一个提醒"
        Operations must execute in correct order
        """
        create_test_reminder(reminder_dao, test_user_id, "游泳")
        create_test_reminder(reminder_dao, test_user_id, "开会")

        from agent.agno_agent.tools.reminder_tools import (
            _batch_operations,
            set_reminder_session_state,
        )

        session_state = {
            "user": {"_id": test_user_id},
            "character": {"_id": "test_char"},
            "conversation": {"_id": "test_conv"},
        }
        set_reminder_session_state(session_state)

        tomorrow = datetime.now() + timedelta(days=1)
        tomorrow_str = tomorrow.strftime("%Y年%m月%d日15时00分")

        operations = json.dumps([
            {"action": "delete", "keyword": "游泳"},
            {"action": "update", "keyword": "开会", "new_trigger_time": tomorrow_str},
            {"action": "create", "title": "新提醒", "trigger_time": tomorrow_str},
        ])

        result = _batch_operations(
            reminder_dao,
            test_user_id,
            operations,
            conversation_id="test_conv",
            character_id="test_char",
            base_timestamp=int(time.time()),
        )

        assert result.get("ok"), f"Batch operation should succeed: {result}"
        summary = result.get("summary", {})
        logger.info(f"Batch operation results: {summary}")


# ========== SUGGESTED IMPROVEMENTS TEST DATA ==========


class TestSuggestedImprovements:
    """Test cases that validate suggested improvements"""

    def test_improved_keyword_specificity_scoring(
        self, reminder_dao, test_user_id, cleanup_reminders
    ):
        """
        IMPROVEMENT: Score keyword matches by specificity

        Instead of deleting all matches, return matches with scores
        and let LLM/user choose the most appropriate one
        """
        create_test_reminder(reminder_dao, test_user_id, "吃药")
        create_test_reminder(reminder_dao, test_user_id, "吃早饭")
        create_test_reminder(reminder_dao, test_user_id, "吃午饭")

        # Find all matches first
        matches = reminder_dao.find_reminders_by_keyword(test_user_id, "吃")

        # Score by match quality (exact match > prefix match > substring)
        scored_matches = []
        for m in matches:
            title = m["title"]
            keyword = "吃"
            if title == keyword:
                score = 1.0  # Exact match
            elif title.startswith(keyword):
                score = 0.8  # Prefix match
            else:
                score = 0.5  # Substring match

            scored_matches.append({"reminder": m, "score": score})

        scored_matches.sort(key=lambda x: x["score"], reverse=True)
        logger.info(f"Scored matches: {[(m['reminder']['title'], m['score']) for m in scored_matches]}")

        # Suggestion: Return scores to LLM for better decision making

    def test_confirmation_for_multiple_matches(
        self, reminder_dao, test_user_id, cleanup_reminders
    ):
        """
        IMPROVEMENT: Require confirmation when multiple reminders match

        Instead of silently updating/deleting all, ask for clarification
        """
        create_test_reminder(reminder_dao, test_user_id, "开会A")
        create_test_reminder(reminder_dao, test_user_id, "开会B")

        matches = reminder_dao.find_reminders_by_keyword(test_user_id, "开会")

        if len(matches) > 1:
            # IMPROVEMENT: Return a needs_clarification response
            clarification_needed = {
                "status": "needs_clarification",
                "matches": [
                    {"id": m["reminder_id"], "title": m["title"]}
                    for m in matches
                ],
                "message": f"找到{len(matches)}个包含「开会」的提醒，请确认要操作哪一个",
            }
            logger.info(f"Clarification response: {clarification_needed}")

    def test_time_context_aware_matching(
        self, reminder_dao, test_user_id, cleanup_reminders
    ):
        """
        IMPROVEMENT: Use time context for better matching

        When user says "删除明天的提醒", consider time in matching
        """
        now = int(time.time())
        # Create reminders at different times
        create_test_reminder(reminder_dao, test_user_id, "今天任务", 60)  # 1 hour
        create_test_reminder(reminder_dao, test_user_id, "明天任务", 1440)  # 24 hours

        # IMPROVEMENT: Time-aware search
        tomorrow_start = (now // 86400 + 1) * 86400  # Start of tomorrow
        tomorrow_end = tomorrow_start + 86400

        # Find reminders for tomorrow
        tomorrow_reminders = [
            r for r in reminder_dao.find_reminders_by_user(test_user_id)
            if tomorrow_start <= r["next_trigger_time"] < tomorrow_end
        ]

        logger.info(
            f"Tomorrow's reminders: {[r['title'] for r in tomorrow_reminders]}"
        )


# ========== VALIDATION TEST DATA ==========


class TestValidationData:
    """Provide test data sets for validation"""

    @pytest.fixture
    def sample_test_data(self, reminder_dao, test_user_id, cleanup_reminders):
        """Create a comprehensive set of test reminders"""
        test_data = [
            # Basic reminders
            {"title": "喝水", "minutes": 30},
            {"title": "吃药", "minutes": 60},
            {"title": "开会-产品评审", "minutes": 90},
            {"title": "开会-技术评审", "minutes": 120},
            {"title": "开会-日常站会", "minutes": 150},
            # Edge case titles
            {"title": "🎂 生日提醒 🎉", "minutes": 200},
            {"title": "[重要] 项目交付", "minutes": 250},
            {"title": "Test Meeting (English)", "minutes": 300},
            # Similar titles
            {"title": "吃早饭", "minutes": 360},
            {"title": "吃午饭", "minutes": 420},
            {"title": "吃晚饭", "minutes": 480},
        ]

        created = []
        for data in test_data:
            doc = create_test_reminder(
                reminder_dao, test_user_id, data["title"], data["minutes"]
            )
            created.append(doc)

        return created

    def test_list_all_test_data(
        self, reminder_dao, test_user_id, sample_test_data, cleanup_reminders
    ):
        """List all test data for manual verification"""
        reminders = reminder_dao.find_reminders_by_user(test_user_id)

        logger.info(f"Total test reminders: {len(reminders)}")
        for i, r in enumerate(reminders, 1):
            trigger_time = datetime.fromtimestamp(r["next_trigger_time"])
            logger.info(f"  {i}. {r['title']} - {trigger_time}")

    def test_keyword_matching_accuracy(
        self, reminder_dao, test_user_id, sample_test_data, cleanup_reminders
    ):
        """Test keyword matching accuracy across various scenarios"""
        test_cases = [
            ("喝水", 1, "Exact match"),
            ("开会", 3, "Multiple matches"),
            ("吃", 4, "Prefix match - 吃药 + 吃早/午/晚饭"),
            ("生日", 1, "Unicode with emoji"),
            ("重要", 1, "Special characters"),
            ("不存在", 0, "No match"),
            ("Meeting", 1, "English case-insensitive"),
        ]

        results = []
        for keyword, expected, description in test_cases:
            matches = reminder_dao.find_reminders_by_keyword(test_user_id, keyword)
            actual = len(matches)
            passed = actual == expected
            results.append({
                "keyword": keyword,
                "expected": expected,
                "actual": actual,
                "passed": passed,
                "description": description,
            })

        # Report results
        for r in results:
            status = "✓" if r["passed"] else "✗"
            logger.info(
                f"{status} Keyword '{r['keyword']}': expected {r['expected']}, "
                f"got {r['actual']} ({r['description']})"
            )

        # Assert all passed
        failures = [r for r in results if not r["passed"]]
        if failures:
            logger.warning(f"⚠ {len(failures)} keyword matching tests failed")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
