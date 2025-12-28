# -*- coding: utf-8 -*-

# ========== 消息来源说明（根据 message_source 自动注入） ==========
# 代码层面直接注入，LLM 不需要判断消息来源

CONTEXTPROMPT_消息来源_用户消息 = """### 消息来源说明
这是 {user[platforms][wechat][nickname]} 通过微信发送给你的真实消息."""

CONTEXTPROMPT_消息来源_提醒触发 = """### 消息来源说明
这是系统触发的定时提醒，不是 {user[platforms][wechat][nickname]} 发来的消息.
你需要根据提醒内容，主动向 {user[platforms][wechat][nickname]} 发送提醒消息.
【注意】不要把提醒内容当成用户说的话来回复."""

CONTEXTPROMPT_消息来源_主动消息 = """### 消息来源说明
这是你主动发起对话的场景，不是 {user[platforms][wechat][nickname]} 发来的消息.
你需要根据规划行动，主动向 {user[platforms][wechat][nickname]} 发送消息.
【注意】你是消息的发起方，不是在回复用户."""


def get_message_source_context(message_source: str, context: dict) -> str:
    """
    根据消息来源返回对应的说明上下文

    Args:
        message_source: 消息来源-"user"/"reminder"/"future"
        context: 完整上下文，用于渲染模板

    Returns:
        格式化的消息来源说明
    """
    if message_source == "reminder":
        template = CONTEXTPROMPT_消息来源_提醒触发
    elif message_source == "future":
        template = CONTEXTPROMPT_消息来源_主动消息
    else:  # user
        template = CONTEXTPROMPT_消息来源_用户消息

    try:
        return template.format(**context)
    except KeyError:
        # 回退：直接使用用户昵称
        _user_nickname = (
            context.get("user", {})
            .get("platforms", {})
            .get("wechat", {})
            .get("nickname", "用户")
        )  # 保留以备将来使用
        if message_source == "reminder":
            return """### 消息来源说明
这是系统触发的定时提醒，不是 {user_nickname} 发来的消息.
你需要根据提醒内容，主动向 {user_nickname} 发送提醒消息.
【注意】不要把提醒内容当成用户说的话来回复."""
        elif message_source == "future":
            return """### 消息来源说明
这是你主动发起对话的场景，不是 {user_nickname} 发来的消息.
你需要根据规划行动，主动向 {user_nickname} 发送消息.
【注意】你是消息的发起方，不是在回复用户."""
        else:
            return """### 消息来源说明
这是 {user_nickname} 通过微信发送给你的真实消息，请正常回复."""


CONTEXTPROMPT_时间 = """### 系统当前时间
（24小时制）{conversation[conversation_info][time_str]}"""

CONTEXTPROMPT_新闻 = """
{news_str}
"""

CONTEXTPROMPT_人物信息 = """### {character[platforms][wechat][nickname]}的人物信息
{character[user_info][description]}"""


CONTEXTPROMPT_人物资料 = """### {character[platforms][wechat][nickname]}的人物资料
{context_retrieve[character_global]}
{context_retrieve[character_private]}"""

CONTEXTPROMPT_用户资料 = """###  {user[platforms][wechat][nickname]} 的人物资料
{context_retrieve[user]}"""

# 待办提醒-仅在有待办时使用
# 使用时需要先检查 context_retrieve[confirmed_reminders] 是否为空
CONTEXTPROMPT_待办提醒 = """###  {user[platforms][wechat][nickname]} 的待办提醒
{context_retrieve[confirmed_reminders]}"""


def get_reminders_context(context_retrieve: dict, user_nickname: str) -> str:
    """
    获取待办提醒上下文，仅在有待办时返回

    Args:
        context_retrieve: 上下文检索结果字典
        user_nickname: 用户昵称

    Returns:
        如果有待办提醒则返回格式化的上下文，否则返回空字符串
    """
    reminders = context_retrieve.get("confirmed_reminders", "")
    if reminders and reminders.strip():
        return f"""###  {user_nickname} 的待办提醒
{reminders}"""
    return ""


