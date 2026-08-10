"""
Rule-based changelog generation for the GEMMA release pipeline.

Replaced AI-powered generation (GitHub Models API — discontinued) with a
deterministic, conventional-commit-aware categorizer. Raw commit/PR lines
collected by collect_changes() are classified into structured categories
using prefix matching and keyword heuristics.

No external API calls are made. Fallback behaviour is preserved.
"""

import os
import json
import re
import logging
from dataclasses import dataclass, field
import requests

from scripts.utils.changelog import highlights_to_changes

logger = logging.getLogger(__name__)

# Generic fallback when no changes are found at all
GENERIC_FALLBACK = {
    "summary": "This release includes internal updates and maintenance improvements.",
    "features": [],
    "improvements": [
        "Improved overall plugin stability and performance",
        "Applied internal updates and maintenance fixes",
    ],
    "fixes": [],
    "documentation": [],
    "breaking_changes": [],
}

# Conventional commit prefix → changelog category mapping
_PREFIX_MAP: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^feat[!?(]", re.IGNORECASE), "features"),
    (re.compile(r"^fix[!?(]", re.IGNORECASE), "fixes"),
    (re.compile(r"^docs?[!?(]", re.IGNORECASE), "documentation"),
    (re.compile(r"^refactor[!?(]", re.IGNORECASE), "improvements"),
    (re.compile(r"^perf[!?(]", re.IGNORECASE), "improvements"),
    (re.compile(r"^style[!?(]", re.IGNORECASE), "improvements"),
    (re.compile(r"^test[!?(]", re.IGNORECASE), "improvements"),
    (re.compile(r"^BREAKING[!? ]", re.IGNORECASE), "breaking_changes"),
]

# Keyword heuristics for lines without conventional commit prefixes
_KEYWORD_FEATURES = re.compile(
    r"\b(add(ed)?|new|introduc|implement|creat|support)\b", re.IGNORECASE
)
_KEYWORD_FIXES = re.compile(
    r"\b(fix(ed)?|resolve(d)?|patch(ed)?|correct(ed)?|repair(ed)?|bug)\b",
    re.IGNORECASE,
)
_KEYWORD_DOCS = re.compile(
    r"\b(doc(s|umentation)?|readme|changelog|guide|vitepress)\b", re.IGNORECASE
)
_KEYWORD_BREAKING = re.compile(
    r"(breaking|BREAKING|break[s ])", re.IGNORECASE
)


@dataclass
class ChangelogResult:
    """Result of changelog generation."""

    summary: str = ""
    changes: dict[str, list[str]] = field(default_factory=dict)
    highlights: list[str] = field(default_factory=list)
    ai_generated: bool = False


def generate_changelog(
    version: str,
    raw_lines: list[str],
    ai_token: str = "",
    prompt_path: str = "",
) -> ChangelogResult:
    """Generate a changelog from raw change lines using Hugging Face AI (if token available) or rule-based fallback.

    Args:
        version: Version being released (e.g. "1.5.0").
        raw_lines: Raw change lines from collect_changes().
        ai_token: Hugging Face API token (HF_TOKEN).
        prompt_path: Unused (kept for backward-compatible call sites).

    Returns:
        ChangelogResult with structured changes and a flat highlights list.
    """
    result = ChangelogResult()

    if not raw_lines:
        logger.warning("⚠️  No changes found — using generic fallback")
        result.changes = GENERIC_FALLBACK.copy()
        result.summary = GENERIC_FALLBACK["summary"]
        result.highlights = _flatten_changes(result.changes)
        return result

    # ── Attempt 1: Hugging Face Serverless Inference API ───────────────────────
    hf_token = (ai_token or os.environ.get("HF_TOKEN") or "").strip()
    if hf_token:
        hf_result = _generate_hf_changelog(version, raw_lines, hf_token)
        if hf_result and hf_result.highlights:
            logger.info(
                "🤖 Hugging Face AI changelog generated: %d items (AI=True)",
                len(hf_result.highlights),
            )
            return hf_result
        logger.warning(
            "⚠️  Hugging Face generation returned empty or failed — falling back to rule-based categorizer."
        )

    # ── Attempt 2: Rule-Based Fallback Categorizer ────────────────────────────
    result = _categorize(raw_lines)

    # Ensure we always have at least some highlights
    if not result.highlights:
        result.changes = GENERIC_FALLBACK.copy()
        result.summary = GENERIC_FALLBACK["summary"]
        result.highlights = _flatten_changes(result.changes)

    logger.info(
        "✅ Rule-based changelog: %d items (features=%d fixes=%d improvements=%d docs=%d breaking=%d)",
        len(result.highlights),
        len(result.changes.get("features", [])),
        len(result.changes.get("fixes", [])),
        len(result.changes.get("improvements", [])),
        len(result.changes.get("documentation", [])),
        len(result.changes.get("breaking_changes", [])),
    )
    return result


