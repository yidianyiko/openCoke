# Remove LangBot Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove all LangBot-related code from the Coke project to prepare for alternative platform integration approaches.

**Architecture:** LangBot was integrated as a multi-platform gateway handling Telegram and Feishu through a polling-based connector architecture. This cleanup removes the langbot connector, adapters, PM2 configurations, scripts, tests, and documentation references while preserving the ecloud (WeChat) and whatsapp connectors.

**Tech Stack:** Python 3.12+, Bash scripts, PM2 ecosystem configs, MongoDB integration

**Scope:**
- 299 langbot references across 35 files
- Core directories: `connector/langbot/`, `connector/adapters/langbot/`, `langbot-workdir/`
- Supporting files: Scripts, tests, PM2 configs, documentation
- Configuration cleanup in config.json, ecosystem.config.json, start.sh, stop.sh

---

## Task 1: Remove LangBot Connector Directory

**Files:**
- Delete: `connector/langbot/` (entire directory)
- Delete: `data/langbot.db`

**Step 1: List files to be removed**

Run: `ls -la connector/langbot/`
Expected: Shows langbot_input.py, langbot_output.py, langbot_adapter.py, langbot_api.py, telegram_api.py, feishu_api.py, langbot_start.sh, README.md, __init__.py

Run: `ls -la data/langbot.db`
Expected: Shows the langbot database file

**Step 2: Remove langbot connector directory**

Run: `rm -rf connector/langbot/`
Expected: Directory removed

**Step 3: Remove langbot database**

Run: `rm -f data/langbot.db`
Expected: Database file removed

**Step 4: Verify removal**

Run: `ls connector/langbot/ 2>&1`
Expected: "No such file or directory"

Run: `ls data/langbot.db 2>&1`
Expected: "No such file or directory"

**Step 5: Commit**

```bash
git add -A
git commit -m "refactor(connector): remove langbot connector directory and database

- Remove connector/langbot/ with all input/output handlers
- Remove data/langbot.db database file
- Part of langbot integration cleanup"
```

---

## Task 2: Remove LangBot Adapter from connector/adapters

**Files:**
- Delete: `connector/adapters/langbot/` (entire directory)
- Modify: `connector/adapters/__init__.py:12` (remove import)
- Modify: `connector/adapters/__init__.py:27` (remove from __all__)

**Step 1: List adapter files to be removed**

Run: `ls -la connector/adapters/langbot/`
Expected: Shows langbot_adapter.py, __init__.py

**Step 2: Remove langbot adapter directory**

Run: `rm -rf connector/adapters/langbot/`
Expected: Directory removed

**Step 3: Read current __init__.py**

Run: `cat connector/adapters/__init__.py`
Expected: Shows LangBotAdapter import on line 12 and in __all__ on line 27

**Step 4: Update connector/adapters/__init__.py - remove import**

```python
# Before (line 12):
from connector.adapters.langbot.langbot_adapter import LangBotAdapter

# After:
# (delete this line entirely)
```

**Step 5: Update connector/adapters/__init__.py - remove from __all__**

```python
# Before __all__ list:
__all__ = [
    # Gateway 适配器
    "TelegramAdapter",
    "DiscordAdapter",
    # Polling 适配器（迁移）
    "EcloudAdapter",
    "LangBotAdapter",  # <- remove this line
    "TerminalAdapter",
    # Webhook 适配器
    "WhatsAppAdapter",
]

# After:
__all__ = [
    # Gateway 适配器
    "TelegramAdapter",
    "DiscordAdapter",
    # Polling 适配器（迁移）
    "EcloudAdapter",
    "TerminalAdapter",
    # Webhook 适配器
    "WhatsAppAdapter",
]
```

**Step 6: Verify syntax**

Run: `python3 -m py_compile connector/adapters/__init__.py`
Expected: No output (successful compilation)

**Step 7: Commit**

```bash
git add connector/adapters/__init__.py
git commit -m "refactor(adapters): remove LangBotAdapter from adapters registry

- Delete connector/adapters/langbot/ directory
- Remove LangBotAdapter import and export
- Update __all__ list in connector/adapters/__init__.py"
```

---

## Task 3: Update PollingAdapter docstring

**Files:**
- Modify: `connector/channel/polling_adapter.py:24` (update docstring)

**Step 1: Read current polling adapter**

