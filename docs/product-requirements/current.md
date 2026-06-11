# Coke Current Product Requirements

Status: canonical current product requirements baseline
Created: 2026-05-28  
Updated: 2026-05-31 (moved from design specs to product-requirements baseline; normalized segmented message delivery, reminder filtering, and conversational style requirements)
Scope: Current product: personal accountability companionship, friend system, shared reminders, Product notifications, account/data lifecycle

## 0. Usage Boundaries

This document is the top-level requirements and user journey matrix for the current Coke product. It defines the user journeys, product behaviors, boundaries, and user-visible acceptance criteria that the system must support.

This document records product requirements only. It does not record implementation status, legacy comparison evidence, code paths, architecture refactoring design, gap priorities, bug status, or why a requirement was selected. Legacy comparison and implementation conformance records belong in `docs/issues/`; execution sequencing belongs in `docs/superpowers/plans/`.

Key premises:

- Coke currently does not need to retain historical production data.
- There are no real production-environment constraints.
- Destructive refactoring is acceptable.
- Do not design complex migrations for compatibility with old data, old protocols, or old runtime shapes.
- System behavior must serve clear user requirements and user journeys, rather than abstraction for abstraction's sake.

## 1. Product Scope

This requirements matrix constrains the current Coke product. Confirmed capabilities are no longer weakened or deferred by phase labels.

Current product goals:

- Help individual users maintain goals, habits, tasks, and reminders.
- Build a continuous accountability-companionship relationship through daily conversations, personal reminders, proactive follow-up reminders, and personal-channel reachability.
- Support interpersonal accountability collaboration through the friend system and shared reminders.
- Use informational Product notifications to inform users of the results and error information for friendships, shared reminders, and system events.
- Interpret and display reminders, calendars, and friend availability according to the user's global timezone.
- Let users use Coke naturally inside their own communication channels, instead of forcing them into a complex admin backend.
- Retain necessary account access status, public explanation, FAQ, demo, privacy, and terms pages as support surfaces for user entry, understanding, and compliance. These support surfaces are not the core accountability user value.

Current product users:

- Individual Coke users.

Non-product user participants within the current system boundary:

- Shared-channel personal reachability. The WhatsApp entry point is currently carried by a shared channel, but ordinary users experience it as their own personal conversation entry point. This is not an independent product journey.

Confirmed as not part of current product requirements:

- Complex migrations for old data, old protocols, or old runtime shapes.

First-use definition:

- For web-first users, onboarding completion requires registration/login to be complete, at least one usable personal channel to be connected, and the user to send one message through that channel that the system successfully receives.
- For shared WhatsApp messaging-first users, onboarding completion does not require web registration or login. It requires the sender identity to be bound to a Coke user, the messaging channel to be usable for replies and reminders, and the first inbound message to be successfully received.
- Onboarding refers to the product journey from never activated to first activation complete. The assistant may send first-use guidance, but onboarding completion does not require creating the first reminder, completing agent settings, or completing a web account when the user is messaging-first.
- Existing behavior only remains part of the product when this requirements baseline names the user goal, product behavior, and boundary that justify it.

## 2. Current User Journey Matrix

| # | Product Role | User Type | Trigger Entry | User Goal | System Behavior That Must Hold | Status |
|---|---|---|---|---|---|---|
| 1 | Support journey: registration/login and account access | Individual user | Registration page, login page, email verification page, account access status page, subscription page, public explanation page | Create a web account, log in, establish a session; know the next step when verification, subscription, or access status blocks use | Support registration, login, email verification, resending verification emails, forgot/reset password, current user query, session/token; show users email verification status, subscription/access status, and the next step; enforce account access before channel connection, inbound assistant processing, and calendar import; public explanation, FAQ, demo, privacy, terms, and subscription pages may serve as product understanding, recovery, and compliance support | Current product contract |
| 2 | Support journey: first activation | Individual user | Web registration/login plus channel connection, or shared WhatsApp messaging-first contact, followed by first personal-channel inbound message | Complete the first usable activation and confirm that identity, channel, and first-message paths all work | For web-first users, onboarding completion requires registration/login, one usable personal channel, and one successfully received personal-channel message. For shared WhatsApp messaging-first users, onboarding completion does not require web registration/login; it requires trusted sender identity binding, a usable messaging channel, and one successfully received inbound message. The user is not required to create the first reminder or complete agent settings. The assistant may provide first-use guidance, but the completion definition is based on product-path facts | Current product contract |
| 3 | Support journey: personal channel reachability | Individual user | Channel management page, personal channel page, shared WhatsApp conversation entry | Establish a personal communication entry point on personal WeChat or shared WhatsApp, so daily conversations, reminders, and proactive follow-ups are reachable | Currently only supports an individual user having one reachable personal channel in personal WeChat or shared WhatsApp; supports viewing channel status, selecting channel type, creating a channel, initiating connection, checking connection status, removing a removable channel, retrying or relinking after failure. Personal WeChat is web-first and connection-first. Shared WhatsApp is the only current messaging-first auto-provisioning entry point. From the user's view, shared WhatsApp is still their own conversation entry point. Messaging-first users cannot remove the only channel identity that anchors their account. After a removable channel is removed, that channel is no longer usable, but the user's account and historical reminder ownership are unaffected. Reminders and proactive reach-outs use the user's current only connected personal channel. Currently only one personal channel may be linked | Current product contract |
| 4 | Core journey: daily conversation | Individual user | Personal WeChat or shared WhatsApp channel inbound message | Have daily conversations with the assistant; currently support multimodal input that the channel can carry; receive a text reply when a reply is needed; receive no message when the system explicitly decides no-reply; receive a waiting message when processing is slow, then later receive the final text reply | Inbound messages must be bound to a trusted account/customer context before assistant processing. If account access is not allowed, the user receives a user-understandable access-status reply instead of normal assistant intent execution. Shared WhatsApp inbound messages must be associated with the correct Coke user by sender identity, or by a valid pairing/claim path, before they enter the conversation journey. The system must decide whether the message needs a response: if a response is needed, send a text reply; if the system explicitly produces intentional no-reply, do not send any user-visible message; if processing times out but is still ongoing, send a visible waiting text and eventually an asynchronous final text reply; if processing fails, the error/failure must be observable. Current output contract only requires text replies and does not require voice, image, or video replies. When the Interaction Agent returns multiple text segments, message-style channels must deliver those segments as separate visible messages in order. Intentional no-reply must be distinguished from system failure | Confirmed core |
| 5 | Core journey: user timezone | Individual user | Agent settings page, reminder calendar page, timezone expressions in conversation | Let all reminders, calendar displays, and friend availability be interpreted according to the same personal timezone | A user has only one global default timezone. It can be viewed/modified in the settings page and can also be switched globally through conversation. Independent timezone per reminder is not supported. When the user mentions another timezone, the system should interpret it as an overall timezone switch or confirm the switch. Existing reminders' absolute trigger moments must not be silently rewritten because of a timezone switch; they are only displayed in the new timezone | Current product contract |
| 6 | Core journey: personal reminders | Individual user | Reminder intent in conversation, reminder calendar page, or proactive follow-up scenario | Create, view, edit, complete, and delete personal reminders; find reminders naturally by content, status, type, or time range; receive reminders when due; be asked to schedule reminders that have no trigger time; receive agent-created proactive follow-up reminders when proactive is enabled | Reminders must be owner-scoped. Support natural-language and page-based create, view, edit, complete, and delete. The reminders page is a calendar page used to display reminders that the user can directly manage. Conversation-based reminder lookup must support keyword, status, type, and trigger-time range filters. Conversation-based edit, complete, and delete may resolve reminders by natural-language keyword when that resolution is unambiguous; when resolution is ambiguous, the system must ask the user to choose before mutating reminders. Shared reminders also appear on the reminder calendar page and show related friend identifiers, but direct editing follows shared-reminder boundaries. Support relative time, specific time, global timezone, recurrence rules, and configurable duration (default 15 minutes). Support reminders without trigger times. Forbid creating completely identical actionable personal reminders. Forbid creating or editing calendar-visible timed reminders whose duration interval overlaps the same owner's existing calendar-visible active reminders or shared projections. Proactive follow-up is an agent-created reminder, but it is not shown on the reminder calendar page and cannot be directly modified by the user. When the user turns off proactive, all untriggered proactive follow-up reminders are canceled as well. When due, the reminder enters the Interaction LLM; the LLM knows this is a system reminder and uses text in the role's tone to notify the user. Every night at 8 PM, summarize reminders without trigger times and ask the user whether to schedule trigger times. After a recurring reminder triggers or this occurrence is completed, advance it to the next valid trigger. Deleting a recurring reminder deletes the entire series | Confirmed core |
| 7 | Core journey: friendship | Individual user | Friends page, public friend link, QR code, friend link code in conversation | Generate one's own friend link; let others authenticate as a Coke user or claim an existing messaging-first account after scanning or opening it and establish friendship; manage friend list | Friend links must be openable. Unauthenticated visitors can first be carried into login/registration or existing messaging-first account claim. Only users who have connected a usable personal channel may issue a friend link or link code. Establishing active friendship requires the joining user to be authenticated as a Coke user or to have claimed an existing messaging-first account; the joining user does not need a usable personal channel at friendship establishment time. Authenticated users can establish active friendship through a public friend-link code on the Friends page or a friend link code in conversation. The same pair of users must not create duplicate active friendships. Users can reset/disable links, view friends, and remove friends. Pending friend request accept/reject is not a current requirement | Current product contract |
| 8 | Core journey: shared reminders | Individual user + one or more friends | Social scheduling intent in conversation, friend availability query, reminder calendar page, shared reminder list/cancel/reschedule entry | Create the same shared reminder for one or more friends, view, cancel, or reschedule shared reminders, and check one or more friends' availability before scheduling | Active friendship must exist. Each friend reference must resolve to a unique active friend. Support privacy-safe availability queries for one or more friends. Before creating a shared reminder, confirm the creator has a usable personal channel, check each receiver for conflicts, and confirm each receiver has a usable personal channel. If any receiver has a conflict or any participant has no usable channel, do not silently create a partial reminder; report the conflicting or unreachable participant to the creator. The creator's own time conflict is intentionally not checked for creation. After checks pass, create one group shared reminder. Creator and all receivers should each receive their own associated reminder when due. Active shared reminders can be rescheduled by changing trigger time and/or duration; rescheduling checks all participants for conflicts and channel reachability before updating the shared reminder and all projections. Shared reminders appear on the reminder calendar page and show related friend identifiers. A user's completion action only handles that user's own projection. Any participant may cancel the whole group. Notifications are informational. Forbid creating completely identical active shared reminders. Pending accept/reject is not a current requirement | Current product contract |
| 9 | Support journey: Product notification | Individual user + friends | Friendship creation, shared reminder creation/reschedule/cancellation, system events or error events | Receive factually clear and understandable informational notifications; know what happened and what to do next when there is a failure | Only send informational and system notifications; do not use notifications for approval or action execution. Must cover friendship creation, shared reminder creation, shared reminder reschedule, shared reminder cancellation, related errors/failures/partial failures/undelivered/conflict/cancellation failure. Notification facts must include at least who, did what, object, time/timezone/duration. Errors must include user-understandable error information and must not expose raw channel errors or internal error codes. Final visible text is generated by the Interaction LLM based on structured facts and error facts | Current product contract |
| 10 | Support journey: calendar import | Individual user | Calendar import page, or handoff link given by assistant | Import Google Calendar into Coke reminders one time, and stop future Google Calendar authorization if needed | Confirm account/conversation ready before import. User authorizes calendar access. System fetches calendar events. Future events are converted into Coke-owned reminders. Event title and description become reminder content, event start time becomes reminder trigger time, event duration becomes reminder duration (use default 15 minutes when the event has no duration). All-day events are imported as reminders triggered at 00:00 on that date. Recurring events are preferably imported as Coke recurring reminders. When a recurring event cannot be reliably expressed using current recurrence rules, import it as one-time reminders for visible future occurrences and explain this in the import result. When the same calendar event is imported repeatedly, skip it directly without generating duplicate reminders and without requiring user confirmation. Historical events do not generate reminders. After import completion, report successfully imported count, skipped count, downgraded items, and failed items. The user may stop or revoke Google Calendar authorization. Revocation only affects future imports and does not delete imported Coke-owned reminders. Currently only one-time import is confirmed; continuous sync is not introduced | Confirmed to retain; one-time import |
| 11 | Support journey: agent settings | Individual user | Agent settings page | Set the assistant name, how the assistant addresses the user, persona, background, speaking style, extra rules, proactive switch, and memory switch; view channel connection status | Settings must be customer-scoped. Support view, update, and reset. Users can configure the assistant's user-visible behavior and long-term preferences. After proactive is turned off, the system no longer creates new proactive follow-up reminders and cancels untriggered proactive follow-up reminders. Turning off proactive does not affect ordinary personal reminders, reminders-without-trigger-time summaries, daily conversation replies, or Product notifications. After memory is turned off, the system no longer uses, adds, or updates long-term memory, but does not delete existing long-term memory. After memory is turned back on, existing long-term memory can continue to be used. User self-service clearing of long-term memory is currently not supported | Confirmed to retain; field-level scope confirmed |
| 12 | Support journey: account/data lifecycle | Individual user | Channel management page, reminder calendar page, friends page, agent settings page, calendar import page | Understand which connections, data, and relationships the user can remove, and which account-level actions are not yet supported | Currently supports removing a removable personal channel, deleting/completing personal reminders, canceling shared reminders, removing friends, turning off memory usage, and stopping or revoking Google Calendar authorization. A messaging-first user cannot remove the only channel identity that anchors the account. These actions do not delete the account itself. User self-service account deletion, full account export, full erasure, and clearing long-term memory are not currently supported | Current product contract |
| 13 | Supporting capability: shared-channel personal reachability | Individual user | Shared WhatsApp conversation entry; personal channel status surfaces | Let a shared WhatsApp conversation behave as the user's personal Coke channel for conversations, reminders, and proactive follow-up delivery | Shared WhatsApp inbound messages must be associated with exactly one trusted Coke user before assistant processing or reminder delivery. A known sender continues as the existing Coke user. A first-seen shared WhatsApp sender provisions a messaging-first Coke user bound to that sender identity, unless the inbound carries a valid pairing code from a web-first user's channel-connection flow, which binds the sender to that existing account instead (see §5.13). Visible replies, reminders, and proactive follow-ups must be delivered through the user's current connected personal channel. Channel failures must appear as user-understandable channel unavailable, connection failed, or reconnection required states. This capability supports personal channel reachability and is not an independent product journey | Current product contract |
| 14 | Support journey: account identity and web claim | Individual user | Shared WhatsApp first contact; web registration/login; friend link or calendar import on web; one-time login link in conversation | Keep one human mapped to one Coke user, and let a messaging-first user reach an authenticated web session without a second account | A Coke user is either web-first (email) or messaging-first (auto-provisioned only on first contact through shared WhatsApp, bound to the sender identity, no password). Each messaging identity maps to its own Coke user; the system does not merge or unlink accounts. A messaging-first user cannot remove the only channel identity that anchors the account. A messaging user reaches an authenticated web session by claiming their existing account, bidirectionally: a chat-initiated one-time login URL, or a web-initiated one-time code sent to the channel. During a web-first user's channel-connection flow, an inbound carrying a valid pairing code binds the channel identity to the existing account instead of auto-provisioning. Login URLs, claim codes, and pairing codes are one-time, time-limited, single-use | Current product contract |

