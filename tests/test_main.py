"""
Unit tests for app/main.py — FastAPI routes.

Covers:
- GET  /                    — dashboard renders topics and runs
- POST /topics              — blank topic → 422, valid topic → redirect
- DELETE /topics/{id}       — deletes topic
- POST /topics/{id}/run     — triggers run, unknown topic → 404
- GET  /posts               — lists blog posts
- GET  /posts/{id}          — view post, unknown → 404
- GET  /posts/{id}/edit     — edit form, unknown → 404
- POST /posts/{id}/edit     — save edit, unknown → 404
- GET  /api/runs/{id}/status — JSON shape, unknown → 404

Validates: Requirements 1.1, 1.3, 4.1, 5.1
"""

import os
import uuid
from unittest.mock import MagicMock

import pytest

# Set env vars before any app imports
os.environ.setdefault("SERPER_API_KEY", "test-serper-key")
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from sqlalchemy import create_engine, StaticPool
from sqlalchemy.orm import sessionmaker

from app.models import Base, RunStatus

# ---------------------------------------------------------------------------
# Shared in-memory engine for all tests in this module
# Use StaticPool so all connections share the same in-memory database
# ---------------------------------------------------------------------------

_TEST_ENGINE = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Base.metadata.create_all(_TEST_ENGINE)
_TestSessionFactory = sessionmaker(bind=_TEST_ENGINE)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def patch_store_db():
    """Redirect all store calls to the shared in-memory SQLite DB."""
    import app.store as store_mod
    import app.database as db_mod

    # Patch both the store's _session and the database's SessionLocal
    original_session = store_mod._session
    original_session_local = db_mod.SessionLocal

    store_mod._session = lambda: _TestSessionFactory()
    db_mod.SessionLocal = _TestSessionFactory

    yield store_mod

    store_mod._session = original_session
    db_mod.SessionLocal = original_session_local


@pytest.fixture(autouse=True)
def clean_db():
    """Wipe all rows between tests."""
    yield
    from app.models import BlogPost, Run, Topic
    session = _TestSessionFactory()
    try:
        session.query(BlogPost).delete()
        session.query(Run).delete()
        session.query(Topic).delete()
        session.commit()
    finally:
        session.close()


@pytest.fixture()
def client(patch_store_db):
    """Return a synchronous TestClient for the FastAPI app."""
    from fastapi.testclient import TestClient
    import app.main as main_mod

    mock_exec = MagicMock()
    mock_exec.submit = MagicMock()
    original_executor = main_mod._executor
    main_mod._executor = mock_exec
    with TestClient(main_mod.app, raise_server_exceptions=True) as c:
        yield c, mock_exec
    main_mod._executor = original_executor


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

class TestDashboard:
    def test_get_root_returns_200(self, client):
        c, _ = client
        resp = c.get("/")
        assert resp.status_code == 200

    def test_dashboard_contains_form(self, client):
        c, _ = client
        resp = c.get("/")
        assert "topic_text" in resp.text


# ---------------------------------------------------------------------------
# Topic creation
# ---------------------------------------------------------------------------