Run: `head -30 connector/channel/polling_adapter.py`
Expected: Shows docstring mentioning LangBot on line 24

**Step 2: Update polling adapter docstring**

```python
# Before (line 20-25):
class PollingAdapter(ChannelAdapter):
    """
    轮询模式适配器基类

    适用于：Ecloud (微信)、LangBot (Feishu/Telegram)、Terminal
    """

# After:
class PollingAdapter(ChannelAdapter):
    """
    轮询模式适配器基类

    适用于：Ecloud (微信)、Terminal
    """
```

**Step 3: Verify syntax**

Run: `python3 -m py_compile connector/channel/polling_adapter.py`
Expected: No output

**Step 4: Commit**

```bash
git add connector/channel/polling_adapter.py
git commit -m "refactor(polling): update PollingAdapter docstring to remove LangBot reference"
```

---

## Task 4: Clean up config.json

**Files:**
- Modify: `conf/config.json:52-77` (remove langbot section)
- Modify: `conf/config.json:105-115` (remove langbot platforms from access_control)

**Step 1: Backup current config**

Run: `cp conf/config.json conf/config.json.backup`
Expected: Backup created

**Step 2: Read langbot section**

Run: `sed -n '52,77p' conf/config.json`
Expected: Shows entire langbot configuration block

**Step 3: Remove langbot configuration section**

```json
// Before (lines 52-77):
    "langbot": {
        "enabled": true,
        "base_url": "http://127.0.0.1:5300",
        "api_key": "${LANGBOT_API_KEY}",
        "webhook_port": 8081,
        "default_character_alias": "qiaoyun",
        "single_server_mode": true,
        "bots": {
            "qiaoyun-feishu": {
                "bot_uuid": "${LANGBOT_BOT_FEISHU_UUID}",
                "character": "qiaoyun"
            },
            "qiaoyun-telegram": {
                "bot_uuid": "${LANGBOT_BOT_TELEGRAM_UUID}",
                "character": "qiaoyun"
            }
        },
        "feishu": {
            "app_id": "${FEISHU_APP_ID}",
            "app_secret": "${FEISHU_APP_SECRET}"
        },
        "telegram": {
            "bot_token": "${TELEGRAM_BOT_TOKEN}",
            "parse_mode": null
        }
    },

// After:
// (delete entire section, including trailing comma)
```

**Step 4: Update access_control platforms**

```json
// Before (lines 105-115):
    "access_control": {
        "enabled": false,
        "platforms": {
            "wechat": false,
            "langbot_telegram": false,  // <- remove
            "langbot_feishu": false      // <- remove
        },

// After:
    "access_control": {
        "enabled": false,
        "platforms": {
            "wechat": false
        },
```

**Step 5: Validate JSON syntax**

Run: `python3 -c "import json; json.load(open('conf/config.json'))"`
Expected: No output (valid JSON)

**Step 6: Commit**

```bash
git add conf/config.json
git commit -m "refactor(config): remove langbot configuration section

- Remove langbot settings (base_url, bots, feishu, telegram)
- Remove langbot_telegram and langbot_feishu from access_control
- Clean configuration for future platform integrations"
```

---

## Task 5: Remove LangBot Scripts

**Files:**
- Delete: `scripts/langbot_insert_pending_output.py`
- Delete: `scripts/check_langbot_platform.py`
- Delete: `scripts/add_langbot_platform_to_characters.py`
- Delete: `scripts/pm2_langbot_manager.sh`

**Step 1: List scripts to remove**

Run: `ls -la scripts/*langbot* scripts/pm2_langbot*`
Expected: Shows 4 files to be deleted

**Step 2: Remove langbot scripts**

Run: `rm -f scripts/langbot_insert_pending_output.py scripts/check_langbot_platform.py scripts/add_langbot_platform_to_characters.py scripts/pm2_langbot_manager.sh`
Expected: Files removed

**Step 3: Verify removal**

Run: `ls scripts/*langbot* 2>&1`
Expected: "No such file or directory"

**Step 4: Commit**

```bash
git add -A
git commit -m "refactor(scripts): remove langbot utility scripts

- Remove langbot_insert_pending_output.py
- Remove check_langbot_platform.py
- Remove add_langbot_platform_to_characters.py
- Remove pm2_langbot_manager.sh"
```

---

## Task 6: Remove LangBot Test Files

