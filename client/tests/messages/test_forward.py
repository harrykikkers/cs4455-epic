import requests
from helpers import auth_headers, send_msg, dummy_msg_fields, BASE_URL, VERIFY_SSL


def test_forward_message_success(user_a, user_b, user_c):
    msg_id = send_msg(user_a["token"], user_b["user_id"], "to forward")
    fields = dummy_msg_fields()
    resp = requests.post(
        f"{BASE_URL}/api/messages/{msg_id}/forward",
        json={
            "recipientId": user_c["user_id"],
            "enc": fields["enc"],
            "ciphertext": fields["ciphertext"],
            "nonce": fields["nonce"],
        },
        headers=auth_headers(user_b["token"]),
        verify=VERIFY_SSL,
    )
    assert resp.status_code == 201
    assert "id" in resp.json()["data"]


def test_forward_message_requires_auth(user_a, user_b, user_c):
    msg_id = send_msg(user_a["token"], user_b["user_id"])
    fields = dummy_msg_fields()
    resp = requests.post(
        f"{BASE_URL}/api/messages/{msg_id}/forward",
        json={
            "recipientId": user_c["user_id"],
            "enc": fields["enc"],
            "ciphertext": fields["ciphertext"],
            "nonce": fields["nonce"],
        },
        verify=VERIFY_SSL,
    )
    assert resp.status_code == 401


def test_forward_by_non_recipient_rejected(user_a, user_b, user_c):
    msg_id = send_msg(user_a["token"], user_b["user_id"])
    fields = dummy_msg_fields()
    resp = requests.post(
        f"{BASE_URL}/api/messages/{msg_id}/forward",
        json={
            "recipientId": user_c["user_id"],
            "enc": fields["enc"],
            "ciphertext": fields["ciphertext"],
            "nonce": fields["nonce"],
        },
        headers=auth_headers(user_c["token"]),
        verify=VERIFY_SSL,
    )
    assert resp.status_code in (403, 404)