## 3. Current Requirements List

This section consolidates the user journeys in the matrix into current requirement items. A single requirement item may serve multiple journeys.

| Current Requirement Item | Related Journey | Current Requirement Statement |
|---|---|---|
| Account access status and public explanation | Registration/login; channel reachability; daily conversation; calendar import | The system can show the user account access status, email verification status, subscription/access status, and guide the user to the next step. Account access is also a product gate: when access is denied because email verification is still required, subscription access is inactive, or the account is suspended, normal inbound assistant processing, channel connection, and calendar import must not proceed. The user must receive user-understandable recovery information. For shared WhatsApp messaging-first users whose subscription access is inactive, the conversation recovery reply may include a public checkout link. Public explanation, FAQ, demo, privacy, terms, and subscription pages may be retained as product understanding, recovery, and compliance support. Subscription/access status is a current requirement item. |
| First activation | Registration/login; channel reachability; daily conversation | Web-first onboarding completion requires registration/login, at least one usable personal channel, and one personal-channel message that the system successfully receives. Shared WhatsApp messaging-first onboarding completion does not require web registration/login; it requires trusted sender identity binding, a usable messaging channel, and one inbound message that the system successfully receives. The assistant may send first-use guidance, but onboarding completion does not require the user to create the first reminder, complete agent settings, or finish a fixed tutorial. |
| User timezone | User timezone; personal reminders; shared reminders; calendar import; agent settings | A user has only one global default timezone. It can be viewed and modified in the settings page and can also be switched globally through conversation. Reminder creation, editing, display, reminder calendar page, reminders-without-trigger-time summary, friend availability, and shared reminders all use this global timezone. Independent timezone per reminder is not supported. When the user mentions another timezone, the system should treat it as an overall timezone switch or confirm the switch. Existing reminders' absolute trigger moments must not be silently rewritten because of timezone switching; they are only displayed in the new timezone. |
| Trusted inbound message receiving | Daily conversation; channel reachability; shared-channel personal reachability | The system must receive personal WeChat or shared WhatsApp channel inbound messages, associate each message with a trusted Coke account/customer context, and preserve the message for the user's conversation without silent loss. For shared WhatsApp, messages are associated by each sender's own WhatsApp identity: a known sender identity continues as its existing Coke user, and a first-seen sender identity provisions a new messaging-first Coke user. During a web-first user's channel-connection flow, an inbound carrying a valid pairing code binds the sender to that existing account instead of provisioning (see §5.13). Sender identity is the account anchor for messaging-first shared WhatsApp users, so this is identity-based association, not identity guessing. Inbound can include text, images, voice, and other multimodal content that the channel can carry. The top-level requirement is that the system can receive the content into processable input; it does not require output media content. If a received message cannot be processed or associated with a trusted user, the failure must be observable. |
| Message sending and outbound delivery | Daily conversation; personal reminders; shared reminders; shared-channel personal reachability | The system must push visible replies, reminder triggers, and proactive follow-ups to the user's current only connected personal channel. Currently an individual user can only have one reachable channel in personal WeChat or shared WhatsApp. Text reply is the current product output contract. Media URL delivery is a channel capability, not a requirement that the AI generate media replies. When a reply consists of multiple text segments, message-style channels must receive those segments as separate ordered visible messages, not as one merged message with newline separators. After a reminder triggers, if the user has no usable channel or sending fails, it cannot be considered successfully delivered. |
| Conversation ordering and stale-reply safety | Daily conversation; personal reminders | When multiple messages arrive in the same conversation, the system must preserve the correct user-intent order. Older in-progress context must not continue to act as the latest user intent after a newer message changes the conversation. The system must not send duplicate replies or stale replies for work the user has already superseded. Partial, waiting, or already sent replies must be remembered well enough to avoid confusing repetition, and failures must remain observable. |
| Conversation generation and segmented visible output | Daily conversation | The Interaction Agent must output user-visible text replies. Currently output may be in 1-3 short segments. When a reply is needed, each segment is part of the user-visible reply and must be delivered through outbound delivery in order. Ordinary chat replies should fit a message-channel style: concise wording, no generic customer-service closing, and the final ordinary statement segment should not end with a full stop (`.` or `。`) unless another punctuation mark is semantically required. |
| Reply necessity determination and intentional no-reply | Daily conversation | Daily conversations do not require a reply to every message. The system must determine whether the user's message needs a response: if a response is needed, send a text reply; if the system explicitly produces intentional no-reply, do not send any user-visible message; if processing times out but is still ongoing, send a visible waiting text and send the final asynchronous text reply after completion; if processing fails, the error/failure must be observable. Intentional no-reply must be distinguished from system failure, empty-output exception, and tool-fallback failure. |
| Conversation history and user memory | Daily conversation; agent settings; personalization support | The system must maintain necessary recent conversation history, user preferences, relationship descriptions, boundaries, and disturbance willingness so later conversations, reminders, and proactive follow-ups understand context. Long-term memory is controlled by the memory switch. After memory is turned off, the system no longer uses, adds, or updates long-term memory, but does not delete existing memory. After memory is turned back on, existing long-term memory can continue to be used. User self-service clearing of long-term memory is currently not supported. |
| Reminder recognition, filtering, and personal reminder CRUD | Personal reminders | Users can create, view, edit, complete, and delete personal reminders through natural language or the reminder calendar page. Conversation-based reminder lookup must support keyword matching, lifecycle/status filters, reminder type filters, and trigger-time ranges. The reminder calendar page uses a calendar as the main view to show reminders. The system must understand relative time, specific time, global timezone, recurrence rules, and configurable duration (default 15 minutes), while keeping reminders owner-scoped. Reminders without trigger times are supported. Multiple reminder operations in one message are supported. The system must forbid completely identical actionable personal reminders: same owner, same matter/content, same trigger time; or same owner, same matter/content where both have no trigger time. The system must also forbid creating or editing a calendar-visible timed reminder when its duration interval overlaps an existing calendar-visible active reminder or shared projection for the same owner. Duration, creation entry point, and expression style are not part of the duplication definition. Similar but not completely identical reminders are not hard rejected. Completing a recurring reminder only completes this occurrence; deleting a recurring reminder deletes the entire series. Natural-language edit, complete, and delete can target a reminder by keyword only when the target is unambiguous; if no reminder or multiple reminders match, the system must ask a clarification or report the trusted failure before changing state. After creation, editing, completion, or deletion, the system should give the user a text confirmation. |
| Reminder triggering and recurring reminders | Personal reminders; shared reminder reachability | Due reminders must form reminder trigger events and enter the Interaction LLM. The LLM must know this is a system reminder and use text in the role's tone to notify the user. After a recurring reminder triggers or this occurrence is completed, advance the next valid trigger. Multiple reminders for the same owner at the same trigger time are merged into one reminder message when reminding, but each reminder and its event remain independent. If there is no usable channel or sending fails, an observable undelivered status must be retained. |
| Summary prompt for reminders without trigger times | Personal reminders | For reminders without trigger times, the system summarizes reminders still lacking scheduled times every night at 8 PM and asks the user through the Interaction LLM whether to schedule trigger times for these reminders. |
| Proactive follow-up reminder | Personal reminders; channel reachability; daily conversation; agent settings | Proactive follow-up is an agent-created reminder, used by the assistant to proactively care about the user based on the user's goals, habits, tasks, or context. It is not shown on the reminder calendar page and cannot be directly modified by the user. The user/agent settings can turn off proactive. When proactive is turned off, no new proactive follow-up reminders are created, and untriggered proactive follow-up reminders are canceled as well. Turning proactive back on only affects whether new proactive follow-up reminders can be created in the future; it does not restore previously canceled follow-ups. The prompt decides whether and when to create proactive follow-up reminders; this requirements layer does not define an independently verifiable frequency target. Do-not-disturb or notification preference settings are not currently provided. Proactive follow-up is user-invisible: when the channel is unavailable or sending fails, the follow-up expires and is discarded — it is not resent, does not enter undelivered handling, and is not shown on the reminder calendar page. |
| Product notification | Product notification; friendship; shared reminders; personal reminder reachability; shared-channel personal reachability | The system only sends informational and system notifications, and does not use notifications for approval or action execution. It must cover friendship creation, shared reminder creation, shared reminder reschedule, shared reminder cancellation, related system events, and error events. Notification facts must include at least who, did what, object, time/timezone/duration. In failure, partial failure, undelivered, conflict, or reschedule/cancellation failure scenarios, the notification must include user-understandable error information, such as the other party's channel being unavailable, the time conflicting with the other party's existing schedule, or reschedule/cancellation not succeeding. It must not expose raw channel errors, internal error codes, queue status, or low-level delivery attempts. Final visible text is generated by the Interaction LLM based on structured facts and error facts. |
| Calendar import | Calendar import; personal reminders; account/data lifecycle | Users can authorize Google Calendar and import future calendar events one time as Coke reminders. Imported reminders belong to the current individual user. Event title and description become reminder content, event start time becomes trigger time, and event duration becomes reminder duration (use default 15 minutes if the event has no duration). All-day events are imported as reminders triggered at 00:00 on that date. Recurring events are preferably imported as Coke recurring reminders. When a recurring event cannot be reliably expressed using current recurrence rules, import it as one-time reminders for visible future occurrences and explain this in the import result. When the same calendar event is imported repeatedly, skip it directly and do not generate duplicate reminders or require user confirmation. Historical events do not generate reminders. After import completion, the system must report successfully imported count, skipped count, downgraded items, and failed items. The user may stop or revoke Google Calendar authorization. Revocation only affects future imports and does not delete imported Coke-owned reminders. Currently only one-time import is confirmed; continuous sync is not required. |
| Agent settings configuration | Agent settings; daily conversation; personal reminders; proactive follow-up reminder | Users can view, modify, and reset their assistant name, how the assistant addresses the user, persona, background information, speaking style, extra rules, proactive switch, and memory switch, and view channel connection status. Settings must be customer-scoped. Reset restores default settings. After memory is turned off, the system no longer uses, adds, or updates long-term memory, but does not delete existing long-term memory. After memory is turned back on, existing long-term memory can continue to be used. User self-service clearing of long-term memory is currently not supported. The memory switch does not affect recent context needed to complete the current conversation. |
| User profile, relationship description, role goals/attitude updates | Daily conversation; agent settings; personalization support | The system can update the user's real name/nickname/description, relationship descriptions, and the role's long-term/short-term goals and attitude as personalization support. This item does not include numerical intimacy, trust, or dislike scores. |
| Friendship | Friendship; shared reminders | Users can generate, view, reset, and disable their public friend links and QR codes. A user who visits a friend link can establish active friendship after authenticating as a Coke user or claiming an existing messaging-first account, even if that joining account has not connected a usable personal channel yet. Only users who have connected a usable personal channel may issue friend links or link codes. Users can establish active friendship through a friend link code in conversation. Users can view their friend list and remove friends. The same pair of users must not create duplicate active friendship. Users cannot become friends with themselves. Pending friend request accept/reject is not a current requirement. |
| Shared reminders | Shared reminders; friendship; personal reminder reachability; Product notification | Users can create one group shared reminder for one or more active friends, view shared reminders, reschedule active shared reminders by changing trigger time and/or duration, cancel shared reminders, and check one or more friends' availability before scheduling. Creating a shared reminder must resolve each receiver to a unique active friend. If title, time, or necessary context is missing, the system must ask follow-up questions. Before creation, the creator must have a usable personal channel, each receiver conflict must be checked, and each receiver must resolve to a usable personal channel. The creator's own time conflict is intentionally not checked for creation. If any receiver has a conflict or any participant has no usable channel, the system explains who is conflicting or unreachable and who is available, and asks the creator to adjust time or participants; it must not silently create a partial reminder. After checks pass, the shared reminder immediately becomes active. Before rescheduling an active shared reminder, the system checks all participants for conflicts and usable personal channels; if any participant conflicts or is unreachable, the system does not update the shared reminder. Creator and all receivers should each receive their own associated projection when due. Shared reminders appear on the personal reminder calendar page and show related friend identifiers. A user's completion action only completes that user's own projection, and does not automatically complete for other participants. Any participant may cancel the whole group. Pending shared reminder accept/reject is not a current requirement. Notifications are informational only and not approval. Completely identical active shared reminders are forbidden: same creator, same participant set, same title/activity content, same local trigger time, same timezone, and same duration. |
| Personal channel delivery | personal WeChat; shared WhatsApp channel; shared-channel personal reachability | Currently an individual user may have only one reachable channel in personal WeChat or shared WhatsApp. Shared WhatsApp must appear to the user as that user's own conversation entry point. Personal WeChat remains web-first and connection-first. Shared WhatsApp is the only current messaging-first auto-provisioning entry point. A messaging-first user cannot remove the only channel identity that anchors their account. |
| Account identity and web claim | Registration/login; channel reachability; daily conversation; friendship; calendar import | A Coke user is either web-first (email registration/login) or messaging-first (auto-provisioned only on first contact through shared WhatsApp, bound to the sender identity, with no password). Each messaging identity maps to its own Coke user; the system does not merge separate accounts or provide unlinking. A messaging-first user cannot remove the only channel identity that anchors the account. A messaging user reaches an authenticated web session by claiming their existing account, never by registering a second one: bidirectionally via a chat-initiated one-time login URL or a web-initiated one-time code sent to the channel. During a web-first user's channel-connection flow, an inbound carrying a valid pending pairing code binds the channel identity to the existing account instead of auto-provisioning. Login URLs, claim codes, and pairing codes are one-time, time-limited, and single-use. Personal WeChat remains a web-first channel-connection path unless a later current requirement explicitly changes it. |
| Account/data lifecycle | Account/data lifecycle; channel reachability; personal reminders; shared reminders; friendship; agent settings; calendar import | Currently supports removing a removable personal channel, deleting or completing personal reminders, canceling shared reminders, removing friends, turning off memory usage, and stopping or revoking Google Calendar authorization. Removing a removable channel does not delete the account or reminders. A messaging-first user cannot remove the only channel identity that anchors the account. Deleting/completing reminders does not delete the account. Canceling a shared reminder stops all associated projections for the entire group. Removing a friend does not automatically cancel existing shared reminders. Turning off memory does not delete long-term memory. Revoking Google Calendar authorization does not delete imported Coke-owned reminders. User self-service account deletion, full account export, full erasure, and user self-service clearing of long-term memory are not currently supported. |