**Files:**
- Delete: `tests/unit/connector/test_langbot_input.py`
- Delete: `tests/unit/connector/test_langbot_output.py`
- Delete: `tests/unit/connector/test_langbot_adapter.py`
- Delete: `tests/unit/connector/test_langbot_api.py`

**Step 1: List test files**

Run: `ls -la tests/unit/connector/test_langbot_*.py`
Expected: Shows 4 test files

**Step 2: Remove langbot test files**

Run: `rm -f tests/unit/connector/test_langbot_*.py`
Expected: Files removed

**Step 3: Verify removal**

Run: `ls tests/unit/connector/test_langbot_* 2>&1`
Expected: "No such file or directory"

**Step 4: Run remaining tests to ensure no dependencies**

Run: `pytest tests/unit/connector/ -v 2>&1 | head -20`
Expected: Tests run without import errors (may have other failures, but no langbot import issues)

**Step 5: Commit**

```bash
git add -A
git commit -m "test(connector): remove langbot connector tests

- Remove test_langbot_input.py
- Remove test_langbot_output.py
- Remove test_langbot_adapter.py
- Remove test_langbot_api.py"
```

---

## Task 7: Update ecosystem.config.json

**Files:**
- Modify: `ecosystem.config.json:3-25` (remove langbot-core)
- Modify: `ecosystem.config.json:89-120` (remove langbot-input and langbot-output)

**Step 1: Read current ecosystem config**

Run: `cat ecosystem.config.json | jq '.apps[] | .name'`
Expected: Shows 6 services including langbot-core, langbot-input, langbot-output

**Step 2: Create updated ecosystem config without langbot services**

```json
// Before: 6 apps
{
  "apps": [
    {
      "name": "langbot-core",
      ...
    },
    {
      "name": "coke-agent",
      ...
    },
    {
      "name": "ecloud-input",
      ...
    },
    {
      "name": "ecloud-output",
      ...
    },
    {
      "name": "langbot-input",
      ...
    },
    {
      "name": "langbot-output",
      ...
    }
  ]
}

// After: 3 apps (remove langbot-core, langbot-input, langbot-output)
{
  "apps": [
    {
      "name": "coke-agent",
      ...
    },
    {
      "name": "ecloud-input",
      ...
    },
    {
      "name": "ecloud-output",
      ...
    }
  ]
}
```

**Step 3: Remove langbot-core (lines 3-25)**

Delete the entire langbot-core app object from the apps array.

**Step 4: Remove langbot-input and langbot-output (lines 89-120)**

Delete both langbot-input and langbot-output app objects from the apps array.

**Step 5: Validate JSON**

Run: `python3 -c "import json; json.load(open('ecosystem.config.json'))"`
Expected: No output (valid JSON)

**Step 6: Verify app count**

Run: `cat ecosystem.config.json | jq '.apps | length'`
Expected: 3

**Step 7: Commit**

```bash
git add ecosystem.config.json
git commit -m "refactor(pm2): remove langbot services from PM2 ecosystem

- Remove langbot-core service
- Remove langbot-input webhook service
- Remove langbot-output message sender
- Retain coke-agent, ecloud-input, ecloud-output"
```

---

## Task 8: Remove ecosystem.langbot.config.json

**Files:**
- Delete: `ecosystem.langbot.config.json`

**Step 1: Check file exists**

Run: `ls -la ecosystem.langbot.config.json`
Expected: Shows the langbot-specific ecosystem config

**Step 2: Remove file**

Run: `rm -f ecosystem.langbot.config.json`
Expected: File removed

**Step 3: Verify removal**

Run: `ls ecosystem.langbot.config.json 2>&1`
Expected: "No such file or directory"

**Step 4: Commit**

```bash
git add -A
git commit -m "refactor(pm2): remove langbot-specific ecosystem configuration"
```

---

## Task 9: Update start.sh script

**Files:**
- Modify: `start.sh:286` (remove --check help text)
- Modify: `start.sh:296-297` (remove dev mode description)
- Modify: `start.sh:301-305` (remove PM2 mode service list)
- Modify: `start.sh:925-937` (remove platform check section)
- Modify: `start.sh:1032-1041` (remove langbot startup in dev mode)
- Modify: `start.sh:1050-1053` (remove langbot PID from status output)
- Modify: `start.sh:1059` (remove langbot log path)
- Modify: `start.sh:1073-1127` (update PM2 mode startup - remove langbot checks)
- Modify: `start.sh:1190-1197` (update PM2 mode service list)
- Modify: `start.sh:1208-1213` (remove langbot restart examples)
- Modify: `start.sh:1271-1274` (remove langbot startup in prod mode)
- Modify: `start.sh:1283` (remove langbot from port allocation)

