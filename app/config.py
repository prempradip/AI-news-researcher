"""
Configuration management for AI News Researcher and Blog Writer.
Reads all required environment variables at import time.
Raises EnvironmentError with a descriptive message if required vars are missing.
"""

import os
from dotenv import load_dotenv

load_dotenv()


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise EnvironmentError(
            f"Required environment variable '{name}' is missing or empty. "
            f"Please set it in your environment or in a .env file. "
            f"See .env.example for reference."
        )
    return value


class Settings:
    SERPER_API_KEY: str = _require_env("SERPER_API_KEY")
    OPENAI_API_KEY: str = _require_env("OPENAI_API_KEY")
    DATABASE_URL: str = os.environ.get("DATABASE_URL", "sqlite:///./posts.db")
    OPENAI_MODEL: str = os.environ.get("OPENAI_MODEL", "gpt-4o")


settings = Settings()
