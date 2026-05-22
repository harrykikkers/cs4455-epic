import requests
from helpers import auth_headers, send_msg, BASE_URL, VERIFY_SSL


def test_sender_can_delete_message(user_a, user_b):
    msg_id = send_msg(user_a["token"], user_b["user_id"])
    resp = requests.delete(
        f"{BASE_URL}/api/messages/{msg_id}",
        headers=auth_headers(user_a["token"]),
        verify=VERIFY_SSL,
    )
    assert resp.status_code == 200


def test_delete_requires_auth(user_a, user_b):
    msg_id = send_msg(user_a["token"], user_b["user_id"])
    resp = requests.delete(f"{BASE_URL}/api/messages/{msg_id}", verify=VERIFY_SSL)
    assert resp.status_code == 401


def test_non_sender_cannot_delete(user_a, user_b, user_c):
    msg_id = send_msg(user_a["token"], user_b["user_id"])
    resp = requests.delete(
        f"{BASE_URL}/api/messages/{msg_id}",
        headers=auth_headers(user_c["token"]),
        verify=VERIFY_SSL,
    )
    assert resp.status_code in (403, 404)


def test_deleted_message_not_accessible(user_a, user_b):
    msg_id = send_msg(user_a["token"], user_b["user_id"])
    requests.delete(
        f"{BASE_URL}/api/messages/{msg_id}",
        headers=auth_headers(user_a["token"]),
        verify=VERIFY_SSL,
    ).raise_for_status()

    resp = requests.get(
        f"{BASE_URL}/api/messages/{msg_id}",
        headers=auth_headers(user_b["token"]),
        verify=VERIFY_SSL,
    )
    assert resp.status_code in (403, 404)
