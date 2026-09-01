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
from typing import Any
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
    primary_model = os.environ.get("HF_MODEL", "Qwen/Qwen2.5-Coder-32B-Instruct")
    candidate_models = [
        primary_model,
        "meta-llama/Llama-3.3-70B-Instruct",
        "deepseek-ai/DeepSeek-V4-Flash-0731",
    ]

    raw_text = "\n".join(f"- {line}" for line in raw_lines[:30])
    system_prompt = (
        "You are an expert open-source release manager for the GEMMA QGIS plugin. "
        "Your job is to transform raw developer commit logs into a clean, professional, "
        "and user-friendly release changelog. Focus on clear technical summaries. "
        "Do NOT include duplicate author tags or unlinked (@user #123) references inside the summary text. "
        "Each bullet point should end with at most one linked author tag (e.g. ([@username](https://github.com/username))) "
        "and at most one linked PR reference (e.g. ([#123](https://github.com/owner/repo/pull/123)))."
    )
    user_prompt = (
        f"Generate a production-ready release changelog for GEMMA QGIS Plugin version {version}.\n"
        f"Below are the recent commit notes (with author and PR references attached):\n{raw_text}\n\n"
        f"IMPORTANT INSTRUCTIONS:\n"
        f"1. Categorize and rewrite these changes into professional, concise release bullet points.\n"
        f"2. Retain exactly one linked author tag (e.g. ([@username](https://github.com/username))) and/or one PR link (e.g. ([#123](url))) at the end of each generated bullet point.\n"
        f"3. CRITICAL: Never produce duplicate author tags or unlinked compound tags like (@username #123).\n\n"
        f"Return ONLY valid JSON matching this schema:\n"
        f"{{\n"
        f'  "features": ["Descriptive bullet point ending with author and PR tags"],\n'
        f'  "improvements": ["Descriptive bullet point ending with author and PR tags"],\n'
        f'  "fixes": ["Descriptive bullet point ending with author and PR tags"],\n'
        f'  "documentation": ["Descriptive bullet point ending with author and PR tags"],\n'
        f'  "breaking_changes": ["Descriptive bullet point ending with author and PR tags"]\n'
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
                    max_tokens=2048,
                    temperature=0.2,
                )
                if resp.choices and resp.choices[0].message:
                    # Skip truncated responses — incomplete JSON is unusable
                    if resp.choices[0].finish_reason == "length":
                        logger.warning(
                            "⚠️ Response truncated (finish_reason=length) for %s, trying next model",
                            model,
                        )
                        continue
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

    # Method 2: HTTP requests fallback — use the general Inference Providers router
    if not generated_text:
        headers = {
            "Authorization": f"Bearer {hf_token}",
            "Content-Type": "application/json",
        }
        ROUTER_URL = "https://router.huggingface.co/v1/chat/completions"

        for model in candidate_models:
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "max_tokens": 2048,
                "temperature": 0.2,
            }
            try:
                logger.info("🤖 Trying router endpoint for %s ...", model)
                resp = requests.post(ROUTER_URL, headers=headers, json=payload, timeout=30)
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, dict) and "choices" in data and len(data["choices"]) > 0:
                        choice = data["choices"][0]
                        # Skip truncated responses — incomplete JSON is unusable
                        if choice.get("finish_reason") == "length":
                            logger.warning(
                                "⚠️ Response truncated (finish_reason=length) for %s, trying next model",
                                model,
                            )
                            continue
                        generated_text = choice.get("message", {}).get("content", "")
                    if generated_text:
                        logger.info("✅ Received AI response from router (%s)", model)
                        break
                else:
                    logger.warning(
                        "⚠️ HTTP %d from router (%s): %s",
                        resp.status_code, model, resp.text[:200],
                    )
            except Exception as err:
                logger.warning("⚠️ Router request failed for %s: %s", model, err)

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


