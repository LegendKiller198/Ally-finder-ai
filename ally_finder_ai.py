"""
AI-Powered Partner Outreach Automation (with Partner Discovery)
A Streamlit prototype for discovering, scoring, ranking, and reaching out to
potential business partners. Assumes "our company" is an EdTech / exam-prep
platform. Scoring is rule-based, not ML -- every point is traceable.

Two separate scores exist in this app:
- Discovery Score: how well a company found via web search matches what you
  searched for. Only used during discovery, before a company is added.
- Partner Score (Total Score): the existing fit-scoring model, calculated
  for every partner already in the pipeline, discovered or manual.
"""

import os
import re
import json
import pandas as pd
import streamlit as st

DATA_FILE = "partners.csv"

# --- Scoring config (this is "our company's" ideal partner profile) --------
HIGH_RELEVANCE_INDUSTRIES = ["EdTech", "EdTech / Data Science", "FinTech Education"]
MEDIUM_RELEVANCE_INDUSTRIES = ["Professional Services", "Media & Entertainment", "IT Services"]

AUDIENCE_KEYWORDS = [
    "student", "students", "professional", "professionals", "exam",
    "career", "aspirant", "aspirants", "coder", "coders", "learning",
    "mba", "finance", "data scientist", "analysts"
]
POSITIVE_INTENT_KEYWORDS = [
    "eager", "actively seeking", "open to", "interested",
    "looking to", "exploring", "referral"
]
SIZE_SCORES = {"Large": 20, "Medium": 14, "Small": 8}

MAX_INDUSTRY_SCORE = 30
MAX_AUDIENCE_SCORE = 25
MAX_SIZE_SCORE = 20
MAX_INTENT_SCORE = 25


# --- Partner Score functions (existing scoring model) ------------------------
def score_industry(industry: str) -> int:
    if industry in HIGH_RELEVANCE_INDUSTRIES:
        return MAX_INDUSTRY_SCORE
    elif industry in MEDIUM_RELEVANCE_INDUSTRIES:
        return int(MAX_INDUSTRY_SCORE / 2)
    return 5


def score_audience(target_audience: str) -> int:
    text = str(target_audience).lower()
    matches = sum(1 for k in AUDIENCE_KEYWORDS if k in text)
    return min(matches * 8, MAX_AUDIENCE_SCORE)


def score_size(company_size: str) -> int:
    return SIZE_SCORES.get(str(company_size).strip(), 5)


def score_intent(notes: str) -> int:
    text = str(notes).lower()
    matches = sum(1 for k in POSITIVE_INTENT_KEYWORDS if k in text)
    return min(matches * 12, MAX_INTENT_SCORE)


def classify_priority(score: int) -> str:
    if score >= 65:
        return "High"
    elif score >= 50:
        return "Medium"
    return "Low"


def score_partner(row: pd.Series) -> pd.Series:
    industry_pts = score_industry(row["Industry"])
    audience_pts = score_audience(row["Target Audience"])
    size_pts = score_size(row["Company Size"])
    intent_pts = score_intent(row["Partnership Notes"])
    total = industry_pts + audience_pts + size_pts + intent_pts

    return pd.Series({
        "Industry Score": industry_pts,
        "Audience Score": audience_pts,
        "Size Score": size_pts,
        "Intent Score": intent_pts,
        "Total Score": total,
        "Priority": classify_priority(total),
    })


