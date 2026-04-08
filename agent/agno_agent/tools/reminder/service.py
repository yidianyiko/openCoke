# -*- coding: utf-8 -*-
"""
ReminderService module for reminder tools.

Provides business logic orchestration for reminder management.
Coordinates between DAO, parser, validator, and formatter to handle
reminder operations.
"""

import json
import time
import uuid
from typing import TYPE_CHECKING, Optional

from util.log_util import get_logger
from util.time_util import validate_timestamp

from .formatter import ReminderFormatter
from .parser import TimeParser
from .validator import ReminderValidator

if TYPE_CHECKING:
    from dao.reminder_dao import ReminderDAO

logger = get_logger(__name__)


def _tz_name(tz) -> str:
    return getattr(tz, "key", "Asia/Shanghai")


class ReminderService:
    """
    Service layer for reminder management operations.

    This class orchestrates the reminder creation process by coordinating
    between the data access layer (DAO), time parser, validator, and formatter.

    Args:
        user_id: User ID for the current operation
        character_id: Character ID for the current operation
        conversation_id: Conversation ID for the current operation
        base_timestamp: Base timestamp for relative time calculations
        session_state: Optional session state containing conversation context

    Attributes:
        dao: ReminderDAO instance for data access
        parser: TimeParser instance for time parsing
        validator: ReminderValidator instance for validation
        formatter: ReminderFormatter instance for response formatting
        user_id: Current user ID
        character_id: Current character ID
        conversation_id: Current conversation ID
        base_timestamp: Base timestamp for time calculations
        session_state: Current session state
    """

    def __init__(
        self,
        user_id: str,
        character_id: str,
        conversation_id: str,
        base_timestamp: Optional[int] = None,
        session_state: Optional[dict] = None,
        dao: Optional["ReminderDAO"] = None,
        user_tz=None,
    ) -> None:
        """
        Initialize the ReminderService with all necessary dependencies.

        Args:
            user_id: User ID for the current operation
            character_id: Character ID for the current operation
            conversation_id: Conversation ID for the current operation
            base_timestamp: Base timestamp for relative time calculations
            session_state: Optional session state containing conversation context
            dao: Optional ReminderDAO instance (for testing/injection)
            user_tz: Optional user timezone (ZoneInfo). Defaults to Asia/Shanghai.
        """
        from dao.reminder_dao import ReminderDAO

        self.dao = dao if dao is not None else ReminderDAO()
        normalized_base_timestamp = validate_timestamp(
            base_timestamp, "base_timestamp", default_to_now=False
        )
        self.parser = TimeParser(base_timestamp=normalized_base_timestamp, tz=user_tz)
        self.validator = ReminderValidator(dao=self.dao, user_id=user_id, tz=user_tz)
        self.formatter = ReminderFormatter(time_parser=self.parser)

        self.user_id = user_id
        self.character_id = character_id
        self.conversation_id = conversation_id
        self.base_timestamp = normalized_base_timestamp
        self.session_state = session_state

    def create(
        self,
        title: Optional[str],
        trigger_time: Optional[str],
        recurrence_type: Optional[str],
        recurrence_interval: Optional[int],
        period_start: Optional[str],
        period_end: Optional[str],
        period_days: Optional[str],
    ) -> dict:
        """
        Create a new reminder.

        This method orchestrates the reminder creation process:
        1. Validates required fields (title)
        2. Parses the trigger time (if provided)
        3. Validates frequency limits for interval-type recurrence
        4. Checks for duplicate reminders
        5. Builds the reminder document
        6. Saves to database
        7. Formats success response

        Args:
            title: Reminder title (required)
            trigger_time: Trigger time string (optional - inbox tasks allowed)
            recurrence_type: Type of recurrence (none/daily/weekly/monthly/interval)
            recurrence_interval: Interval value for recurrence
            period_start: Start time for period-based reminders (HH:MM format)
            period_end: End time for period-based reminders (HH:MM format)
            period_days: Active days for period-based reminders (1-7, comma-separated)

        Returns:
            Dictionary with keys:
                - ok (bool): Whether operation succeeded
                - status (str): Operation status ("created", "duplicate")
                - message (str): Formatted response message
                - reminder_id (str): Created reminder ID (on success)
                - existing_id (str): Existing reminder ID (if duplicate)
                - error (str): Error message (on validation failure)
        """
        # Step 1: Validate required fields
        validation_error = self.validator.check_required_fields(
            title=title, trigger_time=trigger_time
        )
        if validation_error:
            return validation_error

        # Step 2: Parse trigger time
        parsed_time = self.parser.parse(trigger_time) if trigger_time else None

        # Step 3: Parse period configuration
        period_config = self.parser.parse_period_config(
            period_start=period_start,
            period_end=period_end,
            period_days=period_days,
        )
        has_period = period_config is not None

        # Step 4: Validate frequency limits for interval-type recurrence
        if recurrence_type == "interval" and recurrence_interval:
            frequency_error = self.validator.check_frequency_limit(
                recurrence_type=recurrence_type,
                recurrence_interval=recurrence_interval,
                has_period=has_period,
            )
            if frequency_error:
                return frequency_error

        # Step 5: Check for duplicates (only for reminders with trigger time)
        if parsed_time is not None:
            duplicate_result = self.validator.check_duplicate(
                title=title,
                trigger_time=parsed_time,
                recurrence_type=recurrence_type,
            )
            if duplicate_result:
                return duplicate_result

        # Step 6: Build reminder document
        reminder_doc = self._build_reminder_doc(
            title=title,
            trigger_time=parsed_time,
            recurrence_type=recurrence_type,
            recurrence_interval=recurrence_interval,
            period_config=period_config,
        )

        # Step 7: Save to database
        try:
            reminder_id = self.dao.create_reminder(reminder_doc)
        except Exception as e:
            logger.error(f"Failed to create reminder: {e}")
            return {
                "ok": False,
                "error": f"创建提醒失败：{str(e)}",
            }

        # Step 8: Format success response
        reminder_doc["reminder_id"] = reminder_id
        message = self.formatter.create_success(reminder_doc)

        return {
            "ok": True,
            "status": "created",
            "message": message,
            "reminder_id": reminder_id,
        }

    def _build_reminder_doc(
        self,
        title: str,
        trigger_time: Optional[int],
        recurrence_type: Optional[str],
        recurrence_interval: Optional[int],
        period_config: Optional[dict],
    ) -> dict:
        """
        Build a reminder document for database insertion.

        Args:
            title: Reminder title
            trigger_time: Parsed trigger time as Unix timestamp (None for inbox)
            recurrence_type: Type of recurrence
            recurrence_interval: Interval value for recurrence
            period_config: Time period configuration dict

        Returns:
            Dictionary with all reminder fields for database insertion
        """
        current_time = int(time.time())

        # Build recurrence configuration
        if recurrence_type and recurrence_type != "none":
            recurrence = {
                "enabled": True,
                "type": recurrence_type,
                "interval": recurrence_interval or 1,
            }
        else:
            recurrence = {"enabled": False}

        # Determine list_id based on whether trigger time is set
        # Inbox tasks have no trigger time, scheduled reminders do
        list_id = "inbox" if trigger_time is None else "default"

        reminder_doc = {
            "reminder_id": str(uuid.uuid4()),
            "user_id": self.user_id,
            "character_id": self.character_id,
            "conversation_id": self.conversation_id,
            "title": title,
            "next_trigger_time": trigger_time,
            "time_original": None,  # Will be set if needed
            "timezone": _tz_name(self.parser.tz),
            "recurrence": recurrence,
            "time_period": period_config or {"enabled": False},
            "list_id": list_id,
            "status": "active",
            "triggered_count": 0,
            "created_at": current_time,
            "updated_at": current_time,
        }

        return reminder_doc

    def update(
        self,
        keyword: Optional[str],
        new_title: Optional[str],
        new_trigger_time: Optional[str],
        recurrence_type: Optional[str],
        recurrence_interval: Optional[int],
    ) -> dict:
        """
        Update an existing reminder by keyword matching.

        This method orchestrates the reminder update process:
        1. Validates keyword is provided
        2. Validates at least one field to update is provided
        3. Parses new trigger time if provided
        4. Builds update document
        5. Updates matching reminders via DAO
        6. Formats success response

        Args:
            keyword: Keyword to match reminder titles (required)
            new_title: New title for the reminder (optional)
            new_trigger_time: New trigger time string (optional)
            recurrence_type: New recurrence type (optional)
            recurrence_interval: New recurrence interval (optional)

        Returns:
            Dictionary with keys:
                - ok (bool): Whether operation succeeded
                - updated_count (int): Number of reminders updated (on success)
                - updated_reminders (list): List of updated reminders (on success)
                - message (str): Formatted response message
                - error (str): Error message (on validation failure)
        """
        # Step 1: Validate keyword
        if not keyword or not keyword.strip():
            logger.warning(
                f"Update validation failed: missing keyword for user {self.user_id}"
            )
            return {
                "ok": False,
                "error": "更新操作需要提供 keyword（要修改的提醒关键字）",
            }

        keyword = keyword.strip()

        # Step 2: Build update fields and validate at least one field
        update_fields = {}
        update_desc = []

        if new_title:
            update_fields["title"] = new_title
            update_desc.append(f"标题改为「{new_title}」")

        if new_trigger_time:
            parsed_time = self.parser.parse(new_trigger_time)
            if parsed_time is None:
                logger.warning(
                    f"Update validation failed: invalid time '{new_trigger_time}' for user {self.user_id}"
                )
                return {
                    "ok": False,
                    "error": f"无法解析时间: {new_trigger_time}",
                }
            update_fields["next_trigger_time"] = parsed_time
            time_str = self.parser.format_with_date(parsed_time)
            update_desc.append(f"时间改为{time_str}")

        if recurrence_type and recurrence_type != "none":
            update_fields["recurrence"] = {
                "enabled": True,
                "type": recurrence_type,
                "interval": recurrence_interval or 1,
            }
            recurrence_map = {
                "daily": "每天",
                "weekly": "每周",
                "monthly": "每月",
                "yearly": "每年",
                "interval": f"每{recurrence_interval or 1}分钟",
            }
            update_desc.append(
                f"周期改为{recurrence_map.get(recurrence_type, recurrence_type)}"
            )

        if not update_fields:
            logger.warning(
                f"Update validation failed: no fields to update for user {self.user_id}"
            )
            return {
                "ok": False,
                "error": "没有提供要更新的字段（需要 new_title 或 new_trigger_time）",
            }

        # Step 3: Update via DAO
        try:
            updated_count, updated_reminders = self.dao.update_reminders_by_keyword(
                user_id=self.user_id, keyword=keyword, update_data=update_fields
            )

            if updated_count > 0:
                updated_titles = [r.get("title", "") for r in updated_reminders]
                titles_str = "、".join([f"「{t}」" for t in updated_titles[:5]])
                if len(updated_titles) > 5:
                    titles_str += f" 等{len(updated_titles)}个"

                desc_str = "、".join(update_desc) if update_desc else "已更新"
                message = f"提醒修改成功：已更新包含「{keyword}」的提醒 {titles_str}，{desc_str}"
                return {
                    "ok": True,
                    "updated_count": updated_count,
                    "updated_reminders": updated_reminders,
                    "message": message,
                }
            else:
                logger.info(
                    f"Update found no reminders: keyword='{keyword}', user={self.user_id}"
                )
                return {
                    "ok": False,
                    "error": f"没有找到或已经完成了包含「{keyword}」的提醒",
                    "updated_count": 0,
                }

        except Exception as e:
            logger.error(f"Failed to update reminders by keyword '{keyword}': {e}")
            return {
                "ok": False,
                "error": f"更新提醒失败：{str(e)}",
            }

    def delete(self, keyword: Optional[str], session_state: Optional[dict]) -> dict:
        """
        Delete reminders by keyword matching.

        This method orchestrates the reminder deletion process:
        1. Validates keyword is provided
        2. Runs side-effect guard to prevent unintended deletions
        3. Deletes matching reminders via DAO
        4. Formats success response

        Args:
            keyword: Keyword to match reminder titles ("*" for all)
            session_state: Current session state for guard validation

        Returns:
            Dictionary with keys:
                - ok (bool): Whether operation succeeded
                - deleted_count (int): Number of reminders deleted (on success)
                - message (str): Formatted response message
                - error (str): Error message (on validation failure)
                - needs_confirmation (bool): Whether user confirmation is needed
        """
        # Step 1: Validate keyword
        if not keyword or not keyword.strip():
            logger.warning(
                f"Delete validation failed: missing keyword for user {self.user_id}"
            )
            return {
                "ok": False,
                "error": "删除操作需要提供 keyword（要删除的提醒关键字）",
            }

        keyword = keyword.strip()

        # Step 2: Run side-effect guard
        guard = self.validator.guard_side_effect(
            action="delete", keyword=keyword, session_state=session_state
        )
        if not guard.get("allowed"):
            logger.warning(
                f"Delete guard blocked: keyword={keyword}, reason={guard.get('reason')}, user={self.user_id}"
            )
            # Use formatter to generate the guarded response message
            message = self.formatter.guarded_response(guard, action="delete")
            return {
                "ok": False,
                "error": guard.get("error", "操作被阻止"),
                "message": message,
                "needs_confirmation": guard.get("needs_confirmation", False),
                "candidates": guard.get("candidates", []),
            }

        # Use resolved keyword if guard provided one
        if guard.get("resolved_keyword") is not None:
            keyword = guard.get("resolved_keyword")

        # Step 3: Delete via DAO
        try:
            # Support "*" for delete all
            if keyword == "*":
                deleted_count = self.dao.delete_all_by_user(self.user_id)
                message = self.formatter.delete_success(deleted_count, keyword)
                return {
                    "ok": True,
                    "deleted_count": deleted_count,
                    "message": message,
                }

            # Delete by keyword
            deleted_count, deleted_reminders = self.dao.delete_reminders_by_keyword(
                user_id=self.user_id, keyword=keyword
            )

            if deleted_count > 0:
                deleted_titles = [r.get("title", "") for r in deleted_reminders]
                titles_str = "、".join([f"「{t}」" for t in deleted_titles[:5]])
                if len(deleted_titles) > 5:
                    titles_str += f" 等{len(deleted_titles)}个"

                message = f"提醒删除成功：已删除包含「{keyword}」的提醒：{titles_str}"
                return {
                    "ok": True,
                    "deleted_count": deleted_count,
                    "deleted_reminders": deleted_reminders,
                    "message": message,
                }
            else:
                logger.info(
                    f"Delete found no reminders: keyword='{keyword}', user={self.user_id}"
                )
                return {
                    "ok": False,
                    "error": f"没有找到或已经完成了包含「{keyword}」的提醒",
                    "deleted_count": 0,
                }

        except Exception as e:
            logger.error(f"Failed to delete reminders by keyword '{keyword}': {e}")
            return {
                "ok": False,
                "error": f"删除提醒失败：{str(e)}",
            }

    def complete(self, keyword: Optional[str], session_state: Optional[dict]) -> dict:
        """
        Complete reminders by keyword matching.

        This method orchestrates the reminder completion process:
        1. Validates keyword is provided
        2. Runs side-effect guard to prevent unintended completions
        3. Marks matching reminders as completed via DAO
        4. Formats success response

        Args:
            keyword: Keyword to match reminder titles (required)
            session_state: Current session state for guard validation

        Returns:
            Dictionary with keys:
                - ok (bool): Whether operation succeeded
                - completed_count (int): Number of reminders completed (on success)
                - completed_reminders (list): List of completed reminders (on success)
                - message (str): Formatted response message
                - error (str): Error message (on validation failure)
                - needs_confirmation (bool): Whether user confirmation is needed
        """
        # Step 1: Validate keyword
        if not keyword or not keyword.strip():
            logger.warning(
                f"Complete validation failed: missing keyword for user {self.user_id}"
            )
            return {
                "ok": False,
                "error": "完成操作需要提供 keyword（要完成的提醒关键字）",
            }

        keyword = keyword.strip()

        # Step 2: Run side-effect guard
        guard = self.validator.guard_side_effect(
            action="complete", keyword=keyword, session_state=session_state
        )
        if not guard.get("allowed"):
            logger.warning(
                f"Complete guard blocked: keyword={keyword}, reason={guard.get('reason')}, user={self.user_id}"
            )
            # Use formatter to generate the guarded response message
            message = self.formatter.guarded_response(guard, action="complete")
            return {
                "ok": False,
                "error": guard.get("error", "操作被阻止"),
                "message": message,
                "needs_confirmation": guard.get("needs_confirmation", False),
                "candidates": guard.get("candidates", []),
            }

        # Use resolved keyword if guard provided one
        if guard.get("resolved_keyword") is not None:
            keyword = guard.get("resolved_keyword")

        # Step 3: Complete via DAO
        try:
            completed_count, completed_reminders = (
                self.dao.complete_reminders_by_keyword(
                    user_id=self.user_id, keyword=keyword
                )
            )

            if completed_count > 0:
                completed_titles = [r.get("title", "") for r in completed_reminders]
                titles_str = "、".join([f"「{t}」" for t in completed_titles[:5]])
                if len(completed_titles) > 5:
                    titles_str += f" 等{len(completed_titles)}个"

                message = f"提醒完成成功：已完成包含「{keyword}」的提醒：{titles_str}"
                return {
                    "ok": True,
                    "completed_count": completed_count,
                    "completed_reminders": completed_reminders,
                    "message": message,
                }
            else:
                logger.info(
                    f"Complete found no reminders: keyword='{keyword}', user={self.user_id}"
                )
                return {
                    "ok": False,
                    "error": f"没有找到或已经完成了包含「{keyword}」的提醒",
                    "completed_count": 0,
                }

        except Exception as e:
            logger.error(f"Failed to complete reminders by keyword '{keyword}': {e}")
            return {
                "ok": False,
                "error": f"完成提醒失败：{str(e)}",
            }

    def filter(
        self,
        status: Optional[str],
        reminder_type: Optional[str],
        keyword: Optional[str],
        trigger_after: Optional[str],
        trigger_before: Optional[str],
    ) -> dict:
        """
        Query/filter reminders with flexible criteria.

        This method orchestrates the reminder filtering process:
        1. Parses status parameter (JSON string or single value)
        2. Parses time range parameters if provided
        3. Queries reminders via DAO
        4. Formats results grouped by type (scheduled vs inbox)

        Args:
            status: Status filter as JSON string (e.g., '["active"]') or single value
            reminder_type: Type filter ("one_time" or "recurring")
            keyword: Keyword to search in titles
            trigger_after: Time range start (string to parse)
            trigger_before: Time range end (string to parse)

        Returns:
            Dictionary with keys:
                - ok (bool): Whether operation succeeded
                - status (str): Operation status ("success")
                - reminders (list): List of filtered reminders
                - count (int): Number of reminders found
                - message (str): Formatted response message
                - error (str): Error message (on failure)
        """
        try:
            # Step 1: Parse status parameter
            status_list = None
            if status:
                try:
                    status_list = json.loads(status)
                    if not isinstance(status_list, list):
                        status_list = [status_list]
                except json.JSONDecodeError:
                    # If not JSON, treat as single status
                    status_list = [status]

            # Step 2: Parse time range parameters
            trigger_after_ts = None
            trigger_before_ts = None

            if trigger_after:
                trigger_after_ts = self.parser.parse(trigger_after)
                if trigger_after_ts is None:
                    logger.warning(f"Failed to parse trigger_after: {trigger_after}")

            if trigger_before:
                trigger_before_ts = self.parser.parse(trigger_before)
                if trigger_before_ts is None:
                    logger.warning(f"Failed to parse trigger_before: {trigger_before}")

            # Step 3: Query via DAO
            reminders = self.dao.filter_reminders(
                user_id=self.user_id,
                status_list=status_list,
                reminder_type=reminder_type,
                keyword=keyword,
                trigger_after=trigger_after_ts,
                trigger_before=trigger_before_ts,
            )

            # Step 4: Format results
            message = self.formatter.filter_result(reminders)

            return {
                "ok": True,
                "status": "success",
                "reminders": reminders,
                "count": len(reminders),
                "message": message,
            }

        except Exception as e:
            logger.error(f"Failed to filter reminders: {e}")
            return {
                "ok": False,
                "error": f"筛选提醒失败：{str(e)}",
            }

    def close(self) -> None:
        """
        Close the DAO connection.

        This method should be called when the service is no longer needed
        to properly release database resources.
        """
        if self.dao:
            self.dao.close()

    def batch(self, operations: str) -> dict:
        """
        Execute multiple reminder operations in a single batch.

        This method parses a JSON array of operations and executes them sequentially.
        Batch operations skip side-effect guards since user intent is explicit.

        Args:
            operations: JSON string containing array of operation dicts

        Returns:
            Dictionary with keys:
                - ok (bool): Whether batch operation completed
                - total (int): Total number of operations
                - succeeded (int): Number of successful operations
                - failed (int): Number of failed operations
                - results (list): List of individual operation results
                - error (str): Error message (if JSON parsing failed)

        Operation format:
            [
                {"action": "create", "title": "...", "trigger_time": "...", ...},
                {"action": "update", "keyword": "...", "new_title": "...", ...},
                {"action": "delete", "keyword": "..."},
                {"action": "complete", "keyword": "..."}
            ]
        """
        try:
            ops_list = json.loads(operations)
        except json.JSONDecodeError as e:
            return {
                "ok": False,
                "error": f"操作列表格式错误: {str(e)}",
            }

        if not isinstance(ops_list, list):
            return {
                "ok": False,
                "error": "操作列表必须是数组格式",
            }

        results = []
        succeeded = 0
        failed = 0

        for op in ops_list:
            if not isinstance(op, dict):
                results.append(
                    {
                        "ok": False,
                        "error": "操作必须是对象格式",
                    }
                )
                failed += 1
                continue

            action = op.get("action")

            if action == "create":
                result = self._batch_create(op)
            elif action == "update":
                result = self._batch_update(op)
            elif action == "delete":
                result = self._batch_delete(op)
            elif action == "complete":
                result = self._batch_complete(op)
            else:
                result = {
                    "ok": False,
                    "error": f"未知操作: {action}",
                }

            results.append(result)
            if result.get("ok"):
                succeeded += 1
            else:
                failed += 1

        return {
            "ok": True,
            "total": len(ops_list),
            "succeeded": succeeded,
            "failed": failed,
            "results": results,
        }

    def _batch_create(self, op: dict) -> dict:
        """
        Execute create operation within batch (skips side-effect guard).

        Args:
            op: Operation dict with create parameters

        Returns:
            Result dict from create operation
        """
        # Validate required fields
        validation_error = self.validator.check_required_fields(
            title=op.get("title"), trigger_time=op.get("trigger_time")
        )
        if validation_error:
            return validation_error

        # Parse trigger_time if provided
        trigger_time = op.get("trigger_time")
        if trigger_time:
            parsed_time = self.parser.parse(trigger_time)
        else:
            parsed_time = None

        # Parse period config if provided
        period_config = self.parser.parse_period_config(
            period_start=op.get("period_start"),
            period_end=op.get("period_end"),
            period_days=op.get("period_days"),
        )

        # Check frequency limit for interval type
        recurrence_type = op.get("recurrence_type")
        recurrence_interval = op.get("recurrence_interval")
        has_period = period_config is not None

        if recurrence_type == "interval" and recurrence_interval:
            frequency_error = self.validator.check_frequency_limit(
                recurrence_type=recurrence_type,
                recurrence_interval=recurrence_interval,
                has_period=has_period,
            )
            if frequency_error:
                return frequency_error

        # Check for duplicates (only if trigger time is set)
        if parsed_time is not None:
            duplicate_result = self.validator.check_duplicate(
                title=op.get("title"),
                trigger_time=parsed_time,
                recurrence_type=recurrence_type,
            )
            if duplicate_result:
                return duplicate_result

        # Build and create reminder
        reminder_doc = self._build_reminder_doc(
            title=op.get("title"),
            trigger_time=parsed_time,
            recurrence_type=recurrence_type,
            recurrence_interval=recurrence_interval,
            period_config=period_config,
        )

        try:
            reminder_id = self.dao.create_reminder(reminder_doc)
            reminder_doc["reminder_id"] = reminder_id
            return {
                "ok": True,
                "status": "created",
                "reminder_id": reminder_id,
            }
        except Exception as e:
            logger.error(f"Batch create failed: {e}")
            return {
                "ok": False,
                "error": f"创建失败: {str(e)}",
            }

    def _batch_update(self, op: dict) -> dict:
        """
        Execute update operation within batch (skips side-effect guard).

        Args:
            op: Operation dict with update parameters

        Returns:
            Result dict from update operation
        """
        keyword = op.get("keyword")
        if not keyword or not keyword.strip():
            return {
                "ok": False,
                "error": "更新操作需要提供 keyword",
            }

        update_fields = {}
        new_title = op.get("new_title")
        new_trigger_time = op.get("new_trigger_time")
        recurrence_type = op.get("recurrence_type")
        recurrence_interval = op.get("recurrence_interval")

        if new_title:
            update_fields["title"] = new_title

        if new_trigger_time:
            parsed_time = self.parser.parse(new_trigger_time)
            if parsed_time is None:
                return {
                    "ok": False,
                    "error": f"无法解析时间: {new_trigger_time}",
                }
            update_fields["next_trigger_time"] = parsed_time

        if recurrence_type and recurrence_type != "none":
            update_fields["recurrence"] = {
                "enabled": True,
                "type": recurrence_type,
                "interval": recurrence_interval or 1,
            }

        if not update_fields:
            return {
                "ok": False,
                "error": "没有提供要更新的字段",
            }

        try:
            updated_count, _ = self.dao.update_reminders_by_keyword(
                user_id=self.user_id, keyword=keyword.strip(), update_data=update_fields
            )
            if updated_count > 0:
                return {
                    "ok": True,
                    "updated_count": updated_count,
                }
            else:
                return {
                    "ok": False,
                    "error": f"没有找到包含「{keyword}」的提醒",
                }
        except Exception as e:
            logger.error(f"Batch update failed: {e}")
            return {
                "ok": False,
                "error": f"更新失败: {str(e)}",
            }

    def _batch_delete(self, op: dict) -> dict:
        """
        Execute delete operation within batch (skips side-effect guard).

        Args:
            op: Operation dict with delete parameters

        Returns:
            Result dict from delete operation
        """
        keyword = op.get("keyword")
        if not keyword or not keyword.strip():
            return {
                "ok": False,
                "error": "删除操作需要提供 keyword",
            }

        keyword = keyword.strip()

        try:
            if keyword == "*":
                deleted_count = self.dao.delete_all_by_user(self.user_id)
                return {
                    "ok": True,
                    "deleted_count": deleted_count,
                }

            deleted_count, _ = self.dao.delete_reminders_by_keyword(
                user_id=self.user_id, keyword=keyword
            )

            if deleted_count > 0:
                return {
                    "ok": True,
                    "deleted_count": deleted_count,
                }
            else:
                return {
                    "ok": False,
                    "error": f"没有找到包含「{keyword}」的提醒",
                }
        except Exception as e:
            logger.error(f"Batch delete failed: {e}")
            return {
                "ok": False,
                "error": f"删除失败: {str(e)}",
            }

    def _batch_complete(self, op: dict) -> dict:
        """
        Execute complete operation within batch (skips side-effect guard).

        Args:
            op: Operation dict with complete parameters

        Returns:
            Result dict from complete operation
        """
        keyword = op.get("keyword")
        if not keyword or not keyword.strip():
            return {
                "ok": False,
                "error": "完成操作需要提供 keyword",
            }

        keyword = keyword.strip()

        try:
            completed_count, _ = self.dao.complete_reminders_by_keyword(
                user_id=self.user_id, keyword=keyword
            )

            if completed_count > 0:
                return {
                    "ok": True,
                    "completed_count": completed_count,
                }
            else:
                return {
                    "ok": False,
                    "error": f"没有找到包含「{keyword}」的提醒",
                }
        except Exception as e:
            logger.error(f"Batch complete failed: {e}")
            return {
                "ok": False,
                "error": f"完成失败: {str(e)}",
            }
