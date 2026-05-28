# Coke 需求与用户旅程矩阵草案

Status: draft
Created: 2026-05-28
Scope: Phase 1 个人监督陪伴

## 0. 使用边界

本草案是 Coke 的顶层需求与用户旅程矩阵，用来约束后续架构重构路线图。

本文只记录产品需求、用户旅程、系统必须支持的能力和当前需求取舍；不在需求文档中引用代码、文档、文件路径或行号。实现依据、架构评审和代码定位应放在后续 discovery、architecture review、issue 或 execution plan 中。

关键前提：

- Coke 目前不需要保留历史生产数据。
- 没有真实投入生产的环境约束。
- 破坏性重构可以接受。
- 不为了兼容旧数据、旧协议、旧 runtime shape 设计复杂迁移。
- 架构重构必须服务明确用户需求和用户旅程，而不是为了架构漂亮。

## 1. 产品阶段

本需求矩阵当前只约束 Phase 1：个人监督陪伴。

Phase 1 的核心产品目标：

- 帮助个人用户维持目标、习惯、任务和提醒。
- 通过日常对话、个人提醒、主动 follow-up 和个人 channel 触达，形成持续监督陪伴关系。
- 让用户能在自己的通信 channel 中自然使用 Coke，而不是为了使用系统进入复杂后台。

Phase 1 当前用户：

- 个人 Coke 用户。
- 管理员/运营者，只作为内部运维和调试用户存在。
- 外部 channel operator，仅在 shared channel 获客/交付路径需要时存在。

已确认不作为当前 Phase 1 需求和 clean rebuild 驱动：

- 为旧数据、旧协议、旧 runtime shape 做复杂迁移。

旅程命名口径：

- “注册登录”只表示身份识别与会话建立，不等同于 onboarding。
- “Onboarding”从用户第一次成功对话算起。
- 已经实现的功能默认不因为当前不是核心就移除；只有当能力明确造成维护负担、误导产品合同、阻塞重构，或用户确认不再需要时，才进入删除讨论。

## 2. 当前用户旅程矩阵

