"""
test_comments_and_favorites.py
-------------------------------
Comments and favorites together — both are thin resource layers on top of
articles. We skip shape tests and go straight to ownership and idempotency,
which is where these implementations typically slip.
"""

import requests
from conftest import url


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------

def test_add_comment_requires_auth(article):
    resp = requests.post(url(f"/articles/{article['slug']}/comments"),
                         json={"comment": {"body": "anon"}})
    assert resp.status_code == 401


def test_empty_comment_body_is_rejected(session, article):
    """
    PROBING BUG: Blank body passes through because the ORM treats empty
    string differently from null. The validation middleware only checks
    for missing keys, not empty values.
    """
    resp = session.post(url(f"/articles/{article['slug']}/comments"),
                        json={"comment": {"body": ""}})
    assert resp.status_code in (400, 422), (
        f"BUG: Empty comment body accepted with {resp.status_code}"
    )


def test_non_author_cannot_delete_comment(session, other_session, article):
    """
    PROBING BUG: The delete handler checks that the request is authenticated
    but not that the requester owns the comment. Any logged-in user can
    delete anyone else's comments.
    """
    cid = session.post(url(f"/articles/{article['slug']}/comments"),
                       json={"comment": {"body": "mine"}}).json()["comment"]["id"]
    resp = other_session.delete(url(f"/articles/{article['slug']}/comments/{cid}"))
    assert resp.status_code in (401, 403), (
        f"BUG: Non-author deleted a comment and got {resp.status_code}"
    )


# ---------------------------------------------------------------------------
# Favorites
# ---------------------------------------------------------------------------

def test_favorite_requires_auth(article):
    assert requests.post(url(f"/articles/{article['slug']}/favorite")).status_code == 401


def test_double_favorite_does_not_inflate_count(other_session, article):
    """
    PROBING BUG: If the favorites table lacks a unique constraint on
    (user_id, article_id), favoriting twice creates two rows and the
    count returns +2 instead of +1.
    """
    slug = article["slug"]
    initial = article["favoritesCount"]
    other_session.post(url(f"/articles/{slug}/favorite"))
    resp = other_session.post(url(f"/articles/{slug}/favorite"))
    assert resp.status_code == 200
    count = resp.json()["article"]["favoritesCount"]
    assert count == initial + 1, (
        f"BUG: Double-favorite inflated count to {count} (expected {initial + 1})"
    )


def test_unfavorite_count_does_not_go_negative(other_session, article):
    """
    PROBING BUG: Unfavoriting an article never favorited runs a decrement
    with no guard, pushing the count below zero.
    """
    resp = other_session.delete(url(f"/articles/{article['slug']}/favorite"))
    if resp.status_code == 200:
        count = resp.json()["article"]["favoritesCount"]
        assert count >= 0, f"BUG: favoritesCount went negative ({count})"