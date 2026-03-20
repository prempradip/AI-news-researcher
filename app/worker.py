"""
Background run worker for AI News Researcher and Blog Writer.

execute_run(run_id, topic_text) is called in a background thread.
It drives the full lifecycle: pending → running → completed | failed.
"""

import logging
import re
import traceback
from datetime import datetime, timezone

from app import store

# crew_module is imported lazily inside execute_run so that tests can patch it
# and so that importing worker.py does not require crewai to be installed.
try:
    from app import crew as crew_module  # type: ignore[assignment]
except ImportError:  # pragma: no cover
    crew_module = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _parse_output(output: str) -> tuple[str, str]:
    """
    Extract title and body from a Markdown string.

    The title is the text of the first `#` heading (level-1).
    The body is everything after that heading line (stripped).
    If no `#` heading is found, the entire output is treated as the body
    and a fallback title is used.
    """
    lines = output.splitlines()
    title = "Untitled"
    body_lines: list[str] = []
    found_title = False

    for i, line in enumerate(lines):
        match = re.match(r"^#\s+(.+)", line)
        if match and not found_title:
            title = match.group(1).strip()
            body_lines = lines[i + 1:]
            found_title = True
            break

    if not found_title:
        body_lines = lines

    body = "\n".join(body_lines).strip()
    return title, body


def execute_run(run_id: str, topic_text: str) -> None:
    """
    Execute a research-and-write run in the background.

    Steps:
    1. Mark the run as 'running'.
    2. Build and kick off the CrewAI crew.
    3. Parse the Writer_Agent output into title + body.
    4. Persist the BlogPost.
    5. Mark the run as 'completed'.

    Any exception causes the run to be marked 'failed' with the error message stored.
    """
    # Step 1 — mark running
    run = store.update_run_status(run_id, "running")
    topic_id = run.topic_id

    try:
        # Step 2 — invoke the crew
        _crew_mod = crew_module
        if _crew_mod is None:
            raise ImportError("crewai is not installed; cannot execute run.")
        result = _crew_mod.build_crew(topic_text).kickoff()

        # CrewAI may return a CrewOutput object or a plain string
        output_str: str = str(result) if result is not None else ""

        if not output_str.strip():
            raise ValueError("Writer_Agent produced no output.")

        # Step 3 — parse title and body
        title, body = _parse_output(output_str)

        # Step 4 — persist the blog post
        store.save_blog_post(
            run_id=run_id,
            topic_id=topic_id,
            title=title,
            body_md=output_str,  # store the full output as the Markdown body
        )

        # Step 5 — mark completed
        store.update_run_status(run_id, "completed", ended_at=_utcnow())

    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Run %s failed: %s\n%s",
            run_id,
            exc,
            traceback.format_exc(),
        )
        store.update_run_status(
            run_id,
            "failed",
            error_msg=str(exc),
            ended_at=_utcnow(),
        )
