"""
My Daily Spanish – Coach Applications Dashboard
================================================
Reads application records from Supabase (written by the main portal app).

Run locally:
    streamlit run dashboard.py
"""

import streamlit as st
import pandas as pd
import requests
from datetime import datetime

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SUPABASE_URL = st.secrets.get("supabase_url", "")
SUPABASE_KEY = st.secrets.get("supabase_key", "")

st.set_page_config(
    page_title="Coach Applications Dashboard",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Custom CSS
# ---------------------------------------------------------------------------
st.markdown("""
<style>
    .dashboard-header {
        background: linear-gradient(135deg, #1a5276, #2980b9);
        color: white; padding: 1.5rem 2rem; border-radius: 10px; margin-bottom: 1.5rem;
    }
    .dashboard-header h1 { color: white; margin: 0; font-size: 1.8rem; }
    .dashboard-header p  { color: #d6eaf8; margin: 0.3rem 0 0 0; font-size: 1rem; }

    .metric-card {
        background: white; border: 1px solid #e0e0e0; border-radius: 10px;
        padding: 1.2rem; text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    }
    .metric-card .number { font-size: 2rem; font-weight: 700; color: #1a5276; }
    .metric-card .label  { font-size: 0.85rem; color: #7f8c8d; margin-top: 0.2rem; }

    .badge-recommended {
        background: #27ae60; color: white; padding: 3px 10px;
        border-radius: 12px; font-size: 0.8rem; font-weight: 600;
    }
    .badge-maybe {
        background: #f39c12; color: white; padding: 3px 10px;
        border-radius: 12px; font-size: 0.8rem; font-weight: 600;
    }
    .badge-not-recommended {
        background: #e74c3c; color: white; padding: 3px 10px;
        border-radius: 12px; font-size: 0.8rem; font-weight: 600;
    }

    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Nice column labels (JSON key → display name)
# ---------------------------------------------------------------------------
COLUMN_LABELS = {
    "submission_date": "Submission Date",
    "name": "Name",
    "email": "Email",
    "age": "Age",
    "country_origin": "Country of Origin",
    "current_location": "Current Location",
    "timezone": "Time Zone",
    "mobile": "Mobile",
    "whatsapp": "WhatsApp",
    "address": "Address",
    "tax_info": "Tax Information",
    "payment_pref": "Payment Preference",
    "teaching_schedule": "Teaching Schedule",
    "profile_link": "Profile Link",
    "native_spanish": "Native Speaker",
    "spanish_type": "Type of Spanish",
    "years_teaching": "Years Teaching",
    "certifications": "Certifications",
    "students_taught": "Students Taught",
    "all_levels": "Teach A1-C2",
    "levels_detail": "Levels Detail",
    "dele_exp": "DELE Experience",
    "dele_detail": "DELE Detail",
    "current_platforms": "Current Platforms",
    "testimonial_link": "Testimonial Link",
    "english_level": "English Level",
    "ideal_rate": "Ideal Rate (USD)",
    "ai_score": "Score",
    "ai_verdict": "Verdict",
    "ai_summary": "Summary",
    "video_mode": "Video Mode",
    "video_link": "Video Link",
    "files_link": "Files Link",
}

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_applications():
    """Load application records from Supabase."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return pd.DataFrame()

    try:
        resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/applications?select=*&order=id.desc",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        if not data:
            return pd.DataFrame()
        df = pd.DataFrame(data)
        df.drop(columns=["id"], errors="ignore", inplace=True)
        df.rename(columns=COLUMN_LABELS, inplace=True)
        return df
    except Exception:
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# Dashboard components
# ---------------------------------------------------------------------------

def render_metrics(df):
    total = len(df)
    recommended = maybe = not_rec = 0
    if "Verdict" in df.columns:
        verdicts = df["Verdict"].str.strip().str.upper()
        recommended = (verdicts == "RECOMMENDED").sum()
        maybe = (verdicts == "MAYBE").sum()
        not_rec = (verdicts == "NOT RECOMMENDED").sum()

    cols = st.columns(4)
    with cols[0]:
        st.markdown(f'<div class="metric-card"><div class="number">{total}</div>'
                     f'<div class="label">Total Applications</div></div>',
                     unsafe_allow_html=True)
    with cols[1]:
        st.markdown(f'<div class="metric-card"><div class="number" style="color:#27ae60">{recommended}</div>'
                     f'<div class="label">Recommended</div></div>',
                     unsafe_allow_html=True)
    with cols[2]:
        st.markdown(f'<div class="metric-card"><div class="number" style="color:#f39c12">{maybe}</div>'
                     f'<div class="label">Maybe</div></div>',
                     unsafe_allow_html=True)
    with cols[3]:
        st.markdown(f'<div class="metric-card"><div class="number" style="color:#e74c3c">{not_rec}</div>'
                     f'<div class="label">Not Recommended</div></div>',
                     unsafe_allow_html=True)


def render_filters(df):
    st.sidebar.markdown("## Filters")
    filtered = df.copy()

    # Search
    search = st.sidebar.text_input("Search (name or email):", "")
    if search:
        mask = (
            filtered.get("Name", pd.Series(dtype=str)).str.contains(search, case=False, na=False) |
            filtered.get("Email", pd.Series(dtype=str)).str.contains(search, case=False, na=False)
        )
        filtered = filtered[mask]

    # Verdict filter
    if "Verdict" in filtered.columns:
        verdicts = sorted(filtered["Verdict"].dropna().unique())
        verdicts = [v for v in verdicts if v.strip()]
        if verdicts:
            selected = st.sidebar.multiselect("Verdict:", verdicts, default=verdicts)
            filtered = filtered[filtered["Verdict"].isin(selected)]

    # Country filter
    if "Country of Origin" in filtered.columns:
        countries = sorted(filtered["Country of Origin"].dropna().unique())
        countries = [c for c in countries if c.strip()]
        if countries:
            selected = st.sidebar.multiselect("Country:", countries)
            if selected:
                filtered = filtered[filtered["Country of Origin"].isin(selected)]

    # Score range
    if "Score" in filtered.columns:
        scores = pd.to_numeric(filtered["Score"], errors="coerce")
        if scores.notna().any():
            mn, mx = int(scores.min()), int(scores.max())
            if mn < mx:
                rng = st.sidebar.slider("Score range:", mn, mx, (mn, mx))
                filtered = filtered[scores.between(rng[0], rng[1]) | scores.isna()]

    st.sidebar.markdown("---")
    st.sidebar.markdown(f"**Showing {len(filtered)} of {len(df)} applications**")
    return filtered


def render_table(df):
    st.markdown("### Applications")

    if df.empty:
        st.info("No applications match the current filters.")
        return

    summary_cols = [
        "Submission Date", "Name", "Email", "Country of Origin",
        "Years Teaching", "Score", "Verdict", "Ideal Rate (USD)",
    ]
    available = [c for c in summary_cols if c in df.columns]

    st.dataframe(
        df[available],
        use_container_width=True,
        hide_index=True,
        height=min(400, 50 + 35 * len(df)),
    )

    csv = df.to_csv(index=False)
    st.download_button(
        "Download as CSV",
        csv,
        f"coach_applications_{datetime.now().strftime('%Y%m%d')}.csv",
        "text/csv",
    )


def render_detail_view(df):
    st.markdown("### Applicant Details")

    if df.empty:
        return

    names = df.get("Name", pd.Series(dtype=str)).tolist()
    emails = df.get("Email", pd.Series(dtype=str)).tolist()
    options = [f"{n} ({e})" for n, e in zip(names, emails)]

    selected = st.selectbox("Select an applicant to view details:", options)
    if selected is None:
        return

    idx = options.index(selected)
    row = df.iloc[idx]

    sections = {
        "Personal Information": [
            "Name", "Email", "Age", "Country of Origin", "Current Location",
            "Time Zone", "Mobile", "WhatsApp", "Address",
        ],
        "Employment Details": [
            "Tax Information", "Payment Preference", "Teaching Schedule",
            "Profile Link",
        ],
        "Teaching Background": [
            "Native Speaker", "Type of Spanish", "Years Teaching",
            "Certifications", "Students Taught", "Teach A1-C2", "Levels Detail",
            "DELE Experience", "DELE Detail", "Current Platforms",
            "Testimonial Link",
        ],
        "Preferences": [
            "English Level", "Ideal Rate (USD)",
        ],
        "Assessment": [
            "Score", "Verdict", "Summary",
        ],
        "Media & Files": [
            "Video Mode", "Video Link", "Files Link",
        ],
    }

    link_fields = {"Video Link", "Files Link", "Profile Link", "Testimonial Link"}

    for section_name, fields in sections.items():
        available = [f for f in fields if f in row.index and str(row[f]).strip()]
        if not available:
            continue

        with st.expander(section_name, expanded=(section_name == "Personal Information")):
            for field in available:
                value = str(row[field])
                if field == "Verdict":
                    v = value.strip().upper()
                    badge = ("badge-recommended" if v == "RECOMMENDED"
                             else "badge-maybe" if v == "MAYBE"
                             else "badge-not-recommended")
                    st.markdown(f"**{field}:** <span class='{badge}'>{value}</span>",
                                unsafe_allow_html=True)
                elif field in link_fields and value.startswith("http"):
                    st.markdown(f"**{field}:** [{value}]({value})")
                elif field == "Summary":
                    st.markdown(f"**{field}:**")
                    st.text_area("", value, height=150, disabled=True,
                                 key=f"summary_{idx}_{field}")
                else:
                    st.markdown(f"**{field}:** {value}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    st.markdown("""
    <div class="dashboard-header">
        <h1>Coach Applications Dashboard</h1>
        <p>My Daily Spanish — View and manage coach applications</p>
    </div>
    """, unsafe_allow_html=True)

    df = load_applications()

    if df.empty:
        st.info("No applications recorded yet. Applications will appear here "
                "after coaches submit through the portal.")
        return

    # Refresh
    col1, col2 = st.columns([6, 1])
    with col2:
        if st.button("Refresh", use_container_width=True):
            st.rerun()

    render_metrics(df)
    st.markdown("")

    filtered_df = render_filters(df)

    tab1, tab2 = st.tabs(["Table View", "Detail View"])
    with tab1:
        render_table(filtered_df)
    with tab2:
        render_detail_view(filtered_df)


if __name__ == "__main__":
    main()
