"""Groq outreach generation with multi-key failover + Mad-Libs template fallback."""

from __future__ import annotations

import re
from collections import Counter
from typing import List, Optional, Tuple

from groq import Groq

from src.config import get_settings

# Prefer Llama-3 when exposed; otherwise current Groq catalog (GPT-OSS / Qwen).
FALLBACK_MODELS = (
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "openai/gpt-oss-20b",
    "openai/gpt-oss-120b",
    "qwen/qwen3.8-27b",
)

SYSTEM_PROMPT = (
    "You are an expert B2B SDR writing concise, personalized cold emails for IncuBrix, "
    "a growth engine that helps creators and brands scale YouTube channels with data-driven "
    "outreach and audience growth tooling. Write professionally, avoid fluff, and never "
    "invent facts about the recipient."
)

STOPWORDS = {
    "about", "after", "also", "been", "being", "between", "channel", "check", "click",
    "collab", "collaboration", "contact", "content", "creator", "daily", "email", "every",
    "follow", "from", "have", "here", "https", "into", "just", "like", "link", "make",
    "more", "official", "please", "subscribe", "their", "there", "these", "this", "that",
    "video", "videos", "watch", "website", "welcome", "what", "when", "where", "with",
    "would", "your", "yours", "youtube", "business", "free", "best", "new", "get",
    "http", "www", "com", "org", "net", "mail", "gmail", "outlook", "hello", "thanks",
}

# Niche seeds boost keyword extraction toward recognizable verticals
NICHE_SEEDS = {
    "fitness", "health", "workout", "nutrition", "tech", "saas", "software", "startup",
    "marketing", "agency", "finance", "fintech", "crypto", "web3", "reviews", "gaming",
    "education", "coaching", "realestate", "ecommerce", "brand", "growth", "b2b",
    "podcast", "ai", "devtools", "productivity", "design", "travel", "beauty",
}


def _build_user_prompt(channel_name: str, channel_description: str) -> str:
    niche_hint = (channel_description or "").strip()[:1200] or "general content creator"
    return (
        f"Write a personalized 3-sentence cold email pitching IncuBrix's growth tool "
        f"to the YouTube channel \"{channel_name}\".\n\n"
        f"Channel description / niche context:\n{niche_hint}\n\n"
        "Requirements:\n"
        "- Exactly 3 sentences.\n"
        "- Open with a specific observation about their niche or content theme.\n"
        "- Explain how IncuBrix helps channels like theirs grow and convert audience into leads.\n"
        "- End with a soft CTA to book a short demo or reply.\n"
        "- Do not use placeholders like [Name]. Do not include a subject line."
    )


def _call_groq(api_key: str, model: str, channel_name: str, channel_description: str) -> str:
    client = Groq(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        temperature=0.7,
        max_tokens=400,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(channel_name, channel_description)},
        ],
    )
    content = response.choices[0].message.content if response.choices else None
    if not content or not content.strip():
        raise RuntimeError("Empty response from Groq")
    return content.strip()


def extract_niche_keywords(channel_description: str, limit: int = 3) -> List[str]:
    """Pull 2–3 niche keywords from a channel description for Mad-Libs fallback."""
    text = (channel_description or "").lower()
    text = re.sub(r"https?://\S+|www\.\S+|[\w.+-]+@[\w.-]+", " ", text)
    tokens = re.findall(r"[a-z][a-z0-9+]{2,}", text)

    counts: Counter[str] = Counter()
    for tok in tokens:
        if tok in STOPWORDS or tok.isdigit():
            continue
        weight = 3 if tok in NICHE_SEEDS else 1
        counts[tok] += weight

    # Prefer known niche seeds that appear at least once
    ranked = [w for w, _ in counts.most_common(12)]
    keywords: List[str] = []
    for word in ranked:
        if word in NICHE_SEEDS and word not in keywords:
            keywords.append(word)
        if len(keywords) >= limit:
            break
    if len(keywords) < 2:
        for word in ranked:
            if word not in keywords:
                keywords.append(word)
            if len(keywords) >= limit:
                break

    while len(keywords) < 2:
        keywords.append("growth")
    return keywords[:limit]


def template_pitch(channel_name: str, channel_description: str) -> str:
    """Mad-Libs style 3-sentence cold email when Groq is unavailable."""
    kws = extract_niche_keywords(channel_description, limit=3)
    primary = kws[0]
    secondary = kws[1] if len(kws) > 1 else kws[0]
    tertiary = kws[2] if len(kws) > 2 else secondary
    name = (channel_name or "your channel").strip()

    return (
        f"I've been following {name}'s work around {primary} and {secondary}, "
        f"and the clarity you bring to that niche stands out. "
        f"IncuBrix helps {primary}/{tertiary} creators turn audience attention into "
        f"qualified outbound conversations with contact-first sourcing and personalized outreach. "
        f"If you're open to it, I'd love to show a quick demo of how teams in the "
        f"{secondary} space use IncuBrix to grow partnerships — worth a short reply?"
    )


def generate_pitch(channel_name: str, channel_description: str) -> Tuple[str, bool]:
    """
    Generate a personalized 3-sentence cold email.

    Returns (pitch, is_fallback):
      - is_fallback=False when Groq succeeds
      - is_fallback=True when all Groq keys/models fail and template is used
    """
    settings = get_settings()
    keys: List[str] = settings.groq_keys()
    errors: List[str] = []

    if keys:
        for key_index, api_key in enumerate(keys):
            for model in FALLBACK_MODELS:
                try:
                    pitch = _call_groq(api_key, model, channel_name, channel_description)
                    return pitch, False
                except Exception as exc:  # noqa: BLE001 — failover intentionally broad
                    errors.append(f"key[{key_index}]/{model}: {exc}")
                    continue

    # Smart template fallback when Groq quota/keys are exhausted
    return template_pitch(channel_name, channel_description), True


def generate_pitch_safe(
    channel_name: str,
    channel_description: str,
) -> Tuple[Optional[str], bool, Optional[str]]:
    """Return (pitch, is_fallback, error_message). Template fallback rarely errors."""
    try:
        pitch, is_fallback = generate_pitch(channel_name, channel_description)
        return pitch, is_fallback, None
    except Exception as exc:  # noqa: BLE001
        return None, True, str(exc)