**Step 1: Update help text (remove --check)**

```bash
# Before (line 286):
echo "  --check                启动前检查 LangBot 平台配置"

# After:
# (delete this line)
```

**Step 2: Update dev mode description (line 296)**

```bash
# Before:
echo "  dev   - 开发模式: 启动 Agent + Ecloud + LangBot 连接器 (nohup)"

# After:
echo "  dev   - 开发模式: 启动 Agent + Ecloud 连接器 (nohup)"
```

**Step 3: Update PM2 mode service list (lines 301-305)**

```bash
# Before:
echo "  - 统一管理所有服务 (LangBot + Agent + ecloud + connectors)"

# After:
echo "  - 统一管理所有服务 (Agent + ecloud connectors)"
```

**Step 4: Remove platform check section (lines 925-937)**

```bash
# Before:
# 部署前检查(可选)
if [ "$CHECK_PLATFORM" = true ]; then
    echo ""
    echo "运行部署前检查..."
    python scripts/check_langbot_platform.py
    if [ $? -ne 0 ]; then
        echo ""
        echo "❌ 平台配置检查失败，请先修复配置问题"
        echo "提示: 编辑 conf/config.json 配置 langbot.bots"
        exit 1
    fi
    echo "✓ 平台配置检查通过"
    echo ""
fi

# After:
# (delete entire section)
```

**Step 5: Remove langbot startup in dev mode (lines 1032-1041)**

```bash
# Before:
    # 启动 LangBot（多平台网关，使用 nohup 后台运行）
    if [ -f connector/langbot/langbot_start.sh ]; then
        echo ""
        echo "=========================================="
        echo "启动 LangBot 网关..."
        echo "=========================================="
        nohup bash connector/langbot/langbot_start.sh > logs/langbot-startup.log 2>&1 &
        LANGBOT_PID=$!
        echo $LANGBOT_PID > "$LANGBOT_PID_FILE"
    fi

# After:
# (delete entire section)
```

**Step 6: Remove langbot from PID output (lines 1050-1053)**

```bash
# Before:
    echo "  Ecloud PID: $ECLOUD_PID"
    if [ -n "$LANGBOT_PID" ]; then
        echo "  LangBot PID: $LANGBOT_PID"
    fi

# After:
    echo "  Ecloud PID: $ECLOUD_PID"
```

**Step 7: Remove langbot log path (line 1059)**

```bash
# Before:
echo "  Ecloud: tail -f connector/ecloud/ecloud.log"
echo "  LangBot: tail -f connector/langbot/langbot.log"

# After:
echo "  Ecloud: tail -f connector/ecloud/ecloud.log"
```

**Step 8: Update PM2 mode startup (lines 1073-1127)**

Remove uvx installation section and langbot-core health check:

```bash
# Before (lines 1073-1127):
    # 查找 uvx 路径
    UVX_PATH=$(command -v uvx 2>/dev/null || echo "")
    ...
    # 检查 LangBot 核心是否启动成功
    ...

# After:
# (delete uvx installation and langbot-core health check sections)
```

**Step 9: Update PM2 service list output (lines 1190-1197)**

```bash
# Before:
    echo "服务列表:"
    echo "  - langbot-core    (LangBot 核心服务，端口 5300)"
    echo "  - coke-agent      (Agent 服务)"
    echo "  - ecloud-input    (E云管家 webhook，端口 8080)"
    echo "  - ecloud-output   (E云管家消息发送)"
    echo "  - langbot-input   (LangBot webhook，端口 8081)"
    echo "  - langbot-output  (LangBot 消息发送)"

# After:
    echo "服务列表:"
    echo "  - coke-agent      (Agent 服务)"
    echo "  - ecloud-input    (E云管家 webhook，端口 8080)"
    echo "  - ecloud-output   (E云管家消息发送)"
```

**Step 10: Remove langbot restart examples (lines 1208-1213)**

