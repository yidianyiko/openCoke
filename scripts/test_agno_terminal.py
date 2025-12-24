# -*- coding: utf-8 -*-
"""
Agno Terminal 集成测试脚本

使用 Terminal Connector 测试 Agno Workflow 的完整流程.

Usage:
    python scripts/test_agno_terminal.py

测试流程：
1. 启动 handler 循环
2. 在另一个终端运行 terminal_input.py 发送消息
3. 在另一个终端运行 terminal_output.py 查看回复
"""
import sys
sys.path.append(".")

# 加载 .env 文件
from dotenv import load_dotenv
load_dotenv()

import os
import asyncio
import logging
from logging import getLogger

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = getLogger(__name__)


async def run_handler_loop():
    """运行 handler 循环"""
    from agent.runner.agent_handler import handler
    
    logger.info("=" * 60)
    logger.info("Agno Terminal 集成测试")
    logger.info("=" * 60)
    logger.info("")
    logger.info("测试步骤：")
    logger.info("1. 在另一个终端运行: python connector/terminal/terminal_input.py")
    logger.info("2. 在另一个终端运行: python connector/terminal/terminal_output.py")
    logger.info("3. 在 terminal_input 中输入消息，观察 terminal_output 的回复")
    logger.info("")
    logger.info("按 Ctrl+C 停止测试")
    logger.info("=" * 60)
    
    while True:
        try:
            await handler()
            await asyncio.sleep(1)  # 每秒检查一次新消息
        except KeyboardInterrupt:
            logger.info("测试停止")
            break
        except Exception as e:
            logger.error(f"Handler error: {e}")
            await asyncio.sleep(1)


async def run_single_test():
    """运行单次测试（用于调试）"""
    from agent.runner.agent_handler import handler
    
    logger.info("运行单次测试")
    await handler()
    logger.info("单次测试完成")


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Agno Terminal 集成测试')
    parser.add_argument('--single', action='store_true', help='只运行一次（用于调试）')
    parser.add_argument('--verbose', '-v', action='store_true', help='显示详细日志')
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    if args.single:
        asyncio.run(run_single_test())
    else:
        asyncio.run(run_handler_loop())


if __name__ == "__main__":
    main()
