from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_proactive_followup_no_longer_has_deferred_action_runtime_path():
    forbidden_paths = [
        ROOT / "agent" / "agno_agent" / "workflows" / "post_analyze_workflow.py",
        ROOT / "agent" / "agno_agent" / "tools" / "deferred_action" / "service.py",
        ROOT / "agent" / "runner" / "deferred_action_executor.py",
        ROOT / "agent" / "prompt" / "chat_contextprompt.py",
        ROOT / "dao" / "deferred_action_dao.py",
        ROOT / "tests" / "unit" / "runner" / "test_deferred_action_message_source.py",
        ROOT / "tests" / "unit" / "agent" / "test_message_util_clawscale_routing.py",
    ]
    offenders = []
    for path in forbidden_paths:
        text = path.read_text()
        if "proactive_followup" in text or "find_active_internal_followup" in text:
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []
