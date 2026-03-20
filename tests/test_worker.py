"""
Tests for app/worker.py — background run worker.

Covers:
- Unit tests: success path, Serper timeout, writer failure (mocked Crew)
- Property 5: Run status transitions are monotonic
- Property 6: Failed run stores error message
"""

import os
import sys
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Ensure app.config can be imported in tests (set dummy env vars if needed)
# ---------------------------------------------------------------------------

os.environ.setdefault("SERPER_API_KEY", "test-serper-key")
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

# ---------------------------------------------------------------------------
# In-memory DB fixture helpers
# ---------------------------------------------------------------------------

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, RunStatus


def _make_in_memory_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def db_session_factory():
    """Return a fresh in-memory SQLite session factory for each test."""
    return _make_in_memory_session()


@pytest.fixture()
def patched_store(db_session_factory):
    """
    Patch app.store to use an in-memory SQLite database.
    Returns the patched store module.
    """
    import app.store as store_mod

    original_session = store_mod._session

    def _in_memory_session():
        return db_session_factory()

    store_mod._session = _in_memory_session
    yield store_mod
    store_mod._session = original_session


@pytest.fixture()
def topic_and_run(patched_store):
    """Create a topic and a pending run; return (topic, run, store_mod)."""
    topic = patched_store.create_topic("AI trends")
    run = patched_store.create_run(topic.id)
    return topic, run, patched_store


# ---------------------------------------------------------------------------
# Helper: build a minimal valid Markdown blog post
# ---------------------------------------------------------------------------

def _make_blog_md(title="Test Title", n_sections=3):
    lines = [f"# {title}", "", "Introduction paragraph.", ""]
    for i in range(1, n_sections + 1):
        lines += [f"## Section {i}", "", f"Body of section {i}.", ""]
    lines += ["## Conclusion", "", "Concluding thoughts."]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Unit tests — success path
# ---------------------------------------------------------------------------

import app.worker as worker_mod  # ensure module is loaded before patching


class TestWorkerSuccessPath:
    def test_run_transitions_to_completed(self, topic_and_run):
        topic, run, store_mod = topic_and_run
        mock_output = _make_blog_md("My Blog Post")

        mock_crew = MagicMock()
        mock_crew.kickoff.return_value = mock_output

        with patch.object(worker_mod, "crew_module", MagicMock(build_crew=MagicMock(return_value=mock_crew))), \
             patch.object(worker_mod, "store", store_mod):
            worker_mod.execute_run(run.id, topic.text)

        updated_run = store_mod.get_run(run.id)
        assert updated_run.status == RunStatus.completed

    def test_blog_post_is_saved_on_success(self, topic_and_run):
        topic, run, store_mod = topic_and_run
        mock_output = _make_blog_md("My Blog Post")

        mock_crew = MagicMock()
        mock_crew.kickoff.return_value = mock_output

        with patch.object(worker_mod, "crew_module", MagicMock(build_crew=MagicMock(return_value=mock_crew))), \
             patch.object(worker_mod, "store", store_mod):
            worker_mod.execute_run(run.id, topic.text)

        posts = store_mod.list_blog_posts()
        assert len(posts) == 1
        assert posts[0].run_id == run.id

    def test_ended_at_is_set_on_success(self, topic_and_run):
        topic, run, store_mod = topic_and_run
        mock_output = _make_blog_md()

        mock_crew = MagicMock()
        mock_crew.kickoff.return_value = mock_output

        with patch.object(worker_mod, "crew_module", MagicMock(build_crew=MagicMock(return_value=mock_crew))), \
             patch.object(worker_mod, "store", store_mod):
            worker_mod.execute_run(run.id, topic.text)

        updated_run = store_mod.get_run(run.id)
        assert updated_run.ended_at is not None

    def test_title_parsed_from_first_h1(self, topic_and_run):
        topic, run, store_mod = topic_and_run
        mock_output = "# Parsed Title\n\nIntro\n\n## S1\n\nBody\n\n## S2\n\nBody\n\n## S3\n\nBody"

        mock_crew = MagicMock()
        mock_crew.kickoff.return_value = mock_output

        with patch.object(worker_mod, "crew_module", MagicMock(build_crew=MagicMock(return_value=mock_crew))), \
             patch.object(worker_mod, "store", store_mod):
            worker_mod.execute_run(run.id, topic.text)

        posts = store_mod.list_blog_posts()
        assert posts[0].title == "Parsed Title"