# --- Outreach message generator --------------------------------------------
def generate_template_message(row: pd.Series) -> str:
    name = row["Company Name"]
    industry = row["Industry"]
    audience = row["Target Audience"]
    notes = row["Partnership Notes"]
    website = row.get("Website", "")

    website_line = f"\nI came across {name} at {website}. " if website else "\n"

    return f"""Subject: Exploring a Partnership Between Our Teams and {name}

Hi {name} team,{website_line}
I hope you're doing well. I've been following the work {name} is doing in the
{industry} space, particularly around {audience.lower() if audience else "your audience"},
and I think there could be a strong opportunity for our organizations to collaborate.

Given that {notes.lower()}, I believe a partnership focused on shared
audience growth, co-branded content, or referral opportunities could be
mutually beneficial for both teams.

Would you be open to a short 15-minute call next week to explore whether
this could be a good fit? Happy to work around your schedule.

Looking forward to hearing your thoughts.

Best regards,
[Your Name]
Business Development / Strategic Alliances""".strip()


def generate_ai_message(row: pd.Series) -> str:
    """Optional: polish the template with Claude if a key is set. Falls back silently."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    base_message = generate_template_message(row)
    if not api_key:
        return base_message
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=400,
            messages=[{
                "role": "user",
                "content": (
                    "Rewrite this outreach email to sound more natural, keeping the "
                    f"same length and facts unchanged:\n\n{base_message}"
                )
            }]
        )
        return response.content[0].text
    except Exception:
        return base_message


# --- Legacy AI-powered discovery (Anthropic, optional) ----------------------
def discover_partners_ai(niche: str):
    """
    Ask Claude (with web search) to suggest a few real companies in a given
    niche. Kept for backward compatibility -- the newer Tavily-based
    discovery section above is the main discovery workflow now.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None, "No API key configured. Add partners manually using the form below instead."
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{
                "role": "user",
                "content": (
                    f"Find 3 real companies in the '{niche}' space that could be a good "
                    "partnership fit for an EdTech / exam-prep platform. Respond with ONLY "
                    "a JSON array (no extra text), in this exact format:\n"
                    '[{"Company Name": "...", "Industry": "...", "Target Audience": "...", '
                    '"Company Size": "Small or Medium or Large", "Partnership Notes": "..."}]'
                )
            }]
        )
        text = "".join(b.text for b in response.content if getattr(b, "type", None) == "text")
        text = text.strip().replace("```json", "").replace("```", "").strip()
        suggestions = json.loads(text)
        return suggestions, None
    except Exception:
        return None, "AI search didn't return usable results. Try again or add manually below."


# ============================================================================
# NEW: AI PARTNER DISCOVERY (free web search via Tavily + rule-based parsing)
# ============================================================================
# No paid LLM is used here. Search queries are built with a template (not an
# LLM), and company details are extracted from search results using keyword
# matching -- the same style of logic as the scoring system above, so it's
# just as easy to explain. If a fact can't be determined this way, the field
# is left as "Unknown" rather than guessed.

BLOCKED_DOMAINS = [
    "wikipedia.org", "reddit.com", "linkedin.com", "indeed.com", "glassdoor.com",
    "facebook.com", "twitter.com", "x.com", "instagram.com", "youtube.com",
    "quora.com", "medium.com", "news.google.com", "timesofindia.com",
    "economictimes.com", "businessinsider.com", "crunchbase.com", "pinterest.com"
]

INDUSTRY_KEYWORDS = {
    "EdTech": ["education", "edtech", "e-learning", "exam prep", "tutoring", "online courses", "learning platform"],
    "EdTech / Data Science": ["data science course", "analytics training", "data science bootcamp"],
    "FinTech Education": ["fintech education", "finance learning", "mba prep", "cat preparation"],
    "IT Services": ["software company", "it services", "cloud services", "saas", "technology solutions"],
    "Professional Services": ["career services", "consulting", "recruitment", "placement", "coaching institute"],
    "Media & Entertainment": ["media company", "content platform", "entertainment", "creator economy"],
}


