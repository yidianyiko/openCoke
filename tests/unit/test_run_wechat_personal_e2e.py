from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "run_wechat_personal_e2e.py"
)
SPEC = spec_from_file_location("run_wechat_personal_e2e", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_wait_until_retries_after_transient_predicate_error(monkeypatch):
    attempts = {"count": 0}

    def predicate():
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise RuntimeError("transient_startup_error")
        return {"ok": True}

    monkeypatch.setattr(MODULE.time, "sleep", lambda _: None)
    result = MODULE.wait_until(
        "fake_provider_healthz",
        predicate,
        timeout_seconds=1.0,
        interval_seconds=0.0,
    )

    assert result == {"ok": True}
    assert attempts["count"] == 3


def test_output_platform_fields_present_detects_legacy_runtime_fields():
    assert MODULE.output_platform_fields_present(
        {
            "account_id": "acc_1",
            "platform": "wechat_personal",
            "metadata": {
                "business_conversation_key": "bc_1",
            },
        }
    )
    assert MODULE.output_platform_fields_present(
        {
            "account_id": "acc_1",
            "metadata": {
                "business_conversation_key": "bc_1",
                "external_end_user_id": "wxid_1",
            },
        }
    )
    assert (
        MODULE.output_platform_fields_present(
            {
                "account_id": "acc_1",
                "metadata": {
                    "business_conversation_key": "bc_1",
                    "delivery_mode": "push",
                },
            }
        )
        is False
    )


def test_assert_cutover_invariants_accepts_complete_result():
    MODULE.assert_cutover_invariants(
        {
            "first_turn": {"business_conversation_key": "bc_1"},
            "steady_state": {
                "reply_text": "still here",
                "business_conversation_key": "bc_1",
            },
            "proactive": {"delivered_count": 1},
            "mongo_assertions": {"output_platform_fields_present": False},
        }
    )


def test_assert_cutover_invariants_rejects_platform_field_regression():
    try:
        MODULE.assert_cutover_invariants(
            {
                "first_turn": {"business_conversation_key": "bc_1"},
                "steady_state": {
                    "reply_text": "still here",
                    "business_conversation_key": "bc_1",
                },
                "proactive": {"delivered_count": 1},
                "mongo_assertions": {"output_platform_fields_present": True},
            }
        )
    except AssertionError:
        return
    raise AssertionError("expected AssertionError")


def test_fetch_latest_business_output_requires_matching_causal_event_and_key(monkeypatch):
    collection = type(
        "FakeCollection",
        (),
        {
            "__init__": lambda self: setattr(self, "queries", []),
            "find_one": lambda self, query, sort=None: (
                self.queries.append((query, sort))
                or {
                    "metadata": {
                        "business_protocol": {
                            "causal_inbound_event_id": "in_evt_1",
                            "business_conversation_key": "bc_1",
                        }
                    }
                }
            ),
        },
    )()

    monkeypatch.setattr(MODULE, "mongo_collection", lambda *args, **kwargs: collection)

    doc = MODULE.fetch_latest_business_output(
        "mongodb://example",
        "db",
        causal_inbound_event_id="in_evt_1",
        min_expect_output_timestamp=1710000000,
    )

    assert doc["metadata"]["business_protocol"]["business_conversation_key"] == "bc_1"
    query, sort = collection.queries[0]
    assert query["metadata.business_protocol.causal_inbound_event_id"] == "in_evt_1"
    assert query["metadata.business_protocol.business_conversation_key"] == {
        "$exists": True,
        "$ne": "",
    }
    assert sort == [("expect_output_timestamp", -1), ("_id", -1)]


def test_fetch_latest_business_input_can_skip_business_key_requirement(monkeypatch):
    collection = type(
        "FakeCollection",
        (),
        {
            "__init__": lambda self: setattr(self, "queries", []),
            "find_one": lambda self, query, sort=None: (
                self.queries.append((query, sort))
                or {
                    "from_user": "acct_1",
                    "metadata": {
                        "source": "clawscale",
                        "business_protocol": {
                            "causal_inbound_event_id": "in_evt_1",
                        },
                    },
                }
            ),
        },
    )()

    monkeypatch.setattr(MODULE, "mongo_collection", lambda *args, **kwargs: collection)

    doc = MODULE.fetch_latest_business_input(
        "mongodb://example",
        "db",
        "acct_1",
        min_input_timestamp=1710000000,
        require_business_conversation_key=False,
    )

    assert doc["metadata"]["business_protocol"]["causal_inbound_event_id"] == "in_evt_1"


def test_fetch_conversation_by_business_key_requires_persisted_key(monkeypatch):
    collection = type(
        "FakeCollection",
        (),
        {
            "__init__": lambda self: setattr(self, "queries", []),
            "find_one": lambda self, query: (
                self.queries.append(query)
                or {"_id": "conv_1", "business_conversation_key": "bc_1"}
            ),
        },
    )()

    monkeypatch.setattr(MODULE, "mongo_collection", lambda *args, **kwargs: collection)

    doc = MODULE.fetch_conversation_by_business_key(
        "mongodb://example",
        "db",
        business_conversation_key="bc_1",
    )

    assert doc == {"_id": "conv_1", "business_conversation_key": "bc_1"}
    assert collection.queries == [{"business_conversation_key": "bc_1"}]
