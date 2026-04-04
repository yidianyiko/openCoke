# -*- coding: utf-8 -*-
import time
from types import SimpleNamespace

import pytest


class _FakeCursor:
    def __init__(self, documents):
        self._documents = list(documents)

    def sort(self, field, direction):
        reverse = direction == -1
        self._documents.sort(
            key=lambda doc: (doc.get(field) is None, doc.get(field)), reverse=reverse
        )
        return self

    def __iter__(self):
        return iter(self._documents)


class _FakeCollection:
    def __init__(self):
        self._documents = []
        self._next_id = 1

    def _matches(self, document, query):
        for key, expected in query.items():
            if document.get(key) != expected:
                return False
        return True

    def insert_one(self, document):
        stored = dict(document)
        stored["_id"] = self._next_id
        self._next_id += 1
        self._documents.append(stored)
        return SimpleNamespace(inserted_id=stored["_id"])

    def find_one(self, query):
        for document in self._documents:
            if self._matches(document, query):
                return dict(document)
        return None

    def find(self, query):
        matched = [dict(doc) for doc in self._documents if self._matches(doc, query)]
        return _FakeCursor(matched)

    def delete_one(self, query):
        for index, document in enumerate(self._documents):
            if self._matches(document, query):
                del self._documents[index]
                return SimpleNamespace(deleted_count=1)
        return SimpleNamespace(deleted_count=0)

    def delete_many(self, query):
        original_count = len(self._documents)
        self._documents = [
            doc for doc in self._documents if not self._matches(doc, query)
        ]
        return SimpleNamespace(deleted_count=original_count - len(self._documents))


class _FakeDB:
    def __init__(self, collection):
        self.reminders = collection


class _FakeMongoClient:
    def __init__(self, *args, **kwargs):
        self._collection = _FakeCollection()
        self._db = _FakeDB(self._collection)
        self.closed = False

    def __getitem__(self, name):
        return self._db

    def close(self):
        self.closed = True


@pytest.fixture
def dao(monkeypatch):
    from dao import reminder_dao as reminder_dao_module

    monkeypatch.setattr(reminder_dao_module, "MongoClient", _FakeMongoClient)
    return reminder_dao_module.ReminderDAO()


def test_list_id_defaults_to_inbox(dao):
    """测试 list_id 默认值为 inbox"""
    reminder_data = {
        "user_id": "test_user",
        "title": "test reminder",
        "next_trigger_time": int(time.time()) + 3600,
    }

    inserted_id = dao.create_reminder(reminder_data)

    assert inserted_id is not None

    reminder = dao.collection.find_one({"user_id": "test_user", "title": "test reminder"})

    assert reminder["list_id"] == "inbox"


def test_create_reminder_with_custom_list_id(dao):
    """测试创建提醒时可以指定自定义 list_id"""
    reminder_data = {
        "user_id": "test_user",
        "title": "test reminder with custom list",
        "next_trigger_time": int(time.time()) + 3600,
        "list_id": "work",
    }

    inserted_id = dao.create_reminder(reminder_data)

    assert inserted_id is not None

    reminder = dao.collection.find_one(
        {"user_id": "test_user", "title": "test reminder with custom list"}
    )

    assert reminder["list_id"] == "work"


def test_create_reminder_without_trigger_time(dao):
    """测试创建无触发时间的提醒"""
    reminder_data = {
        "user_id": "test_user",
        "title": "buy milk",
        "next_trigger_time": None,
        "list_id": "inbox",
    }

    inserted_id = dao.create_reminder(reminder_data)

    assert inserted_id is not None

    reminder = dao.collection.find_one({"user_id": "test_user", "title": "buy milk"})

    assert reminder["next_trigger_time"] is None
    assert reminder["list_id"] == "inbox"


def test_find_reminders_by_user_includes_null_trigger_time(dao):
    """测试查询用户提醒时包含无时间的任务"""
    reminder_with_time = {
        "user_id": "test_user_2",
        "title": "reminder with time",
        "next_trigger_time": int(time.time()) + 3600,
        "list_id": "inbox",
        "status": "active",
    }
    dao.create_reminder(reminder_with_time)

    reminder_no_time = {
        "user_id": "test_user_2",
        "title": "reminder without time",
        "next_trigger_time": None,
        "list_id": "inbox",
        "status": "active",
    }
    dao.create_reminder(reminder_no_time)

    reminders = dao.find_reminders_by_user("test_user_2", status="active")

    assert len(reminders) == 2

    titles = [r["title"] for r in reminders]
    assert "reminder with time" in titles
    assert "reminder without time" in titles
