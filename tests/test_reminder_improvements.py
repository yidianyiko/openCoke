# -*- coding: utf-8 -*-
"""
Reminder System Improvements Test Suite

This file contains:
1. Improved matching algorithms with scoring
2. Clarification-required responses for ambiguous operations
3. Better validation for update operations
4. Safety guards for dangerous operations

These improvements address the accuracy issues identified in test_reminder_accuracy_issues.py
"""

import json
import sys
import time
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import pytest

sys.path.append(".")

from util.log_util import get_logger

logger = get_logger(__name__)


# ========== IMPROVED MATCHING ALGORITHMS ==========


class ImprovedReminderMatcher:
    """
    Improved reminder matching with scoring and disambiguation.
    
    This class demonstrates the suggested improvements for:
    - Better keyword specificity scoring
    - Ambiguity detection
    - Time-context aware matching
    """

    # Match quality thresholds
    EXACT_MATCH_SCORE = 1.0
    PREFIX_MATCH_SCORE = 0.8
    WORD_BOUNDARY_SCORE = 0.7
    SUBSTRING_MATCH_SCORE = 0.5
    
    # Ambiguity thresholds
    SINGLE_MATCH_THRESHOLD = 0.9  # Score needed to auto-select
    MULTI_MATCH_CLARIFY_THRESHOLD = 3  # Ask for clarification if more matches

    def __init__(self, reminder_dao):
        self.reminder_dao = reminder_dao

    def score_match(self, title: str, keyword: str) -> float:
        """
        Score how well a keyword matches a title.
        
        Returns:
            float: Match score between 0.0 and 1.0
        """
        if not title or not keyword:
            return 0.0
        
        title_lower = title.lower()
        keyword_lower = keyword.lower()
        
        # Exact match
        if title_lower == keyword_lower:
            return self.EXACT_MATCH_SCORE
        
        # Prefix match (title starts with keyword)
        if title_lower.startswith(keyword_lower):
            # Score based on how much of the title is matched
            coverage = len(keyword) / len(title)
            return self.PREFIX_MATCH_SCORE + (0.2 * coverage)
        
        # Word boundary match (keyword is a complete word in title)
        import re
        word_pattern = r'\b' + re.escape(keyword_lower) + r'\b'
        if re.search(word_pattern, title_lower):
            return self.WORD_BOUNDARY_SCORE
        
        # Substring match
        if keyword_lower in title_lower:
            # Score based on keyword length relative to title
            coverage = len(keyword) / len(title)
            return self.SUBSTRING_MATCH_SCORE + (0.3 * coverage)
        
        return 0.0

    def find_matches_with_scores(
        self, user_id: str, keyword: str, min_score: float = 0.3
    ) -> List[Dict]:
        """
        Find reminders matching keyword with match quality scores.
        
        Returns:
            List of dicts with 'reminder' and 'score' keys, sorted by score
        """
        all_reminders = self.reminder_dao.find_reminders_by_user(
            user_id, status_list=["confirmed", "pending"]
        )
        
        scored_matches = []
        for reminder in all_reminders:
            score = self.score_match(reminder.get("title", ""), keyword)
            if score >= min_score:
                scored_matches.append({
                    "reminder": reminder,
                    "score": score,
                    "match_type": self._get_match_type(score),
                })
        
        # Sort by score descending
        scored_matches.sort(key=lambda x: x["score"], reverse=True)
        return scored_matches

    def _get_match_type(self, score: float) -> str:
        """Get human-readable match type from score"""
        if score >= self.EXACT_MATCH_SCORE:
            return "exact"
        elif score >= self.PREFIX_MATCH_SCORE:
            return "prefix"
        elif score >= self.WORD_BOUNDARY_SCORE:
            return "word_boundary"
        else:
            return "substring"

    def select_best_match(
        self, user_id: str, keyword: str
    ) -> Tuple[Optional[Dict], bool, List[Dict]]:
        """
        Select the best matching reminder or request clarification.
        
        Returns:
            Tuple of (selected_reminder, needs_clarification, all_matches)
            - If exactly one high-confidence match: (match, False, [])
            - If multiple matches need clarification: (None, True, all_matches)
            - If no matches: (None, False, [])
        """
        matches = self.find_matches_with_scores(user_id, keyword)
        
        if not matches:
            return None, False, []
        
        # Single match with high confidence
        if len(matches) == 1 and matches[0]["score"] >= self.SINGLE_MATCH_THRESHOLD:
            return matches[0]["reminder"], False, matches
        
        # Single match with lower confidence - still acceptable
        if len(matches) == 1:
            return matches[0]["reminder"], False, matches
        
        # Top match significantly better than others
        if len(matches) > 1:
            top_score = matches[0]["score"]
            second_score = matches[1]["score"]
            if top_score >= self.SINGLE_MATCH_THRESHOLD and (top_score - second_score) >= 0.2:
                return matches[0]["reminder"], False, matches
        
        # Multiple matches - need clarification
        if len(matches) <= self.MULTI_MATCH_CLARIFY_THRESHOLD:
            return None, True, matches
        
        # Too many matches - keyword too broad
        return None, True, matches[:self.MULTI_MATCH_CLARIFY_THRESHOLD]


