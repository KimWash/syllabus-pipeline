"""Pluggable LLM layer: every backend is a Provider with complete(prompt) -> str.

A provider is built from a config table, e.g. (TOML)
    provider = "openai"            # openai | anthropic | cli
    model = "claude-haiku-5-5"
    concurrency = 2
    ...backend-specific options
See configs/*.toml for examples. New backends: subclass Provider and add them to KINDS.
"""
import tomllib
from .base import Provider, LLMError
from .openai_compat import OpenAICompat
from .anthropic_api import AnthropicAPI
from .cli import CLI

KINDS = {c.kind: c for c in (OpenAICompat, AnthropicAPI, CLI)}

def load_config(path):
    with open(path, "rb") as f:
        return tomllib.load(f)

def make(spec):
    """Build a Provider from a config table (dict). Returns None for a missing/empty table."""
    if not spec:
        return None
    spec = dict(spec)
    kind = spec.pop("provider")
    if kind not in KINDS:
        raise ValueError(f"unknown provider {kind!r}; known: {sorted(KINDS)}")
    return KINDS[kind](**spec)
