# =============================================================================
# Spanish Coach Application Portal — Talk in Spanish
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
    page_title="Spanish Coach Application — Talk in Spanish",
    page_icon="🇪🇸",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------------------------
# Brand CSS
# ---------------------------------------------------------------------------
st.markdown("""
<style>
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
    margin-bottom: 1rem;
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

/* Nav buttons row */
.nav-row { display: flex; gap: 0.75rem; margin-top: 1.5rem; }

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

# Google Drive config (optional — falls back to email attachments if not set)
# Google service account — supports both TOML section and one-line JSON string
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
    SUBMISSIONS_DIR = _local_dir          # Windows desktop
else:
    SUBMISSIONS_DIR = Path(_tf.mkdtemp())  # Cloud / Linux

secrets_ok = all([
    ANTHROPIC_KEY and ANTHROPIC_KEY != "YOUR_API_KEY_HERE",
    SENDER_EMAIL and SENDER_EMAIL != "YOUR_GMAIL_HERE",
    SENDER_PASSWORD and SENDER_PASSWORD != "YOUR_GMAIL_APP_PASSWORD_HERE",
])

# ---------------------------------------------------------------------------
# Session-state initialiser
# ---------------------------------------------------------------------------
DEFAULTS = {
    "step": 0,
    # Step 1 – Personal
    "full_name": "", "email": "", "age": 25, "mobile": "", "whatsapp": "",
    "country_origin": "", "current_location": "", "address": "",
    "timezone": "", "profile_link": "", "teaching_schedule": "",
    "payment_pref": "Upwork", "legal_status": "Freelancer", "tax_info": "",
    # Step 2 – Background
    "native_spanish": "Yes", "spanish_type": "", "years_teaching": 0,
    "certifications": "", "students_taught": "", "all_levels": "Yes",
    "levels_detail": "", "testimonials": "", "dele_exp": "No",
    "dele_detail": "", "current_platforms": "",
    # Step 3 – Philosophy
    "assess_proficiency": "", "tailor_lessons": "", "successful_lesson": "",
    "engaging_online": "", "student_duration": "", "motivate_struggling": "",
    "enjoy_process": "",
    # Step 4 – Technology
    "multimedia": "Yes", "multimedia_examples": "", "tech_setup": "Yes",
    "software": [], "software_other": "", "assess_progress": "",
    "feedback_style": "", "adapt_teaching": "", "cultural_lesson": "",
    # Step 5 – Development
    "improve_skills": "", "excited_areas": "", "grammar_error": "",
    "lesson_plan_levels": "",
    # Step 6 – Team / Rate
    "handle_criticism": "", "teamwork": "", "follow_process": "Yes",
    "first_session_win": "", "session_notes_ok": "Yes", "english_level": "Advanced/C1-C2",
    "respond_24h": "Yes", "ideal_rate": "", "hours_per_week": 10,
    "confirm_payment": False, "confirm_taxes": False, "confirm_parttime": False,
    # Step 7 – Documents
    "cv_file": None, "cert_files": [], "photo_link": "",
    # Step 8 – Videos
    "video_spanish": None, "video_english": None,
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
    """Map step 0-10 to 0.0-1.0 (step 0 = welcome = 0%)."""
    return max(0.0, min(1.0, step / 10.0))


def show_header(title: str, subtitle: str = ""):
    st.markdown(f"""
    <div class="portal-header">
        <h1>{title}</h1>
        {"<p>" + subtitle + "</p>" if subtitle else ""}
    </div>""", unsafe_allow_html=True)


def show_step_pill(step: int, total: int = 10):
    st.markdown(f'<div class="step-pill">Step {step} of {total}</div>', unsafe_allow_html=True)
    st.progress(progress_pct(step))


# ---------------------------------------------------------------------------
# File / document extraction helpers
# ---------------------------------------------------------------------------

def extract_text_from_bytes(file_bytes: bytes, filename: str) -> str:
    """Extract plain text from PDF or DOCX bytes. Returns empty string on failure."""
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
    """Save all uploaded files and JSON data to the submissions folder."""
    name_clean = re.sub(r"[^\w\s-]", "", state["full_name"]).strip().replace(" ", "_")
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

    # Videos
    if state["video_spanish"] is not None:
        vs_ext  = Path(state["video_spanish"].name).suffix
        vs_path = folder / f"video_spanish{vs_ext}"
        vs_path.write_bytes(state["video_spanish"].getbuffer())

    if state["video_english"] is not None:
        ve_ext  = Path(state["video_english"].name).suffix
        ve_path = folder / f"video_english{ve_ext}"
        ve_path.write_bytes(state["video_english"].getbuffer())

    # JSON data dump (all text answers)
    json_data = {k: v for k, v in state.items()
                 if k not in ("cv_file", "cert_files", "video_spanish", "video_english", "step", "submitted")}
    (folder / "submission_data.json").write_text(
        json.dumps(json_data, indent=2, default=str), encoding="utf-8"
    )

    return folder


# ---------------------------------------------------------------------------
# Google Drive upload (optional)
# ---------------------------------------------------------------------------

def _get_drive_service():
    """Build and return a Google Drive API service using service account credentials."""
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    creds_info = dict(st.secrets["google_service_account"])
    creds = service_account.Credentials.from_service_account_info(
        creds_info, scopes=["https://www.googleapis.com/auth/drive"]
    )
    return build("drive", "v3", credentials=creds)


def _get_or_create_root_folder(service) -> str:
    """Get the root 'Spanish Coach Applications' folder owned by the service account.
    Creates it if it doesn't exist, and shares it with the admin."""
    folder_name = "Spanish Coach Applications"

    # Check if we already created this folder
    results = service.files().list(
        q=f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false",
        pageSize=1, fields="files(id,name)"
    ).execute()
    files = results.get("files", [])

    if files:
        return files[0]["id"]

    # Create the folder (owned by service account)
    folder_meta = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder",
    }
    folder = service.files().create(body=folder_meta, fields="id").execute()
    folder_id = folder["id"]

    # Share with admin
    service.permissions().create(
        fileId=folder_id,
        body={"type": "user", "role": "writer", "emailAddress": ADMIN_EMAIL},
    ).execute()

    # Also share with anyone who has the link (for team access)
    service.permissions().create(
        fileId=folder_id,
        body={"type": "anyone", "role": "reader"},
    ).execute()

    return folder_id


