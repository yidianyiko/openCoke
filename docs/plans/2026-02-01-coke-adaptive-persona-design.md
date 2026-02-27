# Coke Adaptive Persona 系统设计文档

> 日期：2026-02-01
> 目的：设计一个能够根据用户需求和情境动态调整角色的自适应 Persona 系统

---

## 一、设计目标

### 核心问题

当前 Coke 系统的身份和目标过于单一（"云监督员 + 学习督促"），无法自然适应不同场景（如心理咨询、GTD 教练、编程导师等）。

### 期望能力

1. **隐式自适应** - 根据对话内容自动调整风格和能力侧重点
2. **完全隐形** - 用户不感知任何"角色切换"，始终是同一个人
3. **长期偏好记忆** - 虚拟人逐渐了解用户，变得越来越懂 ta
4. **核心不变，动态适配** - 核心使命是"帮你变得更好"，但语气、指令、工具按场景动态加载

---

## 二、Soul vs Skills 边界

```
┌─────────────────────────────────────────────────────────────────┐
│                        SOUL (永恒不变)                          │
│  定义"我是谁" —— Coke 的核心身份                                │
├─────────────────────────────────────────────────────────────────┤
│  身份                                                          │
│    我是 Coke，你的朋友兼老师                                    │
│                                                                │
│  核心价值观                                                    │
│    • 我相信你有能力变得更好                                     │
│    • 我陪你走这条路                                            │
│    • 我们一起来解决问题                                         │
│                                                                │
│  边界                                                          │
│    • 我不会代替你做决定                                        │
│    • 我不会放弃你                                             │
│    • 我不会伤害你                                             │
│                                                                │
│  性格底色                                                      │
│    机智、温暖、有同理心、说话自然如朋友                          │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                     SKILLS (动态可变)                          │
│  定义"我如何回应你" —— 根据场景动态调整                         │
├─────────────────────────────────────────────────────────────────┤
│  姿态层 - 回应风格                                             │
│    • 倾听型：共情、接纳、不评判                                │
│    • 推动型：督促、提醒、严格执行                              │
│    • 指导型：分析、建议、引导思考                              │
│    • 陪伴型：轻松聊天、分享、在场感                            │
│                                                                │
│  知识层 - 专业领域                                             │
│    • GTD/任务管理：目标拆解、流程优化                           │
│    • 心理学：情绪识别、动机引导、ADHD 理解                     │
│    • 学习方法：时间管理、习惯养成、拖延应对                     │
│                                                                │
│  工作流层 - 行为模式                                           │
│    • 晨间启动：询问计划、确认重点                               │
│    • 任务跟进：提醒、检查、确认完成                             │
│    • 晚间复盘：回顾一天、反思总结                               │
└─────────────────────────────────────────────────────────────────┘
```

---

## 三、系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                  Coke Adaptive Persona 系统                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                    核心身份 (Soul)                         │  │
│  │           "我是 Coke，你的朋友兼老师"                      │  │
│  │                                                           │  │
│  │  价值观：相信你 / 陪你走 / 一起解决                         │  │
│  │  边界：不代替决定 / 不放弃 / 不伤害                        │  │
│  │  性格：机智 / 温暖 / 有同理心                              │  │
│  └──────────────────────────────────────────────────────────┘  │
│                            ↑                                     │
│                            │ 动态注入                             │
│                            │                                     │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │           Context Perception Layer (语境感知层)           │  │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐         │  │
│  │  │ IntentDetect│ │UserMemory   │ │AdaptDecision│         │  │
│  │  │ LLM意图检测  │ │ Agno记忆    │ │ 适配决策    │         │  │
│  │  └─────────────┘ └─────────────┘ └─────────────┘         │  │
│  └──────────────────────────────────────────────────────────┘  │
│                            ↑                                     │
│                            │ 按需激活                             │
│                            │                                     │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                    Skills Modules                         │  │
│  │  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐  │  │
│  │  │ listener  │ │  pusher   │ │   guide   │ │ companion │  │  │
│  │  │ (倾听型)  │ │ (推动型)  │ │ (指导型)  │ │ (陪伴型)  │  │  │
│  │  └───────────┘ └───────────┘ └───────────┘ └───────────┘  │  │
│  │  ┌───────────┐ ┌───────────┐ ┌───────────┐               │  │
│  │  │ psychology│ │    gtd    │ │  learning │               │  │
│  │  │ (心理学)  │ │ (任务管理)│ │ (学习方法) │               │  │
│  │  └───────────┘ └───────────┘ └───────────┘               │  │
│  └──────────────────────────────────────────────────────────┘  │
│                            ↑                                     │
│                            │ 学习和记忆                           │
│                            │                                     │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              User Adaptive Memory (用户适应记忆)           │  │
│  │  - 对话风格偏好                                            │  │
│  │  - 姿态效果评分                                            │  │
│  │  - 情绪状态历史                                            │  │
│  │  - 任务参与度                                              │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 四、核心组件