def generate_search_queries(description: str, market: str, audience: str, partnership_type: str, max_queries: int = 5) -> list:
    """
    Build several search phrases from the user's own words -- no LLM, just
    template combination. Nothing here is hard-coded to a specific topic;
    change the inputs and the queries change with them.
    """
    desc_words = [w.strip(".,") for w in description.split() if len(w) > 3][:5]
    desc_short = " ".join(desc_words[:3])
    first_audience = audience.split(",")[0].strip() if audience else ""
    first_type = partnership_type.split(",")[0].strip() if partnership_type else ""

    candidates = [
        f"{desc_short} companies {market}".strip(),
        f"{first_audience} platforms {market}".strip(),
        f"{desc_short} {first_type} {market}".strip(),
        f"{' '.join(desc_words[:4])} {market}".strip(),
        f"{first_audience} {desc_short} startups {market}".strip(),
    ]

    queries = []
    for q in candidates:
        q = " ".join(q.split())  # collapse extra whitespace
        if q and q not in queries:
            queries.append(q)
    return queries[:max_queries]


def normalize_domain(url: str) -> str:
    """example.com, www.example.com and https://example.com/x all -> example.com"""
    if not url:
        return ""
    domain = url.lower().strip()
    domain = re.sub(r"^https?://", "", domain)
    domain = re.sub(r"^www\.", "", domain)
    domain = domain.split("/")[0]
    return domain


def is_blocked_domain(domain: str) -> bool:
    """Reject known non-company sources (news, social media, job boards, etc.)."""
    return any(blocked in domain for blocked in BLOCKED_DOMAINS)


def search_web(queries: list, api_key: str, max_results_per_query: int = 5):
    """
    Run each query through Tavily and combine the results.
    Returns (results, error) -- error is None on success. Never raises.
    """
    try:
        from tavily import TavilyClient
    except ImportError:
        return [], "The 'tavily-python' package isn't installed."

    try:
        client = TavilyClient(api_key=api_key)
    except Exception:
        return [], "Could not start the Tavily client -- check the API key."

    all_results = []
    for q in queries:
        try:
            response = client.search(q, max_results=max_results_per_query)
            for r in response.get("results", []):
                r["discovery_query"] = q
                all_results.append(r)
        except Exception:
            continue  # one bad query shouldn't stop the rest

    if not all_results:
        return [], "No results came back. Try a broader description or check your API key."
    return all_results, None


def guess_industry(text: str) -> str:
    text = text.lower()
    for industry, keywords in INDUSTRY_KEYWORDS.items():
        if any(k in text for k in keywords):
            return industry
    return "Unknown"


def extract_company_candidates(raw_results: list) -> list:
    """
    Turn raw search results into structured company candidates using simple
    keyword rules -- no LLM. Rejects obvious non-company sources. Never
    invents a fact -- unknown fields stay "Unknown".
    """
    candidates = []
    for r in raw_results:
        url = r.get("url", "")
        domain = normalize_domain(url)
        if not domain or is_blocked_domain(domain):
            continue  # verification step

        title = (r.get("title") or "").strip()
        content = r.get("content") or ""
        combined_text = f"{title} {content}"

        name = re.split(r"[|\-–—:]", title)[0].strip() if title else domain
        if not name:
            name = domain

        industry = guess_industry(combined_text)

        matched_audience = sorted(set(k for k in AUDIENCE_KEYWORDS if k in content.lower()))
        audience = ", ".join(matched_audience) if matched_audience else "Unknown"

        matched_intent = sorted(set(k for k in POSITIVE_INTENT_KEYWORDS if k in content.lower()))
        partnership_signal = ", ".join(matched_intent) if matched_intent else "Unknown"

        candidates.append({
            "company_name": name,
            "website": domain,
            "industry": industry,
            "target_audience": audience,
            "description": content[:300],
            "company_size": "Unknown",
            "partnership_signals": partnership_signal,
            "source_url": url,
            "discovery_query": r.get("discovery_query", ""),
        })
    return candidates


def deduplicate_companies(candidates: list) -> list:
    """A company is a duplicate if it shares a normalized domain OR name."""
    seen_domains, seen_names, unique = set(), set(), []
    for c in candidates:
        name_key = c["company_name"].strip().lower()
        if c["website"] in seen_domains or name_key in seen_names:
            continue
        seen_domains.add(c["website"])
        seen_names.add(name_key)
        unique.append(c)
    return unique


