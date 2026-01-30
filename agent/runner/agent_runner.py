import sys

sys.path.append(".")
import asyncio
import os

from dotenv import load_dotenv

load_dotenv()

# 必须在其他模块 import 之前初始化日志配置
from util.log_util import get_logger, setup_logging

setup_logging()
logger = get_logger(__name__)

from agent.runner.agent_background_handler import background_handler
from agent.runner.agent_handler import create_handler
from agent.runner.message_processor import consume_stream_batch, get_queue_mode
from dao.mongo import MongoDBBase
from util.redis_client import RedisClient

try:
    import redis  # type: ignore
except ImportError:  # pragma: no cover - optional dependency until redis is installed
    redis = None

# 从环境变量读取 worker 数量，默认 3
NUM_WORKERS = int(os.environ.get("AGENT_WORKERS", 3))


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
    workers = [run_main_agent(i) for i in range(NUM_WORKERS)]
    workers.append(run_background_agent())

    logger.info(f"🚀 启动 {NUM_WORKERS} 个消息处理 worker")
    await asyncio.gather(*workers)


asyncio.run(main())
