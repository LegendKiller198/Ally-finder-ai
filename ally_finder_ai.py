import os
import re
import json
import html
import pandas as pd
import streamlit as st

DATA_FILE = "partners.csv"

# ----------------------------- Scoring ------------------------------------
HIGH_RELEVANCE_INDUSTRIES = ["EdTech", "EdTech / Data Science", "FinTech Education"]
MEDIUM_RELEVANCE_INDUSTRIES = ["Professional Services", "Media & Entertainment", "IT Services"]
AUDIENCE_KEYWORDS = [
    "student", "students", "professional", "professionals", "exam", "career",
    "aspirant", "aspirants", "coder", "coders", "learning", "mba", "finance",
    "data scientist", "analysts"
]
POSITIVE_INTENT_KEYWORDS = [
    "eager", "actively seeking", "open to", "interested", "looking to",
    "exploring", "referral"
]
SIZE_SCORES = {"Large": 20, "Medium": 14, "Small": 8}
MAX_INDUSTRY_SCORE = 30
MAX_AUDIENCE_SCORE = 25
MAX_SIZE_SCORE = 20
MAX_INTENT_SCORE = 25


def score_industry(industry: str) -> int:
    if industry in HIGH_RELEVANCE_INDUSTRIES:
        return MAX_INDUSTRY_SCORE
    if industry in MEDIUM_RELEVANCE_INDUSTRIES:
        return 15
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
    if score >= 50:
        return "Medium"
    return "Low"


def score_partner(row: pd.Series) -> pd.Series:
    industry_pts = score_industry(row.get("Industry", ""))
    audience_pts = score_audience(row.get("Target Audience", ""))
    size_pts = score_size(row.get("Company Size", ""))
    intent_pts = score_intent(row.get("Partnership Notes", ""))
    total = industry_pts + audience_pts + size_pts + intent_pts
    return pd.Series({
        "Industry Score": industry_pts,
        "Audience Score": audience_pts,
        "Size Score": size_pts,
        "Intent Score": intent_pts,
        "Total Score": total,
        "Priority": classify_priority(total),
    })


# ----------------------------- Outreach -----------------------------------
def build_rationale(notes: str) -> str:
    text = str(notes).lower()
    matched = [k for k in POSITIVE_INTENT_KEYWORDS if k in text]
    if matched:
        return f"Given your team's interest in {matched[0]} partnerships, "
    return "Given the overlap between our audiences, "


def generate_template_message(row: pd.Series) -> str:
    name = row.get("Company Name", "the team")
    industry = row.get("Industry", "your industry")
    audience = row.get("Target Audience", "your audience")
    notes = row.get("Partnership Notes", "")
    website = row.get("Website", "")
    website_line = f"\nI came across {name} at {website}. " if website else ""
    rationale = build_rationale(notes)
    return f"""Subject: Exploring a Partnership Between Our Teams and {name}

Hi {name} team,{website_line}
I hope you're doing well. I've been following the work {name} is doing in the {industry} space, particularly around {str(audience).lower() if audience and audience != 'Unknown' else 'your audience'}, and I think there could be a strong opportunity for our organizations to collaborate.

{rationale}I believe a partnership focused on shared audience growth, co-branded content, or referral opportunities could be mutually beneficial for both teams.

Would you be open to a short 15-minute call next week to explore whether this could be a good fit? Happy to work around your schedule.

Looking forward to hearing your thoughts.

Best regards,
[Your Name]
Business Development / Strategic Alliances""".strip()


def generate_ai_message(row: pd.Series) -> str:
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
                    "Rewrite this partnership outreach email to sound concise, natural, and professional. "
                    "Keep all facts unchanged and do not invent claims.\n\n" + base_message
                )
            }]
        )
        return response.content[0].text
    except Exception:
        return base_message


# ----------------------------- Discovery ----------------------------------
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
        q = " ".join(q.split())
        if q and q not in queries:
            queries.append(q)
    return queries[:max_queries]


def normalize_domain(url: str) -> str:
    if not url:
        return ""
    domain = url.lower().strip()
    domain = re.sub(r"^https?://", "", domain)
    domain = re.sub(r"^www\.", "", domain)
    return domain.split("/")[0]


def is_blocked_domain(domain: str) -> bool:
    return any(blocked in domain for blocked in BLOCKED_DOMAINS)


