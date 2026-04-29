# -*- coding: utf-8 -*-

import re

# ========== Message source annotation (auto-injected based on message_source) ==========
# Injected at the code level — the LLM does not need to determine the message source

from agent.prompt.rendering import render_prompt_template
from util.profile_util import resolve_profile_label


_CALENDAR_IMPORT_TOOL_NAME = "日历导入入口"
_URL_PATTERN = re.compile(
    r"https?://[^\s，。；;,)）]+|/[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]+"
)

CONTEXTPROMPT_消息来源_用户消息 = """### Message Source
This is a real message sent to you by {user_label} via this chat channel."""

CONTEXTPROMPT_消息来源_提醒触发 = """### Message Source
This is a system-triggered scheduled reminder — not a message sent by {user_label}.
You need to proactively send a reminder message to {user_label} based on the reminder content.
[NOTE] Do not treat the reminder content as something the user said and reply to it."""

CONTEXTPROMPT_消息来源_主动消息 = """### Message Source
This is a scenario where you are initiating the conversation — not a message sent by {user_label}.
You need to proactively send a message to {user_label} based on the planned action.
[NOTE] You are the initiator of this message, not replying to the user."""


def get_message_source_context(message_source: str, context: dict) -> str:
    """
    Return the appropriate source annotation context based on message source.

    Args:
        message_source: Message source — "user" / "deferred_action"
        context: Full context dict used to render templates

    Returns:
        Formatted message source annotation
    """
    deferred_kind = (
        context.get("system_message_metadata", {}).get("kind")
        if isinstance(context, dict)
        else None
    )
    if message_source == "deferred_action":
        template = (
            CONTEXTPROMPT_消息来源_提醒触发
            if deferred_kind == "user_reminder"
            else CONTEXTPROMPT_消息来源_主动消息
        )
    elif message_source == "user":
        template = CONTEXTPROMPT_消息来源_用户消息
    else:
        raise ValueError(f"Unsupported message source: {message_source}")

    try:
        return render_prompt_template(template, context)
    except KeyError:
        _user_nickname = resolve_profile_label(context.get("user"), "user")
        if message_source == "deferred_action":
            if deferred_kind == "user_reminder":
                return f"""### Message Source
This is a system-triggered scheduled reminder — not a message sent by {_user_nickname}.
You need to proactively send a reminder message to {_user_nickname} based on the reminder content.
[NOTE] Do not treat the reminder content as something the user said and reply to it."""
            return f"""### Message Source
This is a scenario where you are initiating the conversation — not a message sent by {_user_nickname}.
You need to proactively send a message to {_user_nickname} based on the planned action.
[NOTE] You are the initiator of this message, not replying to the user."""
        if message_source == "user":
            return f"""### Message Source
This is a real message sent to you by {_user_nickname} via this chat channel. Please reply normally."""
        raise ValueError(f"Unsupported message source: {message_source}")


CONTEXTPROMPT_时间 = """### Current System Time
(24-hour format) {conversation[conversation_info][time_str]}"""

CONTEXTPROMPT_新闻 = """
{news_str}
"""

CONTEXTPROMPT_人物信息 = """### {character_label}'s Character Info
{character[user_info][description]}"""


CONTEXTPROMPT_人物资料 = """### {character_label}'s Character Profile
{context_retrieve[character_global]}
{context_retrieve[character_private]}"""

CONTEXTPROMPT_用户资料 = """### {user_label}'s Profile
{context_retrieve[user]}"""

# Pending reminders — only used when there are pending reminders
# Check context_retrieve[confirmed_reminders] for emptiness before using
CONTEXTPROMPT_待办提醒 = """### {user_label}'s Pending Reminders
{context_retrieve[confirmed_reminders]}"""


def get_reminders_context(context_retrieve: dict, user_nickname: str) -> str:
    """
    Get pending reminder context — only returns content when reminders exist.

    Args:
        context_retrieve: Context retrieval result dictionary
        user_nickname: User nickname

    Returns:
        Formatted context if there are pending reminders, otherwise empty string
    """
    reminders = context_retrieve.get("confirmed_reminders", "")
    if reminders and reminders.strip():
        return f"""### {user_nickname}'s Pending Reminders
{reminders}"""
    return ""


CONTEXTPROMPT_人物知识和技能 = """### {character_label}'s Knowledge and Skills
{context_retrieve[character_knowledge]}"""

CONTEXTPROMPT_人物状态 = """### {character_label}'s Current Status
Location: {character[user_info][status][place]}
Action: {character[user_info][status][action]}
Current state: {relation[relationship][status]}"""

CONTEXTPROMPT_当前目标 = """### {character_label}'s Current Goals
Long-term goal: {relation[character_info][longterm_purpose]}
Short-term goal: {relation[character_info][shortterm_purpose]}
Attitude toward {user_label}: {relation[character_info][attitude]}"""

