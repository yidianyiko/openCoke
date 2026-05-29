# Coke 需求与用户旅程矩阵草案

Status: draft
Created: 2026-05-28
Scope: 当前产品：个人监督陪伴、好友系统、共享提醒、Product notification、账号/数据生命周期

## 0. 使用边界

本草案是 Coke 当前产品的顶层需求与用户旅程矩阵，用来定义系统必须支持的用户旅程、功能和子功能。

本文只记录产品需求、用户旅程、系统必须支持的能力和当前需求取舍；不在需求文档中引用代码、文档、文件路径或行号。实现依据、代码定位和重构方案不进入本文。架构重构设计与重构优先级在 clean-rebuild 目标架构设计 spec（2026-05-28-coke-clean-rebuild-target-architecture-design.md）中维护，不在本文。

关键前提：

- Coke 目前不需要保留历史生产数据。
- 没有真实投入生产的环境约束。
- 破坏性重构可以接受。
- 不为了兼容旧数据、旧协议、旧 runtime shape 设计复杂迁移。
- 系统实现必须服务明确用户需求和用户旅程，而不是为了抽象漂亮。

## 1. 产品范围

本需求矩阵约束 Coke 当前产品，不再按阶段标签弱化或推迟已确认能力。

当前产品目标：

- 帮助个人用户维持目标、习惯、任务和提醒。
- 通过日常对话、个人提醒、主动 follow-up reminder 和个人 channel 触达，形成持续监督陪伴关系。
- 通过好友系统和共享提醒支持人与人之间的监督协作。
- 通过 informational Product notification 告知好友关系、共享提醒和系统事件的结果与错误信息。
- 以用户全局时区解释和展示提醒、日历和好友可用性。
- 让用户能在自己的通信 channel 中自然使用 Coke，而不是为了使用系统进入复杂后台。
- 保留必要的账号访问状态、公开说明、FAQ、演示、隐私和条款页面，作为用户进入、理解和合规支撑；这些支撑面不作为核心监督用户价值。

当前产品用户：

- 个人 Coke 用户。

当前系统边界中的非产品用户参与方：

- Channel provider / shared channel。WhatsApp 入口当前由 shared WhatsApp channel 承载；Evolution、Linq、Ecloud 依赖 provider-backed/shared channel 边界完成 inbound、用户/route 绑定和 outbound delivery；这不是独立产品旅程。

已确认不作为当前产品需求：

- 为旧数据、旧协议、旧 runtime shape 做复杂迁移。

首次使用口径：

- Onboarding 完成口径：注册/登录完成、至少一个可用 personal channel 已连接、用户通过该 channel 发出一条消息且系统成功接收。
- Onboarding 指用户从未完成到完成首次激活的产品旅程；assistant 可以发送首次引导，但 onboarding 完成不要求创建首个 reminder 或完成 agent 设置。
- 已经实现的功能默认不因为当前不是核心就移除；只有当能力明确造成维护负担、误导产品合同、阻碍当前产品合同清晰，或用户确认不再需要时，才进入删除讨论。

## 2. 当前用户旅程矩阵

| # | 产品角色 | 用户类型 | 触发入口 | 用户目标 | 系统必须成立的行为 | 状态 |
|---|---|---|---|---|---|---|
| 1 | 支撑旅程：注册登录 | 个人用户 | 注册页、登录页、邮箱验证页、账号访问状态页、公开说明页 | 创建账号、登录、建立会话；在账号不可用或需要验证时知道下一步 | 支持注册、登录、邮箱验证、重发验证邮件、忘记/重置密码、当前用户查询、会话/token；支持向用户展示邮箱验证、订阅/访问状态、账号暂停或阻塞原因，并给出下一步；公开说明、FAQ、演示、隐私、条款页面可作为产品理解和合规支撑 | 已确认保留 |
| 2 | 支撑旅程：首次激活 | 个人用户 | 注册/登录后、channel 连接完成后、首次 personal channel inbound message | 完成第一次可用激活，确认账号、channel 和首条消息路径都成立 | Onboarding 完成必须同时满足：注册/登录完成、至少一个可用 personal channel 已连接、用户通过该 channel 发出一条消息且系统成功接收；不要求用户创建首个 reminder 或完成 agent 设置；assistant 可以提供首次引导，但完成口径以产品路径事实为准 | 当前产品合同 |
| 3 | 支撑旅程：个人 channel 可达性 | 个人用户 | channel 管理页、personal channel 页 | 在 personal WeChat 或 shared WhatsApp channel 上建立一个个人通信入口，让日常对话、提醒和主动 follow-up 可达 | 当前只支持个人用户在 personal WeChat 或 shared WhatsApp channel 中拥有一个可达 channel；支持查看 channel 状态、选择 channel 类型、创建 channel、发起连接、轮询连接状态、移除 channel、失败后重试或重新链接。Personal WeChat 可以是独立 personal lifecycle；WhatsApp 入口当前由 shared WhatsApp channel 承载，Evolution、Linq、Ecloud 依赖 provider-backed/shared channel 边界，但用户可见上仍是自己的对话入口。移除后该 channel 不再可用，但不影响用户账号和历史提醒归属。提醒和主动触达走用户当前唯一已连接的 personal channel；当前只允许链接一个 personal channel | 已确认保留 |
| 4 | 核心旅程：日常对话 | 个人用户 | personal WeChat 或 shared WhatsApp channel inbound message | 和 assistant 日常对话；当前支持 channel 可承载的多模态输入；需要回复时获得文字回复；系统明确 no-reply 时不收到消息；处理慢时收到等待提示并稍后收到最终文字回复 | inbound message 必须绑定可信 account/customer context；系统执行 single-Agent turn；shared WhatsApp channel inbound 必须先完成标准化和用户/route 绑定；系统必须判断消息是否需要回应：需要回应则文字回复，系统明确 intentional no-reply 则不发送任何用户可见消息，处理超时但仍在处理则发送可见等待文字并最终异步文字回复，处理失败则错误/失败可观测；当前输出合同只要求文字回复，不要求语音、图片或视频回复；intentional no-reply 必须区别于系统失败 | 已确认核心 |
| 5 | 核心旅程：用户时区 | 个人用户 | agent 设置页、提醒日历页、对话中的时区表达 | 让所有提醒、日历展示和好友可用性按同一个个人时区理解 | 用户只有一个全局默认时区；可在设置页查看/修改，也可通过对话整体切换；不支持给单条 reminder 设置独立时区；用户提到另一个时区时应按整体时区切换或确认切换来解释；已存在 reminder 的绝对触发时刻不因时区切换被静默改写，只按新时区展示 | 当前产品合同 |
| 6 | 核心旅程：个人提醒 | 个人用户 | 对话中的 reminder intent，提醒日历页，或主动 follow-up 场景 | 创建、查看、编辑、完成、删除个人提醒；在到点时收到提醒；对没有触发时间的 reminder 获得安排时间询问；接收符合系统频率约束的主动 follow-up reminder | 提醒必须 owner-scoped；支持自然语言和页面创建、查看、编辑、完成、删除；提醒页面是日历页面，用来展示用户可直接管理的 reminder；共享 reminder 也出现在提醒日历页并展示关联好友标识，但直接编辑遵守共享提醒边界；支持相对时间、具体时间、全局时区、重复规则和可设置 duration（默认 15 分钟）；支持无触发时间 reminder；禁止创建完全相同的可行动个人 reminder；主动 follow-up 是一种特殊类型 reminder，但不显示在提醒日历页，也不允许用户直接修改；用户关闭 proactive 时一并取消未触发的主动 follow-up reminder；到点后进入 Interaction LLM，由 LLM 知道这是系统提醒，并用符合角色语气的文字提醒告知用户；每天晚上 8 点汇总无触发时间 reminder，询问用户是否要安排触发时间；重复提醒触发或完成本次后推进下一次有效触发，删除重复提醒删除整个系列 | 已确认核心 |
| 7 | 核心旅程：好友关系 | 个人用户 | 好友页、公开好友链接、二维码、对话中的好友链接码 | 生成自己的好友链接；别人扫码或打开后登录/注册并建立好友关系；管理好友列表 | 好友链接可打开；未登录访问者可先进入登录/注册承接；登录用户可通过 link session 或对话中的好友链接码建立 active friendship；同一对用户不重复创建 active friendship；用户可 reset/disable link、查看和移除好友；pending friend request accept/reject 不作为当前需求 | 当前产品合同 |
| 8 | 核心旅程：共享提醒 | 个人用户 + 一个或多个好友 | 对话中的 social scheduling intent、好友可用性查询、提醒日历页、共享提醒列表/取消入口 | 给一个或多个好友创建同一个共享提醒，查看或取消共享提醒；在约时间前查看一个或多个好友可用时间 | 必须存在 active friendship；每个好友指代必须能解析到唯一 active friend；可查询隐私安全的一个或多个好友可用性；共享提醒创建前检查每个 receiver conflict；任一 receiver 冲突时不静默部分创建；通过检查后创建一个 group shared reminder；creator 和所有 receivers 到点后都应各自收到自己的关联提醒；共享 reminder 出现在提醒日历页并展示关联好友标识；用户处理完成只处理自己这一侧的 projection；任一参与者可取消整个 group；通知是 informational；禁止创建完全相同的 active shared reminder；pending accept/reject 不作为当前需求 | 当前产品合同 |
| 9 | 支撑旅程：Product notification | 个人用户 + 好友 | 好友关系建立、共享提醒创建/取消、系统事件或错误事件 | 收到事实清楚、可理解的信息通知，知道发生了什么以及失败时下一步是什么 | 只发送 informational 和 system notification，不做审批或行动执行；必须覆盖好友关系创建、共享提醒创建、共享提醒取消、关联错误/失败/部分失败/未送达/冲突/取消失败；通知事实至少包含谁、做了什么、对象、时间/时区/duration；有错误时必须包含用户可理解错误信息，不能暴露 raw provider error 或内部错误码；最终可见文字由 Interaction LLM 基于结构化事实和错误事实生成 | 当前产品合同 |
| 10 | 支撑旅程：日历导入 | 个人用户 | 日历导入页，或 assistant 给出的 handoff link | 把 Google Calendar 一次性导入 Coke 提醒，并可停止后续 Google Calendar 授权 | 导入前确认 account/conversation ready；用户授权日历访问；系统拉取 calendar events；未来事件转为 Coke-owned reminders；event 标题和描述进入 reminder 内容，event 开始时间进入 reminder 触发时间，event duration 进入 reminder duration（event 无 duration 时按默认 15 分钟）；全天 event 导入为该日期 0 点触发的 reminder；recurring event 优先导入为 Coke recurring reminder；无法可靠表达为当前重复规则时，导入为未来可见 occurrence 对应的一次性 reminders，并在导入结果中说明；同一个 calendar event 重复导入时直接跳过，不生成重复 reminder，不需要用户确认；历史事件不生成 reminder；导入完成后向用户反馈成功导入数、跳过数、降级项和失败项；用户可以停止或撤销 Google Calendar 授权，撤销只影响未来导入，不删除已导入的 Coke-owned reminders；当前只确认一次性导入，不引入持续 sync | 已确认保留；一次性导入 |
| 11 | 支撑旅程：agent 设置 | 个人用户 | agent 设置页 | 设置自己的 assistant 名称、称呼、persona、背景、说话风格、额外规则、proactive 开关和 memory 开关，并查看 channel 连接状态 | 设置必须 customer-scoped；支持查看、更新、重置；用户可以配置 assistant 的用户可见表现和长期偏好；关闭 proactive 后不再创建新的主动 follow-up reminder，并取消未触发的主动 follow-up reminder；关闭 proactive 不影响普通个人 reminder、无触发时间汇总、日常对话回复或 Product notification；关闭 memory 后不再使用、新增或更新长期记忆，但不删除既有长期记忆；重新打开 memory 后可继续使用仍存在的长期记忆；当前不支持用户自助清除长期记忆 | 已确认保留；字段级范围已确认 |
| 12 | 支撑旅程：账号/数据生命周期 | 个人用户 | channel 管理页、提醒日历页、好友页、agent 设置页、日历导入页 | 理解自己能移除哪些连接、数据和关系，以及哪些账号级动作暂不支持 | 当前支持移除 personal channel、删除/完成个人 reminders、取消 shared reminders、移除好友、关闭 memory 使用、停止或撤销 Google Calendar 授权；这些动作不删除账号本身；当前不支持用户自助删除账号、完整账号导出、完整擦除或清除长期记忆 | 当前产品合同 |
| 13 | 支撑能力：provider-backed/shared channel 接入 | 个人用户；channel provider 边界 | provider webhook、shared WhatsApp channel、Evolution、Linq、Ecloud inbound/outbound | 让依赖 provider/shared channel 的个人会话入口可以进入 Coke 对话、提醒和主动 follow-up 送达 | provider/shared channel inbound 必须标准化；首次 inbound 或连接完成时必须能绑定可信 Coke user/customer 和送达 route；outbound 必须按 provider/shared channel 送达；provider 错误必须能映射到用户可理解的 channel 状态和恢复动作；该能力支撑个人 channel 可达性，不作为独立产品旅程 | 已确认保留；shared WhatsApp channel、Evolution、Linq、Ecloud 依赖 |

