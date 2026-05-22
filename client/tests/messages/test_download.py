import pytest
import requests
from helpers import auth_headers, send_msg, BASE_URL, VERIFY_SSL


def test_chain_proof_accessible_by_recipient(user_a, user_b):
    msg_id = send_msg(user_a["token"], user_b["user_id"])
    resp = requests.get(
        f"{BASE_URL}/api/messages/{msg_id}/chain",
        headers=auth_headers(user_b["token"]),
        verify=VERIFY_SSL,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["messageId"] == msg_id
    assert "digestHash" in data
    assert "chainStatus" in data


def test_chain_proof_accessible_by_sender(user_a, user_b):
    msg_id = send_msg(user_a["token"], user_b["user_id"])
    resp = requests.get(
        f"{BASE_URL}/api/messages/{msg_id}/chain",
        headers=auth_headers(user_a["token"]),
        verify=VERIFY_SSL,
    )
    assert resp.status_code == 200


def test_chain_proof_requires_auth(user_a, user_b):
    msg_id = send_msg(user_a["token"], user_b["user_id"])
    resp = requests.get(
        f"{BASE_URL}/api/messages/{msg_id}/chain",
        verify=VERIFY_SSL,
    )
    assert resp.status_code == 401


def test_chain_proof_unauthorized_user_rejected(user_a, user_b, user_c):
    msg_id = send_msg(user_a["token"], user_b["user_id"])
    resp = requests.get(
        f"{BASE_URL}/api/messages/{msg_id}/chain",
        headers=auth_headers(user_c["token"]),
        verify=VERIFY_SSL,
    )
    assert resp.status_code in (403, 404)


@pytest.mark.skip(reason="TODO: requires Sepolia blockchain connection — txHash is null until on-chain write confirms")
def test_chain_proof_tx_hash_present(user_a, user_b):
    msg_id = send_msg(user_a["token"], user_b["user_id"])
    resp = requests.get(
        f"{BASE_URL}/api/messages/{msg_id}/chain",
        headers=auth_headers(user_b["token"]),
        verify=VERIFY_SSL,
    )
    data = resp.json()["data"]
    assert data["txHash"] is not None
    assert data["chainStatus"] == "recorded"
