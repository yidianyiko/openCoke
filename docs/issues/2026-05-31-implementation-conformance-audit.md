---
kind: active_issue
status: open
created: 2026-05-31
area: clean-rebuild
branch: audit/impl-conformance
---

# Implementation Conformance Audit

## Scope

Static/local audit of the clean Coke rebuild against:

- `docs/superpowers/specs/2026-05-28-coke-requirements-user-journey-matrix-design.md`
- `docs/superpowers/specs/2026-05-28-coke-clean-rebuild-target-architecture-design.md`
- `docs/ARCHITECTURE.md`
- `docs/product-specs/FEATURE_TREE.md`

Inspected surfaces: `coke/` domains, `turn/`, `providers/`, `api/`, `worker/`, `scheduler/`, `composition.py`, `schema.py`, `migrations/`, and `web/`.

No runtime deploy, GCP stack access, SSH, or Docker was used.

## Summary Counts

Coverage matrix rows: 34 total.

| Status | Count |
|---|---:|
| IMPLEMENTED | 2 |
| PARTIAL | 25 |
| MISSING | 2 |
| DIVERGENT | 5 |

Priority gap counts: P0 = 4, P1 = 8, P2 = 2.

## Requirement Coverage

| Requirement / Journey | Status | Evidence / Gap IDs |
|---|---|---|
| Account access status and public explanation | PARTIAL | Inbound and channel actions call access checks (`coke/turn/runner.py:97`, `coke/composition.py:237`, `coke/domains/channel_reachability/service.py:519`), but calendar import is not account-access gated: G-005. |
| First activation | IMPLEMENTED | Activation completion requires identity, usable channel, and first inbound (`coke/domains/identity_access/service.py:755`). Tests cover web-first and messaging-first activation (`tests/unit/coke/identity_access/test_identity_access_service.py:1065`). |
| User timezone | PARTIAL | Accounts carry one `default_timezone` (`coke/schema.py:41`), and reminders store `captured_timezone` (`coke/schema.py:356`), but there is no settings/profile API or conversation operation for global timezone switch: G-006. |
| Trusted inbound message receiving | PARTIAL | Provider webhooks bind account and enqueue inbound (`coke/api/provider_webhooks.py:56`), but channel-carried media is not normalized/passed: G-011. |
| Message sending and outbound delivery | PARTIAL | Delivery attempts are persisted (`coke/domains/channel_reachability/service.py:380`), but delivery outcomes are not propagated to reminder/proactive/notification lifecycle: G-003. |
| Conversation ordering and stale-reply safety | DIVERGENT | Outbound reply freshness exists (`coke/turn/runner.py:405`), but state-changing domain commits are not atomically version-gated: G-002. |
| Conversation generation and segmented visible output | PARTIAL | Output protocol records 1-3 segments (`coke/domains/conversation_runtime/service.py:159`), but replay and delivery lifecycle are incomplete: G-001, G-003. |
| Reply necessity and intentional no-reply | PARTIAL | Semantic interpreter supports no-reply (`coke/llm/semantic_interpreter.py:15`), and TurnRunner records it (`coke/turn/runner.py:134`), but internal reply-wait API is missing: G-007. |
| Conversation history and user memory | PARTIAL | Agno memory can be disabled from trusted facts (`coke/llm/agno_interaction_agent.py:91`), but trusted facts hard-code `memory_enabled=True` (`coke/composition.py:255`) and settings are missing: G-006. |
| Reminder recognition and personal reminder CRUD | PARTIAL | CRUD operations exist in service/routes/tools (`coke/domains/reminder/service.py:46`, `coke/api/reminder_routes.py:17`, `coke/composition.py:277`), but replay idempotency, atomic freshness, reference resolution, and outbox evidence are incomplete: G-001, G-002, G-004, G-008. |
| Reminder triggering and recurring reminders | PARTIAL | Scheduler groups due fires (`coke/scheduler/__main__.py:162`) and recurrence uses captured timezone (`coke/domains/reminder/recurrence.py:20`), but delivery lifecycle/resend is incomplete: G-003, G-009. |
| Summary prompt for no-trigger-time reminders | PARTIAL | Scheduler enqueues 20:00 local summaries (`coke/scheduler/__main__.py:186`), but focus subject and post-summary batch semantics are not durable: G-008. |
| Proactive follow-up reminder | PARTIAL | Proactive reminders are hidden/user-immutable (`coke/domains/reminder/service.py:187`, `coke/domains/reminder/service.py:456`), but settings and failed-delivery discard wiring are incomplete: G-003, G-006. |
| Product notification | PARTIAL | Structured notification facts and recipients exist (`coke/domains/social_scheduling/notifications.py:47`), but per-recipient delivery/fanout is not wired: G-003. |
| Calendar import | PARTIAL | Occurrence dedupe, historical skip, downgrade, and result counts exist (`coke/domains/calendar_import/service.py:348`, `coke/domains/calendar_import/service.py:374`, `coke/domains/calendar_import/service.py:579`), but authorization and account access fail open: G-005. |
| Agent settings configuration | MISSING | Tables exist (`coke/schema.py:57`), web uses old `/api/customer/agent-instance` (`web/lib/customer-agent-instance.ts:77`), and no Python `/api/settings/*` route is registered: G-006, G-007. |
| User profile / relationship updates | MISSING | `user_profile` table exists (`coke/schema.py:75`), but no Python domain service, API, or tool updates it: G-006. |
| Friendship | PARTIAL | Link/code create/join/remove exist (`coke/api/friend_routes.py:15`, `coke/api/friend_routes.py:38`), but deferred self-completion is manual/not automatic on channel connect: G-010. |
| Shared reminders | PARTIAL | Required-field follow-up, conflict/reachability checks, available participant breakdown, projections, and cancellation exist (`coke/domains/social_scheduling/service.py:174`, `coke/domains/social_scheduling/service.py:260`, `coke/domains/social_scheduling/service.py:264`, `coke/domains/social_scheduling/service.py:317`), but focus/replay/delivery lifecycle gaps remain: G-001, G-003, G-008. |
| Personal channel delivery | PARTIAL | Single product channel types are enforced (`coke/domains/channel_reachability/models.py:20`, `coke/domains/channel_reachability/service.py:201`), but delivery results are not reflected back into output-class state: G-003. |
| Account identity and web claim | PARTIAL | Backend implements login URL, claim code, and pairing code (`coke/domains/identity_access/service.py:266`, `coke/domains/identity_access/service.py:287`, `coke/domains/identity_access/service.py:380`), but web/route paths still target unmatched old APIs: G-007. |
| Account/data lifecycle | PARTIAL | Channel removal, reminder delete/complete, friend removal, shared cancellation, and calendar revoke exist (`coke/api/channel_routes.py:79`, `coke/api/reminder_routes.py:66`, `coke/api/friend_routes.py:96`, `coke/api/shared_reminder_routes.py:89`, `coke/api/calendar_import_routes.py:44`), but memory switch and delivery/replay lifecycle are incomplete: G-003, G-006. |

