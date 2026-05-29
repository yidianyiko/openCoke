# Data Retention Policy

This document defines clean-rebuild retention policy identifiers used by
ownership-system docs. Durations are product defaults and do not replace
customer-specific legal requirements.

The clean rebuild stores durable state in Postgres and coordination state in
Redis. Mongo is not part of the retention model.

| Policy | Duration | Cleanup owner | Evidence required |
| --- | --- | --- | --- |
| `identity_access_retention` | account lifetime plus 30 days | IdentityAccess | account ids, access rows, credential/session/auth artifact count |
| `auth_artifact_retention` | 14 days after expiry or consumption | IdentityAccess | artifact count by type and terminal state |
| `channel_reachability_retention` | account lifetime plus 30 days | ChannelReachability | channel ids, delivery route ids, delivery attempt cutoff |
| `conversation_retention` | 180 days | ConversationRuntime | message and turn count by owner and cutoff |
| `turn_trace_retention` | 90 days | ConversationRuntime | turn/disposition count and trace cutoff |
| `reminder_retention` | account lifetime plus 30 days | Reminder | reminder and fire count by owner and lifecycle |
| `undelivered_reminder_retention` | 90 days after terminal handling | Reminder | undelivered fire count by terminal state |
| `calendar_import_retention` | 365 days | CalendarImport | import run and import item count by cutoff |
| `friendship_retention` | account lifetime plus 30 days | SocialScheduling | friendship count by status and owner pair |
| `friend_link_retention` | 30 days after disabled or rotated link expiry | SocialScheduling | link count by terminal state |
| `shared_reminder_retention` | account lifetime plus 30 days | SocialScheduling | shared reminder and projection count by status |
| `product_notification_retention` | 90 days after delivered or failed recipient state | SocialScheduling | notification fact and recipient count by delivery state |
| `agno_memory_retention` | account lifetime plus 30 days | ConversationRuntime | Agno memory/history/knowledge count by owner |
| `ephemeral_runtime_retention` | 7 days | ConversationRuntime | Redis lock/pubsub/stream trim evidence |
| `outbox_retention` | 30 days after durable worker ack | ConversationRuntime | outbox row count by processed cutoff |

## Rule

Any plan that introduces deletion behavior must include a dry-run command, a
non-dry-run command, and evidence output under `artifacts/evidence/`.
