"""YouTube lead sourcing: geo-targeted API, scoring, auto-pitch, ytscrape fallback."""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from src.database import (
    TARGET_REGION_CODES,
    assign_batch_priorities,
    calculate_lead_score,
    insert_lead,
    mark_search_completed,
    save_search_paused,
    update_lead_score_priority,
    upsert_pitch,
)
from src.config import get_settings
from src.llm_pipeline import generate_pitch

EMAIL_REGEX = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    re.IGNORECASE,
)
LINKEDIN_REGEX = re.compile(
    r"(?:https?://)?(?:www\.)?linkedin\.com/(?:in|company|pub)/[A-Za-z0-9_\-/%+.]+",
    re.IGNORECASE,
)
INSTAGRAM_REGEX = re.compile(
    r"(?:https?://)?(?:www\.)?instagram\.com/[A-Za-z0-9_.]+/?",
    re.IGNORECASE,
)
TWITTER_REGEX = re.compile(
    r"(?:https?://)?(?:www\.)?(?:twitter\.com|x\.com)/[A-Za-z0-9_]+/?",
    re.IGNORECASE,
)

QUOTA_EXCEEDED = "QUOTA_EXCEEDED"
DEFAULT_MIN_SUBS = 5_000
DEFAULT_MAX_SUBS = 500_000
# YouTube search.list accepts one regionCode; we rotate across top English CPM markets.
GEO_REGION_CODES = TARGET_REGION_CODES  # US, GB, CA, AU, IE, NZ


