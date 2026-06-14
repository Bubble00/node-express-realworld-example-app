# Conduit API Test Suite

Automated tests for [gothinkster/node-express-realworld-example-app](https://github.com/gothinkster/node-express-realworld-example-app) — the Node/Express/Mongoose reference implementation of the RealWorld spec.

My fork: **https://github.com/Bubble00/node-express-realworld-example-app/tree/main**

---

## Why this implementation

I picked the Node/Express backend for three reasons. First, it's the reference implementation — the one most people fork, so findings here have the widest impact. Second, it has zero Python test coverage: the only tests are a Postman/Newman collection, so there was nothing to duplicate or work around. Third, the API surface is well-documented by the RealWorld spec, so I knew exactly what to assert against without reading implementation code.

**Setup note:** The repo's master branch has been updated to a TypeScript/NX monorepo since the original implementation. I pinned to commit `ba04b70` which is the last known working version of the simple Express app. I also had to upgrade Mongoose from 4.4.10 to 5.13.22 — the original driver uses a legacy wire protocol (`OP_QUERY`) that MongoDB 6+ no longer supports. The mongoose connection string was also updated from `localhost` to `127.0.0.1` to force IPv4 on Windows. These changes are committed to the main branch.

---

## What I tested and what I left out

The suite has 22 tests across four files:

- **Auth** (`test_auth.py`) — registration, login, current user, update user. Auth is load-bearing: if tokens are broken, nothing else is testable. Three of the seven tests probe spec compliance rather than just happy paths.
- **Articles** (`test_articles.py`) — create, delete, list, feed. Focused on the three article-specific failure modes most likely in a Mongoose codebase: slug uniqueness, async delete consistency, and the `limit` param.
- **Comments + Favorites** (`test_comments_and_favorites.py`) — combined into one file because both are thin resource layers. The interesting cases are ownership enforcement on delete and idempotency on favorite.
- **E2E flows** (`test_e2e_flows.py`) — three self-contained user journeys: a full publish/comment/edit/delete lifecycle; a follow → feed → unfollow social flow; and an adversarial authorization probe where a second user attempts every write operation on the first user's content.

**Deliberately left out:** GET /tags (read-only, no auth, no interesting edge cases), article update shape tests (redundant with create), profile GET (public read with no ownership logic), and pagination offset (needs a seeded dataset to test reliably).

---

## Bugs found

Two bugs were caught by failing tests, confirmed against the running server:

| # | Endpoint | What happens | Severity | Test |
|---|----------|--------------|----------|------|
| BUG-1 | `GET /user` with `Bearer` scheme | Server accepts `Bearer <jwt>` instead of rejecting it. The RealWorld spec mandates `Token <jwt>` only. Clients that strictly follow the spec and send `Token` would be fine, but the server silently accepts the wrong scheme — a spec deviation that could mask auth middleware misconfiguration. | Medium | `test_token_scheme_must_be_Token_not_Bearer` |
| BUG-2 | `POST /articles/:slug/comments` with empty body | An empty string comment body (`""`) is accepted with 200. The Mongoose schema requires a body field but doesn't validate that the value is non-empty. Blank comments can be created and persist in the database. | Medium | `test_empty_comment_body_is_rejected` |

20 out of 22 tests pass — the 2 failures are genuine defects, not test issues.

---

## How I used AI agents

I used Claude (claude.ai) throughout this exercise.

**Where it helped:** Scaffolding the conftest fixtures and session/header helpers was fast — the boilerplate is mechanical and Claude got it right first time. It also helped reason through which bugs are structurally likely in a Node/Mongoose codebase (missing unique constraints, unawaited async operations, ORM validation gaps) before running a single test.

**Where it produced something wrong or low-quality:** The first draft contained 73 tests. That's the agent optimizing for coverage metrics rather than the brief. The majority were shape assertions (`assert "slug" in article`) that confirm the implementation works as documented — not useful for finding defects. I rejected most of them and cut to 22 focused tests.

**One decision where I overrode the agent:** Claude initially generated `test_tags.py` as a standalone file. I cut it entirely. The `/tags` endpoint is a read-only GET with no auth, no ownership, and no write path — there's almost nothing to break there that wouldn't already surface in an article test. The agent doesn't weigh the cost of maintaining a test against its likelihood of catching a real defect. I do.

---

## Testing non-deterministic AI features

If Conduit added an LLM feature — say, auto-summarizing articles or suggesting tags — I wouldn't assert on exact output. Instead I'd test the contract around the feature: that a summary is returned within a reasonable length bound, that it contains at least one noun from the article title (a minimal coherence check), that it doesn't echo the full article body verbatim, and that the response arrives within an acceptable latency threshold. For tag suggestions I'd assert that the returned tags are strings, that there are between 1 and 5 of them, and that none are empty or duplicates — structural validity rather than semantic correctness. For regression I'd build a small golden-set eval: a fixed set of articles where a human has rated acceptable outputs, and run the LLM responses through a lightweight judge model that scores relevance on a rubric rather than exact match. The test suite catches structural breakage; the eval catches quality drift.

---

## What I'd do with more time

- **Wire up CI** — GitHub Actions workflow to spin up MongoDB, start the Node server, and run pytest on every push.
- **Seed a dataset and test pagination properly** — offset/limit tests are unreliable without controlling the data they page over.
- **Wire up contract testing against the OpenAPI spec** — `schemathesis` can generate property-based tests directly from the spec YAML and would catch response shape violations automatically.
- **Add a performance baseline** — the async delete bug is timing-dependent. A test with a short retry loop would be more reliable than a single immediate GET.

---

## Running the tests

```bash
# Requirements: Node.js, MongoDB 6, Python 3.x

# 1. Start MongoDB (as a service or manually)
# 2. Start the server
npm install
node app.js

# 3. In a second terminal, run the tests
pip install -r requirements.txt
pytest tests/ -v
```