class TestCreateTopic:
    def test_blank_topic_returns_422(self, client):
        c, _ = client
        resp = c.post("/topics", data={"topic_text": ""}, follow_redirects=False)
        assert resp.status_code == 422

    def test_whitespace_only_topic_returns_422(self, client):
        c, _ = client
        resp = c.post("/topics", data={"topic_text": "   "}, follow_redirects=False)
        assert resp.status_code == 422

    def test_valid_topic_redirects(self, client):
        c, _ = client
        resp = c.post("/topics", data={"topic_text": "AI trends"}, follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"] == "/"

    def test_topic_over_200_chars_returns_422(self, client):
        c, _ = client
        long_text = "x" * 201
        resp = c.post("/topics", data={"topic_text": long_text}, follow_redirects=False)
        assert resp.status_code == 422

    def test_valid_topic_appears_in_dashboard(self, client):
        c, _ = client
        c.post("/topics", data={"topic_text": "Quantum computing"})
        resp = c.get("/")
        assert "Quantum computing" in resp.text


# ---------------------------------------------------------------------------
# Topic deletion
# ---------------------------------------------------------------------------

class TestDeleteTopic:
    def test_delete_topic_via_form_post(self, client, patch_store_db):
        c, _ = client
        topic = patch_store_db.create_topic("To delete")
        resp = c.post(f"/topics/{topic.id}/delete", follow_redirects=False)
        assert resp.status_code == 303
        topics = patch_store_db.list_topics()
        assert all(t.id != topic.id for t in topics)

    def test_delete_topic_via_rest(self, client, patch_store_db):
        c, _ = client
        topic = patch_store_db.create_topic("To delete REST")
        resp = c.delete(f"/topics/{topic.id}", follow_redirects=False)
        assert resp.status_code == 303
        topics = patch_store_db.list_topics()
        assert all(t.id != topic.id for t in topics)


# ---------------------------------------------------------------------------
# Trigger run
# ---------------------------------------------------------------------------

class TestTriggerRun:
    def test_trigger_run_redirects(self, client, patch_store_db):
        c, mock_exec = client
        topic = patch_store_db.create_topic("AI news")
        resp = c.post(f"/topics/{topic.id}/run", follow_redirects=False)
        assert resp.status_code == 303

    def test_trigger_run_dispatches_worker(self, client, patch_store_db):
        c, mock_exec = client
        topic = patch_store_db.create_topic("AI news")
        c.post(f"/topics/{topic.id}/run", follow_redirects=False)
        assert mock_exec.submit.called

    def test_trigger_run_unknown_topic_returns_404(self, client):
        c, _ = client
        resp = c.post(f"/topics/{uuid.uuid4()}/run", follow_redirects=False)
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Blog post list
# ---------------------------------------------------------------------------

class TestListPosts:
    def test_get_posts_returns_200(self, client):
        c, _ = client
        resp = c.get("/posts")
        assert resp.status_code == 200

    def test_posts_page_shows_posts(self, client, patch_store_db):
        c, _ = client
        topic = patch_store_db.create_topic("Test topic")
        run = patch_store_db.create_run(topic.id)
        patch_store_db.save_blog_post(run.id, topic.id, "My Post Title", "# My Post Title\n\nBody.")
        resp = c.get("/posts")
        assert "My Post Title" in resp.text


# ---------------------------------------------------------------------------
# View post
# ---------------------------------------------------------------------------

class TestViewPost:
    def test_view_existing_post_returns_200(self, client, patch_store_db):
        c, _ = client
        topic = patch_store_db.create_topic("Test topic")
        run = patch_store_db.create_run(topic.id)
        post = patch_store_db.save_blog_post(run.id, topic.id, "Hello", "# Hello\n\nWorld.")
        resp = c.get(f"/posts/{post.id}")
        assert resp.status_code == 200
        assert "Hello" in resp.text

    def test_view_unknown_post_returns_404(self, client):
        c, _ = client
        resp = c.get(f"/posts/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_view_post_renders_markdown(self, client, patch_store_db):
        c, _ = client
        topic = patch_store_db.create_topic("Test topic")
        run = patch_store_db.create_run(topic.id)
        post = patch_store_db.save_blog_post(run.id, topic.id, "MD Test", "# MD Test\n\n**bold text**")
        resp = c.get(f"/posts/{post.id}")
        assert "<strong>" in resp.text or "<b>" in resp.text


# ---------------------------------------------------------------------------
# Edit post
# ---------------------------------------------------------------------------

class TestEditPost:
    def test_edit_form_returns_200(self, client, patch_store_db):
        c, _ = client
        topic = patch_store_db.create_topic("Test topic")
        run = patch_store_db.create_run(topic.id)
        post = patch_store_db.save_blog_post(run.id, topic.id, "Edit Me", "# Edit Me\n\nOriginal.")
        resp = c.get(f"/posts/{post.id}/edit")
        assert resp.status_code == 200
        assert "Original." in resp.text

    def test_edit_form_unknown_post_returns_404(self, client):
        c, _ = client
        resp = c.get(f"/posts/{uuid.uuid4()}/edit")
        assert resp.status_code == 404

    def test_save_edit_redirects(self, client, patch_store_db):
        c, _ = client
        topic = patch_store_db.create_topic("Test topic")
        run = patch_store_db.create_run(topic.id)
        post = patch_store_db.save_blog_post(run.id, topic.id, "Edit Me", "# Edit Me\n\nOriginal.")
        resp = c.post(f"/posts/{post.id}/edit", data={"body_md": "# Edit Me\n\nUpdated."}, follow_redirects=False)
        assert resp.status_code == 303

    def test_save_edit_persists_content(self, client, patch_store_db):
        c, _ = client
        topic = patch_store_db.create_topic("Test topic")
        run = patch_store_db.create_run(topic.id)
        post = patch_store_db.save_blog_post(run.id, topic.id, "Edit Me", "# Edit Me\n\nOriginal.")
        c.post(f"/posts/{post.id}/edit", data={"body_md": "# Edit Me\n\nUpdated."})
        updated = patch_store_db.get_blog_post(post.id)
        assert "Updated." in updated.body_md

    def test_save_edit_unknown_post_returns_404(self, client):
        c, _ = client
        resp = c.post(f"/posts/{uuid.uuid4()}/edit", data={"body_md": "new content"}, follow_redirects=False)
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Run status API
# ---------------------------------------------------------------------------

class TestRunStatusAPI:
    def test_status_endpoint_returns_json(self, client, patch_store_db):
        c, _ = client
        topic = patch_store_db.create_topic("Test topic")
        run = patch_store_db.create_run(topic.id)
        resp = c.get(f"/api/runs/{run.id}/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert "error_msg" in data

    def test_status_endpoint_returns_correct_status(self, client, patch_store_db):
        c, _ = client
        topic = patch_store_db.create_topic("Test topic")
        run = patch_store_db.create_run(topic.id)
        resp = c.get(f"/api/runs/{run.id}/status")
        data = resp.json()
        assert data["status"] == "pending"

    def test_status_endpoint_unknown_run_returns_404(self, client):
        c, _ = client
        resp = c.get(f"/api/runs/{uuid.uuid4()}/status")
        assert resp.status_code == 404

    def test_status_endpoint_error_msg_null_when_no_error(self, client, patch_store_db):
        c, _ = client
        topic = patch_store_db.create_topic("Test topic")
        run = patch_store_db.create_run(topic.id)
        resp = c.get(f"/api/runs/{run.id}/status")
        data = resp.json()
        assert data["error_msg"] is None

    def test_status_endpoint_shows_error_msg_on_failure(self, client, patch_store_db):
        c, _ = client
        topic = patch_store_db.create_topic("Test topic")
        run = patch_store_db.create_run(topic.id)
        patch_store_db.update_run_status(run.id, "running")
        patch_store_db.update_run_status(run.id, "failed", error_msg="Something went wrong")
        resp = c.get(f"/api/runs/{run.id}/status")
        data = resp.json()
        assert data["status"] == "failed"
        assert data["error_msg"] == "Something went wrong"


# ---------------------------------------------------------------------------
# Markdown rendering — subtask 9.1
# Validates: Requirements 4.2
# ---------------------------------------------------------------------------

class TestMarkdownRendering:
    """Unit tests for server-side Markdown rendering via the `markdown` library."""

    def test_heading_renders_as_h1(self):
        import markdown as md_lib
        result = md_lib.markdown("# Hello World")
        assert "<h1>" in result
        assert "Hello World" in result

    def test_bold_renders_as_strong(self):
        import markdown as md_lib
        result = md_lib.markdown("**bold text**")
        assert "<strong>" in result
        assert "bold text" in result

    def test_paragraph_renders_as_p(self):
        import markdown as md_lib
        result = md_lib.markdown("This is a paragraph.")
        assert "<p>" in result
        assert "This is a paragraph." in result

    def test_multiple_headings_render(self):
        import markdown as md_lib
        md = "# Title\n\n## Section 1\n\n### Subsection\n\n## Section 2"
        result = md_lib.markdown(md)
        assert "<h1>" in result
        assert "<h2>" in result
        assert "<h3>" in result

    def test_full_blog_post_structure_renders(self, client, patch_store_db):
        """End-to-end: a post with Markdown body renders headings and bold in the view."""
        c, _ = client
        topic = patch_store_db.create_topic("Rendering test")
        run = patch_store_db.create_run(topic.id)
        body = "# My Title\n\nIntro paragraph.\n\n## Section 1\n\n**Important** detail.\n\n## Conclusion\n\nDone."
        post = patch_store_db.save_blog_post(run.id, topic.id, "My Title", body)
        resp = c.get(f"/posts/{post.id}")
        assert resp.status_code == 200
        assert "<h2>" in resp.text
        assert "<strong>" in resp.text
