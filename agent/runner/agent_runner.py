import sys
sys.path.append(".")
import asyncio
import os
import logging
from agent.runner.agent_handler import create_handler
from agent.runner.agent_background_handler import background_handler
from dotenv import load_dotenv
load_dotenv()
# 配置日志格式，包含时间戳
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

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