| # | Phase 1 内部角色 | 用户类型 | 触发入口 | 用户目标 | 系统必须成立的行为 | 状态 |
|---|---|---|---|---|---|---|
| 1 | 支撑旅程：注册登录 | 个人用户 | 注册页、登录页、邮箱验证页 | 创建账号、登录、建立会话，让系统能稳定识别当前用户和后续 owner 归属 | 支持注册、登录、邮箱验证、重发验证邮件、忘记/重置密码、当前用户查询、会话/token、稳定 customer owner identity。注意：这不是 onboarding，onboarding 从第一次成功对话算起 | 已确认保留；订阅/访问状态可保留，但不应主导核心架构 |
| 2 | 支撑旅程：个人 channel 可达性 | 个人用户 | channel 管理页、personal WeChat channel 页 | 创建并连接自己的 personal WeChat channel，让日常对话、提醒和主动 follow-up 可达 | 支持查看 channel 状态、创建 channel、发起连接、轮询连接状态、断开连接、移除 channel、绑定 delivery route。移除后不再作为可用 delivery route，但不影响用户账号和历史提醒归属。personal WeChat 是 Phase 1 默认个人入口 | 已确认保留 |
| 3 | 核心旅程：日常对话 | 个人用户 | personal WeChat 或 shared channel inbound message | 和 assistant 日常对话；当前仅支持文本输入；需要回复时获得文字回复；无意义内容/自然收尾可有意不回复；第一次成功对话是 onboarding 起点 | inbound message 必须绑定可信 account/customer context；系统执行 single-Agent turn；系统必须判断消息是否需要回应：需要回应则文字回复，不需要回应则 intentional no-reply，处理慢则 processing fallback + 最终异步文字回复，处理失败则错误/失败可观测；intentional no-reply 必须区别于系统失败 | 已确认核心 |
| 4 | 核心旅程：个人提醒 | 个人用户 | 对话中的 reminder intent，或提醒管理页 | 创建、查看、编辑、完成、删除个人提醒，并在到点时收到提醒 | 提醒必须 owner-scoped；支持自然语言和 UI/API 创建、查看、编辑、完成、删除；支持相对时间、具体时间、时区、重复规则；到点后进入 Interaction LLM，由 LLM 知道这是系统提醒，并用符合角色语气的文字提醒告知用户；重复提醒触发或完成本次后推进下一次有效触发，删除重复提醒删除整个系列 | 已确认核心 |
| 5 | 支撑/扩展旅程：好友关系 | 个人用户 | 好友页、公开好友链接、二维码 | 生成自己的好友链接；别人扫码或打开后登录/注册并建立好友关系；管理好友列表 | 好友链接可打开；link session 可记录来源；登录用户可通过 link session 建立 active friendship；用户可 reset/disable link、查看和移除好友 | 待确认优先级 |
| 6 | 核心扩展旅程：共享提醒 | 个人用户 + 好友 | 对话中的 scheduling intent，或共享提醒 API/UI | 给好友创建共享提醒，查看或取消共享提醒 | 必须存在 friendship；共享提醒创建前检查 receiver conflict；创建后立即 active；为 creator/receiver 建立提醒投影；通知是 informational；pending accept/reject 不作为当前需求 | 已确认属于 Phase 1，仍需确认是否核心 |
| 7 | 支撑/待验证旅程：日历导入 | 个人用户 | 日历导入页，或 assistant 给出的 handoff link | 把 Google Calendar 一次性导入 Coke 提醒 | 导入前确认 account/conversation ready；用户授权日历访问；系统拉取 primary calendar events；未来事件转为 Coke-owned reminders；历史事件只保留导入记录 | 待确认是否 Phase 1 必须 |
| 8 | 支撑旅程：agent 设置 | 个人用户 | agent 设置页 | 设置自己的 assistant 名称、称呼、persona、背景、说话风格、额外规则、状态、proactive/memory 开关 | 设置必须 customer-scoped；支持查看、更新、重置；runtime 使用设置影响对话、提醒和主动 follow-up 行为 | 待确认字段级范围 |
| 9 | 运维旅程：内部管理 | 管理员/运营者 | admin 后台 | 查看客户、渠道、delivery、shared channels、admin accounts，维护运行状态 | admin auth 独立；支持查看和维护运行状态；该旅程服务内部运营/调试，不是终端用户核心价值 | 已确认属于 Phase 1，倾向只保留内部运维定位 |
| 10 | 待验证旅程：shared channel 获客/交付 | 管理员/外部 channel operator | shared channel 配置页、外部 provider webhook | 配置 shared channels，使外部用户能进入 Coke worker/runtime | admin 可配置 shared channel；provider inbound 需要 normalize；首次 inbound 可完成用户/provisioning/delivery route；outbound 按 provider route 送达 | 已确认属于 Phase 1，仍需确认真实获客价值 |

## 3. 当前需求清单

这些能力进入当前需求清单，但不自动等于最高优先级。后续架构路线图应按用户旅程优先级排序。

