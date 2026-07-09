"""Thin LLM wrapper for document extraction.

Returns ``(parsed_json, total_tokens)`` for a single chunk. Unlike the RAG
gateway there is no offline deterministic fallback: real graph extraction needs
a real model, and the offline demo builds its graph from the seed pipeline
instead. This module stays free of any ``backend/app`` import (same rule as
``embed_chunks``) so ingestion has no dependency on the API package.
"""

from __future__ import annotations

import json
import os

EXTRACTION_MODEL = "gpt-4o-mini"


class LLMNotConfigured(RuntimeError):
    """Raised when a real extraction is requested with no OpenAI key set."""


def is_configured() -> bool:
    return os.getenv("LLM_PROVIDER", "openai") == "openai" and bool(
        os.getenv("OPENAI_API_KEY", "")
    )


def extract(system_prompt: str, user_prompt: str) -> tuple[dict, int]:
    """Call the model for one chunk; return ``(json_dict, total_tokens)``.

    Raises ``LLMNotConfigured`` if no key is available, and lets
    ``json.JSONDecodeError`` propagate so the caller can retry/flag the chunk.
    """
    if not is_configured():
        raise LLMNotConfigured(
            "document extraction requires OPENAI_API_KEY; "
            "the offline demo builds its graph from the seed pipeline instead"
        )

    from openai import OpenAI

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    response = client.chat.completions.create(
        model=EXTRACTION_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
    )
    tokens = response.usage.total_tokens if response.usage else 0
    content = response.choices[0].message.content or "{}"
    return json.loads(content), tokens
