"""
SQLAlchemy ORM models for AI News Researcher and Blog Writer.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class RunStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class Topic(Base):
    __tablename__ = "topics"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    text = Column(String(200), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    runs = relationship("Run", back_populates="topic", cascade="all, delete-orphan")
    blog_posts = relationship("BlogPost", back_populates="topic", cascade="all, delete-orphan")


class Run(Base):
    __tablename__ = "runs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    topic_id = Column(String, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False)
    status = Column(Enum(RunStatus), nullable=False, default=RunStatus.pending)
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)
    error_msg = Column(Text, nullable=True)

    topic = relationship("Topic", back_populates="runs")
    blog_post = relationship("BlogPost", back_populates="run", cascade="all, delete-orphan")


class BlogPost(Base):
    __tablename__ = "blog_posts"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id = Column(String, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)
    topic_id = Column(String, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False)
    title = Column(String, nullable=False)
    body_md = Column(Text, nullable=False)
    word_count = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    edited_at = Column(DateTime, nullable=True)

    run = relationship("Run", back_populates="blog_post")
    topic = relationship("Topic", back_populates="blog_posts")
