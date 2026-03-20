"""
Post Store — repository layer for Topics, Runs, and BlogPosts.
All database interactions go through these functions.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session, joinedload

from app.database import SessionLocal
from app.models import BlogPost, Run, RunStatus, Topic


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _session() -> Session:
    return SessionLocal()


# ---------------------------------------------------------------------------
# Topic functions
# ---------------------------------------------------------------------------

def create_topic(text: str) -> Topic:
    """Persist a new Topic and return it."""
    db = _session()
    try:
        topic = Topic(id=str(uuid.uuid4()), text=text, created_at=_utcnow())
        db.add(topic)
        db.commit()
        db.refresh(topic)
        return topic
    finally:
        db.close()


def list_topics() -> list[Topic]:
    """Return all Topics ordered by created_at DESC."""
    db = _session()
    try:
        return db.query(Topic).order_by(Topic.created_at.desc()).all()
    finally:
        db.close()


def delete_topic(topic_id: str) -> None:
    """Delete a Topic (cascades to Runs and BlogPosts)."""
    db = _session()
    try:
        topic = db.query(Topic).filter(Topic.id == topic_id).first()
        if topic:
            db.delete(topic)
            db.commit()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Run functions
# ---------------------------------------------------------------------------

def create_run(topic_id: str) -> Run:
    """Create a new Run in 'pending' status."""
    db = _session()
    try:
        run = Run(
            id=str(uuid.uuid4()),
            topic_id=topic_id,
            status=RunStatus.pending,
            started_at=_utcnow(),
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        return run
    finally:
        db.close()


def update_run_status(
    run_id: str,
    status: str,
    error_msg: str | None = None,
    ended_at: datetime | None = None,
) -> Run:
    """Update a Run's status (and optionally error_msg / ended_at)."""
    db = _session()
    try:
        run = db.query(Run).filter(Run.id == run_id).first()
        if run is None:
            raise ValueError(f"Run '{run_id}' not found")
        run.status = RunStatus(status) if isinstance(status, str) else status
        if error_msg is not None:
            run.error_msg = error_msg
        if ended_at is not None:
            run.ended_at = ended_at
        db.commit()
        db.refresh(run)
        return run
    finally:
        db.close()


def list_runs() -> list[Run]:
    """Return all Runs ordered by started_at DESC."""
    db = _session()
    try:
        return db.query(Run).options(joinedload(Run.topic)).order_by(Run.started_at.desc()).all()
    finally:
        db.close()


def get_run(run_id: str) -> Run:
    """Return a Run by ID, or raise ValueError if not found."""
    db = _session()
    try:
        run = db.query(Run).filter(Run.id == run_id).first()
        if run is None:
            raise ValueError(f"Run '{run_id}' not found")
        return run
    finally:
        db.close()


# ---------------------------------------------------------------------------
# BlogPost functions
# ---------------------------------------------------------------------------

def save_blog_post(
    run_id: str,
    topic_id: str,
    title: str,
    body_md: str,
) -> BlogPost:
    """Persist a new BlogPost; word_count is auto-computed from body_md."""
    db = _session()
    try:
        word_count = len(body_md.split())
        post = BlogPost(
            id=str(uuid.uuid4()),
            run_id=run_id,
            topic_id=topic_id,
            title=title,
            body_md=body_md,
            word_count=word_count,
            created_at=_utcnow(),
        )
        db.add(post)
        db.commit()
        db.refresh(post)
        return post
    finally:
        db.close()


def list_blog_posts() -> list[BlogPost]:
    """Return all BlogPosts ordered by created_at DESC."""
    db = _session()
    try:
        return db.query(BlogPost).options(joinedload(BlogPost.topic)).order_by(BlogPost.created_at.desc()).all()
    finally:
        db.close()


def get_blog_post(post_id: str) -> BlogPost:
    """Return a BlogPost by ID, or raise ValueError if not found."""
    db = _session()
    try:
        post = db.query(BlogPost).options(joinedload(BlogPost.topic)).filter(BlogPost.id == post_id).first()
        if post is None:
            raise ValueError(f"BlogPost '{post_id}' not found")
        return post
    finally:
        db.close()


def update_blog_post(post_id: str, body_md: str) -> BlogPost:
    """Update a BlogPost's body_md and set edited_at to current UTC time."""
    db = _session()
    try:
        post = db.query(BlogPost).filter(BlogPost.id == post_id).first()
        if post is None:
            raise ValueError(f"BlogPost '{post_id}' not found")
        post.body_md = body_md
        post.word_count = len(body_md.split())
        post.edited_at = _utcnow()
        db.commit()
        db.refresh(post)
        return post
    finally:
        db.close()