CONTEXTPROMPT_人物知识和技能 = """### {character[platforms][wechat][nickname]}的人物知识和技能
{context_retrieve[character_knowledge]}"""

CONTEXTPROMPT_人物状态 = """### {character[platforms][wechat][nickname]}的人物状态
所在地点：{character[user_info][status][place]}
行动：{character[user_info][status][action]}
当前状态：{relation[relationship][status]}"""

CONTEXTPROMPT_当前目标 = """### {character[platforms][wechat][nickname]}的当前目标
长期目标：{relation[character_info][longterm_purpose]}
短期目标：{relation[character_info][shortterm_purpose]}
对 {user[platforms][wechat][nickname]} 的态度：{relation[character_info][attitude]}"""

CONTEXTPROMPT_当前的人物关系 = """### {character[platforms][wechat][nickname]}与 {user[platforms][wechat][nickname]} 当前的人物关系
关系描述：{relation[relationship][description]}
亲密度：{relation[relationship][closeness]}
信任度：{relation[relationship][trustness]}
反感度：{relation[relationship][dislike]}
已知 {user[platforms][wechat][nickname]} 的真名：{relation[user_info][realname]}
{character[platforms][wechat][nickname]}对 {user[platforms][wechat][nickname]} 的亲密昵称：{relation[user_info][hobbyname]}
{character[platforms][wechat][nickname]}对 {user[platforms][wechat][nickname]} 的印象描述：{relation[user_info][description]}
"""

CONTEXTPROMPT_最近的历史对话 = """### 历史对话（最近十五条）
{conversation[conversation_info][chat_history_str]}"""

# 语义检索的相关历史对话-仅在有检索结果时使用
# 使用时需要先检查 context_retrieve[relevant_history] 是否为空
CONTEXTPROMPT_历史最相关的十条对话 = """### 相关历史对话（语义检索）
以下是与当前话题语义相关的过往对话：
{context_retrieve[relevant_history]}"""


def get_relevant_history_context(
    context_retrieve: dict, recent_history_str: str = ""
) -> str:
    """
    获取相关历史对话上下文，仅在有检索结果时返回

    V2.13 优化：过滤掉已经在最近历史对话中出现的消息，避免重复

    Args:
        context_retrieve: 上下文检索结果字典
        recent_history_str: 最近历史对话字符串，用于过滤重复内容

    Returns:
        如果有相关历史则返回格式化的上下文，否则返回空字符串
    """
    relevant_history = context_retrieve.get("relevant_history", "")
    if not relevant_history or not relevant_history.strip():
        return ""

    # V2.13: 过滤掉已经在最近历史中出现的消息
    if recent_history_str:
        filtered_lines = []
        for line in relevant_history.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            # 检查这条消息是否已经在最近历史中存在
            # 移除 "- " 前缀后进行比较
            clean_line = line.lstrip("- ").strip()
            if clean_line and clean_line not in recent_history_str:
                filtered_lines.append(line)

        if not filtered_lines:
            return ""
        relevant_history = "\n".join(filtered_lines)

    return f"""### 相关历史对话（语义检索）
以下是与当前话题语义相关的过往对话：
{relevant_history}"""


# 精简版历史对话，用于主动消息场景（只包含最近几条消息）
CONTEXTPROMPT_历史对话_精简 = """### 最近对话（最近3轮）
{recent_chat_history}"""

CONTEXTPROMPT_最新聊天消息 = """###  {user[platforms][wechat][nickname]} 的最新聊天消息
{conversation[conversation_info][input_messages_str]}"""

