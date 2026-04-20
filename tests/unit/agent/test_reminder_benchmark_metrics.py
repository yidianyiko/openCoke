from agent.agno_agent.evals.reminder_benchmark import summarize_results


def test_summarize_results_computes_tool_metrics():
    results = [
        {
            "model_id": "m1",
            "category": "positive",
            "expect_gate": True,
            "actual_gate": True,
            "expect_tool_call": True,
            "actual_tool_call": True,
            "expect_create": True,
            "actual_create": True,
            "expect_has_time": True,
            "actual_has_time": True,
            "gate_latency_seconds": 1.0,
            "tool_latency_seconds": 2.0,
        },
        {
            "model_id": "m1",
            "category": "negative",
            "expect_gate": False,
            "actual_gate": True,
            "expect_tool_call": False,
            "actual_tool_call": True,
            "expect_create": False,
            "actual_create": False,
            "expect_has_time": None,
            "actual_has_time": None,
            "gate_latency_seconds": 1.0,
            "tool_latency_seconds": 2.0,
        },
        {
            "model_id": "m1",
            "category": "positive",
            "expect_gate": True,
            "actual_gate": True,
            "expect_tool_call": True,
            "actual_tool_call": False,
            "expect_create": True,
            "actual_create": False,
            "expect_has_time": False,
            "actual_has_time": None,
            "gate_latency_seconds": 1.0,
            "tool_latency_seconds": 2.0,
        },
    ]

    summary = summarize_results(results)[0]

    assert summary["gate_accuracy"] == 0.6667
    assert summary["tool_precision"] == 0.5
    assert summary["tool_recall"] == 0.5
    assert summary["tool_f1"] == 0.5
    assert summary["create_accuracy"] == 0.6667
    assert summary["timed_create_accuracy"] == 0.5
    assert summary["negative_false_create_rate"] == 0.0
