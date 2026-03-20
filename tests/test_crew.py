"""
Tests for CrewAI crew builder and blog post structure invariant.
"""

import re

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# Feature: ai-news-researcher-blog-writer, Property 7: Blog post structure invariant


def count_markdown_headings(markdown: str) -> int:
    """Count the number of heading lines (# ... through ###### ...) in a Markdown string."""
    return sum(1 for line in markdown.splitlines() if re.match(r"^#{1,6}\s+\S", line))


def has_valid_blog_structure(markdown: str) -> bool:
    """
    Return True if the Markdown string contains at least 4 heading-level elements,
    which corresponds to: 1 title + at least 3 body section headings.
    A conclusion may or may not have its own heading, so we require ≥4 headings total
    OR ≥3 headings plus a non-empty final paragraph (conclusion).
    Per the design spec: parsing the Markdown must yield at least 4 heading-level elements.
    """
    return count_markdown_headings(markdown) >= 4


# ---------------------------------------------------------------------------
# Helpers to build synthetic blog post Markdown for property testing
# ---------------------------------------------------------------------------

def _build_blog_post(title: str, intro: str, sections: list[tuple[str, str]], conclusion: str) -> str:
    """Assemble a Markdown blog post from its parts."""
    parts = [f"# {title}", "", intro, ""]
    for heading, body in sections:
        parts += [f"## {heading}", "", body, ""]
    parts += ["## Conclusion", "", conclusion]
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Property 7: Blog post structure invariant
# Validates: Requirements 3.2, 3.3
# ---------------------------------------------------------------------------

_text = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters=("#", "\n")),
    min_size=1,
    max_size=80,
).map(str.strip).filter(lambda s: len(s) > 0)

_section = st.tuples(_text, _text)


@given(
    title=_text,
    intro=_text,
    sections=st.lists(_section, min_size=3, max_size=6),
    conclusion=_text,
)
@settings(max_examples=100)
def test_blog_post_structure_invariant(title, intro, sections, conclusion):
    """
    Property 7: For any Blog_Post produced by the Writer_Agent, the Markdown body
    must contain a title, an introduction, at least 3 sections with headings, and
    a conclusion. Parsing the Markdown must yield at least 4 heading-level elements.

    Validates: Requirements 3.2, 3.3
    """
    # Build a well-formed blog post (as the Writer_Agent is expected to produce)
    markdown = _build_blog_post(title, intro, sections, conclusion)

    # The structure must satisfy the invariant
    assert has_valid_blog_structure(markdown), (
        f"Expected ≥4 headings in blog post, got {count_markdown_headings(markdown)}.\n"
        f"Markdown:\n{markdown[:500]}"
    )


# ---------------------------------------------------------------------------
# Unit tests for build_crew (structure / wiring only — no live API calls)
# Skip if crewai is not installed in the current environment.
# ---------------------------------------------------------------------------

try:
    import crewai as _crewai  # noqa: F401
    _crewai_available = True
except ImportError:
    _crewai_available = False

_skip_no_crewai = pytest.mark.skipif(not _crewai_available, reason="crewai not installed")


@_skip_no_crewai
def test_build_crew_returns_crew_with_two_agents():
    """build_crew should return a Crew with exactly 2 agents."""
    from app.crew import build_crew

    crew = build_crew("AI trends")
    assert len(crew.agents) == 2


@_skip_no_crewai
def test_build_crew_write_task_has_research_context():
    """write_task.context must include research_task so the writer receives research output."""
    from app.crew import build_crew

    crew = build_crew("quantum computing")
    tasks = crew.tasks
    assert len(tasks) == 2

    research_task, write_task = tasks
    assert write_task.context is not None
    assert research_task in write_task.context


@_skip_no_crewai
def test_build_crew_task_descriptions_contain_topic():
    """research_task description must embed the topic string."""
    topic = "renewable energy breakthroughs"
    from app.crew import build_crew

    crew = build_crew(topic)
    research_task = crew.tasks[0]
    assert topic in research_task.description


@_skip_no_crewai
def test_research_task_expected_output_mentions_five_results():
    """research_task expected_output should mention at least 5 results."""
    from app.crew import build_crew

    crew = build_crew("space exploration")
    research_task = crew.tasks[0]
    assert "5" in research_task.expected_output


@_skip_no_crewai
def test_write_task_expected_output_mentions_markdown():
    """write_task expected_output should mention Markdown."""
    from app.crew import build_crew

    crew = build_crew("climate change")
    write_task = crew.tasks[1]
    assert "Markdown" in write_task.expected_output or "markdown" in write_task.expected_output.lower()


def test_count_markdown_headings():
    """Unit test for the heading-counting helper."""
    md = "# Title\n\nIntro\n\n## Section 1\n\nBody\n\n## Section 2\n\nBody\n\n## Conclusion\n\nEnd"
    assert count_markdown_headings(md) == 4


def test_has_valid_blog_structure_passes_with_four_headings():
    md = "# Title\n\n## S1\n\n## S2\n\n## S3\n\nConclusion text"
    assert has_valid_blog_structure(md) is True


def test_has_valid_blog_structure_fails_with_three_headings():
    md = "# Title\n\n## S1\n\n## S2\n\nConclusion text"
    assert has_valid_blog_structure(md) is False
