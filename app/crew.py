"""
CrewAI agents and crew builder for AI News Researcher and Blog Writer.
"""

from crewai import Agent, Crew, Task
from crewai_tools import SerperDevTool
from langchain_openai import ChatOpenAI

from app.config import settings

research_agent = Agent(
    role="News Researcher",
    goal="Find at least 5 recent, relevant news items for the given topic",
    tools=[SerperDevTool()],
    llm=ChatOpenAI(model=settings.OPENAI_MODEL),
)

writer_agent = Agent(
    role="Blog Writer",
    goal="Write a well-structured Markdown blog post from the research",
    llm=ChatOpenAI(model=settings.OPENAI_MODEL),
)


def build_crew(topic: str) -> Crew:
    research_task = Task(
        description=(
            f"Research the topic: {topic}. "
            "Retrieve at least 5 results. "
            "For each result, extract the title, URL, and snippet."
        ),
        agent=research_agent,
        expected_output=(
            "A list of at least 5 news items, each with: title, URL, and snippet."
        ),
    )
    write_task = Task(
        description=(
            "Using the research results provided, write a Markdown blog post. "
            "The post must include: a title (# heading), an introduction paragraph, "
            "at least 3 body sections each with a heading (## or ###), "
            "and a conclusion paragraph."
        ),
        agent=writer_agent,
        context=[research_task],
        expected_output=(
            "A complete Markdown blog post string with title, intro, "
            "≥3 body sections with headings, and a conclusion."
        ),
    )
    return Crew(
        agents=[research_agent, writer_agent],
        tasks=[research_task, write_task],
    )
