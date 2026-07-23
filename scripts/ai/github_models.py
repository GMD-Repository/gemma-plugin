"""
GitHub Models API client for the GEMMA release pipeline.

Thin wrapper around the GitHub Models inference endpoint for generating
AI-powered changelog summaries.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

import requests

logger = logging.getLogger(__name__)

GITHUB_MODELS_URL = "https://models.github.ai/inference/chat/completions"
DEFAULT_MODEL = "openai/gpt-4o-mini"


@dataclass
class ModelResponse:
    """Response from a GitHub Models API call."""

    content: str
    model: str
    usage: dict = field(default_factory=dict)


def call_github_model(
    system_prompt: str,
    user_prompt: str,
    token: str,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.2,
    max_tokens: int = 600,
) -> ModelResponse:
    """Call the GitHub Models API for chat completion.

    Args:
        system_prompt: The system message defining behavior.
        user_prompt: The user message with the actual request.
        token: GitHub token with models:read permission.
        model: Model identifier (default: openai/gpt-4o-mini).
        temperature: Sampling temperature (0.0 - 2.0).
        max_tokens: Maximum tokens in the response.

    Returns:
        ModelResponse with the generated content.

    Raises:
        requests.HTTPError: If the API returns a non-2xx status.
        ValueError: If the response format is unexpected.
    """
    logger.info("Calling GitHub Models API (model=%s, temp=%.1f)...", model, temperature)

    response = requests.post(
        GITHUB_MODELS_URL,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        json={
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        },
        timeout=60,
    )

    logger.info("GitHub Models API: HTTP %d", response.status_code)

    if not response.ok:
        error_body = response.text[:400]
        logger.error("GitHub Models API error: %s", error_body)
        response.raise_for_status()

    data = response.json()
    raw_content = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()

    if not raw_content:
        raise ValueError("GitHub Models API returned empty content")

    logger.debug("AI raw output: %s", raw_content[:300])

    return ModelResponse(
        content=raw_content,
        model=data.get("model", model),
        usage=data.get("usage", {}),
    )


def parse_ai_json(raw: str) -> dict | list:
    """Parse JSON from AI model output, handling common formatting issues.

    The AI may wrap JSON in code fences or add preamble text.
    This function strips those and extracts the JSON.

    Args:
        raw: Raw text output from the AI model.

    Returns:
        Parsed JSON as a dict or list.

    Raises:
        json.JSONDecodeError: If the content is not valid JSON after cleaning.
    """
    cleaned = raw.strip()

    # Strip markdown code fences
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip()

    # Try to find JSON object or array in the text
    # Look for the first { or [ and the last } or ]
    json_start = None
    json_end = None

    for i, char in enumerate(cleaned):
        if char in "{[":
            json_start = i
            break

    if json_start is not None:
        expected_end = "}" if cleaned[json_start] == "{" else "]"
        for i in range(len(cleaned) - 1, json_start - 1, -1):
            if cleaned[i] == expected_end:
                json_end = i + 1
                break

    if json_start is not None and json_end is not None:
        cleaned = cleaned[json_start:json_end]

    return json.loads(cleaned)


def load_prompt(prompt_path: str) -> str:
    """Load an AI prompt from a markdown file.

    Args:
        prompt_path: Path to the prompt file.

    Returns:
        The prompt text content.

    Raises:
        FileNotFoundError: If the prompt file doesn't exist.
    """
    from pathlib import Path

    path = Path(prompt_path)
    if not path.exists():
        raise FileNotFoundError(f"AI prompt file not found: {prompt_path}")

    content = path.read_text(encoding="utf-8").strip()
    logger.info("Loaded AI prompt from %s (%d chars)", path.name, len(content))
    return content