## 4. Capabilities Explicitly Not Included in the Current Requirements List

| Capability | Current Conclusion |
|---|---|
| Voice replies, image replies, video replies | The current output contract only requires text replies. The assistant is not required to reply to users with voice, images, or videos. |
| Image generation | Not currently included in product requirements. |
| Memo runtime / memo cards / memo search / memo review queue / agent memo proposals | Explicitly not included in current product requirements. Only long-term memory controlled by the memory switch is retained; no user-visible memo runtime is defined. |
| Photo library, Moments/social feed, photo deletion | Not currently included in product requirements. If content asset management or social display is needed later, it should be defined separately as a new user journey. |
| Numerical intimacy, trust, dislike | Not included in current requirements. Only non-numerical user preferences, relationship descriptions, boundaries, and disturbance willingness are retained. |
| Relationship decay, dislike blocking | Not included in current requirements. |
| Role busy/free schedule scripts | Not included in current requirements. |
| Holding user messages because the role is busy | Not included in current requirements. The current product prioritizes ensuring user help requests, reminders, and conversations are reachable. Proactive reach-out timing is governed by proactive prompt/settings behavior; no user-configurable do-not-disturb or notification preferences are introduced. |
| Independent timezone per reminder | Not included in current requirements. There is only the user's global default timezone; timezone switching is an overall switch. |
| User self-service account deletion / full account export / full erasure | Not included in current requirements. Currently only local lifecycle actions are defined, such as removing channels, deleting/completing reminders, canceling shared reminders, removing friends, and stopping Google Calendar authorization. |
| User self-service clearing of long-term memory | Not included in current requirements. The memory switch only controls whether long-term memory is used, added, and updated; it does not provide an entry point to clear existing long-term memory. |
| Do-not-disturb / notification preference settings | Not included in current requirements. Currently only the proactive switch is retained. Ordinary reminders, shared reminders, and system notifications are not controlled by additional notification preferences. |
| Fixed QueryRewrite/ContextRetrieve agent stage | Not treated as a user-visible requirement or a fixed agent stage. Only the product requirement of "needing historical context and user memory" is retained. |
| Legacy hard-coded chat-style management commands | Not included in current requirements. A generic management surface is not retained simply because of legacy management commands. |
| Legacy fixed SLO values / availability and latency targets | Fixed P99, error-rate values, and availability/latency targets are not part of the current requirements matrix. This document does not define a requirement-level SLO check. |
| Old data compatibility layer, old protocol adapters, old runtime shape compatibility | Not included in current requirements unless later explicitly confirmed as current product requirements. |

## 5. User Journey Details

### 5.1 Registration/Login

Confirmed:

- The onboarding completion definition is in §1 "First-use definition"; the first activation journey is in §5.2; first conversation guidance is in §5.4.
- Already implemented features are not removed by default. Implemented sub-features that are not part of the core contract should retain their current factual status, but must not dominate the core requirements.
- A Coke user may also originate from auto-provisioning on first contact through shared WhatsApp. Such messaging-first accounts have no password and reach the web by claiming their existing account, not by registering again. Account origin paths and web claim are detailed in §5.13.
- Account access is a current product gate, not only a display status. Access can be denied because email verification is still required, subscription access is inactive, or the account is suspended.
- When account access is denied, normal inbound assistant processing, channel connection, and calendar import must not proceed. The user must see or receive a user-understandable recovery step.
- For shared WhatsApp messaging-first users whose access is denied because subscription access is inactive, the conversation recovery reply may include a public checkout link.

User journey:

1. The individual user opens the registration or login entry point.
2. The user completes registration or login.
3. The user completes email verification when necessary.
4. The user completes subscription or renewal when necessary.
5. The system establishes a session/token and can return the current user identity and access status.
6. Subsequent channel connection, reminder, friendship, shared reminder, and calendar import usage can continue only when account access allows that surface.

The system must support:

- Registration.
- Login.
- Email verification.
- Resending verification emails.
- Forgot/reset password.
- Current user query.
- Session/token.
- Current user identity.
- Account access status and denied reason.
- Blocking normal inbound assistant processing when account access is denied.
- Blocking channel connection when account access is denied.
- Blocking calendar import when account access is denied.
- Showing or sending the recovery step for email verification, subscription renewal, or suspended-account support.
- Public checkout recovery for shared WhatsApp messaging-first subscription renewal.

Implemented and retained supporting capabilities:

- Subscription/access status.
- Membership/subscription status return.
- Display of account access status, email verification status, and subscription/access status.
- Account access gate for inbound assistant processing, channel connection, and calendar import.
- Public explanation, FAQ, demo, privacy, and terms pages.

### 5.2 First Activation

Confirmed:

- Web-first onboarding completion must satisfy all of the following: registration/login complete; at least one usable personal channel connected; the user sends one message through that channel and the system successfully receives it.
- Messaging-first onboarding completion currently applies only to shared WhatsApp users. It does not require web registration or login. It must satisfy all of the following: sender identity bound to a Coke user; messaging channel usable for replies and reminders; the system successfully receives the first inbound message.
- Creating the first reminder is not a condition for onboarding completion.
- Completing Agent settings is not a condition for onboarding completion.
- The assistant may send guidance in the first conversation, but onboarding completion does not depend on the user completing a fixed tutorial or replying with fixed content.
- A personal channel being "usable" must mean Coke can already send conversation replies, reminders, and proactive follow-ups through that channel. It cannot merely mean an upstream connection step succeeded.
- The first message must be bindable to a trusted account/customer context. The assistant must not guess the user's identity.

User journey:

1. A web-first user completes registration or login, then enters the channel connection entry point.
2. The web-first user connects a personal conversation entry point carried by personal WeChat or a shared WhatsApp channel.
3. A shared WhatsApp messaging-first user starts from the messaging channel without web registration or login.
4. The system binds the user's web account or sender identity to a trusted Coke user/customer context.
5. The system confirms that the channel is usable for replies and reminders.
6. The user sends the first message through that channel, or the messaging-first user's first inbound message is the activation message.
7. The system successfully receives that inbound message and binds it to the trusted account/customer context.
8. The system marks the user as onboarding complete.
9. The assistant may send first-use guidance or continue processing the real intent of this message.

The system must support:

- Determining whether activation is web-first or messaging-first.
- For web-first users, determining whether the user is registered/logged in.
- For shared WhatsApp messaging-first users, determining whether the sender identity is bound to a Coke user without requiring web registration or login.
- Determining whether the user has at least one usable personal channel.
- Determining whether the first personal-channel inbound message has been successfully received.
- Binding the first inbound message to a trusted account/customer context.
- Treating onboarding as complete only after the relevant identity condition, usable-channel condition, and first-inbound condition are satisfied.
- Showing or sending the next step when conditions are not satisfied, such as login for web-first users, connecting a channel, retrying connection, or sending the first message.
- Not blocking onboarding completion because the user has not created a reminder, set assistant persona, or opened the reminder calendar page.

Requirement boundaries:

- The core contract of first activation is that the account, channel, and first-message paths are valid.
- Onboarding guidance copy is conversation experience, not a completion condition.
- The system must not count states such as channel still connecting, connection failure, no trusted account/channel association, or first message not inbound as onboarding complete.

### 5.3 Personal Communication Channel Integration and Reachability

Confirmed:

- Currently, an individual user may link only one usable personal channel.
- The current personal channel choices are personal WeChat and shared WhatsApp.
- Personal WeChat is web-first and connection-first: the user starts from the web, initiates channel connection, waits for connection status, and then sends a message through that channel.
- Shared WhatsApp is the only current messaging-first auto-provisioning entry point: a first-seen shared WhatsApp sender creates a messaging-first Coke user bound to that sender identity; a known sender continues as the existing Coke user; a valid pairing code from a web-first channel-connection flow binds the sender to the existing web account instead.
- In pages and conversations, the user only needs to see channel type and connection status, such as WeChat, WhatsApp, not connected, connecting, connected, connection failed, and reconnection required.
- A user-visible "connected" state must mean Coke can already send conversation replies, reminders, and proactive follow-ups through that channel.
- This journey is the reachability support journey for daily conversations, reminder triggers, and proactive follow-up.
- There is currently no separate "disconnect channel" action. The user only needs channel removal where removal is allowed.
- A web-first user may remove a connected personal channel. After removal, the system must no longer reach the user through that channel.
- A messaging-first user cannot remove the only shared WhatsApp sender identity that anchors the account. Removing that identity would strand the user's account claim and reachability path, so it is not a supported lifecycle action.
- Removing a removable personal channel does not delete the account, delete reminders, or change reminder ownership.
- The user does not need to see removed channels or historical channels. After an allowed removal, the page returns to an unconnected, reconnectable channel state.
- The user can reconnect or relink a removable personal channel. Future reminders, conversation replies, and proactive follow-ups use the newly connected channel.

User journey:

1. A logged-in individual user opens the channel management entry point.
2. The user views the current personal channel status.
3. If there is no channel, the user selects personal WeChat or a shared WhatsApp channel and creates a reachable channel.
4. For personal WeChat, the user initiates connection from the web and waits for the connection status to change from "connecting" to "connected" or "connection failed".
5. For shared WhatsApp messaging-first use, the first inbound message can create the Coke user and count as the first channel message once the sender identity is trusted.
6. A known shared WhatsApp sender continues as the existing Coke user.
7. A shared WhatsApp inbound carrying a valid pairing code during a web-first channel-connection flow binds that channel identity to the existing web account instead of creating a messaging-first account.
8. If connection fails or the channel is unavailable, the user sees understandable states and recovery actions such as "connection failed", "needs reconnection", or "retry available".
9. If the user has already linked a personal channel, the system does not allow linking a second personal channel at the same time. The user must first remove the existing channel.
10. A web-first user can remove a removable channel when needed.
11. A messaging-first user cannot remove the only shared WhatsApp sender identity that anchors the account.
12. After connection succeeds, the system can deliver that user's conversation replies, reminders, and proactive follow-ups to that personal channel.
13. After an allowed removal, the user can no longer receive conversation replies, reminders, or proactive follow-ups through that removed channel.
14. If a web-first user switches from personal WeChat to shared WhatsApp, or from shared WhatsApp to personal WeChat, they must first remove the old channel. Switching the only channel of a messaging-first account is not currently defined.
15. After the user reconnects or relinks a personal channel, future reach-outs use the newly connected channel.

The system must support:

- Personal channel status.
- WeChat personal channel.
- Shared WhatsApp channel.
- Shared WhatsApp messaging-first first contact.
- Shared WhatsApp known-sender continuation.
- Shared WhatsApp pairing-code binding to an existing web-first account.
- User-visible channel connection entry point.
- User-visible channel connection status polling or refresh.
- User-visible channel unavailable, connection failed, and reconnection required states.
- Channel retry, removal where allowed, and relinking.
- Refreshing connection status and retrying connection (meaning defined in "shared-channel user-visible sub-features" below).
- At most one linked personal channel for the same user.
- Create channel, connect channel, poll connection status, and remove channel.
- Preventing removal of the only channel identity that anchors a messaging-first account.
- The only connected personal channel as the sending channel.
- Semantics for removal, relinking, and switching between personal WeChat and shared WhatsApp channel are defined below in "removal and relinking semantics" and are not repeated here.

User-visible states that must hold:

- Not connected.
- Connecting.
- Connected.
- Connection failed / needs reconnection.

Shared-channel user-visible sub-features:

- The user sees their own conversation entry point and does not need to understand how shared WhatsApp is operated behind the product.
- Ordinary user copy only expresses WeChat/WhatsApp and connection status.
- Personal WeChat must allow the user to initiate a linking or connection flow from the web side.
- "Connecting" means the user has initiated connection, but Coke has not yet confirmed that the channel has completed user binding and usable delivery. A connecting state must not be treated as reachable.
- The user can refresh connection status while connecting.
- The user can retry connection after a connection failure.
- Channel-specific details must be presented as personal channel status.
- Inbound messages must be associable with the correct trusted Coke user/customer. Ambiguous sender identity must not attach messages to the wrong user.
- For shared WhatsApp, each sender is distinguished by their own WhatsApp sender identity. A known sender identity continues as its existing Coke user; a first-seen sender identity provisions a new messaging-first Coke user bound to that identity, and the assistant communicates with them as that user, unless the inbound carries a valid pending pairing code from a web-first user's channel-connection flow, in which case the sender identity is bound to that existing account instead. Messaging-first accounts reach authenticated web sessions by claiming their existing account; this and the web-first pairing flow are detailed in §5.13.
- A channel must complete trusted Coke user/customer association and be usable for replies/reminders before it can be considered user-visibly "connected".
- Channel sending failure must not be considered successful delivery.
- Channel failures should be mapped to user-understandable channel unavailable, connection failed, or reconnection required states.
- Users must be able to retry connection or relink after failure.
- Users must be able to remove removable channels.
- Messaging-first users must not be able to remove the only shared WhatsApp sender identity that anchors the account.
- After a removable channel is removed, that channel is no longer used for future reachability.
- After removal, the user-visible status returns to "not connected" and removed or historical channel lists are not shown.
- Shared WhatsApp counts toward the same per-user limit of at most one reachable channel.
- Switching between personal WeChat and shared WhatsApp requires removing the old channel first when removal is allowed.
- Shared WhatsApp does not introduce a second user identity system, a second reminder owner system, or an independent operation role.

