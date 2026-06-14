"""
test_e2e_flows.py
-----------------
Three end-to-end flows written as user stories, not unit tests.
Each is fully self-contained so failures are unambiguous.
No fixtures — the setup is part of the story.

FLOW 1: Full content lifecycle
  Register → login → publish → comment → edit → delete comment → delete article

FLOW 2: Social graph + feed
  User A publishes → User B follows → feed shows A's article →
  B unfollows → article disappears from feed

FLOW 3: Authorization cannot be bypassed
  User A publishes → User B attempts every write on A's content →
  all rejected → A's content is still intact

These flows catch two bugs the unit tests cannot easily isolate:

  BUG-SLUG-REGEN: PUT /articles/:slug with a new title regenerates the slug.
  The response returns the new slug but the test client (and real frontends)
  still hold the old one. The article becomes unreachable without a redirect.

  BUG-FEED-STALE: After unfollow, GET /articles/feed still returns articles
  from the unfollowed user because the feed query uses a cached join result.
"""

import uuid
import requests
from conftest import url, token_header


def uid():
    return uuid.uuid4().hex[:8]


def make_user():
    """Register a user and return (user_dict, authed Session)."""
    s = uid()
    resp = requests.post(url("/users"), json={"user": {
        "username": f"e2e{s}", "email": f"e2e{s}@test.com", "password": "Password1!"
    }})
    assert resp.status_code in (200, 201), f"Registration failed: {resp.text}"
    user = resp.json()["user"]
    sess = requests.Session()
    sess.headers.update(token_header(user["token"]))
    return user, sess


def make_article(sess, title=None):
    s = uid()
    resp = sess.post(url("/articles"), json={"article": {
        "title": title or f"E2E {s}",
        "description": "desc",
        "body": "body",
    }})
    assert resp.status_code in (200, 201), f"Article creation failed: {resp.text}"
    return resp.json()["article"]


# ---------------------------------------------------------------------------
# Flow 1: Full content lifecycle
# ---------------------------------------------------------------------------

def test_flow_publish_comment_edit_delete():
    user, sess = make_user()

    # Re-login to verify the token from registration is consistent with login
    login_resp = requests.post(url("/users/login"), json={
        "user": {"email": user["email"], "password": "Password1!"}
    })
    assert login_resp.status_code == 200
    sess.headers.update(token_header(login_resp.json()["user"]["token"]))

    # Publish
    art = make_article(sess)
    slug = art["slug"]
    assert requests.get(url(f"/articles/{slug}")).status_code == 200

    # Comment
    c_resp = sess.post(url(f"/articles/{slug}/comments"),
                       json={"comment": {"body": "first comment"}})
    assert c_resp.status_code in (200, 201)
    cid = c_resp.json()["comment"]["id"]

    # Edit body only — deliberately avoid title change to isolate BUG-SLUG-REGEN
    upd = sess.put(url(f"/articles/{slug}"), json={"article": {"body": "updated body"}})
    assert upd.status_code == 200
    assert requests.get(url(f"/articles/{slug}")).status_code == 200, (
        "Article became unreachable after a body-only update"
    )

    # Edit title — slug may be regenerated
    new_title = f"New Title {uid()}"
    title_upd = sess.put(url(f"/articles/{slug}"), json={"article": {"title": new_title}})
    assert title_upd.status_code == 200
    new_slug = title_upd.json()["article"]["slug"]
    # BUG-SLUG-REGEN: if slug changed, old slug must redirect or the article is lost
    if new_slug != slug:
        old_still_works = requests.get(url(f"/articles/{slug}")).status_code
        assert old_still_works in (200, 301, 302), (
            f"BUG-SLUG-REGEN: Title update changed slug from '{slug}' to '{new_slug}' "
            f"but old slug now returns {old_still_works}. Article is unreachable to clients "
            f"holding the original slug."
        )
    slug = new_slug  # use whatever slug is canonical going forward

    # Delete comment
    del_c = sess.delete(url(f"/articles/{slug}/comments/{cid}"))
    assert del_c.status_code in (200, 204)

    # Delete article
    del_a = sess.delete(url(f"/articles/{slug}"))
    assert del_a.status_code in (200, 204)
    assert requests.get(url(f"/articles/{slug}")).status_code == 404


# ---------------------------------------------------------------------------
# Flow 2: Social graph and feed
# ---------------------------------------------------------------------------

def test_flow_follow_feed_unfollow():
    user_a, sess_a = make_user()
    user_b, sess_b = make_user()

    art = make_article(sess_a)

    # Before following: B's feed should not contain A's article
    feed_before = [a["slug"] for a in sess_b.get(url("/articles/feed")).json()["articles"]]
    assert art["slug"] not in feed_before

    # B follows A
    follow = sess_b.post(url(f"/profiles/{user_a['username']}/follow"))
    assert follow.status_code == 200
    assert follow.json()["profile"]["following"] is True

    # Feed now includes A's article
    feed_after = [a["slug"] for a in sess_b.get(url("/articles/feed")).json()["articles"]]
    assert art["slug"] in feed_after, "Article from followed user missing from feed"

    # B unfollows A
    unfollow = sess_b.delete(url(f"/profiles/{user_a['username']}/follow"))
    assert unfollow.status_code == 200
    assert unfollow.json()["profile"]["following"] is False

    # Feed should no longer contain A's article
    feed_final = [a["slug"] for a in sess_b.get(url("/articles/feed")).json()["articles"]]
    assert art["slug"] not in feed_final, (
        f"BUG-FEED-STALE: Article from unfollowed user {user_a['username']} "
        f"still appears in feed after unfollow"
    )


# ---------------------------------------------------------------------------
# Flow 3: Authorization cannot be bypassed
# ---------------------------------------------------------------------------

def test_flow_authorization_holds_under_attack():
    user_a, sess_a = make_user()
    user_b, sess_b = make_user()

    art = make_article(sess_a)
    slug = art["slug"]

    c_resp = sess_a.post(url(f"/articles/{slug}/comments"),
                         json={"comment": {"body": "A's comment"}})
    assert c_resp.status_code in (200, 201)
    cid = c_resp.json()["comment"]["id"]

    # B tries every write on A's content
    assert sess_b.put(url(f"/articles/{slug}"),
                      json={"article": {"title": "Hijacked"}}).status_code in (401, 403), \
        "BUG: B edited A's article"

    assert sess_b.delete(url(f"/articles/{slug}")).status_code in (401, 403), \
        "BUG: B deleted A's article"

    assert sess_b.delete(url(f"/articles/{slug}/comments/{cid}")).status_code in (401, 403), \
        "BUG: B deleted A's comment"

    # A's content must be completely intact
    get = requests.get(url(f"/articles/{slug}"))
    assert get.status_code == 200, "Article gone after failed attacks"
    assert get.json()["article"]["title"] == art["title"], "Title silently changed"

    comments = requests.get(url(f"/articles/{slug}/comments")).json()["comments"]
    assert any(c["id"] == cid for c in comments), "Comment gone after failed attacks"