def calculate_discovery_score(candidate: dict, market: str, audience_input: str, description: str) -> dict:
    """
    Score 0-100 for how well a candidate matches the SEARCH request.
    This is separate from Partner Score -- it measures search relevance,
    not partnership fit with our specific company.
    """
    industry_pts = 30 if candidate["industry"] != "Unknown" else 8

    audience_pts = 10
    if candidate["target_audience"] != "Unknown":
        cand_kw = set(candidate["target_audience"].lower().split(", "))
        input_kw = set(w.strip(",.") for w in audience_input.lower().split())
        overlap = cand_kw & input_kw
        audience_pts = min(len(overlap) * 10, 25) if overlap else 12

    market_text = (candidate["description"] + " " + candidate["source_url"]).lower()
    market_pts = 15 if market and market.lower() in market_text else 5

    signal_pts = 0
    if candidate["partnership_signals"] != "Unknown":
        signal_count = len(candidate["partnership_signals"].split(", "))
        signal_pts = min(signal_count * 10, 20)

    desc_words = set(w.lower().strip(",.") for w in description.split() if len(w) > 3)
    content_words = set(candidate["description"].lower().split())
    relevance_overlap = desc_words & content_words
    relevance_pts = min(len(relevance_overlap) * 2, 10)

    total = industry_pts + audience_pts + market_pts + signal_pts + relevance_pts
    return {
        "Industry Match": industry_pts, "Audience Match": audience_pts,
        "Market Match": market_pts, "Partnership Signal": signal_pts,
        "Search Relevance": relevance_pts, "Discovery Score": total,
    }


def classify_discovery_score(score: int) -> str:
    if score >= 90:
        return "Excellent"
    elif score >= 75:
        return "Strong"
    elif score >= 60:
        return "Potential"
    return "Weak"


def prepare_partner_record(candidate: dict) -> dict:
    """Convert a discovery candidate into the same schema partners.csv already uses."""
    notes = "Discovered through web search."
    if candidate["partnership_signals"] != "Unknown":
        notes += f" Signals found: {candidate['partnership_signals']}."
    else:
        notes += " No explicit partnership interest found yet -- verify before contacting."

    return {
        "Company Name": candidate["company_name"],
        "Industry": candidate["industry"],
        "Target Audience": candidate["target_audience"],
        "Company Size": candidate["company_size"],  # stays "Unknown" if not verifiable
        "Partnership Notes": notes,
        "Website": candidate["website"],
        "Discovery Score": candidate.get("Discovery Score", ""),
        "Discovery Source": "Web Search",
        "Source URL": candidate["source_url"],
    }


# --- Data loading / saving ---------------------------------------------------
def load_data() -> pd.DataFrame:
    df = pd.read_csv(DATA_FILE)
    defaults = {
        "Status": "Not Contacted", "Campaign": "General Outreach",
        "Website": "", "Discovery Score": "", "Discovery Source": "Manual", "Source URL": "",
    }
    for col, default in defaults.items():
        if col not in df.columns:
            df[col] = default
    return df


def save_data(df: pd.DataFrame) -> None:
    cols = ["Company Name", "Industry", "Target Audience", "Company Size", "Partnership Notes",
            "Status", "Campaign", "Website", "Discovery Score", "Discovery Source", "Source URL"]
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    df[cols].to_csv(DATA_FILE, index=False)


def add_partner_row(name, industry, audience, size, notes, campaign="General Outreach",
                     website="", discovery_score="", discovery_source="Manual", source_url=""):
    df = load_data()
    new_row = pd.DataFrame([{
        "Company Name": name, "Industry": industry, "Target Audience": audience,
        "Company Size": size, "Partnership Notes": notes, "Status": "Not Contacted",
        "Campaign": campaign, "Website": website, "Discovery Score": discovery_score,
        "Discovery Source": discovery_source, "Source URL": source_url,
    }])
    df = pd.concat([df, new_row], ignore_index=True)
    save_data(df)


# ============================================================================
# APP
# ============================================================================
st.set_page_config(page_title="AI-Powered Partner Outreach Automation", layout="wide")

st.title("🤝 AI-Powered Partner Outreach Automation")
st.caption("Discover, score, rank, and reach out to potential partners.")

# --- AI Partner Discovery (new) --------------------------------------------
st.subheader("🔎 AI Partner Discovery")
st.caption(
    "Search the web for real companies matching what you're looking for. "
    "Uses free web search (Tavily) -- nothing is added automatically, you review and approve."
)

with st.expander("Discovery settings", expanded=True):
    d_description = st.text_area(
        "Partnership requirement",
        placeholder="e.g. Find education and technology partners for an exam-preparation platform"
    )
    dc1, dc2 = st.columns(2)
    d_market = dc1.text_input("Target market", placeholder="e.g. India")
    d_audience = dc2.text_input("Target audience", placeholder="e.g. College students, MBA aspirants")
    d_type = st.text_input("Partnership type", placeholder="e.g. Referral partnerships, co-marketing")
    dc3, dc4 = st.columns(2)
    d_count = dc3.number_input("Number of companies to discover", min_value=1, max_value=20, value=10)
    d_min_score = dc4.slider("Minimum discovery score", 0, 100, 60)
    discover_clicked = st.button("🔍 Discover Partners")

if discover_clicked:
    tavily_key = os.environ.get("TAVILY_API_KEY")
    if not tavily_key:
        st.info(
            "Web discovery requires a Tavily API key (free tier available at tavily.com). "
            "Existing CSV-based partner management below still works normally."
        )
    elif not d_description.strip():
        st.warning("Describe what kind of partners you're looking for first.")
    else:
        with st.spinner("Searching the web..."):
            queries = generate_search_queries(d_description, d_market, d_audience, d_type)
            raw_results, error = search_web(queries, tavily_key, max_results_per_query=5)

        if error:
            st.warning(f"Discovery couldn't complete: {error}")
        else:
            candidates = extract_company_candidates(raw_results)
            candidates = deduplicate_companies(candidates)
            for c in candidates:
                c.update(calculate_discovery_score(c, d_market, d_audience, d_description))
                c["Match Level"] = classify_discovery_score(c["Discovery Score"])
            candidates = [c for c in candidates if c["Discovery Score"] >= d_min_score]
            candidates = sorted(candidates, key=lambda c: c["Discovery Score"], reverse=True)[:d_count]

            st.session_state["discovery_candidates"] = candidates
            st.session_state["discovery_stats"] = {"discovered": len(raw_results), "verified": len(candidates)}

            if not candidates:
                st.info("No companies met the minimum discovery score. Try lowering the threshold or broadening your description.")

