"""
test_articles.py
----------------
We skip the obvious happy-path shape tests and focus on the three
article-specific bugs this implementation is likely to have.

Endpoints: POST /articles  GET /articles  GET /articles/:slug
           PUT /articles/:slug  DELETE /articles/:slug
"""

import requests
from conftest import url, uid


def test_create_article_requires_auth():
    resp = requests.post(url("/articles"), json={"article": {
        "title": "x", "description": "d", "body": "b"
    }})
    assert resp.status_code == 401


def test_duplicate_title_must_produce_unique_slugs(session):
    """
    PROBING BUG: If slug generation is just title.lower().replace(' ', '-')
    with no uniqueness suffix, the second article shadows the first —
    GET /articles/:slug returns one and the other is permanently unreachable.
    """
    title = f"Same Title {uid()}"
    r1 = session.post(url("/articles"), json={"article": {"title": title, "description": "d", "body": "b"}})
    r2 = session.post(url("/articles"), json={"article": {"title": title, "description": "d", "body": "b"}})
    assert r1.status_code in (200, 201)
    assert r2.status_code in (200, 201)
    slug1 = r1.json()["article"]["slug"]
    slug2 = r2.json()["article"]["slug"]
    assert slug1 != slug2, (
        f"BUG: Both articles got slug '{slug1}'. The first is now unreachable."
    )


def test_deleted_article_is_not_still_accessible(session, article):
    """
    PROBING BUG: Async delete handlers sometimes respond 200 before the
    DB operation completes. The article lingers and GET still returns it.
    """
    session.delete(url(f"/articles/{article['slug']}"))
    resp = requests.get(url(f"/articles/{article['slug']}"))
    assert resp.status_code == 404, (
        f"BUG: Article still accessible after delete (got {resp.status_code})"
    )


def test_non_author_cannot_edit_article(other_session, article):
    resp = other_session.put(url(f"/articles/{article['slug']}"),
                             json={"article": {"title": "Hijacked"}})
    assert resp.status_code in (401, 403)


def test_non_author_cannot_delete_article(other_session, article):
    resp = other_session.delete(url(f"/articles/{article['slug']}"))
    assert resp.status_code in (401, 403)


def test_list_limit_param_is_respected(session):
    """
    PROBING BUG: The limit query param is present in the spec but some
    implementations accept it silently and ignore it, returning all articles.
    """
    for _ in range(3):
        session.post(url("/articles"), json={"article": {
            "title": f"Limit test {uid()}", "description": "d", "body": "b"
        }})
    resp = requests.get(url("/articles?limit=2"))
    assert resp.status_code == 200
    assert len(resp.json()["articles"]) <= 2, (
        f"BUG: limit=2 was ignored, got {len(resp.json()['articles'])} articles"
    )