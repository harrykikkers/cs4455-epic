import os
import base64
import uuid
import requests

from config import BASE_URL, VERIFY_SSL


def dummy_msg_fields():
    b64 = lambda b: base64.b64encode(b).decode()
    return {
        "enc": b64(os.urandom(32)),
        "ciphertext": b64(os.urandom(64)),
        "nonce": b64(os.urandom(12)),
        "signature": b64(os.urandom(64)),
        "seqNo": 0,
        "digest": "0x" + "00" * 32,
    }


def make_credentials():
    return "test_" + uuid.uuid4().hex[:8], "TestPassword123!"


def register_and_login(username, password):
    requests.post(
        f"{BASE_URL}/api/auth/register",
        json={"username": username, "password": password},
        verify=VERIFY_SSL,
    ).raise_for_status()
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"username": username, "password": password},
        verify=VERIFY_SSL,
    )
    resp.raise_for_status()
    data = resp.json()["data"]
    return data["token"], data["user"]["userId"], data["user"]["username"]


def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def send_msg(sender_token, recipient_id, text="hello"):
    payload = {"recipientId": recipient_id, **dummy_msg_fields()}
    resp = requests.post(
        f"{BASE_URL}/api/messages",
        json=payload,
        headers=auth_headers(sender_token),
        verify=VERIFY_SSL,
    )
    resp.raise_for_status()
    return resp.json()["data"]["messageId"]
