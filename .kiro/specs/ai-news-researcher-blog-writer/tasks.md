# Implementation Plan: AI News Researcher and Blog Writer

## Overview

Implement a Python FastAPI + CrewAI application with a SQLite persistence layer, background run worker, and Jinja2 dashboard. Tasks follow the layered architecture: config → models → store → crew → worker → API routes → templates.

## Tasks

- [x] 1. Project setup and configuration
  - Create project directory structure: `app/`, `templates/`, `alembic/`, `tests/`
  - Create `requirements.txt` with all dependencies: fastapi, uvicorn, crewai, crewai-tools, sqlalchemy, alembic, python-dotenv, markdown, hypothesis, pytest, httpx
  - Create `.env.example` with placeholder values for `SERPER_API_KEY`, `OPENAI_API_KEY`, `DATABASE_URL`, `OPENAI_MODEL`
  - Implement `app/config.py` with `Settings` class that reads env vars at import time and raises `EnvironmentError` with a descriptive message if `SERPER_API_KEY` or `OPENAI_API_KEY` are missing
  - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [ ]* 1.1 Write property test for missing env var startup failure
    - **Property 10: Missing environment variable causes startup failure**
    - **Validates: Requirements 6.1, 6.2, 6.3**

- [x] 2. Database models and migrations
  - Implement `app/models.py` with SQLAlchemy ORM models: `Topic`, `Run`, `BlogPost` with all fields, FK relationships, and CASCADE DELETE constraints as specified in the design
  - Define `RunStatus` enum: `pending | running | completed | failed`
  - Set up `app/database.py` with engine creation and `SessionLocal` factory using `DATABASE_URL` from settings
  - Initialize Alembic and create the initial migration for all three tables
  - _Requirements: 1.2, 2.6, 3.4_

- [x] 3. Post Store (repository layer)
  - Implement `app/store.py` with all repository functions: `create_topic`, `list_topics`, `delete_topic`, `create_run`, `update_run_status`, `list_runs`, `get_run`, `save_blog_post`, `list_blog_posts`, `get_blog_post`, `update_blog_post`
  - Ensure `list_topics` returns results ordered by `created_at` DESC
  - Ensure `list_blog_posts` returns results ordered by `created_at` DESC
  - Ensure `delete_topic` cascades to associated Runs and BlogPosts
  - Ensure `update_blog_post` sets `edited_at` to current UTC timestamp
  - _Requirements: 1.2, 1.4, 1.5, 2.6, 3.4, 4.3, 4.4_

  - [ ]* 3.1 Write property test for topic text length invariant
    - **Property 1: Topic text length invariant**
    - **Validates: Requirements 1.1, 1.3**

  - [ ]* 3.2 Write property test for topic persistence round trip
    - **Property 2: Topic persistence round trip**
    - **Validates: Requirements 1.2**

  - [ ]* 3.3 Write property test for topic list ordering invariant
    - **Property 3: Topic list ordering invariant**
    - **Validates: Requirements 1.4**

  - [ ]* 3.4 Write property test for topic deletion cascade
    - **Property 4: Topic deletion cascades**
    - **Validates: Requirements 1.5**

  - [ ]* 3.5 Write property test for blog post list ordering invariant
    - **Property 9: Blog post list ordering invariant**
    - **Validates: Requirements 4.1**

  - [ ]* 3.6 Write property test for blog post edit round trip
    - **Property 8: Blog post edit round trip**
    - **Validates: Requirements 4.3, 4.4**

  - [ ]* 3.7 Write unit tests for store CRUD operations
    - Test `create_topic`, `list_topics`, `delete_topic` with an in-memory SQLite DB
    - Test `save_blog_post`, `get_blog_post`, `update_blog_post`
    - Test `get_run` raises / returns None for unknown IDs
    - _Requirements: 1.2, 1.4, 1.5, 3.4, 4.3_

- [x] 4. Checkpoint — Ensure all store and config tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. CrewAI agents and crew builder
  - Implement `app/crew.py` with `research_agent`, `writer_agent`, and `build_crew(topic: str) -> Crew`
  - Configure `research_task` to require at least 5 results with title, URL, and snippet per result
  - Configure `write_task` to produce Markdown with title, intro, ≥3 body sections with headings, and a conclusion
  - Wire `write_task.context = [research_task]` so the writer receives research output
  - _Requirements: 2.1, 2.2, 2.3, 3.1, 3.2, 3.3_

  - [ ]* 5.1 Write property test for blog post structure invariant
    - **Property 7: Blog post structure invariant**
    - **Validates: Requirements 3.2, 3.3**