## 3. 当前需求清单

本节把矩阵中的用户旅程归并为当前需求项；同一需求项可能服务多个旅程。

| 当前需求项 | 归属旅程 | 当前需求表述 |
|---|---|---|
| 账号访问状态与公开说明 | 注册登录；channel 可达性；日历导入 | 系统可以向用户展示账号访问状态、邮箱验证、订阅/访问状态、账号暂停或阻塞原因，并把用户引导到下一步；公开说明、FAQ、演示、隐私和条款页面可保留为产品理解和合规支撑。subscription/access status 是当前需求项。 |
| 首次激活 | 注册登录；channel 可达性；日常对话 | Onboarding 完成必须同时满足：用户完成注册/登录、至少一个可用 personal channel 已连接、用户通过该 channel 发出一条消息且系统成功接收。assistant 可以发送首次引导，但完成 onboarding 不要求用户创建首个 reminder、完成 agent 设置或走完固定教程。 |
| 用户时区 | 用户时区；个人提醒；共享提醒；日历导入；agent 设置 | 用户只有一个全局默认时区；可在设置页查看和修改，也可通过对话整体切换。提醒创建、编辑、展示、提醒日历页、无触发时间汇总、好友可用性和共享提醒都使用该全局时区。不支持单条 reminder 独立时区。用户提到另一个时区时，系统应按整体时区切换或确认切换处理；已存在 reminder 的绝对触发时刻不因时区切换被静默改写，只按新时区展示。 |
| 消息接收与标准化入队 | 日常对话；channel 可达性；provider-backed/shared channel 接入 | 系统必须接收 personal WeChat 或 shared WhatsApp channel inbound，把消息绑定到可信 Coke account/customer context，并写入 worker 可消费的 input message。inbound 可以包含文本、图片、语音等 channel 可承载的多模态内容；顶层需求要求系统能接收并归一到可处理输入，不要求输出媒体内容。 |
| 消息发送与 outbound delivery | 日常对话；个人提醒；共享提醒；provider-backed/shared channel 接入 | 系统必须把可见回复、提醒触发、主动 follow-up 推送到用户当前已连接的唯一 personal channel。当前个人用户只能在 personal WeChat 或 shared WhatsApp channel 中拥有一个可达 channel。文字回复是当前产品输出合同；media URL delivery 是通道能力，不等于要求 AI 生成媒体回复。提醒触发后如果用户没有可用 channel 或发送失败，不能视为成功送达。 |
| 消息打断、会话锁、rollback | 日常对话；个人提醒 | 同一 conversation 的处理必须有锁；新消息/rollback 场景不能把旧 turn 的上下文继续当作最新用户意图；已发送 partial reply 要进入历史，避免重复回复。 |
| 对话生成与分段可见输出 | 日常对话 | Interaction Agent 必须输出用户可见文字回复；当前可按 1-3 段输出。需要回复时，文字回复必须经 outbound delivery 送达。 |
| 回复必要性判断与 intentional no-reply | 日常对话 | 日常对话不是每条消息都必须回复。系统必须判断用户消息是否需要回应：需要回应则文字回复；系统明确产生 intentional no-reply 时不发送任何用户可见消息；处理超时但仍在处理时发送可见等待文字，并在完成后发送最终异步文字回复；处理失败则错误/失败可观测。intentional no-reply 必须区别于系统失败、空输出异常、工具兜底失败。 |
| 对话历史与用户记忆 | 日常对话；agent 设置；个性化支撑 | 系统必须维护必要的近期对话历史、用户偏好、关系描述、边界感和打扰意愿，让后续对话、提醒和主动 follow-up 理解前后文。长期记忆受 memory 开关控制；关闭 memory 后不再使用、新增或更新长期记忆，但不删除既有记忆；重新打开 memory 后可继续使用仍存在的长期记忆。当前不支持用户自助清除长期记忆。 |
| 提醒识别与个人提醒 CRUD | 个人提醒 | 用户可通过自然语言或提醒日历页创建、查看、编辑、完成、删除个人提醒；提醒日历页以日历为主视图展示 reminder；系统需理解相对时间、具体时间、全局时区、重复规则和可设置 duration（默认 15 分钟），并保持 owner-scoped；支持无触发时间 reminder；支持一条消息中的批量 reminder 操作；禁止创建完全相同的可行动个人 reminder：同一 owner、同一事项/内容、同一触发时间，或同一 owner、同一事项/内容且双方都无触发时间；duration、创建入口和表达方式不进入重复定义；相似但不完全相同不硬拒绝；完成重复提醒只完成本次，删除重复提醒删除整个系列；创建、编辑、完成、删除后应给用户文字确认。 |
| 提醒触发与周期提醒 | 个人提醒；共享提醒触达 | 到点提醒必须形成 reminder trigger event 并进入 Interaction LLM；LLM 必须知道这是系统提醒，并用符合角色语气的文字提醒告知用户。重复提醒触发或完成本次后推进下一次有效触发；同一 owner 同一触发时间的多个 reminder 在提醒时合并成一次提醒告知，但每条 reminder 及其事件仍保持独立；无可用 channel 或发送失败时必须保留可观测未送达状态。 |
| 无触发时间 reminder 汇总询问 | 个人提醒 | 对没有触发时间的 reminder，系统每天晚上 8 点汇总仍未安排时间的 reminder，通过 Interaction LLM 询问用户是否要为这些 reminder 安排触发时间。 |
| 主动 follow-up reminder | 个人提醒；channel 可达性；日常对话；agent 设置 | 主动 follow-up 是一种特殊类型 reminder，用于 assistant 基于用户目标、习惯、任务或上下文主动关心用户；不显示在提醒日历页，不允许用户直接修改；用户/agent 设置可关闭 proactive，关闭时不再创建新的主动 follow-up reminder，并一并取消未触发的主动 follow-up reminder；重新打开 proactive 后只影响未来是否可以创建新的主动 follow-up reminder，不恢复之前已取消的 follow-up；频率必须受上下文和系统反骚扰规则限制，避免骚扰；当前不提供免打扰或通知偏好设置；触达、送达失败、未送达处理遵守个人提醒规则；顶层需求不限定具体规划算法。 |
| Product notification | Product notification；好友关系；共享提醒；个人提醒触达；provider-backed/shared channel 接入 | 系统只发送 informational 和 system notification，不通过 notification 做审批或行动执行。必须覆盖好友关系创建、共享提醒创建、共享提醒取消、关联系统事件和错误事件；通知事实至少包含谁、做了什么、对象、时间/时区/duration。失败、部分失败、未送达、冲突或取消失败时，notification 必须包含用户可理解错误信息，例如对方 channel 不可用、这个时间和对方已有安排冲突、取消没有成功；不暴露 raw provider error、内部错误码、队列状态或底层 delivery attempt。最终可见文字由 Interaction LLM 基于结构化事实和错误事实生成。 |
| 日历导入 | 日历导入；个人提醒；账号/数据生命周期 | 用户可以授权 Google Calendar，把未来 calendar events 一次性导入为 Coke reminders。导入生成的 reminder 归属当前个人用户；event 标题和描述进入 reminder 内容，event 开始时间进入触发时间，event duration 进入 reminder duration（event 无 duration 时按默认 15 分钟）。全天 event 导入为该日期 0 点触发的 reminder。recurring event 优先保留重复语义并导入为 Coke recurring reminder；无法可靠表达为当前重复规则时，导入为未来可见 occurrence 对应的一次性 reminders，并在导入结果中说明。同一个 calendar event 重复导入时直接跳过，不生成重复 reminder，不需要用户确认。历史事件不生成 reminder。导入完成后，系统必须向用户反馈成功导入数、跳过数、降级项和失败项。用户可以停止或撤销 Google Calendar 授权；撤销只影响未来导入，不删除已经导入的 Coke-owned reminders。当前只确认一次性导入，不要求持续 sync。 |
| Agent settings 配置 | agent 设置；日常对话；个人提醒；主动 follow-up reminder | 用户可以查看、修改和重置自己的 assistant 名称、用户称呼、persona、背景信息、说话风格、额外规则、proactive 开关和 memory 开关，并查看 channel 连接状态。设置必须 customer-scoped。重置恢复默认设置。关闭 memory 后不再使用、新增或更新长期记忆，但不删除既有长期记忆；重新打开 memory 后可继续使用仍存在的长期记忆。当前不支持用户自助清除长期记忆。memory 开关不影响完成当前对话所需的近期上下文。 |
| 用户资料、关系描述、角色目标/态度更新 | 日常对话；agent 设置；个性化支撑 | 系统可以更新用户真名/昵称/描述、关系描述、角色长期/短期目标和态度，作为个性化支撑；该项不包含数值化亲密度、信任度、反感度。 |
| 好友关系 | 好友关系；共享提醒 | 用户可以生成、查看、重置和禁用自己的公开好友链接和二维码；访问好友链接的用户登录或注册后可以直接建立 active friendship；用户可以通过对话中的好友链接码建立 active friendship；用户可以查看好友列表和移除好友。同一对用户不重复创建 active friendship；不能和自己建立好友；pending friend request accept/reject 不作为当前需求。 |
| 共享提醒 | 共享提醒；好友关系；个人提醒触达；Product notification | 用户可以给一个或多个 active friends 创建一个 group shared reminder、查看共享提醒、取消共享提醒，并在约时间前查询一个或多个好友可用性。创建共享提醒必须把每个 receiver 解析到唯一 active friend；缺少标题、时间或必要上下文时必须追问；创建前必须检查每个 receiver conflict；任一 receiver 冲突时，系统说明谁冲突、谁可用，并让 creator 调整时间或参与者，不能静默部分创建。通过检查后共享提醒立即 active，creator 和所有 receivers 都应在到点后各自收到自己的关联 projection。共享 reminder 出现在个人提醒日历页并展示关联好友标识。用户处理完成只处理自己这一侧的 projection，不自动替其他参与者完成；任一参与者可以取消整个 group；pending shared reminder accept/reject 不作为当前需求；通知只作为信息告知，不是审批。禁止创建完全相同的 active shared reminder：同一 creator、同一参与者集合、同一标题/活动内容、同一触发时间；duration 不进入重复定义。 |
| 个人 channel/provider delivery | personal WeChat；shared WhatsApp channel；provider-backed/shared channel 接入 | 当前个人用户只允许在 personal WeChat 或 shared WhatsApp channel 中拥有一个可达 channel；provider-backed/shared channel 必须在用户可见上表现为该用户自己的对话入口。WhatsApp 入口当前由 shared WhatsApp channel 承载，Evolution、Linq、Ecloud 依赖 provider-backed/shared channel 边界。不是 legacy connector 原样保留。 |
| 账号/数据生命周期 | 账号/数据生命周期；channel 可达性；个人提醒；共享提醒；好友关系；agent 设置；日历导入 | 当前支持移除 personal channel、删除或完成个人 reminders、取消 shared reminders、移除好友、关闭 memory 使用、停止或撤销 Google Calendar 授权。移除 channel 不删除账号和 reminders；删除/完成 reminders 不删除账号；取消 shared reminder 停止整个 group 的关联 projections；移除好友不自动取消既有 shared reminders；关闭 memory 不删除长期记忆；撤销 Google Calendar 授权不删除已导入的 Coke-owned reminders。当前不支持用户自助删除账号、完整账号导出、完整擦除或用户自助清除长期记忆。 |
| 可用性与延迟目标 | 日常对话；个人提醒；提醒触发；Product notification；主动通知 | 当前核心旅程必须有明确可用性和延迟目标；具体 SLO 数值不在本文定义。 |