| 当前需求项 | 归属旅程 | 当前需求表述 |
|---|---|---|
| 消息接收与标准化入队 | 日常对话；channel 可达性；shared channel 交付 | 系统必须接收 personal WeChat/shared channel inbound，把消息绑定到可信 Coke account/customer context，并写入 worker 可消费的 input message。 |
| 消息发送与 outbound delivery | 日常对话；个人提醒；共享提醒；shared channel 交付 | 系统必须把可见回复、提醒触发、主动 follow-up 推送到对应 delivery route。文字回复是当前产品输出合同；media URL delivery 是通道能力，不等于 AI 生成/理解媒体能力。 |
| 消息打断、会话锁、rollback | 日常对话；个人提醒 | 同一 conversation 的处理必须有锁；新消息/rollback 场景不能把旧 turn 的上下文继续当作最新用户意图；已发送 partial reply 要进入历史，避免重复回复。 |
| 对话生成与分段可见输出 | 日常对话 | Interaction Agent 必须输出用户可见文字回复；当前可按 1-3 段输出。需要回复时，文字回复必须经 outbound delivery 送达。 |
| 回复必要性判断与 intentional no-reply | 日常对话 | 日常对话不是每条消息都必须回复。系统必须判断用户消息是否需要回应：需要回应则文字回复；不需要回应则 intentional no-reply；处理慢则 processing fallback + 最终异步文字回复；处理失败则错误/失败可观测。intentional no-reply 必须区别于系统失败、runtime empty output、工具兜底失败。 |
| 对话历史与用户记忆 | 日常对话；agent 设置；个性化支撑 | 系统必须维护必要的近期对话历史、用户偏好、关系描述、边界感和打扰意愿，让后续对话、提醒和主动 follow-up 理解前后文。 |
| 提醒识别与个人提醒 CRUD | 个人提醒 | 用户可通过自然语言或提醒管理页创建、查看、编辑、完成、删除个人提醒；系统需理解相对时间、具体时间、时区、重复规则，并保持 owner-scoped；完成重复提醒只完成本次，删除重复提醒删除整个系列。 |
| 提醒触发与周期提醒 | 个人提醒；共享提醒投影 | 到点提醒必须进入 Interaction LLM；LLM 必须知道这是系统提醒，并用符合角色语气的文字提醒告知用户。重复提醒触发或完成本次后推进下一次有效触发；同一 owner 同一触发时间的多个提醒合并为一次提醒事件。 |
| 主动 follow-up | channel 可达性；日常对话；agent 设置 | 系统可在对话后规划主动 follow-up，通过内部提醒触发；用户/agent 设置可关闭 proactive；频率必须受上下文和用户打扰意愿限制，避免骚扰。 |
| 用户资料、关系描述、角色目标/态度更新 | 日常对话；agent 设置；个性化支撑 | 系统可以更新用户真名/昵称/描述、关系描述、角色长期/短期目标和态度，作为个性化支撑；该项不包含数值化亲密度、信任度、反感度。 |
| 多 channel/connector delivery | personal WeChat；shared channel 交付 | 当前需求是统一接入 personal WeChat 和已确认 shared channels，保持 provider normalize 与 delivery route 分离；不是 legacy connector 原样保留。 |
| 可用性与延迟目标 | 日常对话；个人提醒；提醒触发；主动通知 | Phase 1 核心旅程必须有明确可用性和延迟目标；具体 SLO 数值待核心旅程和部署形态确认后再定。 |

## 4. 明确不进入当前需求清单的能力

| 能力 | 当前结论 |
|---|---|
| 语音输入理解 | 媒体/语音/图片功能当前一律暂缓，不加入 Phase 1 当前需求，以后再考虑。当前 Coke 仅支持文本输入与文字回复。 |
| 图片输入理解 | 媒体/语音/图片功能当前一律暂缓，不加入 Phase 1 当前需求，以后再考虑。 |
| 图片生成 | 暂不加入 Phase 1 当前需求。 |
| 照片库、朋友圈、照片删除 | 暂不加入 Phase 1 当前需求；若以后需要内容资产管理或社交展示，应作为新的用户旅程单独定义。 |
| 数值化亲密度、信任度、反感度 | 不加入当前需求；只保留非数值化的用户偏好、关系描述、边界感、打扰意愿。 |
| 关系衰减、反感拉黑 | 不加入当前需求。 |
| 角色忙闲日程脚本 | 不加入当前需求。 |
| 角色忙所以 hold 用户消息 | 不加入当前需求；Phase 1 优先保证用户求助、提醒、对话可达。若需要“不打扰”，应从用户侧打扰意愿、免打扰时间、提醒触达策略定义。 |
| QueryRewrite/ContextRetrieve 固定 agent 阶段 | 不作为用户可见需求或固定 agent 阶段；只保留“需要历史上下文和用户记忆”的产品需求。 |
| legacy 聊天式硬编码管理员指令 | 不加入当前需求；当前只保留 Admin Web/API 运维旅程。 |
| legacy 固定 SLO 数值 | 不直接继承固定的 P99 和错误率数值；当前只要求核心旅程必须有可用性和延迟目标。 |
| 旧数据兼容层、旧协议 adapter、旧 runtime shape 兼容 | 不加入当前需求，除非后续被明确确认为当前产品需求。 |

## 5. 用户旅程细节

### 5.1 注册登录

已确认：

- 该旅程只应叫“注册登录”，不应命名为首次进入 Coke 或 onboarding。
- Onboarding 从用户第一次成功对话算起。
- 已经实现的功能默认不移除；不属于核心合同的已实现子功能，应保留当前事实，但不能主导核心架构。

