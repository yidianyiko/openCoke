from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from coke.app import create_app
from coke.config import Settings
from coke.domains.social_scheduling.models import SocialSchedulingError

DATABASE_URL = "postgresql+psycopg://coke:coke@localhost:5432/coke_test"
REDIS_URL = "redis://localhost:6379/15"


class FakeSocialSchedulingService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def get_or_create_friend_link(self, owner_account_id):
        self.calls.append(
            ("get_or_create_friend_link", {"owner_account_id": owner_account_id})
        )
        return SimpleNamespace(
            id="link_1",
            owner_account_id=owner_account_id,
            public_token="public_token",
            link_code="link_code",
            qr_payload="https://coke.example/friends/public_token",
            lifecycle="active",
        )

    def reset_friend_link(self, owner_account_id):
        self.calls.append(("reset_friend_link", {"owner_account_id": owner_account_id}))
        return self.get_or_create_friend_link(owner_account_id)

    def disable_friend_link(self, owner_account_id):
        self.calls.append(
            ("disable_friend_link", {"owner_account_id": owner_account_id})
        )
        return SimpleNamespace(
            id="link_1",
            owner_account_id=owner_account_id,
            public_token=None,
            link_code=None,
            qr_payload=None,
            lifecycle="disabled",
        )

    def establish_friendship_from_token(self, joiner_account_id, public_token):
        self.calls.append(
            (
                "establish_friendship_from_token",
                {"joiner_account_id": joiner_account_id, "public_token": public_token},
            )
        )
        return SimpleNamespace(
            status="created",
            friendship=SimpleNamespace(id="friendship_1"),
            continuation={},
        )

    def establish_friendship_from_code(self, joiner_account_id, link_code):
        self.calls.append(
            (
                "establish_friendship_from_code",
                {"joiner_account_id": joiner_account_id, "link_code": link_code},
            )
        )
        return SimpleNamespace(
            status="already_active",
            friendship=SimpleNamespace(id="friendship_1"),
            continuation={},
        )

    def complete_deferred_friend_link(self, joiner_account_id, friend_link_id):
        self.calls.append(
            (
                "complete_deferred_friend_link",
                {
                    "joiner_account_id": joiner_account_id,
                    "friend_link_id": friend_link_id,
                },
            )
        )
        return SimpleNamespace(
            status="created",
            friendship=SimpleNamespace(id="friendship_1"),
            continuation={},
        )

    def list_friends(self, account_id):
        self.calls.append(("list_friends", {"account_id": account_id}))
        return [SimpleNamespace(account_id="friend", friendship_id="friendship_1")]

    def remove_friend(self, account_id, friend_account_id):
        self.calls.append(
            (
                "remove_friend",
                {"account_id": account_id, "friend_account_id": friend_account_id},
            )
        )
        return SimpleNamespace(id="friendship_1", lifecycle="removed")

    def create_shared_reminder(self, **kwargs):
        self.calls.append(("create_shared_reminder", kwargs))
        return SimpleNamespace(
            status="created",
            shared_reminder=SimpleNamespace(
                id="shared_1",
                creator_account_id=kwargs["creator_account_id"],
                participant_account_ids=("creator", "friend"),
                title=kwargs["title"],
                local_trigger_at=kwargs["local_trigger_at"],
                captured_timezone=kwargs["captured_timezone"],
                duration_minutes=kwargs["duration_minutes"],
                status="active",
            ),
            projections=[
                SimpleNamespace(account_id="creator"),
                SimpleNamespace(account_id="friend"),
            ],
            breakdown={},
            follow_up_facts={},
            notification_facts=[],
        )

    def list_shared_reminders(self, account_id):
        self.calls.append(("list_shared_reminders", {"account_id": account_id}))
        return [self._shared_reminder()]

    def view_shared_reminder(self, account_id, shared_reminder_id):
        self.calls.append(
            (
                "view_shared_reminder",
                {"account_id": account_id, "shared_reminder_id": shared_reminder_id},
            )
        )
        return self._shared_reminder()

    def cancel_shared_reminder(self, account_id, shared_reminder_id):
        self.calls.append(
            (
                "cancel_shared_reminder",
                {"account_id": account_id, "shared_reminder_id": shared_reminder_id},
            )
        )
        return SimpleNamespace(
            status="cancelled",
            shared_reminder=self._shared_reminder(status="cancelled"),
            projections=[],
            notification_facts=[],
        )

    def complete_own_projection(self, account_id, shared_reminder_id):
        self.calls.append(
            (
                "complete_own_projection",
                {"account_id": account_id, "shared_reminder_id": shared_reminder_id},
            )
        )
        return SimpleNamespace(account_id=account_id, completion_status="completed")

    def query_availability(self, **kwargs):
        self.calls.append(("query_availability", kwargs))
        return SimpleNamespace(
            friend_account_id=kwargs["friend_account_ids"][0],
            windows=[
                SimpleNamespace(
                    to_public_dict=lambda: {
                        "start": "2026-06-01T09:00:00",
                        "end": "2026-06-01T09:30:00",
                        "state": "free",
                    }
                )
            ],
        )

    def _shared_reminder(self, status="active"):
        return SimpleNamespace(
            id="shared_1",
            creator_account_id="creator",
            participant_account_ids=("creator", "friend"),
            title="sync",
            local_trigger_at=datetime(2026, 6, 1, 9, 0),
            captured_timezone="UTC",
            duration_minutes=15,
            status=status,
        )