if st.session_state.get("discovery_candidates"):
    st.markdown("#### Discovery Results — review before adding")
    st.caption("Nothing is added automatically. Select companies, then click Add Selected Partners.")

    selected_indices = []
    for i, c in enumerate(st.session_state["discovery_candidates"]):
        with st.container(border=True):
            cc1, cc2 = st.columns([5, 1])
            with cc1:
                st.markdown(f"**{c['company_name']}** — {c['industry']} · [{c['website']}](https://{c['website']})")
                preview = c["description"][:150] + ("..." if len(c["description"]) > 150 else "")
                st.caption(preview)
                st.caption(f"Discovery Score: {c['Discovery Score']}/100 ({c['Match Level']})")
            with cc2:
                if st.checkbox("Select", key=f"disc_sel_{i}"):
                    selected_indices.append(i)
            with st.expander("Score breakdown"):
                st.write({k: c[k] for k in
                          ["Industry Match", "Audience Match", "Market Match", "Partnership Signal", "Search Relevance"]})

    if st.button("➕ Add Selected Partners"):
        if not selected_indices:
            st.warning("Select at least one company first.")
        else:
            added = 0
            for i in selected_indices:
                record = prepare_partner_record(st.session_state["discovery_candidates"][i])
                add_partner_row(
                    record["Company Name"], record["Industry"], record["Target Audience"],
                    record["Company Size"], record["Partnership Notes"], campaign="Web Discovery",
                    website=record["Website"], discovery_score=record["Discovery Score"],
                    discovery_source=record["Discovery Source"], source_url=record["Source URL"],
                )
                added += 1
            stats = st.session_state.get("discovery_stats", {})
            stats["added"] = stats.get("added", 0) + added
            st.session_state["discovery_stats"] = stats
            st.success(f"Added {added} companies to the partner pipeline.")
            del st.session_state["discovery_candidates"]
            st.rerun()

st.divider()

# --- Load + score everything in the pipeline (discovered or manual) --------
df = load_data()
scores = df.apply(score_partner, axis=1)
df = pd.concat([df, scores], axis=1)

st.sidebar.header("Filters")
priority_filter = st.sidebar.multiselect("Priority", options=["High", "Medium", "Low"], default=["High", "Medium", "Low"])
industry_filter = st.sidebar.multiselect("Industry", options=sorted(df["Industry"].unique()), default=sorted(df["Industry"].unique()))
campaign_filter = st.sidebar.multiselect("Campaign", options=sorted(df["Campaign"].unique()), default=sorted(df["Campaign"].unique()))
filtered_df = df[
    df["Priority"].isin(priority_filter) & df["Industry"].isin(industry_filter) & df["Campaign"].isin(campaign_filter)
]

st.subheader("📊 Dashboard Overview")
col1, col2, col3 = st.columns(3)
col1.metric("Total Potential Partners", len(df))
col2.metric("High Priority Partners", int((df["Priority"] == "High").sum()))
col3.metric("Average Partner Score", round(df["Total Score"].mean(), 1))

if "discovery_stats" in st.session_state:
    stats = st.session_state["discovery_stats"]
    dcol1, dcol2, dcol3 = st.columns(3)
    dcol1.metric("Companies Discovered (last search)", stats.get("discovered", 0))
    dcol2.metric("Companies Verified", stats.get("verified", 0))
    dcol3.metric("Added to Pipeline", stats.get("added", 0))

priority_counts = df["Priority"].value_counts().reindex(["High", "Medium", "Low"]).fillna(0)
st.bar_chart(priority_counts)

st.subheader("📣 Campaign Progress")
campaign_progress = df.groupby(["Campaign", "Status"]).size().unstack(fill_value=0)
st.dataframe(campaign_progress, use_container_width=True)

st.subheader("📋 Partner Ranking")
display_cols = ["Company Name", "Industry", "Company Size", "Campaign", "Total Score", "Priority", "Status"]
ranked = filtered_df.sort_values("Total Score", ascending=False)
st.dataframe(ranked[display_cols], use_container_width=True, hide_index=True)

csv_data = ranked[display_cols].to_csv(index=False).encode("utf-8")
st.download_button("⬇️ Download Ranked List as CSV", data=csv_data, file_name="partner_ranking.csv", mime="text/csv")

st.subheader("📈 Average Score by Industry")
industry_avg = df.groupby("Industry")["Total Score"].mean().sort_values(ascending=False)
st.bar_chart(industry_avg)

