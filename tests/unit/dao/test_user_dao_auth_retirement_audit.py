from unittest.mock import MagicMock, patch


def test_audit_customer_id_parity_reports_drift_examples_and_ignores_non_account_ids():
    with patch("dao.user_dao.MongoClient") as mongo_client:
        mock_client = MagicMock()
        mock_db = MagicMock()
        mongo_client.return_value = mock_client
        mock_client.__getitem__.return_value = mock_db

        outputmessages = MagicMock()
        outputmessages.find.return_value = [
            {"_id": "out_ok", "account_id": "ck_live"},
            {"_id": "out_drift", "account_id": "ck_missing"},
        ]
        deferred_actions = MagicMock()
        deferred_actions.find.return_value = [
            {"_id": "rem_ignore", "user_id": "507f1f77bcf86cd799439011"},
            {"_id": "rem_drift", "user_id": "acct_missing"},
        ]
        conversations = MagicMock()
        conversations.find.return_value = [
            {
                "_id": "conv_1",
                "talkers": [
                    {"id": "character_1"},
                    {"id": "ck_missing"},
                ],
            }
        ]

        collections = {
            "outputmessages": outputmessages,
            "deferred_actions": deferred_actions,
            "conversations": conversations,
        }
        mock_db.get_collection.side_effect = collections.__getitem__

        from dao.user_dao import audit_customer_id_parity

        report = audit_customer_id_parity(
            customer_ids=["ck_live"],
            mongo_uri="mongodb://example",
            db_name="test",
            example_limit=2,
            server_selection_timeout_ms=321,
        )

        assert report == {
            "collectionsChecked": ["outputmessages", "deferred_actions", "conversations"],
            "driftCount": 3,
            "examples": [
                {
                    "collection": "outputmessages",
                    "fieldPath": "account_id",
                    "documentId": "out_drift",
                    "accountId": "ck_missing",
                },
                {
                    "collection": "deferred_actions",
                    "fieldPath": "user_id",
                    "documentId": "rem_drift",
                    "accountId": "acct_missing",
                },
            ],
        }
        mongo_client.assert_called_once_with(
            "mongodb://example",
            serverSelectionTimeoutMS=321,
        )
        mock_client.admin.command.assert_called_once_with("ping")
        mock_client.close.assert_called_once()


def test_audit_customer_id_parity_returns_zero_drift_when_all_refs_match():
    with patch("dao.user_dao.MongoClient") as mongo_client:
        mock_client = MagicMock()
        mock_db = MagicMock()
        mongo_client.return_value = mock_client
        mock_client.__getitem__.return_value = mock_db

        outputmessages = MagicMock()
        outputmessages.find.return_value = [{"_id": "out_ok", "account_id": "ck_live"}]
        deferred_actions = MagicMock()
        deferred_actions.find.return_value = [{"_id": "rem_ok", "user_id": "acct_live"}]
        conversations = MagicMock()
        conversations.find.return_value = [
            {"_id": "conv_ok", "talkers": [{"id": "ck_live"}, {"id": "acct_live"}]}
        ]

        collections = {
            "outputmessages": outputmessages,
            "deferred_actions": deferred_actions,
            "conversations": conversations,
        }
        mock_db.get_collection.side_effect = collections.__getitem__

        from dao.user_dao import audit_customer_id_parity

        report = audit_customer_id_parity(
            customer_ids=["ck_live", "acct_live"],
            mongo_uri="mongodb://example",
            db_name="test",
        )

        assert report == {
            "collectionsChecked": ["outputmessages", "deferred_actions", "conversations"],
            "driftCount": 0,
            "examples": [],
        }