## 4. 明确不进入当前需求清单的能力

| 能力 | 当前结论 |
|---|---|
| 语音回复、图片回复、视频回复 | 当前输出合同只要求文字回复；不要求 assistant 用语音、图片或视频回复用户。 |
| 图片生成 | 暂不加入当前产品需求。 |
| Memo runtime / memo cards / memo search / memo review queue / agent memo proposals | 明确不加入当前产品需求；当前只保留受 memory 开关控制的长期记忆能力，不定义用户可见 memo runtime。 |
| 照片库、朋友圈、照片删除 | 暂不加入当前产品需求；若以后需要内容资产管理或社交展示，应作为新的用户旅程单独定义。 |
| 数值化亲密度、信任度、反感度 | 不加入当前需求；只保留非数值化的用户偏好、关系描述、边界感、打扰意愿。 |
| 关系衰减、反感拉黑 | 不加入当前需求。 |
| 角色忙闲日程脚本 | 不加入当前需求。 |
| 角色忙所以 hold 用户消息 | 不加入当前需求；当前产品优先保证用户求助、提醒、对话可达。主动触达频率由 proactive 系统行为约束，不引入用户可配置免打扰或通知偏好。 |
| 单条 reminder 独立时区 | 不加入当前需求；当前只有用户全局默认时区，切换时区是整体切换。 |
| 用户自助删除账号 / 完整账号导出 / 完整擦除 | 不加入当前需求；当前只定义移除 channel、删除/完成 reminders、取消 shared reminders、移除好友、停止 Google Calendar 授权等局部生命周期动作。 |
| 用户自助清除长期记忆 | 不加入当前需求；memory 开关只控制是否使用、新增和更新长期记忆，不提供清除既有长期记忆入口。 |
| 免打扰 / 通知偏好设置 | 不加入当前需求；当前只保留 proactive 开关，普通 reminders、shared reminders、system notifications 不受额外通知偏好控制。 |
| QueryRewrite/ContextRetrieve 固定 agent 阶段 | 不作为用户可见需求或固定 agent 阶段；只保留“需要历史上下文和用户记忆”的产品需求。 |
| legacy 聊天式硬编码管理指令 | 不加入当前需求；不因为 legacy 管理指令保留通用管理 surface。 |
| legacy 固定 SLO 数值 | 不直接继承固定的 P99 和错误率数值；当前只要求核心旅程必须有可用性和延迟目标。 |
| 旧数据兼容层、旧协议 adapter、旧 runtime shape 兼容 | 不加入当前需求，除非后续被明确确认为当前产品需求。 |

## 5. 用户旅程细节

### 5.1 注册登录

已确认：

- Onboarding 完成口径见 §1「首次使用口径」；首次激活旅程见 §5.2；首次对话引导见 §5.4。
- 已经实现的功能默认不移除；不属于核心合同的已实现子功能，应保留当前事实，但不能主导核心需求。

用户旅途：

1. 个人用户打开注册或登录入口。
2. 用户完成注册或登录。
3. 必要时用户完成邮箱验证。
4. 系统建立会话/token，并能返回当前用户身份。
5. 后续 channel、reminder、friendship、shared reminder 都能在同一个已登录账号下继续使用。

系统必须支持：

- 注册。
- 登录。
- 邮箱验证。
- 重发验证邮件。
- 忘记/重置密码。
- 当前用户查询。
- 会话/token。
- 当前用户身份。

已实现并保留的支撑能力：

- subscription/access status。
- membership/subscription 状态返回。
- 账号访问状态、邮箱验证状态、账号暂停或阻塞原因展示。
- 公开说明、FAQ、演示、隐私和条款页面。

### 5.2 首次激活

已确认：

- Onboarding 完成必须同时满足：注册/登录完成、至少一个可用 personal channel 已连接、用户通过该 channel 发出一条消息且系统成功接收。
- 创建首个 reminder 不是 onboarding 完成条件。
- 完成 Agent settings 不是 onboarding 完成条件。
- assistant 可以在首次对话中发送引导，但 onboarding 完成不依赖用户走完固定教程或回复固定内容。
- personal channel 的“可用”必须表示 Coke 已经可以通过该 channel 发送对话回复、提醒和主动 follow-up；不能只表示 provider 侧连接成功。
- 首条消息必须能绑定到可信 account/customer context；不能靠 assistant 猜测用户身份。

用户旅途：

1. 用户完成注册或登录。
2. 用户进入 channel 连接入口。
3. 用户连接 personal WeChat 或 shared WhatsApp channel 承载的个人会话入口。
4. 系统确认该 channel 已完成可信用户绑定和可用送达 route。
5. 用户通过该 channel 发出第一条消息。
6. 系统成功接收该 inbound message，并绑定到该用户的可信 account/customer context。
7. 系统把该用户标记为 onboarding 完成。
8. assistant 可以发送首次引导或继续处理这条消息的真实意图。

系统必须支持：

- 判断用户是否已注册/登录。
- 判断用户是否有至少一个可用 personal channel。
- 判断首条 personal channel inbound message 是否已经成功接收。
- 把首条 inbound message 绑定到可信 account/customer context。
- 在三项条件全部满足后把 onboarding 视为完成。
- 在未满足条件时向用户展示或发送下一步，例如登录、连接 channel、重试连接或发送第一条消息。
- onboarding 完成状态不因用户还没有创建 reminder、没有设置 assistant persona、没有打开提醒日历页而阻塞。

需求边界：

- 首次激活的核心合同是账号、channel 和首条消息路径成立。
- onboarding 引导话术是对话体验，不是完成条件。
- 系统不能把 provider 连接中、连接失败、未绑定 route、首条消息未入站等状态算作 onboarding 完成。

### 5.3 个人通信 channel 接入与可达性

已确认：

- 当前个人用户只允许链接一个 personal channel。
- personal channel 当前只支持 personal WeChat 或 shared WhatsApp channel 承载的个人会话入口。
- WhatsApp 入口当前由 shared WhatsApp channel 承载；Evolution、Linq、Ecloud 依赖 provider-backed/shared channel 边界。
- provider-backed/shared channel 在用户可见上仍然表现为该用户自己的对话入口，而不是独立产品旅程。
- 用户页面和对话中只需要看到 channel 类型和连接状态，例如 WeChat、WhatsApp、未连接、连接中、已连接、连接失败、需要重连；Evolution、Linq、Ecloud 这类 provider 名称不作为普通用户需要选择或理解的产品对象暴露。
- 用户可见的“已连接”必须表示 Coke 已经能通过该 channel 发送对话回复、提醒和主动 follow-up；不能只表示 provider 侧连接成功。
- 当前只允许链接一个 personal channel，唯一已连接的 channel 就是发送渠道。
- 该旅程是日常对话、提醒触发、主动 follow-up 的可达性支撑旅程。
- 当前不需要支持“断开 channel”动作；用户只需要能移除 channel。
- 用户移除 personal channel 后，系统不能再通过该 channel 触达用户。
- 移除 personal channel 不删除账号、不删除 reminder、不改变 reminder owner。
- 用户不需要看到已移除 channel 或历史 channel；移除后页面回到未连接 channel、可重新连接的状态。
- 用户可以重新连接或重新链接一个 personal channel；未来提醒、对话回复和主动 follow-up 走新的已连接 channel。

用户旅途：

1. 已登录个人用户打开 channel 管理入口。
2. 用户查看当前 personal channel 状态。
3. 如果没有 channel，用户在 personal WeChat 或 shared WhatsApp channel 中选择并创建一个可达 channel。
4. 如果所选 channel 依赖 provider-backed/shared channel，系统向用户展示该 channel 的连接动作和连接状态。
5. 用户发起连接，并等待连接状态从“连接中”变为“已连接”或“连接失败”。
6. 连接完成或首次有效 inbound 到达后，系统把 provider 身份绑定到可信 Coke user/customer 和可用送达 route。
7. 如果连接失败或 provider 不可用，用户看到“连接失败”“需要重连”“可重试”这类可理解状态和恢复动作；普通用户文案不展示 Evolution、Linq、Ecloud 的内部错误原因。
8. 用户可以重试连接、刷新连接状态、移除 channel 后重新链接。
9. 如果用户已经链接一个 personal channel，系统不允许再同时链接第二个 personal channel；用户需要先移除现有 channel。
10. 用户可在需要时移除 channel。
11. 连接成功后，系统能把该用户的对话回复、提醒、主动 follow-up 送达到该 personal channel。
12. 用户移除 channel 后，不能再通过该 channel 收到对话回复、提醒或主动 follow-up。
13. 如果用户从 personal WeChat 切换到 shared WhatsApp channel，或从 shared WhatsApp channel 切换到 personal WeChat，需要先移除旧 channel。
14. 用户重新连接或重新链接一个 personal channel 后，未来触达走新的已连接 channel。

系统必须支持：

- personal channel status。
- WeChat personal channel。
- shared WhatsApp channel。
- provider-backed channel inbound/outbound。
- provider-backed channel 的连接入口。
- provider-backed channel 的连接状态轮询或刷新。
- provider-backed channel 的用户/route 绑定。
- provider-backed channel 的 provider 错误映射。
- provider-backed channel 的重试、移除和重新链接。
- 刷新连接状态、重试连接（含义见下方「provider-backed channel 用户可见子功能」）。
- 同一用户最多一个已链接 personal channel。
- create channel、connect channel、poll connection status、remove channel。
- 唯一已连接的 personal channel 作为发送渠道。
- 移除、重新链接、personal WeChat 与 shared WhatsApp channel 之间切换的语义见下方「移除、重新链接语义」，此处不重复。

必须成立的用户可见状态：

- 未连接。
- 连接中。
- 已连接。
- 连接失败/需要重连。

provider-backed channel 用户可见子功能：

- 用户看到的是自己的对话入口，不需要理解 provider-backed/shared channel 的内部实现。
- WhatsApp 入口当前由 shared WhatsApp channel 承载；Evolution、Linq、Ecloud 都依赖 provider-backed/shared channel 边界。
- 普通用户文案只表达 WeChat/WhatsApp 和连接状态，不要求用户选择或排查 Evolution、Linq、Ecloud 等 provider。
- provider-backed channel 必须能从用户侧发起链接或连接流程。
- 连接中表示用户已经发起连接，但 Coke 还没有确认该 channel 已完成用户绑定和可用送达；连接中不能视为可达。
- 用户在连接中时可以刷新连接状态。
- 用户在连接失败后可以重试连接。
- 连接流程可以因 provider 不同而有不同交互形态，但需求层不限定具体实现方案。
- provider-backed channel 必须把连接状态归一到 personal channel 状态。
- provider-backed channel 的入站消息必须能绑定到当前可信 Coke user/customer；不能因为 provider 身份模糊而进入错误用户。
- provider-backed channel 必须完成可信 Coke user/customer 绑定，并建立可用的送达 route，才能被视为用户可见“已连接”。
- provider-backed channel 的 outbound 失败不能被视为成功送达。
- provider-backed channel 的 provider 错误应映射为用户可理解的 channel 不可用、连接失败或需要重新连接。
- 普通用户不需要看到 raw provider error，也不需要知道具体是 Evolution、Linq、Ecloud 返回了什么内部错误。
- 用户必须能在失败后重试连接或重新链接。
- 用户必须能移除 provider-backed channel。
- 移除 provider-backed channel 后，该 channel 的 provider identity 和 route 不再用于未来触达。
- 移除后，用户可见状态回到“未连接”，不展示已移除或历史 channel 列表。
- provider-backed/shared channel 计入同一用户最多一个可达 channel 的限制。
- 切换 provider-backed/shared channel 与切换 personal WeChat / shared WhatsApp channel 一样，需要先移除旧 channel。
- provider-backed channel 不引入第二套用户身份、第二套提醒 owner 或独立操作角色。