def search_web(queries: list, api_key: str, max_results_per_query: int = 5):
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
            continue
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
    candidates = []
    for r in raw_results:
        url = r.get("url", "")
        domain = normalize_domain(url)
        if not domain or is_blocked_domain(domain):
            continue
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
        signal_pts = min(len(candidate["partnership_signals"].split(", ")) * 10, 20)
    desc_words = set(w.lower().strip(",.") for w in description.split() if len(w) > 3)
    content_words = set(candidate["description"].lower().split())
    relevance_pts = min(len(desc_words & content_words) * 2, 10)
    total = industry_pts + audience_pts + market_pts + signal_pts + relevance_pts
    return {
        "Industry Match": industry_pts,
        "Audience Match": audience_pts,
        "Market Match": market_pts,
        "Partnership Signal": signal_pts,
        "Search Relevance": relevance_pts,
        "Discovery Score": total,
    }


def classify_discovery_score(score: int) -> str:
    if score >= 90:
        return "Excellent"
    if score >= 75:
        return "Strong"
    if score >= 60:
        return "Potential"
    return "Weak"


def prepare_partner_record(candidate: dict) -> dict:
    notes = "Discovered through web search."
    if candidate["partnership_signals"] != "Unknown":
        notes += f" Signals found: {candidate['partnership_signals']}."
    else:
        notes += " No explicit partnership interest found yet -- verify before contacting."
    return {
        "Company Name": candidate["company_name"],
        "Industry": candidate["industry"],
        "Target Audience": candidate["target_audience"],
        "Company Size": candidate["company_size"],
        "Partnership Notes": notes,
        "Website": candidate["website"],
        "Discovery Score": candidate.get("Discovery Score", ""),
        "Discovery Source": "Web Search",
        "Source URL": candidate["source_url"],
    }


