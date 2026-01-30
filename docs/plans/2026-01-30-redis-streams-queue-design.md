# Redis Streams Queue Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace MongoDB polling with Redis Streams for low-latency, low-ops message delivery while keeping MongoDB as the source of truth.

**Architecture:** Inbound connectors publish a stream event after `inputmessages` insert succeeds. The agent consumes Redis Streams with a consumer group, fetches the full message from MongoDB, processes it, and ACKs the stream entry. `start.sh --mode pm2` ensures Redis container is running.

**Tech Stack:** Python 3.12+, redis-py, MongoDB, Docker, PM2

---

### Task 1: Add Redis client configuration

**Files:**
- Modify: `conf/config.json`
- Create: `util/redis_client.py`
- Test: `tests/unit/util/test_redis_client.py`

**Step 1: Write the failing test**

```python
def test_redis_client_uses_config_defaults():
    from util.redis_client import RedisClient

    client = RedisClient.from_config()
    assert client.host == "127.0.0.1"
    assert client.port == 6379
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/util/test_redis_client.py::test_redis_client_uses_config_defaults -v`
Expected: FAIL with `ModuleNotFoundError: util.redis_client`

**Step 3: Write minimal implementation**

```python
# util/redis_client.py
from dataclasses import dataclass

from conf.config import CONF


@dataclass
class RedisClient:
    host: str
    port: int
    db: int
    stream_key: str
    group: str

    @classmethod
    def from_config(cls) -> "RedisClient":
        redis_conf = CONF.get("redis", {})
        return cls(
            host=redis_conf.get("host", "127.0.0.1"),
            port=int(redis_conf.get("port", 6379)),
            db=int(redis_conf.get("db", 0)),
            stream_key=redis_conf.get("stream", "coke:input"),
            group=redis_conf.get("group", "coke-workers"),
        )
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/util/test_redis_client.py::test_redis_client_uses_config_defaults -v`
Expected: PASS

**Step 5: Commit**

```bash
git add conf/config.json util/redis_client.py tests/unit/util/test_redis_client.py
git commit -m "feat(redis): add redis config defaults"
```

---

### Task 2: Add Redis stream publisher helper

**Files:**
- Create: `util/redis_stream.py`
- Test: `tests/unit/util/test_redis_stream.py`

**Step 1: Write the failing test**

```python
from unittest.mock import MagicMock


def test_publish_input_event_calls_xadd():
    from util.redis_stream import publish_input_event

    redis_client = MagicMock()
    publish_input_event(redis_client, "abc123", "wechat", 1234567890)

    redis_client.xadd.assert_called_once()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/util/test_redis_stream.py::test_publish_input_event_calls_xadd -v`
Expected: FAIL with `ModuleNotFoundError: util.redis_stream`

**Step 3: Write minimal implementation**

```python
# util/redis_stream.py
def publish_input_event(redis_client, message_id: str, platform: str, ts: int, stream_key: str = "coke:input"):
    redis_client.xadd(
        stream_key,
        {"message_id": message_id, "platform": platform, "ts": str(ts)},
    )
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/util/test_redis_stream.py::test_publish_input_event_calls_xadd -v`
Expected: PASS

**Step 5: Commit**

```bash
git add util/redis_stream.py tests/unit/util/test_redis_stream.py
git commit -m "feat(redis): add stream publisher helper"
```

---

### Task 3: Publish stream event on input insert

**Files:**
- Modify: `connector/ecloud/ecloud_input.py`
- Modify: `connector/langbot/langbot_input.py`
- Modify: `connector/terminal/terminal_input.py`
- Modify: `connector/terminal/terminal_chat.py`
- Test: `tests/unit/connector/test_stream_publish.py`

**Step 1: Write the failing test**

```python
from unittest.mock import MagicMock


def test_ecloud_input_publishes_stream_event(monkeypatch):
    from connector.ecloud import ecloud_input

    mock_redis = MagicMock()
    monkeypatch.setattr(ecloud_input, "redis_client", mock_redis)

    ecloud_input._publish_stream_event("abc123", "wechat", 123)
    mock_redis.xadd.assert_called_once()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/connector/test_stream_publish.py::test_ecloud_input_publishes_stream_event -v`
