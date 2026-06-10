"""openCoke agent test-set v6 encoded as executable smoke cases.

Source of truth: ``openCoke-agent-test-set-v6`` (human-authored behavioral
test set for the WeChat personal channel). This module turns each prose case
into a structured, machine-checkable specification.

Verdict model (see ``v6_wechat_smoke``), corrected against the live stack:

* The assistant reply is a hypothesis; the clean Postgres rows are the verdict.
* The HARD verdict is the **row effect** of a turn: which active
  ``reminder`` / ``shared_reminder`` rows were created, cancelled, or updated.
  This is unambiguous and what v6 actually cares about.
* ``staged_command`` is a SOFT signal. Its ``operation`` is an execution-layer
  name, not the planner vocab: a personal-reminder create materializes as
  ``reminder.execute_batch`` / ``reminder.detect_and_create`` / ``reminder.create``;
  a shared create as ``social_scheduling.detect_and_create_shared_reminder`` /
  ``create_shared_reminder``. Read intents (list, availability) produce NO
  ``staged_command`` at all. So we assert at the semantic-bucket + row-effect
  level, never on an exact operation string.
* We never assert reply *wording*. Reply quality is an eval concern.

Product decision baked into this corpus (confirmed 2026-06-11): there is no
separate "calendar event" entity. A personal schedule ("日程") IS a personal
reminder. The v6 D-group ("管理自己的日程") therefore maps onto reminder
operations, not a distinct domain.

Capability gaps (``gap=...``) target behavior the current product does NOT
implement. The smoke records current behavior and treats it as an expected gap,
never as a green pass for the v6-desired behavior. Negative assertions
(``forbid``) are still enforced for gap cases.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

# Semantic forbid tags ("不允许发生" lines). Checked against both the
# materialized staged_command buckets and the row-effect diff.
ForbidTag = Literal["reminder_create", "shared_create", "shared_cancel"]

Outcome = Literal[
    "create_reminder",  # a new active reminder row
    "create_shared",  # a new shared_reminder row
    "query_availability",  # read; reply, no write
    "list_reminders",  # read; reply, no write
    "update_reminder",  # an existing reminder changes; no new row
    "cancel_reminder",  # a reminder goes active -> cancelled
    "cancel_shared",  # a shared_reminder goes active -> cancelled
    "clarify",  # no write; a clarifying reply
    "chat",  # no write; a conversational reply
    "conflict_block",  # write refused (e.g. receiver conflict); no row
]


@dataclass(frozen=True, slots=True)
class FriendFixture:
    """A friend the requester must already have before the message is sent.

    ``alias`` is the name the user types. ``display_name`` is what the friend's
    account resolves to (may differ, e.g. "Oliver Chen" vs typed "Oliver").
    """

    alias: str
    display_name: str


@dataclass(frozen=True, slots=True)
class ReminderFixture:
    """A personal reminder that must already exist for the requester."""

    content: str
    time_phrase: str
    kind: Literal["timed", "recurring"] = "timed"
    duration_minutes: int | None = None


@dataclass(frozen=True, slots=True)
class SharedFixture:
    """A shared reminder that must already exist between requester and friend."""

    friend_alias: str
    title: str
    time_phrase: str


@dataclass(frozen=True, slots=True)
class Fixtures:
    friends: tuple[FriendFixture, ...] = ()
    reminders: tuple[ReminderFixture, ...] = ()
    shared: tuple[SharedFixture, ...] = ()
    # Free/busy blocks the friend must have so availability/conflict cases are
    # deterministic, as (alias, "[今天|明天] HH:MM-HH:MM").
    friend_busy: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class Expect:
    outcome: Outcome
    # "不允许发生": these must NOT happen (enforced for every case incl. gaps).
    forbid: tuple[ForbidTag, ...] = ()
    # A user-visible reply is expected for this turn.
    reply_expected: bool = True
    # For create_reminder: the reminder.kind the row must carry.
    reminder_kind: Literal["timed", "recurring"] | None = None
    # When set, this case targets an unimplemented v6 behavior. The smoke
    # records current behavior and marks the case ``expected_gap`` instead of
    # asserting the v6-desired outcome. Forbids are still enforced.
    gap: str | None = None


@dataclass(frozen=True, slots=True)
class V6Case:
    case_id: str
    group: str
    now_local: str  # documents the v6 当前时间 (Asia/Shanghai); not pinned live
    message: str
    expect: Expect
    fixtures: Fixtures = field(default_factory=Fixtures)
    note: str = ""

    @property
    def needs_friends(self) -> bool:
        return bool(self.fixtures.friends or self.fixtures.friend_busy)


TIMEZONE = "Asia/Shanghai"


CASES: tuple[V6Case, ...] = (
    # ---- A. Personal reminders ------------------------------------------
    V6Case(
        case_id="reminder_001",
        group="A_personal_reminder",
        now_local="2026-06-10 11:30",
        message="明天下午 3 点提醒我给客户发材料",
        expect=Expect(
            outcome="create_reminder", forbid=("shared_create",), reminder_kind="timed"
        ),
        note="A1 explicit time, personal only, must not notify friends",
    ),
    V6Case(
        case_id="reminder_002",
        group="A_personal_reminder",
        now_local="2026-06-10 11:30",
        message="过 10 分钟提醒我看一下锅里的汤",
        expect=Expect(outcome="create_reminder", reminder_kind="timed"),
        note="A2 relative minutes; ~11:40; must not ask 'when'",
    ),
    V6Case(
        case_id="reminder_003",
        group="A_personal_reminder",
        now_local="2026-06-10 11:30",
        message="下周一早上 9 点提醒我看 openCoke 的测试结果",
        expect=Expect(outcome="create_reminder", reminder_kind="timed"),
        note="A3 next Monday 09:00; not this Monday; not recurring",
    ),
    V6Case(
        case_id="reminder_004",
        group="A_personal_reminder",
        now_local="2026-06-10 11:30",
        message="7 月 3 号下午 2 点提醒我续订服务",
        expect=Expect(outcome="create_reminder", reminder_kind="timed"),
        note="A4 specific date 2026-07-03 14:00",
    ),
    V6Case(
        case_id="reminder_005",
        group="A_personal_reminder",
        now_local="2026-06-10 17:30",
        message="8 点提醒我去跑步",
        expect=Expect(
            outcome="create_reminder",
            reminder_kind="timed",
            gap="vague-time best-guess vs clarify both acceptable",
        ),
        note="A5 vague 8 o'clock; context implies tonight 20:00",
    ),
    # ---- B. Recurring reminders -----------------------------------------
    V6Case(
        case_id="recurring_reminder_001",
        group="B_recurring",
        now_local="2026-06-10 11:30",
        message="每周一早上 9 点提醒我看一下项目进展",
        expect=Expect(outcome="create_reminder", reminder_kind="recurring"),
        note="B1 weekly Monday 09:00",
    ),
    V6Case(
        case_id="recurring_reminder_002",
        group="B_recurring",
        now_local="2026-06-10 11:30",
        message="每天晚上 10 点提醒我复盘今天",
        expect=Expect(outcome="create_reminder", reminder_kind="recurring"),
        note="B2 daily 22:00",
    ),
    V6Case(
        case_id="recurring_reminder_003",
        group="B_recurring",
        now_local="2026-06-10 11:30",
        message="工作日每天早上 8 点提醒我看日程",
        expect=Expect(outcome="create_reminder", reminder_kind="recurring"),
        note="B3 weekdays 08:00; one recurring row, not 7",
    ),
    # ---- C. Availability queries ----------------------------------------
    V6Case(
        case_id="availability_001",
        group="C_availability",
        now_local="2026-06-10 11:30",
        message="olivers今天什么时候有空",
        fixtures=Fixtures(
            friends=(FriendFixture("olivers", "Oliver"),),
            friend_busy=(("olivers", "14:00-15:00"),),
        ),
        expect=Expect(outcome="query_availability", forbid=("shared_create",)),
        note="C1 friend free/busy; tolerate spelling 'olivers'",
    ),
    V6Case(
        case_id="availability_002",
        group="C_availability",
        now_local="2026-06-10 11:30",
        message="王五今天什么时候有空？",
        expect=Expect(outcome="clarify", forbid=("shared_create",)),
        note="C2 non-friend; ask to confirm contact, do not fabricate",
    ),
    V6Case(
        case_id="availability_003",
        group="C_availability",
        now_local="2026-06-10 11:30",
        message="Oliver 今天什么时候有空？",
        fixtures=Fixtures(
            friends=(
                FriendFixture("Oliver Chen", "Oliver Chen"),
                FriendFixture("Oliver Wang", "Oliver Wang"),
            ),
        ),
        expect=Expect(outcome="clarify", forbid=("shared_create",)),
        note="C3 ambiguous name; ask which Oliver, no random pick",
    ),
    # ---- D. Self schedule == personal reminder --------------------------
    V6Case(
        case_id="calendar_self_create_001",
        group="D_self_schedule",
        now_local="2026-06-10 07:30",
        message="今天8-9给我建立一个运动的日程",
        expect=Expect(
            outcome="create_reminder", forbid=("shared_create",), reminder_kind="timed"
        ),
        note="D1 self schedule = timed reminder 08:00, 60min duration",
    ),
    V6Case(
        case_id="calendar_self_query_001",
        group="D_self_schedule",
        now_local="2026-06-10 11:30",
        message="我今天有哪些日程",
        fixtures=Fixtures(
            reminders=(
                ReminderFixture("运动", "今天 08:00", duration_minutes=60),
                ReminderFixture("和张三聊 openCoke", "今天 15:00", duration_minutes=60),
            ),
        ),
        expect=Expect(outcome="list_reminders", forbid=("reminder_create",)),
        note="D2 list today's reminders in order",
    ),
    V6Case(
        case_id="calendar_self_create_002",
        group="D_self_schedule",
        now_local="2026-06-10 07:30",
        message="今天8-9给我建立一个运动的日程",
        fixtures=Fixtures(
            reminders=(ReminderFixture("团队会议", "今天 08:30", duration_minutes=60),),
        ),
        expect=Expect(
            outcome="create_reminder",
            reminder_kind="timed",
            gap="self-reminder conflict warning not implemented",
        ),
        note="D3 overlaps existing 08:30-09:30; v6 wants a conflict prompt",
    ),
    V6Case(
        case_id="calendar_self_reschedule_001",
        group="D_self_schedule",
        now_local="2026-06-10 11:30",
        message="把今天运动的日程改到晚上 7 点",
        fixtures=Fixtures(
            reminders=(ReminderFixture("运动", "今天 08:00", duration_minutes=60),),
        ),
        expect=Expect(outcome="update_reminder", forbid=("reminder_create",)),
        note="D4 reschedule the 运动 reminder to 19:00; no second row",
    ),
    V6Case(
        case_id="calendar_self_cancel_001",
        group="D_self_schedule",
        now_local="2026-06-10 11:30",
        message="取消今天运动的日程",
        fixtures=Fixtures(
            reminders=(ReminderFixture("运动", "今天 08:00", duration_minutes=60),),
        ),
        expect=Expect(outcome="cancel_reminder"),
        note="D5 cancel the 运动 reminder only",
    ),
    # ---- E. Scheduling with others --------------------------------------
    V6Case(
        case_id="scheduling_001",
        group="E_scheduling",
        now_local="2026-06-10 11:30",
        message="帮我约张三明天下午 3 点聊一下 openCoke",
        fixtures=Fixtures(friends=(FriendFixture("张三", "张三"),)),
        expect=Expect(outcome="create_shared", forbid=("reminder_create",)),
        note="E1 shared reminder with 张三; notify 张三",
    ),
    V6Case(
        case_id="scheduling_002",
        group="E_scheduling",
        now_local="2026-06-10 11:30",
        message="帮我约张三聊一下 openCoke",
        fixtures=Fixtures(friends=(FriendFixture("张三", "张三"),)),
        expect=Expect(outcome="clarify", forbid=("shared_create", "reminder_create")),
        note="E2 missing time; ask when, do not create/notify",
    ),
    V6Case(
        case_id="scheduling_003",
        group="E_scheduling",
        now_local="2026-06-10 11:30",
        message="帮我约王五明天下午 3 点吃饭",
        expect=Expect(outcome="clarify", forbid=("shared_create",)),
        note="E3 friend 王五 not found; ask to confirm/add",
    ),
    V6Case(
        case_id="scheduling_conflict_001",
        group="E_scheduling",
        now_local="2026-06-10 11:30",
        message="帮我约 Oliver 今天下午 2 点聊 openCoke",
        fixtures=Fixtures(
            friends=(FriendFixture("Oliver", "Oliver"),),
            friend_busy=(("Oliver", "14:00-15:00"),),
        ),
        expect=Expect(
            outcome="conflict_block",
            forbid=("reminder_create",),
            gap="no alternative-time suggestion on receiver conflict",
        ),
        note="E4 KEY UX: v6 wants suggested free slots, product only blocks",
    ),
    V6Case(
        case_id="scheduling_reschedule_001",
        group="E_scheduling",
        now_local="2026-06-10 11:30",
        message="和张三的那个 openCoke 预约改到明天下午 4 点吧",
        fixtures=Fixtures(
            friends=(FriendFixture("张三", "张三"),),
            shared=(SharedFixture("张三", "聊 openCoke", "明天 15:00"),),
        ),
        expect=Expect(
            outcome="cancel_shared",
            gap="no reschedule op; reschedule == cancel+create composite",
        ),
        note="E5 reschedule to 16:00 (no conflict); product has no reschedule",
    ),
    V6Case(
        case_id="scheduling_reschedule_002",
        group="E_scheduling",
        now_local="2026-06-10 11:30",
        message="和张三的那个 openCoke 预约改到明天下午 4 点吧",
        fixtures=Fixtures(
            friends=(FriendFixture("张三", "张三"),),
            shared=(SharedFixture("张三", "聊 openCoke", "明天 15:00"),),
            friend_busy=(("张三", "明天 16:00-17:00"),),
        ),
        expect=Expect(
            outcome="conflict_block",
            forbid=("shared_cancel",),
            gap="no reschedule op; new-time conflict path not modeled",
        ),
        note="E6 reschedule into a conflict; keep old, suggest other time",
    ),
    V6Case(
        case_id="scheduling_cancel_001",
        group="E_scheduling",
        now_local="2026-06-10 11:30",
        message="取消明天下午和张三聊 openCoke 的预约",
        fixtures=Fixtures(
            friends=(FriendFixture("张三", "张三"),),
            shared=(SharedFixture("张三", "聊 openCoke", "明天 15:00"),),
        ),
        expect=Expect(outcome="cancel_shared"),
        note="E7 cancel the shared reminder; notify 张三",
    ),
    V6Case(
        case_id="scheduling_cancel_002",
        group="E_scheduling",
        now_local="2026-06-10 11:30",
        message="取消我和张三的预约",
        fixtures=Fixtures(
            friends=(FriendFixture("张三", "张三"),),
            shared=(
                SharedFixture("张三", "聊 openCoke", "明天 15:00"),
                SharedFixture("张三", "聊融资", "后天 14:00"),
            ),
        ),
        expect=Expect(outcome="clarify", forbid=("shared_cancel",)),
        note="E8 two shared reminders with 张三; ask which to cancel",
    ),
    # ---- F. Chat / no product action ------------------------------------
    V6Case(
        case_id="chat_001",
        group="F_chat",
        now_local="2026-06-10 11:30",
        message="你觉得游泳这个运动怎么样？",
        expect=Expect(outcome="chat", forbid=("reminder_create", "shared_create")),
        note="F1 chat advice; no reminder/schedule",
    ),
    V6Case(
        case_id="chat_002",
        group="F_chat",
        now_local="2026-06-10 11:30",
        message="我最近想开始跑步，你有什么建议？",
        expect=Expect(outcome="chat", forbid=("reminder_create", "shared_create")),
        note="F2 chat advice; '最近' is not a time instruction",
    ),
)


# First-round execution order recommended by the v6 doc.
FIRST_ROUND: tuple[str, ...] = (
    "reminder_002",
    "reminder_003",
    "reminder_005",
    "recurring_reminder_001",
    "recurring_reminder_002",
    "availability_001",
    "calendar_self_create_001",
    "calendar_self_query_001",
    "scheduling_001",
    "scheduling_conflict_001",
    "scheduling_reschedule_001",
    "scheduling_reschedule_002",
    "scheduling_cancel_001",
    "chat_001",
)

# Cases runnable with only a paired requester account (no friend personas).
REQUESTER_ONLY: tuple[str, ...] = tuple(
    c.case_id for c in CASES if not c.needs_friends and not c.fixtures.shared
)


def case_by_id(case_id: str) -> V6Case:
    for case in CASES:
        if case.case_id == case_id:
            return case
    raise KeyError(case_id)