## Architecture Invariant Coverage

| Invariant | Status | Evidence / Gap IDs |
|---|---|---|
| Exactly one Interaction Agent prose producer | PARTIAL | Render mode has no tools (`coke/turn/context.py:62`), but delivery callbacks/internal routes are absent, so output-class state cannot complete the prose-to-delivery chain: G-003, G-007. |
| Access gate fail-closed | PARTIAL | Inbound/channel enforce access, calendar import does not: G-005. |
| Single transactional outbox | PARTIAL | Inbound and notification facts append outbox (`coke/domains/conversation_runtime/repository.py:319`, `coke/domains/social_scheduling/repository.py:761`), but personal reminder lifecycle writes do not: G-004. |
| Worker-turn replay idempotency | DIVERGENT | `start_turn` returns replayed existing turns (`coke/domains/conversation_runtime/service.py:136`), but runners ignore `replayed` and can invoke the agent again: G-001. |
| Freshness expected-version on every state-changing commit | DIVERGENT | Tool adapters call a guard before dispatch (`coke/composition.py:272`, `coke/composition.py:387`), but domain writes are not atomically guarded: G-002. |
| Disposition and delivery state remain separate | DIVERGENT | Disposition is recorded, but delivery attempt results are discarded by the Turn delivery adapter: G-003. |
| Reminder execution | PARTIAL | Due/catch-up/summary scans exist (`coke/scheduler/__main__.py:25`), but undelivered/proactive lifecycle and Focus subject are incomplete: G-003, G-008, G-009. |
| Social Scheduling | PARTIAL | Core service invariants are implemented, but notification delivery and deferred friend-link completion are incomplete: G-003, G-010. |
| Notification facts and per-recipient state | PARTIAL | Rows are written, but recipient state is never updated by worker/delivery paths: G-003. |
| Web thin client over Python API | DIVERGENT | Feature tree says Python `/api/settings/*`, `/api/subscription/*`, `/api/claim/*`, but web calls old `/api/customer/*` and unmatched auth-claim paths: G-007. |
| Schema/table ownership | PARTIAL | Defined tables map to modules, but some schema is unused and SocialScheduling writes `reminder` rows directly: G-006, G-014. |
| No legacy imports, keyword routing, or fallback prose | IMPLEMENTED | Production search found no `pymongo`, `memo_runtime`, or keyword router implementation; prompt/runtime text explicitly forbids keyword routing and fallback prose (`coke/llm/semantic_interpreter.py:75`, `coke/llm/agno_interaction_agent.py:163`). |

