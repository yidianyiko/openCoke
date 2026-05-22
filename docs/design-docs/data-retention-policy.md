# Data Retention Policy

This document defines retention policy identifiers used by ownership-system
docs. Durations are product defaults and do not replace customer-specific legal
requirements.

| Policy | Duration | Cleanup owner | Evidence required |
| --- | --- | --- | --- |
| `user_content_retention` | account lifetime plus 30 days | Reminder System | deletion run id, affected owner ids, dry-run count |
| `short_lived_workflow_retention` | 30 days after terminal workflow state | Reminder System | workflow count by terminal state |
| `conversation_retention` | 180 days | Agent Runtime System | input/output message count by owner and cutoff |
| `calendar_import_retention` | 365 days | Calendar Import System | import run count by cutoff |
| `handoff_session_retention` | 14 days after expiry | Calendar Import System | handoff session count by cutoff |
| `timezone_state_retention` | account lifetime plus 30 days | Timezone System | owner ids and changed settings count |
| `memo_retention` | account lifetime plus 30 days | Memo System | memo card count by owner and cutoff |
| `friend_link_session_retention` | 30 days after unclaimed session creation | Platform System | link session count by terminal state |
| `disabled_user_link_retention` | audit-retained after disablement; de-listed and not reused | Platform System | disabled user link count |
| `friend_request_retention` | 30 days after terminal request state | Platform System | friend request count by terminal state |
| `friendship_retention` | account lifetime plus 30 days | Platform System | friendship count by status and owner pair |
| `account_block_retention` | account lifetime plus 30 days | Platform System | account block count by owner pair |
| `shared_reminder_request_retention` | 365 days after terminal shared reminder request state | Platform System | shared reminder request count by terminal state |
| `product_notification_retention` | 90 days after delivered or failed notification state | Platform System | product notification count by delivery state |
| `ephemeral_runtime_retention` | 7 days | Agent Runtime System | lock/batch state count |
| `ephemeral_trigger_retention` | 24 hours | Agent Runtime System | Redis key or stream trim evidence |
| `migration_retention` | 90 days after migration closeout | Owning migration plan | migration evidence path and archive count |

## Rule

Any plan that introduces deletion behavior must include a dry-run command, a
non-dry-run command, and evidence output under `artifacts/evidence/`.