```bash
# Before:
    echo "  pm2 restart langbot-core   # 重启 LangBot 核心"
    echo "  pm2 restart coke-agent     # 重启 Agent"
    echo "  pm2 restart ecloud-input   # 重启 ecloud input"
    echo "  pm2 restart ecloud-output  # 重启 ecloud output"
    echo "  pm2 restart langbot-input  # 重启 langbot input"
    echo "  pm2 restart langbot-output # 重启 langbot output"

# After:
    echo "  pm2 restart coke-agent     # 重启 Agent"
    echo "  pm2 restart ecloud-input   # 重启 ecloud input"
    echo "  pm2 restart ecloud-output  # 重启 ecloud output"
```

**Step 11: Remove langbot from prod mode (lines 1271-1274)**

```bash
# Before:
    # 4. 启动 LangBot 连接器 (Input + Output)
    echo "启动 LangBot 连接器..."
    bash connector/langbot/langbot_start.sh > "$LOG_DIR/langbot.log" 2>&1 &
    LANGBOT_PID=$!
    echo "LangBot 连接器 PID: $LANGBOT_PID" >> "$PIDS_FILE"

# After:
# (delete entire section)
```

**Step 12: Remove langbot from port allocation (line 1283)**

```bash
# Before:
    echo "服务端口分配:"
    echo "  - LangBot 核心服务: 5300"
    echo "  - Coke 主服务: 8080"
    echo "  - LangBot Webhook: 8081"
    echo "  - MongoDB: 27017"

# After:
    echo "服务端口分配:"
    echo "  - Coke 主服务: 8080"
    echo "  - MongoDB: 27017"
```

**Step 13: Verify script syntax**

Run: `bash -n start.sh`
Expected: No output (valid syntax)

**Step 14: Commit**

```bash
git add start.sh
git commit -m "refactor(scripts): remove langbot from start.sh

- Remove langbot startup logic in dev and prod modes
- Remove langbot from PM2 service management
- Remove langbot from help text and documentation
- Remove platform check functionality
- Clean up service lists and port allocations"
```

---

## Task 10: Update stop.sh script

**Files:**
- Modify: `stop.sh:11` (remove LANGBOT_PID_FILE)
- Modify: `stop.sh:22` (remove langbot from PM2 check)
- Modify: `stop.sh:28` (remove langbot from dev mode check)
- Modify: `stop.sh:96-97` (remove langbot pkill in single_server mode)
- Modify: `stop.sh:115-119` (remove langbot section in dev mode)
- Modify: `stop.sh:131-132` (remove langbot pkill in none mode)

**Step 1: Remove LANGBOT_PID_FILE variable (line 11)**

```bash
# Before:
LANGBOT_PID_FILE="$SCRIPT_DIR/.langbot.pid"

# After:
# (delete this line)
```

**Step 2: Update PM2 mode detection (line 22)**

```bash
# Before:
if pm2 list 2>/dev/null | grep -q "langbot-core\|coke-agent\|ecloud-input"; then

# After:
if pm2 list 2>/dev/null | grep -q "coke-agent\|ecloud-input"; then
```

**Step 3: Update dev mode detection (line 28)**

```bash
# Before:
elif [ -f "$AGENT_PID_FILE" ] || [ -f "$ECLOUD_PID_FILE" ] || [ -f "$LANGBOT_PID_FILE" ]; then

# After:
elif [ -f "$AGENT_PID_FILE" ] || [ -f "$ECLOUD_PID_FILE" ]; then
```

**Step 4: Remove langbot pkill in single_server mode (lines 96-97)**

```bash
# Before:
        pkill -f "gunicorn.*langbot_input" 2>/dev/null && echo "  已停止残留的 LangBot Input Handler" && STOPPED_ANY=true
        pkill -f "langbot_output.py" 2>/dev/null && echo "  已停止残留的 LangBot Output Handler" && STOPPED_ANY=true

# After:
# (delete these lines)
```

**Step 5: Remove langbot section in dev mode (lines 115-119)**

```bash
# Before:
        if [ -f "$LANGBOT_PID_FILE" ]; then
            LANGBOT_PID=$(cat "$LANGBOT_PID_FILE")
            stop_process "LangBot" "$LANGBOT_PID"
            rm -f "$LANGBOT_PID_FILE"
        fi

# After:
# (delete entire section)
```

**Step 6: Remove langbot pkill in none mode (lines 131-132)**