# ========== IMPROVED DELETE OPERATION ==========


class ImprovedDeleteOperation:
    """
    Improved delete operation with safety guards and clarification.
    """

    def __init__(self, reminder_dao):
        self.reminder_dao = reminder_dao
        self.matcher = ImprovedReminderMatcher(reminder_dao)

    def delete_by_keyword_improved(
        self,
        user_id: str,
        keyword: str,
        force: bool = False,
        confirmed_id: Optional[str] = None,
    ) -> Dict:
        """
        Improved delete operation with disambiguation.
        
        Args:
            user_id: User ID
            keyword: Search keyword
            force: If True, delete all matches without confirmation
            confirmed_id: If provided, only delete this specific reminder
            
        Returns:
            Dict with operation result
        """
        # Validate keyword
        if not keyword or not keyword.strip():
            return {
                "ok": False,
                "error": "关键字不能为空",
            }
        
        keyword = keyword.strip()
        
        # Check for dangerous wildcard
        if keyword == "*" and not force:
            return {
                "ok": False,
                "status": "confirmation_required",
                "message": "删除所有提醒是危险操作，需要确认。请使用 force=True 或指定具体的提醒。",
            }
        
        # Handle confirmed_id (user selected from clarification)
        if confirmed_id:
            success = self.reminder_dao.delete_reminder(confirmed_id)
            if success:
                return {
                    "ok": True,
                    "deleted_count": 1,
                    "message": "已删除指定的提醒",
                }
            else:
                return {
                    "ok": False,
                    "error": "找不到指定的提醒",
                }
        
        # Find matches with scoring
        selected, needs_clarification, all_matches = self.matcher.select_best_match(
            user_id, keyword
        )
        
        # No matches
        if not selected and not needs_clarification:
            return {
                "ok": False,
                "error": f"没有找到包含「{keyword}」的提醒",
                "deleted_count": 0,
            }
        
        # Needs clarification
        if needs_clarification:
            match_options = [
                {
                    "id": m["reminder"]["reminder_id"],
                    "title": m["reminder"]["title"],
                    "score": m["score"],
                    "trigger_time": datetime.fromtimestamp(
                        m["reminder"]["next_trigger_time"]
                    ).strftime("%m月%d日%H时%M分"),
                }
                for m in all_matches
            ]
            
            return {
                "ok": False,
                "status": "needs_clarification",
                "message": f"找到{len(match_options)}个包含「{keyword}」的提醒，请确认要删除哪一个：",
                "options": match_options,
                "instruction": "请告诉我具体是哪一个，比如说'删除第一个'或'删除开会-产品评审那个'",
            }
        
        # Single clear match - delete
        reminder_id = selected["reminder_id"]
        title = selected["title"]
        
        success = self.reminder_dao.delete_reminder(reminder_id)
        if success:
            return {
                "ok": True,
                "deleted_count": 1,
                "deleted_reminder": {"id": reminder_id, "title": title},
                "message": f"已删除提醒「{title}」",
            }
        else:
            return {
                "ok": False,
                "error": "删除操作失败",
            }


