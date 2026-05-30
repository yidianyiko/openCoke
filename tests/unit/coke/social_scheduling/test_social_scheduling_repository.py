from __future__ import annotations

from coke.domains.social_scheduling.repository import PostgresSocialSchedulingRepository


class ExplodingSession:
    def execute(self, *_args, **_kwargs):
        raise AssertionError("database should not be queried for invalid ids")


def test_postgres_repository_treats_invalid_friend_account_id_as_not_found():
    repository = PostgresSocialSchedulingRepository(ExplodingSession())

    assert (
        repository.get_active_friendship(
            "ae02ff016fcd4d39a189e51c8c8a31e6",
            "olivers",
        )
        is None
    )
    assert repository.list_active_friendships("olivers") == []


def test_postgres_repository_treats_invalid_shared_reminder_id_as_not_found():
    repository = PostgresSocialSchedulingRepository(ExplodingSession())

    assert repository.get_shared_reminder("not-a-shared-reminder-id") is None
    assert repository.list_shared_reminders_for_participant("lizihao") == []
