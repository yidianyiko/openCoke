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

import time
import traceback

from agent.runner.agent_background_handler import background_handler
from agent.runner.agent_handler import create_handler
from agent.runner.message_processor import consume_stream_batch, get_queue_mode
from dao.mongo import MongoDBBase
from dao.user_dao import UserDAO
from entity.message import save_outputmessage
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


async def whatsapp_output_handler(adapter):
    """轮询 outputmessages 并通过 Evolution API 发送 WhatsApp 消息"""
    mongo = MongoDBBase()
    user_dao = UserDAO()

    while True:
        await asyncio.sleep(1)
        try:
            now = int(time.time())
            message = mongo.find_one(
                "outputmessages",
                {
                    "platform": "whatsapp",
                    "status": "pending",
                    "expect_output_timestamp": {"$lte": now},
                },
            )
            if message is None:
                continue

            logger.info(f"WhatsApp 发送消息: {message}")

            # 查找收件人
            user = user_dao.get_user_by_id(message["to_user"])
            if user is None:
                raise Exception(f"user not found: {message['to_user']}")

            # 确定发送目标 JID
            if message.get("chatroom_name"):
                # 群聊：发送到群 JID
                target_jid = message["chatroom_name"]
            else:
                # 私聊：从用户的 WhatsApp 平台信息获取 JID
                whatsapp_info = user.get("platforms", {}).get("whatsapp", {})
                target_jid = whatsapp_info.get("id")
                if not target_jid:
                    raise Exception(
                        f"user {message['to_user']} missing whatsapp id"
                    )

            # 发送文本消息
            success = await adapter.send_text(target_jid, message["message"])

            # 更新状态
            message["status"] = "handled" if success else "failed"
            message["handled_timestamp"] = int(time.time())
            save_outputmessage(message)

        except Exception:
            logger.error(traceback.format_exc())
            try:
                message["status"] = "failed"
                message["handled_timestamp"] = int(time.time())
                save_outputmessage(message)
            except Exception:
                pass


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

    # 设置消息处理回调（保存到 MongoDB + 发布到 Redis Stream）
    async def save_whatsapp_message(message):
        import time

        from dao.mongo import MongoDBBase
        from dao.user_dao import UserDAO
        from util.redis_client import RedisClient
        from util.redis_stream import publish_input_event
        from util.time_util import get_current_timestamp

        user_dao = UserDAO()
        mongo = MongoDBBase()

        # 解析发送者（从平台 ID 查找或自动创建）
        from_user_id = message.from_user
        user = user_dao.get_user_by_platform("whatsapp", from_user_id)
        if not user:
            # 自动创建用户
            push_name = message.metadata.get("raw_message", {}).get("pushName", from_user_id.split("@")[0])
            new_user = {
                "name": push_name,
                "platforms": {
                    "whatsapp": {
                        "id": from_user_id,
                        "account": from_user_id,
                        "nickname": push_name,
                    }
                },
                "status": "normal",
            }
            from_user_db_id = user_dao.upsert_user(
                {"platforms.whatsapp.id": from_user_id}, new_user
            )
            logger.info(f"WhatsApp 自动创建用户: {push_name} -> {from_user_db_id}")
        else:
            from_user_db_id = str(user["_id"])

        # 解析目标角色
        from conf.config import get_config
        config = get_config()
        character_alias = config.get("default_character_alias", "qiaoyun")
        characters = user_dao.find_characters({"name": character_alias})
        to_user_db_id = str(characters[0]["_id"]) if characters else None

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

        # 插入到数据库
        inserted_id = mongo.insert_one("inputmessages", doc)

        # 发布到 Redis Stream，让 worker 消费
        try:
            redis_conf = RedisClient.from_config()
            import redis as redis_lib

            r = redis_lib.Redis(
                host=redis_conf.host, port=redis_conf.port, db=redis_conf.db
            )
            publish_input_event(
                r,
                inserted_id,
                "whatsapp",
                int(doc.get("input_timestamp", time.time())),
                stream_key=redis_conf.stream_key,
            )
        except Exception as e:
            logger.error(f"发布 Redis Stream 事件失败: {e}")

        logger.info(
            f"WhatsApp 消息已保存: from={from_user_id}, "
            f"message_id={inserted_id}"
        )

    adapter.on_message(save_whatsapp_message)
    server.register_adapter(adapter)

    # 启动适配器和服务器
    await adapter.start()
    await server.start()

    logger.info("Webhook 服务器已启动，按 Ctrl+C 停止")

    # 启动输出消息轮询
    output_task = asyncio.create_task(whatsapp_output_handler(adapter))

    # 保持运行
    try:
        while server.is_running:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        output_task.cancel()
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