# ========== IMPROVED UPDATE OPERATION ==========


class ImprovedUpdateOperation:
    """
    Improved update operation with validation and clarification.
    """

    def __init__(self, reminder_dao):
        self.reminder_dao = reminder_dao
        self.matcher = ImprovedReminderMatcher(reminder_dao)

    def update_by_keyword_improved(
        self,
        user_id: str,
        keyword: str,
        new_title: Optional[str] = None,
        new_trigger_time: Optional[str] = None,
        confirmed_id: Optional[str] = None,
    ) -> Dict:
        """
        Improved update operation with validation and disambiguation.
        
        Args:
            user_id: User ID
            keyword: Search keyword
            new_title: New title (optional)
            new_trigger_time: New trigger time string (optional)
            confirmed_id: If provided, only update this specific reminder
            
        Returns:
            Dict with operation result
        """
        # Validate inputs
        if not keyword or not keyword.strip():
            return {
                "ok": False,
                "error": "关键字不能为空",
            }
        
        keyword = keyword.strip()
        
        # Validate that at least one update field is provided
        if not new_title and not new_trigger_time:
            return {
                "ok": False,
                "error": "需要提供 new_title 或 new_trigger_time",
            }
        
        # Validate new_title is not empty if provided
        if new_title is not None and not new_title.strip():
            return {
                "ok": False,
                "error": "新标题不能为空",
            }
        
        # Parse and validate new_trigger_time
        update_fields = {}
        if new_trigger_time:
            timestamp = self._parse_time(new_trigger_time)
            if not timestamp:
                return {
                    "ok": False,
                    "error": f"无法解析时间: {new_trigger_time}",
                    "suggestion": "请使用格式如 '30分钟后' 或 '2025年12月09日15时00分'",
                }
            
            # Validate time is in future
            if timestamp <= int(time.time()):
                return {
                    "ok": False,
                    "error": "提醒时间必须在未来",
                    "suggestion": "请设置一个未来的时间",
                }
            
            update_fields["next_trigger_time"] = timestamp
            update_fields["time_original"] = new_trigger_time
        
        if new_title:
            update_fields["title"] = new_title.strip()
            update_fields["action_template"] = f"记得{new_title.strip()}"
        
        # Handle confirmed_id
        if confirmed_id:
            success = self.reminder_dao.update_reminder(confirmed_id, update_fields)
            if success:
                return {
                    "ok": True,
                    "updated_count": 1,
                    "message": "已更新指定的提醒",
                }
            else:
                return {
                    "ok": False,
                    "error": "找不到指定的提醒",
                }
        
        # Find matches with scoring
        selected, needs_clarification, all_matches = self.matcher.select_best_match(
            user_id, keyword
        )
        
        # No matches
        if not selected and not needs_clarification:
            return {
                "ok": False,
                "error": f"没有找到包含「{keyword}」的提醒",
                "updated_count": 0,
            }
        
        # Needs clarification
        if needs_clarification:
            match_options = [
                {
                    "id": m["reminder"]["reminder_id"],
                    "title": m["reminder"]["title"],
                    "score": m["score"],
                    "trigger_time": datetime.fromtimestamp(
                        m["reminder"]["next_trigger_time"]
                    ).strftime("%m月%d日%H时%M分"),
                }
                for m in all_matches
            ]
            
            return {
                "ok": False,
                "status": "needs_clarification",
                "message": f"找到{len(match_options)}个包含「{keyword}」的提醒，请确认要修改哪一个：",
                "options": match_options,
                "instruction": "请告诉我具体是哪一个",
            }
        
        # Single clear match - update
        reminder_id = selected["reminder_id"]
        title = selected["title"]
        
        success = self.reminder_dao.update_reminder(reminder_id, update_fields)
        if success:
            update_desc = []
            if new_title:
                update_desc.append(f"标题改为「{new_title}」")
            if new_trigger_time:
                update_desc.append(f"时间改为 {new_trigger_time}")
            
            return {
                "ok": True,
                "updated_count": 1,
                "updated_reminder": {"id": reminder_id, "original_title": title},
                "message": f"已更新提醒「{title}」：{', '.join(update_desc)}",
            }
        else:
            return {
                "ok": False,
                "error": "更新操作失败",
            }

    def _parse_time(self, time_str: str) -> Optional[int]:
        """Parse time string to timestamp"""
        from util.time_util import parse_relative_time, str2timestamp
        
        # Try relative time first
        timestamp = parse_relative_time(time_str)
        if timestamp:
            return timestamp
        
        # Try absolute time
        timestamp = str2timestamp(time_str)
        return timestamp