```bash
# Before:
        pkill -f "gunicorn.*langbot_input" 2>/dev/null && echo "  已停止 LangBot Input" && STOPPED_ANY=true
        pkill -f "langbot_output.py" 2>/dev/null && echo "  已停止 LangBot Output" && STOPPED_ANY=true

# After:
# (delete these lines)
```

**Step 7: Verify script syntax**

Run: `bash -n stop.sh`
Expected: No output (valid syntax)

**Step 8: Commit**

```bash
git add stop.sh
git commit -m "refactor(scripts): remove langbot from stop.sh

- Remove LANGBOT_PID_FILE variable
- Remove langbot from process detection
- Remove langbot pkill commands
- Clean up service stop logic"
```

---

## Task 11: Update pm2-manager.sh script

**Files:**
- Modify: `pm2-manager.sh:33` (remove langbot-core from service list)
- Modify: `pm2-manager.sh:37-38` (remove langbot services)
- Modify: `pm2-manager.sh:52` (remove langbot from available services)

**Step 1: Update service list in help (line 33)**

```bash
# Before:
echo "  langbot-core    - LangBot 核心服务"

# After:
# (delete this line)
```

**Step 2: Remove langbot services from list (lines 37-38)**

```bash
# Before:
echo "  langbot-input   - LangBot webhook 接收"
echo "  langbot-output  - LangBot 消息发送"

# After:
# (delete these lines)
```

**Step 3: Update available services in check_service (line 52)**

```bash
# Before:
        echo "可用服务: langbot-core, coke-agent, ecloud-input, ecloud-output, langbot-input, langbot-output"

# After:
        echo "可用服务: coke-agent, ecloud-input, ecloud-output"
```

**Step 4: Verify script syntax**

Run: `bash -n pm2-manager.sh`
Expected: No output (valid syntax)

**Step 5: Commit**

```bash
git add pm2-manager.sh
git commit -m "refactor(scripts): remove langbot services from pm2-manager.sh

- Remove langbot-core, langbot-input, langbot-output from service lists
- Update help text and available services"
```

---

## Task 12: Update .gitignore

**Files:**
- Modify: `.gitignore:13` (remove .langbot.pid)
- Modify: `.gitignore:169-170` (remove langbot-workdir entries)

**Step 1: Remove .langbot.pid (line 13)**

```gitignore
# Before:
.langbot.pid

# After:
# (delete this line)
```

**Step 2: Remove langbot-workdir entries (lines 169-170)**

```gitignore
# Before:
langbot-workdir/data/langbot.db
langbot-workdir/data/chroma/chroma.sqlite3

# After:
# (delete these lines)
```

**Step 3: Verify .gitignore syntax**

Run: `git check-ignore -v .langbot.pid 2>&1`
Expected: No match (line removed)

**Step 4: Commit**

```bash
git add .gitignore
git commit -m "refactor(gitignore): remove langbot-related ignore patterns

- Remove .langbot.pid
- Remove langbot-workdir database patterns"
```

---

## Task 13: Remove langbot-workdir directory

**Files:**
- Delete: `langbot-workdir/` (entire directory)

**Step 1: Check langbot-workdir exists**

Run: `ls -la langbot-workdir/`
Expected: Shows data/config.yaml and other langbot files

**Step 2: Remove langbot-workdir**

Run: `rm -rf langbot-workdir/`
Expected: Directory removed

**Step 3: Verify removal**

Run: `ls langbot-workdir/ 2>&1`
Expected: "No such file or directory"

**Step 4: Commit**

```bash
git add -A
git commit -m "refactor(langbot): remove langbot working directory

- Remove langbot-workdir with data and config files
- Complete removal of langbot runtime environment"
```

---

## Task 14: Clean up remaining code references

**Files:**
- Modify: `agent/util/message_util.py` (check and remove if needed)
- Modify: `agent/runner/message_processor.py` (check and remove if needed)
- Modify: `agent/runner/agent_background_handler.py` (check and remove if needed)
- Modify: `dao/user_dao.py` (check and remove if needed)

**Step 1: Check message_util.py for langbot references**

Run: `grep -n "langbot" agent/util/message_util.py`
Expected: Shows line numbers with langbot references

**Step 2: Read context around langbot references**

Run: `grep -B3 -A3 "langbot" agent/util/message_util.py`
Expected: Shows code context (likely platform string comparisons)

