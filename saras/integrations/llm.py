"""Picks the LLM provider from LLM_PROVIDER in .env ("gemini" default, or "anthropic").

Everything else in SARAS imports ask/research and the shared exceptions from here.
"""
from saras import config
from saras.integrations.gemini_client import (  # noqa: F401  (shared by both providers)
    GeminiHealth,
    GroundedAnswer,
    ModelUnavailable,
    QuotaExceeded,
    health,
)

if config.llm_provider() == "anthropic":
    from saras.integrations.anthropic_client import ask, research
else:
    from saras.integrations.gemini_client import ask, research