- [x] 6. Background run worker
  - Implement `app/worker.py` with `execute_run(run_id: str, topic_text: str)` function
  - On entry: call `store.update_run_status(run_id, "running")`
  - Invoke `crew.build_crew(topic_text).kickoff()` and capture the Writer_Agent output
  - Parse the output string to extract the title (first `#` heading) and body (remaining Markdown)
  - On success: call `store.save_blog_post(...)` then `store.update_run_status(run_id, "completed", ended_at=now)`
  - On any exception: call `store.update_run_status(run_id, "failed", error_msg=str(e), ended_at=now)` and log the full traceback
  - _Requirements: 2.1, 2.4, 2.5, 2.6, 3.4, 3.5_

  - [ ]* 6.1 Write property test for run status transition monotonicity
    - **Property 5: Run status transitions are monotonic**
    - **Validates: Requirements 2.5, 2.6, 5.1**

  - [ ]* 6.2 Write property test for failed run stores error message
    - **Property 6: Failed run stores error message**
    - **Validates: Requirements 2.4, 3.5**

  - [ ]* 6.3 Write unit tests for worker with mocked Crew
    - Test success path: run transitions to `completed`, blog post is saved
    - Test Serper timeout path: run transitions to `failed`, error_msg is set
    - Test writer failure path: run transitions to `failed`, error_msg is set
    - _Requirements: 2.4, 2.5, 3.5_

- [x] 7. Checkpoint — Ensure all worker and crew tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. FastAPI routes and application wiring
  - Implement `app/main.py` with all routes from the design: `GET /`, `POST /topics`, `DELETE /topics/{id}`, `POST /topics/{id}/run`, `GET /posts`, `GET /posts/{id}`, `GET /posts/{id}/edit`, `POST /posts/{id}/edit`, `GET /api/runs/{id}/status`
  - Mount a `ThreadPoolExecutor` (or `asyncio` background task) to dispatch `worker.execute_run` without blocking the event loop
  - Return HTTP 404 for unknown post/run IDs
  - Return HTTP 422 with a validation error message for blank/empty topic submissions
  - Return JSON `{"status": ..., "error_msg": ...}` from the `/api/runs/{id}/status` endpoint
  - _Requirements: 1.1, 1.3, 1.4, 2.1, 2.5, 3.4, 4.1, 4.3, 5.1, 5.3_

  - [ ]* 8.1 Write unit tests for FastAPI routes
    - Use `httpx.AsyncClient` with `TestClient` to test form validation (blank topic → 422), topic creation redirect, 404 on unknown post, status endpoint JSON shape
    - _Requirements: 1.1, 1.3, 4.1, 5.1_

- [x] 9. Jinja2 templates
  - Create `templates/base.html` with shared layout, navigation links, and a `<script>` block for the polling logic (fetch `/api/runs/{id}/status` every 5 seconds, update status badge in-place)
  - Create `templates/index.html` extending `base.html`: topic submission form, topic list with delete buttons, run history table (topic name, start time, duration, status, error message)
  - Create `templates/posts.html` extending `base.html`: blog post list with topic name, run date, word count, and link to post view
  - Create `templates/post_view.html` extending `base.html`: rendered Markdown as HTML (use server-side `markdown` library in the route or pass pre-rendered HTML), edit link
  - Create `templates/post_edit.html` extending `base.html`: `<textarea>` pre-populated with raw Markdown, save button
  - _Requirements: 1.1, 1.3, 1.4, 2.5, 4.1, 4.2, 4.3, 4.5, 5.1, 5.2, 5.3_

  - [ ]* 9.1 Write unit tests for Markdown rendering
    - Test that a known Markdown string (with headings, paragraphs) renders expected HTML elements via the server-side `markdown` library
    - _Requirements: 4.2_

- [x] 10. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP
- Each task references specific requirements for traceability
- Property tests use Hypothesis with `@settings(max_examples=100)` and are tagged with `# Feature: ai-news-researcher-blog-writer, Property N: ...`
- Unit tests and property tests are complementary — both are needed for full coverage
- The background worker must never block the FastAPI event loop; use `ThreadPoolExecutor` or `asyncio.to_thread`
