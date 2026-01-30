# -*- coding: utf-8 -*-
"""
ReminderService module for reminder tools.

Provides business logic orchestration for reminder management.
Coordinates between DAO, parser, validator, and formatter to handle
reminder operations.
"""

import time
import uuid
from typing import TYPE_CHECKING, Optional

from util.log_util import get_logger

from .formatter import ReminderFormatter
from .parser import TimeParser
from .validator import ReminderValidator

if TYPE_CHECKING:
    from dao.reminder_dao import ReminderDAO

logger = get_logger(__name__)


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
        """
        from dao.reminder_dao import ReminderDAO

        self.dao = dao if dao is not None else ReminderDAO()
        self.parser = TimeParser(base_timestamp=base_timestamp)
        self.validator = ReminderValidator(dao=self.dao, user_id=user_id)
        self.formatter = ReminderFormatter(time_parser=self.parser)

        self.user_id = user_id
        self.character_id = character_id
        self.conversation_id = conversation_id
        self.base_timestamp = base_timestamp
        self.session_state = session_state

    def create(
        self,
        title: Optional[str],
        trigger_time: Optional[str],
        action_template: Optional[str],
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
            action_template: Action message template for the reminder
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
            action_template=action_template or f"提醒：{title}",
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
        action_template: str,
        recurrence_type: Optional[str],
        recurrence_interval: Optional[int],
        period_config: Optional[dict],
    ) -> dict:
        """
        Build a reminder document for database insertion.

        Args:
            title: Reminder title
            trigger_time: Parsed trigger time as Unix timestamp (None for inbox)
            action_template: Action message template
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
            "action_template": action_template,
            "next_trigger_time": trigger_time,
            "time_original": None,  # Will be set if needed
            "timezone": "Asia/Shanghai",
            "recurrence": recurrence,
            "time_period": period_config or {"enabled": False},
            "list_id": list_id,
            "status": "active",
            "triggered_count": 0,
            "created_at": current_time,
            "updated_at": current_time,
        }

        return reminder_doc

    def close(self) -> None:
        """
        Close the DAO connection.

        This method should be called when the service is no longer needed
        to properly release database resources.
        """
        if self.dao:
            self.dao.close()