CONTEXTPROMPT_当前的人物关系 = """### Current Relationship Between {character_label} and {user_label}
Relationship description: {relation[relationship][description]}
Closeness: {relation[relationship][closeness]}
Trust: {relation[relationship][trustness]}
Dislike: {relation[relationship][dislike]}
Known real name of {user_label}: {relation[user_info][realname]}
{character_label}'s nickname for {user_label}: {relation[user_info][hobbyname]}
{character_label}'s impression of {user_label}: {relation[user_info][description]}
"""

CONTEXTPROMPT_最近的历史对话 = """### Conversation History (last 15 messages)
{conversation[conversation_info][chat_history_str]}"""

# Semantically retrieved relevant history — only used when there are results
# Check context_retrieve[relevant_history] for emptiness before using
CONTEXTPROMPT_历史最相关的十条对话 = """### Relevant Conversation History (semantic retrieval)
The following are past conversations semantically related to the current topic:
{context_retrieve[relevant_history]}"""


def get_relevant_history_context(
    context_retrieve: dict, recent_history_str: str = ""
) -> str:
    """
    Get relevant conversation history context — only returns content when there are results.

    V2.13: Filters out messages already present in recent history to avoid duplication.

    Args:
        context_retrieve: Context retrieval result dictionary
        recent_history_str: Recent conversation history string used to filter duplicates

    Returns:
        Formatted context if relevant history exists, otherwise empty string
    """
    relevant_history = context_retrieve.get("relevant_history", "")
    if not relevant_history or not relevant_history.strip():
        return ""

    # V2.13: Filter out messages already present in recent history
    if recent_history_str:
        filtered_lines = []
        for line in relevant_history.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            # Check if this message already exists in recent history
            # Remove "- " prefix before comparing
            clean_line = line.lstrip("- ").strip()
            if clean_line and clean_line not in recent_history_str:
                filtered_lines.append(line)

        if not filtered_lines:
            return ""
        relevant_history = "\n".join(filtered_lines)

    return f"""### Relevant Conversation History (semantic retrieval)
The following are past conversations semantically related to the current topic:
{relevant_history}"""


# Condensed conversation history for proactive message scenarios (only the last few messages)
CONTEXTPROMPT_历史对话_精简 = """### Recent Conversation (last 3 rounds)
{recent_chat_history}"""

CONTEXTPROMPT_最新聊天消息 = """### {user_label}'s Latest Chat Message
{conversation[conversation_info][input_messages_str]}"""

# V2.15: Anti-duplicate-reply prompt (used for all message scenarios)
CONTEXTPROMPT_防重复回复 = """{proactive_forbidden_messages}

[STRICTLY FORBIDDEN — MUST COMPLY] The "messages you recently sent" listed above are content you must absolutely not repeat. You must:
- Not repeat the same question or topic
- Not use similar phrasing or expressions
- Not convey the same or similar meaning
- Respond from a completely different angle or topic
"""

CONTEXTPROMPT_初步回复 = """### {character_label}'s Initial Reply
{MultiModalResponses}"""

CONTEXTPROMPT_最新聊天消息_双方 = """### {user_label}'s Latest Chat Message
{conversation[conversation_info][input_messages_str]}

### {character_label}'s Latest Reply
{MultiModalResponses}"""

CONTEXTPROMPT_规划行动 = """### {character_label}'s Planned Action
{character_label} plans to proactively send a message to {user_label}. Action content: {system_message_metadata[prompt]}
[IMPORTANT] This is a message that {character_label} is initiating — not a message from {user_label}."""

CONTEXTPROMPT_系统提醒触发 = """### System Reminder Triggered
The following reminder has come due. {character_label} needs to proactively remind {user_label}:
Reminder content: {system_message_metadata[title]}
[IMPORTANT] This is reminder content that {character_label} should send to {user_label} — not a message from {user_label}. {character_label} should remind the user in a natural way based on this content."""

# V2.15 simplified: removed duplicate [STRICTLY FORBIDDEN] section — now uniformly provided by CONTEXTPROMPT_防重复回复
CONTEXTPROMPT_主动消息触发 = """### Proactive Message Triggered
{character_label} plans to proactively send a message to {user_label}.
Action content: {system_message_metadata[prompt]}
Proactive prompts sent this round: {proactive_times}

[IMPORTANT] This is a message that {character_label} is initiating — not a message from {user_label}.
"""

