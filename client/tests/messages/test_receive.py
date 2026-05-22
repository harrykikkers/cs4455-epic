import requests
from helpers import auth_headers, send_msg, BASE_URL, VERIFY_SSL


def test_inbox_contains_received_message(user_a, user_b):
    send_msg(user_a["token"], user_b["user_id"], "inbox test")
    resp = requests.get(
        f"{BASE_URL}/api/messages/inbox",
        headers=auth_headers(user_b["token"]),
        verify=VERIFY_SSL,
    )
    assert resp.status_code == 200
    messages = resp.json()["data"]
    assert any(m["messageId"] for m in messages)


def test_inbox_requires_auth():
    resp = requests.get(f"{BASE_URL}/api/messages/inbox", verify=VERIFY_SSL)
    assert resp.status_code == 401


def test_sent_contains_sent_message(user_a, user_b):
    send_msg(user_a["token"], user_b["user_id"], "sent test")
    resp = requests.get(
        f"{BASE_URL}/api/messages/sent",
        headers=auth_headers(user_a["token"]),
        verify=VERIFY_SSL,
    )
    assert resp.status_code == 200
    messages = resp.json()["data"]
    assert len(messages) >= 1


def test_sent_requires_auth():
    resp = requests.get(f"{BASE_URL}/api/messages/sent", verify=VERIFY_SSL)
    assert resp.status_code == 401


def test_get_message_by_id(user_a, user_b):
    msg_id = send_msg(user_a["token"], user_b["user_id"], "get by id")
    resp = requests.get(
        f"{BASE_URL}/api/messages/{msg_id}",
        headers=auth_headers(user_b["token"]),
        verify=VERIFY_SSL,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["messageId"] == msg_id


def test_get_message_by_id_requires_auth(user_a, user_b):
    msg_id = send_msg(user_a["token"], user_b["user_id"])
    resp = requests.get(f"{BASE_URL}/api/messages/{msg_id}", verify=VERIFY_SSL)
    assert resp.status_code == 401


def test_get_message_unauthorized_user_rejected(user_a, user_b, user_c):
    msg_id = send_msg(user_a["token"], user_b["user_id"])
    resp = requests.get(
        f"{BASE_URL}/api/messages/{msg_id}",
        headers=auth_headers(user_c["token"]),
        verify=VERIFY_SSL,
    )
    assert resp.status_code in (403, 404)