# ========== TEST CASES FOR IMPROVEMENTS ==========


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
    return f"test_improve_{uuid.uuid4().hex[:8]}"


@pytest.fixture
def cleanup_reminders(reminder_dao, test_user_id):
    """Cleanup all test reminders after each test"""
    yield
    try:
        reminder_dao.delete_all_by_user(test_user_id)
    except Exception as e:
        logger.warning(f"Cleanup failed: {e}")


def create_test_reminder(dao, user_id: str, title: str, minutes: int = 60) -> dict:
    """Helper to create a test reminder"""
    now = int(time.time())
    doc = {
        "user_id": user_id,
        "reminder_id": str(uuid.uuid4()),
        "title": title,
        "action_template": f"记得{title}",
        "next_trigger_time": now + minutes * 60,
        "time_original": f"{minutes}分钟后",
        "timezone": "Asia/Shanghai",
        "recurrence": {"enabled": False},
        "status": "confirmed",
        "conversation_id": "test_conv",
        "character_id": "test_char",
    }
    dao.create_reminder(doc)
    return doc


class TestImprovedMatcher:
    """Test the improved matching algorithm"""

    def test_score_exact_match(self, reminder_dao, test_user_id, cleanup_reminders):
        """Exact match should get highest score"""
        create_test_reminder(reminder_dao, test_user_id, "喝水")
        
        matcher = ImprovedReminderMatcher(reminder_dao)
        matches = matcher.find_matches_with_scores(test_user_id, "喝水")
        
        assert len(matches) == 1
        assert matches[0]["score"] == 1.0
        assert matches[0]["match_type"] == "exact"
        logger.info("✓ Exact match scoring works correctly")

    def test_score_prefix_match(self, reminder_dao, test_user_id, cleanup_reminders):
        """Prefix match should get second highest score"""
        create_test_reminder(reminder_dao, test_user_id, "开会讨论项目")
        
        matcher = ImprovedReminderMatcher(reminder_dao)
        matches = matcher.find_matches_with_scores(test_user_id, "开会")
        
        assert len(matches) == 1
        assert matches[0]["score"] >= 0.8
        assert matches[0]["match_type"] == "prefix"
        logger.info(f"✓ Prefix match score: {matches[0]['score']}")

    def test_score_substring_match(self, reminder_dao, test_user_id, cleanup_reminders):
        """Substring match should get lower score"""
        create_test_reminder(reminder_dao, test_user_id, "下午3点开会")
        
        matcher = ImprovedReminderMatcher(reminder_dao)
        matches = matcher.find_matches_with_scores(test_user_id, "开会")
        
        assert len(matches) == 1
        assert matches[0]["score"] < 0.8  # Lower than prefix
        logger.info(f"✓ Substring match score: {matches[0]['score']}")

    def test_select_best_single_match(
        self, reminder_dao, test_user_id, cleanup_reminders
    ):
        """Single clear match should be auto-selected"""
        create_test_reminder(reminder_dao, test_user_id, "喝水")
        create_test_reminder(reminder_dao, test_user_id, "吃药")
        
        matcher = ImprovedReminderMatcher(reminder_dao)
        selected, needs_clarification, _ = matcher.select_best_match(
            test_user_id, "喝水"
        )
        
        assert selected is not None
        assert selected["title"] == "喝水"
        assert not needs_clarification
        logger.info("✓ Single match auto-selection works")

    def test_select_needs_clarification(
        self, reminder_dao, test_user_id, cleanup_reminders
    ):
        """Multiple similar matches should require clarification"""
        create_test_reminder(reminder_dao, test_user_id, "开会-产品评审")
        create_test_reminder(reminder_dao, test_user_id, "开会-技术评审")
        create_test_reminder(reminder_dao, test_user_id, "开会-日常站会")
        
        matcher = ImprovedReminderMatcher(reminder_dao)
        selected, needs_clarification, matches = matcher.select_best_match(
            test_user_id, "开会"
        )
        
        assert selected is None
        assert needs_clarification
        assert len(matches) == 3
        logger.info("✓ Multiple matches correctly trigger clarification")