# V2.15 新增：防止 AI 重复回复的提示（用于所有消息场景）
CONTEXTPROMPT_防重复回复 = """{proactive_forbidden_messages}

【严格禁止-必须遵守】上面列出的"你最近发送过的消息"是你绝对不能重复的内容，你必须：
- 不能重复相同的问题或话题
- 不能使用相似的句式或表达
- 不能表达相同或相近的意思
- 换一个完全不同的角度或话题来回应
"""

CONTEXTPROMPT_初步回复 = """### {character[platforms][wechat][nickname]}的初步回复
{MultiModalResponses}"""

CONTEXTPROMPT_最新聊天消息_双方 = """###  {user[platforms][wechat][nickname]} 的最新聊天消息
{conversation[conversation_info][input_messages_str]}

### {character[platforms][wechat][nickname]}的最新回复
{MultiModalResponses}"""

CONTEXTPROMPT_规划行动 = """### {character[platforms][wechat][nickname]}的规划行动
{character[platforms][wechat][nickname]}计划主动向 {user[platforms][wechat][nickname]} 发送消息，行动内容：{conversation[conversation_info][future][action]}
【重要】这是{character[platforms][wechat][nickname]}要主动发起的消息，不是 {user[platforms][wechat][nickname]} 发来的消息."""

CONTEXTPROMPT_系统提醒触发 = """### 系统提醒触发
以下是到期的提醒，{character[platforms][wechat][nickname]}需要主动提醒 {user[platforms][wechat][nickname]} ：
提醒内容：{system_message_metadata[action_template]}
【重要】这是{character[platforms][wechat][nickname]}要发给 {user[platforms][wechat][nickname]} 的提醒内容，不是 {user[platforms][wechat][nickname]} 发来的消息.{character[platforms][wechat][nickname]}应该基于这个提醒内容，用自然的方式提醒用户."""

# V2.15 精简：移除重复的【严格禁止】部分，统一由 CONTEXTPROMPT_防重复回复 提供
CONTEXTPROMPT_主动消息触发 = """### 主动消息触发
{character[platforms][wechat][nickname]}计划主动向 {user[platforms][wechat][nickname]} 发送消息.
行动内容：{conversation[conversation_info][future][action]}
本轮已主动催促次数：{proactive_times}

【重要】这是{character[platforms][wechat][nickname]}要主动发起的消息，不是 {user[platforms][wechat][nickname]} 发来的消息.
"""

# V2.7 新增：提醒工具结果上下文
CONTEXTPROMPT_提醒工具结果 = """### 提醒设置工具消息
{【提醒设置工具消息】}

【说明】以上是系统自动处理提醒的结果.请根据这个结果，用自然的方式回复用户.
例如：
- 如果提醒创建成功，可以说"好的，我帮你设好了"
- 如果信息不足，请自然地询问用户补充缺少的信息
- 如果是重复提醒，可以说"这个提醒已经设置过了哦"

【重要】只有当你看到这个"提醒设置工具消息"时，才能确认提醒操作已执行.如果没有看到这个消息，说明提醒还未创建，不要假设提醒已设置成功.
"""

# V2.8 新增：提醒意图检测但工具未执行的提示
# 当 OrchestratorAgent 判断 need_reminder_detect=True 但 ReminderDetectAgent 未调用工具时使用
CONTEXTPROMPT_提醒未执行 = """### 系统提示：提醒设置待确认
用户的消息似乎包含设置提醒的意图，但系统尚未成功创建提醒.
可能的原因：
- 时间表达不够明确（如"晚一点"、"过一会"等模糊时间）
- 缺少必要的信息（如具体时间或提醒内容）

【重要】请不要假设提醒已经设置成功！你应该：
1. 询问用户具体的提醒时间（如果时间不明确）
2. 确认提醒的具体内容（如果内容不清楚）
3. 用自然的方式引导用户提供完整信息

示例回复：
- "你想什么时候提醒你呢？"
- "具体几点提醒你呀？"
- "好的，你想让我什么时候提醒你[内容]呢？"
"""


