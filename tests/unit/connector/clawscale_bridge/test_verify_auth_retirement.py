import importlib.util
from pathlib import Path
from types import SimpleNamespace


def _load_script_module():
    script_path = (
        Path(__file__).resolve().parents[4]
        / "connector"
        / "scripts"
        / "verify-auth-retirement.py"
    )
    spec = importlib.util.spec_from_file_location("verify_auth_retirement_script", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_verify_auth_retirement_checks_empty_users_collection_account_resolution_and_bridge_payload():
    script = _load_script_module()

    class FakeCollection:
        def __init__(self, count):
            self._count = count

        def count_documents(self, query):
            assert query == {}
            return self._count

    class FakeDatabase:
        def __init__(self):
            self.collection_names = {"user_profiles", "coke_settings", "characters"}

        def list_collection_names(self):
            return sorted(self.collection_names)

        def get_collection(self, name):
            assert name == "users"
            return FakeCollection(0)

    class FakeMongoClient:
        def __init__(self, *args, **kwargs):
            self.admin = SimpleNamespace(command=lambda command: None)
            self._db = FakeDatabase()

        def __getitem__(self, name):
            assert name == "test"
            return self._db

        def close(self):
            return None

    class FakeUserDAO:
        def __init__(self, *args, **kwargs):
            pass

        def get_user_by_account_id(self, account_id):
            assert account_id == "acct_123"
            return {"account_id": "acct_123", "display_name": "Alice"}

        def close(self):
            return None

    class FakeCollection:
        def __init__(self):
            self.created_indexes = []
            self.updated = []

        def create_index(self, *args, **kwargs):
            self.created_indexes.append((args, kwargs))

        def update_one(self, *args, **kwargs):
            self.updated.append((args, kwargs))

    class FakeMongo:
        def __init__(self):
            self.collection = FakeCollection()

        def get_collection(self, name):
            assert name == "inputmessages"
            return self.collection

    mongo = FakeMongo()

    report = script.verify_auth_retirement(
        mongo_client_factory=FakeMongoClient,
        user_dao_factory=FakeUserDAO,
        bridge_gateway_factory=lambda: script.BusinessOnlyBridgeGateway(
            message_gateway=script.CokeMessageGateway(mongo=mongo, user_dao=SimpleNamespace()),
            reply_waiter=SimpleNamespace(wait_for_reply=lambda *args, **kwargs: {"reply": "ok"}),
            target_character_id="char_1",
        ),
        mongo_uri="mongodb://example",
        db_name="test",
        account_id="acct_123",
    )

    assert report == {
        "users_collection": {
            "exists": False,
            "document_count": 0,
        },
        "business_account_resolution": {
            "account_id": "acct_123",
            "resolved": True,
        },
        "bridge_payload": {
            "forbidden_keys": [],
            "customer_keys": ["display_name", "id"],
            "coke_account_keys": ["display_name", "id"],
        },
    }
    inserted = mongo.collection.updated[0][0][1]["$setOnInsert"]
    assert inserted["metadata"]["customer"] == {
        "id": "acct_123",
        "display_name": "Alice",
    }
    assert inserted["metadata"]["coke_account"] == {
        "id": "acct_123",
        "display_name": "Alice",
    }


def test_verify_auth_retirement_allows_empty_business_collections_without_failing_resolution():
    script = _load_script_module()

    class EmptyCollection:
        def count_documents(self, query):
            assert query == {}
            return 0

        def find(self, query, projection):
            return self

        def limit(self, count):
            assert count == 50
            return []

    class EmptyDatabase:
        def list_collection_names(self):
            return []

        def get_collection(self, name):
            return EmptyCollection()

    class FakeMongoClient:
        def __init__(self, *args, **kwargs):
            self.admin = SimpleNamespace(command=lambda command: None)
            self._db = EmptyDatabase()

        def __getitem__(self, name):
            return self._db

        def close(self):
            return None

    class FakeUserDAO:
        def __init__(self, *args, **kwargs):
            pass

        def get_user_by_account_id(self, account_id):
            raise AssertionError("account lookup should be skipped when no business docs exist")

        def close(self):
            return None

    class CapturingCollection:
        def __init__(self):
            self.updated = []

        def create_index(self, *args, **kwargs):
            return None

        def update_one(self, *args, **kwargs):
            self.updated.append((args, kwargs))
            return None

    class CapturingMongo:
        def __init__(self):
            self.collection = CapturingCollection()

        def get_collection(self, name):
            assert name == "inputmessages"
            return self.collection

    mongo = CapturingMongo()

    report = script.verify_auth_retirement(
        mongo_client_factory=FakeMongoClient,
        user_dao_factory=FakeUserDAO,
        bridge_gateway_factory=lambda: script.BusinessOnlyBridgeGateway(
            message_gateway=script.CokeMessageGateway(
                mongo=mongo,
                user_dao=SimpleNamespace(),
            ),
            reply_waiter=SimpleNamespace(wait_for_reply=lambda *args, **kwargs: {"reply": "ok"}),
            target_character_id="char_1",
        ),
        mongo_uri="mongodb://example",
        db_name="test",
    )

    assert report["business_account_resolution"] == {
        "account_id": None,
        "resolved": True,
    }
