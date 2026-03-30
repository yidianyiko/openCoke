from bson import ObjectId

from scripts.qiaoyun_to_coke_migration import (
    build_migration_plan,
    execute_migration_plan,
)


def make_character(_id: str, name: str, wxid: str = "wxid_same"):
    return {
        "_id": ObjectId(_id),
        "name": name,
        "is_character": True,
        "platforms": {"wechat": {"id": wxid, "nickname": name}},
    }


class StubCollection:
    def __init__(self, counts=None):
        self.counts = counts or {}
        self.update_calls = []
        self.delete_calls = []

    def count_documents(self, query):
        return self.counts.get(repr(query), 0)

    def update_one(self, query, update):
        self.update_calls.append((query, update))

    def delete_one(self, query):
        self.delete_calls.append(query)


class StubDB(dict):
    def __getitem__(self, item):
        return super().__getitem__(item)


def test_build_migration_plan_uses_existing_qiaoyun_id():
    qiaoyun = make_character("692c147e972f64f2b65da6ee", "qiaoyun")
    coke = make_character("692c1483972f64f2b65da6ef", "coke")

    plan = build_migration_plan(
        qiaoyun,
        coke,
        StubDB(
            {
                "relations": StubCollection(),
                "inputmessages": StubCollection(),
                "outputmessages": StubCollection(),
                "reminders": StubCollection(),
                "conversations": StubCollection(),
            }
        ),
    )

    assert plan["target_character_id"] == str(qiaoyun["_id"])
    assert plan["legacy_character_id"] == str(coke["_id"])
    assert plan["rename_update"]["$set"]["name"] == "coke"
    assert (
        plan["rename_update"]["$set"]["platforms.wechat.nickname"] == "coke"
    )


def test_build_migration_plan_rejects_non_empty_legacy_coke():
    qiaoyun = make_character("692c147e972f64f2b65da6ee", "qiaoyun")
    coke = make_character("692c1483972f64f2b65da6ef", "coke")
    db = StubDB(
        {
            "relations": StubCollection(
                {
                    repr({"cid": str(coke["_id"])}): 1,
                }
            ),
            "inputmessages": StubCollection(),
            "outputmessages": StubCollection(),
            "reminders": StubCollection(),
            "conversations": StubCollection(),
        }
    )

    try:
        build_migration_plan(qiaoyun, coke, db)
    except RuntimeError as exc:
        assert "legacy coke character is not empty" in str(exc)
    else:
        raise AssertionError("expected non-empty legacy coke to be rejected")


def test_execute_migration_plan_updates_qiaoyun_and_deletes_empty_coke():
    qiaoyun = make_character("692c147e972f64f2b65da6ee", "qiaoyun")
    coke = make_character("692c1483972f64f2b65da6ef", "coke")
    users = StubCollection()
    db = StubDB(
        {
            "relations": StubCollection(),
            "inputmessages": StubCollection(),
            "outputmessages": StubCollection(),
            "reminders": StubCollection(),
            "conversations": StubCollection(),
            "users": users,
        }
    )

    plan = build_migration_plan(qiaoyun, coke, db)
    execute_migration_plan(plan, db)

    assert users.update_calls == [
        (
            {"_id": qiaoyun["_id"]},
            {
                "$set": {
                    "name": "coke",
                    "platforms.wechat.nickname": "coke",
                }
            },
        )
    ]
    assert users.delete_calls == [{"_id": coke["_id"]}]