# V2.8: Reminder intent detected but tool not executed prompt
# Used when OrchestratorAgent sets need_reminder_detect=True but ReminderDetectAgent did not call a tool
CONTEXTPROMPT_提醒未执行 = """### System Notice: Reminder Setup Pending
The user's message appears to contain reminder-setting intent, but the system has not successfully created a reminder yet.
Possible reasons:
- Time expression was not specific enough (e.g. "a bit later", "in a while" — vague time)
- Missing required information (e.g. specific time or reminder content)

[IMPORTANT] Do not assume the reminder has been set successfully! You should:
1. Ask the user for a specific reminder time (if the time is unclear)
2. Confirm the specific reminder content (if the content is unclear)
3. Naturally guide the user to provide complete information

Do not say you remembered, noted, scheduled, arranged, or will handle the reminder.
In Chinese, avoid phrases such as "记下了", "安排好了", "安排上", "帮你定",
"设置好了", "交给我", "我来盯", or "我会提醒" until a reminder tool result
confirms setup.
Do not invent lead times, default reminder times, advance notice, or reminder
policies that the user did not request.
Ask one direct clarification question before any reminder can be considered set.
For Chinese replies, that question should explicitly ask "什么时候" or "几点"
when the reminder time is missing.
When setup is pending, only ask for the missing information. Do not first
acknowledge the reminder as arranged or partially arranged.
Still follow the JSON output format requirements above.

Example replies:
- "When would you like me to remind you?"
- "What time exactly?"
- "Sure, when would you like me to remind you about [content]?"
Bad Chinese replies:
- "订蛋糕的提醒安排上！那你周六大概几点需要提醒你呢？"
- "帮你定个本周六的蛋糕提醒！"
"""


# ========== Web Search ==========

CONTEXTPROMPT_联网搜索结果 = """### Web Search Results
{web_search_result}

[Note] The above is real-time information retrieved via web search. Please answer the user's question based on the search results:
- You may mention the source when citing information
- If the search results are insufficient to answer the question, say so honestly
- Express naturally in keeping with the character persona"""


def get_web_search_context(session_state: dict) -> str:
    """
    Get web search result context.

    Args:
        session_state: Session state dictionary

    Returns:
        Formatted search result context, or empty string if no results
    """
    web_search_result = session_state.get("web_search_result", {})

    if not web_search_result:
        return ""

    # Check if successful
    if not web_search_result.get("ok", False):
        error = web_search_result.get("error", "Search failed")
        return f"""### Web Search Notice
Search was unsuccessful: {error}
Please answer the user's question based on existing knowledge, or inform the user that search is temporarily unavailable."""

    # Get formatted result
    formatted = web_search_result.get("formatted", "")
    if not formatted:
        return ""

    return f"""### Web Search Results
{formatted}

[Note] The above is real-time information retrieved via web search. Please answer the user's question based on the search results:
- You may mention the source when citing information
- If the search results are insufficient to answer the question, say so honestly
- Express naturally in keeping with the character persona"""


def get_url_context(session_state: dict) -> str:
    """
    Get URL content context.

    Args:
        session_state: Session state dictionary

    Returns:
        Formatted URL content context, or empty string if none
    """
    url_context_str = session_state.get("url_context_str", "")

    if not url_context_str:
        return ""

    return f"""{url_context_str}

[Note] The above is a summary of the content from a link in the user's message. Please answer the user's question based on the link content:
- You may mention the link title or source
- If the link content is insufficient to answer the question, say so honestly
- Express naturally in keeping with the character persona"""


# ========== Generic Tool Result ==========


def _get_visible_timezone_name(user: dict) -> str | None:
    return user.get("timezone") or user.get("effective_timezone")


def _looks_like_explicit_timezone_question(message: str) -> bool:
    normalized = " ".join(str(message or "").lower().split())
    if not normalized:
        return False

    timezone_markers = ("时区", "timezone", "time zone")
    query_markers = ("什么", "哪个", "现在", "当前", "按", "用", "what", "which", "current", "using")
    return any(marker in normalized for marker in timezone_markers) and any(
        marker in normalized for marker in query_markers
    )


def _looks_like_explicit_local_time_or_date_question(message: str) -> bool:
    normalized = " ".join(str(message or "").lower().split())
    if not normalized:
        return False

    patterns = (
        r"现在.*几点",
        r"当地时间.*几点",
        r"现在当地时间",
        r"今天几号",
        r"今天星期几",
        r"今天日期",
        r"现在日期",
        r"当前日期",
        r"what time is it",
        r"current local time",
        r"local time",
        r"what date is it",
        r"current date",
        r"today'?s date",
    )
    return any(re.search(pattern, normalized) for pattern in patterns)