Removal and relinking semantics:

- After the user removes a removable personal channel, they can no longer receive conversation replies, reminders, or proactive follow-ups through that channel.
- Removing a channel does not delete the user's account.
- Removing a channel does not delete reminders or change reminder ownership.
- A messaging-first user cannot remove the only shared WhatsApp sender identity that anchors the account.
- The user page does not show removed channels or historical channels.
- Reminders due while the channel is unavailable enter an undelivered state.
- After the user reconnects or relinks a personal channel, future reminders, conversation replies, and proactive follow-ups use the newly connected channel.
- Undelivered reminders may be resent or shown as undelivered on the reminder calendar page.
- If a web-first user switches from personal WeChat to shared WhatsApp, or from shared WhatsApp to personal WeChat, they must first remove the old channel, because currently only one reachable channel is allowed.
- Switching the only channel of a messaging-first account is not currently supported.

Requirement boundaries:

- The core contract of a personal channel is channel ownership, connection state, and user reachability.
- The core contract of shared WhatsApp as a personal channel is user-visible connection status, trusted user association, reply/reminder delivery, and observable failure.
- Daily conversations, reminders, and proactive follow-ups only need to depend on trusted account, channel, and delivery status; they do not need to understand channel-specific connection details.
- States such as connection failure, connecting, and removal should appear as unified channel states, not as special conversation branches that the user must understand.
- Ordinary users only see channel type, connection status, and recovery actions.
- After a user removes a removable personal channel, that channel is no longer available for reachability, but it does not affect the user account, historical reminder ownership, or other user data.
- The removal boundary for messaging-first users is stricter: the only sender identity that anchors the account is not removable under the current product contract.

### 5.4 Daily Conversation

Confirmed:

- Daily conversation is a current core journey.
- Personal WhatsApp refers to a personal conversation carried by a shared WhatsApp channel, not an independent personal WhatsApp channel.
- First conversation may enter an onboarding guidance branch. The onboarding completion definition is in §5.2 First Activation.
- When Agent processing times out, the user should first receive a visible waiting text, and the final text reply should then be delivered asynchronously. This is a current required contract.
- For meaningless content, natural conversation endings, or scenarios where the user explicitly does not want to be disturbed, the system may intentionally produce no reply. This is not system failure and not silent message loss.
- Daily conversation does not require every message to be replied to. The system must decide whether the user message needs a response.
- When the system explicitly produces intentional no-reply, it sends no user-visible message.
- Current support includes multimodal input that the channel can carry, but the output contract only requires text replies.
- The assistant is currently not required to reply to users with voice, images, or videos.

User journey:

1. The user already has an identifiable identity and a reachable channel.
2. The user sends text, images, voice, or other messages that the channel can carry through personal WeChat or a shared WhatsApp channel.
3. The system binds the inbound message to a trusted account/customer context.
4. The system executes a single-Agent turn.
5. The system decides whether the user message needs a response.
6. If a reply is needed, the user receives an immediate text reply. If processing times out but is still ongoing, the user first receives a visible waiting text, and the final text reply is later delivered asynchronously.
7. If the system explicitly produces intentional no-reply, the system sends no user-visible message, but this result should be distinguished from system failure.
8. If processing fails, the error/failure must be observable and must not be mixed with intentional no-reply.
9. If this is a first-use scenario, the system may enter the onboarding guidance branch.

The system must support:

- Receiving personal WeChat inbound messages.
- Receiving shared WhatsApp channel inbound messages.
- Supporting multimodal input that the channel can carry.
- Binding inbound messages to a trusted account/customer context.
- Preserving received messages so accepted user input is not silently lost.
- Processing the message through a single-Agent turn.
- Generating synchronous or asynchronous text replies.
- Sending a visible waiting text when timing out.
- Delivering the final text reply back to the channel through outbound delivery.
- Deciding whether the user's message needs a response.
- Supporting intentional no-reply semantics to avoid treating intentional model no-reply as system failure.
- Providing observable failure status when processing fails, without mixing it with no-reply.
- Maintaining necessary historical context and user memory so replies understand context.

Sub-features that must hold:

- Account context is trusted and does not rely on the agent guessing the user.
- Conversation/session can be stably identified.
- Synchronous waiting and asynchronous supplementary delivery semantics are clear. On timeout, a visible waiting text must be sent first, and the final text reply must be delivered asynchronously.
- The user's current personal channel is usable for outbound delivery.
- The minimum and currently necessary contract for user-visible output is text reply. Voice reply, image reply, video reply, or matching input and output media types is not required.
- System failure, empty-output exception, and intentional model no-reply must be distinguishable: system failure must not be silent; intentional no-reply sends no user-visible message; slow processing must not be misclassified as no-reply.

Onboarding (first conversation):

- When the user has their first conversation with this agent (the system determines this based on whether the user and agent already have a conversation relationship), the system must enter the onboarding branch.
- The specific behavior of the onboarding branch is driven by the configured onboarding prompt/settings. The system sends first-use guidance to the user according to that prompt.
- The top-level requirements do not define the specific onboarding wording, tone, number of steps, or number of messages. These are determined by the onboarding prompt/settings.
- Onboarding is injected only in the first conversation and is not repeatedly triggered in later conversations.
- Onboarding may only introduce capabilities that are truly currently available. Without successful tool results, it must not claim that it has already completed reminders or other actions for the user.

Requirement boundaries:

- The core contract of daily conversation is trusted account context, text reply, turn execution, reply necessity determination, reply delivery, timeout/fallback semantics, intentional no-reply, and failure observability.
- Multimodal input is part of inbound message standardization and Interaction LLM processable input. It does not change the current output contract of "text reply".
- Daily conversation is not responsible for establishing the channel. Trusted account and usable-channel context must already exist before the message enters the conversation journey.
- No matter how the system processes messages internally, the user-visible semantics must remain: the message is received and will be processed; when a reply is needed, it is replied to in text; timeout produces a visible waiting text, and the final text reply can be delivered asynchronously; when the model intentionally no-replies, no user-visible message is sent; stale or duplicate replies should not appear after a newer user intent supersedes older work.
- Intentional no-reply must be retained as an observable result, not mixed with failure.
- Reply language is identified and handled by the Interaction LLM based on the user's language. It is not a configurable settings field.

### 5.5 User Timezone

Confirmed:

- A user has only one global default timezone.
- The user can view and modify the global default timezone in the settings page.
- The user can switch timezone globally through conversation, for example, "remind me according to Tokyo time from now on".
- Independent timezone per reminder is not currently supported.
- When the user mentions another timezone while creating a reminder, it should be understood as a global timezone switch, or the system should first confirm the global switch when needed to avoid misunderstanding.
- Switching timezone should not silently rewrite existing reminders' absolute trigger moments. Existing reminders are only displayed in the new global timezone.
- Newly created reminders, reminder calendar display, reminders-without-trigger-time summaries, friend availability, and shared reminders all use the current global default timezone.

User journey:

1. The user opens the agent settings page to view the current timezone.
2. The user switches the global default timezone in settings, or says in conversation, "remind me according to Tokyo time from now on".
3. The system confirms that the timezone has been globally switched.
4. When the user later creates reminders, views the calendar, or queries friend availability, the system interprets and displays according to the new global timezone.
5. Existing reminders' absolute trigger moments remain unchanged and are only displayed in the new global timezone.
6. If the user says "remind me tomorrow at 9 AM New York time", the system should understand this as creating after switching the global timezone to New York time, or first confirm whether the user wants to switch globally to New York time.

The system must support:

- Reading the user's global default timezone.
- Modifying the user's global default timezone in the settings page.
- Modifying the user's global default timezone through conversation.
- Using a unified global timezone in reminder creation, editing, confirmation, trigger copy, reminder calendar page, reminders-without-trigger-time summaries, calendar import results, friend availability, and shared reminders.
- Not silently rewriting existing reminders' absolute trigger moments after the global timezone is changed.
- When the user mentions another timezone but the semantics might mean independent timezone for one reminder, the system should confirm global switch semantics instead of creating an independent timezone for a single reminder.

Requirement boundaries:

- User timezone is a customer-scoped global setting, not per-reminder user configuration.
- Channels and the Interaction LLM should not use different default timezones to interpret the same reminder time.
- Current requirements do not support product semantics such as "this reminder uses New York time, while other reminders use Tokyo time".
- For existing reminders, the due moment and recurrence/window interpretation chosen at creation or last edit remain stable. A global timezone switch changes only display and the timezone applied to newly created reminders; it does not recompute existing reminders' trigger moments or recurrence windows. This is a refinement of "only one global timezone", not a per-reminder user-configurable timezone.

### 5.6 Friendship

Confirmed:

- Friendship is part of the current product contract.
- Friendship serves interpersonal accountability collaboration and is also the prerequisite relationship for shared reminders.
- A friend link is an authorization entry point. After visitors authenticate as a Coke user through web login/registration or by claiming an existing messaging-first account, an active friendship is created directly. No owner approval is needed and no pending friend request is produced.
- Users can generate their own public friend links.
- Only users who have connected a usable personal channel may generate or share a friend link or link code.
- Users can share their friend links through QR codes.
- Unauthenticated visitors who open a friend link can first register, log in, or claim an existing messaging-first account.
- Authenticated users who have connected a usable personal channel can establish active friendship with the link owner after friend-link handoff.
- Users can also establish active friendship in conversation through a friend link code.
- The same pair of users cannot create multiple active friendships.
- Users cannot establish friendship with themselves.
- Users can view their friend list.
- Users can remove friends.
- After removing a friend, both parties can re-establish active friendship through a still-valid friend link or link code.
- Users can reset their friend link so the old link is no longer a new-friend entry point.
- Users can disable their friend link so others cannot continue adding them through the link.
- Reset and disable only affect future new friendships and do not affect already established friendships. Reset means the old link becomes invalid and a new link is generated or enabled. Disable means the current friend link is turned off.
- Pending friend request accept/reject is not a current requirement. Establishing friendship means directly active product semantics.
- Generating or sharing a friend link or link code requires the owner to have a connected usable personal channel. Establishing an active friendship requires the joining user to be authenticated as a Coke user or to have claimed an existing messaging-first account, and to have connected a usable personal channel. As a result, both friends always have a usable channel at the moment friendship is established, so friendship-creation notifications and later reachability can be delivered.

User journey:

1. The user opens the friends page.
2. The user views their friend link and QR code.
3. The user shares the friend link or QR code with someone else.
4. The visitor opens the friend link.
5. If the visitor is not authenticated as a Coke user, the system guides the visitor to register, log in, or claim an existing messaging-first account and preserves the current friend-link handoff context.
6. After the visitor is authenticated as a Coke user or has claimed an existing messaging-first account, and has connected a usable personal channel, the system establishes active friendship between the visitor and the link owner. If the visitor has not yet connected a usable personal channel, friendship is not established until they complete channel connection.
7. If the two users are already active friends, the system does not create a duplicate relationship and tells the user they are already friends.
8. If a user tries to open their own friend link, the system must not create a self-friendship.
9. The user can enter a friend link code in conversation, and the system establishes the corresponding active friendship.
10. The user can view the friend list on the friends page.
11. The user can remove a friend.
12. If the two parties were friends before but the friendship was removed, they can re-establish active friendship through a valid friend link or link code.
13. The user can reset the friend link. After reset, the old link cannot be used to add new friends; the new link can continue to be shared.
14. The user can disable the friend link. After disable, others cannot continue adding the user through that link.
15. The user can re-enable or regenerate a shareable friend entry point.

The system must support:

- Getting the current user's friend link.
- Displaying the friend-link QR code.
- Public friend-link access.
- Authentication/claim handoff for unauthenticated visitors.
- Continuing friend-link handoff after authentication or account claim.
- Requiring the owner to have a connected usable personal channel before generating or sharing a friend link or link code.
- Requiring the joining user to be authenticated as a Coke user or to have claimed an existing messaging-first account, and to have connected a usable personal channel before establishing active friendship.
- Establishing active friendship through a friend link.
- Establishing active friendship through a friend link code in conversation.
- Re-establishing a removed active friendship through a valid friend link or link code.
- Viewing the friend list.
- Removing friends.
- Resetting the friend link.
- Disabling the friend link.
- Preventing users from establishing friendship with themselves.
- Preventing the same pair of users from creating duplicate active friendships.
- Returning an understandable result when active friendship already exists, instead of creating duplicate relationships.
- Preventing disabled friend links from adding new friends.
- Preventing old friend links after reset from adding new friends.
- Ensuring reset and disable do not delete or hide established friendships.
- Ensuring the friend list at least allows the user to distinguish each friend.
- The friend list currently only needs to show each friend's identifiable name or identifier, active relationship status, and remove-friend action. Notes, groups, avatar, recent interaction time, or friend detail pages are not required.
- When friend names or identifiers are duplicated, later friend matching in conversation must ask follow-up questions for clarification.

Relationship between friendship and channel:

