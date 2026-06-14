"""
test_auth.py
------------
Auth is the foundation — if tokens are broken, nothing else works.
We cover the happy path, the two most likely failure modes, and one
spec-compliance check that the Node/Express implementation gets wrong.

Endpoints: POST /users  POST /users/login  GET /user  PUT /user
"""

import requests
from conftest import url, token_header, register, login, uid


def test_register_and_receive_token(user_payload):
    resp = register(**user_payload)
    assert resp.status_code in (200, 201)
    user = resp.json()["user"]
    assert user["email"] == user_payload["email"]
    assert user.get("token"), "token must be present and non-empty"
    assert "password" not in user


def test_login_with_correct_credentials(registered_user):
    resp = login(registered_user["email"], registered_user["_password"])
    assert resp.status_code == 200
    assert resp.json()["user"].get("token")


def test_login_wrong_password_rejected(registered_user):
    resp = login(registered_user["email"], "WrongPassword!")
    assert resp.status_code in (401, 403, 422)


def test_duplicate_email_returns_422_with_errors_key(registered_user):
    """
    PROBING BUG: The spec mandates the error body is {"errors": {...}}.
    The Node/Express implementation leaks a raw Mongoose validation error
    string instead. Clients that parse the errors key will silently fail.
    """
    resp = register(f"other_{uid()}", registered_user["email"], "Password1!")
    assert resp.status_code == 422
    body = resp.json()
    assert "errors" in body, (
        f"SPEC VIOLATION: 422 body should have 'errors' key, got: {body}"
    )


def test_token_scheme_must_be_Token_not_Bearer(registered_user):
    """
    PROBING BUG: The spec uses 'Token <jwt>' not 'Bearer <jwt>'.
    Some implementations accept both, which is a deviation — clients
    relying on the spec will send 'Token' and may get 401 if the server
    only accepts 'Bearer'.
    """
    token = registered_user["token"]
    good = requests.get(url("/user"), headers={"Authorization": f"Token {token}"})
    bad  = requests.get(url("/user"), headers={"Authorization": f"Bearer {token}"})
    assert good.status_code == 200
    assert bad.status_code == 401, (
        "SPEC DEVIATION: Server accepts Bearer scheme — should only accept Token"
    )


def test_put_user_response_includes_token(session):
    """
    PROBING BUG: Some implementations return 200 from PUT /user but omit
    the token. Any client that refreshes its stored token on update will
    silently lose its session.
    """
    resp = session.put(url("/user"), json={"user": {"bio": "tester"}})
    assert resp.status_code == 200
    assert resp.json()["user"].get("token"), (
        "BUG: PUT /user response missing token — clients will lose their session"
    )


def test_unauthenticated_request_to_protected_endpoint():
    assert requests.get(url("/user")).status_code == 401