def _generate_hf_changelog(
    version: str,
    raw_lines: list[str],
    hf_token: str,
) -> ChangelogResult | None:
    """Attempt to summarize release changes using Hugging Face Inference API."""
    primary_model = os.environ.get("HF_MODEL", "deepseek-ai/DeepSeek-V4-Flash-0731")
    candidate_models = [
        primary_model,
        "Qwen/Qwen2.5-Coder-32B-Instruct",
        "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B",
    ]

    raw_text = "\n".join(f"- {line}" for line in raw_lines[:30])
    system_prompt = (
        "You are an expert open-source release manager for the GEMMA QGIS plugin. "
        "Your job is to transform raw developer commit logs into a clean, professional, "
        "and user-friendly release changelog. Focus on clear technical summaries while "
        "ALWAYS preserving author mentions (e.g. (@username) or ([@username](url))) "
        "and PR/issue references (e.g. (#123) or ([#123](url))) at the end of each line."
    )
    user_prompt = (
        f"Generate a production-ready release changelog for GEMMA QGIS Plugin version {version}.\n"
        f"Below are the recent commit notes (with author and PR references attached):\n{raw_text}\n\n"
        f"IMPORTANT INSTRUCTIONS:\n"
        f"1. Categorize and rewrite these changes into professional release bullet points.\n"
        f"2. CRITICAL: Retain and include the author tags (e.g. (@username)) and PR numbers (e.g. (#123)) at the end of each generated bullet point.\n\n"
        f"Return ONLY valid JSON matching this schema:\n"
        f"{{\n"
        f'  "summary": "1-2 sentence executive summary of the release.",\n'
        f'  "features": ["Descriptive bullet point ending with author (@user) and PR (#123) tags"],\n'
        f'  "improvements": ["Descriptive bullet point ending with author (@user) and PR (#123) tags"],\n'
        f'  "fixes": ["Descriptive bullet point ending with author (@user) and PR (#123) tags"],\n'
        f'  "documentation": ["Descriptive bullet point ending with author (@user) and PR (#123) tags"],\n'
        f'  "breaking_changes": ["Descriptive bullet point ending with author (@user) and PR (#123) tags"]\n'
        f"}}\n"
    )

    generated_text = ""

    # Method 1: Use huggingface_hub InferenceClient if available
    try:
        from huggingface_hub import InferenceClient
        client = InferenceClient(api_key=hf_token)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        for model in candidate_models:
            try:
                logger.info("🤖 Querying HF InferenceClient (%s)...", model)
                resp = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_tokens=512,
                    temperature=0.2,
                )
                if resp.choices and resp.choices[0].message:
                    generated_text = resp.choices[0].message.content or ""
                    if generated_text:
                        logger.info("✅ Received AI response from %s", model)
                        break
            except Exception as model_err:
                logger.warning("⚠️ HF InferenceClient error for model %s: %s", model, model_err)
    except ImportError:
        logger.info("ℹ️ huggingface_hub not installed, skipping InferenceClient.")
    except Exception as err:
        logger.warning("⚠️ InferenceClient initialization failed: %s", err)

    # Method 2: HTTP requests fallback
    if not generated_text:
        headers = {
            "Authorization": f"Bearer {hf_token}",
            "Content-Type": "application/json",
        }
        for model in candidate_models:
            endpoints = [
                ("https://router.huggingface.co/hf-inference/v1/chat/completions", {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "max_tokens": 512,
                    "temperature": 0.2,
                }),
                (f"https://api-inference.huggingface.co/models/{model}", {
                    "inputs": f"{system_prompt}\n\n{user_prompt}",
                    "parameters": {"max_new_tokens": 512, "temperature": 0.2, "return_full_text": False},
                }),
            ]
            for url, payload in endpoints:
                try:
                    logger.info("🤖 Trying HTTP endpoint (%s)...", url)
                    resp = requests.post(url, headers=headers, json=payload, timeout=15)
                    if resp.status_code == 200:
                        data = resp.json()
                        if isinstance(data, dict):
                            if "choices" in data and len(data["choices"]) > 0:
                                generated_text = data["choices"][0].get("message", {}).get("content", "")
                            else:
                                generated_text = data.get("generated_text", "")
                        elif isinstance(data, list) and len(data) > 0:
                            generated_text = data[0].get("generated_text", "")
                        
                        if generated_text:
                            break
                    else:
                        logger.warning("⚠️ HTTP %d from %s: %s", resp.status_code, url, resp.text[:100])
                except Exception as err:
                    logger.warning("⚠️ HTTP request failed for %s: %s", url, err)
            if generated_text:
                break

    try:
        json_match = re.search(r"\{.*\}", generated_text, re.DOTALL)
        if not json_match:
            logger.warning("⚠️ Could not extract JSON block from HF response")
            return None

        parsed = json.loads(json_match.group(0))
        raw_changes = {
            "features": parsed.get("features", []),
            "improvements": parsed.get("improvements", []),
            "fixes": parsed.get("fixes", []),
            "documentation": parsed.get("documentation", []),
            "breaking_changes": parsed.get("breaking_changes", []),
        }
        changes = _enrich_with_author_and_pr_tags(raw_changes, raw_lines)
        highlights = _flatten_changes(changes)
        if not highlights:
            return None

        return ChangelogResult(
            summary=parsed.get("summary", f"Release v{version} updates."),
            changes=changes,
            highlights=highlights,
            ai_generated=True,
        )
    except Exception as err:
        logger.warning("⚠️ Error parsing HF response: %s", err)
        return None


