"""
统一日志配置模块
从 .env 读取 LOG_LEVEL，配置带时间戳和日志等级的格式
"""

import logging
import os
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

# 从环境变量读取日志级别，默认 INFO
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# 日志格式：时间戳-日志等级-模块名-消息
LOG_FORMAT = "%(asctime)s-%(levelname)s-%(name)s-%(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# 第三方库日志级别设为 WARNING，避免刷屏
NOISY_LOGGERS = [
    "pymongo",
    "urllib3",
    "httpx",
    "httpcore",
    "openai",
    "asyncio",
    "dashscope",
]

# 标记是否已初始化
_initialized = False


def setup_logging():
    """初始化全局日志配置，只执行一次"""
    global _initialized
    if _initialized:
        return
    
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL, logging.INFO),
        format=LOG_FORMAT,
        datefmt=DATE_FORMAT,
        force=True,  # 强制重新配置，覆盖之前的配置
    )
    
    # 降低第三方库日志级别
    for noisy_logger in NOISY_LOGGERS:
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)
    
    _initialized = True


def get_logger(name: str) -> logging.Logger:
    """获取 logger，自动确保日志已配置"""
    setup_logging()
    return logging.getLogger(name)