Expected: FAIL with `AttributeError: module has no attribute _publish_stream_event`

**Step 3: Write minimal implementation**

```python
# connector/ecloud/ecloud_input.py (add)
from util.redis_client import RedisClient
from util.redis_stream import publish_input_event
import redis

redis_conf = RedisClient.from_config()
redis_client = redis.Redis(host=redis_conf.host, port=redis_conf.port, db=redis_conf.db)


def _publish_stream_event(message_id: str, platform: str, ts: int):
    publish_input_event(redis_client, message_id, platform, ts, stream_key=redis_conf.stream_key)
```

Repeat for langbot_input and terminal_input/terminal_chat after insert_one success.

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/connector/test_stream_publish.py::test_ecloud_input_publishes_stream_event -v`
Expected: PASS

**Step 5: Commit**

```bash
git add connector/ecloud/ecloud_input.py connector/langbot/langbot_input.py connector/terminal/terminal_input.py connector/terminal/terminal_chat.py tests/unit/connector/test_stream_publish.py
git commit -m "feat(redis): publish input stream events"
```

---

### Task 4: Add Redis consumer loop in agent runner

**Files:**
- Modify: `agent/runner/message_processor.py`
- Test: `tests/unit/agent/test_message_processor_stream.py`

**Step 1: Write the failing test**

```python
from unittest.mock import MagicMock


def test_stream_consumer_ack_on_success():
    from agent.runner.message_processor import consume_stream_batch

    redis_client = MagicMock()
    redis_client.xreadgroup.return_value = [("coke:input", [("1-0", {b"message_id": b"abc"})])]

    mongo = MagicMock()
    mongo.find_one.return_value = {"_id": "abc", "status": "pending"}

    consume_stream_batch(redis_client, mongo)
    redis_client.xack.assert_called_once()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/agent/test_message_processor_stream.py::test_stream_consumer_ack_on_success -v`
Expected: FAIL with `ImportError: consume_stream_batch not found`

**Step 3: Write minimal implementation**

```python
# agent/runner/message_processor.py (add)
from util.redis_client import RedisClient
import redis


def consume_stream_batch(redis_client, mongo, group: str = "coke-workers", stream: str = "coke:input"):
    entries = redis_client.xreadgroup(group, "worker-1", {stream: ">"}, count=10, block=1000)
    for _stream, messages in entries:
        for entry_id, data in messages:
            message_id = data.get(b"message_id")
            if message_id:
                mongo.find_one("inputmessages", {"_id": message_id.decode()})
            redis_client.xack(stream, group, entry_id)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/agent/test_message_processor_stream.py::test_stream_consumer_ack_on_success -v`
Expected: PASS

**Step 5: Commit**

```bash
git add agent/runner/message_processor.py tests/unit/agent/test_message_processor_stream.py
git commit -m "feat(redis): add stream consumer loop"
```

---

### Task 5: Add Redis container startup to start.sh

**Files:**
- Modify: `start.sh`
- Test: `tests/unit/scripts/test_start_redis.sh` (shell test placeholder)

**Step 1: Write the failing test**

```bash
#!/bin/bash
# tests/unit/scripts/test_start_redis.sh
set -euo pipefail