def upload_to_google_drive(folder_path: Path, coach_name: str) -> str:
    """Upload all files from folder_path to Google Drive. Returns shareable folder URL."""
    from googleapiclient.http import MediaFileUpload

    service = _get_drive_service()

    # Get or create root folder (owned by service account, shared with admin)
    root_folder_id = _get_or_create_root_folder(service)

    # Create subfolder for this coach
    date_str = datetime.now().strftime("%Y-%m-%d")
    subfolder_meta = {
        "name": f"{coach_name} - {date_str}",
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [root_folder_id],
    }
    subfolder = service.files().create(body=subfolder_meta, fields="id").execute()
    subfolder_id = subfolder["id"]

    # Upload each file
    for file_path in folder_path.iterdir():
        if file_path.is_file():
            media = MediaFileUpload(str(file_path), resumable=True)
            file_meta = {"name": file_path.name, "parents": [subfolder_id]}
            service.files().create(body=file_meta, media_body=media, fields="id").execute()

    # Make subfolder viewable by anyone with link
    service.permissions().create(
        fileId=subfolder_id,
        body={"type": "anyone", "role": "reader"},
    ).execute()

    return f"https://drive.google.com/drive/folders/{subfolder_id}"


# ---------------------------------------------------------------------------
# ZIP + file hosting fallback (if Google Drive fails)
# ---------------------------------------------------------------------------

def create_zip_of_folder(folder_path: Path) -> Path:
    """Create a ZIP file of all files in the folder."""
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
    """Send full application data to Claude and return structured analysis JSON."""
    import anthropic

    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

    quiz_answers = "\n".join([
        f"Q{i}: {state.get(f'quiz_{i}', '')}" for i in range(1, 13)
    ])
    certs_combined = "\n\n".join(cert_texts) if cert_texts else "No certificate text extracted."

    prompt = f"""You are an expert hiring manager for Talk in Spanish, an online Spanish coaching platform.

Analyse the following Spanish coach application and return a JSON object with your assessment.

=== PERSONAL INFO ===
Name: {state['full_name']}
Email: {state['email']}
Age: {state['age']}
Country of Origin: {state['country_origin']}
Current Location: {state['current_location']}
Timezone: {state['timezone']}
Upwork/LinkedIn: {state['profile_link']}
Teaching Schedule: {state['teaching_schedule']}
Payment Preference: {state['payment_pref']}
Legal Status: {state['legal_status']}
Tax Info: {state['tax_info']}

=== PROFESSIONAL BACKGROUND ===
Native Spanish Speaker: {state['native_spanish']}
Type of Spanish: {state['spanish_type']}
Years Teaching: {state['years_teaching']}
Certifications: {state['certifications']}
Students Taught: {state['students_taught']}
Can Teach A1-C2: {state['all_levels']}
Level Details: {state['levels_detail']}
Testimonials: {state['testimonials']}
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
Respond 24h: {state['respond_24h']}
Ideal Rate: {state['ideal_rate']}
Hours Per Week: {state['hours_per_week']}

=== PROGRAM QUIZ ANSWERS ===
{quiz_answers}

=== CV TEXT ===
{cv_text if cv_text else "CV text could not be extracted."}

=== CERTIFICATE TEXT ===
{certs_combined}

=== PHOTO LINK ===
{state['photo_link']}

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
    # Strip any accidental markdown fences
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)

    return json.loads(raw)


# ---------------------------------------------------------------------------
# Email sender
# ---------------------------------------------------------------------------

def build_email_html(analysis: dict, folder: Path, files_list: list[str], drive_link: str = "") -> str:
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
    upwork_display = f'<a href="{upwork}">{upwork}</a>' if upwork else "—"

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
    <h1>🇪🇸 New Spanish Coach Application</h1>
    <p>Received: {datetime.now().strftime("%B %d, %Y at %H:%M")}</p>
  </div>
  <div class="body">

    <div style="text-align:center;padding:8px 0 16px;">
      <div class="verdict-badge">{verdict} — {score}/100</div>
    </div>

    <table>
      <tr><th>Coach Name</th><td>{analysis.get('coach_name','')}</td></tr>
      <tr><th>Upwork / LinkedIn</th><td>{upwork_display}</td></tr>
      <tr><th>Country of Origin</th><td>{analysis.get('country_of_origin','')}</td></tr>
      <tr><th>Type of Spanish</th><td>{analysis.get('type_of_spanish','')}</td></tr>
      <tr><th>Native Speaker</th><td>{analysis.get('native_speaker','')}</td></tr>
      <tr><th>Experience</th><td>{analysis.get('years_experience','')} years</td></tr>
      <tr><th>Students Taught</th><td>{analysis.get('num_students_taught','')}</td></tr>
      <tr><th>Teaches A1–C2</th><td>{analysis.get('can_teach_a1_c2','')}</td></tr>
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
    {"<p style='text-align:center;margin:12px 0 16px;'><a href='" + drive_link + "' style='display:inline-block;background:#c0392b;color:white;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:700;font-size:1rem;'>View All Files on Google Drive</a></p>" if drive_link else "<p>Location: <code>" + str(folder) + "</code></p>"}
    <ul>{files_items}</ul>

  </div>
  <div class="footer">
    This email was generated automatically by the Talk in Spanish Coach Portal.
    Please do not reply to this email.
  </div>
</div>
</body>
</html>
"""