- Generating or sharing a friend link or link code requires the owner to have a connected usable personal channel.
- Establishing an active friendship requires the joining user to be authenticated as a Coke user or to have claimed an existing messaging-first account, and to have connected a usable personal channel. A user without a connected channel cannot complete friendship establishment.
- Because both the link owner and the joining user have a connected channel at establishment time, friendship-creation notifications, shared reminders, and later proactive reachability can be delivered.
- Removing a channel later does not delete existing friendships; later reachability when a channel is missing follows the existing undelivered/reachability rules.

Remove-friend semantics:

- Removing a friend only changes the friendship relationship. It does not delete accounts, personal reminders, or automatically cancel existing active shared reminders.
- After a friend is removed, that friend no longer appears in the current user's active friend list.
- After a friend is removed, the two parties can no longer create new shared reminders based on that active friendship.
- The two parties can later re-establish active friendship through a still-valid friend link or link code.
- Removing a friend does not delete either party's account.
- Removing a friend does not delete either party's personal reminders.
- Handling of existing shared reminders after friend removal belongs to the shared reminder journey and is not predefined in the friendship journey.

Currently not required:

- Friend request pending approval.
- Friend request rejection.
- Friend request pending state.
- Friend groups.
- Friend notes.
- Friend avatars.
- Recent interaction time.
- Friend detail page.
- Friend blacklist.
- Friend recommendations.
- Friend activity feed or social content stream.

Requirement boundaries:

- The core contract of friendship is active friendship, not a pending request workflow.
- Friend links are product entry points and should not be mixed with personal channel binding entry points.
- A connected usable personal channel is a precondition for both sides of friendship: the owner must have one to issue a link or code, and the joiner must have one to complete establishment.
- Friendship must be account/customer-scoped and must not rely on the assistant guessing the identities of both parties.
- Establishing friendship must be idempotent. Repeated visits, repeated link-code inputs, or repeated submissions must not create multiple active friendships.
- Removing a friend is a relationship state change and should not cascade-delete user accounts, personal reminders, or unrelated data.

### 5.7 Shared Reminders

Confirmed:

- Shared reminders are part of the current product contract.
- Shared reminders depend on active friendship. Each receiver must have active friendship with the creator.
- Shared reminders support one creator scheduling with one or more active friends. For example, if the user says "schedule with Bob and Carol", the system should create one group shared reminder rather than split it into multiple pairwise reminders.
- The group shared reminder's participants include the creator and all receivers.
- Each participant has their own reminder projection. When due, each participant receives their own associated reminder through their own channel.
- A shared reminder is not an invitation approval flow. It becomes active immediately after creation, receivers do not need to accept/reject, and notifications are informational only.
- Users can create shared reminders for one or more friends through conversation.
- Users can view shared reminders.
- Users can reschedule active shared reminders by changing trigger time and/or duration.
- Users can cancel shared reminders.
- Users can query one or more friends' availability before scheduling.
- Friend availability only exposes privacy-safe busy/free information and does not expose friend reminder details.
- Friend availability uses Coke reminders as the data source and does not use Google Calendar for this feature.
- When creating a shared reminder, each friend reference must resolve to a unique active friend. If any friend name or target is ambiguous, the system must ask follow-up questions.
- If any receiver does not exist, cannot be resolved, or is not an active friend, the system must not silently skip that receiver. It must ask a follow-up question or return a user-understandable error.
- Creating a shared reminder requires at least participants, title or activity content, and trigger time. Time interpretation uses the user's global default timezone.
- Shared reminder duration defaults to 15 minutes. The user may explicitly set another duration.
- Receiver conflict is a hard pre-creation constraint. The system checks each receiver for conflicts in the time interval corresponding to the reminder duration (default 15 minutes). If any receiver has a conflict, the system does not create the shared reminder. It should explain who has a conflict and who is available, then ask the creator to adjust time or participants.
- Receiver conflict checks use each receiver's personal reminders and shared reminders (both count), judged by overlap between each reminder's duration interval. This uses the same source as friend availability queries.
- Participant channel availability is a hard pre-creation constraint alongside receiver conflict: the creator and each receiver must have a usable personal channel at creation time. If any participant has no usable channel, the shared reminder is not created, and the creator is told who is unreachable.
- Before creation, receiver conflicts and participant channel availability are checked. The creator's own time conflict is intentionally not checked.
- Before rescheduling an active shared reminder, all participants' conflicts and channel availability are checked, excluding that same shared reminder's current projections from the conflict calculation.
- Shared reminder rescheduling updates the group shared reminder and every participant projection in place. It must not cancel and recreate the shared reminder under a new identity.
- After all receiver conflict checks pass, the shared reminder immediately becomes active.
- After creation, creator and all receivers should each receive their own associated projection when due.
- Creator and receivers' reminder triggering, delivery failure, and undelivered handling follow the channel and delivery rules for personal reminders.
- From the user's perspective, a shared reminder is still their own reminder, just with friend associations. A user's completion action only processes that user's own projection and does not automatically complete for other participants.
- Creating completely duplicate shared reminders is forbidden: an active shared reminder with the same creator, same participant set, same title or activity content, same local trigger time, same timezone, and same duration is considered duplicate. Participant order does not affect duplicate judgment. Timezone and duration participate in duplicate judgment.
- If a completely identical active shared reminder already exists, the system rejects creation and tells the user it already exists. Similar but not completely identical shared reminders are not hard rejected.
- Shared reminder notifications are informational, not invitation approval.
- Receivers do not need to accept; the creator does not need to wait for receivers to accept.
- Pending shared reminder accept/reject is not a current requirement.
- Any participant can cancel an active shared reminder.
- After any participant cancels a shared reminder, the system cancels the whole group, stops all participant projections, and notifies the other participants. Non-participants cannot view or cancel it.
- The shared reminder list only needs to show title or activity content, participants, trigger time, user's global timezone, duration, current status, and support canceling or rescheduling active shared reminders. Detail page, content editing, comments, chat, or time-voting are not required.
- Shared reminders support rescheduling trigger time and duration. Shared reminder title or activity content editing is not currently supported; to change title or activity content, the user needs to cancel the entire shared reminder and create it again.
- Shared reminders appear on the personal reminder calendar page and show related friend identifiers. The shared reminder list currently does not require filtering.
- After a shared reminder is canceled, none of the participants will receive that associated reminder.
- Canceling a shared reminder notifies the other participants. The notification is informational.
- Removing a friend does not automatically cancel existing active shared reminders. The user must use the shared reminder cancellation action to cancel them.
- After a friend is removed, the two parties can no longer create new shared reminders based on that removed friendship.

User journey:

1. The user has already established active friendship with each target friend.
2. The user expresses in conversation that they want to schedule with one or more friends, invite friends, arrange a shared activity for friends, or opens the shared-reminder entry point.
3. If the user only wants to know when one or more friends are available, the system queries friend availability and only returns privacy-safe busy/free information.
4. If the user wants to create a shared reminder, the system resolves the target friend set.
5. If any friend reference is ambiguous, the system asks the user to choose which friend.
6. If any target user is not an active friend, the system does not create the shared reminder and prompts the user to first establish friendship or adjust participants.
7. The system confirms the shared reminder's title or activity content, trigger time, and duration (default 15 minutes, configurable). Time is interpreted according to the user's global default timezone.
8. If necessary information is missing, the system asks follow-up questions.
9. The system checks whether the creator and each receiver have a usable personal channel, and whether each receiver has a conflict in the corresponding time interval.
10. If any participant has no usable channel, or any receiver conflict exists, the system does not create the shared reminder. It tells the creator who is unreachable, or who has a conflict and who is available, then asks the user to change time or adjust participants.
11. If checks pass, the system checks whether a completely identical active shared reminder already exists.
12. If a completely identical active shared reminder already exists, the system rejects duplicate creation and tells the creator it already exists.
13. If checks pass and there is no duplicate, the system creates one active group shared reminder.
14. The system ensures creator and all receivers will each receive their own associated projection when due.
15. The system confirms to the creator that the shared reminder has been created.
16. The system sends informational notifications to all receivers.
17. When due, all participants each receive their own associated reminder through their own usable personal channel.
18. Any participant can view their own shared reminder list.
19. Any participant can cancel an active shared reminder.
20. After cancellation, all participant projections stop, and the other participants receive an informational notification.
21. Any participant can request a time and/or duration change for an active shared reminder.
22. If the reschedule target is ambiguous, missing required time information, would conflict with any participant's existing reminders, or any participant is unreachable, the system asks a follow-up question or returns a user-understandable failure without changing the shared reminder.
23. If checks pass, the system updates the existing shared reminder and all participant projections in place, then confirms the reschedule and notifies the other participants.

The system must support:

- Querying friend availability.
- Friend availability queries must specify or resolve one or more active friends.
- Friend availability queries must have a date range and use the user's global default timezone.
- Friend availability only returns privacy-safe busy/free information and does not return friend reminder details.
- Creating group shared reminders.
- Viewing the shared reminder list.
- The shared reminder list shows title or activity content, participants, trigger time, user's global timezone, duration, current status, and cancellation/reschedule entry.
- Showing shared reminders on the personal reminder calendar page with related friend identifiers.
- Rescheduling active shared reminders by changing trigger time and/or duration.
- Before rescheduling, checking every participant conflict in the new time interval, excluding the current shared reminder's existing projections from self-conflict.
- Before rescheduling, checking that every participant still has a usable personal channel.
- Not rescheduling a shared reminder when any participant conflict exists or any participant has no usable channel.
- Updating the group shared reminder and all participant projections in place when rescheduling succeeds.
- Canceling shared reminders.
- When the user wants to modify the title or activity content of a shared reminder, guiding the user to cancel the entire shared reminder and create it again.
- Creating shared reminders through conversation.
- Viewing shared reminders through conversation.
- Canceling shared reminders through conversation.
- Resolving each receiver to a unique active friend.
- Asking follow-up questions when any receiver is ambiguous.
- Refusing creation or requiring participant adjustment when any receiver is not an active friend.
- Requiring title or activity content, trigger time, and at least one receiver to create a shared reminder.
- Supporting duration, default 15 minutes, with explicit user override.
- Before creation, checking each receiver conflict in the time interval corresponding to reminder duration (default 15 minutes).
- Before creation, checking that the creator and each receiver have a usable personal channel.
- Not creating a shared reminder when any receiver conflict exists or any participant has no usable channel.
- Explaining who has a conflict and who is available when receiver conflict exists, and explaining who is unreachable when a participant has no usable channel.
- Preventing completely identical active shared reminders from being created twice.
- Becoming active immediately after creation.
- Creating each participant's own reminder projection for creator and all receivers.
- Ensuring each participant can receive their own associated reminder when due.
- Ensuring reminders received by participants retain the group shared reminder association and do not become unrelated ordinary reminders.
- A user's completion action only processes that user's own projection, and does not automatically complete other participants' projections.
- Notifying receivers that the shared reminder has been created.
- Allowing any participant to cancel the shared reminder.
- Stopping all participant projections after cancellation.
- Notifying other participants after cancellation.
- If cancellation matches multiple candidates, the system must ask follow-up questions and must not cancel the wrong shared reminder.
- Canceling an already canceled shared reminder should return an understandable result rather than executing the destructive action again.

Relationship between shared reminders and personal reminders:

- From the user's perspective, a shared reminder is still their own reminder, just with friend associations.
- Each participant should receive their own associated reminder through their own usable personal channel.
- After the user receives the associated reminder, completion processing by default only affects that user's own projection.
- Completing one's own projection does not automatically complete it for other participants.
- Canceling a shared reminder stops all projections for the whole group. It is not equivalent to completing or modifying one's own projection.
- Rescheduling a shared reminder changes the group shared reminder's time and/or duration for all projections. It is not equivalent to modifying only one participant's projection.
- Directly modifying the title or activity content of a shared reminder is not currently supported. The user needs to cancel the entire shared reminder and create it again.
- The visible reminder after a shared reminder is due still enters the Interaction LLM. The assistant reminds the user in the role's tone.
- A delivery failure for one participant only affects whether that participant receives their own associated reminder. It does not affect whether other participants receive their reminders.

Currently not required:

- Pending shared reminder.
- Receiver accept.
- Receiver reject.
- Batch accept/reject.
- Shared reminder detail page.
- Direct title or activity-content editing of shared reminders; currently the user needs to cancel the entire shared reminder and create it again.
- Shared reminder list filtering.
- Shared reminder comments.
- Shared reminder chat group.
- Shared reminder time-voting.
- Reading friend availability from Google Calendar.
- Exposing the other party's reminder details, calendar details, or private schedule contents.
- Shared reminder rate limiting, or blocking shared reminders from a specific friend (anti-harassment controls). Not currently considered; removing the friend is the only escape hatch, which stops new shared reminders.

Requirement boundaries:

- The core contract of shared reminders is group participant association + each participant's own due-time reachability + informational notification.
- Pending accept/reject workflows should not re-enter current requirements.
- Friend availability queries must protect privacy and only output busy/free information useful for scheduling.
- Receiver conflict is a pre-creation product constraint. When there is a conflict, the system must not create first and wait for the other party to handle it, nor silently skip conflicting participants and create partially.
- Participant channel availability is also a pre-creation product constraint. The system must not create a shared reminder when the creator or any receiver currently has no usable channel and would not receive their own associated reminder.
- After a shared reminder is created, the system must not claim creation succeeded while some participant will not receive their own associated reminder.
- After a shared reminder is canceled, the system must not stop only part of the participant projections and allow other participants to continue receiving the associated reminder.
- Shared reminders must be participant-scoped. Non-participants cannot view or cancel them.
- Cross-timezone friend scenarios for availability queries and receiver conflict detection are not specially designed for in the current requirements. Availability and conflict follow the current product's timezone handling and are not given dedicated multi-timezone treatment.

### 5.8 Personal Reminders

Confirmed:

