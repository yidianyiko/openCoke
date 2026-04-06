from pymongo import MongoClient


class WechatBindSessionDAO:
    def __init__(self, mongo_uri: str, db_name: str):
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self.collection = self.db.get_collection("wechat_bind_sessions")

    def create_indexes(self) -> None:
        self.collection.create_index([("session_id", 1)], unique=True)
        self.collection.create_index([("bind_token", 1)], unique=True)
        self.collection.create_index([("bind_code", 1)], unique=True)
        self.collection.create_index([("account_id", 1), ("status", 1), ("expires_at", 1)])

    def find_active_session_for_account(self, account_id: str, now_ts: int):
        return self.collection.find_one(
            {
                "account_id": account_id,
                "status": "pending",
                "expires_at": {"$gt": now_ts},
            },
            sort=[("created_at", -1)],
        )

    def find_latest_session_for_account(self, account_id: str):
        return self.collection.find_one(
            {"account_id": account_id},
            sort=[("created_at", -1)],
        )

    def find_active_session_by_bind_token(self, bind_token: str, now_ts: int):
        return self.collection.find_one(
            {
                "bind_token": bind_token,
                "status": "pending",
                "expires_at": {"$gt": now_ts},
            }
        )

    def find_active_session_by_bind_code(self, bind_code: str, now_ts: int):
        return self.collection.find_one(
            {
                "bind_code": bind_code,
                "status": "pending",
                "expires_at": {"$gt": now_ts},
            }
        )

    def create_session(self, doc: dict):
        self.collection.insert_one(doc)
        return doc

    def mark_bound(
        self,
        session_id: str,
        masked_identity: str,
        external_end_user_id: str,
        now_ts: int,
    ):
        self.collection.update_one(
            {"session_id": session_id, "status": "pending"},
            {
                "$set": {
                    "status": "bound",
                    "masked_identity": masked_identity,
                    "matched_external_end_user_id": external_end_user_id,
                    "bound_at": now_ts,
                }
            },
        )
