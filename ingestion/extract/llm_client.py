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

from ingestion.extract import strict_schema

EXTRACTION_MODEL = "gpt-4o-mini"


class LLMNotConfigured(RuntimeError):
    """Raised when a real extraction is requested with no OpenAI key set."""


def is_configured() -> bool:
    return os.getenv("LLM_PROVIDER", "openai") == "openai" and bool(os.getenv("OPENAI_API_KEY", ""))


class LLMRefused(RuntimeError):
    """The model returned a refusal instead of content."""


def response_format() -> dict:
    """The ``response_format`` argument, as a plain dict so it can be asserted offline.

    ``json_object`` only guaranteed *valid JSON*; the shape was left to the prompt, and a single
    edge missing its ``id`` discarded the whole chunk. ``json_schema`` with ``strict`` makes the
    shape a decoding constraint instead of a request.
    """
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "graph_extraction",
            "strict": True,
            "schema": strict_schema.build_strict_schema(),
        },
    }


def content_of(message) -> str:
    """Return the message text, or raise if the model refused.

    Structured Outputs can answer with ``refusal`` instead of ``content``. Reading ``content``
    blindly would turn a refusal into an empty extraction — a chunk silently yielding nothing
    while the job reports success.
    """
    refusal = getattr(message, "refusal", None)
    if refusal:
        raise LLMRefused(str(refusal))
    return message.content or "{}"


def extract(system_prompt: str, user_prompt: str) -> tuple[dict, int]:
    """Call the model for one chunk; return ``(json_dict, total_tokens)``.

    Raises ``LLMNotConfigured`` if no key is available, ``LLMRefused`` on a refusal, and lets
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
        response_format=response_format(),
    )
    tokens = response.usage.total_tokens if response.usage else 0
    parsed = json.loads(content_of(response.choices[0].message))
    return strict_schema.drop_strict_nulls(parsed), tokens