- Personal reminders are a current core journey.
- Personal reminders cover creation through conversation, management on the reminder calendar page, due-time triggering, post-reminder reply handling, and undelivered handling.
- The reminder calendar page is the main page for personal reminders. It uses a calendar as the main view to display future one-time reminders, recurring reminder series, reminders without trigger times, shared reminders, and undelivered reminders.
- Due reminders enter the Interaction LLM. The LLM knows this is a system reminder and uses text in the role's tone to notify the user.
- Reminders without trigger times belong to personal reminders. Every night at 8 PM, the system summarizes them and asks the user whether to schedule trigger times.
- Recurring reminders are part of the personal reminder core requirements. Completion means completing this occurrence; deletion means deleting the entire series. Independent skip is currently not supported.
- Proactive follow-up is a special type of reminder. It is not shown on the reminder calendar page, cannot be directly modified by the user, and is controlled by the proactive switch.
- Duration defaults to 15 minutes. Users can explicitly set another duration. Time is interpreted according to the user's global default timezone. Independent timezone per reminder is not supported.
- When users mention another timezone in conversation, the system should globally switch the user's default timezone or first confirm the global switch.
- User-visible status focuses on product actions and does not expose internal state-machine fields. Deleting a reminder means removing it from the current product state.

User journey:

1. The user expresses reminder intent through conversation, or opens the reminder calendar page.
2. If the user gives a trigger time or recurrence rule, the user creates a one-time or recurring personal reminder.
3. If the user does not give a trigger time, the system creates a reminder without a trigger time.
4. If the user explicitly gives a duration, the system uses that setting. If not, the default is 15 minutes.
5. The user can view their reminders, reminders without trigger times, shared reminders, undelivered reminders, and single-reminder details on the reminder calendar page.
6. The user can edit the content, trigger time, and duration of an ordinary personal reminder, and can also add a trigger time to a reminder without a trigger time.
7. The user can complete reminders. For a one-time reminder, completion means the item has been handled. For a recurring reminder, completion means completing this occurrence. For a reminder without a trigger time, completion means the item has been handled.
8. The user can delete reminders. For a one-time reminder, delete that reminder. For a recurring reminder, delete the entire series. For a reminder without a trigger time, delete that reminder.
9. In the default view of the reminder calendar page, the user only sees reminders that are still actionable or will still trigger in the future.
10. A completed one-time reminder or reminder without a trigger time leaves the default view of the reminder calendar page.
11. The completed occurrence of a recurring reminder leaves pending state, but the series continues and shows the next trigger according to the rule.
12. Deleted reminders no longer appear in user-visible lists, reminders-without-trigger-time summaries, or future triggers.
13. When a reminder is due, the system passes the context "this is a system reminder" to the Interaction LLM.
14. The Interaction LLM notifies the user with a text reminder in the role's tone.
15. After receiving a reminder, the user can reply to complete it, reschedule it, delete it, or continue ordinary conversation.
16. If the user replies that it is completed, the current reminder occurrence is completed. If it is a recurring reminder, only this occurrence is completed.
17. If one reminder message contains multiple reminders, the user's reply "done" means all items in this reminder message are completed.
18. If the user replies with "remind me later", "change it to tomorrow", "change to another time", etc., the system updates the reminder time when the new time is clear, and asks a follow-up question when the time is unclear.
19. If the user replies "no need to remind me" or "delete it", a one-time reminder is deleted; a recurring reminder's entire series is deleted.
20. If the user replies with ordinary chat or meaningless content, the system should not automatically change reminder status.
21. Every night at 8 PM, the system summarizes reminders that still have no scheduled trigger time and asks the user whether to schedule trigger times for them.
22. The user can schedule times for one or more reminders in the summary.
23. The user can complete or delete one or more reminders in the summary.
24. When the user explicitly expresses batch scheduling, the system sets trigger times for the corresponding reminders in batch.
25. If the user gives only one time while the summary contains multiple reminders and the target cannot be determined, the system should ask a follow-up question.
26. When the user says "all of these are done", the system batch-completes the reminders in the summary.
27. After the user schedules a trigger time for a reminder without a trigger time, that reminder becomes a reminder with a trigger time and appears on the calendar page at the new time.
28. After the user removes the trigger time of a one-time reminder, that reminder becomes a reminder without a trigger time and enters the unscheduled area and the daily 8 PM summary.
29. If the user attempts to remove the trigger time of a recurring reminder and the recurrence rule can no longer be maintained after removal, the system should ask whether to convert it into a reminder without a trigger time or delete the entire recurring series.
30. If the user does not respond or does not schedule times for these reminders, they remain and appear again in the summary at 8 PM the next day.
31. If the user replies to the summary with ordinary chat or meaningless content, the system should not automatically change these reminder states.
32. If it is a recurring reminder, after this occurrence triggers or the user completes this occurrence, the system advances the next trigger time.

The system must support (capability index; detailed rules are in the topic sections below and are not repeated here):

- Reminder CRUD: creating, viewing, editing, completing, and deleting personal reminders through conversation and the reminder calendar page, including creating reminders without trigger times, batch operations, and setting/modifying/clearing duration.
- Reminder calendar page display, creation/editing, status, and detail fields: see "Reminder calendar page display rules", "Reminder calendar page creation and editing rules", and "Reminder status and detail fields".
- Conversation creation follow-up questions and operation confirmations: see "Follow-up boundaries for creating reminders in conversation" and "Reminder operation confirmation replies".
- Due-time triggering and delivery failure handling: see "Reminder triggering and delivery failure handling".
- Handling user replies after reminders: see "User reply semantics after reminders".
- Reminders-without-trigger-time summary and conversion between with-trigger-time and without-trigger-time reminders: see "User reply semantics after reminders-without-trigger-time summaries" and "Conversion between reminders without trigger times and reminders with trigger times".
- Proactive follow-up reminder: see "Proactive follow-up reminder".
- Recurring reminders: see "Recurring reminder rule constraints".
- Matching ambiguity and creation-time duplicate/similar handling: see "Matching ambiguity handling" and "Creation-time duplicate/similar reminder handling".
- Time and timezone interpretation: see "Time interpretation and past-time handling" and "Timezone interpretation rules".
- Global invariants: all reminders are owner-scoped; do not expose reminder internal IDs, low-level delivery attempts, internal retry counts, error codes, queue status, or internal state-machine fields to the user.

Reminder calendar page display rules:

- The reminder calendar page is the main page for personal reminders. It is not a task list independent from reminders.
- The calendar page must display reminders according to the user's global default timezone.
- One-time reminders with trigger times are shown on the corresponding date and time.
- Shared reminders are shown on the corresponding date and time, with related friend identifiers.
- Recurring reminders show concrete occurrences in the currently visible time range. The user sees occurrences on the calendar, but the underlying reminder still belongs to the same recurring reminder series.
- When multiple reminders exist on the same day or at the same time, the calendar page may merge the display entry to avoid page overload.
- After entering a merged display entry, the user must be able to see each reminder and execute edit, complete, and delete actions separately.
- Reminders without trigger times are not forced onto a specific day. They should be shown as unscheduled reminders in the calendar page.
- Undelivered reminders must have clear status on the calendar page so the user knows the system already triggered them but did not successfully deliver them.
- The current top-level requirements do not specify whether the calendar page must use month view, week view, or day view. The core requirement is that the user can view and manage reminders in a calendar context.

Reminder calendar page creation and editing rules:

- The user can create reminders from the reminder calendar page.
- If the user creates a reminder from a specific date or time position on the calendar, the system defaults to using that date or time as the trigger time.
- The user can create reminders without trigger times in the unscheduled area of the reminder calendar page.
- The user can schedule trigger times for reminders without trigger times from the reminder calendar page.
- The user can edit ordinary personal reminder content, trigger time, and recurrence rules from the reminder calendar page.
- The user can reschedule shared reminders by changing trigger time and/or duration from supported shared-reminder flows. The user cannot directly edit shared reminder title or activity content from the reminder calendar page; to modify title or activity content, the user needs to cancel the entire shared reminder and create it again.
- After the user opens a specific recurring reminder occurrence from the calendar page, completion means completing this occurrence.
- After the user opens a specific recurring reminder occurrence from the calendar page, editing defaults to editing the entire recurring reminder series.
- After the user opens a specific recurring reminder occurrence from the calendar page, deletion means deleting the entire recurring reminder series.
- The current top-level requirements do not specify whether calendar-page creation or editing must use click, drag, modal, side panel, or any other specific page interaction form.

Reminder status and detail fields:

- Current user-visible states at least include future one-time reminders, reminders without trigger times, recurring reminder series, shared reminders, and undelivered reminders.
- Completed status does not enter the default view of the reminder calendar page.
- Deleted status is not retained as a user-visible state.
- Single-reminder details show at least content, trigger time or unscheduled time, time expression in the user's global default timezone, recurrence rule, and current status.
- Recurring reminder details must show the series rule and next trigger time.
- A recurring reminder occurrence on the calendar is only a visible instance of the series at a certain time point, not an independent reminder.
- Undelivered reminder details need to show the state that it has triggered but not been successfully delivered.
- The current top-level requirements do not require exposing internal retry counts, error codes, queue status, low-level delivery attempts, internal state-machine fields, or reminder internal IDs in the user interface.

Follow-up boundaries for creating reminders in conversation:

- When user intent is clear but necessary information is missing, the system should ask follow-up questions instead of guessing key content.
- Creating a timed reminder requires at least item content and trigger time.
- Creating or editing a calendar-visible timed reminder also requires that its duration interval does not overlap the same owner's existing calendar-visible active reminders or shared projections. If it overlaps, the system should explain the conflict and ask the user to pick another time instead of creating or updating the reminder.
- Creating a reminder without a trigger time only requires clear item content and does not require trigger time.
- Creating a recurring reminder requires at least item content, recurrence rule, and a trigger time or trigger window derivable from the rule.
- When the user only says vague messages such as "remind me", without item content, the system must not create a reminder and should ask what to remind them about.
- When the user gives an item but no time, the system can create a reminder without a trigger time and confirm that the reminder has no trigger time and will be summarized every night at 8 PM to ask for scheduling.
- For vague time expressions such as "remind me next week", if no specific date or time can be determined, the system should ask a follow-up question. If the user is actually expressing an unscheduled item, the system can create a reminder without a trigger time.
- Follow-up and confirmation replies should be generated by the Interaction LLM and accurately reflect whether the system has actually created the reminder.

Reminder operation confirmation replies:

- After the user creates, edits, completes, or deletes a reminder through conversation, the system should provide a text confirmation.
- Confirmation replies should be generated by the Interaction LLM rather than fixed templates.
- Confirmation content must include key information the user needs to check, such as reminder content, trigger time, recurrence rule, and whether there is no trigger time.
- For reminders without trigger times, the confirmation must clearly state that it has no trigger time yet and will be summarized every night at 8 PM to ask for scheduling.
- If creation, editing, completion, or deletion fails, or if a follow-up question is needed, the system must not provide a confirmation claiming the operation has been completed.

User reply semantics after reminders:

- After receiving a reminder, the user's subsequent reply can operate on the reminder based on the most recent reminder context.
- When the user replies with completion expressions such as "done" or "finished", the most recently triggered reminder should be completed.
- If the most recently triggered reminder is recurring, completion only completes this occurrence.
- If the same reminder message contains multiple reminders, the user's reply "done" means all items in that reminder message are completed.
- When the user replies with rescheduling expressions such as "remind me later", "change it to tomorrow", or "another time", if the new time is clear, the trigger time should be updated.
- If the user wants to reschedule but the new time is unclear, the system should ask a follow-up question.
- When the user replies with deletion expressions such as "no need to remind me" or "delete it", a one-time reminder deletes that reminder, while a recurring reminder deletes the entire series.
- When the user replies with ordinary chat or meaningless content, reminder status should not be automatically changed.

User reply semantics after reminders-without-trigger-time summaries:

- After receiving the daily 8 PM summary of reminders without trigger times, the user can schedule times for one or more reminders in the summary.
- When the user explicitly expresses batch scheduling, the system should set trigger times for the corresponding reminders in batch.
- If the user gives only one time while the summary contains multiple reminders and the target cannot be determined, the system should ask a follow-up question.
- The user can complete or delete a specific reminder in the summary.
- When the user says "all of these are done", the system should batch-complete the reminders in the summary.
- If the user does not reply, the reminders in the summary remain and will be summarized again at 8 PM the next day.
- If the user replies with ordinary chat or meaningless content, the system should not automatically change the status of these reminders.

Conversion between reminders without trigger times and reminders with trigger times:

- Once a reminder without a trigger time is scheduled with a trigger time, it becomes a reminder with a trigger time.
- If the user removes the trigger time from a reminder with a trigger time, it becomes a reminder without a trigger time.
- Conversion does not change reminder content, owner, or creation source.
- After conversion, the reminder should appear in the reminder calendar page according to its new state: either at the calendar position or in the unscheduled area.
- Recurring reminders must have derivable trigger rules.
- If the user removes the trigger time from a recurring reminder and the recurrence rule can no longer be maintained, the system should ask whether to convert it into a reminder without a trigger time or delete the entire recurring series.
- After conversion, the system must confirm to the user whether the reminder currently has a trigger time and whether it will still remind at a due time.

Proactive follow-up reminder:

- Proactive follow-up is an agent-created reminder.
- Proactive follow-up reminders are used by the assistant to proactively care about the user based on the user's goals, habits, tasks, or context.
- Proactive follow-up reminders do not require the user to explicitly create an ordinary reminder.
- The proactive switch's impact on proactive follow-up (turning off/on and whether untriggered items are canceled) is described in §5.11 Agent settings under "proactive switch" and is not repeated here.
- Proactive follow-up reminders are not shown on the reminder calendar page.
- Users cannot directly view, edit, or delete proactive follow-up reminders from the reminder calendar page.
- Users cannot directly modify proactive follow-up reminders.
- The trigger timing and frequency of proactive follow-up reminders are driven by the configured follow-up planning prompt/settings. The prompt decides whether and when to create, replace, or cancel proactive follow-up.
- The current requirements accept that proactive follow-up frequency is prompt-governed and not independently verifiable as a product target in this layer. The product contract is limited to proactive switch behavior, hidden-calendar behavior, text delivery through the current personal channel, and discard-on-failed-delivery behavior.
- Do-not-disturb or notification preference settings are not currently provided. Proactive follow-up's low-disturbance behavior is governed by proactive prompt/settings behavior.
- Proactive follow-up reminders can only send text messages through the currently connected personal channel.
- When the channel is unavailable, proactive follow-up reminders are not considered reached.
- Failed proactive follow-up reminder delivery is not resent. If the channel is unavailable or sending fails, that follow-up expires and is discarded; it does not enter undelivered resend and is not shown on the reminder calendar page.
- The top-level requirements do not specify concrete planning algorithms, concrete time intervals, concrete thresholds, or a separate frequency SLO.