## Prioritized Gaps

| ID | Pri | Status | Contract Violated | Evidence |
|---|---|---|---|---|
| G-001 | P0 | DIVERGENT | Same-trigger replay must reconcile the existing turn and never duplicate user-visible work. Target §5 says worker replay resumes/reconciles and domain commands are idempotent by `turn_id + item_index` (`docs/superpowers/specs/2026-05-28-coke-clean-rebuild-target-architecture-design.md:551`). | `ConversationRuntimeService.start_turn` returns `replayed=True` for an existing trigger (`coke/domains/conversation_runtime/service.py:136`), but `TurnRunner.run_inbound_turn` continues to invoke the agent after `start_turn` without checking `start.replayed` (`coke/turn/runner.py:102`, `coke/turn/runner.py:164`), and render turns do the same (`coke/turn/runner.py:244`, `coke/turn/runner.py:277`). Tool ports accept only `(command, guard)` (`coke/turn/agent.py:16`) and `ReminderBatchItem` has no turn/item idempotency fields (`coke/domains/reminder/models.py:71`). |
| G-002 | P0 | DIVERGENT | Every interactive state-changing domain commit must atomically check `based_on_inbound_seq`. Target §4 requires an expected-version precondition at commit, not only before send (`docs/superpowers/specs/2026-05-28-coke-clean-rebuild-target-architecture-design.md:420`). | Tool adapters call `_guard_state_change` before dispatch (`coke/composition.py:272`, `coke/composition.py:387`, `coke/composition.py:527`, `coke/composition.py:581`), but services save directly afterward (`coke/domains/reminder/service.py:91`, `coke/domains/reminder/service.py:141`, `coke/domains/reminder/service.py:174`, `coke/domains/reminder/service.py:205`, `coke/domains/reminder/service.py:461`). The Postgres reminder repository updates only `reminder` rows and unique constraints, with no conversation expected-version condition (`coke/domains/reminder/repository.py:174`, `coke/domains/reminder/repository.py:187`). |
| G-003 | P0 | PARTIAL | Delivery state must update output-class lifecycle: reminder undelivered, proactive discard, per-projection delivery, and per-recipient notification partial failure. Requirements §5.8 and target §8 require failed sends to remain undelivered or discarded (`docs/superpowers/specs/2026-05-28-coke-requirements-user-journey-matrix-design.md:873`, `docs/superpowers/specs/2026-05-28-coke-clean-rebuild-target-architecture-design.md:700`, `docs/superpowers/specs/2026-05-28-coke-clean-rebuild-target-architecture-design.md:809`). | `ChannelReachabilityService.send_text` returns a persisted `DeliveryAttempt` (`coke/domains/channel_reachability/service.py:380`), but `ChannelReachabilityOutboundDelivery.deliver` discards it (`coke/composition.py:177`), `OutboundDeliveryPort.deliver` returns `None` (`coke/turn/runner.py:27`), and `TurnRunner` calls delivery without recording output-class results (`coke/turn/runner.py:414`). `SocialSchedulingService.record_notification_delivery` exists (`coke/domains/social_scheduling/service.py:416`) but worker topics only render notification turns (`coke/worker/__main__.py:96`) and no delivery callback route is registered (`coke/app.py:44`). |
| G-004 | P0 | PARTIAL | Atomic domain write + outbox. Target §5 requires every producer to append outbox in the same transaction as the domain write, including personal reminder creation/lifecycle updates (`docs/superpowers/specs/2026-05-28-coke-clean-rebuild-target-architecture-design.md:582`). | Inbound uses message + outbox transaction (`coke/domains/conversation_runtime/repository.py:319`), and notification facts insert an outbox row (`coke/domains/social_scheduling/repository.py:761`). Personal reminder create/update/delete writes only `reminder`/`reminder_fire` rows (`coke/domains/reminder/repository.py:174`, `coke/domains/reminder/repository.py:238`, `coke/domains/reminder/repository.py:250`); there is no outbox append in `ReminderService._create`, `complete_reminder`, `delete_reminder`, `schedule_unscheduled`, or `reschedule_reminder` (`coke/domains/reminder/service.py:91`, `coke/domains/reminder/service.py:191`, `coke/domains/reminder/service.py:204`, `coke/domains/reminder/service.py:461`). |
| G-005 | P1 | PARTIAL | Account access gate must fail closed for calendar import; Google import must require authorized access. Requirements §3 and §5.10 require import readiness and account access before import (`docs/superpowers/specs/2026-05-28-coke-requirements-user-journey-matrix-design.md:80`, `docs/superpowers/specs/2026-05-28-coke-requirements-user-journey-matrix-design.md:1034`). | IdentityAccess exposes `check_access_for_action(..., "calendar_import")` (`coke/domains/identity_access/service.py:140`), but `CalendarImportService` has no IdentityAccess dependency (`coke/domains/calendar_import/service.py:262`) and `import_google_calendar` only calls `_require_active_authorization` (`coke/domains/calendar_import/service.py:290`). `_require_active_authorization` allows a missing authorization state and blocks only present stopped/revoked/expired states (`coke/domains/calendar_import/service.py:554`). The API route accepts raw `account_id`/`auth_handle` from the body (`coke/api/calendar_import_routes.py:21`). |
| G-006 | P1 | MISSING | Agent settings, user profile, global timezone switch, proactive switch, and memory switch must be customer-scoped, view/update/reset capable, and control runtime behavior. Requirements §5.11 require these settings (`docs/superpowers/specs/2026-05-28-coke-requirements-user-journey-matrix-design.md:1091`). | Schema defines `agent_settings` and `user_profile` (`coke/schema.py:57`, `coke/schema.py:75`), but no Python settings/profile domain or `/api/settings/*` route is registered (`coke/app.py:44`). Trusted facts hard-code `memory_enabled=True` (`coke/composition.py:255`), while Agno honors that flag (`coke/llm/agno_interaction_agent.py:91`). Web settings still call `/api/customer/agent-instance` (`web/lib/customer-agent-instance.ts:77`) and do not map to the clean schema. |
| G-007 | P1 | DIVERGENT | Feature-tree API/web/internal route parity and thin Next.js client over Python API. Feature tree lists `/api/account/*`, `/api/settings/*`, `/api/subscription/*`, `/internal/outbound/delivery-callback`, and `/internal/reply-wait/:causal_inbound_event_id` (`docs/product-specs/FEATURE_TREE.md:44`). Target §13 says web remains thin over Python API (`docs/superpowers/specs/2026-05-28-coke-clean-rebuild-target-architecture-design.md:885`). | `app.py` registers auth, claim, channels, reminders, friends, shared reminders, calendar import, provider webhooks, and health only (`coke/app.py:44`). No Python `account`, `settings`, `subscription`, or `internal` blueprint exists. Web calls old/unmatched paths such as `/api/customer/subscription` (`web/app/(customer)/account/subscription/page.tsx:86`), `/api/customer/google-calendar-import/preflight` (`web/lib/customer-google-calendar-import.ts:55`), `/api/customer/agent-instance` (`web/lib/customer-agent-instance.ts:77`), and `/api/auth/claim` (`web/app/(customer)/auth/claim/page.tsx:53`). |
| G-008 | P1 | PARTIAL | Focus and ReferenceResolver must make post-reminder "done", summary batch actions, shared cancellation ambiguity, and reminder edit/delete ambiguity safe before mutation. Target §4 requires durable `message_subject` and per-reference clarification (`docs/superpowers/specs/2026-05-28-coke-clean-rebuild-target-architecture-design.md:394`, `docs/superpowers/specs/2026-05-28-coke-clean-rebuild-target-architecture-design.md:402`); requirements §5.8 require grouped "done" semantics (`docs/superpowers/specs/2026-05-28-coke-requirements-user-journey-matrix-design.md:796`). | `FocusResolver` returns `None` without an injected repository (`coke/turn/focus.py:20`) and there is no `message_subject` schema/table or production repository (`coke/turn/focus.py:14`). `ReferenceResolver` is a generic scaffold (`coke/turn/reference_resolver.py:52`), but `TurnRunner` always calls `resolve_all([])` (`coke/turn/runner.py:151`), so no natural-language reference is resolved before the agent calls tools. |
| G-009 | P1 | PARTIAL | Undelivered reminder resend after reconnect must re-render pending undelivered reminders or expose them as undelivered. Target §8 requires an `UndeliveredResendTurn` on channel reconnect (`docs/superpowers/specs/2026-05-28-coke-clean-rebuild-target-architecture-design.md:700`). | `ReminderService.undelivered_resend_turn` builds a trigger payload (`coke/domains/reminder/service.py:323`), but `ChannelReachabilityService.mark_connected` only marks the channel and observes activation (`coke/domains/channel_reachability/service.py:234`), and worker topics do not include any undelivered-resend topic (`coke/worker/__main__.py:96`). |
| G-010 | P1 | PARTIAL | Deferred friend-link self-completion must automatically establish friendship once the joiner connects a usable channel. Target §9 requires deferred self-completion on channel connect (`docs/superpowers/specs/2026-05-28-coke-clean-rebuild-target-architecture-design.md:760`). | SocialScheduling returns `deferred_channel_required` with `friend_link_id` continuation (`coke/domains/social_scheduling/service.py:444`), and a manual `/api/friends/complete-deferred` endpoint exists (`coke/api/friend_routes.py:72`). Channel connection does not consume the continuation or call `complete_deferred_friend_link` (`coke/domains/channel_reachability/service.py:226`), and the agent tool surface does not expose `complete_deferred_friend_link` (`coke/composition.py:356`). |
| G-011 | P1 | PARTIAL | Channel-carried media must be preserved as processable inbound input. Requirements §3 include text/images/voice/etc. (`docs/superpowers/specs/2026-05-28-coke-requirements-user-journey-matrix-design.md:83`), and target §3.3 names `inbound_media` (`docs/superpowers/specs/2026-05-28-coke-clean-rebuild-target-architecture-design.md:253`). | `ConversationRuntimeService.record_inbound` can preserve `media` when passed (`coke/domains/conversation_runtime/service.py:81`), but `NormalizedInbound` has no media field (`coke/domains/channel_reachability/models.py:105`) and provider webhooks call `record_inbound` without `media` (`coke/api/provider_webhooks.py:58`). |
| G-012 | P1 | PARTIAL | Agent-callable tool surface is incomplete for current requirements. Interactive mode must expose reminder CRUD, social scheduling, settings, identity/claim, and calendar import (`docs/superpowers/specs/2026-05-28-coke-clean-rebuild-target-architecture-design.md:120`). | Tool names are only reminder, social_scheduling, calendar_import, and identity_access (`coke/turn/context.py:13`). The Interaction Agent instructions mention settings work (`coke/llm/agno_interaction_agent.py:172`), but no settings tool exists. Implemented domain operations such as `complete_deferred_friend_link` and `record_notification_delivery` are not reachable from the relevant worker/tool paths (`coke/domains/social_scheduling/service.py:138`, `coke/domains/social_scheduling/service.py:416`, `coke/composition.py:356`). |
| G-013 | P2 | PARTIAL | Retained provider webhook discoverability. Feature tree lists ecloud and linq provider webhooks (`docs/product-specs/FEATURE_TREE.md:57`), while the architecture says retained provider adapters include `wechat_ecloud` and `linq` (`docs/ARCHITECTURE.md:145`). | The routes exist (`coke/api/provider_webhooks.py:35`, `coke/api/provider_webhooks.py:39`), but `_handle_inbound` rejects any provider outside current product channels before normalization (`coke/api/provider_webhooks.py:47`). This may be intentional because current product channels are only personal WeChat and shared WhatsApp, but the route contract should be clarified. |
| G-014 | P2 | PARTIAL | Bounded-context table ownership needs cleanup or documentation for shared projections. Target §3 says each module owns its tables and adapters must not write another module's tables (`docs/superpowers/specs/2026-05-28-coke-clean-rebuild-target-architecture-design.md:175`). | SocialScheduling repository inserts a `reminder` row directly when adding a projection (`coke/domains/social_scheduling/repository.py:654`), even though Reminder owns `reminder` (`docs/superpowers/specs/2026-05-28-coke-clean-rebuild-target-architecture-design.md:261`). If shared projections are intended to be SocialScheduling-owned writes into the Reminder table, the architecture doc should say so explicitly. |

