"""
FastAPI application for AI News Researcher and Blog Writer.

Routes:
  GET  /                      — Dashboard home (topic list + run history)
  POST /topics                — Create a new topic
  POST /topics/{id}/delete    — Delete a topic (HTML form fallback)
  DELETE /topics/{id}         — Delete a topic (REST)
  POST /topics/{id}/run       — Trigger a new Run
  GET  /posts                 — List all blog posts
  GET  /posts/{id}            — View a single blog post (rendered HTML)
  GET  /posts/{id}/edit       — Edit form for a blog post
  POST /posts/{id}/edit       — Save edits to a blog post
  GET  /api/runs/{id}/status  — JSON status endpoint polled by dashboard
"""

import os
from concurrent.futures import ThreadPoolExecutor

import markdown as md_lib
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app import store, worker

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(title="AI News Researcher and Blog Writer")

_TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")
templates = Jinja2Templates(directory=_TEMPLATES_DIR)

# ThreadPoolExecutor for background run dispatch
_executor = ThreadPoolExecutor(max_workers=4)


# ---------------------------------------------------------------------------
# Dashboard home
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    topics = store.list_topics()
    runs = store.list_runs()
    return templates.TemplateResponse(
        request,
        "index.html",
        {"topics": topics, "runs": runs, "error": None},
    )


# ---------------------------------------------------------------------------
# Topic routes
# ---------------------------------------------------------------------------

@app.post("/topics")
async def create_topic(request: Request, topic_text: str = Form(default="")):
    stripped = topic_text.strip()
    if not stripped or len(stripped) > 200:
        topics = store.list_topics()
        runs = store.list_runs()
        error = (
            "Topic must be between 1 and 200 characters."
            if stripped
            else "Topic cannot be blank."
        )
        return templates.TemplateResponse(
            request,
            "index.html",
            {"topics": topics, "runs": runs, "error": error},
            status_code=422,
        )
    store.create_topic(stripped)
    return RedirectResponse(url="/", status_code=303)


@app.delete("/topics/{topic_id}")
async def delete_topic_rest(topic_id: str):
    store.delete_topic(topic_id)
    return RedirectResponse(url="/", status_code=303)


@app.post("/topics/{topic_id}/delete")
async def delete_topic_form(topic_id: str):
    """HTML-form-friendly DELETE (browsers can't send DELETE via form)."""
    store.delete_topic(topic_id)
    return RedirectResponse(url="/", status_code=303)


@app.post("/topics/{topic_id}/run")
async def trigger_run(topic_id: str):
    topics = store.list_topics()
    topic = next((t for t in topics if t.id == topic_id), None)
    if topic is None:
        return JSONResponse({"detail": "Topic not found"}, status_code=404)

    run = store.create_run(topic_id)
    _executor.submit(worker.execute_run, run.id, topic.text)
    return RedirectResponse(url="/", status_code=303)


# ---------------------------------------------------------------------------
# Blog post routes
# ---------------------------------------------------------------------------

@app.get("/posts", response_class=HTMLResponse)
async def list_posts(request: Request):
    posts = store.list_blog_posts()
    return templates.TemplateResponse(
        request,
        "posts.html",
        {"posts": posts},
    )


@app.get("/posts/{post_id}", response_class=HTMLResponse)
async def view_post(request: Request, post_id: str):
    try:
        post = store.get_blog_post(post_id)
    except ValueError:
        return templates.TemplateResponse(
            request,
            "base.html",
            {},
            status_code=404,
        )
    body_html = md_lib.markdown(post.body_md)
    return templates.TemplateResponse(
        request,
        "post_view.html",
        {"post": post, "body_html": body_html},
    )


@app.get("/posts/{post_id}/edit", response_class=HTMLResponse)
async def edit_post_form(request: Request, post_id: str):
    try:
        post = store.get_blog_post(post_id)
    except ValueError:
        return templates.TemplateResponse(
            request,
            "base.html",
            {},
            status_code=404,
        )
    return templates.TemplateResponse(
        request,
        "post_edit.html",
        {"post": post},
    )


@app.post("/posts/{post_id}/edit")
async def save_post_edit(post_id: str, body_md: str = Form(...)):
    try:
        store.update_blog_post(post_id, body_md)
    except ValueError:
        return JSONResponse({"detail": "Post not found"}, status_code=404)
    return RedirectResponse(url=f"/posts/{post_id}", status_code=303)


# ---------------------------------------------------------------------------
# API status endpoint
# ---------------------------------------------------------------------------

@app.get("/api/runs/{run_id}/status")
async def run_status(run_id: str):
    try:
        run = store.get_run(run_id)
    except ValueError:
        return JSONResponse({"detail": "Run not found"}, status_code=404)
    return JSONResponse(
        {"status": run.status.value, "error_msg": run.error_msg},
    )
