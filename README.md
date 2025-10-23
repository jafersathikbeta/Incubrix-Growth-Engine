# Incubrix Growth Engine

A comprehensive B2B lead generation and outreach desktop application built with Streamlit. Designed as a growth engine, this tool automates the discovery of high-value YouTube creators, extracts their contact information, scores their commercial viability, and generates personalized AI cold emails. 

*Note: This system was successfully used to generate and process over 5,000+ leads during its initial deployment, meeting exceptional tier-level criteria in a technical hiring assessment.*

## Core Features

- **YouTube Lead Scraper:** Search for channels by niche, geo-market, and subscriber count. Uses the official YouTube Data API with a seamless `ytscrape` (InnerTube) fallback when API quotas are exceeded.
- **Smart Contact Extraction:** Automatically parses channel descriptions and links to extract Emails, LinkedIn, Instagram, and Twitter profiles.
- **Lead Scoring & Prioritization:** Calculates a proprietary `lead_score` based on views, subscribers, country, and monetization intent (e.g., checking for "buy," "course," or "sponsor" keywords). Flags the top 5% of any batch as "Priority A".
- **AI Pitch Generation:** Integrates with Groq API (using Llama-3 and GPT-OSS models) to write highly personalized 3-sentence cold emails. Includes a Mad-Libs style fallback template if the LLM quota is exhausted.
- **Automated Outreach:** Built-in SMTP integration to send emails directly from the dashboard. Includes a toggle for "Auto-Send" and a manual bulk-send table.
- **Local CRM & Database:** Stores leads and search states (allowing you to "pause" and "resume" quota-limited searches) in a local SQLite database.
- **Data Export:** Export your entire pipeline or specific searches to Excel (`.xlsx`).

## Architecture

- **Frontend/UI:** Streamlit (Custom CSS for a premium SaaS aesthetic).
- **Database:** SQLite (managed via custom `src/database.py`).
- **AI Pipeline:** Groq Python SDK (with multi-key failover).
- **Scraping:** Google API Python Client & `ytscrape`.

## Setup & Installation

1. Clone the repository and install dependencies:
   ```bash
   git clone https://github.com/jafersathikbeta/Incubrix-Growth-Engine.git
   cd Incubrix-Growth-Engine
   pip install -r requirements.txt
   ```

2. Configure your Environment Variables:
   Rename `.env.example` to `.env` and add your API keys:
   ```env
   YOUTUBE_API_KEY=your_youtube_key
   GROQ_API_KEYS=your_groq_key_1,your_groq_key_2
   ```
   *(You can also set these directly inside the app's Settings tab).*

3. Run the application:
   ```bash
   streamlit run app.py
   ```
   *(Or run the desktop wrapper: `python run.py`)*

## Usage Guide

1. **Lead Scraper Tab:** Select a niche, choose your geo-markets, set your min/max subscriber limits, and click "Start New Search".
2. **Leads Database Tab:** View all scraped leads, check their Priority status, and export to Excel.
3. **Outreach Tab:** Review the AI-generated pitches, edit them inline if necessary, check the box next to the leads you want to contact, and click "Send All Selected".
4. **Settings Tab:** Manage your Groq/YouTube API keys and SMTP server configuration. 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
