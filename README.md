# AI-Powered Partner Outreach Automation (with Partner Discovery)

A working prototype that helps a Business Development / Strategic Alliances
team **find**, score, rank, and reach out to potential partner companies.

**Status:** Ongoing student portfolio project (prototype, not production).

---

## 1. Project Overview

Earlier versions of this project worked from a fixed list of companies typed
into a spreadsheet. This version adds a real **AI Partner Discovery** feature:
describe the kind of partner you're looking for, and the app searches the
web, extracts candidate companies, scores how well they match your search,
and lets you review and approve them before anything is added.

## 2. Problem Statement

A BD/Partnerships team usually starts with **no list at all** — they have to
find companies worth approaching in the first place, then figure out which
ones are worth prioritizing, then write outreach for them. Most tools
(including earlier versions of this project) only solve the second half.

## 3. Solution — the full pipeline

```
Search Request → Web Search → Candidate Extraction → Verification
→ Deduplication → Discovery Score → Human Review → Approved Companies
→ Partner Score (existing model) → Priority → Outreach → Follow-up Tracking
```

Nothing is added to the partner list automatically — every discovered
company is reviewed and approved by a person first.

## 4. Features

- 🔎 **AI Partner Discovery** — describe your target partner (market, audience,
  partnership type) and search the real web for matching companies, using
  Tavily's free search API
- 🧮 **Two separate, explainable scores:**
  - **Discovery Score** (0-100) — how well a company matches your *search*
  - **Partner Score** (0-100) — the existing fit-scoring model, calculated
    for every partner in the pipeline regardless of how they were added
- ✅ **Verification & deduplication** — rejects obvious non-company sources
  (Wikipedia, news, social media, job boards) and merges duplicate results
- 👤 **Human-in-the-loop** — nothing is added automatically; you select and
  approve candidates before they enter the pipeline
- 📊 Dashboard with key metrics, priority chart, and discovery stats
- 📣 Campaign tracking — group partners into named outreach campaigns
- 📋 Filterable, sortable ranking table + CSV export
- ✉️ Personalized outreach message generator (optional AI polish)
- 📌 Follow-up status tracker (Not Contacted → Contacted → Replied → Meeting → Converted)
- ✍️ Manual "Add Partner" form always available, no API key required

## 5. Architecture

```
User describes what they want
        ↓
generate_search_queries()   -- template-based, no LLM
        ↓
search_web()                -- Tavily API (free tier)
        ↓
extract_company_candidates()-- keyword-based extraction, no LLM
        ↓
verify (blocked-domain filter) + deduplicate_companies()
        ↓
calculate_discovery_score() -- 5-factor score out of 100
        ↓
Human reviews & selects candidates
        ↓
prepare_partner_record()    -- converts to the existing partners.csv schema
        ↓
score_partner()             -- the ORIGINAL scoring model (unchanged)
        ↓
Partner Score + Priority → Outreach Generator → Follow-up Tracker
```

## 6. How Partner Discovery works (no paid LLM)

- **Search queries** are built from your own words using a template — not
  an LLM. Change your inputs and the queries change with them.
- **Company extraction** uses keyword matching against the same industry
  and audience keyword lists the scoring system already uses. If a fact
  (like company size) can't be determined this way, it's marked
  **"Unknown"** rather than guessed.
- **Verification** rejects results from known non-company domains
  (Wikipedia, Reddit, LinkedIn, news sites, job boards, etc.)
- **Deduplication** merges results that share the same website domain or
  the same company name, even if they came from different search queries.

## 7. Discovery Score vs Partner Score

| | Discovery Score | Partner Score |
|---|---|---|
| Measures | Match to your *search request* | Fit with our company's partner profile |
| When calculated | Only during discovery, before approval | For every partner, always |
| Factors | Industry Match (30), Audience Match (25), Market Match (15), Partnership Signal (20), Search Relevance (10) | Industry Relevance (30), Audience Overlap (25), Company Size (20), Partnership Intent (25) |
| Bands | 90+ Excellent · 75-89 Strong · 60-74 Potential · <60 Weak | 65+ High · 50-64 Medium · <50 Low |

A company can score high on Discovery (great search match) but lower on
Partner Score (weaker fit with our specific profile) — that's expected and
is exactly why both scores are shown separately.

## 8. Tech Stack

- **Python + Pandas** — data handling and scoring
- **Streamlit** — the web dashboard
- **Tavily API** (free tier) — real web search for discovery
- **CSV** — data storage, auto-upgraded if older files are missing new columns
- **Anthropic API (optional)** — only for outreach-message polish and the
  legacy single-company AI search tab; the app works fully without it

## 9. Installation

```bash
cd AI-Partner-Outreach-Automation-v4
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## 10. Environment Variables

Copy `.env.example` to `.env` and fill in your own keys, or set them
directly in your environment / Streamlit Cloud secrets:

- `TAVILY_API_KEY` — required for AI Partner Discovery. Free tier at tavily.com.
  Without it, discovery shows a clear message and the rest of the app works normally.
- `ANTHROPIC_API_KEY` — optional. Only used for outreach message polishing
  and the legacy AI search tab.

## 11. How to Run It

```bash
streamlit run app.py
```

## 12. How to Test Partner Discovery

1. Set `TAVILY_API_KEY` in your environment
2. Fill in the discovery form, e.g.:
   - Partnership requirement: "Find education and technology partners for an exam-preparation platform"
   - Target market: "India"
   - Target audience: "College students, MBA aspirants"
   - Partnership type: "Referral partnerships, co-marketing"
3. Click "🔍 Discover Partners"
4. Review the candidates, check the ones you want, click "➕ Add Selected Partners"
5. They now appear in the Partner Ranking table with a real Partner Score,
   and are available in the Outreach Message Generator

Without a key, this section shows a message and the rest of the app
(manual add, scoring, outreach, follow-up) works exactly as before.

## 13. Limitations

- Company extraction uses keyword matching, not deep NLP — a well-matched
  company could still be missed if its website doesn't use expected keywords.
- Search quality depends entirely on what Tavily returns; results aren't
  independently fact-checked beyond the domain-blocklist filter.
- Company Size is not reliably determinable from search results and stays
  "Unknown" for discovered companies — a human would confirm this.
- No real email is ever sent and no company is ever contacted automatically.
- Discovery stats (companies discovered/verified/added) reset each session —
  they aren't stored long-term, this is a demo-level metric only.

## 14. Future Improvements

- Use an LLM for extraction instead of keyword matching, for higher accuracy
- Persist discovery history across sessions (currently session-only)
- Connect to a real CRM instead of a CSV file
- Let users adjust scoring weights from the UI

---

*This project is a work-in-progress prototype built for learning and
portfolio purposes. It does not autonomously contact real companies, and
all company data returned by discovery should be verified by a human
before outreach.*