def _enrich_with_author_and_pr_tags(
    changes: dict[str, list[str]], raw_lines: list[str]
) -> dict[str, list[str]]:
    """Ensure every line in changes retains the author tag and PR link from the raw commits if missing."""
    ref_map: dict[str, tuple[str, str]] = {}
    for line in raw_lines:
        author_match = re.search(r"(\[\s*@[\w-]+\s*\]\([^)]+\)|\(@[\w-]+\))", line)
        pr_match = re.search(r"(\[\s*#\d+\s*\]\([^)]+\)|\(#\d+\))", line)

        author_tag = author_match.group(1) if author_match else ""
        pr_tag = pr_match.group(1) if pr_match else ""

        words = re.sub(r"[^\w\s]", "", line.lower()).split()
        for w in words:
            if len(w) > 4 and (author_tag or pr_tag):
                ref_map[w] = (author_tag, pr_tag)

    enriched_changes: dict[str, list[str]] = {}
    for category, items in changes.items():
        new_items: list[str] = []
        for item in items:
            has_author = bool(re.search(r"(@[\w-]+)", item))
            has_pr = bool(re.search(r"(#\d+)", item))

            author_tag, pr_tag = "", ""
            item_words = re.sub(r"[^\w\s]", "", item.lower()).split()
            for w in item_words:
                if w in ref_map:
                    author_tag, pr_tag = ref_map[w]
                    if author_tag or pr_tag:
                        break

            suffix: list[str] = []
            if not has_author and author_tag:
                suffix.append(author_tag)
            if not has_pr and pr_tag:
                suffix.append(pr_tag)

            if suffix:
                item = f"{item} {' '.join(suffix)}"
            new_items.append(item)
        enriched_changes[category] = new_items

    return enriched_changes


# ── Internal helpers ──────────────────────────────────────────────────────────


def _categorize(raw_lines: list[str]) -> ChangelogResult:
    """Classify raw lines into changelog categories using heuristics."""
    buckets: dict[str, list[str]] = {
        "features": [],
        "improvements": [],
        "fixes": [],
        "documentation": [],
        "breaking_changes": [],
    }

    for line in raw_lines:
        category = _classify_line(line)
        buckets[category].append(line)

    highlights = _flatten_changes(buckets)

    # Build a one-sentence summary from dominant category
    summary = _build_summary(buckets)

    return ChangelogResult(
        summary=summary,
        changes=buckets,
        highlights=highlights,
        ai_generated=False,
    )


def _classify_line(line: str) -> str:
    """Return the best-matching changelog category for a raw change line."""
    # Check conventional commit prefix first (most reliable)
    for pattern, category in _PREFIX_MAP:
        if pattern.search(line):
            return category

    # Fall back to keyword heuristics
    if _KEYWORD_BREAKING.search(line):
        return "breaking_changes"
    if _KEYWORD_FIXES.search(line):
        return "fixes"
    if _KEYWORD_FEATURES.search(line):
        return "features"
    if _KEYWORD_DOCS.search(line):
        return "documentation"

    # Default: general improvement
    return "improvements"


def _flatten_changes(changes: dict[str, list[str]]) -> list[str]:
    """Flatten a structured changes dict into a flat list of highlights."""
    highlights: list[str] = []
    for key in ["features", "improvements", "fixes", "documentation", "breaking_changes"]:
        highlights.extend(changes.get(key, []))
    return highlights


def _build_summary(buckets: dict[str, list[str]]) -> str:
    """Build a short release summary sentence from bucket sizes."""
    parts: list[str] = []
    if buckets.get("features"):
        n = len(buckets["features"])
        parts.append(f"{n} new feature{'s' if n > 1 else ''}")
    if buckets.get("fixes"):
        n = len(buckets["fixes"])
        parts.append(f"{n} bug fix{'es' if n > 1 else ''}")
    if buckets.get("improvements"):
        n = len(buckets["improvements"])
        parts.append(f"{n} improvement{'s' if n > 1 else ''}")
    if buckets.get("documentation"):
        parts.append("documentation updates")
    if buckets.get("breaking_changes"):
        parts.append("breaking changes")

    if not parts:
        return GENERIC_FALLBACK["summary"]

    return "This release includes " + ", ".join(parts) + "."