移除、重新链接语义：

- 用户移除 personal channel 后，不能再通过该 channel 收到对话回复、提醒或主动 follow-up。
- 移除 channel 不删除用户账号。
- 移除 channel 不删除 reminder，也不改变 reminder owner。
- 用户页面不展示已移除 channel 或历史 channel；是否保留 provider identity/route 的内部记录不是用户可见需求。
- channel 不可用期间到点的 reminder 进入未送达状态。
- 用户重新连接或重新链接一个 personal channel 后，未来提醒、对话回复和主动 follow-up 走新的已连接 channel。
- 未送达提醒可以补发，或在提醒日历页展示为未送达。
- 如果用户从 personal WeChat 切换到 shared WhatsApp channel，或从 shared WhatsApp channel 切换到 personal WeChat，需要先移除旧 channel，因为当前只允许一个可达 channel。

需求边界：

- personal channel 的核心合同是 channel ownership、connection state 和用户可达性。
- provider-backed channel 的核心合同是用户可见连接状态、provider inbound 标准化、用户/route 绑定、outbound delivery 和可观测失败。
- 日常对话、提醒和主动 follow-up 只需要依赖可信 account、channel 和 delivery 状态，不需要理解 WeChat、WhatsApp 或 provider 的连接细节。
- 连接失败、连接中、移除等状态应表现为统一 channel 状态，不能变成用户需要理解的特殊对话分支。
- provider 身份、provider 错误和 route 绑定是系统内部细节；普通用户只看到 channel 类型、连接状态和恢复动作。
- 用户移除 personal channel 后，该 channel 不再可用于触达，但不影响用户账号、历史提醒归属或其他用户数据。

### 5.4 日常对话

已确认：

- 日常对话是当前核心旅程。
- personal WhatsApp 指 shared WhatsApp channel 承载的个人会话，不是独立 personal WhatsApp channel。
- 首次对话时可以进入 onboarding 指导分支；onboarding 完成口径见 §5.2 首次激活。
- Agent 处理超时时，用户应先收到可见等待文字，最终文字回复再异步送达；这是当前必须合同。
- 对无意义内容、自然收尾、或用户明确不希望被打扰的场景，系统可以有意不生成回复；这不是系统失败，也不是静默丢消息。
- 日常对话不是每条消息都必须回复；系统必须判断用户消息是否需要回应。
- 系统明确产生 intentional no-reply 时，不发送任何用户可见消息。
- 当前支持 channel 可承载的多模态输入，但输出合同只要求文字回复。
- 当前不要求 assistant 用语音、图片或视频回复用户。

用户旅途：

1. 用户已经有可识别身份和可达 channel。
2. 用户通过 personal WeChat 或 shared WhatsApp channel 发送文本、图片、语音等 channel 可承载的消息。
3. 系统把 inbound message 绑定到可信 account/customer context。
4. 系统执行 single-Agent turn。
5. 系统判断用户消息是否需要回应。
6. 如果需要回复，用户收到即时文字回复；如果处理超时但仍在处理，用户先收到可见等待文字，最终文字回复再异步送达。
7. 如果系统明确产生 intentional no-reply，系统不发送任何用户可见消息，但该结果应和系统失败区分。
8. 如果处理失败，错误/失败必须可观测，不能和 intentional no-reply 混在一起。
9. 如果这是用户首次使用场景，系统可以进入 onboarding 指导分支。

系统必须支持：

- 接收 personal WeChat inbound message。
- 接收 shared WhatsApp channel inbound message。
- 接收 provider-backed/shared channel inbound message。
- 支持 channel 可承载的多模态输入。
- 将 inbound message 绑定到可信 account/customer context。
- 写入 input message。
- worker 拉取并执行 single-Agent turn。
- 生成同步或异步文字回复。
- 超时时发送可见等待文字。
- 最终文字回复通过 outbound delivery 送回 channel。
- 判断用户消息是否需要回应。
- 支持 intentional no-reply 语义，避免把模型有意不回复误判为系统失败。
- 处理失败时提供可观测失败状态，不能和 no-reply 混在一起。
- 维护必要的历史上下文和用户记忆，让回复理解前后文。

必须成立的子功能：

- account context 可信，不靠 agent 猜用户。
- conversation/session 能稳定识别。
- 同步等待和异步补发语义清楚；超时时必须先给可见等待文字，最终文字回复必须异步送达。
- outbound route 可用。
- 用户可见输出的最低且当前必要合同是文字回复；不要求语音回复、图片回复、视频回复或输入输出媒体类型一致。
- 系统失败、空输出异常、模型有意 no-reply 必须可区分：系统失败不能静默丢；有意 no-reply 不发送任何用户可见消息；处理慢不能被误判为 no-reply。

Onboarding（首次对话）：

- 当用户第一次与该 agent 对话（系统据该用户与该 agent 是否已有对话关系判定是否首次）时，系统必须进入 onboarding 分支。
- onboarding 分支的具体行为由配置的 onboarding 提示词/设定驱动；系统按该提示词向用户发送首次引导消息。
- 顶层需求不规定 onboarding 的具体话术、语气、步骤数或消息条数；这些由 onboarding 提示词/设定决定。
- onboarding 只在首次对话注入，后续对话不重复触发。
- onboarding 只能介绍当前真实可用的能力；在没有成功工具结果时，不得声称已经替用户完成提醒等操作。

需求边界：

- 日常对话的核心合同是可信 account context、文字回复、turn execution、回复必要性判断、reply delivery、timeout/fallback semantics、intentional no-reply、failure observability。
- 多模态输入属于 inbound message 标准化和 Interaction LLM 可处理输入的一部分；它不改变当前“文字回复”的输出合同。
- 日常对话不负责建立 channel 或选择 provider；这些必须在消息进入对话旅程前成为可信上下文。
- 无论内部队列、锁、等待和分发方式如何变化，用户可见语义必须保持：消息被接收、会处理；需要回复时会用文字回复；超时有可见等待文字，最终文字回复可异步送达；模型有意 no-reply 时不发送任何用户可见消息。
- intentional no-reply 必须作为可观测结果保留，而不是和失败混在一起。

### 5.5 用户时区

已确认：

- 用户只有一个全局默认时区。
- 用户可以在设置页查看和修改全局默认时区。
- 用户可以通过对话整体切换时区，例如“以后按东京时间提醒我”。
- 当前不支持单条 reminder 独立时区。
- 用户在创建 reminder 时提到另一个时区，应被理解为整体切换时区，或在需要避免误解时先确认整体切换。
- 切换时区不应静默改写已有 reminder 的绝对触发时刻；已有 reminder 只按新的全局时区展示。
- 新创建 reminder、提醒日历页展示、无触发时间汇总、好友可用性和共享提醒都使用当前全局默认时区。

用户旅途：

1. 用户打开 agent 设置页查看当前时区。
2. 用户在设置页切换全局默认时区，或在对话中说“以后按东京时间提醒我”。
3. 系统确认时区已经整体切换。
4. 用户之后创建 reminder、查看日历或查询好友可用性时，系统按新的全局时区解释和展示。
5. 用户已有 reminder 的绝对触发时刻保持不变，只按新的全局时区展示时间。
6. 如果用户在创建 reminder 时说“明天 9 点纽约时间提醒我”，系统应把这理解为全局时区切换到纽约时间后创建，或先确认是否整体切换到纽约时间。

系统必须支持：

- 读取用户全局默认时区。
- 在设置页修改用户全局默认时区。
- 通过对话修改用户全局默认时区。
- 在提醒创建、编辑、确认、触发文案、提醒日历页、无触发时间汇总、日历导入结果、好友可用性和共享提醒中使用统一全局时区。
- 切换全局时区后，已存在 reminder 的绝对触发时刻不被静默重写。
- 在用户提到另一个时区但语义可能是单条 reminder 独立时区时，系统应确认整体切换语义，而不是创建单条独立时区 reminder。

需求边界：

- 用户时区是 customer-scoped 的全局设置，不是每条 reminder 的字段级用户配置。
- channel 和 Interaction LLM 不应各自使用不同默认时区解释同一个提醒时间。
- 当前需求不支持“这一条提醒用纽约时间、其他提醒用东京时间”的产品语义。

### 5.6 好友关系

已确认：

- 好友关系是当前产品合同。
- 好友关系服务人与人之间的监督协作，也是共享提醒的前置关系。
- 好友链接是授权入口；访问者登录或注册承接后直接建立 active friendship，不需要 owner 审批，不产生 pending friend request。
- 用户可以生成自己的公开好友链接。
- 用户可以通过二维码分享自己的好友链接。
- 未登录访问者打开好友链接后，可以先注册或登录。
- 登录用户通过好友链接承接后，可以与链接 owner 建立 active friendship。
- 用户也可以在对话中通过好友链接码建立 active friendship。
- 同一对用户不能重复创建多个 active friendship。
- 用户不能和自己建立好友关系。
- 用户可以查看自己的好友列表。
- 用户可以移除好友。
- 移除好友后，双方可以通过仍有效的好友链接或链接码重新建立 active friendship。
- 用户可以 reset 自己的好友链接，使旧链接不再作为新的好友入口。
- 用户可以 disable 自己的好友链接，使别人不能继续通过该链接加自己。
- reset 和 disable 都只影响未来新增好友，不影响已经建立的好友关系；reset 表示旧链接失效并生成或启用新链接，disable 表示关闭当前好友链接。
- pending friend request accept/reject 不作为当前需求；建立好友是直接 active 的产品语义。
- 好友关系不要求用户已经连接 personal channel；但好友关系后续带来的通知、共享提醒触达仍依赖可用 channel。

用户旅途：

1. 用户打开好友页。
2. 用户查看自己的好友链接和二维码。
3. 用户把好友链接或二维码分享给别人。
4. 访问者打开好友链接。
5. 如果访问者未登录，系统引导访问者注册或登录，并保留本次好友链接承接上下文。
6. 访问者登录后，系统建立访问者与链接 owner 的 active friendship。
7. 如果双方已经是 active friends，系统不重复创建关系，并向用户表达已经是好友。
8. 如果用户尝试打开自己的好友链接，系统不能创建自我好友关系。
9. 用户可以在对话中输入好友链接码，系统建立对应 active friendship。
10. 用户可以在好友页查看好友列表。
11. 用户可以移除某个好友。
12. 如果双方曾经是好友但已被移除，且用户再次通过有效好友链接或链接码进入，系统可以重新建立 active friendship。
13. 用户可以 reset 好友链接；reset 后，旧链接不能再用于新增好友，新链接可以继续分享。
14. 用户可以 disable 好友链接；disable 后，别人不能继续通过该链接加自己。
15. 用户可以重新启用或重新生成可分享的好友入口。

系统必须支持：

- 获取当前用户的好友链接。
- 展示好友链接二维码。
- 公开好友链接访问。
- 未登录访问者的登录/注册承接。
- 登录后继续完成好友链接承接。
- 通过好友链接建立 active friendship。
- 通过对话中的好友链接码建立 active friendship。
- 通过有效好友链接或链接码重新建立曾被移除的 active friendship。
- 查看好友列表。
- 移除好友。
- reset 好友链接。
- disable 好友链接。
- 防止用户和自己建立好友关系。
- 防止同一对用户重复创建 active friendship。
- 已有 active friendship 时返回可理解结果，而不是创建重复关系。
- 已 disable 的好友链接不能继续新增好友。
- reset 后的旧好友链接不能继续新增好友。
- reset 和 disable 都不删除或隐藏已建立的好友关系。
- 好友列表至少能让用户区分每个好友。
- 好友列表当前只要求展示好友的可识别名称或标识、active 关系状态和移除好友动作；不要求备注、分组、头像、最近互动时间或好友详情页。
- 好友名称或标识重复时，后续对话中的好友匹配必须能追问澄清。

好友关系与 channel 的关系：

- 好友关系本身依赖登录身份，不依赖用户已经连接 personal channel。
- 如果用户没有可用 channel，仍可以建立好友关系。
- 好友关系建立后的通知、共享提醒、后续主动触达依赖用户自己的可用 channel。
- channel 移除不删除好友关系。

