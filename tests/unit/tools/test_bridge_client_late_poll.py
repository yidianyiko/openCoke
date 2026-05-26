import sys
import time
import types

from tools.agent_smoke.bridge_client import (
    SYNC_REPLY_TIMEOUT_FALLBACK_REPLY,
    poll_late_reply_text,
)


class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *_args, **_kwargs):
        return self

    def __iter__(self):
        return iter(self._docs)


class _FakeOutputMessages:
    def __init__(self, poll_results):
        self.poll_results = list(poll_results)
        self.queries = []

    def find(self, query):
        self.queries.append(query)
        docs = self.poll_results.pop(0) if self.poll_results else []
        return _FakeCursor(docs)


class _FakeDb:
    def __init__(self, outputmessages):
        self.outputmessages = outputmessages


class _FakeMongoClient:
    def __init__(self, outputmessages):
        self.outputmessages = outputmessages
        self.closed = False

    def __getitem__(self, _name):
        return _FakeDb(self.outputmessages)

    def close(self):
        self.closed = True


def _install_fake_mongo(monkeypatch, outputmessages):
    fake_client = _FakeMongoClient(outputmessages)
    fake_pymongo = types.SimpleNamespace(MongoClient=lambda _uri: fake_client)
    monkeypatch.setitem(sys.modules, "pymongo", fake_pymongo)
    monkeypatch.setattr("tools.agent_smoke.bridge_client._config.mongo_uri", lambda: "mongodb://fake")
    monkeypatch.setattr("tools.agent_smoke.bridge_client._config.mongo_db_name", lambda: "fake_db")
    return fake_client


def test_poll_late_reply_text_returns_immediate_matching_reply(monkeypatch):
    outputmessages = _FakeOutputMessages(
        [[{"_id": "out1", "status": "handled", "message": "已经帮你约好了。"}]]
    )
    _install_fake_mongo(monkeypatch, outputmessages)

    reply_text, output_doc = poll_late_reply_text(
        causal_inbound_event_id="evt1",
        coke_account_id="ck_alice",
        poll_seconds=1,
        poll_interval_seconds=0.01,
    )

    assert reply_text == "已经帮你约好了。"
    assert output_doc == {"_id": "out1", "status": "handled", "message": "已经帮你约好了。"}
    query = outputmessages.queries[0]
    assert {"to_user": "ck_alice"} in query["$and"][0]["$or"]
    assert {"account_id": "ck_alice"} in query["$and"][0]["$or"]
    assert {
        "metadata.business_protocol.causal_inbound_event_id": "evt1"
    } in query["$and"][1]["$or"]
    assert {"metadata.causal_inbound_event_id": "evt1"} in query["$and"][1]["$or"]
    assert query["$and"][2]["status"]["$in"] == ["failed", "handled"]
    assert query["$and"][3]["message"]["$nin"] == [
        "",
        SYNC_REPLY_TIMEOUT_FALLBACK_REPLY,
    ]


def test_poll_late_reply_text_waits_until_reply_lands(monkeypatch):
    outputmessages = _FakeOutputMessages(
        [
            [],
            [],
            [{"_id": "out2", "status": "handled", "message": "迟到的真实回复。"}],
        ]
    )
    _install_fake_mongo(monkeypatch, outputmessages)

    reply_text, output_doc = poll_late_reply_text(
        causal_inbound_event_id="evt2",
        coke_account_id="ck_bob",
        poll_seconds=1,
        poll_interval_seconds=0.01,
    )

    assert reply_text == "迟到的真实回复。"
    assert output_doc == {"_id": "out2", "status": "handled", "message": "迟到的真实回复。"}
    assert len(outputmessages.queries) == 3


def test_poll_late_reply_text_ignores_pending_until_final_output_lands(monkeypatch):
    outputmessages = _FakeOutputMessages(
        [
            [{"_id": "out_pending", "status": "pending", "message": "未最终输出。"}],
            [{"_id": "out_pending", "status": "pending", "message": "未最终输出。"}],
            [{"_id": "out_final", "status": "handled", "message": "最终真实回复。"}],
        ]
    )
    _install_fake_mongo(monkeypatch, outputmessages)

    reply_text, output_doc = poll_late_reply_text(
        causal_inbound_event_id="evt_final",
        coke_account_id="ck_dana",
        poll_seconds=1,
        poll_interval_seconds=0.01,
    )

    assert reply_text == "最终真实回复。"
    assert output_doc == {"_id": "out_final", "status": "handled", "message": "最终真实回复。"}
    assert len(outputmessages.queries) == 3


def test_poll_late_reply_text_returns_none_on_timeout(monkeypatch):
    outputmessages = _FakeOutputMessages([[], [], []])
    _install_fake_mongo(monkeypatch, outputmessages)

    start = time.monotonic()
    reply_text, output_doc = poll_late_reply_text(
        causal_inbound_event_id="evt3",
        coke_account_id="ck_cara",
        poll_seconds=0.03,
        poll_interval_seconds=0.01,
    )

    assert time.monotonic() - start < 5
    assert reply_text is None
    assert output_doc is None
