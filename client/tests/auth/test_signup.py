import requests
from helpers import make_credentials, BASE_URL, VERIFY_SSL


def test_register_success():
    username, password = make_credentials()
    resp = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={"username": username, "password": password},
        verify=VERIFY_SSL,
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["username"] == username
    assert "userId" in data


def test_register_duplicate_username_rejected():
    username, password = make_credentials()
    requests.post(
        f"{BASE_URL}/api/auth/register",
        json={"username": username, "password": password},
        verify=VERIFY_SSL,
    ).raise_for_status()

    resp = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={"username": username, "password": password},
        verify=VERIFY_SSL,
    )
    assert resp.status_code == 409


def test_register_short_password_rejected():
    username, _ = make_credentials()
    resp = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={"username": username, "password": "short"},
        verify=VERIFY_SSL,
    )
    assert resp.status_code == 400
