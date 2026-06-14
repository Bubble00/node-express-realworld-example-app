"""
conftest.py — shared helpers and fixtures.

Set CONDUIT_BASE_URL to point at your running server:
    export CONDUIT_BASE_URL=http://localhost:3000/api
    pytest -v
"""

import os
import uuid
import pytest
import requests

BASE_URL = os.getenv("CONDUIT_BASE_URL", "http://localhost:3000/api")


def uid():
    return uuid.uuid4().hex[:8]


def url(path):
    return f"{BASE_URL}{path}"


def token_header(token):
    return {"Authorization": f"Token {token}"}


def register(username, email, password):
    return requests.post(url("/users"), json={
        "user": {"username": username, "email": email, "password": password}
    })


def login(email, password):
    return requests.post(url("/users/login"), json={
        "user": {"email": email, "password": password}
    })


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def user_payload():
    s = uid()
    return {"username": f"user{s}", "email": f"user{s}@test.com", "password": "Password1!"}


@pytest.fixture()
def registered_user(user_payload):
    resp = register(**user_payload)
    assert resp.status_code in (200, 201), resp.text
    u = resp.json()["user"]
    u["_password"] = user_payload["password"]
    return u


@pytest.fixture()
def session(registered_user):
    s = requests.Session()
    s.headers.update(token_header(registered_user["token"]))
    return s


@pytest.fixture()
def other_user():
    s = uid()
    resp = register(f"other{s}", f"other{s}@test.com", "Password1!")
    assert resp.status_code in (200, 201), resp.text
    u = resp.json()["user"]
    u["_password"] = "Password1!"
    return u


@pytest.fixture()
def other_session(other_user):
    s = requests.Session()
    s.headers.update(token_header(other_user["token"]))
    return s


@pytest.fixture()
def article(session):
    s = uid()
    resp = session.post(url("/articles"), json={"article": {
        "title": f"Article {s}",
        "description": "desc",
        "body": "body",
        "tagList": ["pytest", s],
    }})
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["article"]