rg -n "check_redis" start.sh
```

**Step 2: Run test to verify it fails**

Run: `bash tests/unit/scripts/test_start_redis.sh`
Expected: FAIL with `check_redis not found`

**Step 3: Write minimal implementation**

```bash
# start.sh (add)
check_redis() {
    info "检查 Redis..."
    if docker ps -a --format '{{.Names}}' | grep -q '^redis$'; then
        if docker ps --format '{{.Names}}' | grep -q '^redis$'; then
            success "Redis 容器已运行"
            return 0
        else
            warn "Redis 容器已停止，正在启动..."
            docker start redis
            [ $? -eq 0 ] && success "Redis 容器已启动" || (error "Redis 容器启动失败"; exit 1)
            return 0
        fi
    fi
    warn "Redis 容器不存在，正在创建..."
    REDIS_DATA_DIR="$HOME/redis/data"
    mkdir -p "$REDIS_DATA_DIR"
    docker pull redis:7.2
    docker run -d --name redis -p 6379:6379 -v "$REDIS_DATA_DIR":/data redis:7.2 redis-server --appendonly yes
}
```

Insert `check_redis` in `run_setup` after `check_mongodb`.

**Step 4: Run test to verify it passes**

Run: `bash tests/unit/scripts/test_start_redis.sh`
Expected: PASS

**Step 5: Commit**

```bash
git add start.sh tests/unit/scripts/test_start_redis.sh
git commit -m "feat(ops): add redis container setup"
```

---

### Task 6: Update docs for new machine setup

**Files:**
- Modify: `doc/ops/devops_new_instance.md`
- Modify: `doc/ops/devops_start_instance.md`

**Step 1: Write the failing doc check**

```bash
#!/bin/bash
# tests/unit/docs/test_docs_redis.sh
set -euo pipefail

rg -n "redis" doc/ops/devops_new_instance.md doc/ops/devops_start_instance.md
```

**Step 2: Run test to verify it fails**

Run: `bash tests/unit/docs/test_docs_redis.sh`
Expected: FAIL with no matches

**Step 3: Write minimal implementation**

Add Redis instructions mirroring MongoDB steps, plus note that `./start.sh --mode pm2` auto-starts Redis container.

**Step 4: Run test to verify it passes**

Run: `bash tests/unit/docs/test_docs_redis.sh`
Expected: PASS

**Step 5: Commit**

```bash
git add doc/ops/devops_new_instance.md doc/ops/devops_start_instance.md tests/unit/docs/test_docs_redis.sh
git commit -m "docs(ops): add redis setup"
```

---

### Task 7: Wire queue mode switch (redis vs poll)

**Files:**
- Modify: `agent/runner/agent_runner.py`
- Modify: `agent/runner/message_processor.py`
- Test: `tests/unit/agent/test_queue_mode.py`

**Step 1: Write the failing test**

```python
def test_queue_mode_defaults_to_poll():
    from agent.runner.message_processor import get_queue_mode
    assert get_queue_mode() == "poll"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/agent/test_queue_mode.py::test_queue_mode_defaults_to_poll -v`
Expected: FAIL with `ImportError: get_queue_mode not found`

**Step 3: Write minimal implementation**

```python
# agent/runner/message_processor.py (add)
from conf.config import CONF

def get_queue_mode():
    return CONF.get("queue_mode", "poll")
```

Wire in `agent_runner.py` to call stream consumer loop when queue_mode == "redis".

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/agent/test_queue_mode.py::test_queue_mode_defaults_to_poll -v`
Expected: PASS

**Step 5: Commit**

```bash
git add agent/runner/message_processor.py agent/runner/agent_runner.py tests/unit/agent/test_queue_mode.py
git commit -m "feat(queue): add redis queue mode switch"
```

---

### Task 8: Add dependency

**Files:**
- Modify: `requirements.txt`

**Step 1: Add redis dependency**

Add:
```
redis==5.0.4
```

**Step 2: Commit**

```bash
git add requirements.txt
git commit -m "chore(deps): add redis client"
```

---

### Task 9: End-to-end smoke check

**Step 1: Run minimal tests**

Run: `pytest tests/unit/util/test_redis_client.py tests/unit/util/test_redis_stream.py -v`
Expected: PASS

**Step 2: Manual run (optional)**

Run: `./start.sh --mode pm2 --skip-install` and verify `redis` container is running: `docker ps | grep redis`.

**Step 3: Commit**

```bash
git add docs/plans/2026-01-30-redis-streams-queue-design.md
git commit -m "docs(plan): add redis streams implementation plan"
```