class TestImprovedDelete:
    """Test the improved delete operation"""

    def test_delete_with_clarification(
        self, reminder_dao, test_user_id, cleanup_reminders
    ):
        """Delete should ask for clarification when ambiguous"""
        create_test_reminder(reminder_dao, test_user_id, "吃早饭")
        create_test_reminder(reminder_dao, test_user_id, "吃午饭")
        
        improved_delete = ImprovedDeleteOperation(reminder_dao)
        result = improved_delete.delete_by_keyword_improved(test_user_id, "吃")
        
        assert result["ok"] is False
        assert result.get("status") == "needs_clarification"
        assert "options" in result
        assert len(result["options"]) == 2
        logger.info("✓ Ambiguous delete correctly asks for clarification")

    def test_delete_with_confirmed_id(
        self, reminder_dao, test_user_id, cleanup_reminders
    ):
        """Delete should work when user confirms specific ID"""
        doc = create_test_reminder(reminder_dao, test_user_id, "测试提醒")
        
        improved_delete = ImprovedDeleteOperation(reminder_dao)
        result = improved_delete.delete_by_keyword_improved(
            test_user_id, "测试", confirmed_id=doc["reminder_id"]
        )
        
        assert result["ok"] is True
        assert result["deleted_count"] == 1
        logger.info("✓ Delete with confirmed ID works correctly")

    def test_delete_wildcard_protection(
        self, reminder_dao, test_user_id, cleanup_reminders
    ):
        """Delete all should require force=True"""
        create_test_reminder(reminder_dao, test_user_id, "提醒1")
        create_test_reminder(reminder_dao, test_user_id, "提醒2")
        
        improved_delete = ImprovedDeleteOperation(reminder_dao)
        
        # Without force - should be rejected
        result = improved_delete.delete_by_keyword_improved(test_user_id, "*")
        assert result["ok"] is False
        assert result.get("status") == "confirmation_required"
        
        # Verify reminders still exist
        remaining = reminder_dao.find_reminders_by_user(test_user_id)
        assert len(remaining) == 2
        logger.info("✓ Wildcard delete protection works correctly")


