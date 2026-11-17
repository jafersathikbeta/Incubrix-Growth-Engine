"""Incubrix Growth Engine — Premium Indigo SaaS CRM (Streamlit)."""

from __future__ import annotations

import io
import smtplib
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import get_settings, save_api_keys_to_env  # noqa: E402
from src.database import (  # noqa: E402
    get_all_leads,
    get_paused_search,
    get_search_state,
    init_db,
    primary_contact,
    update_email_status,
    upsert_pitch,
)
from src.youtube_client import (  # noqa: E402
    DEFAULT_MAX_SUBS,
    DEFAULT_MIN_SUBS,
    QuotaExceededError,
    fetch_leads,
    map_geo_to_region_codes,
)

GEO_COUNTRY_OPTIONS = [
    "United States",
    "United Kingdom",
    "Canada",
    "Australia",
    "Ireland",
    "New Zealand",
    "India",
    "Germany",
    "Singapore",
    "France",
    "Netherlands",
    "Sweden",
    "United Arab Emirates",
    "South Africa",
    "Philippines",
    "Brazil",
]


st.set_page_config(
    page_title="Incubrix Growth Engine",
    page_icon="◆",
    layout="wide",
    initial_sidebar_state="collapsed",
)

CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=IBM+Plex+Mono:wght@400;500&display=swap');

:root {
  --bg0: #0b0a12;
  --bg1: #12101c;
  --surface: #181526;
  --border: #2e2748;
  --accent: #6366f1;
  --accent-2: #4f46e5;
  --accent-soft: rgba(99, 102, 241, 0.14);
  --text: #f4f2ff;
  --muted: #a39ec0;
}