# ----------------------------- Data ---------------------------------------
def load_data() -> pd.DataFrame:
    try:
        df = pd.read_csv(DATA_FILE)
    except FileNotFoundError:
        df = pd.DataFrame(columns=[
            "Company Name", "Industry", "Target Audience", "Company Size",
            "Partnership Notes", "Status", "Campaign", "Website",
            "Discovery Score", "Discovery Source", "Source URL"
        ])
    defaults = {
        "Status": "Not Contacted", "Campaign": "General Outreach", "Website": "",
        "Discovery Score": "", "Discovery Source": "Manual", "Source URL": "",
        "Target Audience": "", "Company Size": "Medium", "Partnership Notes": ""
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
    save_data(pd.concat([df, new_row], ignore_index=True))


# ----------------------------- UI -----------------------------------------
st.set_page_config(page_title="Partner Outreach AI", page_icon="🤝", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
:root { --primary:#6d28d9; --primary2:#4f46e5; --ink:#111827; --muted:#64748b; --bg:#f7f7fc; --card:#ffffff; }
.stApp { background: var(--bg); color: var(--ink); }
[data-testid="stSidebar"] { background: linear-gradient(180deg,#111936 0%,#15104a 100%); border-right: 0; }
[data-testid="stSidebar"] * { color: #eef2ff !important; }
[data-testid="stSidebar"] .stButton button { background: transparent; border: 1px solid transparent; color:#eef2ff !important; text-align:left; }
[data-testid="stSidebar"] .stButton button:hover { background: rgba(124,58,237,.22); border-color: rgba(196,181,253,.25); }
.block-container { max-width: 1400px; padding-top: 2rem; padding-bottom: 3rem; }
.hero { padding: 2.2rem 2.4rem; border-radius: 24px; background: linear-gradient(120deg,#ffffff 0%,#f4f1ff 55%,#e9e7ff 100%); border:1px solid #e8e5f7; box-shadow:0 12px 35px rgba(49,46,129,.08); margin-bottom:1.4rem; }
.eyebrow { color:var(--primary); font-weight:700; font-size:.82rem; letter-spacing:.08em; text-transform:uppercase; }
.hero h1 { font-size:2.55rem; line-height:1.1; margin:.45rem 0 .7rem; color:#111936; }
.hero p { color:#536174; font-size:1.03rem; max-width:720px; margin-bottom:0; }
.card { background:var(--card); border:1px solid #e8eaf2; border-radius:18px; padding:1.15rem 1.25rem; box-shadow:0 7px 25px rgba(15,23,42,.045); }
.metric-label { color:#64748b; font-size:.84rem; }
.metric-value { font-size:1.9rem; font-weight:800; color:#111936; margin-top:.2rem; }
.metric-delta { color:#059669; font-size:.76rem; font-weight:700; }
.section-title { font-size:1.25rem; font-weight:800; color:#111936; margin:1.35rem 0 .7rem; }
.partner-card { background:#fff; border:1px solid #e7e9f2; border-radius:18px; padding:1.05rem 1.15rem; margin-bottom:.75rem; box-shadow:0 5px 18px rgba(15,23,42,.035); }
.score { font-size:1.25rem; font-weight:800; color:#4f46e5; }
.pill { display:inline-block; padding:.22rem .58rem; border-radius:999px; font-size:.72rem; font-weight:700; background:#ede9fe; color:#5b21b6; }
.high { background:#dcfce7; color:#047857; }
.medium { background:#fef3c7; color:#a16207; }
.low { background:#f1f5f9; color:#475569; }
.insight { background:linear-gradient(135deg,#f4f0ff,#faf8ff); border:1px solid #e7ddff; border-radius:18px; padding:1.25rem; }
.insight h3 { margin-top:0; color:#4c1d95; }
.small { color:#64748b; font-size:.82rem; }
.pipeline { min-height:180px; background:#fff; border:1px solid #e7e9f2; border-radius:16px; padding:.9rem; }
.pipeline-head { font-weight:800; font-size:.85rem; margin-bottom:.7rem; }
.pipeline-item { padding:.6rem .7rem; border:1px solid #eef0f5; border-radius:10px; margin-bottom:.45rem; font-size:.8rem; background:#fbfbfd; }
div.stButton > button[kind="primary"] { background:linear-gradient(90deg,#6d28d9,#4f46e5); border:0; color:white; font-weight:700; border-radius:10px; min-height:2.65rem; }
div.stButton > button { border-radius:10px; font-weight:600; }
[data-testid="stMetric"] { background:white; border:1px solid #e8eaf2; padding:1rem; border-radius:16px; box-shadow:0 5px 18px rgba(15,23,42,.035); }
.stTextInput input,
.stTextArea textarea,
div[data-testid="stTextInput"] input,
div[data-testid="stTextArea"] textarea,
div[data-baseweb="input"] input,
div[data-baseweb="textarea"] textarea {
    background-color: #ffffff !important;
    color: #111827 !important;
    -webkit-text-fill-color: #111827 !important;
    caret-color: #111827 !important;
    border: 1px solid #cbd5e1 !important;
    border-radius: 10px !important;
}
div[data-testid="stTextInput"] input::placeholder,
div[data-testid="stTextArea"] textarea::placeholder,
div[data-baseweb="input"] input::placeholder,
div[data-baseweb="textarea"] textarea::placeholder {
    color: #64748b !important;
    -webkit-text-fill-color: #64748b !important;
    opacity: 1 !important;
}
div[data-testid="stTextInput"] label,
div[data-testid="stTextArea"] label {
    color: #334155 !important;
    opacity: 1 !important;
}
.stSelectbox div[data-baseweb="select"] > div {
    background-color: #ffffff !important;
    color: #111827 !important;
    border-radius: 10px !important;
}
hr { border-color:#e9eaf1; }
</style>
""", unsafe_allow_html=True)

if "page" not in st.session_state:
    st.session_state.page = "Dashboard"
if "discovery_candidates" not in st.session_state:
    st.session_state.discovery_candidates = []

# Sidebar
with st.sidebar:
    st.markdown("## 🤝 Partner Outreach **AI**")
    st.caption("Strategic Alliances Workspace")
    st.divider()
    for page_name, icon in [
        ("Dashboard", "⌂"), ("Find Partners", "⌕"), ("All Partners", "◉"),
        ("Prioritized List", "★"), ("Generate Outreach", "✈"),
        ("Pipeline", "▥"), ("Follow-ups", "◷")
    ]:
        if st.button(f"{icon}  {page_name}", key=f"nav_{page_name}", use_container_width=True):
            st.session_state.page = page_name
            st.rerun()
    st.divider()
    st.markdown("### ✨ AI-powered")
    st.caption("Smarter discovery. Better prioritization. More relevant outreach.")
    st.caption("Built for practical Strategic Alliances & Business Development workflows.")

# Load + score
df = load_data()
if len(df):
    scores = df.apply(score_partner, axis=1)
    df_scored = pd.concat([df.reset_index(drop=True), scores.reset_index(drop=True)], axis=1)
else:
    df_scored = df.copy()

# ----------------------------- Dashboard ----------------------------------
if st.session_state.page == "Dashboard":
    st.markdown('<div class="hero"><div class="eyebrow">Partner Intelligence & Outreach</div><h1>Find the right partners.<br>Start the right conversations.</h1><p>Discover relevant companies, prioritize the strongest opportunities, and create personalized partnership outreach — all in one workflow.</p></div>', unsafe_allow_html=True)
    q = st.text_input("", placeholder="e.g. EdTech companies targeting college students", label_visibility="collapsed")
    if st.button("🔍 Find Partners", type="primary"):
        st.session_state.page = "Find Partners"
        st.session_state.discovery_prefill = q
        st.rerun()

    total = len(df_scored)
    high = int((df_scored["Priority"] == "High").sum()) if total else 0
    contacted = int((df_scored["Status"] != "Not Contacted").sum()) if total else 0
    meetings = int((df_scored["Status"] == "Meeting").sum()) if total else 0
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Total Partners", total)
    c2.metric("High Priority", high)
    c3.metric("Outreach Started", contacted)
    c4.metric("Meetings", meetings)

    st.markdown('<div class="section-title">Top Priority Partners</div>', unsafe_allow_html=True)
    left, right = st.columns([1.7, 1])
    with left:
        if total:
            top = df_scored.sort_values("Total Score", ascending=False).head(5)
            for rank, (_, r) in enumerate(top.iterrows(), 1):
                priority_class = str(r["Priority"]).lower()
                st.markdown(f'''<div class="partner-card"><div style="display:flex;justify-content:space-between;align-items:center"><div><b>{rank}. {html.escape(str(r['Company Name']))}</b><div class="small">{html.escape(str(r['Industry']))} · {html.escape(str(r['Target Audience']))}</div></div><div style="text-align:right"><span class="pill {priority_class}">{r['Priority']} priority</span><div class="score">{int(r['Total Score'])}/100</div></div></div><div class="small" style="margin-top:.55rem">Strongest signals: Industry {int(r['Industry Score'])}/30 · Audience {int(r['Audience Score'])}/25 · Intent {int(r['Intent Score'])}/25</div></div>''', unsafe_allow_html=True)
        else:
            st.info("Your partner pipeline is empty. Start by finding potential partners.")
    with right:
        st.markdown('<div class="insight"><h3>✦ AI Insight</h3><p><b>Start with fit, not volume.</b></p><p class="small">The strongest prospects are those with clear audience overlap, relevant industry alignment, and partnership signals.</p></div>', unsafe_allow_html=True)
        st.markdown('<div class="section-title">Pipeline Snapshot</div>', unsafe_allow_html=True)
        statuses = ["Not Contacted", "Contacted", "Replied", "Meeting", "Converted"]
        for s in statuses:
            n = int((df_scored["Status"] == s).sum()) if total else 0
            st.markdown(f'<div class="card" style="padding:.7rem 1rem;margin-bottom:.45rem;display:flex;justify-content:space-between"><span>{s}</span><b>{n}</b></div>', unsafe_allow_html=True)

    st.markdown('<div class="section-title">Quick Actions</div>', unsafe_allow_html=True)
    a,b,c = st.columns(3)
    with a:
        if st.button("🔎 Discover partners", use_container_width=True): st.session_state.page="Find Partners"; st.rerun()
    with b:
        if st.button("✉️ Generate outreach", use_container_width=True): st.session_state.page="Generate Outreach"; st.rerun()
    with c:
        if st.button("📌 Open pipeline", use_container_width=True): st.session_state.page="Pipeline"; st.rerun()

# ----------------------------- Discovery ----------------------------------
elif st.session_state.page == "Find Partners":
    st.markdown('<div class="hero"><div class="eyebrow">Step 1 · Discover</div><h1>Find potential partners</h1><p>Describe the partnership opportunity. The tool searches the web, removes obvious non-company sources, and ranks results by search relevance.</p></div>', unsafe_allow_html=True)
    default_desc = st.session_state.get("discovery_prefill", "")
    d_description = st.text_area("Partnership requirement", value=default_desc, placeholder="Find education and technology partners for an exam-preparation platform")
    c1,c2,c3 = st.columns(3)
    d_market = c1.text_input("Target market", placeholder="India")
    d_audience = c2.text_input("Target audience", placeholder="College students, MBA aspirants")
    d_type = c3.text_input("Partnership type", placeholder="Referral, co-marketing")
    c4,c5 = st.columns(2)
    d_count = c4.slider("Companies to discover", 3, 20, 8)
    d_min_score = c5.slider("Minimum discovery score", 0, 100, 60)
    if st.button("🔍 Discover Partners", type="primary"):
        tavily_key = os.environ.get("TAVILY_API_KEY")
        if not tavily_key:
            st.warning("Web discovery needs TAVILY_API_KEY. Add the key to your environment, then run the search again.")
        elif not d_description.strip():
            st.warning("Describe what kind of partners you're looking for first.")
        else:
            with st.spinner("Searching and ranking potential partners..."):
                queries = generate_search_queries(d_description, d_market, d_audience, d_type)
                raw_results, error = search_web(queries, tavily_key, 5)
            if error:
                st.warning(error)
            else:
                candidates = deduplicate_companies(extract_company_candidates(raw_results))
                for c in candidates:
                    c.update(calculate_discovery_score(c, d_market, d_audience, d_description))
                    c["Match Level"] = classify_discovery_score(c["Discovery Score"])
                candidates = sorted([c for c in candidates if c["Discovery Score"] >= d_min_score], key=lambda x:x["Discovery Score"], reverse=True)[:d_count]
                st.session_state.discovery_candidates = candidates
                st.session_state.discovery_stats = {"discovered": len(raw_results), "verified": len(candidates), "added": 0}
                if not candidates: st.info("No companies met the threshold. Try a broader description or lower the minimum score.")

    candidates = st.session_state.get("discovery_candidates", [])
    if candidates:
        st.markdown('<div class="section-title">Recommended matches</div>', unsafe_allow_html=True)
        st.caption("Review the evidence before adding a company to your pipeline.")
        selected = []
        for i,c in enumerate(candidates):
            with st.container(border=True):
                top1,top2,top3 = st.columns([5,1.2,1])
                with top1:
                    st.markdown(f"**{c['company_name']}**  ·  {c['industry']}")
                    st.caption(c['description'][:220] + ("..." if len(c['description'])>220 else ""))
                    st.caption(f"{c['website']}  ·  Search relevance: {c['Match Level']}")
                with top2:
                    st.markdown(f"<div class='score'>{c['Discovery Score']}/100</div>", unsafe_allow_html=True)
                with top3:
                    if st.checkbox("Add", key=f"add_disc_{i}"): selected.append(i)
                with st.expander("Why this matched"):
                    cols = st.columns(5)
                    for col, label in zip(cols, ["Industry Match","Audience Match","Market Match","Partnership Signal","Search Relevance"]):
                        col.metric(label, c[label])
        if st.button("➕ Add selected to pipeline", type="primary"):
            if not selected:
                st.warning("Select at least one company first.")
            else:
                for i in selected:
                    r = prepare_partner_record(candidates[i])
                    add_partner_row(r["Company Name"],r["Industry"],r["Target Audience"],r["Company Size"],r["Partnership Notes"],"Web Discovery",r["Website"],r["Discovery Score"],r["Discovery Source"],r["Source URL"])
                st.success(f"Added {len(selected)} partner(s) to your pipeline.")
                st.session_state.discovery_candidates = []
                st.rerun()

# ----------------------------- Partner list --------------------------------
elif st.session_state.page in ["All Partners", "Prioritized List"]:
    prioritized = st.session_state.page == "Prioritized List"
    st.markdown(f'<div class="hero"><div class="eyebrow">Step 2 · Prioritize</div><h1>{"Prioritized partners" if prioritized else "All partners"}</h1><p>{"Focus your time on the strongest partnership opportunities first." if prioritized else "Your central partner workspace."}</p></div>', unsafe_allow_html=True)
    if len(df_scored)==0:
        st.info("No partners yet. Go to Find Partners to discover some.")
    else:
        work = df_scored.sort_values("Total Score", ascending=False) if prioritized else df_scored
        search = st.text_input("Filter partners", placeholder="Search company, industry, or audience")
        if search:
            mask = work.astype(str).apply(lambda col: col.str.contains(search, case=False, na=False)).any(axis=1)
            work = work[mask]
        for _,r in work.iterrows():
            pc = str(r['Priority']).lower()
            with st.container(border=True):
                x1,x2,x3 = st.columns([5,1,1])
                with x1:
                    st.markdown(f"**{r['Company Name']}**  ·  {r['Industry']}")
                    st.caption(f"{r['Target Audience']}  ·  {r['Status']}")
                with x2:
                    st.markdown(f"<span class='pill {pc}'>{r['Priority']}</span>", unsafe_allow_html=True)
                with x3:
                    st.markdown(f"<div class='score'>{int(r['Total Score'])}/100</div>", unsafe_allow_html=True)
                st.caption(f"Fit signals: Industry {int(r['Industry Score'])}/30 · Audience {int(r['Audience Score'])}/25 · Size {int(r['Size Score'])}/20 · Intent {int(r['Intent Score'])}/25")

# ----------------------------- Outreach -----------------------------------
elif st.session_state.page == "Generate Outreach":
    st.markdown('<div class="hero"><div class="eyebrow">Step 3 · Personalize</div><h1>Generate partnership outreach</h1><p>Turn partner intelligence into a relevant first conversation. AI enhancement is optional and never invents facts.</p></div>', unsafe_allow_html=True)
    if len(df_scored)==0:
        st.info("Add at least one partner before generating outreach.")
    else:
        companies = df_scored.sort_values("Total Score", ascending=False)["Company Name"].tolist()
        selected_company = st.selectbox("Partner", companies)
        selected_row = df_scored[df_scored["Company Name"]==selected_company].iloc[0]
        a,b = st.columns([1.2,1])
        with a:
            st.markdown(f'''<div class="card"><div class="small">PARTNER FIT</div><h2 style="margin:.25rem 0">{html.escape(str(selected_row['Company Name']))}</h2><span class="pill {str(selected_row['Priority']).lower()}">{selected_row['Priority']} priority</span><div class="score" style="margin-top:.55rem">{int(selected_row['Total Score'])}/100</div><p class="small">{html.escape(str(selected_row['Target Audience']))}</p></div>''', unsafe_allow_html=True)
        with b:
            st.markdown(f'''<div class="insight"><h3>✦ Why approach them?</h3><p class="small">{html.escape(str(selected_row['Industry']))} alignment with {html.escape(str(selected_row['Target Audience']))} and a partner-fit score of {int(selected_row['Total Score'])}/100.</p><p class="small">Use the first conversation to validate goals, audience overlap, and a small pilot opportunity.</p></div>''', unsafe_allow_html=True)
        use_ai = st.checkbox("Enhance with AI", value=bool(os.environ.get("ANTHROPIC_API_KEY")), help="Uses Anthropic only if ANTHROPIC_API_KEY is configured.")
        if st.button("✨ Generate personalized outreach", type="primary"):
            message = generate_ai_message(selected_row) if use_ai else generate_template_message(selected_row)
            st.session_state.generated_message = message
        if st.session_state.get("generated_message"):
            st.text_area("Your outreach", value=st.session_state.generated_message, height=340)
            st.caption("Draft only — this prototype does not send emails.")

# ----------------------------- Pipeline -----------------------------------
elif st.session_state.page in ["Pipeline", "Follow-ups"]:
    st.markdown(f'<div class="hero"><div class="eyebrow">Step 4 · Track</div><h1>{"Follow-up workspace" if st.session_state.page=="Follow-ups" else "Outreach pipeline"}</h1><p>Keep every partnership opportunity moving with a simple, visible status.</p></div>', unsafe_allow_html=True)
    if len(df_scored)==0:
        st.info("Your pipeline is empty.")
    else:
        statuses = ["Not Contacted", "Contacted", "Replied", "Meeting", "Converted"]
        cols = st.columns(5)
        for col,status in zip(cols,statuses):
            with col:
                rows = df_scored[df_scored["Status"]==status]
                st.markdown(f'<div class="pipeline"><div class="pipeline-head">{status} · {len(rows)}</div>', unsafe_allow_html=True)
                for _,r in rows.head(8).iterrows():
                    st.markdown(f'<div class="pipeline-item"><b>{html.escape(str(r["Company Name"]))}</b><br><span class="small">{int(r["Total Score"])} / 100</span></div>', unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)
        st.markdown('<div class="section-title">Update a partner</div>', unsafe_allow_html=True)
        selected_company = st.selectbox("Partner", df_scored["Company Name"].tolist())
        current = df_scored[df_scored["Company Name"]==selected_company].iloc[0]
        status_options = ["Not Contacted", "Contacted", "Replied", "Meeting", "Converted"]
        new_status = st.selectbox("New status", status_options, index=status_options.index(current["Status"]) if current["Status"] in status_options else 0)
        if st.button("Save status", type="primary"):
            raw = load_data()
            raw.loc[raw["Company Name"]==selected_company,"Status"] = new_status
            save_data(raw)
            st.success(f"{selected_company} moved to {new_status}.")
            st.rerun()

st.divider()
st.caption("AI-Powered Partner Outreach Automation · Prototype/MVP · Does not send real emails or contact real companies.")