移除好友语义：

- 移除好友只改变好友关系，不删除账号、不删除个人 reminder，也不自动取消已经存在的 active shared reminder。
- 移除好友后，该好友不再出现在当前用户的 active 好友列表中。
- 移除好友后，双方不能再基于该 active friendship 创建新的共享提醒。
- 双方以后可以通过仍有效的好友链接或链接码重新建立 active friendship。
- 移除好友不删除任一方账号。
- 移除好友不删除任一方个人 reminder。
- 已存在共享提醒在移除好友后的处理归属共享提醒旅程，不在好友关系旅程中提前定义。

当前不要求：

- 好友申请待同意。
- 好友申请拒绝。
- 好友申请 pending 状态。
- 好友分组。
- 好友备注。
- 好友头像。
- 最近互动时间。
- 好友详情页。
- 好友黑名单。
- 好友推荐。
- 好友动态或社交内容流。

需求边界：

- 好友关系的核心合同是 active friendship，而不是 pending request workflow。
- 好友链接是产品入口，不应和 personal channel 绑定入口混用。
- 好友关系必须 account/customer scoped，不能靠 assistant 自己猜测双方身份。
- 建立好友关系必须幂等；重复访问、重复输入链接码或重复提交不能创建多条 active friendship。
- 移除好友是关系状态变化，不应级联删除用户账号、个人提醒或不相关数据。

### 5.7 共享提醒

已确认：

- 共享提醒是当前产品合同。
- 共享提醒依赖 active friendship；每个 receiver 都必须与 creator 存在 active friendship。
- 共享提醒支持一个 creator 约一个或多个 active friends；例如用户说“约 Bob 和 Carol”，系统应创建一条 group shared reminder，而不是拆成多条两两提醒。
- group shared reminder 的 participants 包含 creator 和所有 receivers。
- 每个 participant 都有自己的 reminder projection；到点时每个 participant 都通过自己的 channel 收到自己的关联提醒。
- 共享提醒不是邀请审批流程；创建后直接 active，receiver 不需要 accept/reject，通知只是 informational。
- 用户可以通过对话给一个或多个好友创建共享提醒。
- 用户可以查看共享提醒。
- 用户可以取消共享提醒。
- 用户可以在约时间前查询一个或多个好友可用性。
- 好友可用性只暴露隐私安全的忙闲信息，不暴露好友 reminder 详情。
- 好友可用性以 Coke reminders 为来源，不使用 Google Calendar 作为该功能的数据源。
- 创建共享提醒时，每个好友指代必须解析到唯一 active friend；如果任何好友名称或目标不明确，系统必须追问。
- 如果任何 receiver 不存在、不可解析或不是 active friend，系统不能静默跳过该 receiver；必须追问或返回用户可理解错误。
- 创建共享提醒至少需要 participants、标题或活动内容、触发时间；时间解释使用用户全局默认时区。
- shared reminder duration 默认 15 分钟；用户可显式设置其他时长。
- receiver conflict 是创建前硬约束；系统按 reminder 的 duration（默认 15 分钟）对应的时间段检查每个 receiver 是否冲突；如果任一 receiver 冲突，系统不创建共享提醒，应说明谁冲突、谁可用，并让 creator 调整时间或参与者。
- receiver conflict 检查每个 receiver 的个人 reminder 和共享 reminder（两者都算），按各自 duration 对应的时间段叠加判断是否重叠；与好友可用性查询使用同一来源。
- 当前只在创建前检查 receivers conflict，不检查 creator 自己的时间冲突（有意为之）。
- 通过所有 receivers conflict 检查后，共享提醒立即 active。
- 共享提醒创建后，creator 和所有 receivers 都应在到点后各自收到自己的关联 projection。
- creator 和 receivers 各自的提醒触发、送达失败、未送达处理遵守个人提醒的 channel 和送达规则。
- 在用户视角，共享 reminder 仍然是自己的 reminder，只是带有好友关联；用户处理完成只处理自己这一侧的 projection，不自动替其他参与者完成。
- 共享提醒禁止完全重复创建：同一 creator、同一 participants 集合、同一标题或活动内容、同一触发时间的 active shared reminder 视为重复；participants 顺序不影响重复判断；duration 不进入重复定义。
- 如果已存在完全相同的 active shared reminder，系统拒绝创建并告知用户已经存在；相似但不完全相同的共享提醒不硬拒绝。
- 共享提醒通知是 informational，不是邀请审批。
- receivers 不需要 accept，creator 不需要等待 receivers accept。
- pending shared reminder accept/reject 不作为当前需求。
- 任一参与者都可以取消 active shared reminder。
- 任一参与者取消共享提醒后，系统取消整个 group，停止所有 participant projections，并通知其他参与者；非参与者不能查看或取消。
- 共享提醒列表只要求展示标题或活动内容、参与者、触发时间、用户全局时区、duration、当前状态，并支持取消 active shared reminder；不要求详情页、编辑、评论、聊天或投票选时间。
- 共享提醒不支持直接编辑时间或内容；想改时间或内容时，用户需要取消整条共享提醒后重新创建。
- 共享 reminder 出现在个人提醒日历页，并展示关联好友标识；共享提醒列表暂时不要求筛选功能。
- 取消共享提醒后，所有参与者都不再收到这条关联提醒。
- 取消共享提醒会通知其他参与者；通知是 informational。
- 移除好友不自动取消已存在 active shared reminder；用户需要通过共享提醒取消动作取消。
- 移除好友后，双方不能再基于该 removed friendship 创建新的共享提醒。

用户旅途：

1. 用户已经与每个目标好友建立 active friendship。
2. 用户在对话中表达想约一个或多个好友、邀请好友、给好友安排共同事项，或打开共享提醒入口。
3. 如果用户只是想知道一个或多个好友什么时候有空，系统查询好友可用性，并只返回隐私安全的忙闲信息。
4. 如果用户要创建共享提醒，系统解析目标好友集合。
5. 如果任何好友指代不明确，系统追问用户选择哪个好友。
6. 如果任何目标用户不是 active friend，系统不创建共享提醒，并提示需要先建立好友关系或调整参与者。
7. 系统确认共享提醒的标题或活动内容、触发时间和 duration（默认 15 分钟，可改）；时间按用户全局默认时区解释。
8. 如果缺少必要信息，系统追问。
9. 系统检查每个 receiver 在对应时间段是否冲突。
10. 如果任一 receiver conflict 存在，系统不创建共享提醒，向 creator 说明谁冲突、谁可用，并让用户换时间或调整参与者。
11. 如果检查通过，系统检查是否存在完全相同的 active shared reminder。
12. 如果完全相同的 active shared reminder 已存在，系统拒绝重复创建，并向 creator 说明已存在。
13. 如果检查通过且不重复，系统创建一个 active group shared reminder。
14. 系统确保 creator 和所有 receivers 都会在到点后各自收到自己的关联 projection。
15. 系统向 creator 确认共享提醒已经创建。
16. 系统向所有 receivers 发送 informational notification。
17. 到点后，所有 participants 各自通过自己的可用 personal channel 收到自己的关联提醒。
18. 任一参与者可以查看自己的共享提醒列表。
19. 任一参与者可以取消 active shared reminder。
20. 取消后，所有 participant projections 停止，其他参与者收到 informational notification。

系统必须支持：

- 查询好友可用性。
- 好友可用性查询必须指定或解析一个或多个 active friends。
- 好友可用性查询必须有日期范围，并使用用户全局默认时区。
- 好友可用性只返回隐私安全的忙闲信息，不返回好友 reminder 详情。
- 创建 group shared reminder。
- 查看共享提醒列表。
- 共享提醒列表展示标题或活动内容、参与者、触发时间、用户全局时区、duration、当前状态和取消入口。
- 在个人提醒日历页展示共享 reminder，并展示关联好友标识。
- 取消共享提醒。
- 用户想修改共享提醒时间或内容时，引导用户取消整条共享提醒后重新创建。
- 通过对话创建共享提醒。
- 通过对话查看共享提醒。
- 通过对话取消共享提醒。
- 解析每个 receiver 为唯一 active friend。
- 任一 receiver 不明确时追问。
- 任一 receiver 不是 active friend 时拒绝创建或要求调整参与者。
- 创建共享提醒必须有标题或活动内容、触发时间和至少一个 receiver。
- 支持 duration，默认 15 分钟，用户可显式设置其他时长。
- 创建前按 reminder 的 duration（默认 15 分钟）对应的时间段检查每个 receiver conflict。
- 任一 receiver conflict 存在时不创建共享提醒。
- receiver conflict 存在时说明谁冲突、谁可用。
- 防止完全相同的 active shared reminder 重复创建。
- 创建后立即 active。
- 为 creator 和所有 receivers 建立各自的 reminder projection。
- 确保每个 participant 到点后能收到自己这一侧的关联提醒。
- participants 各自收到的提醒必须保留 group shared reminder 关联，不能变成互不关联的普通提醒。
- 用户处理完成只处理自己这一侧的 projection，不自动替其他参与者完成。
- 通知 receivers 共享提醒已创建。
- 任一参与者取消 shared reminder。
- 取消后所有 participant projections 都停止。
- 取消后通知其他参与者。
- 取消时如果匹配多个候选，系统必须追问，不能取消错误的共享提醒。
- 取消已经取消的共享提醒应返回可理解结果，而不是重复执行破坏性动作。

共享提醒与个人提醒的关系：

- 在用户视角，共享 reminder 仍然是自己的 reminder，只是带有好友关联。
- 每个 participant 都应按各自可用 personal channel 收到自己这一侧的关联提醒。
- 用户收到关联提醒后的完成处理，默认只作用于自己这一侧的 projection。
- 用户完成自己这一侧的 projection，不自动替其他参与者完成。
- 取消共享提醒是整个 group 停止所有 projections 的动作，不等同于完成或修改自己这一侧的 projection。
- 修改共享提醒时间或内容不是当前支持的直接操作；用户需要取消整条共享提醒后重新创建。
- 共享提醒到点后的可见提醒仍进入 Interaction LLM，由 assistant 用符合角色的语气提醒用户。
- 某一参与者的送达失败只影响该参与者是否收到自己的关联提醒，不影响其他参与者是否收到提醒。

当前不要求：

- pending shared reminder。
- receiver accept。
- receiver reject。
- 批量 accept/reject。
- 共享提醒详情页。
- 对共享提醒进行直接编辑；当前用户需要取消整条共享提醒后重新创建。
- 共享提醒列表筛选功能。
- 共享提醒评论。
- 共享提醒聊天群。
- 共享提醒投票选时间。
- 从 Google Calendar 读取好友可用性。
- 向对方暴露 reminder 详情、日历详情或私人安排内容。

需求边界：

- 共享提醒的核心合同是 group participants 关联 + 每个 participant 各自到点触达 + informational notification。
- pending accept/reject workflow 不应重新进入当前需求。
- 好友可用性查询必须保护隐私，只输出可用于约时间的忙闲信息。
- receiver conflict 是创建前产品约束；冲突时不能先创建再等待对方处理，也不能静默跳过冲突参与者后部分创建。
- 创建 shared reminder 后，不能出现系统对用户声称创建成功，但某个 participant 不会收到自己这一侧的关联提醒。
- 取消 shared reminder 后，不能只停止一部分 participant projections，导致其他参与者继续收到这条关联提醒。
- shared reminder 必须 participant-scoped；非参与者不能查看或取消。

### 5.8 个人提醒

已确认：

- 个人提醒是当前核心旅程。
- 个人 reminder 覆盖对话创建、提醒日历页管理、到点触发、提醒后回复处理和未送达处理。
- 提醒日历页是个人 reminder 的主要页面，以日历为主视图展示未来一次性提醒、重复提醒系列、无触发时间 reminder、共享 reminder 和未送达提醒。
- 到点提醒进入 Interaction LLM，由 LLM 知道这是系统提醒，并用符合角色语气的文字提醒告知用户。
- 无触发时间 reminder 属于个人 reminder；系统每天晚上 8 点汇总询问用户是否要安排触发时间。
- 重复提醒属于个人提醒核心需求；完成表示完成本次，删除表示删除整个系列，当前不支持独立跳过操作。
- 主动 follow-up 是特殊类型 reminder，不显示在提醒日历页，不允许用户直接修改，并受 proactive 开关控制。
- duration 默认 15 分钟，用户可显式设置其他时长；时间按用户全局默认时区解释，不支持单条 reminder 独立时区。
- 用户在对话中提到另一个时区时，系统应按整体切换用户全局时区或先确认整体切换。
- 用户可见状态聚焦产品动作，不暴露内部状态机字段；删除 reminder 表示从当前产品状态中移除。

