import pytest
from helpers import make_credentials, register_and_login


@pytest.fixture
def user_a():
    u, p = make_credentials()
    token, uid, username = register_and_login(u, p)
    return {"token": token, "user_id": uid, "username": username}


@pytest.fixture
def user_b():
    u, p = make_credentials()
    token, uid, username = register_and_login(u, p)
    return {"token": token, "user_id": uid, "username": username}


@pytest.fixture
def user_c():
    u, p = make_credentials()
    token, uid, username = register_and_login(u, p)
    return {"token": token, "user_id": uid, "username": username}
