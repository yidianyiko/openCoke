# Runner Alias Cleanup Evidence

Date: 2026-05-27

Scope:
- `agent/runner/agent_handler.py`
- `agent/runner/output_delivery.py`
- `agent/runner/runtime_lock.py`
- `agent/runner/message_history.py`
- runner/agent tests that previously patched compatibility aliases

What changed:
- Removed `agent_handler` wrapper aliases for runtime lock and output delivery helpers.
- Removed private implementation plus public alias pairs from runner helper modules.
- Moved tests to patch the module that owns each contract.

Verification:
- `PATH=/data/projects/coke/.venv/bin:$PATH zsh scripts/verify-surface worker-runtime`
  - `tests/unit/runner/`: 71 passed
  - `tests/unit/agent/`: 539 passed
  - `tests/unit/test_clawscale_only_topology.py`: 7 passed

Notes:
- Initial `zsh scripts/verify-surface worker-runtime` failed because this environment has no bare `python` command. Re-run with `.venv/bin` prepended to `PATH` succeeded.
