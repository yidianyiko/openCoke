#!/usr/bin/env bash
set -euo pipefail

required_docs=(
  "docs/ARCHITECTURE.md"
  "docs/product-specs/FEATURE_TREE.md"
  "docs/roadmap.md"
  "docs/clawscale_bridge.md"
  "docs/deploy.md"
  "docs/design-docs/coke-working-contract.md"
  "docs/design-docs/interface-contract.md"
  "docs/design-docs/data-retention-policy.md"
  "docs/fitness/coke-verification-matrix.md"
  "docs/fitness/surfaces.yaml"
  "scripts/e2e/clean-rebuild-canonical-doc-sync.sh"
)

canonical_docs=(
  "docs/ARCHITECTURE.md"
  "docs/product-specs/FEATURE_TREE.md"
  "docs/roadmap.md"
  "docs/clawscale_bridge.md"
  "docs/deploy.md"
  "docs/design-docs/coke-working-contract.md"
  "docs/design-docs/interface-contract.md"
  "docs/design-docs/data-retention-policy.md"
  "docs/fitness/coke-verification-matrix.md"
  "docs/fitness/surfaces.yaml"
)

for doc in "${required_docs[@]}"; do
  test -f "$doc"
done

rg -q "The Turn" docs/ARCHITECTURE.md
rg -q "IdentityAccess" docs/ARCHITECTURE.md
rg -q "ChannelReachability" docs/ARCHITECTURE.md
rg -q "ConversationRuntime" docs/ARCHITECTURE.md
rg -q "SocialScheduling" docs/ARCHITECTURE.md
rg -q "CalendarImport" docs/ARCHITECTURE.md
rg -q "Postgres.*Redis" docs/ARCHITECTURE.md
rg -q "MongoDB.*Removed entirely|Mongo.*Removed entirely" docs/ARCHITECTURE.md
rg -q "clean-rebuild" docs/fitness/surfaces.yaml docs/fitness/coke-verification-matrix.md

for forbidden in \
  "model-output repair" \
  "second model call" \
  "MongoDB remains the source of truth" \
  "Gateway API owns" \
  "ClawScale Bridge :8090"; do
  if rg -n "$forbidden" "${canonical_docs[@]}"; then
    echo "Forbidden stale rebuild contract found: $forbidden" >&2
    exit 1
  fi
done

pending_workflow_pattern="(pending (friend[ -]request|shared[ -]reminder).*(current product|active requirement|supported|workflow)|\
(current product|active requirement|supported|workflow).*pending (friend[ -]request|shared[ -]reminder)|\
(friend[ -]request|shared[ -]reminder|approval).*(accept/reject|approval).*(current product|active requirement|supported|workflow)|\
(current product|active requirement|supported|workflow).*(friend[ -]request|shared[ -]reminder|approval).*(accept/reject|approval))"

if rg -ni "$pending_workflow_pattern" "${canonical_docs[@]}" \
  | rg -vi "deleted|deletion|out[- ]of[- ]scope|not (a |an )?current|not part of|no .*current|superseded"; then
  echo "Pending approval workflows may be mentioned only as deleted or out of scope, never as current rebuild behavior." >&2
  exit 1
fi