def _parse_item_tags(text: str) -> tuple[str, str | None, str | None, str | None]:
    """Parse a line into clean description text, author username, PR number, and PR URL.

    Strips all variations of author mentions and PR tags from the text.
    """
    cleaned = text.strip()

    # 1. Extract PR number and URL
    pr_num = None
    pr_url = None
    url_match = re.search(r"https?://github\.com/([^/]+)/([^/]+)/(?:pull|issues)/(\d+)", cleaned)
    if url_match:
        pr_num = url_match.group(3)
        pr_url = url_match.group(0)
    else:
        md_pr_match = re.search(r"\[\s*#(\d+)\s*\]\((https?://[^\s)]+)\)", cleaned)
        if md_pr_match:
            pr_num = md_pr_match.group(1)
            pr_url = md_pr_match.group(2)
        else:
            compound_match = re.search(r"\(@[\w-]+\s*(?:[,&/-]\s*|\s+)#?(\d+)\)", cleaned)
            if compound_match:
                pr_num = compound_match.group(1)
            else:
                num_match = re.search(r"\(\s*#(\d+)\s*\)", cleaned)
                if num_match:
                    pr_num = num_match.group(1)
                else:
                    trailing_num = re.search(r"(?:^|\s)#(\d+)(?:\s*$)", cleaned)
                    if trailing_num:
                        pr_num = trailing_num.group(1)

    # 2. Extract author
    author = None
    embedded_author = re.search(
        r"\(\s*\[?@([\w-]+)\]?(?:\([^)]*\))?(?:\s*[,&/-]?\s*#?\d+)?\s*\)", cleaned
    )
    if embedded_author:
        author = embedded_author.group(1)
    else:
        md_author = re.search(r"\[\s*@([\w-]+)\s*\](?:\([^)]*\))?", cleaned)
        if md_author:
            author = md_author.group(1)
        else:
            by_author = re.search(r"\sby\s+@([\w-]+)", cleaned)
            if by_author:
                author = by_author.group(1)

    if author and ("[bot]" in author.lower() or "github-actions" in author.lower()):
        author = None

    # 3. Strip all tags, URLs, and markers from description text
    cleaned = re.sub(r"^[\s*\-•]+\s*", "", cleaned)
    # Strip "by @user in https://..." or "in https://..." (safe against eating parens)
    cleaned = re.sub(r"\s+by\s+@[\w-]+(?:\s+in\s+https?://[^\s)]+)?", "", cleaned)
    cleaned = re.sub(r"\s+in\s+https?://[^\s)]+", "", cleaned)
    # Strip outer parens enclosing markdown links: ([@user](url)) or ([#123](url))
    cleaned = re.sub(r"\(\s*\[\s*@[\w-]+\s*\]\([^)]+\)\s*\)", "", cleaned)
    cleaned = re.sub(r"\(\s*\[\s*#\d+\s*\]\([^)]+\)\s*\)", "", cleaned)
    # Strip compound author/PR parenthesized tags: (@user #123), (@user, #123), ([@user](url) [#123](url))
    cleaned = re.sub(
        r"\(\s*\[?@[\w-]+\]?(?:\([^)]*\))?\s*(?:[,&/\-]\s*|\s+)?\[?#\d+\]?(?:\([^)]*\))?\s*\)",
        "",
        cleaned,
    )
    cleaned = re.sub(
        r"\(\s*\[?#\d+\]?(?:\([^)]*\))?\s*(?:[,&/\-]\s*|\s+)?\[?@[\w-]+\]?(?:\([^)]*\))?\s*\)",
        "",
        cleaned,
    )
    # Strip single parenthesized tags: (@user), (#123)
    cleaned = re.sub(r"\(\s*\[?@[\w-]+\]?(?:\([^)]*\))?\s*\)", "", cleaned)
    cleaned = re.sub(r"\(\s*\[?#\d+\]?(?:\([^)]*\))?\s*\)", "", cleaned)
    # Strip bare markdown links or brackets: [@user](url), [#123](url)
    cleaned = re.sub(r"\[\s*@[\w-]+\s*\]\([^)]+\)", "", cleaned)
    cleaned = re.sub(r"\[\s*#\d+\s*\]\([^)]+\)", "", cleaned)
    cleaned = re.sub(r"\[\s*@[\w-]+\s*\]", "", cleaned)
    cleaned = re.sub(r"\[\s*#\d+\s*\]", "", cleaned)
    # Strip remaining bare URLs without consuming closing parens
    cleaned = re.sub(r"https?://[^\s)]+", "", cleaned)
    # Strip standalone @user or #123 tokens
    cleaned = re.sub(r"(?:^|\s)@[\w-]+(?:\s|$)", " ", cleaned)
    cleaned = re.sub(r"(?:^|\s)#\d+(?:\s|$)", " ", cleaned)
    # Strip conventional commit prefixes (e.g. feat:, fix(scope):, feat!:)
    cleaned = re.sub(
        r"^(feat|fix|refactor|perf|docs|style|test|chore|build|ci)(\([^)]*\))?[!:]\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    # Strip trailing ellipsis and punctuation
    cleaned = re.sub(r"[…\.]+$", "", cleaned)
    cleaned = re.sub(r"[\s,;:\-()]+$", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    return cleaned, author, pr_num, pr_url


def _enrich_with_author_and_pr_tags(
    changes: dict[str, list[str]], raw_lines: list[str]
) -> dict[str, list[str]]:
    """Ensure every line in changes has exactly ONE linked author and ONE linked PR tag.

    Extracts authoritative author/PR links from raw commit lines or the generated item,
    completely strips any duplicate, plain, or compound tags from the description text,
    and attaches canonical Markdown links at the end.
    """
    # ── Parse authoritative data from raw lines ───────────────────────────
    raw_entries: list[dict[str, Any]] = []
    for raw in raw_lines:
        clean_txt, auth, p_num, p_url = _parse_item_tags(raw)
        words = set(w for w in re.sub(r"[^\w\s]", "", clean_txt.lower()).split() if len(w) > 3)
        raw_entries.append({
            "clean": clean_txt,
            "author": auth,
            "pr_num": p_num,
            "pr_url": p_url,
            "words": words,
        })

    enriched_changes: dict[str, list[str]] = {}
    for category, items in changes.items():
        new_items: list[str] = []
        for item in items:
            item_clean, item_author, item_pr_num, item_pr_url = _parse_item_tags(item)
            if not item_clean:
                continue

            item_words = set(w for w in re.sub(r"[^\w\s]", "", item_clean.lower()).split() if len(w) > 3)

            # Match against raw entries to find authoritative author & PR info
            matched_entry: dict[str, Any] | None = None

            # 1. Match by PR number if present
            if item_pr_num:
                for entry in raw_entries:
                    if entry["pr_num"] == item_pr_num:
                        matched_entry = entry
                        break

            # 2. Match by highest keyword overlap
            if not matched_entry and item_words:
                best_score = 0
                for entry in raw_entries:
                    score = len(item_words & entry["words"])
                    if score > best_score:
                        best_score = score
                        matched_entry = entry

            # Determine final author and PR
            final_author = matched_entry["author"] if matched_entry and matched_entry["author"] else item_author
            final_pr_num = matched_entry["pr_num"] if matched_entry and matched_entry["pr_num"] else item_pr_num
            final_pr_url = matched_entry["pr_url"] if matched_entry and matched_entry["pr_url"] else item_pr_url

            # Construct canonical suffix tags
            suffix_parts: list[str] = []
            if final_author:
                suffix_parts.append(f"([@{final_author}](https://github.com/{final_author}))")
            if final_pr_num:
                if final_pr_url:
                    suffix_parts.append(f"([#{final_pr_num}]({final_pr_url}))")
                else:
                    suffix_parts.append(f"(#{final_pr_num})")

            if suffix_parts:
                new_items.append(f"{item_clean} {' '.join(suffix_parts)}")
            else:
                new_items.append(item_clean)

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
