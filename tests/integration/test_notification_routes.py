"""Integration tests for notifications."""

import pytest
from fastapi.testclient import TestClient
from src.shared.infrastructure.database import MongoSession

from src.modules.notification.domain.entities.notification import Notification
from src.modules.notification.domain.enums.notification_kind import NotificationKind

NOTES = "/api/v1/app/notifications"


def _notify(db: MongoSession, user, title: str) -> Notification:
    row = Notification(user_id=user.id, kind=NotificationKind.SYSTEM, title=title)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@pytest.mark.integration
class TestNotifications:
    def test_list_count_and_mark_read(
        self, client: TestClient, db_session: MongoSession, seeker, seeker_headers
    ):
        first = _notify(db_session, seeker, "First")
        _notify(db_session, seeker, "Second")

        assert client.get(f"{NOTES}/unread-count", headers=seeker_headers).json()[
            "data"
        ] == {"unread": 2}
        read = client.patch(f"{NOTES}/{first.id}/read", headers=seeker_headers).json()[
            "data"
        ]
        assert read["read_at"] is not None
        assert (
            client.get(f"{NOTES}/unread-count", headers=seeker_headers).json()["data"][
                "unread"
            ]
            == 1
        )

        unread = client.get(
            NOTES, params={"unread_only": "true"}, headers=seeker_headers
        )
        assert [n["title"] for n in unread.json()["data"]["items"]] == ["Second"]

        marked = client.post(f"{NOTES}/read-all", headers=seeker_headers).json()["data"]
        assert marked == {"marked": 1}

    def test_someone_elses_notification_is_a_404(
        self, client, db_session, seeker, other_seeker_headers
    ):
        row = _notify(db_session, seeker, "Private")
        response = client.patch(f"{NOTES}/{row.id}/read", headers=other_seeker_headers)
        assert response.status_code == 404
        assert (
            client.get(NOTES, headers=other_seeker_headers).json()["data"]["total"] == 0
        )
