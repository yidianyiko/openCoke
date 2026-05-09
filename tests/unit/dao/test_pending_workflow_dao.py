from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_collection(monkeypatch):
    from dao import pending_workflow_dao as dao_module

    collection = MagicMock()
    db = MagicMock()
    db.get_collection.return_value = collection
    client = MagicMock()
    client.__getitem__.return_value = db
    monkeypatch.setattr(dao_module, "MongoClient", MagicMock(return_value=client))
    return collection


def _document(status="awaiting_user", revision=0):
    now = datetime(2026, 5, 9, 1, 0, tzinfo=UTC)
    return {
        "id": "workflow_1",
        "owner_user_id": "user-1",
        "conversation_id": "conv-1",
        "kind": "reminder_create",
        "status": status,
        "revision": revision,
        "created_at": now,
        "updated_at": now,
        "expires_at": now + timedelta(days=1),
        "document": {
            "id": "workflow_1",
            "kind": "reminder_create",
            "status": status,
            "origin": {
                "conversation_id": "conv-1",
                "message_ids": ["msg-1"],
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
                "expires_at": (now + timedelta(days=1)).isoformat(),
            },
            "goal": "Set up reminder",
            "slots": {"title": {"value": "打卡", "status": "filled"}},
            "missing_fields": [],
            "assumptions": [],
            "constraints": [],
            "next_steps": ["execute_now"],
            "payload": {"reminder": {"draft_operations": []}},
        },
    }


def test_create_indexes_uses_partial_unique_active_index(mock_collection):
    from dao.pending_workflow_dao import PendingWorkflowDAO

    dao = PendingWorkflowDAO()
    dao.collection = mock_collection

    dao.create_indexes()

    calls = mock_collection.create_index.call_args_list
    assert any(
        call.args[0] == [("owner_user_id", 1), ("conversation_id", 1)]
        and call.kwargs["unique"] is True
        and call.kwargs["partialFilterExpression"]["status"]["$in"]
        == ["draft", "awaiting_user", "ready_to_execute", "executing"]
        for call in calls
    )
    assert any(call.args[0] == [("expires_at", 1)] for call in calls)
    assert any(call.args[0] == [("status", 1), ("updated_at", 1)] for call in calls)


def test_load_active_for_conversation_filters_active_statuses(mock_collection):
    from dao.pending_workflow_dao import PendingWorkflowDAO

    dao = PendingWorkflowDAO()
    dao.collection = mock_collection
    mock_collection.find_one.return_value = _document()

    result = dao.load_active_for_conversation("user-1", "conv-1")

    assert result["id"] == "workflow_1"
    mock_collection.find_one.assert_called_once_with(
        {
            "owner_user_id": "user-1",
            "conversation_id": "conv-1",
            "status": {
                "$in": ["draft", "awaiting_user", "ready_to_execute", "executing"]
            },
        },
        sort=[("updated_at", -1)],
    )


def test_upsert_new_active_workflow_sets_revision_zero(mock_collection):
    from dao.pending_workflow_dao import PendingWorkflowDAO

    dao = PendingWorkflowDAO()
    dao.collection = mock_collection
    document = _document(revision=7)

    dao.upsert_new_active_workflow(document)

    written = mock_collection.update_one.call_args.args[1]
    assert written["$set"]["revision"] == 0
    assert written["$set"]["id"] == "workflow_1"


def test_cas_update_requires_expected_revision_and_increments(mock_collection):
    from dao.pending_workflow_dao import PendingWorkflowDAO

    dao = PendingWorkflowDAO()
    dao.collection = mock_collection
    mock_collection.update_one.return_value = MagicMock(matched_count=1)

    assert dao.cas_update_workflow("workflow_1", 3, _document(revision=3)) is True

    selector, update = mock_collection.update_one.call_args.args
    assert selector == {"id": "workflow_1", "revision": 3}
    assert update["$set"]["revision"] == 4


def test_cas_update_returns_false_on_stale_revision(mock_collection):
    from dao.pending_workflow_dao import PendingWorkflowDAO

    dao = PendingWorkflowDAO()
    dao.collection = mock_collection
    mock_collection.update_one.return_value = MagicMock(matched_count=0)

    assert dao.cas_update_workflow("workflow_1", 3, _document(revision=3)) is False


def test_pending_workflow_flags_default_off():
    from conf.config import CONF

    flags = CONF["features"]["pending_workflow"]["reminders"]
    assert flags["enabled"] is False
    assert flags["execution_envelope"]["enabled"] is False
