from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.blocking import BlockingScheduler

from coke import schema
from coke.composition import CokeRuntime, build_runtime_from_settings
from coke.config import Settings
from coke.domains.conversation_runtime.models import OutboxRecord
from coke.domains.reminder.models import ReminderFireGroup
from coke.domains.reminder.scheduler import ReminderScheduler
from coke.infra.tracing import generate_traceparent


LOGGER = logging.getLogger(__name__)


def scan_and_enqueue_due_turns(runtime: CokeRuntime, now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    count = 0
    for group in _due_fire_groups(runtime, now):
        count += _append_outbox(
            runtime,
            topic="turn.reminder_fire",
            idempotency_key=group.trigger_id,
            payload={
                "trigger_id": group.trigger_id,
                "account_id": group.owner_account_id,
                "due_at": group.due_at.isoformat(),
                "fire_ids": list(group.fire_ids),
            },
        )
    for event in _proactive_fire_payloads(runtime, now):
        count += _append_outbox(
            runtime,
            topic="turn.proactive_fire",
            idempotency_key=event["trigger_id"],
            payload=event,
        )
    for event in _nightly_summary_payloads(runtime, now):
        count += _append_outbox(
            runtime,
            topic="turn.nightly_summary",
            idempotency_key=event["trigger_id"],
            payload=event,
        )
    runtime.session.commit()
    return count


def run_scheduler(
    settings: Settings | None = None,
    *,
    runtime: CokeRuntime | None = None,
    run_forever: bool = True,
) -> BlockingScheduler:
    settings = settings or Settings.from_env()
    runtime = runtime or build_runtime_from_settings(settings)
    scheduler = BlockingScheduler(
        timezone="UTC",
        jobstores={
            "default": SQLAlchemyJobStore(url=settings.database_url),
        },
    )
    scheduler.add_job(
        lambda: _scan_with_rollback(runtime),
        "interval",
        seconds=settings.scheduler_interval_s,
        id="coke-runtime-readiness-scan",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    if run_forever:
        scheduler.start()
    return scheduler


def _scan_with_rollback(runtime: CokeRuntime) -> None:
    try:
        scan_and_enqueue_due_turns(runtime)
    except Exception:
        runtime.session.rollback()
        LOGGER.exception("scheduler scan failed")


def _append_outbox(
    runtime: CokeRuntime,
    *,
    topic: str,
    idempotency_key: str,
    payload: dict,
) -> int:
    if _outbox_exists(runtime, idempotency_key):
        return 0
    now = datetime.now(UTC)
    runtime.repositories.conversation_runtime.add_outbox(
        OutboxRecord(
            id=uuid4().hex,
            topic=topic,
            idempotency_key=idempotency_key,
            payload=payload,
            traceparent=generate_traceparent(),
            status="pending",
            created_at=now,
            published_at=None,
            processed_at=None,
            acked_at=None,
            retry_count=0,
            last_error=None,
        )
    )
    return 1


def _outbox_exists(runtime: CokeRuntime, idempotency_key: str) -> bool:
    row = runtime.session.execute(
        sa.select(schema.outbox.c.id).where(
            schema.outbox.c.idempotency_key == idempotency_key
        )
    ).first()
    return row is not None


def _proactive_fire_payloads(runtime: CokeRuntime, now: datetime) -> list[dict]:
    payloads: list[dict] = []
    for reminder in runtime.repositories.reminder.list_due_reminders(now):
        if reminder.kind != "proactive" or reminder.next_fire_at is None:
            continue
        fire = runtime.reminder_service.claim_due_fire(
            reminder_id=reminder.id,
            due_at=reminder.next_fire_at,
        )
        payloads.append(
            {
                "trigger_id": f"proactive_fire:{reminder.owner_account_id}:{fire.id}",
                "account_id": reminder.owner_account_id,
                "fire_id": fire.id,
                "due_at": fire.due_at.isoformat(),
            }
        )
    return payloads


def _due_fire_groups(runtime: CokeRuntime, now: datetime) -> list[ReminderFireGroup]:
    grouped: dict[tuple[str, datetime], list[str]] = {}
    for reminder in runtime.repositories.reminder.list_due_reminders(now):
        if reminder.kind == "proactive" or reminder.next_fire_at is None:
            continue
        fire = runtime.reminder_service.claim_due_fire(
            reminder_id=reminder.id,
            due_at=reminder.next_fire_at,
            missed_catch_up=reminder.next_fire_at < now,
        )
        grouped.setdefault((reminder.owner_account_id, reminder.next_fire_at), []).append(
            fire.id
        )
    return [
        ReminderFireGroup(
            owner_account_id=owner,
            due_at=due_at,
            fire_ids=fire_ids,
            trigger_id=f"reminder_fire:{owner}:{due_at.isoformat()}",
        )
        for (owner, due_at), fire_ids in sorted(grouped.items())
    ]


def _nightly_summary_payloads(runtime: CokeRuntime, now: datetime) -> list[dict]:
    payloads: list[dict] = []
    for account_id in _accounts_with_no_trigger_reminders(runtime):
        timezone = ZoneInfo(_account_timezone(runtime, account_id))
        local_now = now.astimezone(timezone)
        if local_now.hour != 20:
            continue
        summary = ReminderScheduler(
            service=runtime.reminder_service,
            jobstore="postgres",
            account_timezone=lambda _account_id: _account_timezone(
                runtime, _account_id
            ),
        ).nightly_summary_turn(account_id, local_now.date())
        if not summary.reminder_ids:
            continue
        payloads.append(
            {
                "trigger_id": summary.trigger_id,
                "account_id": summary.owner_account_id,
                "local_scheduled_at": summary.local_scheduled_at.isoformat(),
                "reminder_ids": list(summary.reminder_ids),
            }
        )
    return payloads


def _accounts_with_no_trigger_reminders(runtime: CokeRuntime) -> list[str]:
    rows = runtime.session.execute(
        sa.select(schema.reminder.c.owner_account_id)
        .where(
            schema.reminder.c.lifecycle == "active",
            schema.reminder.c.kind == "no_trigger_time",
            schema.reminder.c.next_fire_at.is_(None),
        )
        .distinct()
    )
    return [str(row[0]).replace("-", "") for row in rows]


def _account_timezone(runtime: CokeRuntime, account_id: str) -> str:
    account = runtime.identity_access_service.repository.get_account(account_id)
    return account.default_timezone if account is not None else "UTC"


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    while True:
        try:
            run_scheduler()
            return
        except Exception:
            LOGGER.exception("scheduler crashed before blocking start")
            time.sleep(5.0)


if __name__ == "__main__":
    main()