用户旅途：

1. 用户通过对话表达提醒意图，或打开提醒日历页。
2. 如果用户给出触发时间或重复规则，用户创建一个一次性或重复个人提醒。
3. 如果用户没有给出触发时间，系统创建一个无触发时间 reminder。
4. 如果用户明确给出 duration，系统按其设置；未给出时按默认 15 分钟。
5. 用户可以在提醒日历页查看自己的 reminder、无触发时间 reminder、共享 reminder、未送达提醒和单条详情。
6. 用户可以编辑普通个人 reminder 的内容、触发时间和 duration，也可以给无触发时间 reminder 补充触发时间。
7. 用户可以完成提醒。对于一次性提醒，完成表示这件事已处理；对于重复提醒，完成表示完成本次；对于无触发时间 reminder，完成表示该事项已处理。
8. 用户可以删除提醒。对于一次性提醒，删除该提醒；对于重复提醒，删除整个系列；对于无触发时间 reminder，删除该 reminder。
9. 用户查看提醒日历页默认视图时，只看到仍然可行动或未来仍会触发的 reminder。
10. 已完成的一次性 reminder 或无触发时间 reminder 离开提醒日历页默认视图。
11. 已完成的重复提醒本次离开待处理状态，但系列继续按规则展示下一次触发。
12. 已删除的 reminder 不再出现在用户可见列表、无触发时间汇总和后续触发中。
13. 提醒到点后，系统把“这是系统提醒”的上下文交给 Interaction LLM。
14. Interaction LLM 用符合角色语气的文字提醒告知用户。
15. 用户收到提醒后，可以回复完成、改时间、删除或继续普通对话。
16. 如果用户回复完成，本次提醒被完成；如果是重复提醒，只完成本次。
17. 如果同一次提醒告知包含多条 reminder，用户回复完成表示这次提醒中的事项都已完成。
18. 如果用户回复晚点提醒、改到明天、换个时间等，系统在时间明确时更新提醒时间；时间不明确时追问。
19. 如果用户回复不用提醒了或删掉，一次性提醒删除该提醒；重复提醒删除整个系列。
20. 如果用户回复普通聊天或无意义内容，系统不应自动改变 reminder 状态。
21. 每天晚上 8 点，系统把仍未安排触发时间的 reminder 汇总给用户，询问是否要为这些 reminder 安排触发时间。
22. 用户可以对汇总里的一个或多个 reminder 安排时间。
23. 用户可以完成或删除汇总里的一个或多个 reminder。
24. 用户明确表达批量安排时，系统为对应 reminder 批量设置触发时间。
25. 用户只给一个时间但汇总里有多条 reminder，且无法判断作用对象时，系统应追问。
26. 用户说“这些都完成了”时，系统批量完成汇总里的 reminder。
27. 用户为无触发时间 reminder 安排触发时间后，该 reminder 转为有触发时间 reminder，并按新时间出现在日历页。
28. 用户移除一次性 reminder 的触发时间后，该 reminder 转为无触发时间 reminder，并进入未安排时间区域和每天晚上 8 点汇总。
29. 用户试图移除重复提醒的触发时间，且移除后无法维持重复规则时，系统应追问用户是改成无触发时间 reminder，还是删除整个重复系列。
30. 如果用户不回应，或没有为这些 reminder 安排触发时间，这些 reminder 继续保留，并在下一天晚上 8 点继续出现在汇总询问中。
31. 如果用户对汇总回复普通聊天或无意义内容，系统不应自动改变这些 reminder 状态。
32. 如果是重复提醒，本次触发或用户完成本次后，系统推进下一次触发时间。

系统必须支持（能力索引，详细规则见下方各专题小节，不在此重复）：

- 提醒 CRUD：对话与提醒日历页创建、查看、编辑、完成、删除个人 reminder，包括创建无触发时间 reminder、批量操作、设置/修改/清除 duration。
- 提醒日历页展示、创建编辑、状态与详情字段：见「提醒日历页展示规则」「提醒日历页创建与编辑规则」「提醒状态与详情字段」。
- 对话创建追问与操作确认：见「对话创建 reminder 的追问边界」「提醒操作确认回复」。
- 到点触发与送达失败处理：见「提醒触发与送达失败处理」。
- 提醒后的用户回复处理：见「提醒后的用户回复语义」。
- 无触发时间 reminder 汇总与有/无触发时间转换：见「无触发时间汇总后的用户回复语义」「无触发时间和有触发时间 reminder 的转换」。
- 主动 follow-up reminder：见「主动 follow-up reminder」。
- 重复提醒：见「重复提醒规则限制」。
- 匹配歧义与创建期重复/相似处理：见「匹配歧义处理」「创建期重复/相似 reminder 处理」。
- 时间与时区解释：见「时间解释与过去时间处理」「时区解释规则」。
- 全局不变量：所有提醒 owner-scoped；不向用户暴露 reminder 内部 ID、底层 delivery attempt、内部重试次数、错误码、队列状态或内部状态机字段。

提醒日历页展示规则：

- 提醒日历页是个人 reminder 的主页面，不是独立于 reminder 的任务列表。
- 日历页必须按用户全局默认时区展示 reminder。
- 有触发时间的一次性 reminder 显示在对应日期和时间上。
- 共享 reminder 显示在对应日期和时间上，并展示关联好友标识。
- 重复提醒在当前可见时间范围内显示具体 occurrence；用户看到的是日历上的 occurrence，但底层仍然属于同一个重复提醒系列。
- 同一天或同一时间存在多个 reminder 时，日历页可以合并展示入口，避免页面过载。
- 合并展示入口进入详情后，必须能看到每一条 reminder，并能分别执行编辑、完成、删除。
- 无触发时间 reminder 不强行落到某一天；它应在日历页中作为未安排时间的 reminder 展示。
- 未送达提醒必须在日历页中有明确状态，让用户知道系统已经触发但没有成功送达。
- 当前顶层需求不限定日历页必须使用月视图、周视图或日视图；核心要求是用户能在日历语境下查看和管理 reminder。

提醒日历页创建与编辑规则：

- 用户可以从提醒日历页创建 reminder。
- 如果用户从日历上的某个日期或时间位置创建 reminder，系统默认使用该日期或时间作为触发时间。
- 用户可以在提醒日历页的未安排时间区域创建无触发时间 reminder。
- 用户可以从提醒日历页给无触发时间 reminder 安排触发时间。
- 用户可以从提醒日历页编辑普通个人 reminder 内容、触发时间和重复规则。
- 用户不能从提醒日历页直接编辑共享 reminder 的时间或内容；想修改时需要取消整条共享提醒后重新创建。
- 用户从日历页点进某次重复提醒 occurrence 后，完成表示完成本次。
- 用户从日历页点进某次重复提醒 occurrence 后，编辑默认编辑整个重复提醒系列。
- 用户从日历页点进某次重复提醒 occurrence 后，删除表示删除整个重复提醒系列。
- 当前顶层需求不限定日历页创建或编辑必须使用点击、拖拽、弹窗、侧栏或其他具体页面交互形态。

提醒状态与详情字段：

- 当前用户可见状态至少包括未来一次性提醒、无触发时间 reminder、重复提醒系列、共享 reminder、未送达提醒。
- 完成状态不进入提醒日历页默认视图。
- 删除状态不作为用户可见状态保留。
- 单条详情至少展示内容、触发时间或未安排时间、用户全局默认时区下的时间表达、重复规则和当前状态。
- 重复提醒详情必须展示系列规则和下一次触发时间。
- 日历上的重复提醒 occurrence 只是系列在某个时间点的可见实例，不是独立 reminder。
- 未送达提醒详情需要展示已触发但未成功送达的状态。
- 当前顶层需求不要求在用户界面暴露内部重试次数、错误码、队列状态、底层 delivery attempt、内部状态机字段或 reminder 内部 ID。

对话创建 reminder 的追问边界：

- 用户意图明确但缺少必要信息时，系统应追问，而不是猜测关键内容。
- 创建 timed reminder 至少需要事项内容和触发时间。
- 创建无触发时间 reminder 只需要明确事项内容，不需要触发时间。
- 创建 recurring reminder 至少需要事项内容、重复规则，以及规则能推导出的触发时间或触发窗口。
- 用户只说“提醒我一下”这类缺少事项内容的消息时，系统不能创建 reminder，应追问用户要提醒什么。
- 用户给出事项但没有给时间时，系统可以创建无触发时间 reminder，并确认该 reminder 没有触发时间，会在每天晚上 8 点汇总询问安排时间。
- 用户表达含糊时间，例如“下周提醒我”，如果无法确定具体日期或时间，应追问；如果用户实际是在表达一个暂未安排时间的事项，可以创建无触发时间 reminder。
- 追问和确认回复都应由 Interaction LLM 生成，并准确反映系统是否已经创建 reminder。

提醒操作确认回复：

- 用户通过对话创建、编辑、完成、删除 reminder 后，系统应给出文字确认。
- 确认回复应由 Interaction LLM 生成，而不是固定模板。
- 确认内容必须包含用户需要核对的关键信息，例如提醒内容、触发时间、重复规则、是否无触发时间。
- 对无触发时间 reminder，确认时必须明确它还没有触发时间，并会在每天晚上 8 点汇总询问安排时间。
- 如果创建失败、编辑失败、完成失败、删除失败，或需要追问用户，系统不能给出“已完成操作”的确认。

提醒后的用户回复语义：

- 用户收到提醒后，后续回复可以基于最近一次提醒上下文操作 reminder。
- 用户回复“完成了”“做完了”等完成表达时，应完成最近触发的 reminder。
- 如果最近触发的是重复提醒，完成表达只完成本次。
- 如果同一次提醒告知包含多条 reminder，用户回复“完成了”表示这次提醒中的事项都已完成。
- 用户回复“晚点提醒”“改到明天”“换个时间”等改时间表达时，如果新时间明确，应更新提醒触发时间。
- 如果用户想改时间但新时间不明确，系统应追问。
- 用户回复“不用提醒了”“删掉”等删除表达时，一次性提醒删除该提醒，重复提醒删除整个系列。
- 用户回复普通聊天或无意义内容时，不应自动改变 reminder 状态。

无触发时间汇总后的用户回复语义：

- 用户收到每天晚上 8 点的无触发时间 reminder 汇总后，可以对汇总里的一个或多个 reminder 安排时间。
- 用户明确表达批量安排时，系统应为对应 reminder 批量设置触发时间。
- 用户只给一个时间但汇总里有多条 reminder，且无法判断作用对象时，系统应追问。
- 用户可以完成或删除汇总里的某个 reminder。
- 用户说“这些都完成了”时，系统应批量完成汇总里的 reminder。
- 用户不回复时，汇总里的 reminder 继续保留，下一天晚上 8 点继续汇总。
- 用户回复普通聊天或无意义内容时，不应自动改变这些 reminder 状态。

无触发时间和有触发时间 reminder 的转换：

- 无触发时间 reminder 一旦安排触发时间，就转为有触发时间 reminder。
- 有触发时间 reminder 如果用户移除触发时间，就转为无触发时间 reminder。
- 转换不改变 reminder 内容、owner 或创建来源。
- 转换后，reminder 应按新状态出现在提醒日历页的日历位置或未安排时间区域。
- 重复提醒必须有可推导的触发规则。
- 如果用户移除重复提醒的触发时间后无法维持重复规则，系统应追问用户是改成无触发时间 reminder，还是删除整个重复系列。
- 转换后必须给用户确认，说明 reminder 当前是否还有触发时间、是否还会到点提醒。

主动 follow-up reminder：