class ErrorService(FakeSocialSchedulingService):
    def remove_friend(self, account_id, friend_account_id):
        raise SocialSchedulingError(
            "friendship_not_found", fact={"type": "not_active_friend"}
        )


def make_client(service=None):
    service = service or FakeSocialSchedulingService()
    app = create_app(
        Settings(database_url=DATABASE_URL, redis_url=REDIS_URL),
        social_scheduling_service=service,
    )
    return app.test_client(), service


def test_friend_routes_are_thin_service_adapters():
    client, service = make_client()

    assert client.get("/api/friends/link?owner_account_id=owner").status_code == 200
    assert (
        client.post(
            "/api/friends/link/reset", json={"owner_account_id": "owner"}
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/friends/link/disable", json={"owner_account_id": "owner"}
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/friends/join",
            json={"joiner_account_id": "joiner", "public_token": "public_token"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/friends/join",
            json={"joiner_account_id": "joiner", "link_code": "link_code"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/friends/complete-deferred",
            json={"joiner_account_id": "joiner", "friend_link_id": "link_1"},
        ).status_code
        == 200
    )
    assert client.get("/api/friends?account_id=owner").status_code == 200
    assert (
        client.post(
            "/api/friends/friend/remove", json={"account_id": "owner"}
        ).status_code
        == 200
    )

    assert [call[0] for call in service.calls] == [
        "get_or_create_friend_link",
        "reset_friend_link",
        "get_or_create_friend_link",
        "disable_friend_link",
        "establish_friendship_from_token",
        "establish_friendship_from_code",
        "complete_deferred_friend_link",
        "list_friends",
        "remove_friend",
    ]


def test_shared_reminder_routes_are_thin_service_adapters():
    client, service = make_client()

    create = client.post(
        "/api/shared-reminders",
        json={
            "creator_account_id": "creator",
            "receiver_account_ids": ["friend"],
            "title": "sync",
            "local_trigger_at": "2026-06-01T09:00:00",
            "captured_timezone": "UTC",
            "duration_minutes": 15,
            "context": {"source": "route-test"},
        },
    )
    assert create.status_code == 201
    assert client.get("/api/shared-reminders?account_id=creator").status_code == 200
    assert (
        client.get("/api/shared-reminders/shared_1?account_id=creator").status_code
        == 200
    )
    assert (
        client.post(
            "/api/shared-reminders/shared_1/cancel", json={"account_id": "creator"}
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/shared-reminders/shared_1/complete-own-projection",
            json={"account_id": "creator"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/shared-reminders/availability",
            json={
                "requester_account_id": "creator",
                "friend_account_ids": ["friend"],
                "local_start": "2026-06-01T09:00:00",
                "local_end": "2026-06-01T10:00:00",
                "requester_timezone": "UTC",
            },
        ).status_code
        == 200
    )

    assert [call[0] for call in service.calls] == [
        "create_shared_reminder",
        "list_shared_reminders",
        "view_shared_reminder",
        "cancel_shared_reminder",
        "complete_own_projection",
        "query_availability",
    ]


def test_routes_return_social_scheduling_errors_as_user_safe_json():
    client, _ = make_client(ErrorService())

    response = client.post("/api/friends/friend/remove", json={"account_id": "owner"})

    assert response.status_code == 400
    assert response.get_json() == {
        "error": {
            "code": "friendship_not_found",
            "fact": {"type": "not_active_friend"},
        }
    }