用户旅途：

1. 个人用户打开注册或登录入口。
2. 用户完成注册或登录。
3. 必要时用户完成邮箱验证。
4. 系统建立会话/token，并能返回当前用户身份。
5. 后续 channel、reminder、friendship、shared reminder 都能挂到同一个 owner identity。

系统必须支持：

- 注册。
- 登录。
- 邮箱验证。
- 重发验证邮件。
- 忘记/重置密码。
- 当前用户查询。
- 会话/token。
- customer owner identity。

已实现但不应主导核心架构：

- subscription/access status。
- membership/subscription 状态返回。

架构约束：

- Auth 的核心职责是稳定识别个人用户和 owner 归属。
- 注册登录旅程不应扩展成复杂 membership、subscription、多租户平台模型。

### 5.2 个人 WeChat channel 接入与可达性

已确认：

- personal WeChat 是 Phase 1 默认个人入口。
- 该旅程是日常对话、提醒触发、主动 follow-up 的可达性支撑旅程。

用户旅途：

1. 已登录个人用户打开 channel 管理入口。
2. 用户查看当前 personal WeChat channel 状态。
3. 如果没有 channel，用户创建 personal WeChat channel。
4. 用户发起连接，并等待连接状态从 pending 变为 connected。
5. 用户可在需要时断开连接或移除 channel。
6. 连接成功后，系统能把该用户的对话回复、提醒、主动 follow-up 送达到 personal WeChat。

系统必须支持：

- personal WeChat channel status。
- create channel。
- connect channel。
- poll connection status。
- disconnect channel。
- remove channel。
- delivery route 绑定。

必须成立的状态：

- missing。
- disconnected。
- pending。
- connected。
- error。
- archived。

架构约束：

- personal WeChat channel 的核心合同是 channel ownership、connection state 和 delivery route。
- Agent Runtime 只应依赖稳定的 account/channel/delivery contract，不应直接依赖 WeChat adapter 或连接细节。
- adapter 失败、连接中、断开、移除等状态应留在 Channel/Gateway 边界内表达，不能泄漏成 agent prompt/runtime 的特殊分支。
- 用户移除 personal WeChat channel 后，该 channel 不再作为可用 delivery route，但不影响用户账号、历史提醒归属或其他用户数据。

### 5.3 日常对话

已确认：

- 日常对话是 Phase 1 核心旅程。
- 第一次成功对话正式定义为 Coke 的 onboarding 起点。
- Agent 处理超时时，用户应先收到 processing fallback，最终文字回复再异步送达；这是 Phase 1 必须合同。
- 对无意义内容、自然收尾、或用户明确不希望被打扰的场景，系统可以有意不生成回复；这不是系统失败，也不是静默丢消息。
- 日常对话不是每条消息都必须回复；系统必须判断用户消息是否需要回应。
- 当前仅支持文本输入与文字回复；语音、图片输入理解已暂缓（见 §4），以后再考虑。

用户旅途：

1. 用户已经有可识别身份和可达 channel。
2. 用户通过 personal WeChat 或 shared channel 发送文本消息。
3. 系统把 inbound message 绑定到可信 account/customer context。
4. 系统执行 single-Agent turn。
5. 系统判断用户消息是否需要回应。
6. 如果需要回复，用户收到即时文字回复；如果处理超时，用户先收到 processing fallback，最终文字回复再异步送达。
7. 如果模型基于上下文判断无需回复，系统可以不发送用户可见消息，但该结果应和 runtime failure 区分。
8. 如果处理失败，错误/失败必须可观测，不能和 intentional no-reply 混在一起。
9. 如果这是用户第一次成功对话，Coke onboarding 从这一刻开始。

系统必须支持：

- 接收 personal WeChat inbound message。
- 接收已确认 shared channel inbound message。
- 支持文本输入。
- 将 inbound message 绑定到可信 account/customer context。
- 写入 input message。
- worker 拉取并执行 single-Agent turn。
- 生成同步或异步文字回复。
- 超时返回 processing fallback。
- 最终文字回复通过 outbound delivery 送回 channel。
- 判断用户消息是否需要回应。
- 支持 intentional no-reply 语义，避免把模型有意不回复误判为系统失败。
- 处理失败时提供可观测失败状态，不能和 no-reply 混在一起。
- 维护必要的历史上下文和用户记忆，让回复理解前后文。

