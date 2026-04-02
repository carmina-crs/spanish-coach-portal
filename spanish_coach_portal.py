# =============================================================================
# Spanish Coach Application Portal — My Daily Spanish
# Coach-facing multi-step application wizard
# Sends analysis email to admin upon submission
# =============================================================================

import streamlit as st
import os
import json
import re
import smtplib
import traceback
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path

# ---------------------------------------------------------------------------
# Page config (must be first Streamlit call)
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Spanish Coach Application — My Daily Spanish",
    page_icon="🇪🇸",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------------------------
# Brand CSS
# ---------------------------------------------------------------------------
st.markdown("""
<style>
/* Hide ALL Streamlit branding, toolbar, footer, badges, profile icons */
[data-testid="stToolbar"] { display: none !important; }
header[data-testid="stHeader"] { display: none !important; }
footer { display: none !important; }
#MainMenu { display: none !important; }
[data-testid="stDecoration"] { display: none !important; }
[data-testid="stStatusWidget"] { display: none !important; }
.stApp > footer { display: none !important; }
.reportview-container .main footer { display: none !important; }
.stApp::after { display: none !important; }
/* Hide ALL bottom-right fixed elements (Streamlit Cloud badges, profile, branding) */
div[class*="viewerBadge"] { display: none !important; }
div[class*="stDeployButton"] { display: none !important; }
div[class*="StatusWidget"] { display: none !important; }
div[class*="profileContainer"] { display: none !important; }
div[class*="stAppViewBlockContainer"] ~ div { display: none !important; }
a[href*="streamlit.io"] { display: none !important; }
iframe[title*="badge"] { display: none !important; }
iframe[title*="streamlit"] { display: none !important; }
/* Nuclear option: hide any fixed/absolute positioned element in bottom-right corner */
div[style*="position: fixed"][style*="bottom"] { display: none !important; }
div[style*="position:fixed"][style*="bottom"] { display: none !important; }
/* Target Streamlit Cloud injected elements by common class patterns */
[class*="Badge"] { display: none !important; }
[class*="badge"] { display: none !important; }
[class*="Watermark"] { display: none !important; }
[class*="watermark"] { display: none !important; }

/* Global layout */
.block-container { max-width: 800px; padding-top: 2rem; }

/* Brand colours */
:root {
    --brand-red:  #c0392b;
    --brand-gold: #f39c12;
    --brand-dark: #1a1a2e;
}

/* Header */
.portal-header {
    background: linear-gradient(135deg, #c0392b 0%, #922b21 100%);
    color: white;
    padding: 2rem 2rem 1.5rem;
    border-radius: 12px;
    text-align: center;
    margin-bottom: 1.5rem;
    box-shadow: 0 4px 15px rgba(192,57,43,0.3);
}
.portal-header h1 { margin: 0; font-size: 1.9rem; }
.portal-header p  { margin: 0.4rem 0 0; opacity: 0.92; font-size: 1rem; }

/* Step indicator pill */
.step-pill {
    display: inline-block;
    background: #f39c12;
    color: white;
    padding: 0.25rem 0.9rem;
    border-radius: 20px;
    font-size: 0.82rem;
    font-weight: 700;
    margin-bottom: 0.3rem;
}

/* Progress container */
.progress-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.3rem;
}
.progress-pct {
    font-size: 0.85rem;
    color: #888;
    font-weight: 600;
}

/* Section cards */
.section-card {
    background: #fafafa;
    border: 1px solid #eee;
    border-left: 4px solid #c0392b;
    border-radius: 8px;
    padding: 1.2rem 1.4rem;
    margin-bottom: 1.2rem;
}

/* Required badge */
.req-badge {
    background: #e74c3c;
    color: white;
    font-size: 0.7rem;
    padding: 1px 6px;
    border-radius: 4px;
    margin-left: 6px;
    vertical-align: middle;
}

/* Warning / error box */
.warn-box {
    background: #fdecea;
    border: 1px solid #e74c3c;
    border-radius: 8px;
    padding: 1rem 1.2rem;
    margin: 1rem 0;
    color: #922b21;
}

/* Success box */
.success-box {
    background: #eafaf1;
    border: 1px solid #27ae60;
    border-radius: 8px;
    padding: 1.2rem 1.4rem;
    color: #1e8449;
    text-align: center;
}

/* Checklist item */
.check-item { padding: 0.3rem 0; font-size: 1rem; }

/* File note */
.file-note { font-size: 0.82rem; color: #777; margin-top: 0.3rem; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Secrets / config check
# ---------------------------------------------------------------------------
def get_secret(key: str, default=None):
    try:
        return st.secrets[key]
    except Exception:
        return default

ANTHROPIC_KEY   = get_secret("anthropic_api_key")
SENDER_EMAIL    = get_secret("sender_email")
SENDER_PASSWORD = get_secret("sender_password")
ADMIN_EMAIL     = "carmina@talkinfrench.com"

# Google Drive config (optional)
GOOGLE_SA_JSON = ""
try:
    sa_section = st.secrets["google_service_account"]
    sa_dict = {k: str(v) for k, v in sa_section.items()}
    if "type" in sa_dict:
        GOOGLE_SA_JSON = json.dumps(sa_dict)
except Exception:
    GOOGLE_SA_JSON = get_secret("google_service_account_json", "")
GOOGLE_DRIVE_FOLDER = get_secret("google_drive_folder_id", "")

# Questions config URL (optional — for editing questions via GitHub)
QUESTIONS_CONFIG_URL = get_secret("questions_config_url", "")
ADMIN_MODE = get_secret("admin_mode", "") == "true"

@st.cache_data(ttl=300)
def load_questions_config():
    """Load questions config from remote URL or local file."""
    if QUESTIONS_CONFIG_URL:
        import requests as _req
        try:
            resp = _req.get(QUESTIONS_CONFIG_URL, timeout=10)
            if resp.ok:
                return resp.json()
        except Exception:
            pass
    config_path = Path(__file__).parent / "questions_config.json"
    if config_path.exists():
        return json.loads(config_path.read_text(encoding="utf-8"))
    return None

# File storage — works on Windows desktop AND cloud
import tempfile as _tf
_local_dir = Path(r"C:\Users\USER\Desktop\Spanish Coach Applications")
if _local_dir.parent.exists():
    SUBMISSIONS_DIR = _local_dir
else:
    SUBMISSIONS_DIR = Path(_tf.mkdtemp())

secrets_ok = all([
    ANTHROPIC_KEY and ANTHROPIC_KEY != "YOUR_API_KEY_HERE",
    SENDER_EMAIL and SENDER_EMAIL != "YOUR_GMAIL_HERE",
    SENDER_PASSWORD and SENDER_PASSWORD != "YOUR_GMAIL_APP_PASSWORD_HERE",
])

# ---------------------------------------------------------------------------
# Timezone list
# ---------------------------------------------------------------------------
# Build timezone list: Country/City — UTC offset
_TZ_DATA = [
    # UTC-12 to UTC-10
    ("US Minor Outlying Islands — Baker Island", "UTC-12:00"),
    ("American Samoa — Pago Pago", "UTC-11:00"),
    ("United States — Hawaii (Honolulu)", "UTC-10:00"),
    ("French Polynesia — Tahiti", "UTC-10:00"),
    ("Cook Islands — Rarotonga", "UTC-10:00"),
    # UTC-9 to UTC-8
    ("United States — Alaska (Anchorage)", "UTC-09:00"),
    ("United States — Pacific Time (Los Angeles)", "UTC-08:00"),
    ("Canada — Pacific Time (Vancouver)", "UTC-08:00"),
    ("Mexico — Tijuana", "UTC-08:00"),
    # UTC-7
    ("United States — Mountain Time (Denver)", "UTC-07:00"),
    ("Canada — Mountain Time (Edmonton)", "UTC-07:00"),
    ("Mexico — Chihuahua", "UTC-07:00"),
    # UTC-6
    ("United States — Central Time (Chicago)", "UTC-06:00"),
    ("Canada — Central Time (Winnipeg)", "UTC-06:00"),
    ("Mexico — Mexico City", "UTC-06:00"),
    ("Guatemala — Guatemala City", "UTC-06:00"),
    ("Honduras — Tegucigalpa", "UTC-06:00"),
    ("El Salvador — San Salvador", "UTC-06:00"),
    ("Costa Rica — San Jose", "UTC-06:00"),
    ("Nicaragua — Managua", "UTC-06:00"),
    ("Belize — Belmopan", "UTC-06:00"),
    # UTC-5
    ("United States — Eastern Time (New York)", "UTC-05:00"),
    ("Canada — Eastern Time (Toronto)", "UTC-05:00"),
    ("Colombia — Bogota", "UTC-05:00"),
    ("Peru — Lima", "UTC-05:00"),
    ("Ecuador — Quito", "UTC-05:00"),
    ("Cuba — Havana", "UTC-05:00"),
    ("Panama — Panama City", "UTC-05:00"),
    ("Jamaica — Kingston", "UTC-05:00"),
    ("Haiti — Port-au-Prince", "UTC-05:00"),
    # UTC-4
    ("Canada — Atlantic Time (Halifax)", "UTC-04:00"),
    ("Venezuela — Caracas", "UTC-04:00"),
    ("Bolivia — La Paz", "UTC-04:00"),
    ("Dominican Republic — Santo Domingo", "UTC-04:00"),
    ("Puerto Rico — San Juan", "UTC-04:00"),
    ("Paraguay — Asuncion", "UTC-04:00"),
    ("Chile — Santiago", "UTC-04:00"),
    ("Trinidad and Tobago — Port of Spain", "UTC-04:00"),
    ("Barbados — Bridgetown", "UTC-04:00"),
    ("Guyana — Georgetown", "UTC-04:00"),
    # UTC-3
    ("Argentina — Buenos Aires", "UTC-03:00"),
    ("Brazil — Sao Paulo", "UTC-03:00"),
    ("Brazil — Rio de Janeiro", "UTC-03:00"),
    ("Brazil — Brasilia", "UTC-03:00"),
    ("Uruguay — Montevideo", "UTC-03:00"),
    ("Suriname — Paramaribo", "UTC-03:00"),
    ("French Guiana — Cayenne", "UTC-03:00"),
    ("Falkland Islands — Stanley", "UTC-03:00"),
    # UTC-2 to UTC-1
    ("Brazil — Fernando de Noronha", "UTC-02:00"),
    ("South Georgia", "UTC-02:00"),
    ("Portugal — Azores", "UTC-01:00"),
    ("Cape Verde — Praia", "UTC-01:00"),
    # UTC+0
    ("United Kingdom — London", "UTC+00:00"),
    ("Ireland — Dublin", "UTC+00:00"),
    ("Portugal — Lisbon", "UTC+00:00"),
    ("Iceland — Reykjavik", "UTC+00:00"),
    ("Ghana — Accra", "UTC+00:00"),
    ("Senegal — Dakar", "UTC+00:00"),
    ("Morocco — Casablanca", "UTC+01:00"),
    ("Ivory Coast — Abidjan", "UTC+00:00"),
    ("Gambia — Banjul", "UTC+00:00"),
    ("Guinea — Conakry", "UTC+00:00"),
    ("Sierra Leone — Freetown", "UTC+00:00"),
    ("Liberia — Monrovia", "UTC+00:00"),
    ("Mali — Bamako", "UTC+00:00"),
    ("Mauritania — Nouakchott", "UTC+00:00"),
    ("Burkina Faso — Ouagadougou", "UTC+00:00"),
    ("Togo — Lome", "UTC+00:00"),
    # UTC+1
    ("France — Paris", "UTC+01:00"),
    ("Germany — Berlin", "UTC+01:00"),
    ("Spain — Madrid", "UTC+01:00"),
    ("Italy — Rome", "UTC+01:00"),
    ("Netherlands — Amsterdam", "UTC+01:00"),
    ("Belgium — Brussels", "UTC+01:00"),
    ("Switzerland — Zurich", "UTC+01:00"),
    ("Austria — Vienna", "UTC+01:00"),
    ("Poland — Warsaw", "UTC+01:00"),
    ("Czech Republic — Prague", "UTC+01:00"),
    ("Sweden — Stockholm", "UTC+01:00"),
    ("Norway — Oslo", "UTC+01:00"),
    ("Denmark — Copenhagen", "UTC+01:00"),
    ("Hungary — Budapest", "UTC+01:00"),
    ("Serbia — Belgrade", "UTC+01:00"),
    ("Croatia — Zagreb", "UTC+01:00"),
    ("Slovakia — Bratislava", "UTC+01:00"),
    ("Slovenia — Ljubljana", "UTC+01:00"),
    ("Albania — Tirana", "UTC+01:00"),
    ("North Macedonia — Skopje", "UTC+01:00"),
    ("Bosnia — Sarajevo", "UTC+01:00"),
    ("Montenegro — Podgorica", "UTC+01:00"),
    ("Nigeria — Lagos", "UTC+01:00"),
    ("Cameroon — Douala", "UTC+01:00"),
    ("Cameroon — Yaounde", "UTC+01:00"),
    ("Angola — Luanda", "UTC+01:00"),
    ("Congo (DRC) — Kinshasa", "UTC+01:00"),
    ("Chad — Ndjamena", "UTC+01:00"),
    ("Central African Republic — Bangui", "UTC+01:00"),
    ("Republic of Congo — Brazzaville", "UTC+01:00"),
    ("Gabon — Libreville", "UTC+01:00"),
    ("Equatorial Guinea — Malabo", "UTC+01:00"),
    ("Tunisia — Tunis", "UTC+01:00"),
    ("Algeria — Algiers", "UTC+01:00"),
    ("Libya — Tripoli", "UTC+02:00"),
    ("Niger — Niamey", "UTC+01:00"),
    ("Benin — Porto-Novo", "UTC+01:00"),
    # UTC+2
    ("Finland — Helsinki", "UTC+02:00"),
    ("Greece — Athens", "UTC+02:00"),
    ("Romania — Bucharest", "UTC+02:00"),
    ("Bulgaria — Sofia", "UTC+02:00"),
    ("Ukraine — Kyiv", "UTC+02:00"),
    ("Moldova — Chisinau", "UTC+02:00"),
    ("Latvia — Riga", "UTC+02:00"),
    ("Lithuania — Vilnius", "UTC+02:00"),
    ("Estonia — Tallinn", "UTC+02:00"),
    ("Cyprus — Nicosia", "UTC+02:00"),
    ("Israel — Jerusalem", "UTC+02:00"),
    ("Palestine — Ramallah", "UTC+02:00"),
    ("Lebanon — Beirut", "UTC+02:00"),
    ("Jordan — Amman", "UTC+02:00"),
    ("Syria — Damascus", "UTC+02:00"),
    ("Egypt — Cairo", "UTC+02:00"),
    ("South Africa — Johannesburg", "UTC+02:00"),
    ("South Africa — Cape Town", "UTC+02:00"),
    ("Mozambique — Maputo", "UTC+02:00"),
    ("Zimbabwe — Harare", "UTC+02:00"),
    ("Zambia — Lusaka", "UTC+02:00"),
    ("Malawi — Lilongwe", "UTC+02:00"),
    ("Botswana — Gaborone", "UTC+02:00"),
    ("Namibia — Windhoek", "UTC+02:00"),
    ("Rwanda — Kigali", "UTC+02:00"),
    ("Burundi — Bujumbura", "UTC+02:00"),
    ("Congo (DRC) — Lubumbashi", "UTC+02:00"),
    ("Eswatini — Mbabane", "UTC+02:00"),
    ("Lesotho — Maseru", "UTC+02:00"),
    # UTC+3
    ("Turkey — Istanbul", "UTC+03:00"),
    ("Russia — Moscow", "UTC+03:00"),
    ("Saudi Arabia — Riyadh", "UTC+03:00"),
    ("Iraq — Baghdad", "UTC+03:00"),
    ("Kuwait — Kuwait City", "UTC+03:00"),
    ("Qatar — Doha", "UTC+03:00"),
    ("Bahrain — Manama", "UTC+03:00"),
    ("Yemen — Sanaa", "UTC+03:00"),
    ("Kenya — Nairobi", "UTC+03:00"),
    ("Ethiopia — Addis Ababa", "UTC+03:00"),
    ("Tanzania — Dar es Salaam", "UTC+03:00"),
    ("Uganda — Kampala", "UTC+03:00"),
    ("Somalia — Mogadishu", "UTC+03:00"),
    ("Eritrea — Asmara", "UTC+03:00"),
    ("Djibouti — Djibouti", "UTC+03:00"),
    ("Madagascar — Antananarivo", "UTC+03:00"),
    ("Comoros — Moroni", "UTC+03:00"),
    ("Belarus — Minsk", "UTC+03:00"),
    # UTC+3:30
    ("Iran — Tehran", "UTC+03:30"),
    # UTC+4
    ("United Arab Emirates — Dubai", "UTC+04:00"),
    ("Oman — Muscat", "UTC+04:00"),
    ("Georgia — Tbilisi", "UTC+04:00"),
    ("Armenia — Yerevan", "UTC+04:00"),
    ("Azerbaijan — Baku", "UTC+04:00"),
    ("Mauritius — Port Louis", "UTC+04:00"),
    ("Seychelles — Victoria", "UTC+04:00"),
    ("Reunion — Saint-Denis", "UTC+04:00"),
    # UTC+4:30
    ("Afghanistan — Kabul", "UTC+04:30"),
    # UTC+5
    ("Pakistan — Karachi", "UTC+05:00"),
    ("Pakistan — Islamabad", "UTC+05:00"),
    ("Uzbekistan — Tashkent", "UTC+05:00"),
    ("Tajikistan — Dushanbe", "UTC+05:00"),
    ("Turkmenistan — Ashgabat", "UTC+05:00"),
    ("Kazakhstan — Almaty", "UTC+05:00"),
    ("Kyrgyzstan — Bishkek", "UTC+06:00"),
    ("Maldives — Male", "UTC+05:00"),
    # UTC+5:30
    ("India — Mumbai", "UTC+05:30"),
    ("India — New Delhi", "UTC+05:30"),
    ("India — Bangalore", "UTC+05:30"),
    ("India — Kolkata", "UTC+05:30"),
    ("India — Chennai", "UTC+05:30"),
    ("Sri Lanka — Colombo", "UTC+05:30"),
    # UTC+5:45
    ("Nepal — Kathmandu", "UTC+05:45"),
    # UTC+6
    ("Bangladesh — Dhaka", "UTC+06:00"),
    ("Bhutan — Thimphu", "UTC+06:00"),
    ("Kazakhstan — Astana", "UTC+06:00"),
    # UTC+6:30
    ("Myanmar — Yangon", "UTC+06:30"),
    ("Cocos Islands", "UTC+06:30"),
    # UTC+7
    ("Thailand — Bangkok", "UTC+07:00"),
    ("Vietnam — Ho Chi Minh City", "UTC+07:00"),
    ("Vietnam — Hanoi", "UTC+07:00"),
    ("Indonesia — Jakarta", "UTC+07:00"),
    ("Cambodia — Phnom Penh", "UTC+07:00"),
    ("Laos — Vientiane", "UTC+07:00"),
    ("Mongolia — Ulaanbaatar", "UTC+08:00"),
    # UTC+8
    ("China — Beijing", "UTC+08:00"),
    ("China — Shanghai", "UTC+08:00"),
    ("China — Shenzhen", "UTC+08:00"),
    ("Taiwan — Taipei", "UTC+08:00"),
    ("Hong Kong", "UTC+08:00"),
    ("Macau", "UTC+08:00"),
    ("Singapore", "UTC+08:00"),
    ("Malaysia — Kuala Lumpur", "UTC+08:00"),
    ("Philippines — Manila", "UTC+08:00"),
    ("Indonesia — Bali (Denpasar)", "UTC+08:00"),
    ("Brunei — Bandar Seri Begawan", "UTC+08:00"),
    ("Australia — Perth", "UTC+08:00"),
    # UTC+9
    ("Japan — Tokyo", "UTC+09:00"),
    ("South Korea — Seoul", "UTC+09:00"),
    ("North Korea — Pyongyang", "UTC+09:00"),
    ("Indonesia — Jayapura", "UTC+09:00"),
    ("Timor-Leste — Dili", "UTC+09:00"),
    ("Palau — Ngerulmud", "UTC+09:00"),
    # UTC+9:30
    ("Australia — Darwin", "UTC+09:30"),
    ("Australia — Adelaide", "UTC+09:30"),
    # UTC+10
    ("Australia — Sydney", "UTC+10:00"),
    ("Australia — Melbourne", "UTC+10:00"),
    ("Australia — Brisbane", "UTC+10:00"),
    ("Australia — Canberra", "UTC+10:00"),
    ("Papua New Guinea — Port Moresby", "UTC+10:00"),
    ("Guam — Hagatna", "UTC+10:00"),
    # UTC+11
    ("Solomon Islands — Honiara", "UTC+11:00"),
    ("New Caledonia — Noumea", "UTC+11:00"),
    ("Vanuatu — Port Vila", "UTC+11:00"),
    ("Micronesia — Palikir", "UTC+11:00"),
    # UTC+12
    ("New Zealand — Auckland", "UTC+12:00"),
    ("New Zealand — Wellington", "UTC+12:00"),
    ("Fiji — Suva", "UTC+12:00"),
    ("Marshall Islands — Majuro", "UTC+12:00"),
    ("Tuvalu — Funafuti", "UTC+12:00"),
    ("Nauru — Yaren", "UTC+12:00"),
    ("Kiribati — Tarawa", "UTC+12:00"),
    # UTC+13
    ("Tonga — Nuku'alofa", "UTC+13:00"),
    ("Samoa — Apia", "UTC+13:00"),
    # UTC+14
    ("Kiribati — Line Islands", "UTC+14:00"),
]

TIMEZONE_OPTIONS = ["(Select your timezone)"] + [f"{country} ({utc})" for country, utc in _TZ_DATA]

# ---------------------------------------------------------------------------
# Session-state initialiser
# ---------------------------------------------------------------------------
DEFAULTS = {
    "step": 0,
    # Step 1 – Documents
    "cv_file": None, "cert_files": [], "photo_file": None,
    # Step 2 – Videos
    "video_mode": "Upload two separate videos (Spanish + English)",
    "video_spanish": None, "video_english": None,
    "video_combined": None, "video_link": "",
    # Step 3 – Personal
    "first_name": "", "last_name": "", "email": "", "age": "",
    "mobile": "", "whatsapp": "",
    "country_origin": "", "current_location": "", "address": "",
    "timezone": "", "profile_link": "", "teaching_schedule": "",
    "payment_pref": "Upwork", "tax_info": "",
    # Step 4 – Background
    "native_spanish": "Yes", "spanish_type": "", "years_teaching": "",
    "certifications": "", "students_taught": "", "all_levels": "Yes",
    "levels_detail": "", "testimonial_files": [], "testimonial_link": "",
    "dele_exp": "No", "dele_detail": "", "current_platforms": "",
    # Step 5 – Philosophy (dynamic)
    "assess_proficiency": "", "tailor_lessons": "", "successful_lesson": "",
    "engaging_online": "", "student_duration": "", "motivate_struggling": "",
    "enjoy_process": "",
    # Step 6 – Technology (dynamic)
    "multimedia": "Yes", "multimedia_examples": "", "tech_setup": "Yes",
    "software": [], "software_other": "", "assess_progress": "",
    "feedback_style": "", "adapt_teaching": "", "cultural_lesson": "",
    # Step 7 – Development (dynamic)
    "improve_skills": "", "excited_areas": "", "grammar_error": "",
    "lesson_plan_levels": "",
    # Step 8 – Team / Rate
    "handle_criticism": "", "teamwork": "", "follow_process": "Yes",
    "first_session_win": "", "session_notes_ok": "Yes", "english_level": "Advanced/C1-C2",
    "respond_24h": "Yes", "ideal_rate": "", "hours_per_week": 10,
    "confirm_communication": None, "confirm_payment": None,
    "confirm_taxes": None, "confirm_parttime": None,
    # Step 9 – Quiz
    "quiz_1": "", "quiz_2": "", "quiz_3": "", "quiz_4": "",
    "quiz_5": "", "quiz_6": "", "quiz_7": "", "quiz_8": "",
    "quiz_9": "", "quiz_10": "", "quiz_11": "", "quiz_12": "",
    # Submission
    "submitted": False,
}

for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def go_to(step: int):
    st.session_state["step"] = step


def valid_email(addr: str) -> bool:
    return bool(re.match(r"[^@]+@[^@]+\.[^@]+", addr.strip()))


def progress_pct(step: int) -> float:
    return max(0.0, min(1.0, step / 10.0))


def get_full_name() -> str:
    return f"{st.session_state.get('first_name', '')} {st.session_state.get('last_name', '')}".strip()


def show_header(title: str, subtitle: str = ""):
    st.markdown(f"""
    <div class="portal-header">
        <h1>{title}</h1>
        {"<p>" + subtitle + "</p>" if subtitle else ""}
    </div>""", unsafe_allow_html=True)


def show_step_pill(step: int, total: int = 10):
    pct = int(step / total * 100)
    st.markdown(f"""
    <div class="progress-row">
        <div class="step-pill">Step {step} of {total}</div>
        <span class="progress-pct">{pct}% complete</span>
    </div>""", unsafe_allow_html=True)
    st.progress(progress_pct(step))


def show_save_button(step: int):
    """Render a prominent Save My Progress button below navigation."""
    try:
        st.markdown("---")
        progress_json = json.dumps(get_saveable_state(), indent=2, default=str)
        st.download_button("\U0001f4be Save My Progress", progress_json,
                           "my_spanish_coach_application.json", "application/json",
                           use_container_width=True, key=f"save_step_{step}")
    except Exception:
        pass


def nav_buttons(back_step: int, back_key: str, next_key: str = "", next_label: str = "Continue",
                on_next=None, form_mode: bool = False):
    """Render equal-width Back and Next buttons. Returns True if Next was clicked (non-form mode)."""
    if form_mode:
        return None
    col_back, col_next = st.columns(2)
    with col_back:
        if st.button(f"← Back", use_container_width=True, key=back_key):
            go_to(back_step); st.rerun()
    with col_next:
        if st.button(f"{next_label} →", type="primary", use_container_width=True, key=next_key):
            if on_next:
                on_next()
            return True
    return False


# ---------------------------------------------------------------------------
# Save / Load progress
# ---------------------------------------------------------------------------

def get_saveable_state() -> dict:
    exclude = {"cv_file", "cert_files", "photo_file", "video_spanish", "video_english",
               "video_combined", "testimonial_files", "submitted", "_success_name",
               "_success_email", "_email_sent", "_email_error"}
    data = {}
    for k, v in st.session_state.items():
        if k not in exclude and not k.startswith("_") and not k.startswith("FormSubmitter"):
            if isinstance(v, (str, int, float, bool)):
                data[k] = v
            elif isinstance(v, list):
                # Only save lists of simple types (not file objects)
                if all(isinstance(item, (str, int, float, bool)) for item in v):
                    data[k] = v
    return data


def load_saved_state(data: dict):
    # Handle legacy full_name → first_name + last_name
    if "full_name" in data and "first_name" not in data:
        parts = data["full_name"].split(" ", 1)
        data["first_name"] = parts[0]
        data["last_name"] = parts[1] if len(parts) > 1 else ""
    for k, v in data.items():
        if k in DEFAULTS:
            st.session_state[k] = v


# ---------------------------------------------------------------------------
# File / document extraction helpers
# ---------------------------------------------------------------------------

def extract_text_from_bytes(file_bytes: bytes, filename: str) -> str:
    text = ""
    try:
        ext = Path(filename).suffix.lower()
        if ext == ".pdf":
            import pdfplumber, io
            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                for page in pdf.pages:
                    t = page.extract_text()
                    if t:
                        text += t + "\n"
        elif ext in (".docx", ".doc"):
            import docx, io
            doc = docx.Document(io.BytesIO(file_bytes))
            text = "\n".join(p.text for p in doc.paragraphs)
    except Exception:
        text = ""
    return text.strip()


# ---------------------------------------------------------------------------
# Folder / file saving
# ---------------------------------------------------------------------------

def save_submission_files(state: dict) -> Path:
    full_name = f"{state['first_name']} {state['last_name']}".strip()
    name_clean = re.sub(r"[^\w\s-]", "", full_name).strip().replace(" ", "_")
    date_str   = datetime.now().strftime("%Y-%m-%d")
    folder     = SUBMISSIONS_DIR / f"{name_clean}_{date_str}"
    folder.mkdir(parents=True, exist_ok=True)

    # CV
    if state["cv_file"] is not None:
        cv_ext  = Path(state["cv_file"].name).suffix
        cv_path = folder / f"cv{cv_ext}"
        cv_path.write_bytes(state["cv_file"].getbuffer())

    # Certificates
    for i, cert in enumerate(state["cert_files"], start=1):
        cert_ext  = Path(cert.name).suffix
        cert_path = folder / f"certificate_{i}{cert_ext}"
        cert_path.write_bytes(cert.getbuffer())

    # Photo
    if state.get("photo_file") is not None:
        ph_ext  = Path(state["photo_file"].name).suffix
        ph_path = folder / f"photo{ph_ext}"
        ph_path.write_bytes(state["photo_file"].getbuffer())

    # Videos — depends on video_mode
    vmode = state.get("video_mode", "Upload two separate videos (Spanish + English)")
    if vmode == "Upload two separate videos (Spanish + English)":
        if state["video_spanish"] is not None:
            vs_ext  = Path(state["video_spanish"].name).suffix
            (folder / f"video_spanish{vs_ext}").write_bytes(state["video_spanish"].getbuffer())
        if state["video_english"] is not None:
            ve_ext  = Path(state["video_english"].name).suffix
            (folder / f"video_english{ve_ext}").write_bytes(state["video_english"].getbuffer())
    elif vmode == "Upload one combined video (Spanish & English in one)":
        if state["video_combined"] is not None:
            vc_ext  = Path(state["video_combined"].name).suffix
            (folder / f"video_combined{vc_ext}").write_bytes(state["video_combined"].getbuffer())

    # Testimonial screenshots
    for i, tf in enumerate(state.get("testimonial_files", []), start=1):
        try:
            tf_ext = Path(tf.name).suffix
            (folder / f"testimonial_{i}{tf_ext}").write_bytes(tf.getbuffer())
        except Exception:
            pass

    # JSON data dump
    json_data = {k: v for k, v in state.items()
                 if k not in ("cv_file", "cert_files", "photo_file", "video_spanish",
                              "video_english", "video_combined", "testimonial_files",
                              "step", "submitted")}
    (folder / "submission_data.json").write_text(
        json.dumps(json_data, indent=2, default=str), encoding="utf-8"
    )

    return folder


# ---------------------------------------------------------------------------
# File hosting upload
# ---------------------------------------------------------------------------

def upload_files_to_hosting(folder_path: Path, coach_name: str) -> str:
    import requests as _req
    import zipfile

    date_str = datetime.now().strftime("%Y-%m-%d")
    zip_name = f"{re.sub(r'[^a-zA-Z0-9_-]', '_', coach_name)}_{date_str}.zip"
    zip_path = folder_path.parent / zip_name
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in folder_path.iterdir():
            if f.is_file():
                zf.write(f, f.name)

    server_resp = _req.get("https://api.gofile.io/servers", timeout=10).json()
    server = server_resp["data"]["servers"][0]["name"]

    with open(zip_path, "rb") as f:
        upload_resp = _req.post(
            f"https://{server}.gofile.io/contents/uploadfile",
            files={"file": (zip_name, f)},
            timeout=300,
        ).json()

    if upload_resp.get("status") == "ok":
        return upload_resp["data"]["downloadPage"]

    raise Exception(f"File hosting upload failed: {upload_resp}")


def create_zip_of_folder(folder_path: Path) -> Path:
    import zipfile
    zip_path = folder_path.parent / f"{folder_path.name}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in folder_path.iterdir():
            if f.is_file():
                zf.write(f, f.name)
    return zip_path


# ---------------------------------------------------------------------------
# Claude analysis
# ---------------------------------------------------------------------------

def run_claude_analysis(state: dict, cv_text: str, cert_texts: list[str]) -> dict:
    import anthropic

    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    full_name = f"{state['first_name']} {state['last_name']}".strip()

    quiz_answers = "\n".join([
        f"Q{i}: {state.get(f'quiz_{i}', '')}" for i in range(1, 13)
    ])
    certs_combined = "\n\n".join(cert_texts) if cert_texts else "No certificate text extracted."

    prompt = f"""You are an expert hiring manager for My Daily Spanish, an online Spanish coaching platform.

Analyse the following Spanish coach application and return a JSON object with your assessment.

=== PERSONAL INFO ===
Name: {full_name}
Email: {state['email']}
Age: {state['age']}
Country of Origin: {state['country_origin']}
Current Location: {state['current_location']}
Timezone: {state['timezone']}
Upwork/LinkedIn: {state['profile_link']}
Teaching Schedule: {state['teaching_schedule']}
Payment Preference: {state['payment_pref']}
Tax Info: {state['tax_info']}

=== PROFESSIONAL BACKGROUND ===
Native Spanish Speaker: {state['native_spanish']}
Type of Spanish: {state['spanish_type']}
Years Teaching: {state['years_teaching']}
Certifications: {state['certifications']}
Students Taught: {state['students_taught']}
Can Teach A1-C2: {state['all_levels']}
Level Details: {state['levels_detail']}
Testimonials: {"Screenshots uploaded" if state.get('testimonial_files') else "None uploaded"} {state.get('testimonial_link', '')}
DELE Experience: {state['dele_exp']}
DELE Detail: {state['dele_detail']}
Current Platforms: {state['current_platforms']}

=== TEACHING PHILOSOPHY ===
Assess Proficiency: {state['assess_proficiency']}
Tailor Lessons: {state['tailor_lessons']}
Successful Lesson Example: {state['successful_lesson']}
Engaging Online: {state['engaging_online']}
Student Duration: {state['student_duration']}
Motivate Struggling: {state['motivate_struggling']}
Enjoy Process: {state['enjoy_process']}

=== TECHNOLOGY & ASSESSMENT ===
Multimedia Use: {state['multimedia']}
Multimedia Examples: {state['multimedia_examples']}
Tech Setup: {state['tech_setup']}
Software: {', '.join(state['software'])} {state['software_other']}
Assess Progress: {state['assess_progress']}
Feedback Style: {state['feedback_style']}
Adapt Teaching: {state['adapt_teaching']}
Cultural Lesson: {state['cultural_lesson']}

=== PROFESSIONAL DEVELOPMENT ===
Improve Skills: {state['improve_skills']}
Excited Areas: {state['excited_areas']}
Grammar Error Approach: {state['grammar_error']}
Lesson Plan Levels: {state['lesson_plan_levels']}

=== TEAM & COMMUNICATION ===
Handle Criticism: {state['handle_criticism']}
Teamwork: {state['teamwork']}
Follow Process: {state['follow_process']}
First Session Win: {state['first_session_win']}
Session Notes OK: {state['session_notes_ok']}
English Level: {state['english_level']}
Ideal Rate (USD): {state['ideal_rate']}

=== PROGRAM QUIZ ANSWERS ===
{quiz_answers}

=== CV TEXT ===
{cv_text if cv_text else "CV text could not be extracted."}

=== CERTIFICATE TEXT ===
{certs_combined}

=== PHOTO ===
{"Photo uploaded: " + state["photo_file"].name if state.get("photo_file") else "No photo uploaded."}

---

Return ONLY a valid JSON object (no markdown, no extra text) with exactly these fields:
{{
  "coach_name": "",
  "upwork_link": "",
  "country_of_origin": "",
  "type_of_spanish": "",
  "native_speaker": "Yes/No/Unclear",
  "years_experience": "",
  "num_students_taught": "",
  "can_teach_a1_c2": "Yes/No/Partial",
  "certificates": "",
  "english_level": "",
  "rate_per_hour": "",
  "availability_hours_per_week": "",
  "payment_preference": "",
  "teaching_methodology_summary": "",
  "technology_setup": "Good/Adequate/Poor",
  "quiz_performance": "Excellent/Good/Fair/Poor",
  "quiz_notes": "",
  "cv_summary": "",
  "strengths": ["", "", ""],
  "concerns": ["", ""],
  "missing_elements": [""],
  "overall_score": 0,
  "verdict": "STRONGLY RECOMMENDED / RECOMMENDED / NEEDS FURTHER REVIEW / NOT RECOMMENDED",
  "verdict_reason": "",
  "summary": "",
  "recommended_action": ""
}}

Score out of 100. Verdict: STRONGLY RECOMMENDED (85-100), RECOMMENDED (70-84), NEEDS FURTHER REVIEW (50-69), NOT RECOMMENDED (0-49).
Be honest and thorough. Flag anything missing, vague, or concerning."""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)

    return json.loads(raw)


# ---------------------------------------------------------------------------
# Email sender
# ---------------------------------------------------------------------------

def build_email_html(analysis: dict, folder: Path, files_list: list[str], drive_link: str = "", video_info: str = "") -> str:
    verdict = analysis.get("verdict", "NEEDS FURTHER REVIEW")
    score   = analysis.get("overall_score", 0)

    verdict_color = {
        "STRONGLY RECOMMENDED": "#27ae60",
        "RECOMMENDED": "#2ecc71",
        "NEEDS FURTHER REVIEW": "#f39c12",
        "NOT RECOMMENDED": "#e74c3c",
    }.get(verdict, "#888")

    strengths_html  = "".join(f"<li>{s}</li>" for s in analysis.get("strengths", []))
    concerns_html   = "".join(f"<li>{c}</li>" for c in analysis.get("concerns", []))
    missing         = analysis.get("missing_elements", [])
    missing_html    = ""
    if missing and missing != [""]:
        items = "".join(f"<li>{m}</li>" for m in missing if m)
        missing_html = f"""
        <div style="background:#fdecea;border:1px solid #e74c3c;border-radius:8px;padding:1rem;margin:1rem 0;">
            <strong style="color:#c0392b;">Missing / Incomplete Items:</strong>
            <ul style="margin:0.5rem 0 0;">{items}</ul>
        </div>"""

    upwork = analysis.get("upwork_link", "")
    upwork_display = f'<a href="{upwork}">{upwork}</a>' if upwork else "\u2014"

    files_items = "".join(f"<li>{f}</li>" for f in files_list)

    return f"""
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><style>
  body {{ font-family: Arial, sans-serif; color: #333; background: #f5f5f5; margin:0; padding:20px; }}
  .container {{ max-width:700px; margin:0 auto; background:white; border-radius:12px; overflow:hidden;
                box-shadow:0 2px 10px rgba(0,0,0,0.1); }}
  .header {{ background:linear-gradient(135deg,#c0392b,#922b21); color:white; padding:24px 28px; }}
  .header h1 {{ margin:0; font-size:1.5rem; }}
  .header p  {{ margin:4px 0 0; opacity:0.9; }}
  .body {{ padding:24px 28px; }}
  .verdict-badge {{ display:inline-block; background:{verdict_color}; color:white; font-size:1.4rem;
                    font-weight:700; padding:10px 28px; border-radius:30px; margin:12px 0; }}
  table {{ width:100%; border-collapse:collapse; margin:16px 0; }}
  th {{ background:#f8f8f8; text-align:left; padding:8px 10px; font-size:0.85rem; color:#555;
        border-bottom:1px solid #eee; }}
  td {{ padding:8px 10px; border-bottom:1px solid #f0f0f0; font-size:0.9rem; }}
  h3 {{ color:#c0392b; margin:20px 0 8px; }}
  ul {{ margin:4px 0 0 16px; }}
  li {{ margin:3px 0; }}
  .footer {{ background:#f8f8f8; padding:14px 28px; font-size:0.8rem; color:#888; border-top:1px solid #eee; }}
</style></head>
<body>
<div class="container">
  <div class="header">
    <h1>New Spanish Coach Application</h1>
    <p>Received: {datetime.now().strftime("%B %d, %Y at %H:%M")}</p>
  </div>
  <div class="body">

    <div style="text-align:center;padding:8px 0 16px;">
      <div class="verdict-badge">{verdict} \u2014 {score}/100</div>
    </div>

    <table>
      <tr><th>Coach Name</th><td>{analysis.get('coach_name','')}</td></tr>
      <tr><th>Upwork / LinkedIn</th><td>{upwork_display}</td></tr>
      <tr><th>Country of Origin</th><td>{analysis.get('country_of_origin','')}</td></tr>
      <tr><th>Type of Spanish</th><td>{analysis.get('type_of_spanish','')}</td></tr>
      <tr><th>Native Speaker</th><td>{analysis.get('native_speaker','')}</td></tr>
      <tr><th>Experience</th><td>{analysis.get('years_experience','')} years</td></tr>
      <tr><th>Students Taught</th><td>{analysis.get('num_students_taught','')}</td></tr>
      <tr><th>Teaches A1\u2013C2</th><td>{analysis.get('can_teach_a1_c2','')}</td></tr>
      <tr><th>Certificates</th><td>{analysis.get('certificates','')}</td></tr>
      <tr><th>English Level</th><td>{analysis.get('english_level','')}</td></tr>
      <tr><th>Rate Per Hour</th><td>{analysis.get('rate_per_hour','')}</td></tr>
      <tr><th>Availability</th><td>{analysis.get('availability_hours_per_week','')} hrs/week</td></tr>
      <tr><th>Payment Preference</th><td>{analysis.get('payment_preference','')}</td></tr>
      <tr><th>Quiz Performance</th><td>{analysis.get('quiz_performance','')}</td></tr>
    </table>

    <h3>Summary</h3>
    <p>{analysis.get('summary','')}</p>

    <h3>Teaching Methodology</h3>
    <p>{analysis.get('teaching_methodology_summary','')}</p>

    <h3>Strengths</h3>
    <ul>{strengths_html}</ul>

    <h3>Concerns</h3>
    <ul>{concerns_html}</ul>

    {missing_html}

    <h3>Quiz Notes</h3>
    <p>{analysis.get('quiz_notes','')}</p>

    <h3>CV Summary</h3>
    <p>{analysis.get('cv_summary','')}</p>

    <h3>Verdict Reason</h3>
    <p>{analysis.get('verdict_reason','')}</p>

    <h3>Recommended Action</h3>
    <p style="background:#f0f7ff;border-left:4px solid #3498db;padding:10px 14px;border-radius:4px;">
      {analysis.get('recommended_action','')}
    </p>

    <h3>Files</h3>
    {"<p style='text-align:center;margin:12px 0 16px;'><a href='" + drive_link + "' style='display:inline-block;background:#c0392b;color:white;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:700;font-size:1rem;'>Download All Files (CV, Certificates, Videos)</a></p><p style='text-align:center;font-size:0.85rem;color:#888;'>Link is available for 10 days. Download and save to your Google Drive.</p>" if drive_link else "<p>Location: <code>" + str(folder) + "</code></p>"}
    <ul>{files_items}</ul>

    {"<h3>Video</h3><p>" + video_info + "</p>" if video_info else ""}

  </div>
  <div class="footer">
    This email was generated automatically by the My Daily Spanish Coach Portal.
    Please do not reply to this email.
  </div>
</div>
</body>
</html>
"""


def send_email(analysis: dict, html_body: str, folder: Path, attach_paths: list[Path]):
    msg = MIMEMultipart("mixed")
    msg["From"]    = SENDER_EMAIL
    msg["To"]      = ADMIN_EMAIL
    verdict        = analysis.get("verdict", "NEEDS FURTHER REVIEW")
    coach_name     = analysis.get("coach_name", "Unknown")
    msg["Subject"] = f"New Spanish Coach Application \u2014 {coach_name} \u2014 {verdict}"

    msg.attach(MIMEText(html_body, "html", "utf-8"))

    for path in attach_paths:
        if path.exists():
            with open(path, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", "attachment", filename=path.name)
            msg.attach(part)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, ADMIN_EMAIL, msg.as_string())


def send_applicant_confirmation(applicant_email: str, applicant_name: str):
    msg = MIMEMultipart("alternative")
    msg["From"]    = SENDER_EMAIL
    msg["To"]      = applicant_email
    msg["Subject"] = "Your Spanish Coach Application \u2014 Received"

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;color:#333;margin:0;padding:20px;background:#f5f5f5;">
<div style="max-width:600px;margin:0 auto;background:white;border-radius:12px;overflow:hidden;box-shadow:0 2px 10px rgba(0,0,0,0.1);">
  <div style="background:linear-gradient(135deg,#c0392b,#922b21);color:white;padding:24px 28px;">
    <h1 style="margin:0;font-size:1.4rem;">My Daily Spanish</h1>
    <p style="margin:4px 0 0;opacity:0.9;">Coach Application Confirmation</p>
  </div>
  <div style="padding:24px 28px;">
    <p>Dear <strong>{applicant_name}</strong>,</p>
    <p>Thank you for submitting your application to become a Spanish coach with My Daily Spanish!</p>
    <p>We have received your application and all accompanying documents. Our team will review everything
    and get back to you within <strong>5\u20137 business days</strong>.</p>
    <p>If you have any questions in the meantime, please contact us at
    <a href="mailto:carmina@talkinfrench.com">carmina@talkinfrench.com</a>.</p>
    <p style="margin-top:24px;">Best regards,<br><strong>The My Daily Spanish Team</strong></p>
  </div>
  <div style="background:#f8f8f8;padding:14px 28px;font-size:0.8rem;color:#888;border-top:1px solid #eee;">
    This is an automated confirmation. Please do not reply to this email.
  </div>
</div>
</body></html>"""

    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, applicant_email, msg.as_string())


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def check_completeness(state: dict) -> list[str]:
    missing = []

    # Step 1 checks — Documents
    if state["cv_file"] is None:           missing.append("CV / Resume (Step 1)")
    if not state["cert_files"]:            missing.append("At least one Teaching Certificate (Step 1)")
    if state.get("photo_file") is None:    missing.append("Professional Photo (Step 1)")

    # Step 2 checks — Video
    vmode = state.get("video_mode", "Upload two separate videos (Spanish + English)")
    if vmode == "Upload two separate videos (Spanish + English)":
        if state["video_spanish"] is None:  missing.append("Spanish Introduction Video (Step 2)")
        if state["video_english"] is None:  missing.append("English Introduction Video (Step 2)")
    elif vmode == "Upload one combined video (Spanish & English in one)":
        if state["video_combined"] is None: missing.append("Combined Introduction Video (Step 2)")
    else:
        if not state.get("video_link", "").strip(): missing.append("Video Link (Step 2)")

    # Step 3 checks — Personal
    if not state["first_name"].strip():    missing.append("First Name (Step 3)")
    if not state["last_name"].strip():     missing.append("Last Name (Step 3)")
    if not valid_email(state["email"]):    missing.append("Valid Email Address (Step 3)")
    if not state["mobile"].strip():        missing.append("Mobile Number (Step 3)")
    if not state["country_origin"].strip(): missing.append("Country of Origin (Step 3)")
    if not state["address"].strip():       missing.append("Full Address (Step 3)")
    if not state["timezone"].strip():      missing.append("Time Zone (Step 3)")

    # Step 4 checks — Background
    if not state["certifications"].strip(): missing.append("Certifications (Step 4)")
    if not state["students_taught"].strip(): missing.append("Students Taught (Step 4)")

    # Step 8 checks — Team/Rate
    if not state.get("confirm_communication"): missing.append("Confirmation: Communication commitment (Step 8)")
    if not state["confirm_payment"]:  missing.append("Confirmation: Payment basis (Step 8)")
    if not state["confirm_taxes"]:    missing.append("Confirmation: Tax responsibility (Step 8)")
    if not state["confirm_parttime"]: missing.append("Confirmation: Part-time role & assignments (Step 8)")

    # Step 9 quiz — all 12 required
    for i in range(1, 13):
        if not state.get(f"quiz_{i}", "").strip():
            missing.append(f"Quiz Answer {i} (Step 9)")

    return missing


# ===========================================================================
# STEP RENDERERS
# ===========================================================================

# ---------------------------------------------------------------------------
# Step 0 — Welcome
# ---------------------------------------------------------------------------

def render_step_0():
    show_header("Spanish Coach Application", "My Daily Spanish")

    st.markdown("""
    <div class="section-card">
    <h3 style="margin-top:0;">Welcome!</h3>
    <p>Apply to become a certified Spanish coach with our platform.<br>
    Complete all steps carefully — this usually takes <strong>20–30 minutes</strong>.</p>
    <p>If you cannot finish your application now, use the <strong>"Save My Progress"</strong> button at the bottom of each step — a <code>.json</code> file will be downloaded to your device (check your Downloads folder).</p>
    <p>When you're ready to continue, simply upload that <code>.json</code> file below to pick up where you left off.<br>
    <strong>Don't forget to save and download your progress before leaving if you want to resume later.</strong></p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("### Before you begin, please have ready:")
    items = [
        "Your <strong>CV / Resume in English</strong> (PDF or Word document)",
        "Your <strong>relevant certificates</strong> — degree or recognized teaching certificate in Spanish or education (PDF, PNG, or JPG)",
        "A <strong>professional photo</strong> of yourself (PNG or JPG)",
        "A <strong>short introduction video</strong> (2–5 min) in Spanish and English — <strong>good video quality, no background noise</strong>",
    ]
    for label in items:
        st.markdown(f'<div class="check-item">\u2714 {label}</div>', unsafe_allow_html=True)

    st.markdown("")

    # Resume from saved progress
    st.markdown("---")
    st.markdown("**Returning applicant?** Upload your saved progress file below:")
    resume_file = st.file_uploader("Upload your saved progress file (.json)",
                                    type=["json"], key="resume_uploader")
    if resume_file:
        try:
            data = json.loads(resume_file.read())
            load_saved_state(data)
            st.success("Progress loaded! Click 'Start Application' to continue.")
        except Exception:
            st.error("Could not load the file. Please make sure it's a valid progress file.")

    st.markdown("")
    if st.button("Start Application", type="primary", use_container_width=True):
        go_to(1)
        st.rerun()


# ---------------------------------------------------------------------------
# Step 1 — Upload Documents (CV, Certificates, Photo)
# ---------------------------------------------------------------------------

def render_step_1():
    show_header("Spanish Coach Application")
    show_step_pill(1)
    st.subheader("Step 1 — Upload Documents")

    st.markdown("""
    <div class="section-card">
    <p>Please upload your documents below. We will review them as part of your application.</p>
    <ul>
        <li><strong>CV / Resume</strong> — Must be <strong>in English</strong></li>
        <li><strong>Relevant Certificates</strong> — Degree or recognized teaching certificate in Spanish or education</li>
        <li><strong>Professional Photo</strong> — Clear, professional-looking headshot</li>
    </ul>
    </div>
    """, unsafe_allow_html=True)

    cv_file    = st.file_uploader("CV / Resume (in English) — PDF or DOCX",
                                  type=["pdf", "docx", "doc"],
                                  key="cv_uploader")
    cert_files = st.file_uploader("Relevant Certificates — Degree or recognized teaching certificate in Spanish or education (PDF, PNG, or JPG)",
                                  type=["pdf", "png", "jpg", "jpeg"],
                                  accept_multiple_files=True,
                                  key="cert_uploader")
    photo_file = st.file_uploader("Professional Photo — PNG or JPG",
                                  type=["png", "jpg", "jpeg"],
                                  key="photo_uploader",
                                  help="Upload a clear, professional-looking photo of yourself.")

    # Status
    col1, col2, col3 = st.columns(3)
    with col1:
        if cv_file or st.session_state["cv_file"]:
            st.success("\u2705 CV uploaded")
        else:
            st.warning("\u274c CV not yet uploaded")
    with col2:
        n_certs = len(cert_files) if cert_files else len(st.session_state["cert_files"])
        if n_certs > 0:
            st.success(f"\u2705 {n_certs} certificate(s)")
        else:
            st.warning("\u274c No certificates")
    with col3:
        if photo_file or st.session_state.get("photo_file"):
            st.success("\u2705 Photo uploaded")
        else:
            st.warning("\u274c Photo missing")

    col_back, col_next = st.columns(2)
    with col_back:
        if st.button("\u2190 Back", use_container_width=True, key="back1"):
            go_to(0); st.rerun()
    with col_next:
        if st.button("Continue \u2192", type="primary", use_container_width=True, key="next1"):
            saved_cv    = cv_file if cv_file else st.session_state["cv_file"]
            saved_certs = cert_files if cert_files else st.session_state["cert_files"]
            saved_photo = photo_file if photo_file else st.session_state.get("photo_file")

            errors = []
            if saved_cv is None:          errors.append("CV / Resume is required.")
            if not saved_certs:           errors.append("At least one Teaching Certificate is required.")
            if saved_photo is None:       errors.append("Professional photo is required.")

            if errors:
                for e in errors: st.error(e)
            else:
                st.session_state["cv_file"]    = saved_cv
                st.session_state["cert_files"] = saved_certs
                st.session_state["photo_file"] = saved_photo
                go_to(2); st.rerun()

    show_save_button(1)


# ---------------------------------------------------------------------------
# Step 2 — Video Introduction
# ---------------------------------------------------------------------------

RECORDER_HTML = """
<div style="text-align:center;padding:1rem;border:1px solid #ddd;border-radius:12px;background:#fafafa;">
    <video id="preview" autoplay muted playsinline
           style="width:100%;max-width:480px;border-radius:8px;background:#000;min-height:200px;"></video>
    <div style="margin-top:1rem;">
        <button id="startBtn" onclick="startRec()"
                style="background:#c0392b;color:white;border:none;padding:10px 24px;border-radius:8px;font-size:1rem;cursor:pointer;margin:4px;">
            Start Recording</button>
        <button id="stopBtn" onclick="stopRec()" disabled
                style="background:#888;color:white;border:none;padding:10px 24px;border-radius:8px;font-size:1rem;cursor:pointer;margin:4px;">
            Stop Recording</button>
    </div>
    <div id="result" style="margin-top:1rem;display:none;">
        <p style="color:#27ae60;font-weight:700;">Recording complete!</p>
        <p>Click below to download, then upload the file using the uploader.</p>
        <a id="downloadLink" download="my_video.webm"
           style="display:inline-block;background:#27ae60;color:white;padding:10px 24px;border-radius:8px;text-decoration:none;font-weight:700;">
            Download Recording</a>
    </div>
</div>
<script>
let mr,chunks=[];
async function startRec(){
    try{
        const s=await navigator.mediaDevices.getUserMedia({video:true,audio:true});
        document.getElementById('preview').srcObject=s;
        mr=new MediaRecorder(s,{mimeType:'video/webm;codecs=vp8,opus'});
        chunks=[];
        mr.ondataavailable=e=>chunks.push(e.data);
        mr.onstop=()=>{
            const b=new Blob(chunks,{type:'video/webm'});
            const u=URL.createObjectURL(b);
            const a=document.getElementById('downloadLink');
            a.href=u;
            document.getElementById('result').style.display='block';
            s.getTracks().forEach(t=>t.stop());
            document.getElementById('preview').srcObject=null;
        };
        mr.start();
        document.getElementById('startBtn').disabled=true;
        document.getElementById('startBtn').style.background='#888';
        document.getElementById('stopBtn').disabled=false;
        document.getElementById('stopBtn').style.background='#c0392b';
        document.getElementById('result').style.display='none';
    }catch(e){
        alert('Camera access denied or not available. Please check your browser permissions.');
    }
}
function stopRec(){
    if(mr&&mr.state==='recording'){mr.stop();}
    document.getElementById('startBtn').disabled=false;
    document.getElementById('startBtn').style.background='#c0392b';
    document.getElementById('stopBtn').disabled=true;
    document.getElementById('stopBtn').style.background='#888';
}
</script>
"""


def render_step_2():
    show_header("Spanish Coach Application")
    show_step_pill(2)
    st.subheader("Step 2 — Video Introduction")

    st.markdown("""
    <div class="section-card">
    <p>Please provide a <strong>short video introduction (2–5 minutes)</strong> where you introduce yourself
    and describe your teaching approach — <strong>in both Spanish and English</strong>.</p>
    <p>You can upload videos, share a link, or record directly from your webcam.</p>
    <p><em>Make sure the video quality is good and there is no background noise, as we will use it to assess
    the quality of your online classes.</em></p>
    </div>
    """, unsafe_allow_html=True)

    video_mode = st.radio(
        "How would you like to share your video(s)?",
        options=[
            "Upload two separate videos (Spanish + English)",
            "Upload one combined video (Spanish & English in one)",
            "Share a video link",
            "Record from webcam",
        ],
        index=["Upload two separate videos (Spanish + English)",
               "Upload one combined video (Spanish & English in one)",
               "Share a video link",
               "Record from webcam"].index(
                   st.session_state["video_mode"]
                   if st.session_state["video_mode"] in [
                       "Upload two separate videos (Spanish + English)",
                       "Upload one combined video (Spanish & English in one)",
                       "Share a video link",
                       "Record from webcam",
                   ] else "Upload two separate videos (Spanish + English)"
               ),
        key="video_mode_radio",
    )
    st.session_state["video_mode"] = video_mode

    video_spanish = None
    video_english = None
    video_combined = None
    video_link = ""

    if video_mode == "Upload two separate videos (Spanish + English)":
        video_spanish = st.file_uploader("Video in Spanish (mp4, mov, avi, mkv, webm)",
                                         type=["mp4", "mov", "avi", "mkv", "webm"],
                                         key="video_es_uploader")
        video_english = st.file_uploader("Video in English (mp4, mov, avi, mkv, webm)",
                                         type=["mp4", "mov", "avi", "mkv", "webm"],
                                         key="video_en_uploader")
        st.markdown('<p class="file-note">Videos are large files. Upload may take a few minutes.</p>',
                    unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        with col1:
            if video_spanish or st.session_state["video_spanish"]:
                st.success("\u2705 Spanish video uploaded")
            else:
                st.warning("\u274c Spanish video missing")
        with col2:
            if video_english or st.session_state["video_english"]:
                st.success("\u2705 English video uploaded")
            else:
                st.warning("\u274c English video missing")

    elif video_mode == "Upload one combined video (Spanish & English in one)":
        video_combined = st.file_uploader("Combined video (Spanish & English) (mp4, mov, avi, mkv, webm)",
                                          type=["mp4", "mov", "avi", "mkv", "webm"],
                                          key="video_combined_uploader")
        st.markdown('<p class="file-note">Videos are large files. Upload may take a few minutes.</p>',
                    unsafe_allow_html=True)
        if video_combined or st.session_state["video_combined"]:
            st.success("\u2705 Combined video uploaded")
        else:
            st.warning("\u274c Combined video missing")

    elif video_mode == "Share a video link":
        video_link = st.text_input(
            "Paste your video link (YouTube, Google Drive, Loom, etc.)",
            value=st.session_state["video_link"],
            key="video_link_input",
        )
        st.markdown('<p class="file-note">Make sure the link is publicly accessible or set to "Anyone with the link can view".</p>',
                    unsafe_allow_html=True)
        if video_link.strip():
            st.success("\u2705 Video link provided")
        else:
            st.warning("\u274c Video link missing")

    else:  # Record from webcam
        st.markdown("**Record your video below**, then download it and upload using the file uploader.")
        import streamlit.components.v1 as components
        components.html(RECORDER_HTML, height=450)

        st.markdown("---")
        st.markdown("**Upload your recorded video here:**")
        video_combined = st.file_uploader("Upload recorded video (webm, mp4, mov)",
                                          type=["webm", "mp4", "mov", "avi", "mkv"],
                                          key="video_recorded_uploader")
        if video_combined or st.session_state["video_combined"]:
            st.success("\u2705 Recorded video uploaded")
        else:
            st.warning("\u274c No video uploaded yet")

    col_back, col_next = st.columns(2)
    with col_back:
        if st.button("\u2190 Back", use_container_width=True, key="back2"):
            go_to(1); st.rerun()
    with col_next:
        if st.button("Continue \u2192", type="primary", use_container_width=True, key="next2"):
            errors = []

            if video_mode == "Upload two separate videos (Spanish + English)":
                saved_es = video_spanish if video_spanish else st.session_state["video_spanish"]
                saved_en = video_english if video_english else st.session_state["video_english"]
                if saved_es is None: errors.append("Spanish introduction video is required.")
                if saved_en is None: errors.append("English introduction video is required.")
                if not errors:
                    st.session_state["video_spanish"] = saved_es
                    st.session_state["video_english"] = saved_en
                    st.session_state["video_combined"] = None
                    st.session_state["video_link"] = ""

            elif video_mode == "Upload one combined video (Spanish & English in one)":
                saved_comb = video_combined if video_combined else st.session_state["video_combined"]
                if saved_comb is None: errors.append("Combined video is required.")
                if not errors:
                    st.session_state["video_combined"] = saved_comb
                    st.session_state["video_spanish"] = None
                    st.session_state["video_english"] = None
                    st.session_state["video_link"] = ""

            elif video_mode == "Share a video link":
                if not video_link.strip(): errors.append("Video link is required.")
                if not errors:
                    st.session_state["video_link"] = video_link.strip()
                    st.session_state["video_spanish"] = None
                    st.session_state["video_english"] = None
                    st.session_state["video_combined"] = None

            else:  # Record from webcam
                saved_comb = video_combined if video_combined else st.session_state["video_combined"]
                if saved_comb is None: errors.append("Please record and upload your video.")
                if not errors:
                    st.session_state["video_combined"] = saved_comb
                    st.session_state["video_spanish"] = None
                    st.session_state["video_english"] = None
                    st.session_state["video_link"] = ""
                    st.session_state["video_mode"] = "Upload one combined video (Spanish & English in one)"

            if errors:
                for e in errors: st.error(e)
            else:
                go_to(3); st.rerun()

    show_save_button(2)


# ---------------------------------------------------------------------------
# Step 3 — Personal Information
# ---------------------------------------------------------------------------

def render_step_3():
    show_header("Spanish Coach Application")
    show_step_pill(3)
    st.subheader("Step 3 — Personal Information")

    with st.form("form_step3"):
        st.markdown('<div class="section-card">', unsafe_allow_html=True)

        col1, col2 = st.columns(2)
        with col1:
            first_name = st.text_input("First Name", value=st.session_state["first_name"])
        with col2:
            last_name = st.text_input("Last Name", value=st.session_state["last_name"])

        col3, col4 = st.columns(2)
        with col3:
            email = st.text_input("Email Address", value=st.session_state["email"])
        with col4:
            age = st.text_input("Age", value=str(st.session_state["age"]) if st.session_state["age"] else "",
                                placeholder="e.g. 28")

        col5, col6 = st.columns(2)
        with col5:
            mobile = st.text_input("Mobile Number", value=st.session_state["mobile"])
        with col6:
            whatsapp = st.text_input("WhatsApp Number", value=st.session_state["whatsapp"],
                                     help="We'll use this if we can't reach you by email")

        col7, col8 = st.columns(2)
        with col7:
            country_origin = st.text_input("Country of Origin",
                                           value=st.session_state["country_origin"])
        with col8:
            current_location = st.text_input("Current City & Country",
                                             value=st.session_state["current_location"])

        # Timezone dropdown
        tz_current = st.session_state["timezone"]
        tz_idx = 0
        if tz_current in TIMEZONE_OPTIONS:
            tz_idx = TIMEZONE_OPTIONS.index(tz_current)
        timezone = st.selectbox("Time zone in your current location", TIMEZONE_OPTIONS, index=tz_idx)

        address = st.text_area("Full Address (House No, Street, City, State/Province, Postal Code, Country)",
                               value=st.session_state["address"],
                               placeholder="House No, Street, City, State/Province, Postal Code, Country",
                               height=80)

        profile_link = st.text_input("Upwork / LinkedIn Profile Link",
                                     value=st.session_state["profile_link"])
        teaching_schedule = st.text_area("Preferred Teaching Schedule (Specify days, time and time zone)",
                                         value=st.session_state["teaching_schedule"],
                                         height=80)

        payment_pref = st.selectbox("Payment Preference",
                                    ["Upwork", "Wise", "Bank Transfer"],
                                    index=["Upwork", "Wise", "Bank Transfer"]
                                    .index(st.session_state["payment_pref"]
                                           if st.session_state["payment_pref"] in ["Upwork", "Wise", "Bank Transfer"]
                                           else "Upwork"))

        tax_info = st.text_area("Tax Information (Tax ID/Number, Registered Address, Phone Number)",
                                value=st.session_state["tax_info"],
                                placeholder="Example: Tax ID: RFC XXXX000000XX0, Address: 123 Main Street, Mexico City, Phone: +52 55 1234 5678",
                                height=80)

        st.markdown('</div>', unsafe_allow_html=True)

        submitted = st.form_submit_button("Continue \u2192", type="primary", use_container_width=True)

    if submitted:
        errors = []
        if not first_name.strip():       errors.append("First Name is required.")
        if not last_name.strip():        errors.append("Last Name is required.")
        if not valid_email(email):       errors.append("A valid Email Address is required.")
        if not mobile.strip():           errors.append("Mobile Number is required.")
        if not whatsapp.strip():         errors.append("WhatsApp Number is required.")
        if not country_origin.strip():   errors.append("Country of Origin is required.")
        if not current_location.strip(): errors.append("Current City & Country is required.")
        if not address.strip():          errors.append("Full Address is required.")
        if not timezone or timezone == "(Select your timezone)": errors.append("Time Zone is required.")
        if age.strip() and not age.strip().isdigit(): errors.append("Age must be a number.")
        if not age.strip(): errors.append("Age is required.")
        if not tax_info.strip():         errors.append("Tax Information is required.")
        if not teaching_schedule.strip(): errors.append("Preferred Teaching Schedule is required.")

        if errors:
            for e in errors:
                st.error(e)
        else:
            st.session_state.update({
                "first_name": first_name, "last_name": last_name,
                "email": email, "age": age,
                "mobile": mobile, "whatsapp": whatsapp,
                "country_origin": country_origin, "current_location": current_location,
                "address": address, "timezone": timezone,
                "profile_link": profile_link, "teaching_schedule": teaching_schedule,
                "payment_pref": payment_pref, "tax_info": tax_info,
            })
            go_to(4)
            st.rerun()

    if st.button("\u2190 Back", use_container_width=True, key="back3"):
        go_to(2); st.rerun()

    show_save_button(3)


# ---------------------------------------------------------------------------
# Step 4 — Professional Background
# ---------------------------------------------------------------------------

def render_step_4():
    show_header("Spanish Coach Application")
    show_step_pill(4)
    st.subheader("Step 4 — Professional Background")

    native_spanish = st.radio("1. Are you a native Spanish speaker?",
                              ["Yes", "No"],
                              index=["Yes","No"].index(st.session_state["native_spanish"]),
                              horizontal=True)

    spanish_type = st.text_area(
        "2. What type of Spanish do you specialize in? (e.g. Castilian, Latin American — please specify all the varieties you can teach, such as Mexican, Colombian, Argentinian, etc.)",
        value=st.session_state["spanish_type"],
        height=80)

    years_teaching = st.text_input("3. How many years have you been teaching Spanish?",
                                   value=str(st.session_state["years_teaching"]) if st.session_state["years_teaching"] else "",
                                   placeholder="e.g. 5")

    certifications = st.text_area(
        "4. What degrees or certifications do you hold in Spanish or language teaching? If none, list any other certifications you have.",
        value=st.session_state["certifications"],
        height=100)

    students_taught = st.text_area("5. How many students have you taught? Ages and proficiency levels?",
                                   value=st.session_state["students_taught"],
                                   height=80)

    all_levels_options = ["Yes", "No", "Some levels only"]
    current_all_levels = st.session_state["all_levels"]
    if current_all_levels not in all_levels_options:
        current_all_levels = "Yes"
    all_levels = st.radio("6. Can you teach all levels from A1 to C2?",
                          all_levels_options,
                          index=all_levels_options.index(current_all_levels),
                          horizontal=True)

    levels_detail = ""
    if all_levels == "Some levels only":
        levels_detail = st.text_input("Please specify which levels you can teach:",
                                      value=st.session_state["levels_detail"])

    st.markdown("---")
    st.markdown("**7. Share examples of testimonials or feedback from past students.**")
    st.markdown("Upload screenshots (PNG/JPG) or share a Google Drive / Dropbox link.")
    testimonial_files = st.file_uploader("Upload testimonial screenshots (PNG or JPG)",
                                         type=["png", "jpg", "jpeg"],
                                         accept_multiple_files=True,
                                         key="testimonial_uploader")
    testimonial_link = st.text_input("Or paste a link to your testimonials (Google Drive, Dropbox, etc.)",
                                     value=st.session_state["testimonial_link"])
    st.markdown("---")

    dele_exp = st.radio(
        "8. Do you have experience preparing students for official language proficiency exams such as the DELE?",
        ["Yes", "No"],
        index=["Yes","No"].index(st.session_state["dele_exp"]),
        horizontal=True)

    dele_detail = st.text_area(
        "9. If so, please specify the exam(s), levels, and the approach or materials you typically use to support students in reaching exam readiness.",
        value=st.session_state["dele_detail"],
        height=80)

    current_platforms = st.text_area(
        "10. Where do you currently teach Spanish online? Please share your profile link/s.",
        value=st.session_state["current_platforms"],
        height=80)

    col_back, col_next = st.columns(2)
    with col_back:
        if st.button("\u2190 Back", use_container_width=True, key="back4"):
            go_to(3); st.rerun()
    with col_next:
        if st.button("Continue \u2192", type="primary", use_container_width=True, key="next4"):
            errors = []
            if not spanish_type.strip():     errors.append("Please describe your type of Spanish.")
            if not str(years_teaching).strip(): errors.append("Years of teaching experience is required.")
            if not certifications.strip():   errors.append("Certifications field is required.")
            if not students_taught.strip():  errors.append("Students Taught field is required.")
            if not current_platforms.strip(): errors.append("Current Platforms field is required.")
            if all_levels == "Some levels only" and not levels_detail.strip():
                errors.append("Please specify which levels you can teach.")

            if errors:
                for e in errors: st.error(e)
            else:
                saved_testimonials = testimonial_files if testimonial_files else st.session_state["testimonial_files"]
                st.session_state.update({
                    "native_spanish": native_spanish, "spanish_type": spanish_type,
                    "years_teaching": years_teaching, "certifications": certifications,
                    "students_taught": students_taught, "all_levels": all_levels,
                    "levels_detail": levels_detail,
                    "testimonial_files": saved_testimonials,
                    "testimonial_link": testimonial_link,
                    "dele_exp": dele_exp, "dele_detail": dele_detail,
                    "current_platforms": current_platforms,
                })
                go_to(5); st.rerun()

    show_save_button(4)


# ---------------------------------------------------------------------------
# Dynamic step renderer for config-driven steps (5, 6, 7)
# ---------------------------------------------------------------------------

def render_dynamic_step(step_num: int):
    config = load_questions_config()
    step_cfg = config["steps"][str(step_num)] if config and str(step_num) in config.get("steps", {}) else None

    if step_cfg is None:
        _fallback = {5: _render_step_5_hardcoded, 6: _render_step_6_hardcoded, 7: _render_step_7_hardcoded}
        _fallback[step_num]()
        return

    prev_step = step_num - 1
    next_step = step_num + 1
    title = step_cfg["title"]
    questions = step_cfg["questions"]

    show_header("Spanish Coach Application")
    show_step_pill(step_num)
    st.subheader(f"Step {step_num} \u2014 {title}")

    with st.form(f"form_step{step_num}"):
        values = {}
        for q in questions:
            key = q["key"]
            label = q["label"]
            qtype = q.get("type", "textarea")
            help_text = q.get("help", None)

            if qtype == "textarea":
                values[key] = st.text_area(label, value=st.session_state.get(key, ""),
                                            height=q.get("height", 100), help=help_text)
            elif qtype == "text":
                values[key] = st.text_input(label, value=st.session_state.get(key, ""), help=help_text)
            elif qtype == "radio":
                options = q.get("options", ["Yes", "No"])
                current = st.session_state.get(key, options[0])
                idx = options.index(current) if current in options else 0
                values[key] = st.radio(label, options, index=idx, horizontal=True, help=help_text)
            elif qtype == "select":
                options = q.get("options", [])
                current = st.session_state.get(key, options[0] if options else "")
                idx = options.index(current) if current in options else 0
                values[key] = st.selectbox(label, options, index=idx, help=help_text)
            elif qtype == "multiselect":
                options = q.get("options", [])
                current = st.session_state.get(key, [])
                values[key] = st.multiselect(label, options,
                                              default=[s for s in current if s in options], help=help_text)
            elif qtype == "number":
                values[key] = st.number_input(label, min_value=q.get("min", 0),
                                               max_value=q.get("max", 100),
                                               value=st.session_state.get(key, 0), help=help_text)

        submitted = st.form_submit_button("Continue \u2192", type="primary", use_container_width=True)

    if submitted:
        required_fields = [q for q in questions if q.get("required")]
        text_fields = [q for q in required_fields if q.get("type", "textarea") in ("textarea", "text")]
        filled = sum(1 for q in text_fields if str(values.get(q["key"], "")).strip())
        total_text = len(text_fields) if text_fields else 1

        multiselect_ok = True
        for q in required_fields:
            if q.get("type") == "multiselect" and not values.get(q["key"]):
                multiselect_ok = False
                st.error(f"Please select at least one option for: {q['label']}")

        if filled < total_text:
            st.error("Please answer all questions in this section before proceeding.")
        elif not multiselect_ok:
            pass
        else:
            st.session_state.update(values)
            go_to(next_step); st.rerun()

    if st.button("\u2190 Back", use_container_width=True, key=f"back{step_num}"):
        go_to(prev_step); st.rerun()

    show_save_button(step_num)


# ---------------------------------------------------------------------------
# Hardcoded fallbacks for steps 5, 6, 7
# ---------------------------------------------------------------------------

def _render_step_5_hardcoded():
    show_header("Spanish Coach Application")
    show_step_pill(5)
    st.subheader("Step 5 \u2014 Teaching Philosophy, Engagement & Motivation")

    with st.form("form_step5"):
        assess_proficiency = st.text_area("1. How do you assess a student's proficiency in Spanish before starting lessons?",
                                          value=st.session_state["assess_proficiency"], height=100)
        tailor_lessons = st.text_area("2. How do you tailor your lessons to suit different learning styles and proficiency levels?",
                                      value=st.session_state["tailor_lessons"], height=100)
        successful_lesson = st.text_area("3. Can you give an example of a particularly successful lesson or course you've delivered? What made it effective?",
                                         value=st.session_state["successful_lesson"], height=100)
        engaging_online = st.text_area("4. How do you keep online lessons engaging and interactive for students?",
                                       value=st.session_state["engaging_online"], height=100)
        student_duration = st.text_area("5. How long do students typically stay with you, and what do you think contributes to student retention?",
                                         value=st.session_state["student_duration"], height=100)
        motivate_struggling = st.text_area("6. What strategies do you use to motivate students who are struggling or losing interest?",
                                           value=st.session_state["motivate_struggling"], height=100)
        enjoy_process = st.text_area("7. How do you ensure that students are not only learning effectively but also enjoying the process?",
                                     value=st.session_state["enjoy_process"], height=100)

        submitted = st.form_submit_button("Continue \u2192", type="primary", use_container_width=True)

    if submitted:
        fields = [assess_proficiency, tailor_lessons, successful_lesson,
                  engaging_online, student_duration, motivate_struggling, enjoy_process]
        filled = sum(1 for f in fields if str(f).strip())
        if filled < len(fields):
            st.error("Please answer all questions in this section before proceeding.")
        else:
            st.session_state.update({
                "assess_proficiency": assess_proficiency, "tailor_lessons": tailor_lessons,
                "successful_lesson": successful_lesson, "engaging_online": engaging_online,
                "student_duration": student_duration, "motivate_struggling": motivate_struggling,
                "enjoy_process": enjoy_process,
            })
            go_to(6); st.rerun()

    if st.button("\u2190 Back", use_container_width=True, key="back5"):
        go_to(4); st.rerun()

    show_save_button(5)


def _render_step_6_hardcoded():
    show_header("Spanish Coach Application")
    show_step_pill(6)
    st.subheader("Step 6 \u2014 Technology, Assessment & Adapting to Challenges")

    with st.form("form_step6"):
        multimedia = st.text_area("1. Do you incorporate multimedia resources or cultural content into your lessons? If yes, can you give examples?",
                                  value=st.session_state.get("multimedia_examples", "") or (st.session_state["multimedia"] if st.session_state["multimedia"] not in ["Yes","No","Sometimes"] else ""),
                                  height=100)

        tech_setup = st.text_area("2. Do you have a quality microphone, webcam, stable internet connection, and a quiet, well-lit workspace for conducting online classes?",
                                  value=st.session_state.get("tech_setup", "") if st.session_state.get("tech_setup","") not in ["Yes","No","Some but not all"] else "",
                                  height=80)

        software = st.text_area("3. Which software or platforms do you use for conducting online classes? (e.g., Zoom, Skype, Google Meet, or others)",
                                value=st.session_state.get("software_other", "") or (", ".join(st.session_state.get("software",[])) if isinstance(st.session_state.get("software"), list) else ""),
                                height=80)

        assess_progress = st.text_area("4. How do you assess your students' progress, and how often do you provide updates or evaluations?",
                                       value=st.session_state["assess_progress"], height=100)
        feedback_style  = st.text_area("5. How do you provide constructive and motivating feedback to your students?",
                                       value=st.session_state["feedback_style"], height=100)
        adapt_teaching  = st.text_area("6. Can you share an example of a time when you had to adapt your teaching approach to meet the needs of a particularly challenging student?",
                                       value=st.session_state["adapt_teaching"], height=100)
        cultural_lesson = st.text_area("7. Can you give an example of a cultural lesson or activity that you believe is essential for students learning Spanish?",
                                       value=st.session_state["cultural_lesson"], height=100)

        submitted = st.form_submit_button("Continue \u2192", type="primary", use_container_width=True)

    if submitted:
        text_fields = [multimedia, tech_setup, software, assess_progress, feedback_style, adapt_teaching, cultural_lesson]
        filled = sum(1 for f in text_fields if str(f).strip())
        if filled < len(text_fields):
            st.error("Please answer all questions in this section before proceeding.")
        else:
            st.session_state.update({
                "multimedia_examples": multimedia,
                "tech_setup": tech_setup,
                "software_other": software,
                "assess_progress": assess_progress,
                "feedback_style": feedback_style, "adapt_teaching": adapt_teaching,
                "cultural_lesson": cultural_lesson,
            })
            go_to(7); st.rerun()

    if st.button("\u2190 Back", use_container_width=True, key="back6"):
        go_to(5); st.rerun()

    show_save_button(6)


def _render_step_7_hardcoded():
    show_header("Spanish Coach Application")
    show_step_pill(7)
    st.subheader("Step 7 \u2014 Professional Development & Scenarios")

    with st.form("form_step7"):
        improve_skills   = st.text_area("1. What steps do you take to continuously improve your teaching skills and stay updated with new methodologies?",
                                        value=st.session_state["improve_skills"], height=100)
        excited_areas    = st.text_area("2. Are there any particular areas of Spanish language teaching that you are currently working on or excited to develop further?",
                                        value=st.session_state["excited_areas"], height=100)
        grammar_error    = st.text_area("3. A student consistently makes the same grammatical error despite corrections. How would you address this issue while keeping the student motivated?",
                                        value=st.session_state["grammar_error"], height=100)
        lesson_plan_levels = st.text_area("4. How would you structure a lesson plan for a complete beginner compared to an advanced student preparing for a certification exam?",
                                          value=st.session_state["lesson_plan_levels"], height=120)

        submitted = st.form_submit_button("Continue \u2192", type="primary", use_container_width=True)

    if submitted:
        fields = [improve_skills, excited_areas, grammar_error, lesson_plan_levels]
        filled = sum(1 for f in fields if f.strip())
        if filled < len(fields):
            st.error("Please answer all questions in this section before proceeding.")
        else:
            st.session_state.update({
                "improve_skills": improve_skills, "excited_areas": excited_areas,
                "grammar_error": grammar_error, "lesson_plan_levels": lesson_plan_levels,
            })
            go_to(8); st.rerun()

    if st.button("\u2190 Back", use_container_width=True, key="back7"):
        go_to(6); st.rerun()

    show_save_button(7)


# Wrapper functions for dynamic steps
def render_step_5():
    render_dynamic_step(5)

def render_step_6():
    render_dynamic_step(6)

def render_step_7():
    render_dynamic_step(7)


# ---------------------------------------------------------------------------
# Step 8 — Team, Communication & Rate
# ---------------------------------------------------------------------------

def render_step_8():
    show_header("Spanish Coach Application")
    show_step_pill(8)
    st.subheader("Step 8 \u2014 Team, Communication & Rate")

    with st.form("form_step8"):
        handle_criticism = st.text_area("1. How do you respond to constructive criticism from a supervisor?",
                                        value=st.session_state["handle_criticism"], height=100)
        teamwork         = st.text_area("2. How comfortable are you working closely with a team?",
                                        value=st.session_state["teamwork"], height=100)

        follow_process   = st.radio("3. Are you comfortable following a set process rather than always doing things your own way?",
                                    ["Yes", "No", "Somewhat"],
                                    index=["Yes","No","Somewhat"].index(st.session_state["follow_process"]),
                                    horizontal=True)

        first_session_win = st.text_area('4. In our program, the first session must give the student a "quick win"\u2014something they can apply right away. How would you do this in practice?',
                                         value=st.session_state["first_session_win"], height=100)

        session_notes_ok = st.radio("5. Are you comfortable with session notes and tracker updates immediately after each session?",
                                    ["Yes", "No"],
                                    index=["Yes","No"].index(st.session_state["session_notes_ok"]),
                                    horizontal=True)

        english_opts = ["Native", "Advanced/C1-C2", "Upper-Intermediate/B2", "Intermediate/B1", "Basic/A1-A2"]
        english_level = st.selectbox("6. What is your current English level?",
                                     english_opts,
                                     index=english_opts.index(st.session_state["english_level"]))

        ideal_rate     = st.text_input("7. What is your ideal hourly rate for this role? (in USD)",
                                       value=st.session_state["ideal_rate"],
                                       placeholder="e.g. $15/hr")

        st.markdown("---")
        st.markdown("**Please confirm all of the following to proceed:**")

        _confirm_opts = ["Yes", "No"]
        def _confirm_idx(key):
            v = st.session_state.get(key)
            if v is True: return 0
            if v is False: return 1
            return None

        st.markdown("Effective communication is key in this role. Our coaches are expected to respond to team emails and student messages within 24 hours on weekdays. Can you confirm if you're able to commit to this?")
        confirm_communication = st.radio("", _confirm_opts,
            index=_confirm_idx("confirm_communication"),
            horizontal=True, key="confirm_communication_radio")

        st.markdown("Payment Basis: Coaches are compensated only for completed online sessions. Onboarding, preparation, waiting periods, or unassigned time are not billable. Do you agree with this term?")
        confirm_payment = st.radio("", _confirm_opts,
            index=_confirm_idx("confirm_payment"),
            horizontal=True, key="confirm_payment_radio")

        st.markdown("Tax Responsibility: As a freelancer, you are responsible for your own tax obligations based on the laws in your country. Do you fully understand your tax obligations as a freelancer and agree to handle them independently?")
        confirm_taxes = st.radio("", _confirm_opts,
            index=_confirm_idx("confirm_taxes"),
            horizontal=True, key="confirm_taxes_radio")

        st.markdown("Part-time role & student assignments: This is a part-time position and should not be considered your primary source of income. Student assignments and volume depend on active enrollment, location, schedule compatibility, time zone and specific dialect preferences. While Lingohabit strives to provide and distribute students fairly and maintain a consistent rotation among coaches, assignment timing and volume cannot be guaranteed. There may be waiting periods between coach onboarding and first student assignment, which can range from several days to a few weeks. Payment begins only after the first confirmed session with an assigned student. Do you understand and agree to these terms?")
        confirm_parttime = st.radio("", _confirm_opts,
            index=_confirm_idx("confirm_parttime"),
            horizontal=True, key="confirm_parttime_radio")

        submitted = st.form_submit_button("Continue \u2192", type="primary", use_container_width=True)

    if submitted:
        errors = []
        text_fields = [handle_criticism, teamwork, first_session_win]
        filled = sum(1 for f in text_fields if f.strip())
        if filled < len(text_fields):
            errors.append("Please answer all questions in this section before proceeding.")
        if not ideal_rate.strip():
            errors.append("Ideal rate is required.")
        if confirm_communication is None:
            errors.append("Please select Yes or No for the communication commitment.")
        elif confirm_communication != "Yes":
            errors.append("You must select 'Yes' for the communication commitment to proceed.")
        if confirm_payment is None:
            errors.append("Please select Yes or No for the payment basis terms.")
        elif confirm_payment != "Yes":
            errors.append("You must select 'Yes' for the payment basis terms to proceed.")
        if confirm_taxes is None:
            errors.append("Please select Yes or No for the tax responsibility terms.")
        elif confirm_taxes != "Yes":
            errors.append("You must select 'Yes' for the tax responsibility terms to proceed.")
        if confirm_parttime is None:
            errors.append("Please select Yes or No for the part-time role & student assignment terms.")
        elif confirm_parttime != "Yes":
            errors.append("You must select 'Yes' for the part-time role & student assignment terms to proceed.")

        if errors:
            for e in errors: st.error(e)
        else:
            st.session_state.update({
                "handle_criticism": handle_criticism, "teamwork": teamwork,
                "follow_process": follow_process, "first_session_win": first_session_win,
                "session_notes_ok": session_notes_ok, "english_level": english_level,
                "ideal_rate": ideal_rate,
                "confirm_communication": confirm_communication == "Yes",
                "confirm_payment": confirm_payment == "Yes",
                "confirm_taxes": confirm_taxes == "Yes",
                "confirm_parttime": confirm_parttime == "Yes",
            })
            go_to(9); st.rerun()

    if st.button("\u2190 Back", use_container_width=True, key="back8"):
        go_to(7); st.rerun()

    show_save_button(8)


# ---------------------------------------------------------------------------
# Step 9 — Program Understanding Quiz
# ---------------------------------------------------------------------------

def render_step_9():
    show_header("Spanish Coach Application")
    show_step_pill(9)
    st.subheader("Step 9 \u2014 Program Understanding Quiz")

    st.markdown("""
    <div class="section-card">
    Before applying, you should have read our <em>Program and Expectations from Coach</em> document.
    Please answer the following questions to demonstrate your understanding. Be as detailed as possible.
    </div>
    """, unsafe_allow_html=True)

    st.link_button("Open Program Document (read before answering)",
                   "https://docs.google.com/document/d/1EUNTrNC03Px6TfjNM4m3FZWylldbk_SU1Ci8Vm7qc9w/edit?usp=sharing",
                   use_container_width=True)

    questions = [
        "1. What are the key commitments and promises we make to students enrolled in the program?",
        "2. What should a coach do upon receiving a student's study plan from the team?",
        "3. Describe what the 12-week study plan typically includes.",
        "4. What should coaches do with the study plan every 2\u20133 weeks?",
        "5. What are the weekly non-negotiable tasks assigned to students, and what is the coach's responsibility regarding these?",
        "6. When and how should the coach reach out to the student upon receiving their details from the team?",
        "7. How are you going to use the student details provided by the team (level, goals, interests, challenges) to prepare for your first session?",
        "8. What is the goal of the first session, and what should it NOT be focused entirely on?",
        "9. What is the purpose of the student profile sheet, and how often should it be updated?",
        "10. Explain the BAMFAM approach and how it should be applied in sessions.",
        "11. Who is responsible for checking and providing feedback on the student's essay exercises, and how should students submit their essays?",
        "12. What is the expected response time for coaches to reply to student or team messages on weekdays and weekends?",
    ]

    with st.form("form_step9"):
        answers = {}
        for i, q in enumerate(questions, start=1):
            answers[f"quiz_{i}"] = st.text_area(
                q,
                value=st.session_state.get(f"quiz_{i}", ""),
                height=100,
                key=f"quiz_input_{i}",
            )

        submitted = st.form_submit_button("Continue \u2192", type="primary", use_container_width=True)

    if submitted:
        missing_qs = [f"Question {i}" for i in range(1, 13)
                      if not answers.get(f"quiz_{i}", "").strip()]
        if missing_qs:
            st.error(f"Please answer all quiz questions. Missing: {', '.join(missing_qs)}")
        else:
            st.session_state.update(answers)
            go_to(10); st.rerun()

    if st.button("\u2190 Back", use_container_width=True, key="back9"):
        go_to(8); st.rerun()

    show_save_button(9)


# ---------------------------------------------------------------------------
# Step 10 — Review & Submit
# ---------------------------------------------------------------------------

def render_step_10():
    show_header("Spanish Coach Application")
    show_step_pill(10)
    st.subheader("Step 10 \u2014 Review & Submit")

    missing = check_completeness(st.session_state)
    full_name = get_full_name()

    st.markdown("### Personal Info")
    st.write(f"**Name:** {full_name}")
    st.write(f"**Email:** {st.session_state['email']}")
    st.write(f"**Country of Origin:** {st.session_state['country_origin']}")
    st.write(f"**Current Location:** {st.session_state['current_location']}")

    st.markdown("### Files Uploaded")
    cv_ok    = st.session_state["cv_file"] is not None
    cert_ok  = len(st.session_state["cert_files"]) > 0
    photo_ok = st.session_state.get("photo_file") is not None

    vmode = st.session_state.get("video_mode", "Upload two separate videos (Spanish + English)")
    if vmode == "Upload two separate videos (Spanish + English)":
        vid_ok = st.session_state["video_spanish"] is not None and st.session_state["video_english"] is not None
        vid_label = "Videos (Spanish + English)"
    elif vmode == "Upload one combined video (Spanish & English in one)":
        vid_ok = st.session_state["video_combined"] is not None
        vid_label = "Combined Video"
    else:
        vid_ok = bool(st.session_state.get("video_link", "").strip())
        vid_label = "Video Link"

    col1, col2 = st.columns(2)
    with col1:
        st.write("CV / Resume:", "\u2705" if cv_ok else "\u274c")
        st.write("Certificates:", f"\u2705 ({len(st.session_state['cert_files'])})" if cert_ok else "\u274c")
    with col2:
        st.write(f"{vid_label}:", "\u2705" if vid_ok else "\u274c")
        st.write("Photo:", "\u2705" if photo_ok else "\u274c")

    st.markdown("### Section Completion")
    sections = [
        ("Step 1 \u2013 Documents", cv_ok and cert_ok and photo_ok),
        ("Step 2 \u2013 Videos", vid_ok),
        ("Step 3 \u2013 Personal Info", bool(st.session_state["first_name"] and st.session_state["email"])),
        ("Step 4 \u2013 Background", bool(st.session_state["certifications"])),
        ("Step 5 \u2013 Philosophy", bool(st.session_state["assess_proficiency"])),
        ("Step 6 \u2013 Technology", bool(st.session_state["assess_progress"])),
        ("Step 7 \u2013 Development", bool(st.session_state["improve_skills"])),
        ("Step 8 \u2013 Team & Rate", bool(st.session_state["ideal_rate"])),
        ("Step 9 \u2013 Quiz", all(st.session_state.get(f"quiz_{i}", "").strip() for i in range(1, 13))),
    ]
    for label, done in sections:
        st.write(f"{'\u2705' if done else '\u274c'} {label}")

    if missing:
        items_html = "".join(f"<li>{m}</li>" for m in missing)
        st.markdown(f"""
        <div class="warn-box">
        <strong>Please complete the following before submitting:</strong>
        <ul>{items_html}</ul>
        </div>""", unsafe_allow_html=True)

        st.markdown("#### Jump to missing section:")
        step_map = {
            "Step 1": 1, "Step 2": 2, "Step 3": 3, "Step 4": 4,
            "Step 5": 5, "Step 6": 6, "Step 7": 7, "Step 8": 8, "Step 9": 9,
        }
        shown_steps = set()
        for m in missing:
            for label, snum in step_map.items():
                if label in m and snum not in shown_steps:
                    if st.button(f"Go to {label}", key=f"goto_{snum}"):
                        go_to(snum); st.rerun()
                    shown_steps.add(snum)

    else:
        st.success("\u2705 All required items are complete. You're ready to submit!")
        st.markdown("---")
        st.markdown("Once submitted, your application will be reviewed by our team. You will hear from us **within 5\u20137 business days**.")

        if st.button("Submit My Application", type="primary", use_container_width=True):
            run_submission()

    st.markdown("---")
    if st.button("\u2190 Back to Quiz", use_container_width=True, key="back10"):
        go_to(9); st.rerun()


# ---------------------------------------------------------------------------
# Submission pipeline
# ---------------------------------------------------------------------------

def run_submission():
    state = dict(st.session_state)
    full_name = f"{state['first_name']} {state['last_name']}".strip()

    progress_placeholder = st.empty()
    status_placeholder   = st.empty()

    def update_status(msg: str, pct: float):
        progress_placeholder.progress(pct)
        status_placeholder.info(msg)

    try:
        # 1. Save files
        update_status("Saving your files...", 0.1)
        folder = save_submission_files(state)

        # 2. Extract document text
        update_status("Processing documents...", 0.25)
        cv_text   = ""
        cert_texts = []
        if state["cv_file"] is not None:
            cv_text = extract_text_from_bytes(
                bytes(state["cv_file"].getbuffer()),
                state["cv_file"].name,
            )
        for cert in state["cert_files"]:
            t = extract_text_from_bytes(bytes(cert.getbuffer()), cert.name)
            if t:
                cert_texts.append(t)

        # 3. Claude analysis
        update_status("Running AI analysis (this may take 30\u201360 seconds)...", 0.45)
        analysis = {}
        try:
            analysis = run_claude_analysis(state, cv_text, cert_texts)
        except Exception as e:
            st.warning(f"AI analysis could not be completed: {e}. Proceeding without it.")
            analysis = {
                "coach_name": full_name,
                "upwork_link": state["profile_link"],
                "country_of_origin": state["country_origin"],
                "type_of_spanish": state["spanish_type"],
                "native_speaker": state["native_spanish"],
                "years_experience": str(state["years_teaching"]),
                "num_students_taught": state["students_taught"][:100],
                "can_teach_a1_c2": state["all_levels"],
                "certificates": state["certifications"][:200],
                "english_level": state["english_level"],
                "rate_per_hour": state["ideal_rate"],
                "availability_hours_per_week": "N/A",
                "payment_preference": state["payment_pref"],
                "teaching_methodology_summary": "Analysis unavailable.",
                "technology_setup": "Unknown",
                "quiz_performance": "Unknown",
                "quiz_notes": "Analysis unavailable.",
                "cv_summary": "Analysis unavailable.",
                "strengths": [],
                "concerns": ["AI analysis could not be completed."],
                "missing_elements": [],
                "overall_score": 0,
                "verdict": "NEEDS FURTHER REVIEW",
                "verdict_reason": "Manual review required \u2014 AI analysis failed.",
                "summary": "Application received. Manual review needed.",
                "recommended_action": "Review application manually.",
            }

        # 4. Upload files to hosting service
        drive_link = ""
        try:
            update_status("Uploading files (CV, certificates, videos)...", 0.60)
            drive_link = upload_files_to_hosting(folder, full_name)
        except Exception as e:
            st.warning(f"File upload failed: {e}. Files will be attached to email instead.")
            drive_link = ""

        # 5. Build file list and video info for email
        files_list = [f.name for f in [state["cv_file"]] if f]
        files_list += [f.name for f in state["cert_files"]]
        if state.get("photo_file"): files_list.append(state["photo_file"].name)
        for tf in state.get("testimonial_files", []):
            try: files_list.append(tf.name)
            except Exception: pass
        vmode = state.get("video_mode", "Upload two separate videos (Spanish + English)")
        video_info = ""
        if vmode == "Upload two separate videos (Spanish + English)":
            if state["video_spanish"]: files_list.append(state["video_spanish"].name)
            if state["video_english"]: files_list.append(state["video_english"].name)
            video_info = "Two separate videos uploaded (Spanish + English) \u2014 check the ZIP file."
        elif vmode == "Upload one combined video (Spanish & English in one)":
            if state["video_combined"]: files_list.append(state["video_combined"].name)
            video_info = "One combined video uploaded (Spanish & English) \u2014 check the ZIP file."
        else:
            link = state.get("video_link", "").strip()
            video_info = f'Video link shared by applicant: <a href="{link}">{link}</a>'
        files_list.append("submission_data.json")

        # 6. Build and send email
        update_status("Sending email to admin...", 0.80)
        html_body = build_email_html(analysis, folder, files_list, drive_link=drive_link, video_info=video_info)

        attach_paths = []
        if not drive_link:
            try:
                update_status("Creating ZIP of all files...", 0.75)
                zip_path = create_zip_of_folder(folder)
                zip_size_mb = zip_path.stat().st_size / (1024 * 1024)
                if zip_size_mb < 24:
                    attach_paths.append(zip_path)
                else:
                    st.warning(f"Files are too large for email ({zip_size_mb:.1f} MB). Only CV and certificates will be attached.")
                    if state["cv_file"]:
                        cv_ext = Path(state["cv_file"].name).suffix
                        attach_paths.append(folder / f"cv{cv_ext}")
                    for i in range(1, len(state["cert_files"]) + 1):
                        cert_ext = Path(state["cert_files"][i-1].name).suffix
                        attach_paths.append(folder / f"certificate_{i}{cert_ext}")
            except Exception:
                if state["cv_file"]:
                    cv_ext = Path(state["cv_file"].name).suffix
                    attach_paths.append(folder / f"cv{cv_ext}")
                for i in range(1, len(state["cert_files"]) + 1):
                    cert_ext = Path(state["cert_files"][i-1].name).suffix
                    attach_paths.append(folder / f"certificate_{i}{cert_ext}")

        email_sent = True
        email_error = ""
        try:
            send_email(analysis, html_body, folder, attach_paths)
        except Exception as e:
            email_sent = False
            email_error = str(e)

        # Send confirmation email to applicant
        try:
            send_applicant_confirmation(state["email"], full_name)
        except Exception:
            pass

        update_status("Submission complete!", 1.0)

        progress_placeholder.empty()
        status_placeholder.empty()

        st.session_state["submitted"] = True
        st.session_state["_success_name"]  = full_name
        st.session_state["_success_email"] = state["email"]
        st.session_state["_email_sent"]    = email_sent
        st.session_state["_email_error"]   = email_error

        go_to(-1)
        st.rerun()

    except Exception as e:
        progress_placeholder.empty()
        status_placeholder.empty()
        st.error(f"An unexpected error occurred during submission: {e}")
        st.code(traceback.format_exc())


# ---------------------------------------------------------------------------
# Success page
# ---------------------------------------------------------------------------

def render_success():
    name  = st.session_state.get("_success_name", "Coach")
    email = st.session_state.get("_success_email", "")
    email_sent = st.session_state.get("_email_sent", False)
    email_error = st.session_state.get("_email_error", "")

    st.markdown(f"""
    <div class="success-box">
        <h2>Application Submitted Successfully!</h2>
        <p style="font-size:1.1rem;">
            Thank you, <strong>{name}</strong>!<br>
            Your application has been received.<br>
            Our team will review it and get back to you within <strong>5\u20137 business days</strong>.
        </p>
        {"<p>A confirmation has been sent to <strong>" + email + "</strong></p>" if email and email_sent else ""}
    </div>
    """, unsafe_allow_html=True)

    if not email_sent and email_error:
        st.error(f"Email notification could not be sent: {email_error}")
        st.info("Your application was still saved. The team will review it manually.")

    st.markdown("")
    st.markdown("We look forward to potentially welcoming you to the My Daily Spanish coaching team.")

    if st.button("Start a new application"):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()


# ===========================================================================
# MAIN ROUTER
# ===========================================================================

def main():
    if not secrets_ok:
        st.markdown("""
        <div class="warn-box">
        <h3>Portal Not Configured Yet</h3>
        <p>The application portal has not been set up yet. Please contact the administrator to configure the portal secrets.</p>
        <p>If you are the administrator, edit <code>.streamlit/secrets.toml</code> with the required API keys and email credentials.</p>
        </div>
        """, unsafe_allow_html=True)
        return

    # Hide sidebar hamburger for applicants (non-admin)
    if not ADMIN_MODE:
        st.markdown("""
        <style>
        [data-testid="collapsedControl"] { display: none !important; }
        section[data-testid="stSidebar"] { display: none !important; }
        </style>
        """, unsafe_allow_html=True)

    # Admin-only sidebar
    if ADMIN_MODE:
        with st.sidebar:
            st.markdown("### Admin Panel")
            if QUESTIONS_CONFIG_URL:
                st.markdown(f"[Edit questions_config.json]({QUESTIONS_CONFIG_URL})")
            else:
                st.info("Set `questions_config_url` secret to enable question editing via GitHub.")
            st.markdown("""
**Editable steps:** 5, 6, 7 (via config)

**Supported question types:**
- `textarea` — Multi-line text
- `text` — Single line text
- `radio` — Radio buttons
- `select` — Dropdown list
- `multiselect` — Multi-select checkboxes
- `number` — Number input
            """)

    step = st.session_state.get("step", 0)

    if step == -1 or st.session_state.get("submitted"):
        render_success()
        return

    routers = {
        0:  render_step_0,
        1:  render_step_1,
        2:  render_step_2,
        3:  render_step_3,
        4:  render_step_4,
        5:  render_step_5,
        6:  render_step_6,
        7:  render_step_7,
        8:  render_step_8,
        9:  render_step_9,
        10: render_step_10,
    }

    renderer = routers.get(step, render_step_0)
    renderer()


if __name__ == "__main__":
    main()
