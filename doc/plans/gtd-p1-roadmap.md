# GTD Task System P1 Roadmap

## Completed (P0)

✅ Data structure: `list_id` field with "inbox" default
✅ Nullable `trigger_time` support
✅ DAO layer updates
✅ Tool layer updates
✅ Display differentiation for inbox tasks

## P1 Scope

### 1. Agent Prompt Modifications

**Orchestrator Agent:**
- Understand "帮我记一下..." as task creation intent
- Differentiate between "提醒我" (needs time) vs "记一下" (quick capture)

**Chat Response Agent:**
- After creating inbox task: "已记下！要设置提醒时间吗？"
- Don't wait for reply, end conversation naturally

**Estimated Effort:** 2-3 tasks

### 2. Daily Inbox Digest

**Implementation:**
- Integrate APScheduler into main process
- Daily trigger at 8:30 AM (configurable)
- Query: `list_id="inbox" AND trigger_time=None AND status="active"`
- Send message with full task list

**Message Format:**
```
☀️ 早上好！你的收集篮里有 3 个待安排的想法：

📥 待安排：
  • 买牛奶
  • 整理书架
  • 研究新框架

要处理哪一个吗？
```

**Estimated Effort:** 3-4 tasks

### 3. Custom List Support

**Features:**
- Allow `list_id` to be user-defined (e.g., "work", "personal")
- Update tools to accept `list_id` parameter
- Query by list

**Out of Scope for P1:**
- List management UI
- Context-based lists (@home, @office)

**Estimated Effort:** 2-3 tasks

### 4. Priority & Tags (Optional)

**Schema:**
```python
{
    "priority": int,  # 0-5, default 0
    "tags": List[str]  # ["work", "urgent"]
}
```

**Estimated Effort:** 3-4 tasks

## Total P1 Effort

10-14 tasks across 4 features

## Success Criteria

- [ ] Users can create tasks conversationally without explicit time
- [ ] Daily digest delivered reliably at 8:30 AM
- [ ] Users can query inbox separately from scheduled reminders
- [ ] Test coverage maintains 70%+ threshold
