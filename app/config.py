"""Environment config. main.py calls validate() at startup."""

import os
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "").strip().lower()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

if not LLM_PROVIDER:
    if ANTHROPIC_API_KEY:
        LLM_PROVIDER = "anthropic"
    elif OPENAI_API_KEY:
        LLM_PROVIDER = "openai"

# Defaults. Confirm these models exist on your account.
_DEFAULT_MODELS = {"anthropic": "claude-sonnet-5-5", "openai": "gpt-4o"}
LLM_MODEL = os.getenv("LLM_MODEL") or _DEFAULT_MODELS.get(LLM_PROVIDER, "")
API_KEY = {"anthropic": ANTHROPIC_API_KEY, "openai": OPENAI_API_KEY}.get(LLM_PROVIDER, "")

LLM_TIMEOUT_S = float(os.getenv("LLM_TIMEOUT_S", "30"))
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "2"))

EXTRACTION_MAX_TOKENS = int(os.getenv("EXTRACTION_MAX_TOKENS", "600"))
GENERATION_MAX_TOKENS = int(os.getenv("GENERATION_MAX_TOKENS", "1024"))
HISTORY_WINDOW = int(os.getenv("HISTORY_WINDOW", "6"))

OFFTOPIC_LIMIT = 2
FRUSTRATION_LIMIT = 3
MAX_REVISIONS = 2

MAX_VERIFY_FAILURES = 5
# (max hits, window seconds)
IP_VERIFY_FAIL_LIMIT = (15, 900.0)
SESSION_RATE_LIMIT = (30, 60.0)
IP_RATE_LIMIT = (60, 60.0)
SESSION_TTL_S = float(os.getenv("SESSION_TTL_S", "1800"))
MAX_SESSIONS = int(os.getenv("MAX_SESSIONS", "5000"))


def validate() -> None:
    if LLM_PROVIDER not in ("anthropic", "openai"):
        raise RuntimeError(
            "No AI model configured. Set ANTHROPIC_API_KEY or OPENAI_API_KEY "
            "(and optionally LLM_PROVIDER / LLM_MODEL). See .env.example.")
    if not API_KEY:
        key = "ANTHROPIC_API_KEY" if LLM_PROVIDER == "anthropic" else "OPENAI_API_KEY"
        raise RuntimeError(f"LLM_PROVIDER={LLM_PROVIDER} but {key} is not set.")