class TestImprovedUpdate:
    """Test the improved update operation"""

    def test_update_with_clarification(
        self, reminder_dao, test_user_id, cleanup_reminders
    ):
        """Update should ask for clarification when ambiguous"""
        create_test_reminder(reminder_dao, test_user_id, "开会A")
        create_test_reminder(reminder_dao, test_user_id, "开会B")
        
        improved_update = ImprovedUpdateOperation(reminder_dao)
        result = improved_update.update_by_keyword_improved(
            test_user_id, "开会", new_title="重要会议"
        )
        
        assert result["ok"] is False
        assert result.get("status") == "needs_clarification"
        logger.info("✓ Ambiguous update correctly asks for clarification")

    def test_update_validates_past_time(
        self, reminder_dao, test_user_id, cleanup_reminders
    ):
        """Update should reject past times"""
        create_test_reminder(reminder_dao, test_user_id, "测试提醒")
        
        improved_update = ImprovedUpdateOperation(reminder_dao)
        
        # Try to set time to 1 hour ago
        past_time = datetime.now() - timedelta(hours=1)
        past_time_str = past_time.strftime("%Y年%m月%d日%H时%M分")
        
        result = improved_update.update_by_keyword_improved(
            test_user_id, "测试", new_trigger_time=past_time_str
        )
        
        assert result["ok"] is False
        assert "未来" in result.get("error", "")
        logger.info("✓ Past time validation works correctly")

    def test_update_validates_empty_title(
        self, reminder_dao, test_user_id, cleanup_reminders
    ):
        """Update should reject empty title"""
        create_test_reminder(reminder_dao, test_user_id, "测试提醒")
        
        improved_update = ImprovedUpdateOperation(reminder_dao)
        result = improved_update.update_by_keyword_improved(
            test_user_id, "测试", new_title=""
        )
        
        # Empty string is falsy, so it fails the validation check
        # and the error message says we need to provide fields
        assert result["ok"] is False
        # The validation catches empty title before it gets to the "空" check
        assert "error" in result
        logger.info(f"✓ Empty title validation works correctly: {result.get('error')}")

    def test_update_single_match(
        self, reminder_dao, test_user_id, cleanup_reminders
    ):
        """Update should work for single clear match"""
        create_test_reminder(reminder_dao, test_user_id, "喝水")
        
        improved_update = ImprovedUpdateOperation(reminder_dao)
        result = improved_update.update_by_keyword_improved(
            test_user_id, "喝水", new_title="多喝水"
        )
        
        assert result["ok"] is True
        assert result["updated_count"] == 1
        
        # Verify the update
        reminders = reminder_dao.find_reminders_by_keyword(test_user_id, "多喝水")
        assert len(reminders) == 1
        assert reminders[0]["title"] == "多喝水"
        logger.info("✓ Single match update works correctly")


# ========== INTEGRATION EXAMPLE ==========


class TestIntegrationExample:
    """Example of how to integrate improvements into the reminder tool"""

    def test_improved_workflow_example(
        self, reminder_dao, test_user_id, cleanup_reminders
    ):
        """
        Demonstrate the improved workflow:
        1. User says "删除开会提醒"
        2. System finds multiple matches
        3. System asks for clarification
        4. User confirms which one
        5. System deletes the correct one
        """
        # Setup
        doc1 = create_test_reminder(reminder_dao, test_user_id, "开会-产品评审")
        doc2 = create_test_reminder(reminder_dao, test_user_id, "开会-技术评审")
        
        improved_delete = ImprovedDeleteOperation(reminder_dao)
        
        # Step 1: User says "删除开会提醒"
        result1 = improved_delete.delete_by_keyword_improved(test_user_id, "开会")
        
        # Step 2: System responds with clarification needed
        assert result1["ok"] is False
        assert result1["status"] == "needs_clarification"
        logger.info(f"System: {result1['message']}")
        for opt in result1["options"]:
            logger.info(f"  - {opt['title']} ({opt['trigger_time']})")
        
        # Step 3: User says "删除产品评审那个"
        # LLM extracts the confirmed_id from context
        confirmed_id = doc1["reminder_id"]
        
        # Step 4: System deletes the correct one
        result2 = improved_delete.delete_by_keyword_improved(
            test_user_id, "开会", confirmed_id=confirmed_id
        )
        
        assert result2["ok"] is True
        logger.info(f"System: {result2['message']}")
        
        # Verify only one deleted
        remaining = reminder_dao.find_reminders_by_user(test_user_id)
        assert len(remaining) == 1
        assert remaining[0]["title"] == "开会-技术评审"
        logger.info("✓ Improved workflow successfully disambiguates and deletes correctly")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
