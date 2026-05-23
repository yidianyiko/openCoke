from scripts.reminder_eval import dataset as normal_eval
from scripts.reminder_eval import scoring
from scripts.reminder_eval.scoring import SEVERITY_THRESHOLDS


def test_iter_case_batches_preserves_json_order_in_fixed_chunks():
    batches = list(
        normal_eval.iter_case_batches(
            total_count=70, offset=0, limit=None, batch_size=32
        )
    )

    assert batches == [
        normal_eval.CaseBatch(offset=0, limit=32),
        normal_eval.CaseBatch(offset=32, limit=32),
        normal_eval.CaseBatch(offset=64, limit=6),
    ]


def test_iter_case_batches_applies_total_limit_before_chunking():
    batches = list(
        normal_eval.iter_case_batches(
            total_count=70, offset=10, limit=33, batch_size=32
        )
    )

    assert batches == [
        normal_eval.CaseBatch(offset=10, limit=32),
        normal_eval.CaseBatch(offset=42, limit=1),
    ]


def test_load_cases_applies_normal_path_expectation_fixture():
    cases = normal_eval.load_cases()
    expectations = normal_eval.load_case_expectations(
        normal_eval.DEFAULT_EXPECTATIONS_PATH
    )
    merged_metadata_keys = {
        "evaluation_expectation",
        "evaluation_reason",
        "expected_operation",
        "allow_clarification",
        "expected_creates",
        "expected_clarification_terms",
    }

    assert len(expectations) <= 380
    for index, expectation in expectations.items():
        for key, value in expectation.items():
            if key not in merged_metadata_keys:
                assert key == "severity"
                continue
            assert cases[index].metadata[key] == value

    classes = {
        expectation.get("evaluation_expectation", "crud")
        for expectation in expectations.values()
    }
    assert {"crud", "query", "clarify", "discussion", "capability"}.issubset(classes)


def test_run_all_uses_pruned_expectation_cases_and_preserves_raw_indices():
    cases = normal_eval.load_cases()
    expectations = normal_eval.load_case_expectations(
        normal_eval.DEFAULT_EXPECTATIONS_PATH
    )
    selected = normal_eval.select_expectation_cases(cases)
    expected_indices = sorted(expectations)

    assert len(selected) == len(expectations)
    assert [case.metadata["_case_index"] for case in selected] == expected_indices
    assert (
        normal_eval.runtime_case_index(selected[0], fallback_index=-1)
        == expected_indices[0]
    )


def test_expectation_fixture_cases_are_current_and_well_formed():
    cases = normal_eval.load_cases()
    expectations = normal_eval.load_case_expectations(
        normal_eval.DEFAULT_EXPECTATIONS_PATH
    )
    allowed_keys = {
        "evaluation_expectation",
        "evaluation_reason",
        "expected_operation",
        "allow_clarification",
        "expected_creates",
        "expected_clarification_terms",
        "severity",
    }
    allowed_expectations = {"crud", "query", "clarify", "discussion", "capability"}

    assert expectations
    for index, expectation in expectations.items():
        assert 0 <= index < len(cases)
        assert set(expectation).issubset(allowed_keys)
        assert expectation["evaluation_expectation"] in allowed_expectations
        assert expectation["evaluation_reason"].strip()
        assert expectation["severity"] in SEVERITY_THRESHOLDS
        assert (
            scoring.case_evaluation_expectation(cases[index])
            == expectation["evaluation_expectation"]
        )

        for expected_create in expectation.get("expected_creates", []):
            assert expected_create["title"].strip()
        if expectation.get("expected_clarification_terms"):
            assert all(
                term.strip() for term in expectation["expected_clarification_terms"]
            )


def test_history_two_turn_eval_manifest_records_open_runtime_evidence():
    manifest = normal_eval.history_two_turn_eval_manifest()

    assert manifest["name"] == "history-hourly-checkin-two-turn"
    assert manifest["turns"] == [
        "每个整点喊我打卡吧",
        "从现在到晚上七点",
    ]
    assert manifest["guard_modes"] == [
        "high_frequency_guards_enabled",
        "high_frequency_guards_bypassed",
    ]
    assert manifest["transport"] == "business-clawscale"
    assert manifest["expected_path"] == (
        "turn 1 asks for the missing end condition; turn 2 uses recent "
        "conversation history to create bounded reminders"
    )
    assert manifest["evidence_status"] == (
        "open_real_model_business_clawscale_run_required"
    )
