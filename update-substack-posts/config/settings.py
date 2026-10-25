"""All tunable constants and paths for the Substack pipeline.

Each value can be overridden by an environment variable of the same name.
"""

import os
from datetime import date
from pathlib import Path


def _env(name, default, cast=str):
    raw = os.environ.get(name)
    return default if raw in (None, "") else cast(raw)


# --- Fetching ---
START_DATE = _env("START_DATE", date(2023, 10, 7), date.fromisoformat)
REQUEST_DELAY_SECONDS = _env("REQUEST_DELAY_SECONDS", 1.0, float)
REQUEST_TIMEOUT_SECONDS = _env("REQUEST_TIMEOUT_SECONDS", 30.0, float)
ARCHIVE_PAGE_SIZE = _env("ARCHIVE_PAGE_SIZE", 50, int)
MAX_RETRIES = _env("MAX_RETRIES", 3, int)
RETRY_BACKOFF_SECONDS = _env("RETRY_BACKOFF_SECONDS", 5.0, float)
MAX_TEXT_CHARS = _env("MAX_TEXT_CHARS", 20000, int)
# Floor for dropping stubs before classification (except --post-url posts); Claude judges substance above it
MIN_WORD_COUNT = _env("MIN_WORD_COUNT", 400, int)
USER_AGENT = _env(
    "USER_AGENT",
    "exposeaz-resource-pipeline (+https://github.com/exposeaz/website-resources)",
)

# --- Classification ---
MODEL = _env("MODEL", "claude-sonnet-5-5")
MAX_OUTPUT_TOKENS = _env("MAX_OUTPUT_TOKENS", 600, int)
MIN_TAGS = _env("MIN_TAGS", 1, int)
MAX_TAGS = _env("MAX_TAGS", 5, int)
MAX_SUGGESTED_TAGS = _env("MAX_SUGGESTED_TAGS", 5, int)
SUMMARY_MIN_SENTENCES = _env("SUMMARY_MIN_SENTENCES", 1, int)
SUMMARY_MAX_SENTENCES = _env("SUMMARY_MAX_SENTENCES", 2, int)
# Refusal fallback routing; only the "default" form is valid for Sonnet 5.5
FALLBACK_BETA = _env("FALLBACK_BETA", "server-side-fallback-2026-07-01")

# --- Dry run ---
DRY_RUN_SAMPLE_SIZE = _env("DRY_RUN_SAMPLE_SIZE", 3, int)

# --- Paths ---
PIPELINE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = Path(_env("REPO_ROOT", str(PIPELINE_DIR.parent)))
SUBSTACKS_FILE = PIPELINE_DIR / "config" / "substacks.yaml"
TAGS_FILE = PIPELINE_DIR / "config" / "tags.json"
PROCESSED_FILE = PIPELINE_DIR / "data" / "processed.json"
ARTICLES_FILE = PIPELINE_DIR / "data" / "articles.json"
OUTPUT_DIR = PIPELINE_DIR / "output"
RESOURCES_FILE = REPO_ROOT / "data.json"
AZARYAH_DIR = Path(_env("AZARYAH_DIR", str(REPO_ROOT / "azaryah")))
AZARYAH_PROMPT_FILE = AZARYAH_DIR / "lambda" / "azaryah-ws-default" / "prompts" / "substack-posts.md"
PR_BODY_FILE = PIPELINE_DIR / "output" / "pr-body.md"

# --- Output content ---
RESOURCE_CATEGORY_ID = "substack-articles"
RESOURCE_CATEGORY_LABEL = "Substack articles"
AZARYAH_HEADER = (
    "These are specific Substack articles on relevant topics that can be recommended to users:"
)