## Schema Usage Notes

- `agent_settings` and `user_profile` are schema-only for the clean Python backend: defined in `coke/schema.py:57` and `coke/schema.py:75`, but no domain service/API/tool consumes them.
- `delivery_attempt` rows are written by ChannelReachability (`coke/domains/channel_reachability/service.py:380`), but no output-class lifecycle consumes the result.
- `notification_recipient` rows are inserted (`coke/domains/social_scheduling/notifications.py:82`) but remain pending unless `record_notification_delivery` is called; no production worker/delivery path calls it.
- `inbound_media` persistence exists in ConversationRuntime (`coke/domains/conversation_runtime/service.py:81`) but provider normalization currently cannot populate it.
- Reminder duplicate constraints are enforced in schema and repository (`coke/schema.py:542`, `coke/domains/reminder/repository.py:174`).
- Shared reminder duplicate constraints and available-participant breakdown are implemented (`coke/schema.py:578`, `coke/domains/social_scheduling/service.py:260`).
- Calendar occurrence-grain dedupe is implemented (`coke/schema.py:525`, `coke/domains/calendar_import/service.py:348`).

## Safe Fix Decision

No safe isolated code fix was made in this audit worktree.

Reason: the confirmed gaps either touch active/concurrent areas (`coke/turn/runner.py`, `coke/llm/*`, `coke/domains/reminder/service.py`, web channel/customer surfaces), require cross-domain architecture changes, or need new API/service contracts. Applying a small one-off change would risk masking the contract problem without making the runtime conformant.

## Verification Notes

Commands run during audit:

```bash
git status --short --branch
rg --files coke migrations web tests/unit/coke
rg -n "NotImplemented|TODO|FIXME|pass$|placeholder|pymongo|dao|connector|gateway|memo_runtime|fallback|regex|keyword" coke migrations web tests/unit/coke
```

Final verification:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke -q
```

Result: `429 passed in 11.53s`.

Whitespace check: `git diff --check` passed.