**Step 3: Remove langbot platform strings**

For each file, remove langbot-specific platform identifiers like:
- "langbot_telegram"
- "langbot_feishu"
- "langbot"

Update any platform lists or conditionals to exclude these values.

**Step 4: Check message_processor.py**

Run: `grep -n "langbot" agent/runner/message_processor.py`
Expected: Shows langbot references

**Step 5: Update message_processor.py**

Remove any langbot platform handling logic.

**Step 6: Check agent_background_handler.py**

Run: `grep -n "langbot" agent/runner/agent_background_handler.py`
Expected: Shows langbot references

**Step 7: Update agent_background_handler.py**

Remove langbot platform logic.

**Step 8: Check user_dao.py**

Run: `grep -n "langbot" dao/user_dao.py`
Expected: Shows langbot references

**Step 9: Update user_dao.py**

Remove langbot platform handling.

**Step 10: Run tests**

Run: `pytest tests/unit/ -v -k "not integration" 2>&1 | tail -30`
Expected: Tests pass (or same failures as before, no new langbot-related errors)

**Step 11: Commit**

```bash
git add agent/util/message_util.py agent/runner/message_processor.py agent/runner/agent_background_handler.py dao/user_dao.py
git commit -m "refactor(core): remove langbot platform references from core code

- Remove langbot_telegram and langbot_feishu platform identifiers
- Clean up platform handling in message processing
- Update user DAO platform logic"
```

---

## Task 15: Update access gate tests

**Files:**
- Modify: `tests/unit/runner/test_access_gate.py` (remove langbot tests)
- Modify: `tests/unit/runner/test_message_dispatcher_gate.py` (remove langbot references)

**Step 1: Check test_access_gate.py**

Run: `grep -n "langbot" tests/unit/runner/test_access_gate.py`
Expected: Shows langbot test cases

**Step 2: Remove langbot test cases**

Remove any test functions that test langbot_telegram or langbot_feishu access control.

**Step 3: Check test_message_dispatcher_gate.py**

Run: `grep -n "langbot" tests/unit/runner/test_message_dispatcher_gate.py`
Expected: Shows langbot references

**Step 4: Update test_message_dispatcher_gate.py**

Remove langbot platform test cases.

**Step 5: Run updated tests**

Run: `pytest tests/unit/runner/test_access_gate.py tests/unit/runner/test_message_dispatcher_gate.py -v`
Expected: All tests pass

**Step 6: Commit**

```bash
git add tests/unit/runner/test_access_gate.py tests/unit/runner/test_message_dispatcher_gate.py
git commit -m "test(runner): remove langbot from access gate tests

- Remove langbot_telegram and langbot_feishu test cases
- Update gate tests to only cover wechat platform"
```

---

## Task 16: Update CLAUDE.md documentation

**Files:**
- Modify: `CLAUDE.md` (remove langbot references)

**Step 1: Find langbot references in CLAUDE.md**

Run: `grep -n "langbot\|LangBot" CLAUDE.md`
Expected: Shows 2 references

**Step 2: Read context**

Run: `grep -B2 -A2 -i "langbot" CLAUDE.md`
Expected: Shows access control platform list

**Step 3: Update access control documentation**

```markdown
# Before:
"platforms": {
    "wechat": false,
    "langbot_telegram": true,
    "langbot_feishu": true
}

# After:
"platforms": {
    "wechat": false
}
```

**Step 4: Remove any other langbot mentions**

Search and remove references to:
- LangBot integration
- Telegram/Feishu through LangBot
- LangBot configuration examples

**Step 5: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(claude): remove langbot references from CLAUDE.md

