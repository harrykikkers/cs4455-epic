"""Demo conversations used in dev mode (no backend required)."""

DEMO_CONVERSATIONS = {
    "user-alice-id": {
        "name": "alice",
        "key_warning": False,
        "messages": [
            {
                "messageId": "msg-001", "sender_id": "user-alice-id",
                "sender_username": "alice", "recipient_id": "dev-user-id",
                "recipient_username": "test", "_mine": False,
                "plaintext": "Hey, are you free to chat?",
                "created_at": "2025-05-20 09:15", "chain_status": "recorded",
            },
            {
                "messageId": "msg-002", "sender_id": "dev-user-id",
                "sender_username": "test", "recipient_id": "user-alice-id",
                "recipient_username": "alice", "_mine": True,
                "plaintext": "Yeah! What's up?",
                "created_at": "2025-05-20 09:17", "chain_status": "recorded",
            },
            {
                "messageId": "msg-003", "sender_id": "user-alice-id",
                "sender_username": "alice", "recipient_id": "dev-user-id",
                "recipient_username": "test", "_mine": False,
                "plaintext": "Wanted to share the project notes with you. Check your downloads.",
                "created_at": "2025-05-20 09:20", "chain_status": "pending",
                "_forwarded_to": [
                    {"username": "carol", "user_id": "user-carol-id",
                     "forwarded_at": "2025-05-20 09:25"},
                ],
            },
        ],
    },
    "user-bob-id": {
        "name": "bob",
        "key_warning": True,
        "messages": [
            {
                "messageId": "msg-004", "sender_id": "dev-user-id",
                "sender_username": "test", "recipient_id": "user-bob-id",
                "recipient_username": "bob", "_mine": True,
                "plaintext": "Meeting at 3pm tomorrow?",
                "created_at": "2025-05-19 14:00", "chain_status": "recorded",
            },
            {
                "messageId": "msg-005", "sender_id": "user-bob-id",
                "sender_username": "bob", "recipient_id": "dev-user-id",
                "recipient_username": "test", "_mine": False,
                "plaintext": "Works for me. I'll send the agenda.",
                "created_at": "2025-05-19 14:05", "chain_status": "recorded",
            },
        ],
    },
    "user-carol-id": {
        "name": "carol",
        "key_warning": False,
        "messages": [
            {
                "messageId": "msg-006", "sender_id": "user-carol-id",
                "sender_username": "carol", "recipient_id": "dev-user-id",
                "recipient_username": "test", "_mine": False,
                "plaintext": None,
                "created_at": "2025-05-21 11:00", "chain_status": "pending",
            },
        ],
    },
}
