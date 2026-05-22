from datetime import UTC, datetime


class FakeIndexCollection:
    def __init__(self):
        self.indexes = []

    def create_index(self, keys, **kwargs):
        self.indexes.append((keys, kwargs))


class FakeCollection(FakeIndexCollection):
    def __init__(self):
        super().__init__()
        self.documents = []
        self.updates = []

    def find_one(self, selector):
        for document in self.documents:
            if all(document.get(key) == value for key, value in selector.items()):
                return dict(document)
        return None

    def update_one(self, selector, update, upsert=False):
        self.updates.append((selector, update, upsert))
        for document in self.documents:
            if all(document.get(key) == value for key, value in selector.items()):
                document.update(update.get("$set", {}))
                return type("Result", (), {"matched_count": 1, "modified_count": 1, "upserted_id": None})()

        if upsert:
            inserted = dict(selector)
            inserted.update(update.get("$setOnInsert", {}))
            inserted.update(update.get("$set", {}))
            self.documents.append(inserted)
            return type("Result", (), {"matched_count": 0, "modified_count": 0, "upserted_id": "new"})()

        return type("Result", (), {"matched_count": 0, "modified_count": 0, "upserted_id": None})()


def test_create_indexes_uses_partial_unique_active_index():
    from dao.agent_instance_dao import AgentInstanceDAO

    collection = FakeIndexCollection()
    dao = AgentInstanceDAO(collection=collection)

    dao.create_indexes()

    assert collection.indexes == [
        (
            [("owner_user_id", 1), ("base_agent_type", 1)],
            {
                "unique": True,
                "partialFilterExpression": {"active": True},
            },
        )
    ]


def test_get_active_agent_instance_is_owner_and_type_scoped():
    from dao.agent_instance_dao import AgentInstanceDAO

    collection = FakeCollection()
    collection.documents.append(
        {
            "agent_instance_id": "agentinst_1",
            "owner_user_id": "ck_1",
            "base_agent_type": "coke_companion",
            "active": True,
            "display_name": "Shen",
        }
    )
    dao = AgentInstanceDAO(collection=collection)

    assert dao.get_active_agent_instance("ck_1")["agent_instance_id"] == "agentinst_1"
    assert dao.get_active_agent_instance("ck_2") is None


def test_upsert_active_agent_instance_rejects_untrusted_identity_fields():
    from dao.agent_instance_dao import AgentInstanceDAO

    collection = FakeCollection()
    dao = AgentInstanceDAO(collection=collection, now_provider=lambda: datetime(2026, 5, 22, tzinfo=UTC))

    saved = dao.upsert_active_agent_instance(
        "ck_1",
        {
            "owner_user_id": "ck_attacker",
            "base_agent_type": "other",
            "active": False,
            "display_name": "沈妄",
            "proactive": {"enabled": False},
        },
        base_character_id="char_1",
    )

    assert saved["owner_user_id"] == "ck_1"
    assert saved["base_agent_type"] == "coke_companion"
    assert saved["active"] is True
    assert saved["display_name"] == "沈妄"
    assert saved["proactive"] == {"enabled": False}
    assert "ck_attacker" not in str(collection.documents)


def test_reset_active_agent_instance_clears_override_fields_but_keeps_row():
    from dao.agent_instance_dao import AgentInstanceDAO

    collection = FakeCollection()
    collection.documents.append(
        {
            "agent_instance_id": "agentinst_1",
            "owner_user_id": "ck_1",
            "base_agent_type": "coke_companion",
            "base_character_id": "char_1",
            "active": True,
            "display_name": "沈妄",
            "persona": "custom",
            "proactive": {"enabled": False},
            "created_at": datetime(2026, 5, 1, tzinfo=UTC),
        }
    )
    dao = AgentInstanceDAO(collection=collection, now_provider=lambda: datetime(2026, 5, 22, tzinfo=UTC))

    reset = dao.reset_active_agent_instance("ck_1", base_character_id="char_1")

    assert reset["agent_instance_id"] == "agentinst_1"
    assert reset["owner_user_id"] == "ck_1"
    assert reset["base_character_id"] == "char_1"
    assert reset["display_name"] is None
    assert reset["persona"] is None
    assert reset["proactive"]["enabled"] is None
    assert reset["active"] is True