# V2.9 新增：结构化工具执行上下文模板
# 提供更详细的工具执行信息，帮助 ChatResponseAgent 理解用户意图与实际执行的差距
CONTEXTPROMPT_提醒工具结果_结构化 = """### 提醒操作执行结果
用户意图：{tool_execution_context[user_intent]}
实际执行：{tool_execution_context[action_executed]}
意图满足：{tool_execution_context[intent_fulfilled]}
执行结果：{tool_execution_context[result_summary]}

【说明】以上是系统自动处理提醒的结果.请根据这个结果，用自然的方式回复用户.
- 如果"意图满足"为 True，说明用户的需求已被满足，可以确认操作成功
- 如果"意图满足"为 False，说明用户的需求未被完全满足，需要引导用户补充信息或说明原因

【重要】只有当你看到这个"提醒操作执行结果"时，才能确认提醒操作已执行.如果没有看到这个消息，说明提醒还未处理，不要假设提醒已设置成功.
"""


def get_reminder_result_context(session_state: dict) -> str:
    """
    获取提醒工具结果上下文，优先使用结构化格式

    Args:
        session_state: 会话状态字典

    Returns:
        格式化的提醒工具结果上下文，如果没有结果则返回空字符串
    """
    # 频率限制规则说明（当遇到频率限制错误时追加）
    FREQUENCY_LIMIT_RULES = """
### 重复提醒频率限制规则（向用户解释时参考）
- 分钟级别（< 60分钟）的无限重复提醒：不支持，频率过高会导致服务被限制，用户可以使用时间段提醒（如"上午9点到下午6点每30分钟"），小时级别以上的重复提醒（每小时、每天等）：支持，默认最多提醒10次"""

    # 检查是否有结构化工具执行上下文
    tool_context = session_state.get("tool_execution_context")
    if tool_context:
        # 检查是否是频率限制错误
        details = tool_context.get("details", {})
        is_frequency_error = details.get("error") == "frequency_too_high"
        frequency_rules = FREQUENCY_LIMIT_RULES if is_frequency_error else ""

        user_intent = tool_context.get("user_intent", "未识别")
        action_executed = tool_context.get("action_executed", "unknown")
        intent_fulfilled = "是" if tool_context.get("intent_fulfilled", False) else "否"
        result_summary = tool_context.get("result_summary", "")

        return f"""### 提醒操作执行结果
用户意图：{user_intent}
实际执行：{action_executed}
意图满足：{intent_fulfilled}
执行结果：{result_summary}

【说明】以上是系统自动处理提醒的结果.请根据这个结果，用自然的方式回复用户.
- 如果"意图满足"为"是"，说明用户的需求已被满足，可以确认操作成功
- 如果"意图满足"为"否"，说明用户的需求未被完全满足，需要根据"执行结果"中的原因向用户解释：
 -如果是频率过高被拒绝，向用户解释限制原因并建议替代方案
 -如果是信息不足，引导用户补充缺少的信息
 -如果是其他错误，说明具体原因

【重要】只有当你看到这个"提醒操作执行结果"时，才能确认提醒操作已执行.如果没有看到这个消息，说明提醒还未处理，不要假设提醒已设置成功.
{frequency_rules}"""

    # 回退到旧的语义化消息格式
    reminder_message = session_state.get("【提醒设置工具消息】", "")
    if reminder_message:
        return f"""### 提醒设置工具消息
{reminder_message}

【说明】以上是系统自动处理提醒的结果.请根据这个结果，用自然的方式回复用户.
例如：
- 如果提醒创建成功，可以说"好的，我帮你设好了"
- 如果信息不足，请自然地询问用户补充缺少的信息
- 如果是重复提醒，可以说"这个提醒已经设置过了哦"

【重要】只有当你看到这个"提醒设置工具消息"时，才能确认提醒操作已执行.如果没有看到这个消息，说明提醒还未创建，不要假设提醒已设置成功.
"""

    return ""
