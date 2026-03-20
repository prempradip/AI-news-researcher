"""
Tests for app/config.py — configuration and environment variable handling.

# Feature: ai-news-researcher-blog-writer, Property 10: Missing environment variable causes startup failure
"""

import importlib
import os
import sys
import pytest
from hypothesis import given, settings as h_settings
from hypothesis import strategies as st


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_settings_with_env(env: dict):
    """
    Import (or re-import) app.config with a controlled environment.
    Returns the Settings class or raises EnvironmentError.
    """
    # Patch os.environ for the duration of the import
    original_env = os.environ.copy()
    # Remove all relevant keys first, then apply the provided env
    for key in ("SERPER_API_KEY", "OPENAI_API_KEY", "DATABASE_URL", "OPENAI_MODEL"):
        os.environ.pop(key, None)
    os.environ.update(env)

    # Remove cached module so it re-executes module-level code
    for mod_name in list(sys.modules.keys()):
        if mod_name in ("app.config", "app"):
            del sys.modules[mod_name]

    try:
        import app.config as cfg
        return cfg.Settings
    finally:
        # Restore original environment
        os.environ.clear()
        os.environ.update(original_env)
        # Clean up cached module again so subsequent tests start fresh
        for mod_name in list(sys.modules.keys()):
            if mod_name in ("app.config", "app"):
                del sys.modules[mod_name]


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

class TestSettingsUnit:
    def test_raises_when_serper_key_missing(self):
        with pytest.raises(EnvironmentError) as exc_info:
            _load_settings_with_env({"OPENAI_API_KEY": "sk-test"})
        assert "SERPER_API_KEY" in str(exc_info.value)

    def test_raises_when_openai_key_missing(self):
        with pytest.raises(EnvironmentError) as exc_info:
            _load_settings_with_env({"SERPER_API_KEY": "serper-test"})
        assert "OPENAI_API_KEY" in str(exc_info.value)

    def test_raises_when_both_keys_missing(self):
        with pytest.raises(EnvironmentError):
            _load_settings_with_env({})

    def test_succeeds_with_both_keys_present(self):
        Settings = _load_settings_with_env({
            "SERPER_API_KEY": "serper-test",
            "OPENAI_API_KEY": "sk-test",
        })
        assert Settings.SERPER_API_KEY == "serper-test"
        assert Settings.OPENAI_API_KEY == "sk-test"

    def test_default_database_url(self):
        Settings = _load_settings_with_env({
            "SERPER_API_KEY": "serper-test",
            "OPENAI_API_KEY": "sk-test",
        })
        assert Settings.DATABASE_URL == "sqlite:///./posts.db"

    def test_default_openai_model(self):
        Settings = _load_settings_with_env({
            "SERPER_API_KEY": "serper-test",
            "OPENAI_API_KEY": "sk-test",
        })
        assert Settings.OPENAI_MODEL == "gpt-4o"

    def test_custom_database_url(self):
        Settings = _load_settings_with_env({
            "SERPER_API_KEY": "serper-test",
            "OPENAI_API_KEY": "sk-test",
            "DATABASE_URL": "sqlite:///./custom.db",
        })
        assert Settings.DATABASE_URL == "sqlite:///./custom.db"

    def test_error_message_is_descriptive(self):
        """Error message should name the missing variable and hint at .env."""
        with pytest.raises(EnvironmentError) as exc_info:
            _load_settings_with_env({"OPENAI_API_KEY": "sk-test"})
        msg = str(exc_info.value)
        assert "SERPER_API_KEY" in msg
        assert ".env" in msg.lower() or "environment" in msg.lower()


# ---------------------------------------------------------------------------
# Property-based test
# ---------------------------------------------------------------------------

# Strategies for generating subsets of required keys
_REQUIRED_KEYS = ["SERPER_API_KEY", "OPENAI_API_KEY"]
_non_empty_str = st.text(min_size=1, max_size=50).filter(str.strip)


@given(
    missing=st.lists(
        st.sampled_from(_REQUIRED_KEYS),
        min_size=1,
        max_size=len(_REQUIRED_KEYS),
        unique=True,
    )
)
@h_settings(max_examples=100)
def test_property_10_missing_env_var_causes_startup_failure(missing):
    """
    # Feature: ai-news-researcher-blog-writer, Property 10: Missing environment variable causes startup failure

    For any configuration where SERPER_API_KEY or OPENAI_API_KEY is absent,
    loading Settings must raise EnvironmentError.

    Validates: Requirements 6.1, 6.2, 6.3
    """
    # Build an env that has all required keys, then remove the 'missing' ones
    full_env = {k: "dummy-value" for k in _REQUIRED_KEYS}
    for key in missing:
        del full_env[key]

    with pytest.raises(EnvironmentError) as exc_info:
        _load_settings_with_env(full_env)

    # The error message must mention at least one of the missing keys
    error_text = str(exc_info.value)
    assert any(key in error_text for key in missing), (
        f"EnvironmentError did not mention any missing key. "
        f"Missing: {missing}, Error: {error_text}"
    )
