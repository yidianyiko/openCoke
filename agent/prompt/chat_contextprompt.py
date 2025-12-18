# -*- coding: utf-8 -*-
CONTEXTPROMPT_时间 = '''### 系统当前时间
（24小时制）{conversation[conversation_info][time_str]}'''

CONTEXTPROMPT_新闻 = '''
{news_str}
'''

CONTEXTPROMPT_人物信息 = '''### {character[platforms][wechat][nickname]}的人物信息
{character[user_info][description]}'''


CONTEXTPROMPT_人物资料 = '''### {character[platforms][wechat][nickname]}的人物资料
{context_retrieve[character_global]}
{context_retrieve[character_private]}'''

CONTEXTPROMPT_用户资料 = '''### {user[platforms][wechat][nickname]}的人物资料
{context_retrieve[user]}'''

CONTEXTPROMPT_待办提醒 = '''### {user[platforms][wechat][nickname]}的待办提醒
{context_retrieve[confirmed_reminders]}'''

CONTEXTPROMPT_人物知识和技能 = '''### {character[platforms][wechat][nickname]}的人物知识和技能
{context_retrieve[character_knowledge]}'''

CONTEXTPROMPT_人物状态 = '''### {character[platforms][wechat][nickname]}的人物状态
所在地点：{character[user_info][status][place]}
行动：{character[user_info][status][action]}
当前状态：{relation[relationship][status]}'''

CONTEXTPROMPT_当前目标 = '''### {character[platforms][wechat][nickname]}的当前目标
长期目标：{relation[character_info][longterm_purpose]}
短期目标：{relation[character_info][shortterm_purpose]}
对{user[platforms][wechat][nickname]}的态度：{relation[character_info][attitude]}'''

CONTEXTPROMPT_当前的人物关系 = '''### {character[platforms][wechat][nickname]}与{user[platforms][wechat][nickname]}当前的人物关系
关系描述：{relation[relationship][description]}
亲密度：{relation[relationship][closeness]}
信任度：{relation[relationship][trustness]}
反感度：{relation[relationship][dislike]}
已知{user[platforms][wechat][nickname]}的真名：{relation[user_info][realname]}
{character[platforms][wechat][nickname]}对{user[platforms][wechat][nickname]}的亲密昵称：{relation[user_info][hobbyname]}
{character[platforms][wechat][nickname]}对{user[platforms][wechat][nickname]}的印象描述：{relation[user_info][description]}
'''

CONTEXTPROMPT_历史对话 = '''### 历史对话
{conversation[conversation_info][chat_history_str]}'''

# 精简版历史对话，用于主动消息场景（只包含最近几条消息）
CONTEXTPROMPT_历史对话_精简 = '''### 最近对话（最近3轮）
{recent_chat_history}'''

CONTEXTPROMPT_最新聊天消息 = '''### {user[platforms][wechat][nickname]}的最新聊天消息
{conversation[conversation_info][input_messages_str]}'''

CONTEXTPROMPT_初步回复 = '''### {character[platforms][wechat][nickname]}的初步回复
{MultiModalResponses}'''

CONTEXTPROMPT_最新聊天消息_双方 = '''### {user[platforms][wechat][nickname]}的最新聊天消息
{conversation[conversation_info][input_messages_str]}

### {character[platforms][wechat][nickname]}的最新回复
{MultiModalResponses}'''

CONTEXTPROMPT_规划行动 = '''### {character[platforms][wechat][nickname]}的规划行动
{character[platforms][wechat][nickname]}计划主动向{user[platforms][wechat][nickname]}发送消息，行动内容：{conversation[conversation_info][future][action]}
【重要】这是{character[platforms][wechat][nickname]}要主动发起的消息，不是{user[platforms][wechat][nickname]}发来的消息。'''

CONTEXTPROMPT_系统提醒触发 = '''### 系统提醒触发
以下是到期的提醒，{character[platforms][wechat][nickname]}需要主动提醒{user[platforms][wechat][nickname]}：
提醒内容：{system_message_metadata[action_template]}
【重要】这是{character[platforms][wechat][nickname]}要发给{user[platforms][wechat][nickname]}的提醒内容，不是{user[platforms][wechat][nickname]}发来的消息。{character[platforms][wechat][nickname]}应该基于这个提醒内容，用自然的方式提醒用户。'''

CONTEXTPROMPT_主动消息触发 = '''### 主动消息触发
{character[platforms][wechat][nickname]}计划主动向{user[platforms][wechat][nickname]}发送消息。
行动内容：{conversation[conversation_info][future][action]}
本轮已主动催促次数：{proactive_times}

【重要】这是{character[platforms][wechat][nickname]}要主动发起的消息，不是{user[platforms][wechat][nickname]}发来的消息。
【严格禁止】请仔细查看上面的“最近对话”，如果{character[platforms][wechat][nickname]}刚刚发过类似内容的消息，你必须生成完全不同的新内容，绝对不能重复或相似。
'''

# V2.7 新增：提醒工具结果上下文
CONTEXTPROMPT_提醒工具结果 = '''### 提醒设置工具消息
{【提醒设置工具消息】}

【说明】以上是系统自动处理提醒的结果。请根据这个结果，用自然的方式回复用户。
例如：
- 如果提醒创建成功，可以说“好的，我帮你设好了”
- 如果信息不足，请自然地询问用户补充缺少的信息
- 如果是重复提醒，可以说“这个提醒已经设置过了哦”
'''