def get_inferred_timezone_visibility_context(
    session_state: dict,
    input_message: str,
    *,
    message_source: str = "user",
) -> str:
    if message_source != "user":
        return ""

    user = session_state.get("user") or {}
    timezone = _get_visible_timezone_name(user)
    if not timezone:
        return ""

    timezone_status = user.get("timezone_status")
    explicit_timezone_question = _looks_like_explicit_timezone_question(input_message)
    explicit_local_time_question = _looks_like_explicit_local_time_or_date_question(
        input_message
    )

    if explicit_timezone_question:
        if timezone_status == "system_inferred":
            source = user.get("timezone_source") or "unknown source"
            return (
                "### Timezone Context\n"
                f"Current time-sensitive interpretation should use {timezone}.\n"
                f"This timezone is system inferred from {source}.\n"
                "If you answer the user's timezone, local time, or local date question, mention that the timezone is inferred."
            )

        return (
            "### Timezone Context\n"
            f"Current user timezone should be treated as {timezone}.\n"
            "Use it when answering the user's explicit timezone question."
        )

    if timezone_status != "system_inferred" or not explicit_local_time_question:
        return ""

    source = user.get("timezone_source") or "unknown source"
    return (
        "### Timezone Context\n"
        f"Current time-sensitive interpretation should use {timezone}.\n"
        f"This timezone is system inferred from {source}.\n"
        "If you answer the user's timezone, local time, or local date question, mention that the timezone is inferred."
    )


def _get_inferred_timezone_note(session_state: dict, results: list[dict]) -> str:
    user = session_state.get("user") or {}
    timezone = _get_visible_timezone_name(user)
    if not timezone or user.get("timezone_status") != "system_inferred":
        return ""

    if not any("提醒" in str(entry.get("tool_name", "")) for entry in results):
        return ""

    source = user.get("timezone_source") or "unknown source"
    return (
        "Time-sensitive note: the reminder time above was interpreted using "
        f"{timezone} (system inferred from {source})."
    )


def get_tool_results_context(session_state: dict) -> str:
    """Render all tool execution results into a unified ### System Operation Results prompt block.

    Each tool call writes to session_state["tool_results"] via append_tool_result().
    This function is called when ChatWorkflow renders the prompt, injecting results for ChatResponseAgent.

    Returns:
        Formatted prompt block, or empty string if no results.
    """
    results: list[dict] = session_state.get("tool_results") or []
    if not results:
        return ""

    lines = ["### System Operation Results\n"]
    for entry in results:
        status = "Success" if entry.get("ok") else "Failed"
        lines.append(f"[{entry['tool_name']}]")
        lines.append(f"Status: {status}")
        lines.append(f"Result: {entry['result_summary']}")
        extra = entry.get("extra_notes", "")
        if extra:
            lines.append(f"Additional notes: {extra}")
        lines.append("")

    timezone_note = _get_inferred_timezone_note(session_state, results)
    if timezone_note:
        lines.append(timezone_note)
        lines.append("")

    lines += [
        '[Note] The above are the results of operations automatically executed by the system. Please reply to the user naturally based on the results:',
        '- Status "Success": Confirm the operation is complete and explain the result to the user.',
        '- Status "Failed": Explain the reason, and if necessary guide the user to provide more information or retry.',
        '- If there are "Additional notes": Reply according to the content of those notes.',
        "",
        '[IMPORTANT] Only confirm an operation has been executed when you see this "System Operation Results" block. Do not assume success when this block is absent.',
    ]
    return "\n".join(lines)


def get_calendar_import_direct_reply(session_state: dict) -> str:
    """Return a deterministic first reply for Google Calendar import entry links."""
    results: list[dict] = session_state.get("tool_results") or []
    for entry in results:
        if entry.get("tool_name") != _CALENDAR_IMPORT_TOOL_NAME or not entry.get("ok"):
            continue

        summary = str(entry.get("result_summary") or "")
        match = _URL_PATTERN.search(summary)
        if not match:
            return ""

        link = match.group(0).rstrip("。.,，；;)")
        return (
            f"可以，打开这个入口导入 Google Calendar：{link}\n"
            "登录或验证邮箱后，点击 Start Google Calendar import 授权 Google。"
        )
    return ""


def reminder_tool_result_counts_as_setup(entry: dict) -> bool:
    if entry.get("tool_name") != "提醒操作":
        return False
    action = _tool_result_action(entry)
    return action != "list"


def get_reminder_operation_direct_reply(session_state: dict) -> str:
    """Return deterministic reminder CRUD acknowledgements from tool results."""
    results: list[dict] = session_state.get("tool_results") or []
    summaries = [
        str(entry.get("result_summary") or "").strip()
        for entry in results
        if reminder_tool_result_counts_as_setup(entry)
    ]
    return "；".join(summary for summary in summaries if summary)


def _tool_result_action(entry: dict) -> str:
    extra_notes = str(entry.get("extra_notes") or "")
    match = re.search(r"(?:^|;\s*)action=([^;]+)", extra_notes)
    return match.group(1).strip() if match else ""