### 4.1 IntentDetector (意图检测器)

使用 LLM 分析用户消息的深层意图：

```python
@dataclass
class IntentDetectionResult:
    emotion: str              # anxious/low_mood/excited/calm/confused
    emotion_intensity: float   # 0-1
    primary_need: str         # support/push/guidance/chat/help
    secondary_need: Optional[str]
    has_task: bool
    task_clarity: float
    recommended_pose: str     # listener/pusher/guide/companion
    pose_confidence: float
    reasoning: str
```

### 4.2 UserMemory (用户记忆)

使用 Agno Memory 系统存储用户适应画像：

```python
class UserAdaptiveProfile:
    user_id: str
    recent_mood: str
    preferred_pose: str
    pose_effectiveness: Dict[str, float]
    task_engagement: float
    mood_history: List[dict]
```

### 4.3 SkillLoader (技能加载器)

从 `agent/skills/` 目录加载姿态和知识技能：

```python
class AdaptiveSkillLoader:
    def load_pose_instructions(self, pose: str) -> str
    def load_knowledge_instructions(self, knowledge: List[str]) -> str
```

---

## 五、Workflow 集成

### 修订后的三阶段 Workflow

```
Phase 1: PrepareWorkflow (增强)
├─ OrchestratorAgent (原有)
├─ IntentDetector (NEW) - LLM 意图分析
├─ UserMemoryLookup (NEW) - 读取用户画像
├─ AdaptationDecision (NEW) - 适配决策
├─ SkillLoader (NEW) - 加载 Skills
└─ context_retrieve_tool (原有)

Phase 2: StreamingChatWorkflow (动态指令)
└─ ChatResponseAgent
   └─ instructions = Soul + Pose Skills + Knowledge

Phase 3: PostAnalyzeWorkflow (增强)
├─ PostAnalyzeAgent (原有)
└─ UserMemoryUpdater (NEW) - 更新用户画像
```

---

## 六、文件结构

```
agent/soul/                              # NEW: Soul 层（不变）
├── __init__.py
├── identity.py                          # 核心身份定义
├── values.py                            # 核心价值观
├── boundaries.py                        # 边界定义
└── personality.py                       # 性格底色

agent/skills/                            # NEW: Skills 层（可变）
├── __init__.py
├── poses/                               # 姿态技能
│   ├── listener/SKILL.md
│   ├── pusher/SKILL.md
│   ├── guide/SKILL.md
│   └── companion/SKILL.md
├── knowledge/                           # 知识领域
│   ├── psychology/SKILL.md
│   ├── gtd/SKILL.md
│   └── learning/SKILL.md
└── workflows/                           # 工作流模式 (future)

agent/agno_agent/adaptive/               # NEW: 自适应层
├── __init__.py
├── intent_detector.py                   # LLM 意图检测
├── user_memory.py                       # Agno 记忆系统封装
├── adaptation_decision.py               # 适配决策逻辑
└── skill_loader.py                      # 技能加载器
```

---

## 七、配置

```json
{
  "models": {
    "default": {"provider": "deepseek", "id": "deepseek-chat"},
    "agents": {
      "chat_response": {"id": "deepseek-chat", "temperature": 0.8},
      "intent_detector": {"id": "deepseek-lite", "temperature": 0.1},
      "post_analyze": {"id": "deepseek-chat", "temperature": 0.3}
    }
  },
  "adaptive": {
    "enabled": true,
    "skills_path": "agent/skills",
    "memory_backend": "agno",
    "fallback_pose": "companion"
  }
}
```

---

## 八、迁移路径

### Phase 1: 基础设施搭建 (1-2 周)
- 创建 `agent/soul/` 目录，分离核心身份
- 创建 `agent/skills/poses/` 目录，迁移姿态相关指令
- 实现 `IntentDetector` (LLM 版本)
- 实现 `AdaptiveSkillLoader`
- 基础单元测试

### Phase 2: Workflow 集成 (2-3 周)
- 修改 `PrepareWorkflow`，集成意图检测
- 修改 `ChatResponseAgent`，使用动态指令
- 实现 `UserAdaptiveProfile` 基于 Agno Memory
- 回归测试确保原有功能正常

### Phase 3: 学习系统上线 (1-2 周)
- 实现 `UserMemoryUpdater`
- 实现 `InteractionQualityAnalyzer`
- 添加用户画像管理 CLI
- A/B 测试

### Phase 4: 优化和扩展 (持续)
- 根据真实数据调整阈值
- 添加更多知识域 Skills
- 优化 LLM 调用成本
- 用户反馈收集和迭代

---

## 九、决策记录

| 决策点 | 选择 |
|--------|------|
| 模型选择 | 配置驱动，不同 Agent 可用不同模型 |
| 用户画像存储 | Agno 记忆系统 |
| 技能文件位置 | `agent/skills/`，与代码一起版本控制 |