- 主动 follow-up 是一种特殊类型 reminder。
- 主动 follow-up reminder 用于 assistant 基于用户目标、习惯、任务或上下文主动关心用户。
- 主动 follow-up reminder 不要求用户显式创建一个普通 reminder。
- proactive 开关对主动 follow-up 的影响（关闭/重开、是否取消未触发项）见 §5.11 Agent settings 的「proactive 开关」，此处不重复。
- 主动 follow-up reminder 不显示在提醒日历页。
- 用户不能在提醒日历页直接查看、编辑、删除主动 follow-up reminder。
- 用户不能直接修改主动 follow-up reminder。
- 主动 follow-up reminder 的触发时机和频率由配置的 follow-up 规划提示词/设定驱动；系统按该提示词决定是否、何时创建、替换或取消主动 follow-up。
- 主动 follow-up reminder 必须尊重用户打扰意愿，避免骚扰：连续多次主动消息得不到用户回复时，系统必须降低频率，直至停止该主动 follow-up；用户重新回复后频率可恢复。具体阈值由 follow-up 规划提示词/设定决定。
- 当前不提供免打扰或通知偏好设置；主动 follow-up 的低打扰要求由系统频率和上下文规则保证。
- 主动 follow-up reminder 只能通过当前已连接 personal channel 发送文字消息。
- channel 不可用时，主动 follow-up reminder 不视为已触达。
- 主动 follow-up reminder 送达失败不补发：channel 不可用或发送失败时，该 follow-up 过期即丢，不进入未送达补发，也不在提醒日历页展示。
- 顶层需求不规定具体规划算法、具体时间间隔或具体阈值；这些由 follow-up 规划提示词/设定决定。

批量 reminder 操作：

- 用户一条消息中可以包含多个 reminder 操作。
- 系统应能批量创建、编辑、完成、删除 reminder。
- 批量操作的确认回复应汇总展示成功项、失败项和需要追问项。
- 批量操作不要求事务式全成功；部分成功时必须清楚告诉用户哪些成功、哪些没有成功。
- 如果某一项需要追问，不应阻塞其他可以明确执行的项。
- 每个子操作仍必须遵守 owner、时间解释、全局时区、重复规则、送达、确认回复等个人提醒合同。

匹配歧义处理：

- 系统可以按用户描述匹配 reminder。
- 如果只匹配到一个明确 reminder，系统可以执行编辑、完成或删除，并给出确认。
- 如果匹配到多个候选 reminder，系统必须向用户澄清，让用户选择。
- 澄清时应展示足够区分的信息，例如内容、触发时间、重复规则、是否无触发时间。
- 在用户确认前，系统不能删除、完成、编辑任何候选 reminder。
- 批量操作中某一项匹配歧义，只阻塞这一项，不阻塞其他明确可执行的项。

创建期重复/相似 reminder 处理：

- 系统禁止创建完全相同的可行动个人 reminder。
- 完全相同的个人 reminder 定义：同一 owner、同一事项/内容、同一触发时间；无触发时间 reminder 则是同一 owner、同一事项/内容且双方都无触发时间。
- duration、创建入口和自然语言表达方式不进入个人 reminder 重复定义。
- 如果当前已存在完全相同的可行动 personal reminder，系统应拒绝创建并告知用户该提醒已经存在。
- 相似但不完全相同的 reminder 不应硬拒绝。
- 系统允许不同内容的多个 reminder 拥有同一触发时间。
- 同一 owner 同一触发时间的多个 reminder 在提醒时合并成一次提醒告知，避免多条消息骚扰；每条 reminder 及其事件本身仍保持独立。
- 当前需求不要求为了相似 reminder 引入复杂相似度判断。

提醒触发与送达失败处理：

- 提醒到点后必须形成一次 reminder trigger event。
- 如果用户当前有已连接的 personal channel，reminder trigger event 进入 Interaction LLM，并通过该 channel 发送文字提醒。
- 当前个人用户只能在 personal WeChat 或 shared WhatsApp channel 中拥有一个可达 channel。
- 如果用户没有可用 channel，系统不能把提醒视为已成功送达。
- 如果 channel 发送失败，系统不能把提醒视为已成功送达。
- 未送达的提醒触发必须保留可观测状态。
- channel 不可用期间到点的 reminder 进入未送达状态。
- 用户重新连接或重新链接 personal channel 后，未来提醒走新的已连接 channel。
- 用户重新连接或重新链接 personal channel 后，系统可以补发未送达提醒，或在提醒日历页显示未送达。
- 未送达提醒补发只适用于已经触发但未送达的 reminder。
- 补发内容应让用户知道这是之前未送达的提醒，而不是新的 reminder。
- 如果多条未送达提醒待补发，可以合并成一条文字提醒。
- 已完成或已删除的 reminder 不再补发。
- 如果未送达提醒已经在提醒日历页被用户处理，重新连接后不再重复补发。
- 当前产品不支持为了失败 channel 立即改用另一个未链接或未确认的渠道。
- 当前顶层需求不限定具体重试次数、过期时间、自动补发策略或仅在提醒日历页展示的策略。

时间解释与过去时间处理：

- 系统必须能判断用户给出的触发时间是否已经过去。
- 相对时间表达应正常创建提醒，例如“10 分钟后”“明天早上 9 点”。
- 如果用户给出明确但已经过去的时间，系统不应静默创建一个过去提醒。
- 对过去时间，系统应通过 Interaction LLM 追问或确认新的未来时间。
- 对日期不完整但可合理推断的时间，如果当天目标时间还未过去，可以按当天处理。
- 对日期不完整但当天目标时间已经过去的时间，系统应追问或确认，不应自动改成某个未来时间。
- 系统不应自行把过去时间改写为未来时间，除非 Interaction LLM 已经和用户确认。

时区解释规则：

- 提醒时间默认按用户全局默认时区解释。
- 用户可以在设置页修改全局默认时区，也可以通过对话整体切换。
- 如果用户在创建或编辑 reminder 时明确提到另一个时区，系统应把它理解为整体切换用户全局默认时区，或在语义可能误解时先确认整体切换。
- 当前不支持给单条 reminder 设置独立时区。
- 如果用户没有设置过时区，系统可以按账号、channel 或地区推断一个初始全局默认时区；之后所有 reminder 仍使用同一个全局默认时区。
- 切换全局默认时区不应静默改写既有 reminder 的绝对触发时刻；既有 reminder 只按新的全局默认时区展示。
- 系统保存和比较触发时间时可以使用统一时间基准，但用户可见的创建、编辑、确认、提醒文案必须按用户全局默认时区表达。
- 系统内部、channel 和 Interaction LLM 不应各自使用不同默认时区解释同一个提醒时间。

重复提醒规则限制：

- 必须支持每小时、每天、每周、每月、每年。
- 必须支持自定义间隔重复，例如每 2 小时、每 3 天。
- 重复提醒的最小间隔是每小时；不支持小于 1 小时的重复提醒。
- 小于一天的重复间隔必须受时间窗口限制，不能默认全天 24 小时无限触发。
- 用户可以显式指定小于一天重复间隔的触发时间窗口；未指定时，系统必须使用默认限定时间窗口。
- 默认限定时间窗口为每天 8 点到 23 点。
- 时间窗口内重复是一种重复提醒能力，例如“从 X 点到 Y 点，每隔 Z 分钟/小时提醒”。
- 时间窗口内重复必须有开始时间和结束时间。
- 时间窗口内重复的间隔不得小于 1 小时。
- 时间窗口内重复只在指定时间窗口和可选星期内触发。
- 每次触发后，系统必须推进下一次有效触发时间。
- 如果下一次触发时间不在有效时间段内，系统必须推进到下一个有效时间段。
- 编辑重复提醒默认编辑整个系列，影响后续所有触发。
- 当前不支持只编辑某一次重复提醒 occurrence。
- 完成重复提醒只完成本次；删除重复提醒才删除整个系列。
- 当前不支持独立的“跳过”操作；跳过这次等同于完成本次，并推进到下一次有效触发。
- 彻底停止重复提醒就是删除整个系列。
- 同一 owner 下同一触发时间的多个 reminder 在提醒时合并成一次提醒告知；合并只影响用户可见提醒方式，不改变每条 reminder 及其事件本身的独立性、内容、归属和后续状态推进。
- 重复提醒默认持续生效，直到用户删除整个系列，或编辑规则使其停止。
- 系统不应为所有重复提醒设置默认最大触发次数。
- 如果用户明确提出结束条件，例如提醒固定次数、提醒到某一天、只在接下来若干天提醒，系统应把结束条件作为该重复规则的一部分。

需求边界：

- 个人提醒的核心合同不是“直接发送一条固定通知”，而是“提醒事件触发后进入 Interaction LLM，由角色化 assistant 以文字方式提醒用户”。
- 系统可以负责时间、状态和触发；用户可见表达应由 Interaction LLM 完成。
- reminder 操作确认回复也是用户可见合同，应由 Interaction LLM 生成，并准确反映操作是否真实成功。
- 批量 reminder 操作不是一个绕过校验的特殊入口；每个子操作都必须独立满足个人提醒合同，并在汇总确认中表达真实结果。
- 编辑、完成、删除 reminder 时，匹配歧义必须先向用户澄清；未确认前不得对候选 reminder 执行破坏性或状态变更操作。
- 创建 reminder 时禁止完全相同的可行动 personal reminder；相似但不完全相同的 reminder 不做复杂相似度去重；同一触发时间的多条 reminder 通过提醒时合并来控制用户可见打扰。
- 提醒触发和提醒送达是两个不同状态；触发成功不等于用户已收到提醒。
- 无可用 channel 或发送失败不能被标记为成功送达，必须留下可观测未送达状态。
- 过去时间和日期不完整时间的处理属于用户意图确认问题；系统不应在未确认时自动改写时间。
- 系统应依赖统一的用户全局时区合同；channel 和 Interaction LLM 不应各自推断不同默认时区。
- 无触发时间 reminder 属于个人提醒旅程，但不是到点提醒；它的用户可见触达是每天晚上 8 点的安排时间询问。
- 无触发时间 reminder 的安排时间询问应按 owner 每天汇总一次，避免逐条消息造成骚扰。
- 重复提醒是提醒的一种，也是个人提醒核心合同的一部分；系统必须能根据规则推进下一次触发。
- 重复提醒的完成本次 / 删除整个系列 / 跳过等同完成本次 / 编辑整个系列 / 同一触发时间提醒时合并 / 完全相同 reminder 禁止创建等语义，见「重复提醒规则限制」「创建期重复/相似 reminder 处理」，此处不重复。
- 提醒日历页默认视图应面向可行动状态；完成记录或历史列表不属于当前已确认核心需求。
- 删除 reminder 是当前产品状态删除；当前需求不要求为了旧数据兼容或未确认审计需求保留复杂删除历史。
- 提醒必须 owner-scoped，不能依赖 LLM 自己猜测提醒属于谁。
- duration 是 reminder 的时长字段，默认 15 分钟，用户可显式设置其他时长；对个人提醒它不改变是否触发、何时触发、完成或删除，主要用于展示，以及共享提醒的 receiver conflict 时间窗口计算。

### 5.9 Product notification

已确认：

- Product notification 是独立需求项，但本文只从产品需求角度定义，不限定实现架构。
- 当前只发送 informational notification 和 system notification。
- Product notification 不是审批流程，不承载 accept/reject，也不直接执行行动。
- Product notification 必须覆盖好友关系创建、共享提醒创建、共享提醒取消，以及这些事件关联的错误、失败、部分失败、未送达、冲突和取消失败。
- 普通 reminder、shared reminder 和 system notification 不受额外免打扰或通知偏好设置控制；当前没有这类用户配置。
- notification 事实必须清楚表达谁、做了什么、对象是什么、何时发生、使用哪个时区、duration 是多少。
- 当事件包含错误、失败或部分失败时，notification 必须包含用户可理解的错误信息。
- notification 不应暴露 raw provider error、内部错误码、队列状态、delivery attempt 或内部状态机字段。
- 最终用户可见文字由 Interaction LLM 基于结构化事实和错误事实生成。

用户旅途：