def send_email(analysis: dict, html_body: str, folder: Path, attach_paths: list[Path]):
    """Send the analysis email with CV and certificate attachments."""
    msg = MIMEMultipart("mixed")
    msg["From"]    = SENDER_EMAIL
    msg["To"]      = ADMIN_EMAIL
    verdict        = analysis.get("verdict", "NEEDS FURTHER REVIEW")
    coach_name     = analysis.get("coach_name", "Unknown")
    msg["Subject"] = f"🇪🇸 New Spanish Coach Application — {coach_name} — {verdict}"

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
    """Send a simple confirmation email to the applicant."""
    msg = MIMEMultipart("alternative")
    msg["From"]    = SENDER_EMAIL
    msg["To"]      = applicant_email
    msg["Subject"] = "Your Spanish Coach Application \u2014 Received"

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;color:#333;margin:0;padding:20px;background:#f5f5f5;">
<div style="max-width:600px;margin:0 auto;background:white;border-radius:12px;overflow:hidden;box-shadow:0 2px 10px rgba(0,0,0,0.1);">
  <div style="background:linear-gradient(135deg,#c0392b,#922b21);color:white;padding:24px 28px;">
    <h1 style="margin:0;font-size:1.4rem;">Talk in Spanish</h1>
    <p style="margin:4px 0 0;opacity:0.9;">Coach Application Confirmation</p>
  </div>
  <div style="padding:24px 28px;">
    <p>Dear <strong>{applicant_name}</strong>,</p>
    <p>Thank you for submitting your application to become a Spanish coach with Talk in Spanish!</p>
    <p>We have received your application and all accompanying documents. Our team will review everything
    and get back to you within <strong>5\u20137 business days</strong>.</p>
    <p>If you have any questions in the meantime, please contact us at
    <a href="mailto:carmina@talkinfrench.com">carmina@talkinfrench.com</a>.</p>
    <p style="margin-top:24px;">Best regards,<br><strong>The Talk in Spanish Team</strong></p>
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
    """Return list of missing items (empty = all complete)."""
    missing = []

    # Step 1 checks
    if not state["full_name"].strip():     missing.append("Full Name (Step 1)")
    if not valid_email(state["email"]):    missing.append("Valid Email Address (Step 1)")
    if not state["mobile"].strip():        missing.append("Mobile Number (Step 1)")
    if not state["country_origin"].strip(): missing.append("Country of Origin (Step 1)")
    if not state["address"].strip():       missing.append("Full Address (Step 1)")
    if not state["timezone"].strip():      missing.append("Time Zone (Step 1)")

    # Step 2 checks
    if not state["certifications"].strip(): missing.append("Certifications (Step 2)")
    if not state["students_taught"].strip(): missing.append("Students Taught (Step 2)")

    # Step 7 checks
    if state["cv_file"] is None:           missing.append("CV / Resume (Step 7)")
    if not state["cert_files"]:            missing.append("At least one Teaching Certificate (Step 7)")
    if not state["photo_link"].strip():    missing.append("Photo Link (Step 7)")

    # Step 8 checks
    if state["video_spanish"] is None:     missing.append("Spanish Introduction Video (Step 8)")
    if state["video_english"] is None:     missing.append("English Introduction Video (Step 8)")

    # Step 9 quiz — all 12 required
    for i in range(1, 13):
        if not state.get(f"quiz_{i}", "").strip():
            missing.append(f"Quiz Answer {i} (Step 9)")

    # Step 6 confirmations
    if not state["confirm_payment"]:  missing.append("Confirmation: Payment-based role (Step 6)")
    if not state["confirm_taxes"]:    missing.append("Confirmation: Tax responsibility (Step 6)")
    if not state["confirm_parttime"]: missing.append("Confirmation: Part-time role (Step 6)")

    return missing


# ===========================================================================
# STEP RENDERERS
# ===========================================================================