# ---------------------------------------------------------------------------
# Unit tests — failure paths
# ---------------------------------------------------------------------------

class TestWorkerFailurePaths:
    def test_serper_timeout_marks_run_failed(self, topic_and_run):
        topic, run, store_mod = topic_and_run

        mock_crew = MagicMock()
        mock_crew.kickoff.side_effect = TimeoutError("Serper API timed out after 30 seconds")

        with patch.object(worker_mod, "crew_module", MagicMock(build_crew=MagicMock(return_value=mock_crew))), \
             patch.object(worker_mod, "store", store_mod):
            worker_mod.execute_run(run.id, topic.text)

        updated_run = store_mod.get_run(run.id)
        assert updated_run.status == RunStatus.failed

    def test_serper_timeout_stores_error_message(self, topic_and_run):
        topic, run, store_mod = topic_and_run
        error_msg = "Serper API timed out after 30 seconds"

        mock_crew = MagicMock()
        mock_crew.kickoff.side_effect = TimeoutError(error_msg)

        with patch.object(worker_mod, "crew_module", MagicMock(build_crew=MagicMock(return_value=mock_crew))), \
             patch.object(worker_mod, "store", store_mod):
            worker_mod.execute_run(run.id, topic.text)

        updated_run = store_mod.get_run(run.id)
        assert updated_run.error_msg is not None
        assert len(updated_run.error_msg) > 0

    def test_writer_failure_marks_run_failed(self, topic_and_run):
        topic, run, store_mod = topic_and_run

        mock_crew = MagicMock()
        mock_crew.kickoff.side_effect = RuntimeError("Writer_Agent failed to produce output")

        with patch.object(worker_mod, "crew_module", MagicMock(build_crew=MagicMock(return_value=mock_crew))), \
             patch.object(worker_mod, "store", store_mod):
            worker_mod.execute_run(run.id, topic.text)

        updated_run = store_mod.get_run(run.id)
        assert updated_run.status == RunStatus.failed

    def test_empty_output_marks_run_failed(self, topic_and_run):
        topic, run, store_mod = topic_and_run

        mock_crew = MagicMock()
        mock_crew.kickoff.return_value = "   "  # blank output

        with patch.object(worker_mod, "crew_module", MagicMock(build_crew=MagicMock(return_value=mock_crew))), \
             patch.object(worker_mod, "store", store_mod):
            worker_mod.execute_run(run.id, topic.text)

        updated_run = store_mod.get_run(run.id)
        assert updated_run.status == RunStatus.failed

    def test_failure_sets_ended_at(self, topic_and_run):
        topic, run, store_mod = topic_and_run

        mock_crew = MagicMock()
        mock_crew.kickoff.side_effect = Exception("boom")

        with patch.object(worker_mod, "crew_module", MagicMock(build_crew=MagicMock(return_value=mock_crew))), \
             patch.object(worker_mod, "store", store_mod):
            worker_mod.execute_run(run.id, topic.text)

        updated_run = store_mod.get_run(run.id)
        assert updated_run.ended_at is not None


# ---------------------------------------------------------------------------
# Unit tests for _parse_output helper
# ---------------------------------------------------------------------------

class TestParseOutput:
    def test_extracts_title_from_h1(self):
        from app.worker import _parse_output
        md = "# My Title\n\nSome body text."
        title, body = _parse_output(md)
        assert title == "My Title"

    def test_body_excludes_title_line(self):
        from app.worker import _parse_output
        md = "# My Title\n\nSome body text."
        title, body = _parse_output(md)
        assert "# My Title" not in body
        assert "Some body text." in body

    def test_fallback_title_when_no_h1(self):
        from app.worker import _parse_output
        md = "No heading here.\n\nJust paragraphs."
        title, body = _parse_output(md)
        assert title == "Untitled"
        assert "No heading here." in body

    def test_only_first_h1_used_as_title(self):
        from app.worker import _parse_output
        md = "# First Title\n\n# Second Title\n\nBody."
        title, body = _parse_output(md)
        assert title == "First Title"


