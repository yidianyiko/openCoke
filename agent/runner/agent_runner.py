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


async def run_webhook_server():
    """启动 Webhook 服务器（如果配置了）"""
    from connector.adapters.whatsapp.webhook_server import WebhookServer
    from conf.config import get_config

    config = get_config()

    # 检查 WhatsApp 是否启用
    whatsapp_config = config.get("whatsapp", {})
    if not whatsapp_config.get("enabled", False):
        logger.debug("WhatsApp 未启用，跳过 Webhook 服务器")
        # 保持运行但不启动服务器
        while True:
            await asyncio.sleep(60)
        return

    # 创建 Webhook 服务器
    webhook_config = whatsapp_config.get("webhook", {})
    server = WebhookServer(
        host=webhook_config.get("host", "0.0.0.0"),
        port=webhook_config.get("port", 8081),
    )

    # 根据 api_type 选择适配器
    api_type = whatsapp_config.get("api_type", "evolution")

    if api_type == "evolution":
        # 使用 Evolution API (基于 Baileys，不需要 Meta 开发者账号)
        from connector.adapters.whatsapp.evolution_adapter import EvolutionAdapter

        evolution_config = whatsapp_config.get("evolution", {})
        adapter = EvolutionAdapter(
            api_base=evolution_config.get("api_base", "http://localhost:8080"),
            api_key=evolution_config.get("api_key", ""),
            instance_name=evolution_config.get("instance_name", "coke"),
            webhook_url=evolution_config.get(
                "webhook_url", "http://localhost:8081/webhook/whatsapp"
            ),
            webhook_path=webhook_config.get("path", "/webhook/whatsapp"),
        )
        logger.info("使用 Evolution API (Baileys) 方式集成 WhatsApp")
    else:
        # 使用官方 WhatsApp Cloud API (需要 Meta 开发者账号)
        from connector.adapters.whatsapp.whatsapp_adapter import WhatsAppAdapter

        cloud_config = whatsapp_config.get("cloud_api", {})
        adapter = WhatsAppAdapter(
            phone_number_id=cloud_config.get("phone_number_id"),
            access_token=cloud_config.get("access_token"),
            verify_token=cloud_config.get("verify_token"),
            app_secret=cloud_config.get("app_secret"),
            webhook_path=webhook_config.get("path", "/webhook/whatsapp"),
        )
        logger.info("使用 WhatsApp Cloud API 方式集成 WhatsApp")

    # 设置消息处理回调（保存到 MongoDB）
    async def save_whatsapp_message(message):
        from dao.user_dao import UserDAO
        from entity.message import save_inputmessage
        from util.time_util import get_current_timestamp

        user_dao = UserDAO()

        # 解析用户（从平台 ID 到 MongoDB ObjectId）
        from_user_id = message.from_user
        user = user_dao.find_user_by_platform_id("whatsapp", from_user_id)
        from_user_db_id = str(user["_id"]) if user else None

        to_user_id = message.to_user
        character = user_dao.find_character_by_platform_id("whatsapp", to_user_id)
        to_user_db_id = str(character["_id"]) if character else None

        # 构建 inputmessages 文档
        doc = {
            "input_timestamp": message.timestamp or get_current_timestamp(),
            "handled_timestamp": None,
            "status": "pending",
            "from_user": from_user_db_id,
            "platform": "whatsapp",
            "chatroom_name": message.chatroom_id,
            "to_user": to_user_db_id,
            "message_type": message.message_type.value,
            "message": message.content,
            "metadata": message.metadata,
        }

        # 保存到 MongoDB
        save_inputmessage(doc)
        logger.info(
            f"WhatsApp 消息已保存: from={from_user_id}, " f"message_id={doc.get('_id')}"
        )

    adapter.on_message(save_whatsapp_message)
    server.register_adapter(adapter)

    # 启动适配器和服务器
    await adapter.start()
    await server.start()

    logger.info("Webhook 服务器已启动，按 Ctrl+C 停止")

    # 保持运行
    try:
        while server.is_running:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        logger.info("Webhook 服务器正在停止...")
        await adapter.stop()
        await server.stop()


async def main():
    workers = [run_main_agent(i) for i in range(NUM_WORKERS)]
    workers.append(run_background_agent())
    workers.append(run_webhook_server())

    logger.info(f"🚀 启动 {NUM_WORKERS} 个消息处理 worker")
    await asyncio.gather(*workers)


asyncio.run(main())
