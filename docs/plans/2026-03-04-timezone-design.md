# 用户时区功能设计

**日期：** 2026-03-04
**状态：** 已确认

## 背景

当前时区逻辑基于 WhatsApp 手机号区号推断，运行时做三层降级。这对"中国号码但人在海外"的用户会产生错误的时间理解（如"明天下午3点"会按上海时区解析）。

## 目标

- 用户可通过自然语言随时更新自己的时区
- 时区影响所有时间相关功能：Reminder 解析/展示、对话上下文中的时间感知
- 一个用户对应一个时区，持久化到数据库

---

## 数据存储

在 `users` collection 增加 `timezone` 字段，存储 IANA 时区字符串：

```json
{
  "_id": "user_123",
  "timezone": "America/New_York"
}
```

**生命周期：**
- 用户注册时：由手机号区号推断写入（推断不到默认 `Asia/Shanghai`）
- 注册后：用户随时可通过对话更新
- 运行时：始终直接读取此字段，不再做推断降级

---

## 用户时区更新流程

用户通过自然语言表达位置或时区意图，例如：

- "我现在在纽约"
- "切换到东京时间"
- "我搬到新加坡了"

**识别与执行：**

1. OrchestratorAgent 识别到时区更新意图
2. 调用 `set_user_timezone_tool`，由 LLM 直接输出对应的 IANA 时区名（无需维护城市映射表）
3. Tool 将 IANA 时区写入 `users.timezone`
4. Bot 回复确认，例如："已将您的时区更新为纽约时间（UTC-5）。"

---

## 运行时时区获取

在 `agent/runner/context.py` 的 context 准备阶段统一确定用户时区：

```python
stored_tz = user.get("timezone")
if stored_tz:
    user_tz = ZoneInfo(stored_tz)
else:
    # 兜底：老用户迁移期间触发，推断后回写数据库
    user_tz = get_user_timezone(user_platform_id)
    await user_dao.update_timezone(user_id, user_tz.key)

# 之后所有时间格式化均使用 user_tz
```

`user_tz` 确定后传递给所有下游：
- `timestamp2str(..., tz=user_tz)`
- `date2str(..., tz=user_tz)`
- `format_time_friendly(..., tz=user_tz)`
- Reminder parser / validator

---

## 用户注册时初始化

在 DAO 层 `create_user` 时立即写入推断时区：

```python
# dao/user_dao.py
from util.time_util import get_user_timezone

def create_user(platform_id: str, ...) -> dict:
    tz = get_user_timezone(platform_id)
    user = {
        "timezone": tz.key,
        ...
    }
```

---

## Reminder 工具改造

`reminder/parser.py` 和 `validator.py` 中的 `ZoneInfo("Asia/Shanghai")` 硬编码替换为从上层传入的 `user_tz`。

传递链：
```
context.py → user_tz → agent session state → reminder tool → parser/validator
```

---

## 老用户迁移

存量用户无 `timezone` 字段，在 `context.py` 首次读取时触发一次性回写，无需离线迁移脚本。

---

## 测试策略

| 类型 | 测试内容 |
|------|---------|
| unit | `create_user` 时 timezone 字段正确写入 |
| unit | 老用户无 timezone 时，context.py 正确推断并回写 |
| unit | `set_user_timezone_tool` 写入 DB，返回确认消息 |
| integration | 用户说"我在纽约" → 后续 reminder 使用 `America/New_York` |

---

## 不在范围内

- 历史消息的时间戳按用户时区重新格式化
- 多时区支持（一个用户多个时区）
- 时区 UI 设置界面