Batch reminder operations:

- A single user message may contain multiple reminder operations.
- The system should support batch creation, editing, completion, and deletion of reminders.
- Batch operation confirmation replies should summarize successful items, failed items, and items needing follow-up.
- Batch operations are not required to be transactionally all-successful. When partial success occurs, the system must clearly tell the user which items succeeded and which did not.
- If one item needs a follow-up question, it should not block other items that can be clearly executed.
- Each sub-operation must still follow personal reminder contracts such as owner, time interpretation, global timezone, recurrence rules, delivery, and confirmation replies.

Matching ambiguity handling:

- The system can match reminders according to the user's description.
- If only one clear reminder is matched, the system may execute edit, complete, or delete and provide confirmation.
- If multiple candidate reminders are matched, the system must ask the user to clarify and choose.
- During clarification, enough distinguishing information should be shown, such as content, trigger time, recurrence rule, and whether it has no trigger time.
- Before the user confirms, the system must not delete, complete, or edit any candidate reminder.
- In batch operations, ambiguity in one item only blocks that item and does not block other items that can be clearly executed.

Creation-time duplicate/similar reminder handling:

- The system forbids creating completely identical actionable personal reminders.
- Definition of a completely identical personal reminder: same owner, same item/content, same trigger time; for reminders without trigger times, same owner, same item/content, and both have no trigger time.
- Duration, creation entry point, and natural-language expression are not part of the personal reminder duplication definition.
- If a completely identical actionable personal reminder already exists, the system should reject creation and tell the user that the reminder already exists.
- Similar but not completely identical reminders should not be hard rejected.
- The system allows multiple reminders with different content to have the same trigger time.
- Multiple reminders for the same owner at the same trigger time are merged into one reminder message when reminding, to avoid disturbing the user with multiple messages. Each reminder and its event remain independent.
- Current requirements do not require introducing complex similarity judgment for similar reminders.

Reminder triggering and delivery failure handling:

- When a reminder is due, it must form a reminder trigger event.
- If the user currently has a connected personal channel, the reminder trigger event enters the Interaction LLM and sends a text reminder through that channel.
- Currently an individual user can only have one reachable channel in personal WeChat or a shared WhatsApp channel.
- If the user has no usable channel, the system must not consider the reminder successfully delivered.
- If channel sending fails, the system must not consider the reminder successfully delivered.
- Undelivered reminder triggers must retain observable status.
- Reminders due while the channel is unavailable enter an undelivered state.
- After the user reconnects or relinks a personal channel, future reminders use the newly connected channel.
- After the user reconnects or relinks a personal channel, the system may resend undelivered reminders or show them as undelivered on the reminder calendar page.
- Resending undelivered reminders only applies to reminders that have already triggered but were not delivered.
- The resent content should let the user know this is a reminder that was not delivered earlier, not a new reminder.
- If multiple undelivered reminders are waiting to be resent, they may be merged into one text reminder.
- Completed or deleted reminders are not resent.
- If an undelivered reminder has already been handled by the user on the reminder calendar page, it is not resent again after reconnection.
- If a reminder's due moment is missed because the system itself was unavailable, the system must catch up the missed trigger when it recovers — delivering it late through a usable channel, or retaining an observable undelivered state — rather than silently dropping it. This catch-up applies to personal and shared reminders; missed proactive follow-ups are discarded per the proactive follow-up rules.
- The current product does not support immediately switching to another unlinked or unconfirmed channel because the current channel failed.
- The current top-level requirements do not specify concrete retry counts, expiration time, automatic resend strategy, or calendar-page-only display strategy.

Time interpretation and past-time handling:

- The system must determine whether the trigger time given by the user is already in the past.
- Relative time expressions should create reminders normally, such as "in 10 minutes" and "tomorrow at 9 AM".
- If the user gives a clear but already-past time, the system should not silently create a past reminder.
- For past times, the system should ask through the Interaction LLM or confirm a new future time.
- For incomplete date expressions that can be reasonably inferred, if the target time today has not passed, the system may treat it as today.
- For incomplete date expressions where the target time today has already passed, the system should ask or confirm and must not automatically change it to a future time.
- The system should not rewrite past times into future times by itself unless the Interaction LLM has confirmed this with the user.

Timezone interpretation rules:

- Reminder times are interpreted by default according to the user's global default timezone.
- The user can modify the global default timezone in the settings page and can also switch it globally through conversation.
- If the user explicitly mentions another timezone while creating or editing a reminder, the system should understand it as a global switch of the user's default timezone, or first confirm the global switch when the semantics may be misunderstood.
- Independent timezone per reminder is currently not supported.
- If the user has never set a timezone, the system may infer an initial global default timezone from account, channel, or region. All reminders still use the same global default timezone afterward.
- Switching the global default timezone should not silently rewrite existing reminders' absolute trigger moments. Existing reminders are only displayed in the new global default timezone.
- For recurring reminders, future occurrences are expanded using the timezone captured at creation or last edit; a global timezone switch does not recompute their windows or future trigger moments. The global timezone governs display and the timezone applied to newly created reminders.
- User-visible creation, editing, confirmation, and reminder copy must express time according to the user's global default timezone, and the same reminder time must not be interpreted differently across channels or assistant replies.
- Channel handling and assistant replies should not use different default timezones to interpret the same reminder time.

Recurring reminder rule constraints:

- Must support hourly, daily, weekly, monthly, and yearly recurrence.
- Must support custom interval recurrence, such as every 2 hours or every 3 days.
- The minimum interval for recurring reminders is hourly. Recurring reminders more frequent than once per hour are not supported.
- Recurring intervals shorter than one day must be constrained by a time window and must not default to triggering 24 hours a day without limit.
- Users may explicitly specify the trigger time window for recurrence intervals shorter than one day. If not specified, the system must use a default limited time window.
- The default limited time window is 8:00 to 23:00 every day.
- Repetition within a time window is a recurring reminder capability, such as "from X to Y, remind me every Z minutes/hours".
- Repetition within a time window must have a start time and end time.
- The interval for repetition within a time window must not be shorter than 1 hour.
- Repetition within a time window only triggers within the specified time window and optional weekdays.
- After each trigger, the system must advance the next valid trigger time.
- If the next trigger time is outside the valid time period, the system must advance to the next valid time period.
- Editing a recurring reminder defaults to editing the entire series and affects all future triggers.
- Editing only one occurrence of a recurring reminder is currently not supported.
- Completing a recurring reminder only completes this occurrence. Only deleting a recurring reminder deletes the entire series.
- Independent "skip" is currently not supported. Skipping this occurrence is equivalent to completing this occurrence and advancing to the next valid trigger.
- Fully stopping a recurring reminder means deleting the entire series.
- Multiple reminders under the same owner with the same trigger time are merged into one reminder message when reminding. Merging only affects the user-visible reminder method and does not change the independence, content, ownership, or subsequent state advancement of each reminder and event.
- Recurring reminders are active indefinitely by default until the user deletes the entire series or edits the rule to stop it.
- The system should not set a default maximum number of triggers for all recurring reminders.
- If the user explicitly provides an end condition, such as reminding for a fixed number of times, until a certain date, or only for the next few days, the system should include the end condition as part of the recurrence rule.
- A recurring reminder's local time window and rule are expanded using the timezone captured when the reminder was created or last edited. Switching the global default timezone only changes display and the timezone used for newly created reminders; it does not recompute the windows or future occurrences of existing recurring reminders. This keeps the "do not silently rewrite existing reminders" rule deterministic for windowed recurrences.

Requirement boundaries:

- The core contract of personal reminders is not "directly sending a fixed notification", but "after a reminder event triggers, it enters the Interaction LLM, and the role-based assistant reminds the user in text".
- The system can be responsible for time, state, and triggering. User-visible expression should be completed by the Interaction LLM.
- Reminder operation confirmation replies are also part of the user-visible contract. They should be generated by the Interaction LLM and accurately reflect whether the operation actually succeeded.
- Batch reminder operations are not a special entry point that bypasses validation. Each sub-operation must independently satisfy the personal reminder contract and express the real result in the summary confirmation.
- When editing, completing, or deleting reminders, matching ambiguity must be clarified with the user first. Before confirmation, no destructive or state-changing action may be executed on candidate reminders.
- Creating completely identical actionable personal reminders is forbidden. Similar but not completely identical reminders do not require complex similarity-based deduplication.
- Calendar-visible timed personal reminders must not overlap another calendar-visible active reminder or shared projection owned by the same user. Reminder-time merging is only for delivery presentation of already-valid reminders at the same trigger moment; it is not a way to bypass creation or edit conflict checks.
- Reminder triggering and reminder delivery are different states. Trigger success does not mean the user has received the reminder.
- No usable channel or sending failure must not be marked as successful delivery. An observable undelivered state must be left.
- Past-time and incomplete-date handling is a user intent confirmation issue. The system should not automatically rewrite times without confirmation.
- The system should rely on a unified user global timezone contract. Channels and the Interaction LLM should not infer different default timezones independently.
- Reminders without trigger times belong to the personal reminder journey but are not due-time reminders. Their user-visible reach-out is the daily 8 PM scheduling prompt.
- Scheduling prompts for reminders without trigger times should be summarized once per owner per day to avoid disturbance caused by individual messages.
- Recurring reminders are a type of reminder and are also part of the personal reminder core contract. The system must be able to advance the next trigger according to rules.
- Semantics for completing this occurrence / deleting the entire series / skip equivalent to completing this occurrence / editing the entire series / merging reminders at the same trigger time / forbidding completely identical reminders are described in "Recurring reminder rule constraints" and "Creation-time duplicate/similar reminder handling" and are not repeated here.
- The default reminder calendar page should focus on actionable states. Completed records or historical lists are not currently confirmed core requirements.
- Deleting a reminder is deletion from the current product state. Current requirements do not require retaining complex deletion history for legacy data compatibility or unconfirmed audit needs.
- Reminders must be owner-scoped and must not depend on the LLM guessing who the reminder belongs to.
- Duration is a reminder duration field, default 15 minutes, user-configurable. For personal reminders, it does not change whether or when the reminder triggers, nor completion or deletion. It is mainly used for display and for the receiver conflict time-window calculation in shared reminders.

### 5.9 Product Notification

Confirmed:

- Product notification is an independent requirement item, but this document defines it only from the product requirements perspective; technical architecture is out of scope.
- Currently only informational notifications and system notifications are sent.
- Product notification is not an approval flow, does not carry accept/reject, and does not directly execute actions.
- Product notification must cover friendship creation, shared reminder creation, shared reminder reschedule, shared reminder cancellation, and the errors, failures, partial failures, undelivered cases, conflicts, and cancellation failures related to these events.
- Ordinary reminders, shared reminders, and system notifications are not controlled by additional do-not-disturb or notification preference settings. There is currently no such user configuration.
- Notification facts must clearly express who did what, what the object is, when it happened, which timezone is used, and what the duration is.
- When an event includes an error, failure, or partial failure, the notification must include user-understandable error information.
- Notifications should not expose raw channel errors, internal error codes, queue status, delivery attempts, or internal state-machine fields.
- Final user-visible text is generated by the Interaction LLM based on structured facts and error facts.

User journey:

1. User A establishes active friendship with User B through a friend link or link code.
2. The system sends relevant users an informational notification stating that the friendship has been established.
3. User A creates a shared reminder involving User B and User C.
4. The system sends a creation confirmation to the creator and informational notifications to the receivers.
5. If creation fails, partially fails, encounters a receiver conflict, receiver channel unavailable state, or unresolvable receiver, the system sends the creator a system notification containing error information. If the current conversation is waiting for the result, it may also be presented as the final visible error reply.
6. Any participant reschedules a shared reminder.
7. The system sends informational notifications to other participants, stating who rescheduled which shared reminder and its updated time/duration.
8. Any participant cancels a shared reminder.
9. The system sends informational notifications to other participants, stating who canceled which shared reminder and that it will no longer trigger.
10. If reschedule or cancellation fails, or some participant does not receive the notification, the system provides the initiating user with user-understandable error information.

The system must support:

- Sending friendship creation notifications.
- Sending shared reminder creation notifications.
- Sending shared reminder reschedule notifications.
- Sending shared reminder cancellation notifications.
- Sending system notifications.
- Including actor, action, object, participants, time, timezone, duration, and status in notifications.
- Including user-understandable error information in failure, partial failure, undelivered, conflict, or cancellation failure cases.
- Mapping channel failures into product language, such as "the other party's channel is unavailable", "this time conflicts with the other party's existing schedule", or "reschedule/cancellation did not succeed".
- Having the Interaction LLM generate the final visible text based on structured notification facts and error facts.
- Avoiding turning notifications into approval, confirmation, accept/reject, or action execution entry points.

Requirement boundaries:

- The core contract of Product notification is factual notification and error notification, not workflow control.
- Product notification does not introduce new user notification preferences or do-not-disturb settings.
- Product notification must not replace user-understandable error information with internal errors or channel details.
- A shared reminder creation notification does not mean the receiver accepted an invitation. The shared reminder is already active after creation.
- A cancellation notification is not equivalent to completing a reminder. Canceling a shared reminder stops the associated projections for the entire group.

### 5.10 Calendar Import

Confirmed:

