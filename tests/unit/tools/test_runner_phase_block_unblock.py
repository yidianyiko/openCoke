from tools.agent_smoke._runner_phase_block_unblock import (
    _validate_blocked_attempt,
    _validate_final_retry,
)


def test_validate_blocked_attempt_rejects_id_leak_and_fake_success():
    problems = _validate_blocked_attempt(
        "已创建共享提醒，邀请 ck_smoke_alice 一起打球。",
        shared_request_count_delta=1,
    )

    assert "blocked_reply_leaks_internal_account_id" in problems
    assert "blocked_attempt_created_shared_reminder" in problems
    assert "blocked_reply_silent_fake_success" in problems


def test_validate_blocked_attempt_accepts_visible_failure():
    problems = _validate_blocked_attempt(
        "你目前无法给 Alice 创建共享提醒，对方已屏蔽相关互动。",
        shared_request_count_delta=0,
    )

    assert problems == []


def test_validate_final_retry_requires_created_shared_reminder():
    assert _validate_final_retry("已创建共享提醒。", shared_request_count_delta=1) == []
    assert _validate_final_retry("我先帮你看看。", shared_request_count_delta=0) == [
        "final_retry_did_not_create_shared_reminder"
    ]
