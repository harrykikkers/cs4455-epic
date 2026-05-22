import requests
from helpers import make_credentials, register_and_login, BASE_URL, VERIFY_SSL


def test_login_returns_token_and_user():
    username, password = make_credentials()
    token, user_id, uname = register_and_login(username, password)
    assert token and len(token) > 20
    assert user_id
    assert uname == username


def test_login_wrong_password_rejected():
    username, password = make_credentials()
    requests.post(
        f"{BASE_URL}/api/auth/register",
        json={"username": username, "password": password},
        verify=VERIFY_SSL,
    ).raise_for_status()

    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"username": username, "password": "wrongpassword999"},
        verify=VERIFY_SSL,
    )
    assert resp.status_code == 401


def test_login_unknown_user_rejected():
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"username": "ghost_user_xyz", "password": "TestPassword123!"},
        verify=VERIFY_SSL,
    )
    assert resp.status_code == 401
