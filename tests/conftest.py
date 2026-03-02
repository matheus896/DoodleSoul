"""
Shared pytest configuration and fixtures for all Gemini API tests.

Provides:
- client: session-scoped genai.Client() reused across all tests.
- output_dir: Path to tests/output/ guaranteed to exist.
- Registers the 'slow' marker to avoid pytest warnings.
"""

from pathlib import Path

import pytest
from dotenv import load_dotenv
from google import genai

# Load .env at the root before any fixture runs.
# genai.Client() reads GEMINI_API_KEY from the environment automatically.
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")


def pytest_configure(config):
    """Register custom markers to avoid pytest warnings."""
    config.addinivalue_line(
        "markers",
        "slow: mark a test as slow-running (skip with: pytest -m 'not slow')",
    )


@pytest.fixture(scope="session")
def client():
    """
    Create a single genai.Client() for the entire test session.

    Session scope means the client is created once and reused across
    all test files, avoiding repeated authentication overhead.
    """
    return genai.Client()


@pytest.fixture
def output_dir():
    """
    Ensure tests/output/ exists and return its Path.

    Generated images and videos are saved here for inspection after the run.
    """
    output_path = Path(__file__).parent / "output"
    output_path.mkdir(exist_ok=True)
    return output_path
