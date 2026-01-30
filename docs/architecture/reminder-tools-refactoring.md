# Reminder Tools Architecture

## Overview

The reminder tool was refactored from a monolithic 2900-line file into a layered architecture for better maintainability. The refactoring preserves all existing behavior while clearly separating concerns.

**Refactored:** January 2026

## Architecture

```
agent/agno_agent/tools/
├── reminder_tools.py          # Thin @tool entry point (421 lines)
└── reminder/                   # Business logic modules (2123 lines)
    ├── __init__.py            # Package exports (25 lines)
    ├── service.py             # Orchestration layer (697 lines)
    ├── parser.py              # Time parsing (177 lines)
    ├── validator.py           # Validation rules (523 lines)
    └── formatter.py           # Response formatting (362 lines)
```

**Before:** 2,939 lines in a single file
**After:** 2,544 lines total across 5 focused modules (13% reduction, much better organization)

## Layer Responsibilities

### Tool Layer (`reminder_tools.py`)

**Purpose:** LLM interface and async session management

**Responsibilities:**
- `@tool` decorator with LLM-friendly description
- `contextvars` session state management (async isolation)
- Parameter adaptation (LLM → service)
- Action routing (`create`, `update`, `delete`, `filter`, `complete`, `batch`, `list`)
- Session result writing for Agent context

**Key exports:**
- `reminder_tool()` - Main tool entry point
- `set_reminder_session_state()` - External session state injection

### Service Layer (`service.py`)

**Purpose:** Business logic orchestration

**Responsibilities:**
- Coordinates parser, validator, formatter, and DAO
- Implements all CRUD operations (`create`, `update`, `delete`, `complete`, `filter`)
- Batch operation handling with partial failure support
- Document building for database insertion

**Key class:**
```python
class ReminderService:
    def __init__(self, user_id, character_id, conversation_id,
                 base_timestamp=None, session_state=None, dao=None)
    def create(...) -> dict
    def update(...) -> dict
    def delete(...) -> dict
    def complete(...) -> dict
    def filter(...) -> dict
    def batch(operations) -> dict
    def close() -> None
```

### Parser Module (`parser.py`)

**Purpose:** Time parsing and formatting

**Responsibilities:**
- Relative time parsing ("30分钟后", "明天")
- Absolute time parsing ("2025年1月31日15时00分")
- Time formatting (friendly: "3分钟后", with-date: "1月31日 星期五 下午3点")
- Period configuration parsing for time-range reminders

**Key class:**
```python
class TimeParser:
    def parse(time_str: Optional[str]) -> Optional[int]
    def format_friendly(timestamp: int) -> str
    def format_with_date(timestamp: int) -> str
    def parse_period_config(period_start, period_end, period_days) -> Optional[dict]
```

### Validator Module (`validator.py`)

**Purpose:** Validation rules and side-effect guards

**Responsibilities:**
- Required field validation (title is required)
- Frequency limit checking (interval recurrence limits)
- Duplicate reminder detection (time tolerance matching)
- Side-effect guards for destructive operations (delete, complete)
- Operation allowance checking (prevents circular calls)

**Key class:**
```python
class ReminderValidator:
    MIN_INTERVAL_INFINITE = 60      # Minimum minutes for unbounded interval
    MIN_INTERVAL_PERIOD = 25        # Minimum minutes for period-constrained interval
    TIME_TOLERANCE = 60             # Seconds for duplicate detection
    DELETE_ALL_WORDS = [...]         # Keywords indicating delete-all intent

    def check_required_fields(title, trigger_time) -> Optional[dict]
    def check_frequency_limit(recurrence_type, recurrence_interval, has_period) -> Optional[dict]
    def check_duplicate(title, trigger_time, recurrence_type, tolerance) -> Optional[dict]
    def guard_side_effect(action, keyword, session_state) -> dict
```

### Formatter Module (`formatter.py`)

**Purpose:** Response message building

**Responsibilities:**
- Success message formatting for all operations
- Error message formatting
- List/result display with grouped sections (scheduled vs inbox)
- Batch summary generation
- Guarded response formatting (when side-effect guard blocks)

**Key class:**
```python
class ReminderFormatter:
    def create_success(reminder) -> dict
    def update_success(updated_count, updated_reminders) -> dict
    def delete_success(deleted_count, keyword) -> str
    def complete_success(completed_count, completed_reminders) -> dict
    def filter_result(reminders) -> str
    def batch_summary(total, succeeded, failed) -> str
    def guarded_response(candidates, action) -> str
```