必须成立的子功能：

- account context 可信，不靠 agent 猜用户。
- conversation/session 能稳定识别。
- 同步等待和异步补发语义清楚；超时时必须先给 processing fallback，最终文字回复必须异步送达。
- outbound route 可用。
- 用户可见输出的最低且当前必要合同是文字回复；不要求语音回复、图片回复或输入输出媒体类型一致。
- 系统失败、runtime empty output、模型有意 no-reply 必须可区分：系统失败不能静默丢；有意 no-reply 不应触发兜底废话；处理慢不能被误判为 no-reply。

架构约束：

- 日常对话的核心合同是可信 account context、文字回复、turn execution、回复必要性判断、reply delivery、timeout/fallback semantics、intentional no-reply、failure observability。
- Agent Runtime 不应承担 provider 身份解析、channel provisioning、delivery route 选择等 Channel/Gateway 职责。
- Bridge/Worker 的队列、锁、reply waiter、output dispatcher 可以重构，但必须保持用户可见语义：消息被接收、会处理；需要回复时会用文字回复；超时有 processing fallback，最终文字回复可异步送达；模型有意 no-reply 时不强行补废话。
- 需要把 intentional no-reply 建成显式 output disposition，而不是把所有空输出都当作错误兜底。

### 5.4 个人提醒

已确认：

- 个人提醒是 Phase 1 核心旅程。
- 提醒可以由用户在对话中创建，也可以由用户在提醒管理页创建。
- 到点提醒不应只是机械发送模板消息；应进入 Interaction LLM，由 LLM 知道这是系统提醒，并用符合角色语气的文字提醒告知用户。
- 重复提醒是提醒的一种，属于个人提醒核心需求。

用户旅途：

1. 用户通过对话表达提醒意图，或打开提醒管理页。
2. 用户创建一个一次性或重复个人提醒。
3. 用户可以查看自己的提醒列表和单条详情。
4. 用户可以编辑提醒内容和触发时间。
5. 用户可以完成提醒。对于一次性提醒，完成表示这件事已处理；对于重复提醒，完成表示完成本次。
6. 用户可以删除提醒。对于一次性提醒，删除该提醒；对于重复提醒，删除整个系列。
7. 提醒到点后，系统把“这是系统提醒”的上下文交给 Interaction LLM。
8. Interaction LLM 用符合角色语气的文字提醒告知用户。
9. 如果是重复提醒，本次触发或用户完成本次后，系统推进下一次触发时间。

系统必须支持：

- 对话创建提醒。
- 提醒管理页创建提醒。
- 查看提醒列表。
- 查看单条提醒详情。
- 编辑提醒内容。
- 编辑提醒触发时间。
- 创建重复提醒。
- 编辑重复提醒规则。
- 完成提醒。
- 删除提醒。
- 到点触发提醒。
- 触发后进入 Interaction LLM 生成角色化文字提醒。
- 重复提醒每次触发后推进下一次触发时间。
- 重复提醒完成语义是完成本次，不删除整个系列。
- 删除重复提醒时删除整个系列。
- 同一 owner 下同一触发时间的多个提醒应合并为一次提醒事件，由 Interaction LLM 一次性告知多项提醒内容，而不是分别触发多次用户可见提醒。
- 所有提醒必须绑定当前个人用户，不能串到其他 owner。
- 提醒创建、编辑、触发必须正确处理时区。

重复提醒规则限制：

- 支持固定周期重复和间隔重复。
- 间隔重复必须有频率上限，避免骚扰和系统滥用；具体最小间隔数值待确认。
- 时间段内重复是一种重复提醒能力：只在指定时间窗口和可选星期内触发。
- 每次触发后，系统必须推进下一次有效触发时间。
- 如果下一次触发时间不在有效时间段内，系统必须推进到下一个有效时间段。
- 完成重复提醒只完成本次；删除重复提醒才删除整个系列。
- 同一 owner 下同一触发时间的多个提醒应合并为一次提醒事件；合并只影响触达方式，不改变每条提醒自身的内容、归属和后续状态推进。
- 支持哪些固定周期类型、是否需要最大触发次数、最大触发次数如何告知用户，仍需确认。

