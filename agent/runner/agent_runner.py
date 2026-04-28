import sys

sys.path.append(".")
import asyncio
import os

from dotenv import load_dotenv

load_dotenv()

from agent.runner.deferred_action_executor import DeferredActionExecutor
from agent.runner.deferred_action_scheduler import (
    DeferredActionScheduler,
    get_deferred_action_scheduler_instance,
    set_deferred_action_scheduler_instance,
)
from agent.runner.reminder_event_handler import ReminderFireEventHandler
from agent.runner.reminder_scheduler import (
    ReminderScheduler,
    get_reminder_scheduler_instance,
    set_reminder_scheduler_instance,
)
from util.log_util import get_logger, setup_logging

setup_logging()
logger = get_logger(__name__)

from agent.runner.agent_background_handler import background_handler
from agent.runner.agent_handler import create_handler
from agent.runner.message_processor import consume_stream_batch, get_queue_mode
from dao.deferred_action_dao import DeferredActionDAO
from dao.deferred_action_occurrence_dao import DeferredActionOccurrenceDAO
from dao.reminder_dao import ReminderDAO
from dao.mongo import MongoDBBase
from util.redis_client import RedisClient

try:
    import redis  # type: ignore
except ImportError:  # pragma: no cover - optional dependency until redis is installed
    redis = None


NUM_WORKERS = int(os.environ.get("AGENT_WORKERS", 3))


def bootstrap_deferred_action_runtime():
    existing = get_deferred_action_scheduler_instance()
    if existing is not None:
        return existing

    action_dao = DeferredActionDAO()
    occurrence_dao = DeferredActionOccurrenceDAO()
    executor = DeferredActionExecutor(
        action_dao=action_dao,
        occurrence_dao=occurrence_dao,
        scheduler=None,
    )
    scheduler = DeferredActionScheduler(
        action_dao=action_dao,
        executor=executor.execute_due_action,
    )
    executor.scheduler = scheduler
    set_deferred_action_scheduler_instance(scheduler)
    scheduler.start()
    return scheduler


def bootstrap_reminder_runtime():
    existing = get_reminder_scheduler_instance()
    if existing is not None:
        return existing

    reminder_dao = ReminderDAO()
    handler = ReminderFireEventHandler()
    scheduler = ReminderScheduler(
        reminder_dao=reminder_dao,
        fire_event_handler=handler,
    )
    set_reminder_scheduler_instance(scheduler)
    scheduler.start()
    return scheduler


async def run_main_agent(worker_id: int):
    """单个 worker 的消息处理循环"""
    handler = create_handler(worker_id)
    queue_mode = get_queue_mode()
    redis_client = None
    redis_conf = None
    mongo = None

    if queue_mode == "redis":
        if redis is None:
            logger.error("redis-py 未安装，回退到轮询模式")
            queue_mode = "poll"
        else:
            redis_conf = RedisClient.from_config()
            redis_client = redis.Redis(
                host=redis_conf.host, port=redis_conf.port, db=redis_conf.db
            )
            mongo = MongoDBBase()

    while True:
        try:
            if queue_mode == "redis" and redis_client and redis_conf and mongo:
                consume_stream_batch(
                    redis_client,
                    mongo,
                    group=redis_conf.group,
                    stream=redis_conf.stream_key,
                    consumer=f"worker-{worker_id}",
                )
                await handler()
            else:
                await asyncio.sleep(0.5)
                await handler()
        except Exception as e:
            logger.error(f"[Worker-{worker_id}] Error: {e}")


async def run_background_agent():
    while True:
        await asyncio.sleep(1)
        await background_handler()


async def main():
    deferred_action_scheduler = None
    reminder_scheduler = None
    try:
        deferred_action_scheduler = bootstrap_deferred_action_runtime()
        reminder_scheduler = bootstrap_reminder_runtime()
        workers = [run_main_agent(i) for i in range(NUM_WORKERS)]
        workers.append(run_background_agent())

        logger.info(f"启动 {NUM_WORKERS} 个消息处理 worker")
        await asyncio.gather(*workers)
    finally:
        _shutdown_runtime(
            "deferred action scheduler",
            deferred_action_scheduler,
            set_deferred_action_scheduler_instance,
        )
        _shutdown_runtime(
            "reminder scheduler",
            reminder_scheduler,
            set_reminder_scheduler_instance,
        )


def _shutdown_runtime(name, scheduler, clear_instance):
    try:
        if scheduler is not None:
            scheduler.shutdown()
    except Exception as exc:
        logger.error(f"failed to shutdown {name}: {exc}")
    finally:
        clear_instance(None)


if __name__ == "__main__":
    asyncio.run(main())