html, body, [data-testid="stAppViewContainer"] {
  background:
    radial-gradient(1200px 600px at 12% -10%, rgba(99,102,241,0.22), transparent 55%),
    radial-gradient(900px 500px at 90% 0%, rgba(79,70,229,0.16), transparent 50%),
    linear-gradient(165deg, var(--bg0) 0%, var(--bg1) 50%, #0e0c18 100%) !important;
  color: var(--text) !important;
  font-family: 'Plus Jakarta Sans', sans-serif !important;
}

[data-testid="stHeader"] { background: transparent !important; }
[data-testid="stToolbar"] { display: none !important; }
[data-testid="stSidebar"], section[data-testid="stSidebar"] { display: none !important; }

.block-container {
  padding-top: 1.25rem !important;
  padding-bottom: 3rem !important;
  max-width: 1180px !important;
}

.ige-hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1.35rem;
  padding: 1.35rem 1.5rem;
  background: linear-gradient(135deg, #1a1530 0%, #15112a 55%, #1c1636 100%);
  border: 1px solid var(--border);
  border-radius: 16px;
  box-shadow: 0 0 0 1px rgba(99,102,241,0.08), 0 18px 50px rgba(0,0,0,0.35);
}
.ige-hero-left { display: flex; align-items: center; gap: 1rem; }
.ige-mark {
  width: 48px; height: 48px;
  border-radius: 14px;
  background: linear-gradient(145deg, #818cf8, #4f46e5);
  display: grid; place-items: center;
  font-weight: 800; color: white; font-size: 1.05rem;
  box-shadow: 0 0 24px rgba(99,102,241,0.55);
}
.ige-title { font-size: 1.5rem; font-weight: 800; margin: 0; letter-spacing: -0.03em; color: #f8f7ff; }
.ige-sub { margin: 0.2rem 0 0; color: var(--muted); font-size: 0.9rem; font-weight: 500; }
.ige-pill {
  font-size: 0.75rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: #c7d2fe;
  background: var(--accent-soft);
  border: 1px solid rgba(99,102,241,0.35);
  border-radius: 999px;
  padding: 0.4rem 0.75rem;
}

.ige-banner {
  padding: 0.9rem 1.15rem;
  border-radius: 12px;
  border: 1px solid var(--border);
  margin-bottom: 1rem;
  font-weight: 560;
}
.ige-banner.warn {
  background: rgba(251, 191, 36, 0.1);
  border-color: rgba(251, 191, 36, 0.35);
  color: #fcd34d;
}
.ige-banner.info {
  background: var(--accent-soft);
  border-color: rgba(99, 102, 241, 0.35);
  color: #c7d2fe;
}
.ige-fallback {
  color: #fbbf24;
  font-size: 0.82rem;
  font-style: italic;
  margin: 0.35rem 0 0.55rem;
}

div[data-testid="stTabs"] [data-baseweb="tab-list"] {
  gap: 0.35rem;
  background: rgba(24, 21, 38, 0.85);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 0.35rem;
}
div[data-testid="stTabs"] button[role="tab"] {
  color: var(--muted) !important;
  font-weight: 700 !important;
  border-radius: 10px !important;
}
div[data-testid="stTabs"] button[aria-selected="true"] {
  color: #eef2ff !important;
  background: linear-gradient(180deg, #6366f1 0%, #4f46e5 100%) !important;
}

div[data-testid="stTextInput"] input,
div[data-testid="stNumberInput"] input,
div[data-testid="stTextArea"] textarea,
div[data-baseweb="select"] > div {
  background: var(--surface) !important;
  color: var(--text) !important;
  border: 1px solid var(--border) !important;
  border-radius: 10px !important;
}

.stButton > button {
  background: linear-gradient(180deg, #6366f1 0%, #4f46e5 100%) !important;
  color: white !important;
  border: 1px solid #4338ca !important;
  border-radius: 10px !important;
  font-weight: 700 !important;
  padding: 0.5rem 1.15rem !important;
  box-shadow: 0 8px 24px rgba(79, 70, 229, 0.28) !important;
}
.stButton > button:hover {
  background: linear-gradient(180deg, #818cf8 0%, #6366f1 100%) !important;
  border-color: #6366f1 !important;
}
button[data-testid="baseButton-primary"] {
  box-shadow: 0 0 0 1px rgba(129,140,248,0.35), 0 0 28px rgba(99,102,241,0.45) !important;
}

[data-testid="stDataFrame"], [data-testid="stTable"] {
  border: 1px solid var(--border) !important;
  border-radius: 12px !important;
  overflow: hidden;
}

div[data-testid="stVerticalBlockBorderWrapper"] {
  background: linear-gradient(180deg, rgba(31,26,51,0.95), rgba(24,21,38,0.92)) !important;
  border: 1px solid var(--border) !important;
  border-radius: 16px !important;
  box-shadow: 0 10px 30px rgba(0,0,0,0.22);
}

.ige-lead-name { font-size: 1.05rem; font-weight: 750; margin: 0; color: #f8f7ff; }
.ige-lead-meta {
  color: var(--muted);
  font-size: 0.82rem;
  font-family: 'IBM Plex Mono', monospace;
  margin-top: 0.25rem;
}
.ige-status {
  display: inline-block;
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  padding: 0.2rem 0.55rem;
  border-radius: 999px;
  border: 1px solid rgba(99,102,241,0.35);
  color: #c7d2fe;
  background: var(--accent-soft);
}
.ige-status.sent { color: #6ee7b7; border-color: rgba(52,211,153,0.35); background: rgba(52,211,153,0.12); }
.ige-status.failed { color: #fca5a5; border-color: rgba(248,113,113,0.35); background: rgba(248,113,113,0.12); }
.ige-stat-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.75rem;
}
.ige-stat {
  background: rgba(99,102,241,0.08);
  border: 1px solid rgba(99,102,241,0.25);
  border-radius: 12px;
  padding: 0.85rem 1rem;
}
.ige-stat .label { color: var(--muted); font-size: 0.75rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; }
.ige-stat .value { color: #eef2ff; font-size: 1.05rem; font-weight: 750; margin-top: 0.25rem; }
.ige-api-pill {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  font-size: 0.86rem;
  font-weight: 750;
  padding: 0.55rem 0.95rem;
  border-radius: 999px;
  margin-bottom: 1rem;
  border: 1px solid transparent;
}
.ige-api-pill.ok {
  color: #bbf7d0;
  background: rgba(34, 197, 94, 0.12);
  border-color: rgba(34, 197, 94, 0.35);
  box-shadow: 0 0 18px rgba(34, 197, 94, 0.15);
}
.ige-api-pill.warn {
  color: #fde68a;
  background: rgba(251, 191, 36, 0.12);
  border-color: rgba(251, 191, 36, 0.4);
  box-shadow: 0 0 18px rgba(251, 191, 36, 0.18);
}
.ige-priority-a {
  display: inline-block;
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  padding: 0.28rem 0.7rem;
  border-radius: 999px;
  color: #bbf7d0;
  background: rgba(34, 197, 94, 0.16);
  border: 1px solid rgba(74, 222, 128, 0.55);
  box-shadow: 0 0 18px rgba(34, 197, 94, 0.45);
}
.ige-priority-b {
  display: inline-block;
  font-size: 0.72rem;
  font-weight: 750;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  padding: 0.28rem 0.7rem;
  border-radius: 999px;
  color: #cbd5e1;
  background: rgba(100, 116, 139, 0.18);
  border: 1px solid rgba(148, 163, 184, 0.35);
}
</style>
"""


def inject_css() -> None:
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def render_header() -> None:
    leads_n = len(get_all_leads())
    st.markdown(
        f"""
        <div class="ige-hero">
          <div class="ige-hero-left">
            <div class="ige-mark">IB</div>
            <div>
              <p class="ige-title">Incubrix Growth Engine</p>
              <p class="ige-sub">B2B lead gen · Contact-first YouTube · Indigo CRM</p>
            </div>
          </div>
          <div class="ige-pill">{leads_n} leads in pipeline</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def smtp_configured(host: str, port: int, email: str, password: str) -> bool:
    return bool(str(host).strip() and port and str(email).strip() and str(password).strip())


def send_email_smtp(
    host: str,
    port: int,
    username: str,
    password: str,
    to_addr: str,
    subject: str,
    body: str,
) -> None:
    msg = MIMEMultipart()
    msg["From"] = username
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))
    with smtplib.SMTP(host, int(port), timeout=30) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(username, password)
        server.sendmail(username, [to_addr], msg.as_string())


B2B_NICHES = [
    "SaaS Reviews",
    "B2B Marketing",
    "Tech Reviews",
    "Fitness Coaches",
    "Finance & Investing",
    "E-commerce",
    "Real Estate",
    "Software Tutorials",
    "Productivity",
    "AI Tools",
    "Business Podcasts",
    "Agency Growth",
    "Startup Founders",
    "Digital Marketing",
    "Content Marketing",
    "SEO & Growth",
    "Sales Training",
    "HR & Recruiting",
    "Cybersecurity",
    "Cloud Computing",
    "DevTools",
    "No-Code Tools",
    "MarTech",
    "FinTech",
    "HealthTech",
    "EdTech",
    "Creator Economy",
    "YouTube Growth",
    "Email Marketing",
    "LinkedIn Growth",
    "Product Management",
    "UX Design",
    "Web Design Agencies",
    "Shopify Stores",
    "Dropshipping",
    "Amazon Sellers",
    "Coaching Business",
    "Online Courses",
    "Consulting Firms",
    "Legal Tech",
]


def leads_dataframe(leads: List[Dict[str, Any]]) -> pd.DataFrame:
    if not leads:
        return pd.DataFrame(
            columns=[
                "channel_name",
                "priority",
                "lead_score",
                "Monetized?",
                "country",
                "subscriber_count",
                "avg_views",
                "contact",
                "email",
                "linkedin",
                "instagram",
                "twitter",
                "email_status",
                "channel_id",
            ]
        )
    enriched = []
    for lead in leads:
        row = dict(lead)
        row["contact"] = primary_contact(lead)
        row["Monetized?"] = "🟢 Yes" if int(lead.get("has_monetization") or 0) else "⚪ No"
        enriched.append(row)
    df = pd.DataFrame(enriched)
    cols = [
        "channel_name",
        "priority",
        "lead_score",
        "Monetized?",
        "country",
        "subscriber_count",
        "avg_views",
        "contact",
        "email",
        "linkedin",
        "instagram",
        "twitter",
        "email_status",
        "pitch_draft",
        "channel_id",
        "description",
    ]
    return df[[c for c in cols if c in df.columns]]


def render_api_status_pill() -> None:
    is_fallback = bool(st.session_state.get("scrape_is_fallback", False))
    if is_fallback:
        st.markdown(
            '<div class="ige-api-pill warn">🟡 <b>Scraper Fallback Active (Quota Exceeded)</b></div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="ige-api-pill ok">🟢 <b>Official API Active</b></div>',
            unsafe_allow_html=True,
        )


def _smtp_from_session() -> Dict[str, Any]:
    return {
        "host": st.session_state.get("smtp_host", ""),
        "port": int(st.session_state.get("smtp_port", 587)),
        "email": st.session_state.get("smtp_email", ""),
        "password": st.session_state.get("smtp_password", ""),
    }


def _maybe_auto_send(leads: List[Dict[str, Any]]) -> None:
    """If Settings toggle is on and SMTP is ready, send pitches that have email contacts."""
    if not st.session_state.get("auto_send_emails", False):
        return
    smtp = _smtp_from_session()
    if not smtp_configured(smtp["host"], smtp["port"], smtp["email"], smtp["password"]):
        st.warning("Auto-Send is on, but SMTP is not configured in Settings.")
        return

    pending = [
        lead
        for lead in leads
        if (lead.get("email") or "").strip()
        and (lead.get("pitch_draft") or "").strip()
        and (lead.get("email_status") or "pending") != "sent"
    ]
    if not pending:
        st.info("Auto-Send: no emailable drafts in this batch.")
        return

    ok = fail = 0
    bar = st.progress(0.0, text="Auto-sending emails…")
    for i, lead in enumerate(pending):
        try:
            send_email_smtp(
                smtp["host"],
                smtp["port"],
                smtp["email"],
                smtp["password"],
                lead["email"],
                f"Quick idea for {lead.get('channel_name', 'your channel')} × IncuBrix",
                lead["pitch_draft"],
            )
            update_email_status(lead["channel_id"], "sent")
            lead["email_status"] = "sent"
            ok += 1
        except Exception:
            update_email_status(lead["channel_id"], "failed")
            lead["email_status"] = "failed"
            fail += 1
        bar.progress((i + 1) / len(pending), text=f"Auto-send {i + 1}/{len(pending)}")
    st.success(f"Auto-Send complete · Sent {ok} · Failed {fail}")


def _run_scrape(
    *,
    query: str,
    min_subs: int,
    max_subs: int,
    max_results: int,
    region_codes: Optional[List[str]] = None,
    page_token: Optional[str] = None,
    start_page: int = 1,
) -> None:
    progress = st.progress(0.0, text="Initializing…")
    status = st.empty()

    def on_progress(pct: float, msg: str) -> None:
        progress.progress(min(max(pct, 0.0), 1.0), text=msg)
        status.caption(msg)

    try:
        leads, _token, is_fallback = fetch_leads(
            query=query.strip(),
            min_subs=int(min_subs),
            max_subs=int(max_subs),
            max_results=int(max_results),
            page_token=page_token or None,
            start_page=start_page,
            region_codes=region_codes,
            progress_callback=on_progress,
        )
        st.session_state["scrape_is_fallback"] = is_fallback
        st.session_state["quota_exceeded"] = bool(is_fallback)
        st.session_state["youtube_quota"] = "exceeded" if is_fallback else "ready"
        st.session_state["last_scrape"] = leads
        progress.progress(1.0, text=f"Complete — {len(leads)} lead(s)")
        mode = "scraper fallback" if is_fallback else "official API"
        if leads:
            a_count = sum(1 for l in leads if (l.get("priority") or "").upper() == "A")
            st.success(
                f"Found {len(leads)} qualified lead(s) via {mode} · "
                f"{a_count} Priority A · pitches auto-generated."
            )
            st.dataframe(leads_dataframe(leads), use_container_width=True, hide_index=True)
            _maybe_auto_send(leads)
        else:
            st.info(f"No contactable leads found via {mode} for this query and subscriber range.")
    except QuotaExceededError as exc:
        st.session_state["quota_exceeded"] = True
        st.session_state["scrape_is_fallback"] = True
        st.session_state["youtube_quota"] = "exceeded"
        st.session_state["last_scrape"] = exc.leads
        progress.progress(1.0, text="Quota Exceeded — Resume Tomorrow")
        st.markdown(
            '<div class="ige-banner warn">⚠ Quota Exceeded — Official API and scraper fallback failed. '
            "Progress saved. Use <b>Resume Search</b> when quota resets.</div>",
            unsafe_allow_html=True,
        )
        if exc.leads:
            st.dataframe(leads_dataframe(exc.leads), use_container_width=True, hide_index=True)
    except Exception as exc:  # noqa: BLE001
        progress.empty()
        st.error(f"YouTube scrape failed: {exc}")


def tab_scraper() -> None:
    st.subheader("Lead Scraper")
    st.caption(
        "Dynamic filters · contact hierarchy · Priority A = top 5% of each filtered batch · API → ytscrape fallback"
    )
    render_api_status_pill()

    with st.container(border=True):
        niche = st.selectbox(
            "Search niche",
            options=B2B_NICHES,
            index=None,
            placeholder="Select a B2B niche…",
            help="Predefined high-converting B2B niches for YouTube channel search",
            key="scrape_niche",
        )
        custom_query = st.text_input(
            "Or enter a custom search keyword",
            placeholder="e.g. B2B SaaS onboarding, dental marketing agency",
            key="scrape_custom_query",
        )
        # Keep empty by default; drop stale ISO codes from older UI versions
        if "scrape_geo" not in st.session_state:
            st.session_state["scrape_geo"] = []
        else:
            st.session_state["scrape_geo"] = [
                c for c in st.session_state["scrape_geo"] if c in GEO_COUNTRY_OPTIONS
            ]
        geo = st.multiselect(
            "Geo Markets",
            options=GEO_COUNTRY_OPTIONS,
            help="Shown as full country names; mapped to ISO region codes for the YouTube API",
            key="scrape_geo",
        )
        c2, c3, c4 = st.columns(3)
        with c2:
            min_subs = st.number_input(
                "Min subscribers",
                min_value=0,
                value=DEFAULT_MIN_SUBS,
                step=500,
                key="scrape_min_subs",
            )
        with c3:
            max_subs = st.number_input(
                "Max subscribers",
                min_value=0,
                value=DEFAULT_MAX_SUBS,
                step=1000,
                key="scrape_max_subs",
            )
        with c4:
            max_results = st.number_input(
                "Max leads",
                min_value=5,
                max_value=100,
                value=15,
                step=5,
                key="scrape_max_results",
            )

        paused = get_paused_search()
        if paused:
            q = paused.get("query") or "unknown"
            page = int(paused.get("page_number") or 1)
            token = (paused.get("next_page_token") or "").strip() or None
            st.markdown(
                '<div class="ige-banner info">Paused search detected. Resume continues from the saved page token.</div>',
                unsafe_allow_html=True,
            )
            if st.button(
                f"Resume Search: {q} (Page {page})",
                type="primary",
                use_container_width=True,
                key="resume_search_btn",
            ):
                region_codes = map_geo_to_region_codes(list(geo))
                if not region_codes:
                    st.warning("Select at least one geo market before resuming.")
                else:
                    _run_scrape(
                        query=q,
                        min_subs=int(paused.get("min_subs") or min_subs),
                        max_subs=int(paused.get("max_subs") or max_subs),
                        max_results=int(max_results),
                        region_codes=region_codes,
                        page_token=token,
                        start_page=page,
                    )
                    st.rerun()

        if st.session_state.get("quota_exceeded") and not paused:
            st.markdown(
                '<div class="ige-banner warn">⚠ Quota Exceeded — Resume Tomorrow</div>',
                unsafe_allow_html=True,
            )

        if st.button("Start New Search", type="primary", key="find_leads_btn"):
            resolved_query = (custom_query or "").strip() or (str(niche).strip() if niche else "")
            region_codes = map_geo_to_region_codes(list(geo))
            if not resolved_query:
                st.warning("Select a niche or enter a custom search keyword.")
            elif not region_codes:
                st.warning("Select at least one geo market.")
            elif min_subs > max_subs:
                st.warning("Min subscribers cannot exceed max subscribers.")
            else:
                _run_scrape(
                    query=resolved_query,
                    min_subs=int(min_subs),
                    max_subs=int(max_subs),
                    max_results=int(max_results),
                    region_codes=region_codes,
                    page_token=None,
                    start_page=1,
                )

    if st.session_state.get("last_scrape"):
        st.markdown(
            '<div class="ige-banner info">Showing last scrape results for this session.</div>',
            unsafe_allow_html=True,
        )
        st.dataframe(
            leads_dataframe(st.session_state["last_scrape"]),
            use_container_width=True,
            hide_index=True,
        )


def tab_database() -> None:
    st.subheader("Leads Database")
    leads = get_all_leads()
    df = leads_dataframe(leads)
    with st.container(border=True):
        st.caption(f"{len(leads)} lead(s) stored locally in SQLite.")
        st.dataframe(df, use_container_width=True, hide_index=True)
        if leads:
            buffer = io.BytesIO()
            export_df = df.drop(columns=[c for c in ["description"] if c in df.columns], errors="ignore")
            with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                export_df.to_excel(writer, index=False, sheet_name="leads")
            st.download_button(
                label="Export to Excel (.xlsx)",
                data=buffer.getvalue(),
                file_name="incubrix_leads.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        else:
            st.info("No leads yet. Run the Lead Scraper to populate the database.")


def tab_outreach(smtp: Dict[str, Any]) -> None:
    st.subheader("Outreach")
    leads = get_all_leads()  # Priority A first, then lead_score
    if not leads:
        st.info("No leads available. Scrape contactable channels first.")
        return

    configured = smtp_configured(smtp["host"], smtp["port"], smtp["email"], smtp["password"])
    if not configured:
        st.markdown(
            '<div class="ige-banner warn">SMTP is not configured. Open the Settings tab to add Host, Port, Email, and Password.</div>',
            unsafe_allow_html=True,
        )

    rows = []
    for lead in leads:
        rows.append(
            {
                "select": False,
                "channel_name": lead.get("channel_name") or "",
                "priority": (lead.get("priority") or "B").upper(),
                "lead_score": int(lead.get("lead_score") or 0),
                "email": lead.get("email") or "",
                "contact": primary_contact(lead),
                "country": (lead.get("country") or "").upper(),
                "pitch_draft": lead.get("pitch_draft") or "",
                "email_status": lead.get("email_status") or "pending",
                "channel_id": lead.get("channel_id") or "",
            }
        )
    editor_df = pd.DataFrame(rows)

    a_count = sum(1 for r in rows if r["priority"] == "A")
    top_l, top_r = st.columns([2, 1])
    with top_l:
        st.caption(
            f"{len(rows)} leads · {a_count} Priority A · edit pitches inline · check Select to send"
        )
    with top_r:
        send_clicked = st.button(
            "Send All Selected",
            use_container_width=True,
            key="send_all_selected",
            type="primary",
        )

    with st.container(border=True):
        edited = st.data_editor(
            editor_df,
            use_container_width=True,
            hide_index=True,
            num_rows="fixed",
            column_config={
                "select": st.column_config.CheckboxColumn("Select", default=False, width="small"),
                "channel_name": st.column_config.TextColumn("Lead", disabled=True, width="medium"),
                "priority": st.column_config.TextColumn("Priority", disabled=True, width="small"),
                "lead_score": st.column_config.NumberColumn("Score", disabled=True, width="small"),
                "email": st.column_config.TextColumn("Email", disabled=True, width="medium"),
                "contact": st.column_config.TextColumn("Contact", disabled=True, width="medium"),
                "country": st.column_config.TextColumn("Country", disabled=True, width="small"),
                "pitch_draft": st.column_config.TextColumn(
                    "Pitch draft",
                    width="large",
                    help="Edit the auto-generated pitch before sending",
                ),
                "email_status": st.column_config.TextColumn("Status", disabled=True, width="small"),
                "channel_id": None,
            },
            disabled=[
                "channel_name",
                "priority",
                "lead_score",
                "email",
                "contact",
                "country",
                "email_status",
                "channel_id",
            ],
            key="outreach_editor",
        )

    # Persist pitch edits from the table
    for _, row in edited.iterrows():
        cid = str(row.get("channel_id") or "")
        if not cid:
            continue
        new_pitch = str(row.get("pitch_draft") or "")
        original = next((r["pitch_draft"] for r in rows if r["channel_id"] == cid), "")
        if new_pitch != original:
            upsert_pitch(cid, new_pitch)

    if send_clicked:
        if not configured:
            st.warning("Configure SMTP in Settings before sending.")
        else:
            selected = edited[edited["select"] == True]  # noqa: E712
            to_send = [
                row
                for _, row in selected.iterrows()
                if str(row.get("email") or "").strip()
                and str(row.get("pitch_draft") or "").strip()
            ]
            if selected.empty:
                st.info("Select at least one lead using the checkbox column.")
            elif not to_send:
                st.warning("Selected leads need both an email and a pitch draft.")
            else:
                ok = fail = 0
                bar = st.progress(0.0)
                for i, row in enumerate(to_send):
                    try:
                        send_email_smtp(
                            smtp["host"],
                            smtp["port"],
                            smtp["email"],
                            smtp["password"],
                            str(row["email"]),
                            f"Partnership idea for {row['channel_name']} × IncuBrix",
                            str(row["pitch_draft"]),
                        )
                        update_email_status(str(row["channel_id"]), "sent")
                        ok += 1
                    except Exception:
                        update_email_status(str(row["channel_id"]), "failed")
                        fail += 1
                    bar.progress((i + 1) / len(to_send))
                st.success(f"Sent {ok} · Failed {fail}")
                st.rerun()


def tab_settings() -> Dict[str, Any]:
    st.subheader("Settings")
    settings = get_settings()
    paused = get_paused_search()
    state = get_search_state()
    groq_n = len(settings.groq_keys())

    if st.session_state.get("scrape_is_fallback"):
        yt_status = "Scraper fallback active (quota exceeded)"
    elif st.session_state.get("youtube_quota") == "exceeded" or paused:
        yt_status = "Quota exceeded — resume tomorrow"
    elif state and state.get("status") == "completed":
        yt_status = "Official API ready (last search completed)"
    else:
        yt_status = "Official API ready" if settings.youtube_api_key else "API key missing"

    with st.container(border=True):
        st.markdown("##### API Status")
        st.markdown(
            f"""
            <div class="ige-stat-row">
              <div class="ige-stat">
                <div class="label">YouTube Quota</div>
                <div class="value">{yt_status}</div>
              </div>
              <div class="ige-stat">
                <div class="label">Groq Keys Loaded</div>
                <div class="value">{groq_n} key{"s" if groq_n != 1 else ""}</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if paused:
            st.caption(
                f"Paused search: “{paused.get('query')}” · page {paused.get('page_number') or 1}"
            )

    with st.container(border=True):
        st.markdown("##### API Key Management")
        st.caption("Keys are written to the local `.env` file. Comma-separate multiple Groq keys.")
        yt_key = st.text_input(
            "YOUTUBE_API_KEY",
            value=settings.youtube_api_key,
            type="password",
            key="settings_youtube_key",
        )
        groq_keys = st.text_input(
            "GROQ_API_KEYS",
            value=settings.groq_api_keys.strip().strip('"'),
            type="password",
            key="settings_groq_keys",
            help="Multiple keys: key1,key2,key3",
        )
        if st.button("Save Keys", type="primary", key="save_api_keys_btn"):
            try:
                path = save_api_keys_to_env(yt_key, groq_keys)
                st.success(f"API keys saved to {path.name}. Settings reloaded.")
                st.rerun()
            except Exception as exc:  # noqa: BLE001
                st.error(f"Failed to save keys: {exc}")

    with st.container(border=True):
        st.markdown("##### Automation")
        auto_send = st.toggle(
            "Auto-Send Emails after Pitch Generation",
            value=bool(st.session_state.get("auto_send_emails", False)),
            key="settings_auto_send",
            help="When enabled, newly scraped leads with email + pitch are sent via SMTP immediately.",
        )
        st.session_state["auto_send_emails"] = bool(auto_send)
        if auto_send:
            st.caption("Auto-Send is ON — requires SMTP below.")
        else:
            st.caption("Auto-Send is OFF — use Outreach → Send All Selected.")

    with st.container(border=True):
        st.markdown("##### SMTP")
        st.caption("Required to send outreach emails. Stored in this browser session only.")
        c1, c2 = st.columns(2)
        with c1:
            smtp_host = st.text_input(
                "Host",
                value=st.session_state.get("smtp_host", ""),
                placeholder="smtp.gmail.com",
                key="settings_smtp_host",
            )
            smtp_email = st.text_input(
                "Email",
                value=st.session_state.get("smtp_email", ""),
                placeholder="you@company.com",
                key="settings_smtp_email",
            )
        with c2:
            smtp_port = st.number_input(
                "Port",
                min_value=1,
                max_value=65535,
                value=int(st.session_state.get("smtp_port", 587)),
                key="settings_smtp_port",
            )
            smtp_password = st.text_input(
                "Password / App password",
                value=st.session_state.get("smtp_password", ""),
                type="password",
                placeholder="App password",
                key="settings_smtp_password",
            )

        if not smtp_configured(smtp_host, int(smtp_port), smtp_email, smtp_password):
            st.markdown(
                '<div class="ige-banner warn">SMTP incomplete — sending stays disabled until Host, Port, Email, and Password are filled.</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="ige-banner info">SMTP ready. Outreach Send is enabled.</div>',
                unsafe_allow_html=True,
            )

    return {
        "host": smtp_host,
        "port": int(smtp_port),
        "email": smtp_email,
        "password": smtp_password,
    }


def main() -> None:
    inject_css()
    init_db()
    render_header()

    smtp = {
        "host": st.session_state.get("smtp_host", ""),
        "port": int(st.session_state.get("smtp_port", 587)),
        "email": st.session_state.get("smtp_email", ""),
        "password": st.session_state.get("smtp_password", ""),
    }

    tab1, tab2, tab3, tab4 = st.tabs(
        ["Lead Scraper", "Leads Database", "Outreach", "⚙️ Settings"]
    )
    with tab1:
        tab_scraper()
    with tab2:
        tab_database()
    with tab3:
        tab_outreach(smtp)
    with tab4:
        updated = tab_settings()
        st.session_state.update(
            {
                "smtp_host": updated["host"],
                "smtp_port": updated["port"],
                "smtp_email": updated["email"],
                "smtp_password": updated["password"],
            }
        )


if __name__ == "__main__":
    main()