暂不混入本轮确认：

- duration。
- 共享提醒投影。
- 日历导入生成提醒。

架构约束：

- 个人提醒的核心合同不是“直接发送一条固定通知”，而是“提醒事件触发后进入 Interaction LLM，由角色化 assistant 以文字方式提醒用户”。
- 提醒运行层可以负责时间、状态和触发；用户可见表达应由 Interaction LLM 完成。
- 重复提醒是提醒的一种，也是个人提醒核心合同的一部分；提醒运行层必须能根据规则推进下一次触发。
- 提醒触发应支持同一 owner 同一触发时间的合并事件，避免用户在同一时间收到多条分散提醒。
- 完成重复提醒只完成本次；删除重复提醒才删除整个系列。
- 提醒必须 owner-scoped，不能依赖 LLM 自己猜测提醒属于谁。

## 6. 架构路线图输入

### 必须先确认的需求

1. Phase 1 内部优先级：10 条旅程虽然都属于 Phase 1，但仍需确认哪些是核心用户价值、哪些是支撑能力、哪些只是内部运维或待验证交付。
2. Phase 1 核心留存旅程排序：已确认日常对话和个人提醒是核心旅程；仍需确认二者相对优先级，以及 proactive follow-up、personal WeChat、好友/共享提醒、calendar import、agent settings 中哪些必须优先保留。
3. shared channels 的产品角色：外部 provider 是真实获客/交付路径，还是已实现但不优先驱动核心架构的实验路径。
4. 好友和共享提醒是否是 Phase 1 核心社交监督能力，还是支撑个人监督的扩展能力。
5. Google Calendar import 是否是 Phase 1 必须能力；如果保留，是一次性 import 足够，还是需要持续 sync。
6. Agent settings 的字段级保留范围：persona/background/speaking_style/extra_rules/status/proactive/memory 哪些真实用户理解并使用。
7. Admin surface 是否只服务内部运维和调试；不要再把它解释为其他产品方向的原型。

### 不应优先驱动核心架构的能力

在上述需求没有被确认前，以下能力默认保留当前事实，但不应驱动核心架构设计：

- memo-runtime live integration。
- media tools 和 vendor wrappers（媒体/语音/图片功能已暂缓，见 §4；以后再考虑）。
- old billing/access gate 和 quota enforcement。
- CLI bridge。
- 多候选 pending action 扩展。
- no-op 用户数据 stub。
- 与 retired public entry、旧 direct channel runtime、pending accept/reject flows 相关的兼容路径。

### 应优先重构的架构方向

这些方向已经能映射到当前核心旅程：

- 对话/提醒 path 的 bus/store 解耦：优先服务日常对话和个人提醒。
- 数据访问连接管理和可观测性：优先服务日常对话、个人提醒、日历导入、agent 设置的稳定性。
- Agent runtime 拆分：只围绕当前 tools 和旅程拆 intent、scheduling、envelope、guardrail，不做脱离当前旅程的抽象。
- Reminder + Scheduling 的 per-turn compensation/outbox：优先覆盖个人提醒、好友关系、共享提醒。
- Gateway write path 的 product notification/outbound 异步化：优先覆盖好友关系、共享提醒。
- web auth hardening：先覆盖 admin/customer 当前页面，不做脱离当前页面的复杂权限平台。
- cross-process tracing：围绕 inbound、agent turn、reminder fire、shared-reminder create/cancel、calendar import run 建 trace。

### 应暂缓的重构

- 完整迁移系统、旧数据兼容层、旧协议 adapter。

## 7. 待确认事项

下一轮继续逐条确认：

- 注册登录旅程是否按当前细分口径确认。
- 个人 WeChat channel 接入与可达性的子功能是否完整。
- 个人提醒是否是 Phase 1 最核心留存路径，以及 duration 对个人提醒是否是核心需求。
- 好友关系是 Phase 1 核心社交监督能力，还是支撑共享提醒的辅助能力。
- 共享提醒是否属于保留核心旅程，还是实验性能力。
- Calendar import 是否是 Phase 1 必须能力。
- Agent settings 的字段级保留范围。
- Admin 是否只保留内部运维定位。
- shared channel provider 是否真实承担获客/交付。
