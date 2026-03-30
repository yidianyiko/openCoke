import sys

sys.path.append(".")
import asyncio
import os
from dotenv import load_dotenv
import uvicorn

from agent.runner.agent_background_handler import background_handler
from agent.runner.agent_handler import create_handler
from agent.runner.message_processor import consume_stream_batch, get_queue_mode
from api.app import create_app
from api.delivery import DeliveryService
from api.openclaw_client import OpenClawClient
from conf.config import get_config
from dao.mongo import MongoDBBase
from util.redis_client import RedisClient
from util.log_util import get_logger, setup_logging

load_dotenv()

# 必须在其他模块 import 之前初始化日志配置
setup_logging()
logger = get_logger(__name__)

try:
    import redis  # type: ignore
except ImportError:  # pragma: no cover - optional dependency until redis is installed
    redis = None

# 从环境变量读取 worker 数量，默认 3
NUM_WORKERS = int(os.environ.get("AGENT_WORKERS", 3))
_delivery_service = None


def background_agents_enabled() -> bool:
    """Whether background agents should run in this process."""
    return os.environ.get("DISABLE_BACKGROUND_AGENTS", "false").lower() != "true"


async def run_http_server(app):
    config = uvicorn.Config(app=app, host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


def _install_shared_delivery_service(openclaw_client):
    import agent.runner.agent_handler as agent_handler_module

    delivery_mongo = getattr(agent_handler_module, "mongo", None)
    if delivery_mongo is None:
        delivery_mongo = MongoDBBase()

    delivery_service = DeliveryService(
        mongo=delivery_mongo,
        openclaw_client=openclaw_client,
    )
    agent_handler_module._delivery_service = delivery_service
    return delivery_service


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
    config = get_config()
    gateway_config = config.get("gateway", {})
    openclaw_client = OpenClawClient(
        gateway_config.get("openclaw_url", ""),
        gateway_config.get("openclaw_token", ""),
    )
    await openclaw_client.start()

    app = create_app()
    app.state.openclaw_client = openclaw_client
    _install_shared_delivery_service(openclaw_client)

    workers = [run_main_agent(i) for i in range(NUM_WORKERS)]
    if background_agents_enabled():
        workers.append(run_background_agent())
    workers.append(run_http_server(app))

    logger.info(f"🚀 启动 {NUM_WORKERS} 个消息处理 worker")
    try:
        await asyncio.gather(*workers)
    finally:
        await openclaw_client.stop()


if __name__ == "__main__":
    asyncio.run(main())
