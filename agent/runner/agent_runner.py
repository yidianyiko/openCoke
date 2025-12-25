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

# 从环境变量读取 worker 数量，默认 3
NUM_WORKERS = int(os.environ.get("AGENT_WORKERS", 3))


async def run_main_agent(worker_id: int):
    """单个 worker 的消息处理循环"""
    handler = create_handler(worker_id)
    while True:
        await asyncio.sleep(0.5)
        try:
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