with st.expander("ℹ️ How is the Partner Score calculated?"):
    st.markdown("""
    | Factor | Max Points | What it measures |
    |---|---|---|
    | Industry Relevance | 30 | How closely the partner's industry matches ours |
    | Target Audience Overlap | 25 | Keyword overlap between their audience and ours |
    | Company Size | 20 | Larger companies score higher (more reach/resources) |
    | Partnership Intent | 25 | Positive language in their notes (e.g. "actively seeking") |

    **Priority bands:** 65+ = High · 50-64 = Medium · Below 50 = Low

    This is different from **Discovery Score**, shown only during search results above --
    that measures how well a company matched your *search*, not its fit in this formula.
    """)
    st.dataframe(
        filtered_df[["Company Name", "Industry Score", "Audience Score", "Size Score", "Intent Score", "Total Score"]],
        use_container_width=True, hide_index=True
    )

# --- Add / Discover Partners (manual + legacy AI tab) -----------------------
st.subheader("➕ Add Partners Manually")
tab_manual, tab_ai_legacy = st.tabs(["✍️ Add Manually", "🔎 Discover with AI (legacy)"])

with tab_manual:
    with st.form("add_partner_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        name = c1.text_input("Company Name")
        industry = c2.text_input("Industry")
        audience = st.text_input("Target Audience")
        size = st.selectbox("Company Size", ["Small", "Medium", "Large"])
        notes = st.text_area("Partnership Notes")
        campaign = st.text_input("Campaign", value="General Outreach")
        submitted = st.form_submit_button("Add Partner")
        if submitted:
            if name.strip() and industry.strip():
                add_partner_row(name, industry, audience, size, notes, campaign)
                st.success(f"Added {name}")
                st.rerun()
            else:
                st.warning("Company Name and Industry are required.")

with tab_ai_legacy:
    st.caption("Older single-company AI search. The section above is the main discovery workflow now.")
    niche = st.text_input("Industry or niche to search", placeholder="e.g. online coding bootcamps")
    if st.button("Find Potential Partners (legacy)"):
        if not niche.strip():
            st.warning("Enter a niche to search first.")
        else:
            with st.spinner("Searching..."):
                suggestions, error = discover_partners_ai(niche)
            if error:
                st.info(error)
            else:
                st.session_state["ai_suggestions"] = suggestions

    if "ai_suggestions" in st.session_state:
        for i, s in enumerate(st.session_state["ai_suggestions"]):
            with st.container(border=True):
                st.markdown(f"**{s.get('Company Name', 'Unknown')}** — {s.get('Industry', '')}")
                st.caption(s.get("Target Audience", ""))
                if st.button("Add to Partner List", key=f"add_ai_{i}"):
                    add_partner_row(
                        s.get("Company Name", "Unknown"), s.get("Industry", ""),
                        s.get("Target Audience", ""), s.get("Company Size", "Medium"),
                        s.get("Partnership Notes", "")
                    )
                    st.success(f"Added {s.get('Company Name')}")
                    st.rerun()

# --- Outreach generator ---------------------------------------------------
st.subheader("✉️ Outreach Message Generator")
selected_company = st.selectbox("Select a partner", options=df["Company Name"].tolist())
selected_row = df[df["Company Name"] == selected_company].iloc[0]

use_ai = st.checkbox("Enhance message with AI", value=False)

if st.button("Generate Outreach Message"):
    message = generate_ai_message(selected_row) if use_ai else generate_template_message(selected_row)
    st.text_area("Generated Message", value=message, height=280)

# --- Follow-up tracker -----------------------------------------------------
st.subheader("📌 Follow-up Tracker")
status_options = ["Not Contacted", "Contacted", "Replied", "Meeting", "Converted"]
new_status = st.selectbox(
    f"Update status for {selected_company}",
    options=status_options,
    index=status_options.index(selected_row["Status"]) if selected_row["Status"] in status_options else 0
)

if st.button("Save Status"):
    df.loc[df["Company Name"] == selected_company, "Status"] = new_status
    save_data(df)
    st.success(f"Status for {selected_company} updated to '{new_status}'.")
    st.rerun()

st.divider()
st.caption("Prototype only. Does not send real emails or contact real companies.")