class QuotaExceededError(Exception):
    """Raised when official API quota is exhausted and scraper fallback also fails."""

    def __init__(
        self,
        message: str = "Quota Exceeded - Resume Tomorrow",
        leads: Optional[List[Dict[str, Any]]] = None,
        next_page_token: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.code = QUOTA_EXCEEDED
        self.leads = leads or []
        self.next_page_token = next_page_token


def extract_email(text: str) -> Optional[str]:
    if not text:
        return None
    match = EMAIL_REGEX.search(text)
    return match.group(0).lower() if match else None


def _normalize_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    if url.startswith("//"):
        url = "https:" + url
    if not re.match(r"^https?://", url, re.IGNORECASE):
        url = "https://" + url
    return url.rstrip("/")


def extract_contacts(text: str, extra_links: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Contact hierarchy: email → LinkedIn → Instagram → Twitter."""
    blob = text or ""
    if extra_links:
        parts = [blob]
        for k, v in extra_links.items():
            parts.append(str(k))
            parts.append(str(v))
        blob = "\n".join(parts)

    email = extract_email(blob) or ""
    linkedin = instagram = twitter = ""

    li = LINKEDIN_REGEX.search(blob)
    if li:
        linkedin = _normalize_url(li.group(0))
    ig = INSTAGRAM_REGEX.search(blob)
    if ig:
        instagram = _normalize_url(ig.group(0))
    tw = TWITTER_REGEX.search(blob)
    if tw:
        twitter = _normalize_url(tw.group(0))

    if extra_links:
        for key, value in extra_links.items():
            combined = f"{key} {value}".lower()
            url = _normalize_url(value)
            if not linkedin and "linkedin" in combined:
                linkedin = url
            if not instagram and "instagram" in combined:
                instagram = url
            if not twitter and ("twitter" in combined or "x.com" in combined):
                twitter = url

    return {
        "email": email,
        "linkedin": linkedin,
        "instagram": instagram,
        "twitter": twitter,
    }


def has_contact(contacts: Dict[str, str]) -> bool:
    return any((contacts.get(k) or "").strip() for k in ("email", "linkedin", "instagram", "twitter"))


MONETIZATION_KEYWORDS = (
    "buy",
    "shop",
    "store",
    "merch",
    "course",
    "consulting",
    "business inquiries",
    "business enquiry",
    "sponsor",
    "patreon",
    "gumroad",
)


def detect_monetization(
    description: str,
    extra_links: Optional[Dict[str, str]] = None,
    contacts: Optional[Dict[str, str]] = None,
) -> int:
    """
    Return 1 if description/links suggest commercial monetization intent.
    """
    parts = [description or ""]
    if extra_links:
        for k, v in extra_links.items():
            parts.append(str(k))
            parts.append(str(v))
    if contacts:
        for v in contacts.values():
            parts.append(str(v))
    blob = " ".join(parts).lower()
    for keyword in MONETIZATION_KEYWORDS:
        if keyword in blob:
            return 1
    return 0


def _is_quota_error(error: HttpError) -> bool:
    if getattr(error, "resp", None) is None:
        return False
    status = int(error.resp.status)
    if status not in (403, 429):
        return False
    content = ""
    try:
        content = error.content.decode("utf-8") if isinstance(error.content, bytes) else str(error.content)
    except Exception:
        content = str(error)
    lowered = content.lower()
    return (
        "quota" in lowered
        or "exceeded" in lowered
        or "daily limit" in lowered
        or "ratelimitexceeded" in lowered
        or "rate limit" in lowered
        or status == 429
    )


def _get_youtube():
    settings = get_settings()
    if not settings.youtube_api_key:
        raise ValueError("YOUTUBE_API_KEY is not configured in .env")
    return build("youtube", "v3", developerKey=settings.youtube_api_key, cache_discovery=False)


def _parse_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _extract_country(channel: Dict[str, Any]) -> str:
    branding = (channel.get("brandingSettings") or {}).get("channel") or {}
    country = branding.get("country") or channel.get("snippet", {}).get("country") or ""
    return str(country).strip().upper()


def _auto_generate_pitch(lead: Dict[str, Any]) -> None:
    """Generate and persist a pitch draft immediately after scrape."""
    try:
        pitch, used_fallback = generate_pitch(
            lead.get("channel_name", ""),
            lead.get("description", ""),
        )
        lead["pitch_draft"] = pitch
        lead["_pitch_fallback"] = bool(used_fallback)
        upsert_pitch(lead["channel_id"], pitch)
    except Exception as exc:  # noqa: BLE001
        lead["pitch_draft"] = lead.get("pitch_draft") or ""
        lead["_pitch_fallback"] = True
        lead["_pitch_error"] = str(exc)


def _finalize_batch(leads: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Score, assign Priority A/B (top 5%), persist, and auto-pitch."""
    if not leads:
        return []

    for lead in leads:
        monetized = 1 if int(lead.get("has_monetization") or 0) else 0
        score = calculate_lead_score(
            subscriber_count=int(lead.get("subscriber_count") or 0),
            total_views=int(lead.get("total_views") or 0),
            avg_views=int(lead.get("avg_views") or 0),
            country=lead.get("country") or "",
            has_monetization=monetized,
        )
        lead["has_monetization"] = monetized
        lead["lead_score"] = score
        lead["priority"] = "B"

    ranked = assign_batch_priorities(leads)
    for lead in ranked:
        # Persist score/priority (and country) even if INSERT OR IGNORE skipped a dupe row
        update_lead_score_priority(
            lead["channel_id"],
            int(lead.get("lead_score") or 0),
            lead.get("priority") or "B",
            lead.get("country") or "",
            has_monetization=int(lead.get("has_monetization") or 0),
        )
        if not (lead.get("pitch_draft") or "").strip():
            _auto_generate_pitch(lead)
    return ranked


def _build_lead(
    *,
    channel_id: str,
    channel_name: str,
    subscriber_count: int,
    avg_views: int,
    description: str,
    contacts: Dict[str, str],
    country: str = "",
    total_views: int = 0,
    extra_links: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    monetized = detect_monetization(description, extra_links=extra_links, contacts=contacts)
    score = calculate_lead_score(
        subscriber_count=subscriber_count,
        total_views=total_views,
        avg_views=avg_views,
        country=country,
        has_monetization=monetized,
    )
    return {
        "channel_id": channel_id,
        "channel_name": channel_name or "Unknown",
        "subscriber_count": int(subscriber_count or 0),
        "avg_views": int(avg_views or 0),
        "total_views": int(total_views or 0),
        "email": contacts.get("email") or "",
        "linkedin": contacts.get("linkedin") or "",
        "instagram": contacts.get("instagram") or "",
        "twitter": contacts.get("twitter") or "",
        "country": (country or "").upper(),
        "lead_score": score,
        "priority": "B",
        "has_monetization": monetized,
        "description": description or "",
        "pitch_draft": "",
        "email_status": "pending",
    }


# Full country name → ISO 3166-1 alpha-2 for YouTube regionCode
COUNTRY_NAME_TO_CODE: Dict[str, str] = {
    "United States": "US",
    "United Kingdom": "GB",
    "Canada": "CA",
    "Australia": "AU",
    "Ireland": "IE",
    "New Zealand": "NZ",
    "India": "IN",
    "Germany": "DE",
    "Singapore": "SG",
    "France": "FR",
    "Netherlands": "NL",
    "Sweden": "SE",
    "United Arab Emirates": "AE",
    "South Africa": "ZA",
    "Philippines": "PH",
    "Brazil": "BR",
}


def map_geo_to_region_codes(geo_values: Optional[List[str]]) -> List[str]:
    """Map UI country names or raw ISO codes to YouTube regionCode values."""
    if not geo_values:
        return []
    codes: List[str] = []
    seen: set[str] = set()
    for value in geo_values:
        raw = str(value or "").strip()
        if not raw:
            continue
        if raw in COUNTRY_NAME_TO_CODE:
            cc = COUNTRY_NAME_TO_CODE[raw]
        elif len(raw) == 2 and raw.isalpha():
            cc = raw.upper()
        else:
            # Case-insensitive name match
            matched = next(
                (code for name, code in COUNTRY_NAME_TO_CODE.items() if name.lower() == raw.lower()),
                "",
            )
            cc = matched
        if cc and cc not in seen:
            codes.append(cc)
            seen.add(cc)
    return codes


def _normalize_regions(region_codes: Optional[List[str]]) -> List[str]:
    """Normalize UI geo values (names or ISO codes) to ISO region codes."""
    mapped = map_geo_to_region_codes(region_codes)
    if mapped:
        return mapped
    # Empty input → fall back to default English CPM set for API safety
    return list(GEO_REGION_CODES)


def _fetch_via_official_api(
    query: str,
    min_subs: int,
    max_subs: int,
    max_results: int,
    page_token: Optional[str],
    start_page: int,
    progress_callback: Optional[Callable[[float, str], None]],
    region_codes: Optional[List[str]] = None,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    youtube = _get_youtube()
    found: List[Dict[str, Any]] = []
    seen_ids: set[str] = set()
    next_page_token: Optional[str] = page_token or None
    resume_token: Optional[str] = page_token or None
    page_number = max(1, int(start_page or 1))
    scanned = 0
    target = max(1, max_results)
    regions = _normalize_regions(region_codes)
    region_index = 0
    region_code = regions[region_index]

    def report(pct: float, msg: str) -> None:
        if progress_callback:
            progress_callback(min(pct, 1.0), msg)

    report(
        0.02,
        f"Official API · geo {','.join(regions)} · region={region_code} · page {page_number}…",
    )

    try:
        while len(found) < max_results:
            resume_token = next_page_token
            request_kwargs: Dict[str, Any] = {
                "part": "snippet",
                "type": "channel",
                "q": query,
                "maxResults": min(50, max_results),
                "regionCode": region_code,  # single ISO code per API call
                "relevanceLanguage": "en",
            }
            if next_page_token:
                request_kwargs["pageToken"] = next_page_token

            search_response = youtube.search().list(**request_kwargs).execute()
            items = search_response.get("items", [])
            if not items:
                # Advance to next geo market
                region_index += 1
                if region_index >= len(regions):
                    next_page_token = None
                    break
                region_code = regions[region_index]
                next_page_token = None
                page_number = 1
                report(0.05, f"Switching geo region → {region_code}")
                continue

            channel_ids = [
                item["snippet"]["channelId"]
                if "channelId" in item.get("snippet", {})
                else item["id"].get("channelId")
                for item in items
            ]
            channel_ids = [cid for cid in channel_ids if cid and cid not in seen_ids]
            if not channel_ids:
                next_page_token = search_response.get("nextPageToken")
                if not next_page_token:
                    region_index += 1
                    if region_index >= len(regions):
                        break
                    region_code = regions[region_index]
                    next_page_token = None
                    page_number = 1
                    continue
                page_number += 1
                continue

            channels_response = (
                youtube.channels()
                .list(
                    part="snippet,statistics,brandingSettings",
                    id=",".join(channel_ids),
                    maxResults=50,
                )
                .execute()
            )

            for channel in channels_response.get("items", []):
                scanned += 1
                cid = channel.get("id") or ""
                if not cid or cid in seen_ids:
                    continue
                stats = channel.get("statistics", {})
                snippet = channel.get("snippet", {})
                subs = _parse_int(stats.get("subscriberCount"))
                if subs < min_subs or subs > max_subs:
                    continue

                description = snippet.get("description") or ""
                contacts = extract_contacts(description)
                if not has_contact(contacts):
                    continue

                view_count = _parse_int(stats.get("viewCount"))
                video_count = max(_parse_int(stats.get("videoCount")), 1)
                avg_views = view_count // video_count
                country = _extract_country(channel)

                lead = _build_lead(
                    channel_id=cid,
                    channel_name=snippet.get("title") or "Unknown",
                    subscriber_count=subs,
                    avg_views=avg_views,
                    description=description,
                    contacts=contacts,
                    country=country,
                    total_views=view_count,
                )
                insert_lead(lead)
                seen_ids.add(cid)
                found.append(lead)
                report(
                    0.05 + 0.85 * (len(found) / target),
                    f"API · {len(found)} leads · {region_code} · scanned {scanned}",
                )
                if len(found) >= max_results:
                    break

            next_page_token = search_response.get("nextPageToken")
            resume_token = next_page_token
            if not next_page_token:
                region_index += 1
                if region_index >= len(regions):
                    break
                region_code = regions[region_index]
                next_page_token = None
                page_number = 1
            elif len(found) < max_results:
                page_number += 1
    except HttpError as exc:
        if _is_quota_error(exc):
            exc.resume_token = resume_token  # type: ignore[attr-defined]
            exc.resume_page = page_number  # type: ignore[attr-defined]
            exc.partial_leads = list(found)  # type: ignore[attr-defined]
        raise

    report(0.92, f"Scoring & auto-pitching {len(found)} lead(s)…")
    ranked = _finalize_batch(found)
    report(1.0, f"Official API done — {len(ranked)} qualified lead(s).")
    return ranked, next_page_token


def _fetch_via_ytscrape(
    query: str,
    min_subs: int,
    max_subs: int,
    max_results: int,
    progress_callback: Optional[Callable[[float, str], None]],
) -> List[Dict[str, Any]]:
    """Quota-free InnerTube scraper fallback via ytscrape."""
    from ytscrape import SearchFilter, YouTube

    found: List[Dict[str, Any]] = []
    scanned = 0
    search_cap = max(max_results * 8, 40)

    def report(pct: float, msg: str) -> None:
        if progress_callback:
            progress_callback(min(pct, 1.0), msg)

    report(0.05, "Scraper fallback active (ytscrape)…")

    with YouTube(language="en", region="US") as yt:
        for channel in yt.search(
            query,
            filter=SearchFilter.CHANNELS,
            max_results=search_cap,
        ):
            if len(found) >= max_results:
                break
            scanned += 1
            channel_id = getattr(channel, "channel_id", None) or ""
            if not channel_id:
                continue

            try:
                details = yt.channel(channel_id)
            except Exception:
                continue

            subs = _parse_int(getattr(details, "subscribers", None))
            if subs < min_subs or subs > max_subs:
                continue

            description = getattr(details, "description", None) or ""
            links = getattr(details, "links", None) or {}
            if not isinstance(links, dict):
                links = {}

            contacts = extract_contacts(description, extra_links=links)
            if not has_contact(contacts):
                continue

            view_count = _parse_int(getattr(details, "view_count", None))
            video_count = max(_parse_int(getattr(details, "video_count", None)), 1)
            avg_views = view_count // video_count if view_count else 0
            country = str(getattr(details, "country", None) or "").strip().upper()

            lead = _build_lead(
                channel_id=channel_id,
                channel_name=getattr(details, "title", None)
                or getattr(channel, "title", None)
                or "Unknown",
                subscriber_count=subs,
                avg_views=avg_views,
                description=description,
                contacts=contacts,
                country=country,
                total_views=view_count,
                extra_links=links,
            )
            insert_lead(lead)
            found.append(lead)
            report(
                0.1 + 0.75 * (len(found) / max(1, max_results)),
                f"Scraper · {len(found)} contactable · scanned {scanned}",
            )

    report(0.9, f"Scoring & auto-pitching {len(found)} lead(s)…")
    return _finalize_batch(found)


def fetch_leads(
    query: str,
    min_subs: int = DEFAULT_MIN_SUBS,
    max_subs: int = DEFAULT_MAX_SUBS,
    max_results: int = 50,
    page_token: Optional[str] = None,
    start_page: int = 1,
    region_codes: Optional[List[str]] = None,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> Tuple[List[Dict[str, Any]], Optional[str], bool]:
    """
    Geo-targeted YouTube search with scoring, auto-pitch, and scraper fallback.

    region_codes: dynamic list of ISO country codes from the UI (e.g. US, GB, CA, AU).
    Priority A = top 5% of whatever batch these filters return.

    Returns (leads, next_page_token, is_fallback).
    """
    min_subs = max(int(min_subs), 0)
    max_subs = max(int(max_subs), min_subs)
    regions = _normalize_regions(region_codes)

    def report(pct: float, msg: str) -> None:
        if progress_callback:
            progress_callback(min(pct, 1.0), msg)

    try:
        leads, next_token = _fetch_via_official_api(
            query=query,
            min_subs=min_subs,
            max_subs=max_subs,
            max_results=max_results,
            page_token=page_token,
            start_page=start_page,
            progress_callback=progress_callback,
            region_codes=regions,
        )
        mark_search_completed(query=query)
        return leads, next_token, False

    except HttpError as exc:
        if not _is_quota_error(exc):
            raise

        resume_token = getattr(exc, "resume_token", page_token)
        resume_page = getattr(exc, "resume_page", start_page)
        partial = list(getattr(exc, "partial_leads", []) or [])

        save_search_paused(
            query=query,
            next_page_token=resume_token,
            page_number=max(1, int(resume_page or 1)),
            min_subs=min_subs,
            max_subs=max_subs,
        )
        report(0.2, "Quota exceeded — switching to scraper fallback…")

        try:
            scraped = _fetch_via_ytscrape(
                query=query,
                min_subs=min_subs,
                max_subs=max_subs,
                max_results=max_results,
                progress_callback=progress_callback,
            )
            # Merge partial API hits + scraper hits, then re-rank as one batch
            by_id: Dict[str, Dict[str, Any]] = {lead["channel_id"]: lead for lead in partial}
            for lead in scraped:
                by_id[lead["channel_id"]] = lead
            return _finalize_batch(list(by_id.values())), resume_token, True
        except Exception as scrape_exc:  # noqa: BLE001
            finalized = _finalize_batch(partial) if partial else []
            raise QuotaExceededError(
                "Quota Exceeded - Resume Tomorrow (scraper fallback failed)",
                leads=finalized,
                next_page_token=resume_token,
            ) from scrape_exc