- Calendar import is a retained current product capability.
- Currently only one-time import is confirmed; continuous sync is not introduced.
- Calendar import only defines user requirements and field mapping. It does not choose a technical design.
- Users can authorize Google Calendar.
- The system can read calendar events from the authorized calendar.
- Future calendar events are imported as Coke reminders.
- Historical calendar events do not generate Coke reminders.
- Imported reminders belong to the current individual user.
- Calendar event title and description become reminder content.
- Calendar event start time becomes reminder trigger time.
- Calendar event duration becomes reminder duration. If the event has no duration, use the default 15 minutes.
- All-day calendar events are imported as Coke reminders triggered at 00:00 on the event date.
- Recurring calendar events are preferably imported as Coke recurring reminders.
- If a recurring calendar event cannot be reliably expressed using Coke's currently supported recurrence rules, the system should import it as one-time reminders for visible future occurrences.
- If a recurring calendar event is downgraded to one-time reminders, the import result should let the user know the recurrence rule was not preserved.
- When the same calendar event is imported repeatedly, the system directly skips it, does not create a duplicate reminder, and does not require user confirmation.
- After import completion, the system must report the import result to the user.
- The import result must include at least successfully imported count, skipped count, downgraded items, and failed items.
- Imported reminders follow the personal reminder rules for owner, global timezone, triggering, completion, deletion, undelivered handling, and calendar display.
- Users can stop or revoke Google Calendar authorization, or let authorization expire.
- Stopping, revocation, or expiration only affects future imports. Coke-owned reminders already imported continue to be managed according to personal reminder rules and are not automatically deleted.

User journey:

1. The user enters the calendar import entry point.
2. The system confirms that the current account/conversation is ready to receive import results.
3. The user authorizes Google Calendar.
4. The system reads calendar events within the user's authorized scope.
5. The system imports future calendar events one time as Coke reminders.
6. If a calendar event is an all-day event, the system imports it as a Coke reminder triggered at 00:00 on that event date.
7. If a calendar event is a recurrence that can be expressed, the system imports it as a Coke recurring reminder.
8. If a calendar event is a recurrence that cannot be reliably expressed, the system imports it as one-time reminders for visible future occurrences and explains this in the import result.
9. If a calendar event has already been imported, the system skips it directly, creates no duplicate reminder, and requires no user confirmation.
10. The system does not generate Coke reminders from historical calendar events.
11. The system shows the user an import result summary.
12. The user can view and manage imported reminders on the reminder calendar page.
13. The user can stop or revoke Google Calendar authorization.
14. After authorization is stopped, revoked, or expired, the user can no longer read new events from that authorization. Imported reminders remain in Coke and are managed by personal reminder rules.

The system must support:

- Google Calendar authorization entry point.
- One-time reading of calendar events.
- Converting only future calendar events into Coke reminders.
- Not generating reminders from historical calendar events.
- Mapping calendar event title and description to reminder content.
- Mapping calendar event start time to reminder trigger time.
- Mapping calendar event duration to reminder duration; if the event has no duration, use default 15 minutes.
- Mapping all-day calendar events to reminders triggered at 00:00 on that event date.
- Mapping recurring calendar events that can be reliably expressed to Coke recurring reminders.
- Mapping recurring calendar events that cannot be reliably expressed with current recurrence rules to one-time reminders for visible future occurrences.
- Explaining the import result to the user when a recurring calendar event did not preserve its recurrence rule.
- Identifying calendar events that have already been imported and skipping them on repeated imports.
- Not requiring user confirmation when repeated imports are skipped.
- Reporting an import result summary after import completion.
- Including successfully imported count in the import result summary.
- Including skipped count in the import result summary.
- Listing recurring calendar events that were downgraded to one-time reminders in the import result summary.
- Listing failed items in the import result summary.
- Setting the current individual user as owner for imported reminders.
- Displaying imported reminders on the reminder calendar page.
- Allowing the user to edit, complete, or delete imported reminders according to personal reminder rules.
- Allowing the user to stop or revoke Google Calendar authorization.
- Stopping future reads when Google Calendar authorization expires or is revoked.
- Ensuring stopping, revocation, or expiration does not delete imported Coke-owned reminders.

Currently not required:

- Continuous sync.
- Two-way sync.
- Writing user modifications to reminders in Coke back to Google Calendar.
- Importing historical calendar events as reminders.
- Overwriting or recreating reminders that were already imported when importing repeatedly.
- Automatically deleting imported reminders when Google Calendar authorization is revoked.

Requirement boundaries:

- Calendar import should not make Google Calendar the runtime source of truth for Coke reminders. After import, Coke reminders run according to the personal reminder contract.
- Continuous sync, complex sync states, conflict resolution, or two-way write-back contracts are not currently required.
- The Google Calendar authorization lifecycle only controls future read capability. It does not change the owner, triggering, completion, deletion, or display rules of imported Coke-owned reminders.

### 5.11 Agent Settings

Confirmed:

- Agent settings are used to configure the assistant's user-visible behavior and long-term preferences.
- Agent settings must be customer-scoped.
- Users can view, modify, and reset their Agent settings.
- Users can set the assistant name.
- Users can set how the assistant addresses them.
- Users can set persona.
- Users can set background information.
- Users can set speaking style.
- Users can set extra rules.
- The agent settings page shows the current personal channel connection status (connected / not connected / connection failed). This status is determined by the channel reachability journey and is not a freely configurable user field.
- Users can turn proactive off and back on.
- Users can turn memory off and back on.
- Resetting Agent settings restores default settings.

Proactive switch:

- After proactive is turned off, the system no longer creates new proactive follow-up reminders.
- When the user turns off proactive, the system should also cancel untriggered proactive follow-up reminders.
- Turning off proactive does not delete ordinary personal reminders and does not affect due-time reminders.
- Turning off proactive does not affect reminders-without-trigger-time summaries.
- Turning off proactive does not affect daily conversation replies.
- Turning off proactive does not affect Product notifications or system notifications.
- Turning proactive back on only affects whether new proactive follow-up reminders can be created in the future.
- Turning proactive back on does not restore follow-ups that were previously canceled.
- The proactive switch only controls proactive follow-up. It does not control user-explicitly-created reminders, reminders-without-trigger-time summaries, daily conversation replies, Product notifications, or system notifications.
- Do-not-disturb or notification preference settings are not currently provided.

Memory switch:

- The memory switch controls whether the system uses and updates long-term memory.
- After memory is turned off, the system no longer uses long-term memory.
- After memory is turned off, the system no longer adds long-term memory.
- After memory is turned off, the system no longer updates long-term memory.
- Turning off memory does not delete existing long-term memory.
- Turning off memory does not affect recent context needed to complete the current conversation.
- After memory is turned back on, the system can continue using existing long-term memory for future conversations, reminders, and proactive follow-ups, and can continue accumulating new long-term memory.
- User self-service clearing of long-term memory is currently not supported.

Requirement boundaries:

- Agent settings are user-understandable preference configurations and should not expand into a complex persona or policy platform.
- The memory switch should constrain the use, creation, and updating of long-term memory. It should not be interpreted as clearing all conversation history and does not provide a capability for clearing long-term memory.
- The proactive switch should constrain proactive follow-up reminders. It should not affect ordinary personal reminders, Product notifications, or system notifications.

### 5.12 Account/Data Lifecycle

Confirmed:

- The current product does not support user self-service account deletion.
- The current product does not support user self-service full account export or full erasure.
- The current product does not support user self-service clearing of long-term memory.
- Currently supported lifecycle actions are local actions: removing a removable personal channel, deleting or completing personal reminders, canceling shared reminders, removing friends, turning off memory usage, and stopping or revoking Google Calendar authorization.
- A messaging-first user cannot remove the only shared WhatsApp sender identity that anchors the account.
- The account remains the identity subject for channels, reminders, friendships, shared reminders, and settings.
- Local lifecycle actions cannot be interpreted as deleting the account itself.

User journey:

1. The user removes a removable personal channel on the channel management page.
2. The system stops reaching the user through that channel, but does not delete the account, reminders, friendships, or settings.
3. The user deletes or completes personal reminders on the reminder calendar page.
4. The system only changes the product state of the corresponding reminders and does not delete the user account.
5. The user cancels a shared reminder.
6. The system cancels the entire group shared reminder, stops all participant projections, and notifies other participants.
7. The user removes a friend on the friends page.
8. The system removes active friendship. This action does not delete accounts, does not delete personal reminders, and does not automatically cancel existing active shared reminders.
9. The user turns off memory.
10. The system stops using, adding, and updating long-term memory, but does not delete existing long-term memory.
11. The user stops or revokes Google Calendar authorization.
12. The system stops future Google Calendar reads. Imported Coke-owned reminders continue to be managed according to personal reminder rules.

The system must support:

- Removing a removable personal channel.
- Preventing removal of the only shared WhatsApp sender identity that anchors a messaging-first account.
- Deleting a personal reminder.
- Completing a personal reminder.
- Canceling a shared reminder.
- Removing a friend.
- Turning memory usage off and back on.
- Stopping or revoking Google Calendar authorization.
- Providing accurate user-visible results after these local lifecycle actions complete.
- Providing user-understandable error information when a local lifecycle action fails.

Currently not required:

- User self-service account deletion.
- User self-service full account export.
- User self-service full data erasure.
- User self-service clearing of long-term memory.
- When the user deletes imported reminders from Coke, synchronously deleting the original Google Calendar events.

Requirement boundaries:

- The current contract of account/data lifecycle is local management actions, not a complete privacy data management platform.
- Removing a removable channel only affects future reachability paths and does not change reminder ownership.
- Messaging-first account-anchor channel removal is not supported under the current product contract.
- Deleting or completing a reminder only affects the corresponding reminder and does not affect account or friendship.
- Canceling a shared reminder affects the entire group shared reminder and is not equivalent to removing a friend.
- Removing a friend does not automatically cancel existing shared reminders.
- Turning off memory only affects the use, creation, and updating of long-term memory; it does not delete existing long-term memory.
- Stopping or revoking Google Calendar authorization only affects future imports and does not delete imported Coke-owned reminders.

### 5.13 Account Identity and Web Claim

Confirmed:

- A Coke user has one of two origins: web-first (email registration/login per §5.1), or messaging-first (auto-provisioned only on first contact through shared WhatsApp, bound to the sender's channel identity).
- Auto-provisioning currently applies only to shared WhatsApp. A first-seen shared WhatsApp sender identity provisions a new Coke user; a known shared WhatsApp sender identity continues as its existing Coke user. Personal WeChat remains a web-first channel-connection path unless a later current requirement explicitly changes it.
- A messaging-first account has no password. Its only web authentication path is a one-time login claim. A web-first account uses email and password (and forgot/reset per §5.1). The two credential types do not cross.
- Each Coke user may have at most one usable personal channel at a time, so each messaging identity corresponds to its own Coke user. The system does not merge separate accounts and does not provide account unlinking.
- A messaging-first user cannot remove the only shared WhatsApp sender identity that anchors the account. The known-sender continuation rule depends on this identity remaining valid.
- If the same human uses two different auto-provisioned sender identities, each channel identity becomes its own separate Coke user. This is an accepted product outcome, not a defect; the system does not merge them.
- A messaging user reaches an authenticated web session by claiming their existing account; no second account is created for them. One human who consistently uses the claim path keeps a single Coke user.
- Claiming is bidirectional:
  - Chat-initiated: when the user needs a web-only action (for example calendar import), the assistant issues a one-time, time-limited, single-use login URL in the conversation; opening it authenticates the web session as that account.
  - Web-initiated: when the user is on a web page that needs authentication (for example a friend link), the page shows a one-time code; the user sends that code to the messaging channel; the page then authenticates the web session as that account.
- The login URL and the web-initiated code are one-time, time-limited, single-use, and bound to exactly one account.
- During a web-first user's channel-connection flow, an inbound message from a new channel identity that carries a valid pending pairing code binds that channel identity to the account that issued the code, instead of auto-provisioning a new account.
- If a messaging-first user instead registers a fresh email account on the web, that is a separate account; the system does not merge it with the messaging account. Web entry points must surface the claim path so messaging users authenticate as their existing account rather than registering a new one.

User journey (messaging-first user reaching web):

1. A human first contacts shared WhatsApp and is auto-provisioned a Coke user bound to their channel identity.
2. The user later needs a web-only surface — opening a friend link, importing a calendar, or using a web page.
3. If the user triggered the need in conversation, the assistant issues a one-time login URL; opening it authenticates the web session as that account.
4. If the user is already on a web page, the page shows a one-time code; the user sends it to the messaging channel; the page then authenticates the web session as that account.
5. The authenticated web session acts as the same single Coke user, with the same reminders, friendships, shared reminders, memory, and settings.
6. The system never requires the messaging user to register a separate account to reach the web.

User journey (web-first user connecting a channel):

1. A human registers and logs in on the web with email and password.
2. The user starts the channel-connection flow and receives a pairing code.
3. The user sends the pairing code from their own messaging identity to the channel.
4. The inbound carrying the valid pairing code binds that channel identity to the web account, instead of auto-provisioning a new account.
5. From then on, inbound from that channel identity is associated with the same single Coke user.

The system must support:

- Auto-provisioning a Coke user on first contact through shared WhatsApp, bound to the sender identity.
- Continuing a known shared WhatsApp sender identity as its existing Coke user.
- Issuing and validating a one-time, time-limited, single-use chat-initiated login URL that authenticates a web session as the issuing account.
- Issuing and validating a one-time, time-limited, single-use web-initiated code that, when sent to the messaging channel, authenticates the web session as that account.
- Binding a new channel identity to an existing web account when the inbound carries a valid pending pairing code, instead of auto-provisioning.
- Surfacing the claim path on web entry points so messaging users authenticate as their existing account.

Currently not required:

- Account merging between separate web-first and messaging-first accounts.
- Account unlinking or splitting.
- Passwords for messaging-first accounts.
- Messaging-first auto-provisioning for personal WeChat.
- Removing the only shared WhatsApp sender identity that anchors a messaging-first account.
- Heuristic or silent identity matching based on display name, profile similarity, or guessed identity.
- More than one usable personal channel per Coke user.

Requirement boundaries:

- Identity reconciliation across surfaces is claim-based, not merge-based: a messaging user authenticates as their existing account rather than creating and later merging a second one.
- Each Coke user honors the single-personal-channel and single-global-timezone contracts; one messaging identity maps to one Coke user.
- For a messaging-first account, the sender identity is the account anchor and is not removable while it is the only channel identity for that account.
- Login URLs, web-initiated claim codes, and channel pairing codes are authentication artifacts: one-time, time-limited, single-use, and never reusable to access a different account.