- Update access control examples
- Remove langbot platform documentation"
```

---

## Task 17: Update README.md

**Files:**
- Modify: `README.md` (check and remove langbot if present)

**Step 1: Check for langbot in README**

Run: `grep -n "langbot\|LangBot" README.md`
Expected: Shows any langbot mentions (1 found from earlier grep)

**Step 2: Read context**

Run: `grep -B3 -A3 -i "langbot" README.md`
Expected: Shows architecture or feature descriptions

**Step 3: Remove langbot references**

Update any architecture diagrams, feature lists, or setup instructions that mention LangBot.

**Step 4: Commit (if changes made)**

```bash
git add README.md
git commit -m "docs(readme): remove langbot references from README"
```

---

## Task 18: Clean up documentation plans

**Files:**
- Check: `docs/plans/2026-01-30-coke-vs-moltbot-comparison.md`
- Check: `docs/plans/2026-01-30-channel-adapter-design.md`
- Check: `docs/plans/2026-01-30-coke-moltbot-agno-alignment.md`

**Step 1: Check comparison doc**

Run: `grep -n "langbot" docs/plans/2026-01-30-coke-vs-moltbot-comparison.md`
Expected: Shows langbot references

**Step 2: Decide on doc updates**

These are historical planning documents. Options:
1. Add deprecation notice at top
2. Remove langbot sections
3. Leave as historical reference

**Recommended:** Add deprecation notice to preserve history.

**Step 3: Add deprecation notices**

For each affected doc, add at the top:

```markdown
> **DEPRECATED (2026-02-16):** LangBot integration has been removed. This document
> is kept for historical reference only. Future platform integrations will use
> alternative approaches.
```

**Step 4: Commit**

```bash
git add docs/plans/
git commit -m "docs(plans): add deprecation notice to langbot-related plans

- Mark langbot integration plans as historical
- Preserve documentation for reference
- Note: Future platforms will use different integration methods"
```

---

## Task 19: Final verification and cleanup

**Files:**
- Verify: No langbot references remain in active code
- Verify: Tests pass
- Verify: Scripts execute without errors

**Step 1: Search for remaining langbot references**

Run: `git grep -i "langbot" -- "*.py" "*.sh" "*.json" | grep -v "docs/plans" | grep -v "\.backup"`
Expected: No results (or only in comments/deprecation notices)

**Step 2: Run full test suite**

Run: `pytest tests/unit/ -v -k "not integration" 2>&1 | tail -50`
Expected: Tests pass with no langbot import errors

**Step 3: Test start.sh syntax**

Run: `bash -n start.sh && echo "✓ start.sh syntax OK"`
Expected: "✓ start.sh syntax OK"

**Step 4: Test stop.sh syntax**

Run: `bash -n stop.sh && echo "✓ stop.sh syntax OK"`
Expected: "✓ stop.sh syntax OK"

**Step 5: Validate JSON configs**

Run: `python3 -c "import json; json.load(open('conf/config.json')); json.load(open('ecosystem.config.json')); print('✓ All JSON valid')"`
Expected: "✓ All JSON valid"

**Step 6: Check for orphaned files**

Run: `find . -name "*langbot*" -not -path "./docs/plans/*" -not -path "./.git/*" -not -path "./*.backup"`
Expected: No results

**Step 7: Review git status**

Run: `git status`
Expected: Shows all changes have been committed

**Step 8: Final commit (if needed)**

If any final cleanup:

```bash
git add -A
git commit -m "refactor(cleanup): final langbot integration removal

- Verified no active code references remain
- All tests passing
- Scripts validated
- Ready for alternative platform integration approaches"
```

---

## Summary

**Total tasks:** 19
**Files deleted:** 15+ (directories count as multiple files)
**Files modified:** 15+
**Estimated time:** 90-120 minutes

**Key changes:**
1. ✅ Removed connector/langbot/ directory
2. ✅ Removed connector/adapters/langbot/
3. ✅ Cleaned config.json (langbot section, access_control platforms)
4. ✅ Removed 4 langbot scripts
5. ✅ Removed 4 langbot test files
6. ✅ Updated ecosystem.config.json (removed 3 services)
7. ✅ Removed ecosystem.langbot.config.json
8. ✅ Updated start.sh (removed startup logic, help text, PM2 management)
9. ✅ Updated stop.sh (removed stop logic)
10. ✅ Updated pm2-manager.sh (removed service lists)
11. ✅ Updated .gitignore (removed patterns)
12. ✅ Removed langbot-workdir/
13. ✅ Cleaned core code references (message_util, processor, handler, DAO)
14. ✅ Updated access gate tests
15. ✅ Updated CLAUDE.md
16. ✅ Updated README.md
17. ✅ Added deprecation notices to historical docs
18. ✅ Final verification

**Testing checkpoints:**
- After Task 6: Tests should run without langbot imports
- After Task 11: Scripts should validate syntax
- After Task 14: Core tests should pass
- After Task 19: Full verification passes

**Rollback:**
All changes are in git commits - can revert individual tasks if needed.
