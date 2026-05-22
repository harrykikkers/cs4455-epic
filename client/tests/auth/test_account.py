import pytest
import requests
from helpers import make_credentials, register_and_login, auth_headers, BASE_URL, VERIFY_SSL


def test_me_returns_user_profile(user_a):
    resp = requests.get(
        f"{BASE_URL}/api/auth/me",
        headers=auth_headers(user_a["token"]),
        verify=VERIFY_SSL,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["username"] == user_a["username"]


def test_me_requires_auth():
    resp = requests.get(f"{BASE_URL}/api/auth/me", verify=VERIFY_SSL)
    assert resp.status_code == 401


def test_change_password_success(user_a):
    resp = requests.put(
        f"{BASE_URL}/api/auth/password",
        json={"currentPassword": "TestPassword123!", "newPassword": "NewPassword456!"},
        headers=auth_headers(user_a["token"]),
        verify=VERIFY_SSL,
    )
    assert resp.status_code == 200


def test_change_password_wrong_current_rejected(user_a):
    resp = requests.put(
        f"{BASE_URL}/api/auth/password",
        json={"currentPassword": "WrongPassword!", "newPassword": "NewPassword456!"},
        headers=auth_headers(user_a["token"]),
        verify=VERIFY_SSL,
    )
    assert resp.status_code in (400, 401)


def test_change_password_requires_auth():
    resp = requests.put(
        f"{BASE_URL}/api/auth/password",
        json={"currentPassword": "TestPassword123!", "newPassword": "NewPassword456!"},
        verify=VERIFY_SSL,
    )
    assert resp.status_code == 401


@pytest.mark.skip(reason="TODO: key registration flow not yet implemented on client — register should POST /api/keys with generated public key")
def test_register_uploads_public_key():
    username, password = make_credentials()
    register_and_login(username, password)
    # after real crypto is added, registration should auto-upload the public key