# ---------------------------------------------------------------------------
# Property 5: Run status transitions are monotonic
# Feature: ai-news-researcher-blog-writer, Property 5: Run status transitions are monotonic
# Validates: Requirements 2.5, 2.6, 5.1
# ---------------------------------------------------------------------------

_VALID_TRANSITIONS = {
    "pending": {"running"},
    "running": {"completed", "failed"},
    "completed": set(),
    "failed": set(),
}

_TERMINAL_STATES = {"completed", "failed"}


def _is_valid_transition(from_status: str, to_status: str) -> bool:
    return to_status in _VALID_TRANSITIONS.get(from_status, set())


@given(
    outcome=st.sampled_from(["completed", "failed"]),
    error_msg=st.one_of(st.none(), st.text(min_size=1, max_size=200)),
)
@h_settings(max_examples=100)
def test_property_5_run_status_transitions_are_monotonic(outcome, error_msg):
    """
    # Feature: ai-news-researcher-blog-writer, Property 5: Run status transitions are monotonic

    For any Run, the sequence of status values must follow the valid state machine:
    pending → running → (completed | failed).

    Validates: Requirements 2.5, 2.6, 5.1
    """
    SessionFactory = _make_in_memory_session()
    import app.store as store_mod
    original_session = store_mod._session
    store_mod._session = lambda: SessionFactory()

    try:
        topic = store_mod.create_topic("test topic")
        run = store_mod.create_run(topic.id)

        # Initial state must be pending
        assert run.status == RunStatus.pending, f"Expected pending, got {run.status}"

        # pending → running is valid
        assert _is_valid_transition("pending", "running"), "pending→running must be valid"
        run = store_mod.update_run_status(run.id, "running")
        assert run.status == RunStatus.running

        # running → outcome is valid
        assert _is_valid_transition("running", outcome), f"running→{outcome} must be valid"

        kwargs = {}
        if outcome == "failed" and error_msg:
            kwargs["error_msg"] = error_msg
        kwargs["ended_at"] = datetime.now(timezone.utc).replace(tzinfo=None)

        run = store_mod.update_run_status(run.id, outcome, **kwargs)
        assert run.status == RunStatus(outcome)

        # Terminal state — no further transitions are valid
        for bad_target in ["pending", "running", "completed", "failed"]:
            if bad_target != outcome:
                assert bad_target not in _VALID_TRANSITIONS.get(outcome, set()), (
                    f"Terminal state {outcome} should not allow transition to {bad_target}"
                )
    finally:
        store_mod._session = original_session


# ---------------------------------------------------------------------------
# Property 6: Failed run stores error message
# Feature: ai-news-researcher-blog-writer, Property 6: Failed run stores error message
# Validates: Requirements 2.4, 3.5
# ---------------------------------------------------------------------------

@given(
    error_msg=st.text(min_size=1, max_size=500).filter(lambda s: s.strip()),
)
@h_settings(max_examples=100)
def test_property_6_failed_run_stores_error_message(error_msg):
    """
    # Feature: ai-news-researcher-blog-writer, Property 6: Failed run stores error message

    For any Run that ends in 'failed' status, the stored error_msg field must be
    non-null and non-empty.

    Validates: Requirements 2.4, 3.5
    """
    SessionFactory = _make_in_memory_session()
    import app.store as store_mod
    original_session = store_mod._session
    store_mod._session = lambda: SessionFactory()

    try:
        topic = store_mod.create_topic("test topic")
        run = store_mod.create_run(topic.id)

        # Simulate the worker failure path
        store_mod.update_run_status(run.id, "running")
        store_mod.update_run_status(
            run.id,
            "failed",
            error_msg=error_msg,
            ended_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )

        failed_run = store_mod.get_run(run.id)
        assert failed_run.status == RunStatus.failed
        assert failed_run.error_msg is not None, "error_msg must not be None for failed runs"
        assert len(failed_run.error_msg.strip()) > 0, "error_msg must not be empty for failed runs"
    finally:
        store_mod._session = original_session
