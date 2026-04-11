# -*- coding: utf-8 -*-
"""
E2E 测试 Fixtures

提供真实 LLM 调用的端到端测试所需的 fixtures。
"""
import os
import sys
from pathlib import Path

import pytest
from pymongo import MongoClient
from pymongo.errors import PyMongoError

sys.path.append(".")

from conf.config import CONF

# ========== 测试账号配置 ==========
# 使用现有测试账号
TEST_USER_ID = "692c14aaa538f0baad5561b3"  # 不辣的皮皮
TEST_CHARACTER_ID = "692c147e972f64f2b65da6ee"  # qiaoyun


def _mongo_is_available() -> bool:
    mongo_uri = (
        "mongodb://"
        + CONF["mongodb"]["mongodb_ip"]
        + ":"
        + CONF["mongodb"]["mongodb_port"]
        + "/"
    )
    try:
        client = MongoClient(
            mongo_uri,
            serverSelectionTimeoutMS=1000,
            connectTimeoutMS=1000,
            socketTimeoutMS=1000,
        )
        client.admin.command("ping")
        client.close()
        return True
    except PyMongoError:
        return False


def _agent_runner_is_available() -> bool:
    for pid_file in (Path(".agent.pid"), Path(".start.pid")):
        if not pid_file.exists():
            continue
        try:
            pid = int(pid_file.read_text(encoding="utf-8").strip())
        except (TypeError, ValueError):
            continue
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            continue
    return False


@pytest.fixture(scope="session", autouse=True)
def require_e2e_prerequisites():
    if not _mongo_is_available():
        pytest.skip("E2E prerequisites unavailable: MongoDB is not reachable")
    if not _agent_runner_is_available():
        pytest.skip("E2E prerequisites unavailable: agent runner is not running")


@pytest.fixture(scope="module")
def terminal_client():
    """
    提供 TerminalTestClient 实例

    scope=module: 同一测试模块内复用，减少连接开销
    """
    from connector.terminal.terminal_test_client import TerminalTestClient

    client = TerminalTestClient(
        user_id=TEST_USER_ID,
        character_id=TEST_CHARACTER_ID,
    )

    # 测试前重置残留消息和会话上下文
    client.reset_test_state()

    yield client

    # 测试后重置，避免污染本地环境
    client.reset_test_state()
    client.close()


@pytest.fixture(scope="function")
def clean_terminal_client(terminal_client):
    """
    每个测试函数前重置消息和会话上下文

    用于需要干净状态的测试
    """
    terminal_client.reset_test_state()
    yield terminal_client


@pytest.fixture(scope="session", autouse=True)
def set_skip_post_analyze():
    """
    自动设置 SKIP_POST_ANALYZE 环境变量

    跳过 PostAnalyzeWorkflow，加快测试速度
    """
    original = os.environ.get("SKIP_POST_ANALYZE")
    os.environ["SKIP_POST_ANALYZE"] = "1"
    yield
    if original is None:
        os.environ.pop("SKIP_POST_ANALYZE", None)
    else:
        os.environ["SKIP_POST_ANALYZE"] = original


@pytest.fixture(scope="session")
def mongodb_client():
    """提供 MongoDB 客户端"""
    from dao.mongo import MongoDBBase

    client = MongoDBBase()
    yield client
    client.close()


def pytest_configure(config):
    """注册 E2E 测试 markers"""
    config.addinivalue_line(
        "markers", "llm: 需要真实 LLM 调用的测试（需要 agent_start.sh 运行中）"
    )
