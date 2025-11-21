# 后台任务快速参考

## 🎯 当前配置（推荐）

```bash
export DISABLE_DAILY_AGENTS="true"        # ❌ 禁用 Daily
export DISABLE_BACKGROUND_AGENTS="false"  # ✅ 启用 Background
```

---

## 📋 功能分类

### Daily Agent（已禁用）
- ❌ 每日新闻生成
- ❌ 每日活动脚本
- ❌ 关系数值衰减
- ❌ 主动消息派发

### Background Agent（已启用）
- ✅ 未来消息派发
- ✅ **提醒任务派发**

---

## 🚀 启动提醒功能

```bash
# 1. 初始化（首次）
python scripts/init_reminder_feature.py

# 2. 启动服务
source qiaoyun/runner/qiaoyun_start.sh
```

---

## 📖 完整文档

- **配置说明**：`doc/background_tasks_configuration.md`
- **提醒使用**：`doc/reminder_usage_guide.md`
- **启动指南**：`doc/reminder_startup_guide.md`
- **实现方案**：`doc/reminder_implementation_plan.md`
