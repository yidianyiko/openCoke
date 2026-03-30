def test_group_conversation_lookup_includes_character_routing_identity():
    from dao.conversation_dao import ConversationDAO

    captured_queries = []

    class StubCollection:
        def find_one(self, query):
            captured_queries.append(query)
            return None

        def insert_one(self, document):
            class Result:
                inserted_id = "conv-1"

            self.last_inserted = document
            return Result()

    dao = ConversationDAO.__new__(ConversationDAO)
    dao.collection = StubCollection()

    conversation_id, created = dao.get_or_create_group_conversation(
        "wechat",
        "room-123",
        "luna-wechat",
        initial_talkers=[
            {"id": "wx-user-1", "nickname": "Alice"},
            {"id": "luna-wechat", "nickname": "Luna"},
        ],
    )

    assert conversation_id == "conv-1"
    assert created is True
    assert captured_queries == [
        {
            "platform": "wechat",
            "chatroom_name": "room-123",
            "talkers.id": {"$in": ["luna-wechat"]},
        }
    ]