## Call Flow

```
LLM Request
    │
    ▼
reminder_tool() [Tool Layer]
    │  • contextvars session state
    │  • Action routing
    │  • Parameter adaptation
    ▼
ReminderService [Service Layer]
    │  • Business logic orchestration
    │  • Coordinates components
    ▼
    ├── TimeParser      → Parse/format times
    ├── ReminderValidator → Validate rules, check guards
    ├── ReminderFormatter → Build responses
    └── ReminderDAO     → Database operations
```

## Key Design Decisions

### 1. Single Tool Entry

Kept a single `@tool` decorator for LLM simplicity. The LLM sees one tool with an `action` parameter, reducing cognitive load compared to multiple separate tools.

### 2. Async Isolation with contextvars

Preserved the original `contextvars` pattern for session state management. This ensures isolation between different async contexts, preventing cross-user data contamination in asyncio concurrent processing.

```python
_context_session_state: contextvars.ContextVar[dict] = contextvars.ContextVar(
    "session_state", default={}
)
```

### 3. Dependency Injection

The `ReminderService` receives DAO as a constructor parameter, not hardcoded. This enables clean testing with mock DAOs.

```python
service = ReminderService(
    user_id="user123",
    character_id="char456",
    conversation_id="conv789",
    dao=Mock(),  # Test injection
)
```

### 4. Side-Effect Guards

Destructive operations (delete, complete) are protected by guards that verify user intent against their actual message text. This prevents accidental deletions from LLM hallucinations.

```python
guard = validator.guard_side_effect(
    action="delete",
    keyword="开会",
    session_state=session_state,  # Contains user's original message
)
```

### 5. Backward Compatibility

All existing behavior is preserved:
- "list" action redirects to "filter"
- Session state keys remain unchanged
- Response format unchanged
- All original tests pass

## Usage

### Via Tool (LLM)

```python
from agent.agno_agent.tools.reminder_tools import reminder_tool

# LLM calls this with action parameter
result = reminder_tool(
    action="create",
    title="开会",
    trigger_time="明天下午3点",
    session_state=session_state,
)
```

### Direct Service Usage

```python
from agent.agno_agent.tools.reminder import ReminderService

service = ReminderService(
    user_id="user123",
    character_id="char456",
    conversation_id="conv789",
    base_timestamp=int(time.time()),
    session_state=session_state,
)

result = service.create(
    title="Meeting",
    trigger_time="明天下午3点",
)

service.close()  # Always close to release DAO connection
```

## Testing

### Test Structure

```
tests/unit/reminder/
├── test_parser.py      # TimeParser tests (14 tests)
├── test_formatter.py   # ReminderFormatter tests (14 tests)
├── test_validator.py   # ReminderValidator tests (33 tests)
└── test_service.py     # ReminderService tests (65 tests)

tests/unit/
├── test_reminder_tools_duplicate_message.py
├── test_reminder_tools_gtd.py
└── test_reminder_tools_side_effect_guard.py
```

### Running Tests

```bash
# Unit tests only (no MongoDB required)
pytest tests/unit/reminder/ -v
pytest tests/unit/test_reminder_*.py -v

# All reminder tests
pytest tests/unit/reminder/ tests/unit/test_reminder_*.py -v

# Integration tests (requires MongoDB)
pytest tests/integration/test_reminder*.py -v
```

**Test Count:** 135 tests total (all passing)

## GTD Support

The reminder system supports GTD-style task collection:

- **Inbox tasks:** Tasks without `trigger_time` are stored with `list_id="inbox"`
- **Quick capture:** Users can create tasks without specifying a time
- **Display separation:** Filter results show scheduled reminders and inbox tasks separately

```python
# Creates inbox task (no time)
service.create(title="Buy milk", trigger_time=None)

# Creates scheduled reminder
service.create(title="Meeting", trigger_time="明天9点")
```

## Migration Notes

If you were previously using internal functions directly:

| Old Function | New Location |
|-------------|--------------|
| `_parse_time()` | `TimeParser.parse()` |
| `_format_time_friendly()` | `TimeParser.format_friendly()` |
| `_check_required_fields()` | `ReminderValidator.check_required_fields()` |
| `_create_reminder()` | `ReminderService.create()` |
| `_batch_operations()` | `ReminderService.batch()` |