1. 用户 A 通过好友链接或链接码与用户 B 建立 active friendship。
2. 系统向相关用户发送 informational notification，说明好友关系已经建立。
3. 用户 A 创建包含用户 B、用户 C 的 shared reminder。
4. 系统向 creator 发送创建确认，并向 receivers 发送 informational notification。
5. 如果创建失败、部分失败、receiver conflict、receiver channel 不可用或 receiver 不可解析，系统向 creator 发送包含错误信息的 system notification；如果当前对话正在等待结果，也可以作为最终可见错误回复呈现。
6. 任一 participant 取消 shared reminder。
7. 系统向其他 participants 发送 informational notification，说明谁取消了哪个 shared reminder，以及后续不会再触发。
8. 如果取消失败或部分 participant 未收到通知，系统向发起用户提供用户可理解错误信息。

系统必须支持：

- 发送好友关系创建 notification。
- 发送 shared reminder 创建 notification。
- 发送 shared reminder 取消 notification。
- 发送 system notification。
- 在 notification 中包含 actor、action、object、participants、time、timezone、duration 和 status。
- 在失败、部分失败、未送达、冲突或取消失败时包含用户可理解错误信息。
- 将 provider/channel 错误映射为产品语言，例如“对方 channel 不可用”“这个时间和对方已有安排冲突”“取消没有成功”。
- 由 Interaction LLM 根据结构化 notification facts 和 error facts 生成最终可见文字。
- 避免把 notification 变成审批、确认、accept/reject 或 action execution 入口。

需求边界：

- Product notification 的核心合同是事实告知和错误告知，不是工作流控制。
- Product notification 不引入新的用户通知偏好或免打扰设置。
- Product notification 不允许用内部错误或 provider 细节替代用户可理解错误信息。
- 共享提醒创建 notification 不表示 receiver 接受邀请；shared reminder 创建后已经 active。
- 取消 notification 不等于完成 reminder；取消 shared reminder 是停止整个 group 的关联 projections。

### 5.10 日历导入

已确认：

- 日历导入是当前产品保留能力。
- 当前只确认一次性导入，不引入持续 sync。
- 日历导入只定义用户需求和字段映射，不限定具体实现方案。
- 用户可以授权 Google Calendar。
- 系统可以从授权日历读取 calendar events。
- 未来 calendar events 会导入为 Coke reminders。
- 历史 calendar events 不生成 Coke reminders。
- 导入生成的 reminder 归属当前个人用户。
- calendar event 标题和描述进入 reminder 内容。
- calendar event 开始时间进入 reminder 触发时间。
- calendar event duration 进入 reminder duration；event 无 duration 时按默认 15 分钟。
- 全天 calendar event 导入为该事件日期 0 点触发的 Coke reminder。
- recurring calendar event 优先导入为 Coke recurring reminder。
- 如果 recurring calendar event 无法可靠表达为 Coke 当前支持的重复规则，系统应导入为未来可见 occurrence 对应的一次性 reminders。
- 如果 recurring calendar event 被降级为一次性 reminders，导入结果应让用户知道没有保留重复规则。
- 同一个 calendar event 重复导入时，系统直接跳过，不生成重复 reminder，不需要用户确认。
- 导入完成后，系统必须向用户反馈导入结果。
- 导入结果至少包含成功导入数量、跳过数量、降级项和失败项。
- 导入生成的 reminder 遵守个人提醒的 owner、全局时区、触发、完成、删除、未送达和日历展示规则。
- 用户可以停止或撤销 Google Calendar 授权，也可以让授权过期。
- 停止、撤销或过期只影响未来导入；已经导入的 Coke-owned reminders 继续按个人提醒规则管理，不自动删除。

用户旅途：

1. 用户进入日历导入入口。
2. 系统确认当前 account/conversation 已准备好承接导入结果。
3. 用户授权 Google Calendar。
4. 系统读取用户授权范围内的 calendar events。
5. 系统把未来 calendar events 一次性导入为 Coke reminders。
6. 如果 calendar event 是全天事件，系统导入为该事件日期 0 点触发的 Coke reminder。
7. 如果 calendar event 是可表达的重复事件，系统导入为 Coke recurring reminder。
8. 如果 calendar event 是无法可靠表达的重复事件，系统导入为未来可见 occurrence 对应的一次性 reminders，并在导入结果中说明。
9. 如果 calendar event 已经导入过，系统直接跳过，不创建重复 reminder，也不要求用户确认。
10. 系统不把历史 calendar events 生成 Coke reminders。
11. 系统向用户展示导入结果摘要。
12. 用户可以在提醒日历页查看和管理导入生成的 reminders。
13. 用户可以停止或撤销 Google Calendar 授权。
14. 授权停止、撤销或过期后，用户不能继续从该授权读取新 events；已导入 reminders 仍留在 Coke 中，由个人提醒规则管理。

系统必须支持：

- Google Calendar 授权入口。
- 一次性读取 calendar events。
- 只把未来 calendar events 转为 Coke reminders。
- 不把历史 calendar events 生成 Coke reminders。
- 把 calendar event 标题和描述映射为 reminder 内容。
- 把 calendar event 开始时间映射为 reminder 触发时间。
- 把 calendar event duration 映射为 reminder duration；event 无 duration 时按默认 15 分钟。
- 把全天 calendar event 映射为该事件日期 0 点触发的 reminder。
- 把可可靠表达的 recurring calendar event 映射为 Coke recurring reminder。
- 把无法可靠表达为当前重复规则的 recurring calendar event 映射为未来可见 occurrence 对应的一次性 reminders。
- 在 recurring calendar event 未保留重复规则时，向用户说明导入结果。
- 识别已经导入过的 calendar event，并在重复导入时直接跳过。
- 重复导入跳过不需要用户确认。
- 导入完成后向用户反馈导入结果摘要。
- 导入结果摘要包含成功导入数量。
- 导入结果摘要包含跳过数量。
- 导入结果摘要列出 recurring calendar event 被降级为一次性 reminders 的项目。
- 导入结果摘要列出失败项。
- 为导入生成的 reminders 设置当前个人用户 owner。
- 在提醒日历页展示导入生成的 reminders。
- 用户可以按个人提醒规则编辑、完成或删除导入生成的 reminders。
- 用户可以停止或撤销 Google Calendar 授权。
- Google Calendar 授权过期或被撤销时，系统停止未来读取。
- 停止、撤销或过期不删除已经导入的 Coke-owned reminders。

当前不要求：

- 持续 sync。
- 双向同步。
- 把用户在 Coke 中对 reminder 的修改写回 Google Calendar。
- 导入历史 calendar events 为 reminders。
- 重复导入时覆盖或重新创建已经导入过的 reminder。
- 撤销 Google Calendar 授权时自动删除已导入 reminders。

需求边界：

- 日历导入不应把 Google Calendar 变成 Coke reminder 的运行时真相来源；导入后 Coke reminder 按个人提醒合同运行。
- 当前不要求持续 sync、复杂同步状态、冲突解决或双向写回合同。
- Google Calendar 授权生命周期只控制未来读取能力，不改变已导入 Coke-owned reminders 的 owner、触发、完成、删除或展示规则。

### 5.11 Agent settings

已确认：

- Agent settings 用来配置 assistant 的用户可见表现和长期偏好。
- Agent settings 必须 customer-scoped。
- 用户可以查看、修改和重置自己的 Agent settings。
- 用户可以设置 assistant 名称。
- 用户可以设置 assistant 对自己的称呼。
- 用户可以设置 persona。
- 用户可以设置背景信息。
- 用户可以设置说话风格。
- 用户可以设置额外规则。
- agent 设置页展示当前 personal channel 的连接状态（已连接 / 未连接 / 连接失败）；该状态由 channel 可达性旅程决定，不是用户自由设置的字段。
- 用户可以关闭和重新打开 proactive。
- 用户可以关闭和重新打开 memory。
- 重置 Agent settings 会恢复默认设置。

proactive 开关：

- 关闭 proactive 后，系统不再创建新的主动 follow-up reminder。
- 用户关闭 proactive 时，应一并取消未触发的主动 follow-up reminder。
- 关闭 proactive 不删除普通个人 reminder，不影响到点提醒。
- 关闭 proactive 不影响无触发时间 reminder 汇总。
- 关闭 proactive 不影响日常对话回复。
- 关闭 proactive 不影响 Product notification 或 system notification。
- 重新打开 proactive 后，只影响未来是否可以创建新的主动 follow-up reminder。
- 重新打开 proactive 不恢复之前已取消的 follow-up。
- proactive 开关只控制主动 follow-up，不控制用户显式创建的 reminder、无触发时间汇总、日常对话回复、Product notification 或 system notification。
- 当前不提供免打扰或通知偏好设置。

memory 开关：

- memory 开关控制系统是否使用和更新长期记忆。
- 关闭 memory 后，系统不再使用长期记忆。
- 关闭 memory 后，系统不再新增长期记忆。
- 关闭 memory 后，系统不再更新长期记忆。
- 关闭 memory 不删除既有长期记忆。
- 关闭 memory 不影响完成当前对话所需的近期上下文。
- 重新打开 memory 后，系统可以继续为未来对话、提醒和主动 follow-up 使用仍存在的长期记忆，并继续积累新的长期记忆。
- 当前不支持用户自助清除长期记忆。

需求边界：

- Agent settings 是用户可理解的偏好配置，不应扩展成复杂 persona 或 policy 平台。
- memory 开关应约束长期记忆的使用、创建和更新；不应被解释成清空所有会话历史，也不提供清除长期记忆能力。
- proactive 开关应约束主动 follow-up reminder；不应影响普通个人 reminder、Product notification 或 system notification。

### 5.12 账号/数据生命周期

已确认：

- 当前产品不支持用户自助删除账号。
- 当前产品不支持用户自助完整账号导出或完整擦除。
- 当前产品不支持用户自助清除长期记忆。
- 当前支持的生命周期动作是局部动作：移除 personal channel、删除或完成个人 reminders、取消 shared reminders、移除好友、关闭 memory 使用、停止或撤销 Google Calendar 授权。
- 账号仍然是 channel、reminder、friendship、shared reminder 和 settings 的身份主体。
- 局部生命周期动作不能被解释成删除账号本身。

用户旅途：

1. 用户在 channel 管理页移除 personal channel。
2. 系统停止通过该 channel 触达用户，但不删除账号、reminders、friendships 或 settings。
3. 用户在提醒日历页删除或完成个人 reminders。
4. 系统只改变对应 reminders 的产品状态，不删除用户账号。
5. 用户取消 shared reminder。
6. 系统取消整个 group shared reminder，停止所有 participant projections，并通知其他 participants。
7. 用户在好友页移除好友。
8. 系统移除 active friendship；该动作不删除账号、不删除个人 reminders，也不自动取消已经存在的 active shared reminders。
9. 用户关闭 memory。
10. 系统停止使用、新增和更新长期记忆，但不删除既有长期记忆。
11. 用户停止或撤销 Google Calendar 授权。
12. 系统停止未来读取 Google Calendar；已导入 Coke-owned reminders 继续按个人提醒规则管理。

系统必须支持：

- 移除 personal channel。
- 删除个人 reminder。
- 完成个人 reminder。
- 取消 shared reminder。
- 移除好友。
- 关闭和重新打开 memory 使用。
- 停止或撤销 Google Calendar 授权。
- 在这些局部生命周期动作完成后给出准确用户可见结果。
- 在局部生命周期动作失败时给出用户可理解错误信息。

当前不要求：

- 用户自助删除账号。
- 用户自助完整账号导出。
- 用户自助完整数据擦除。
- 用户自助清除长期记忆。
- 用户从 Coke 删除已经导入 reminders 时同步删除 Google Calendar 原始 events。

需求边界：

- 账号/数据生命周期的当前合同是局部管理动作，不是完整隐私数据管理平台。
- 移除 channel 只影响未来触达路径，不改变 reminder owner。
- 删除或完成 reminder 只影响对应 reminder，不影响账号或好友关系。
- 取消 shared reminder 影响整个 group shared reminder，不等同于移除好友。
- 移除好友不自动取消既有 shared reminders。
- 关闭 memory 只影响长期记忆使用、创建和更新，不删除既有长期记忆。
- 停止或撤销 Google Calendar 授权只影响未来导入，不删除已导入 Coke-owned reminders。