def render_step_0():
    show_header("🇪🇸 Spanish Coach Application", "Talk in Spanish")

    st.markdown("""
    <div class="section-card">
    <h3 style="margin-top:0;">Welcome!</h3>
    <p>Apply to become a certified Spanish coach with our platform.<br>
    Complete all steps carefully — this usually takes <strong>20–30 minutes</strong>.</p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("### 📋 Before you begin, please have ready:")
    items = [
        ("✅", "CV (PDF or Word document)"),
        ("✅", "Teaching certificates (PDF)"),
        ("✅", "Short introduction video in Spanish"),
        ("✅", "Short introduction video in English"),
        ("✅", "Photo (link to Google Drive or Dropbox)"),
    ]
    for icon, label in items:
        st.markdown(f'<div class="check-item">{icon} {label}</div>', unsafe_allow_html=True)

    st.markdown("")
    if st.button("Start Application →", type="primary", use_container_width=True):
        go_to(1)
        st.rerun()


# ---------------------------------------------------------------------------

def render_step_1():
    show_header("🇪🇸 Spanish Coach Application")
    show_step_pill(1)
    st.subheader("Step 1 — Personal Information")

    with st.form("form_step1"):
        st.markdown('<div class="section-card">', unsafe_allow_html=True)

        col1, col2 = st.columns(2)
        with col1:
            full_name = st.text_input("Full Name *", value=st.session_state["full_name"])
            age       = st.number_input("Age *", min_value=18, max_value=80,
                                        value=st.session_state["age"])
            whatsapp  = st.text_input("WhatsApp Number *",
                                      value=st.session_state["whatsapp"],
                                      help="We'll use this if we can't reach you by email")
        with col2:
            email    = st.text_input("Email Address *", value=st.session_state["email"])
            mobile   = st.text_input("Mobile Number *", value=st.session_state["mobile"])
            timezone = st.text_input("Time Zone *", value=st.session_state["timezone"],
                                     placeholder="e.g. GMT+1, Europe/Paris")

        col3, col4 = st.columns(2)
        with col3:
            country_origin   = st.text_input("Country of Origin *",
                                             value=st.session_state["country_origin"])
        with col4:
            current_location = st.text_input("Current City & Country *",
                                             value=st.session_state["current_location"])

        address = st.text_area("Full Address *",
                               value=st.session_state["address"],
                               help="House No, Street, City, State, Postal Code, Country",
                               height=80)

        profile_link      = st.text_input("Upwork / LinkedIn Profile Link",
                                          value=st.session_state["profile_link"])
        teaching_schedule = st.text_area("Preferred Teaching Schedule",
                                         value=st.session_state["teaching_schedule"],
                                         help="Specify days, time and timezone",
                                         height=80)

        col5, col6 = st.columns(2)
        with col5:
            payment_pref = st.selectbox("Payment Preference *",
                                        ["Upwork", "Wise", "Wire Transfer", "Other"],
                                        index=["Upwork","Wise","Wire Transfer","Other"]
                                        .index(st.session_state["payment_pref"]))
        with col6:
            legal_status = st.selectbox("Legal Status *",
                                        ["Freelancer", "Company"],
                                        index=["Freelancer","Company"]
                                        .index(st.session_state["legal_status"]))

        tax_info = st.text_area("Tax Information *",
                                value=st.session_state["tax_info"],
                                help="Tax ID, Location, Phone Number — must be complete",
                                height=80)

        st.markdown('</div>', unsafe_allow_html=True)

        submitted = st.form_submit_button("Next →", type="primary", use_container_width=True)

    if submitted:
        errors = []
        if not full_name.strip():        errors.append("Full Name is required.")
        if not valid_email(email):       errors.append("A valid Email Address is required.")
        if not mobile.strip():           errors.append("Mobile Number is required.")
        if not whatsapp.strip():         errors.append("WhatsApp Number is required.")
        if not country_origin.strip():   errors.append("Country of Origin is required.")
        if not current_location.strip(): errors.append("Current City & Country is required.")
        if not address.strip():          errors.append("Full Address is required.")
        if not timezone.strip():         errors.append("Time Zone is required.")
        if not tax_info.strip():         errors.append("Tax Information is required.")

        if errors:
            for e in errors:
                st.error(e)
        else:
            st.session_state.update({
                "full_name": full_name, "email": email, "age": age,
                "mobile": mobile, "whatsapp": whatsapp,
                "country_origin": country_origin, "current_location": current_location,
                "address": address, "timezone": timezone,
                "profile_link": profile_link, "teaching_schedule": teaching_schedule,
                "payment_pref": payment_pref, "legal_status": legal_status,
                "tax_info": tax_info,
            })
            go_to(2)
            st.rerun()

    if st.button("← Back", key="back1"):
        go_to(0); st.rerun()


# ---------------------------------------------------------------------------

def render_step_2():
    show_header("🇪🇸 Spanish Coach Application")
    show_step_pill(2)
    st.subheader("Step 2 — Professional Background")

    with st.form("form_step2"):
        native_spanish = st.radio("1. Are you a native Spanish speaker? *",
                                  ["Yes", "No"],
                                  index=["Yes","No"].index(st.session_state["native_spanish"]),
                                  horizontal=True)

        spanish_type = st.text_area("2. What type of Spanish do you specialise in? *",
                                    value=st.session_state["spanish_type"],
                                    help="e.g. Castilian, Mexican, Colombian — describe your accent and regional variant",
                                    height=80)

        years_teaching = st.number_input("3. How many years have you been teaching Spanish? *",
                                         min_value=0, max_value=60,
                                         value=st.session_state["years_teaching"])

        certifications = st.text_area("4. What degrees or certifications do you hold? *",
                                      value=st.session_state["certifications"],
                                      height=100)

        students_taught = st.text_area("5. How many students have you taught? Ages and proficiency levels? *",
                                       value=st.session_state["students_taught"],
                                       height=80)

        all_levels = st.radio("6. Can you teach all levels from A1 to C2? *",
                              ["Yes", "No", "Some levels only"],
                              index=["Yes","No","Some levels only"].index(st.session_state["all_levels"]),
                              horizontal=True)

        levels_detail = st.text_input("7. If not all levels, which levels can you teach? (optional)",
                                      value=st.session_state["levels_detail"])

        testimonials = st.text_area("8. Share examples of testimonials or feedback from past students.",
                                    value=st.session_state["testimonials"],
                                    height=100)

        dele_exp = st.radio("9. Experience preparing students for DELE or similar exams? *",
                            ["Yes", "No"],
                            index=["Yes","No"].index(st.session_state["dele_exp"]),
                            horizontal=True)

        dele_detail = st.text_area("10. If yes, describe your exam preparation experience. (optional)",
                                   value=st.session_state["dele_detail"],
                                   height=80)

        current_platforms = st.text_area("11. Where do you currently teach Spanish online? *",
                                         value=st.session_state["current_platforms"],
                                         height=80)

        submitted = st.form_submit_button("Next →", type="primary", use_container_width=True)

    if submitted:
        errors = []
        if not spanish_type.strip():     errors.append("Please describe your type of Spanish.")
        if not certifications.strip():   errors.append("Certifications field is required.")
        if not students_taught.strip():  errors.append("Students Taught field is required.")
        if not current_platforms.strip(): errors.append("Current Platforms field is required.")

        if errors:
            for e in errors: st.error(e)
        else:
            st.session_state.update({
                "native_spanish": native_spanish, "spanish_type": spanish_type,
                "years_teaching": years_teaching, "certifications": certifications,
                "students_taught": students_taught, "all_levels": all_levels,
                "levels_detail": levels_detail, "testimonials": testimonials,
                "dele_exp": dele_exp, "dele_detail": dele_detail,
                "current_platforms": current_platforms,
            })
            go_to(3); st.rerun()

    if st.button("← Back", key="back2"):
        go_to(1); st.rerun()


# ---------------------------------------------------------------------------
# Dynamic step renderer for config-driven steps (3, 4, 5)
# ---------------------------------------------------------------------------

def render_dynamic_step(step_num: int):
    """Render a questionnaire step from questions_config.json."""
    config = load_questions_config()
    step_cfg = config["steps"][str(step_num)] if config else None

    if step_cfg is None:
        # Fallback to hardcoded renderers
        _fallback = {3: _render_step_3_hardcoded, 4: _render_step_4_hardcoded, 5: _render_step_5_hardcoded}
        _fallback[step_num]()
        return

    prev_step = step_num - 1
    next_step = step_num + 1
    title = step_cfg["title"]
    questions = step_cfg["questions"]

    show_header("\U0001f1ea\U0001f1f8 Spanish Coach Application")
    show_step_pill(step_num)
    st.subheader(f"Step {step_num} \u2014 {title}")

    with st.form(f"form_step{step_num}"):
        values = {}
        for q in questions:
            key = q["key"]
            label = q["label"] + (" *" if q.get("required") else "")
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
            elif qtype == "multiselect":
                options = q.get("options", [])
                current = st.session_state.get(key, [])
                values[key] = st.multiselect(label, options,
                                              default=[s for s in current if s in options], help=help_text)
            elif qtype == "number":
                values[key] = st.number_input(label, min_value=q.get("min", 0),
                                               max_value=q.get("max", 100),
                                               value=st.session_state.get(key, 0), help=help_text)

        submitted = st.form_submit_button("Next \u2192", type="primary", use_container_width=True)

    if submitted:
        # Count required text fields that are filled
        required_fields = [q for q in questions if q.get("required")]
        text_fields = [q for q in required_fields if q["type"] in ("textarea", "text")]
        filled = sum(1 for q in text_fields if str(values.get(q["key"], "")).strip())
        total_text = len(text_fields) if text_fields else 1

        # Check multiselect required fields
        multiselect_ok = True
        for q in required_fields:
            if q["type"] == "multiselect" and not values.get(q["key"]):
                multiselect_ok = False
                st.error(f"Please select at least one option for: {q['label']}")

        if filled / total_text < 0.70:
            st.error("Please complete at least 70% of the required fields in this section.")
        elif not multiselect_ok:
            pass  # error already shown
        else:
            st.session_state.update(values)
            go_to(next_step); st.rerun()

    if st.button("\u2190 Back", key=f"back{step_num}"):
        go_to(prev_step); st.rerun()


# ---------------------------------------------------------------------------

def _render_step_3_hardcoded():
    """Original hardcoded step 3 (fallback)."""
    show_header("\U0001f1ea\U0001f1f8 Spanish Coach Application")
    show_step_pill(3)
    st.subheader("Step 3 \u2014 Teaching Philosophy & Methods")

    with st.form("form_step3"):
        assess_proficiency = st.text_area("1. How do you assess a student's proficiency in Spanish? *",
                                          value=st.session_state["assess_proficiency"], height=100)
        tailor_lessons = st.text_area("2. How do you tailor lessons for different learning styles and levels? *",
                                      value=st.session_state["tailor_lessons"], height=100)
        successful_lesson = st.text_area("3. Give an example of a particularly successful lesson or course you've delivered. *",
                                         value=st.session_state["successful_lesson"], height=100)
        engaging_online = st.text_area("4. How do you keep online lessons engaging and interactive? *",
                                       value=st.session_state["engaging_online"], height=100)
        student_duration = st.text_input("5. How long do students typically stay with you? *",
                                         value=st.session_state["student_duration"])
        motivate_struggling = st.text_area("6. How do you motivate students who are struggling or losing interest? *",
                                           value=st.session_state["motivate_struggling"], height=100)
        enjoy_process = st.text_area("7. How do you ensure students are both learning and enjoying the process? *",
                                     value=st.session_state["enjoy_process"], height=100)

        submitted = st.form_submit_button("Next →", type="primary", use_container_width=True)

    if submitted:
        fields = [assess_proficiency, tailor_lessons, successful_lesson,
                  engaging_online, student_duration, motivate_struggling, enjoy_process]
        filled = sum(1 for f in fields if str(f).strip())
        if filled / len(fields) < 0.70:
            st.error("Please complete at least 70% of the fields in this section.")
        else:
            st.session_state.update({
                "assess_proficiency": assess_proficiency, "tailor_lessons": tailor_lessons,
                "successful_lesson": successful_lesson, "engaging_online": engaging_online,
                "student_duration": student_duration, "motivate_struggling": motivate_struggling,
                "enjoy_process": enjoy_process,
            })
            go_to(4); st.rerun()

    if st.button("← Back", key="back3"):
        go_to(2); st.rerun()


# ---------------------------------------------------------------------------

def _render_step_4_hardcoded():
    """Original hardcoded step 4 (fallback)."""
    show_header("🇪🇸 Spanish Coach Application")
    show_step_pill(4)
    st.subheader("Step 4 — Technology & Assessment")

    with st.form("form_step4"):
        multimedia = st.radio("1. Do you incorporate multimedia and cultural content into your lessons? *",
                              ["Yes", "No", "Sometimes"],
                              index=["Yes","No","Sometimes"].index(st.session_state["multimedia"]),
                              horizontal=True)
        multimedia_examples = st.text_area("2. If yes, give examples of multimedia/cultural content you use. (optional)",
                                           value=st.session_state["multimedia_examples"], height=80)

        tech_setup = st.radio("3. Do you have good microphone, webcam, stable internet, and quiet workspace? *",
                              ["Yes", "No", "Some but not all"],
                              index=["Yes","No","Some but not all"].index(st.session_state["tech_setup"]),
                              horizontal=True)

        sw_options = ["Zoom", "Skype", "Google Meet", "Teams", "Other"]
        software = st.multiselect("4. Which software do you use for online classes? *",
                                  sw_options,
                                  default=[s for s in st.session_state["software"] if s in sw_options])
        software_other = st.text_input("5. If 'Other', please specify: (optional)",
                                       value=st.session_state["software_other"])

        assess_progress = st.text_area("6. How do you assess students' progress, and how often? *",
                                       value=st.session_state["assess_progress"], height=100)
        feedback_style  = st.text_area("7. How do you provide constructive and motivating feedback? *",
                                       value=st.session_state["feedback_style"], height=100)
        adapt_teaching  = st.text_area("8. Share an example where you adapted your approach for a challenging student. *",
                                       value=st.session_state["adapt_teaching"], height=100)
        cultural_lesson = st.text_area("9. Give an example of a cultural lesson essential for Spanish learners. *",
                                       value=st.session_state["cultural_lesson"], height=100)

        submitted = st.form_submit_button("Next →", type="primary", use_container_width=True)

    if submitted:
        text_fields = [assess_progress, feedback_style, adapt_teaching, cultural_lesson]
        filled = sum(1 for f in text_fields if f.strip())
        if not software:
            st.error("Please select at least one teaching software.")
        elif filled / len(text_fields) < 0.70:
            st.error("Please complete at least 70% of the text fields.")
        else:
            st.session_state.update({
                "multimedia": multimedia, "multimedia_examples": multimedia_examples,
                "tech_setup": tech_setup, "software": software,
                "software_other": software_other, "assess_progress": assess_progress,
                "feedback_style": feedback_style, "adapt_teaching": adapt_teaching,
                "cultural_lesson": cultural_lesson,
            })
            go_to(5); st.rerun()

    if st.button("← Back", key="back4"):
        go_to(3); st.rerun()


# ---------------------------------------------------------------------------

def _render_step_5_hardcoded():
    """Original hardcoded step 5 (fallback)."""
    show_header("🇪🇸 Spanish Coach Application")
    show_step_pill(5)
    st.subheader("Step 5 — Professional Development & Scenarios")

    with st.form("form_step5"):
        improve_skills   = st.text_area("1. What steps do you take to continuously improve your teaching skills? *",
                                        value=st.session_state["improve_skills"], height=100)
        excited_areas    = st.text_area("2. Are there areas in Spanish teaching you're currently working on or excited to improve? *",
                                        value=st.session_state["excited_areas"], height=100)
        grammar_error    = st.text_area("3. A student consistently makes the same grammatical error. How would you address it? *",
                                        value=st.session_state["grammar_error"], height=100)
        lesson_plan_levels = st.text_area("4. How would you structure a lesson plan for a complete beginner vs. an advanced student? *",
                                          value=st.session_state["lesson_plan_levels"], height=120)

        submitted = st.form_submit_button("Next →", type="primary", use_container_width=True)

    if submitted:
        fields = [improve_skills, excited_areas, grammar_error, lesson_plan_levels]
        filled = sum(1 for f in fields if f.strip())
        if filled / len(fields) < 0.70:
            st.error("Please complete at least 70% of the fields in this section.")
        else:
            st.session_state.update({
                "improve_skills": improve_skills, "excited_areas": excited_areas,
                "grammar_error": grammar_error, "lesson_plan_levels": lesson_plan_levels,
            })
            go_to(6); st.rerun()

    if st.button("← Back", key="back5"):
        go_to(4); st.rerun()


# ---------------------------------------------------------------------------
# Wrapper functions for dynamic steps 3, 4, 5
# ---------------------------------------------------------------------------

def render_step_3():
    render_dynamic_step(3)

def render_step_4():
    render_dynamic_step(4)

def render_step_5():
    render_dynamic_step(5)


# ---------------------------------------------------------------------------

def render_step_6():
    show_header("🇪🇸 Spanish Coach Application")
    show_step_pill(6)
    st.subheader("Step 6 — Team, Communication & Rate")

    with st.form("form_step6"):
        handle_criticism = st.text_area("1. How do you respond to constructive criticism from a supervisor? *",
                                        value=st.session_state["handle_criticism"], height=100)
        teamwork         = st.text_area("2. How comfortable are you working closely with a team? *",
                                        value=st.session_state["teamwork"], height=100)

        follow_process   = st.radio("3. Are you comfortable following a set process rather than always doing things your own way? *",
                                    ["Yes", "No", "Somewhat"],
                                    index=["Yes","No","Somewhat"].index(st.session_state["follow_process"]),
                                    horizontal=True)

        first_session_win = st.text_area('4. How would you structure the first session to give the student a "quick win"? *',
                                         value=st.session_state["first_session_win"], height=100)

        session_notes_ok = st.radio("5. Are you comfortable with session notes and tracker updates immediately after each session? *",
                                    ["Yes", "No"],
                                    index=["Yes","No"].index(st.session_state["session_notes_ok"]),
                                    horizontal=True)

        english_opts = ["Native", "Advanced/C1-C2", "Upper-Intermediate/B2", "Intermediate/B1", "Basic/A1-A2"]
        english_level = st.selectbox("6. What is your current English level? *",
                                     english_opts,
                                     index=english_opts.index(st.session_state["english_level"]))

        respond_24h = st.radio("7. Can you commit to responding within 24h on weekdays and 48h on weekends? *",
                               ["Yes", "No"],
                               index=["Yes","No"].index(st.session_state["respond_24h"]),
                               horizontal=True)

        ideal_rate     = st.text_input("8. What is your ideal hourly rate for this role? *",
                                       value=st.session_state["ideal_rate"],
                                       placeholder="e.g. $15/hr")
        hours_per_week = st.number_input("9. How many hours per week can you dedicate? *",
                                         min_value=1, max_value=80,
                                         value=st.session_state["hours_per_week"])

        st.markdown("---")
        st.markdown("**Please confirm all of the following to proceed:**")
        confirm_payment  = st.checkbox("I understand this is a payment-based role and I will be compensated per session/hour",
                                       value=st.session_state["confirm_payment"])
        confirm_taxes    = st.checkbox("I understand I am responsible for my own taxes as a freelancer or independent contractor",
                                       value=st.session_state["confirm_taxes"])
        confirm_parttime = st.checkbox("I understand this is a part-time role and student assignments are based on availability and demand",
                                       value=st.session_state["confirm_parttime"])

        submitted = st.form_submit_button("Next →", type="primary", use_container_width=True)

    if submitted:
        errors = []
        text_fields = [handle_criticism, teamwork, first_session_win]
        filled = sum(1 for f in text_fields if f.strip())
        if filled / len(text_fields) < 0.70:
            errors.append("Please complete the text fields in this section.")
        if not ideal_rate.strip():
            errors.append("Ideal rate is required.")
        if not confirm_payment:
            errors.append("Please confirm the payment-based role acknowledgement.")
        if not confirm_taxes:
            errors.append("Please confirm the tax responsibility acknowledgement.")
        if not confirm_parttime:
            errors.append("Please confirm the part-time role acknowledgement.")

        if errors:
            for e in errors: st.error(e)
        else:
            st.session_state.update({
                "handle_criticism": handle_criticism, "teamwork": teamwork,
                "follow_process": follow_process, "first_session_win": first_session_win,
                "session_notes_ok": session_notes_ok, "english_level": english_level,
                "respond_24h": respond_24h, "ideal_rate": ideal_rate,
                "hours_per_week": hours_per_week, "confirm_payment": confirm_payment,
                "confirm_taxes": confirm_taxes, "confirm_parttime": confirm_parttime,
            })
            go_to(7); st.rerun()

    if st.button("← Back", key="back6"):
        go_to(5); st.rerun()


# ---------------------------------------------------------------------------

def render_step_7():
    show_header("🇪🇸 Spanish Coach Application")
    show_step_pill(7)
    st.subheader("Step 7 — Upload Documents")

    st.markdown("""
    <div class="section-card">
    <p>Please upload your documents below. Accepted formats are listed for each file.</p>
    </div>
    """, unsafe_allow_html=True)

    cv_file    = st.file_uploader("CV / Resume * (PDF or DOCX)",
                                  type=["pdf", "docx", "doc"],
                                  key="cv_uploader")
    cert_files = st.file_uploader("Teaching Certificates * (PDF — at least one required)",
                                  type=["pdf"],
                                  accept_multiple_files=True,
                                  key="cert_uploader")
    photo_link = st.text_input("Photo Link * (Google Drive or Dropbox)",
                               value=st.session_state["photo_link"],
                               help="Upload your photo to Google Drive or Dropbox, make it publicly viewable, and paste the link here. PNG preferred.")

    # Show current state
    col1, col2 = st.columns(2)
    with col1:
        if cv_file or st.session_state["cv_file"]:
            st.success("✅ CV uploaded")
        else:
            st.warning("❌ CV not yet uploaded")
    with col2:
        n_certs = len(cert_files) if cert_files else len(st.session_state["cert_files"])
        if n_certs > 0:
            st.success(f"✅ {n_certs} certificate(s) uploaded")
        else:
            st.warning("❌ No certificates uploaded yet")

    col_next, col_back = st.columns([3, 1])
    with col_next:
        if st.button("Next →", type="primary", use_container_width=True, key="next7"):
            # Persist uploads (fall back to previously saved if new not provided)
            saved_cv    = cv_file if cv_file else st.session_state["cv_file"]
            saved_certs = cert_files if cert_files else st.session_state["cert_files"]

            errors = []
            if saved_cv is None:          errors.append("CV / Resume is required.")
            if not saved_certs:           errors.append("At least one Teaching Certificate is required.")
            if not photo_link.strip():    errors.append("Photo link is required.")

            if errors:
                for e in errors: st.error(e)
            else:
                st.session_state["cv_file"]    = saved_cv
                st.session_state["cert_files"] = saved_certs
                st.session_state["photo_link"] = photo_link
                go_to(8); st.rerun()
    with col_back:
        if st.button("← Back", key="back7"):
            go_to(6); st.rerun()


# ---------------------------------------------------------------------------

def render_step_8():
    show_header("🇪🇸 Spanish Coach Application")
    show_step_pill(8)
    st.subheader("🎥 Step 8 — Video Introduction")

    st.markdown("""
    <div class="section-card">
    <p>Please upload <strong>two short video introductions (2–5 minutes each)</strong>:</p>
    <ul>
        <li><strong>Video 1 — In SPANISH:</strong> Introduce yourself and describe your teaching approach in Spanish.</li>
        <li><strong>Video 2 — In ENGLISH:</strong> Same introduction in English.</li>
    </ul>
    <p><em>Make sure the video quality is good and there is no background noise, as we will use it to assess the quality of your online classes.</em></p>
    </div>
    """, unsafe_allow_html=True)

    video_spanish = st.file_uploader("Video in Spanish * (mp4, mov, avi, mkv, webm)",
                                     type=["mp4", "mov", "avi", "mkv", "webm"],
                                     key="video_es_uploader")
    video_english = st.file_uploader("Video in English * (mp4, mov, avi, mkv, webm)",
                                     type=["mp4", "mov", "avi", "mkv", "webm"],
                                     key="video_en_uploader")

    st.markdown('<p class="file-note">📌 Videos are large files. Upload may take a few minutes depending on your connection.</p>',
                unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        if video_spanish or st.session_state["video_spanish"]:
            st.success("✅ Spanish video uploaded")
        else:
            st.warning("❌ Spanish video missing")
    with col2:
        if video_english or st.session_state["video_english"]:
            st.success("✅ English video uploaded")
        else:
            st.warning("❌ English video missing")

    col_next, col_back = st.columns([3, 1])
    with col_next:
        if st.button("Next →", type="primary", use_container_width=True, key="next8"):
            saved_es = video_spanish if video_spanish else st.session_state["video_spanish"]
            saved_en = video_english if video_english else st.session_state["video_english"]

            errors = []
            if saved_es is None: errors.append("Spanish introduction video is required.")
            if saved_en is None: errors.append("English introduction video is required.")

            if errors:
                for e in errors: st.error(e)
            else:
                st.session_state["video_spanish"] = saved_es
                st.session_state["video_english"] = saved_en
                go_to(9); st.rerun()
    with col_back:
        if st.button("← Back", key="back8"):
            go_to(7); st.rerun()


# ---------------------------------------------------------------------------

def render_step_9():
    show_header("🇪🇸 Spanish Coach Application")
    show_step_pill(9)
    st.subheader("📚 Step 9 — Program Understanding Quiz")

    st.markdown("""
    <div class="section-card">
    Before applying, you should have read our <em>Program and Expectations from Coach</em> document.
    Please answer the following questions to demonstrate your understanding. Be as detailed as possible.
    </div>
    """, unsafe_allow_html=True)

    st.link_button("📖 Open Program Document (read before answering)",
                   "https://docs.google.com/document/d/1EUNTrNC03Px6TfjNM4m3FZWylldbk_SU1Ci8Vm7qc9w/edit?usp=sharing",
                   use_container_width=True)

    questions = [
        "1. What are the key commitments and promises we make to students enrolled in the program?",
        "2. What should a coach do upon receiving a student's study plan from the team?",
        "3. Describe what the 12-week study plan typically includes.",
        "4. What should coaches do with the study plan every 2–3 weeks?",
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
                q + " *",
                value=st.session_state.get(f"quiz_{i}", ""),
                height=100,
                key=f"quiz_input_{i}",
            )

        submitted = st.form_submit_button("Next →", type="primary", use_container_width=True)

    if submitted:
        missing_qs = [f"Question {i}" for i in range(1, 13)
                      if not answers.get(f"quiz_{i}", "").strip()]
        if missing_qs:
            st.error(f"Please answer all quiz questions. Missing: {', '.join(missing_qs)}")
        else:
            st.session_state.update(answers)
            go_to(10); st.rerun()

    if st.button("← Back", key="back9"):
        go_to(8); st.rerun()


# ---------------------------------------------------------------------------

def render_step_10():
    show_header("🇪🇸 Spanish Coach Application")
    show_step_pill(10)
    st.subheader("Step 10 — Review & Submit")

    missing = check_completeness(st.session_state)

    # Summary table
    st.markdown("### 👤 Personal Info")
    st.write(f"**Name:** {st.session_state['full_name']}")
    st.write(f"**Email:** {st.session_state['email']}")
    st.write(f"**Country of Origin:** {st.session_state['country_origin']}")
    st.write(f"**Current Location:** {st.session_state['current_location']}")

    st.markdown("### 📎 Files Uploaded")
    cv_ok    = st.session_state["cv_file"] is not None
    cert_ok  = len(st.session_state["cert_files"]) > 0
    vid_es   = st.session_state["video_spanish"] is not None
    vid_en   = st.session_state["video_english"] is not None
    photo_ok = bool(st.session_state["photo_link"].strip())

    col1, col2, col3 = st.columns(3)
    with col1:
        st.write("CV / Resume:", "✅" if cv_ok else "❌")
        st.write("Certificates:", f"✅ ({len(st.session_state['cert_files'])})" if cert_ok else "❌")
    with col2:
        st.write("Spanish Video:", "✅" if vid_es else "❌")
        st.write("English Video:", "✅" if vid_en else "❌")
    with col3:
        st.write("Photo Link:", "✅" if photo_ok else "❌")

    st.markdown("### 📋 Section Completion")
    sections = [
        ("Step 1 – Personal Info", bool(st.session_state["full_name"] and st.session_state["email"])),
        ("Step 2 – Background", bool(st.session_state["certifications"])),
        ("Step 3 – Philosophy", bool(st.session_state["assess_proficiency"])),
        ("Step 4 – Technology", bool(st.session_state["assess_progress"])),
        ("Step 5 – Development", bool(st.session_state["improve_skills"])),
        ("Step 6 – Team & Rate", bool(st.session_state["ideal_rate"])),
        ("Step 7 – Documents", cv_ok and cert_ok and photo_ok),
        ("Step 8 – Videos", vid_es and vid_en),
        ("Step 9 – Quiz", all(st.session_state.get(f"quiz_{i}", "").strip() for i in range(1, 13))),
    ]
    for label, done in sections:
        st.write(f"{'✅' if done else '❌'} {label}")

    # Missing items
    if missing:
        items_html = "".join(f"<li>{m}</li>" for m in missing)
        st.markdown(f"""
        <div class="warn-box">
        <strong>⚠️ Please complete the following before submitting:</strong>
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
        st.success("✅ All required items are complete. You're ready to submit!")
        st.markdown("---")
        st.markdown("Once submitted, your application will be reviewed by our team. You will hear from us **within 5–7 business days**.")

        if st.button("🚀 Submit My Application", type="primary", use_container_width=True):
            run_submission()

    st.markdown("---")
    if st.button("← Back to Quiz", key="back10"):
        go_to(9); st.rerun()


# ---------------------------------------------------------------------------
# Submission pipeline
# ---------------------------------------------------------------------------

def run_submission():
    state = dict(st.session_state)

    progress_placeholder = st.empty()
    status_placeholder   = st.empty()

    def update_status(msg: str, pct: float):
        progress_placeholder.progress(pct)
        status_placeholder.info(msg)

    try:
        # 1. Save files
        update_status("💾 Saving your files...", 0.1)
        folder = save_submission_files(state)

        # 2. Extract document text
        update_status("📄 Processing documents...", 0.25)
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
        update_status("🤖 Running AI analysis (this may take 30–60 seconds)...", 0.45)
        analysis = {}
        try:
            analysis = run_claude_analysis(state, cv_text, cert_texts)
        except Exception as e:
            st.warning(f"⚠️ AI analysis could not be completed: {e}. Proceeding without it.")
            analysis = {
                "coach_name": state["full_name"],
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
                "availability_hours_per_week": str(state["hours_per_week"]),
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
                "verdict_reason": "Manual review required — AI analysis failed.",
                "summary": "Application received. Manual review needed.",
                "recommended_action": "Review application manually.",
            }

        # 4. Upload to Google Drive (if configured)
        drive_link = ""
        drive_configured = False
        try:
            _test = st.secrets["google_service_account"]
            drive_configured = bool(GOOGLE_DRIVE_FOLDER)
        except Exception:
            pass

        if drive_configured:
            try:
                update_status("☁️ Uploading files to Google Drive...", 0.60)
                drive_link = upload_to_google_drive(folder, state["full_name"])
            except Exception as e:
                st.warning(f"⚠️ Google Drive upload failed: {e}")
                st.code(traceback.format_exc())
                drive_link = ""

        # 5. Build file list for email
        files_list = [f.name for f in [state["cv_file"]] if f]
        files_list += [f.name for f in state["cert_files"]]
        if state["video_spanish"]: files_list.append(state["video_spanish"].name)
        if state["video_english"]: files_list.append(state["video_english"].name)
        files_list.append("submission_data.json")

        # 6. Build and send email
        update_status("📧 Sending email to admin...", 0.80)
        html_body = build_email_html(analysis, folder, files_list, drive_link=drive_link)

        # Attachments: if Drive succeeded, no attachments. Otherwise attach ZIP of ALL files.
        attach_paths = []
        if not drive_link:
            try:
                update_status("📦 Creating ZIP of all files...", 0.75)
                zip_path = create_zip_of_folder(folder)
                # Gmail limit is ~25MB. If ZIP is under 24MB, attach it.
                zip_size_mb = zip_path.stat().st_size / (1024 * 1024)
                if zip_size_mb < 24:
                    attach_paths.append(zip_path)
                else:
                    # Too large for email — attach CV/certs only, note about videos
                    st.warning(f"⚠️ Files are too large for email ({zip_size_mb:.1f} MB). Only CV and certificates will be attached.")
                    if state["cv_file"]:
                        cv_ext = Path(state["cv_file"].name).suffix
                        attach_paths.append(folder / f"cv{cv_ext}")
                    for i in range(1, len(state["cert_files"]) + 1):
                        cert_ext = Path(state["cert_files"][i-1].name).suffix
                        attach_paths.append(folder / f"certificate_{i}{cert_ext}")
            except Exception:
                # Fallback: attach CV + certs only
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

        # Send confirmation email to applicant (non-blocking)
        try:
            send_applicant_confirmation(state["email"], state["full_name"])
        except Exception:
            pass  # Don't block submission if applicant email fails

        update_status("✅ Submission complete!", 1.0)

        # 6. Show success page
        progress_placeholder.empty()
        status_placeholder.empty()

        st.session_state["submitted"] = True
        st.session_state["_success_name"]  = state["full_name"]
        st.session_state["_success_email"] = state["email"]
        st.session_state["_email_sent"]    = email_sent
        st.session_state["_email_error"]   = email_error

        # Reset step to trigger success render
        go_to(-1)
        st.rerun()

    except Exception as e:
        progress_placeholder.empty()
        status_placeholder.empty()
        st.error(f"An unexpected error occurred during submission: {e}")
        st.code(traceback.format_exc())


# ---------------------------------------------------------------------------

def render_success():
    name  = st.session_state.get("_success_name", "Coach")
    email = st.session_state.get("_success_email", "")
    email_sent = st.session_state.get("_email_sent", False)
    email_error = st.session_state.get("_email_error", "")

    st.markdown(f"""
    <div class="success-box">
        <h2>✅ Application Submitted Successfully!</h2>
        <p style="font-size:1.1rem;">
            Thank you, <strong>{name}</strong>!<br>
            Your application has been received.<br>
            Our team will review it and get back to you within <strong>5–7 business days</strong>.
        </p>
        {"<p>📧 A confirmation has been sent to <strong>" + email + "</strong></p>" if email and email_sent else ""}
    </div>
    """, unsafe_allow_html=True)

    if not email_sent and email_error:
        st.error(f"⚠️ Email notification could not be sent: {email_error}")
        st.info("Your application was still saved. The team will review it manually.")

    st.markdown("")
    st.markdown("We look forward to potentially welcoming you to the Talk in Spanish coaching team. 🇪🇸")

    if st.button("↩ Start a new application"):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()


# ===========================================================================
# MAIN ROUTER
# ===========================================================================

def main():
    # Check secrets are configured
    if not secrets_ok:
        st.markdown("""
        <div class="warn-box">
        <h3>⚠️ Portal Not Configured Yet</h3>
        <p>The application portal has not been set up yet. Please contact the administrator to configure the portal secrets.</p>
        <p>If you are the administrator, edit <code>.streamlit/secrets.toml</code> with the required API keys and email credentials.</p>
        </div>
        """, unsafe_allow_html=True)
        return

    # Admin sidebar
    if ADMIN_MODE:
        with st.sidebar:
            st.markdown("### Admin Tools")
            config_url = QUESTIONS_CONFIG_URL if QUESTIONS_CONFIG_URL else "Not configured"
            st.markdown(f"**Edit questions:** [questions_config.json]({config_url})" if QUESTIONS_CONFIG_URL else "**Edit questions:** Set `questions_config_url` secret to a GitHub raw URL")

            st.markdown("---")
            if st.button("🧪 Test Google Drive Connection"):
                try:
                    sa = dict(st.secrets["google_service_account"])
                    st.success(f"✅ Secrets loaded. Keys: {list(sa.keys())}")
                    st.info(f"client_email: {sa.get('client_email','MISSING')}")
                    st.info(f"private_key starts: {sa.get('private_key','')[:30]}...")
                    st.info(f"Folder ID: {GOOGLE_DRIVE_FOLDER}")

                    from google.oauth2 import service_account
                    from googleapiclient.discovery import build
                    creds = service_account.Credentials.from_service_account_info(
                        sa, scopes=["https://www.googleapis.com/auth/drive"]
                    )
                    service = build("drive", "v3", credentials=creds)

                    # Try listing files in the target folder
                    results = service.files().list(
                        q=f"'{GOOGLE_DRIVE_FOLDER}' in parents",
                        pageSize=5, fields="files(id,name)"
                    ).execute()
                    st.success(f"✅ Google Drive connected! Files in folder: {len(results.get('files', []))}")
                except KeyError as e:
                    st.error(f"❌ Secret missing: {e}")
                except Exception as e:
                    st.error(f"❌ Google Drive error: {e}")
                    st.code(traceback.format_exc())

    step = st.session_state.get("step", 0)

    # Success page
    if step == -1 or st.session_state.get("submitted"):
        render_success()
        return

    # Step routing
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
