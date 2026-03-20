# Requirements Document

## Introduction

AI News Researcher and Blog Writer is a Python-based application that automates the process of gathering news and insights on user-specified topics from the web, then generating well-structured blog posts from that research. A CrewAI-powered multi-agent system handles research and writing. A lightweight web dashboard (FastAPI + Jinja2) lets users trigger research runs, view generated posts, and manage topics — all from a browser.

## Glossary

- **System**: The AI News Researcher and Blog Writer application as a whole
- **Research_Agent**: The CrewAI agent responsible for searching the web and collecting relevant news and information on a given topic
- **Writer_Agent**: The CrewAI agent responsible for transforming research output into a structured blog post
- **Crew**: A CrewAI Crew that orchestrates the Research_Agent and Writer_Agent in sequence
- **Topic**: A user-defined subject string that drives a research and writing run
- **Run**: A single end-to-end execution of the Crew for a given Topic
- **Blog_Post**: The structured text artifact produced by the Writer_Agent, containing a title, body, and metadata
- **Dashboard**: The web UI served by the FastAPI application
- **Post_Store**: The persistence layer (SQLite database) that stores Topics, Runs, and Blog_Posts
- **Serper_API**: The web search API (serper.dev) used by the Research_Agent to retrieve news results

---

## Requirements

### Requirement 1: Topic Management

**User Story:** As a user, I want to create and manage research topics from the dashboard, so that I can control what subjects the system researches.

#### Acceptance Criteria

1. THE Dashboard SHALL provide a form that accepts a topic string of 1–200 characters.
2. WHEN a user submits a valid topic, THE Post_Store SHALL persist the topic with a unique ID and creation timestamp.
3. IF a user submits an empty or blank topic string, THEN THE Dashboard SHALL display a validation error and reject the submission.
4. THE Dashboard SHALL display a list of all saved topics ordered by creation timestamp descending.
5. WHEN a user deletes a topic, THE Post_Store SHALL remove the topic and all associated Runs and Blog_Posts.

---

### Requirement 2: Research Run Execution

**User Story:** As a user, I want to trigger a research run for a topic, so that the system automatically gathers current news and information.

#### Acceptance Criteria

1. WHEN a user triggers a Run for a Topic, THE System SHALL invoke the Crew with the topic string as input.
2. THE Research_Agent SHALL query the Serper_API with the topic string and retrieve a minimum of 5 search results.
3. WHEN the Serper_API returns results, THE Research_Agent SHALL extract the title, URL, and snippet from each result.
4. IF the Serper_API returns an error or times out after 30 seconds, THEN THE System SHALL mark the Run as failed and store the error message in the Post_Store.
5. WHILE a Run is in progress, THE Dashboard SHALL display the run status as "running".
6. THE Post_Store SHALL record the Run start time, end time, status (pending, running, completed, failed), and any error message.

---

### Requirement 3: Blog Post Generation

**User Story:** As a user, I want the system to automatically write a blog post from the research results, so that I get publish-ready content without manual writing.

#### Acceptance Criteria

1. WHEN the Research_Agent completes a Run, THE Writer_Agent SHALL receive the research output and generate a Blog_Post.
2. THE Writer_Agent SHALL produce a Blog_Post containing a title, an introduction paragraph, a minimum of 3 body sections with headings, and a conclusion paragraph.
3. THE Writer_Agent SHALL write the Blog_Post body in Markdown format.
4. THE Post_Store SHALL persist the Blog_Post linked to its originating Run and Topic.
5. IF the Writer_Agent fails to produce a Blog_Post, THEN THE System SHALL mark the Run as failed and store the error message.

---

### Requirement 4: Blog Post Viewing and Editing

**User Story:** As a user, I want to view and edit generated blog posts in the dashboard, so that I can review and refine content before using it.

#### Acceptance Criteria

1. THE Dashboard SHALL display a list of all Blog_Posts ordered by creation timestamp descending.
2. WHEN a user selects a Blog_Post, THE Dashboard SHALL render the Markdown body as formatted HTML.
3. THE Dashboard SHALL provide an editable text area pre-populated with the raw Markdown content of a Blog_Post.
4. WHEN a user saves edits to a Blog_Post, THE Post_Store SHALL update the stored Markdown content and record the last-edited timestamp.
5. THE Dashboard SHALL display the topic name, run date, and word count for each Blog_Post in the list view.

---

### Requirement 5: Run History and Status Visibility

**User Story:** As a user, I want to see the history and status of all research runs, so that I can monitor progress and diagnose failures.

#### Acceptance Criteria

1. THE Dashboard SHALL display a run history list showing topic name, start time, duration, and status for each Run.
2. WHEN a Run status is "failed", THE Dashboard SHALL display the stored error message alongside the Run entry.
3. THE Dashboard SHALL update run status without requiring a full page reload, by polling the status endpoint at a maximum interval of 5 seconds.

---

### Requirement 6: Configuration Management

**User Story:** As a developer, I want all external API keys and model settings to be managed via environment variables, so that secrets are never hardcoded.

#### Acceptance Criteria

1. THE System SHALL read the Serper_API key exclusively from the `SERPER_API_KEY` environment variable at startup.
2. THE System SHALL read the OpenAI API key exclusively from the `OPENAI_API_KEY` environment variable at startup.
3. IF a required environment variable is missing at startup, THEN THE System SHALL log a descriptive error message and exit with a non-zero status code.
4. THE System SHALL support an `.env` file for local development using the `python-dotenv` library.
