import requests
from helpers import auth_headers, send_msg, dummy_msg_fields, BASE_URL, VERIFY_SSL


def test_send_message_success(user_a, user_b):
    msg_id = send_msg(user_a["token"], user_b["user_id"])
    assert msg_id


def test_send_message_returns_201(user_a, user_b):
    payload = {"recipientId": user_b["user_id"], **dummy_msg_fields()}
    resp = requests.post(
        f"{BASE_URL}/api/messages",
        json=payload,
        headers=auth_headers(user_a["token"]),
        verify=VERIFY_SSL,
    )
    assert resp.status_code == 201
    assert "messageId" in resp.json()["data"]


def test_send_message_requires_auth(user_b):
    payload = {"recipientId": user_b["user_id"], **dummy_msg_fields()}
    resp = requests.post(
        f"{BASE_URL}/api/messages",
        json=payload,
        verify=VERIFY_SSL,
    )
    assert resp.status_code == 401


def test_send_to_nonexistent_user_rejected(user_a):
    payload = {"recipientId": 999999999, **dummy_msg_fields()}
    resp = requests.post(
        f"{BASE_URL}/api/messages",
        json=payload,
        headers=auth_headers(user_a["token"]),
        verify=VERIFY_SSL,
    )
    assert resp.status_code in (400, 404)
