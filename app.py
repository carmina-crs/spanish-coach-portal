import streamlit as st
import os
import json
import re
import csv
from pathlib import Path
from datetime import datetime
import anthropic
import pdfplumber
from docx import Document
import pandas as pd
import base64

# ─── Page Config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Coach Hiring Assistant",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Custom CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .main-header {
        background: linear-gradient(135deg, #1e3a5f 0%, #2d6a4f 100%);
        padding: 2rem;
        border-radius: 12px;
        color: white;
        margin-bottom: 2rem;
        text-align: center;
    }
    .score-card {
        background: white;
        border-radius: 12px;
        padding: 1.5rem;
        box-shadow: 0 2px 12px rgba(0,0,0,0.08);
        margin-bottom: 1rem;
        border-left: 5px solid #2d6a4f;
    }
    .hire-badge {
        background: #d4edda;
        color: #155724;
        padding: 0.5rem 1.5rem;
        border-radius: 25px;
        font-size: 1.3rem;
        font-weight: bold;
        display: inline-block;
    }
    .consider-badge {
        background: #fff3cd;
        color: #856404;
        padding: 0.5rem 1.5rem;
        border-radius: 25px;
        font-size: 1.3rem;
        font-weight: bold;
        display: inline-block;
    }
    .nohire-badge {
        background: #f8d7da;
        color: #721c24;
        padding: 0.5rem 1.5rem;
        border-radius: 25px;
        font-size: 1.3rem;
        font-weight: bold;
        display: inline-block;
    }
    .profile-card {
        background: #f8f9fa;
        border-radius: 12px;
        padding: 1.5rem;
        margin-bottom: 1.5rem;
        border: 1px solid #dee2e6;
    }
    .profile-row {
        display: flex;
        flex-wrap: wrap;
        gap: 1rem;
        margin-bottom: 0.5rem;
    }
    .profile-item {
        background: white;
        border-radius: 8px;
        padding: 0.6rem 1rem;
        border: 1px solid #e0e0e0;
        min-width: 160px;
        flex: 1;
    }
    .profile-label {
        font-size: 0.75rem;
        color: #888;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .profile-value {
        font-size: 1rem;
        color: #1e3a5f;
        font-weight: 700;
        margin-top: 2px;
    }
    .yes-tag { color: #155724; }
    .no-tag { color: #721c24; }
    .partial-tag { color: #856404; }
    .score-card { border-left: 5px solid #2d6a4f; }
    .section-title {
        font-size: 1.1rem;
        font-weight: 600;
        color: #1e3a5f;
        border-bottom: 2px solid #e0e0e0;
        padding-bottom: 0.4rem;
        margin-bottom: 0.8rem;
    }
    .stProgress > div > div > div > div {
        background-color: #2d6a4f;
    }
</style>
""", unsafe_allow_html=True)

# ─── Constants ─────────────────────────────────────────────────────────────────
LOG_FILE = Path(__file__).parent / "results_log.csv"

LOG_COLUMNS = [
    "date", "coach_name", "language", "verdict", "overall_score",
    "upwork_link", "native_speaker", "country_of_origin", "type_of_spanish",
    "years_teaching", "number_of_students", "levels_covered",
    "certificate_name", "certificate_relevant", "english_level", "hourly_rate",
    "video_spanish_accent", "video_english_accent", "program_quiz_completed",
    "verdict_reason",
]

# ─── Helpers: File Extraction ──────────────────────────────────────────────────

def extract_pdf_text(filepath: str) -> str:
    text_parts = []
    try:
        with pdfplumber.open(filepath) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
        return "\n".join(text_parts).strip()
    except Exception as e:
        return f"[Could not extract PDF: {e}]"


def extract_docx_text(filepath: str) -> str:
    try:
        doc = Document(filepath)
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n".join(paragraphs).strip()
    except Exception as e:
        return f"[Could not extract DOCX: {e}]"


def scan_coach_folder(folder_path: str) -> dict:
    result = {
        "folder_path": folder_path,
        "coach_name": Path(folder_path).name,
        "files_found": [],
        "pdfs": {},
        "docx_notes": {},
        "videos": [],
        "other_files": [],
        "raw_text_bundle": "",
    }

    if not os.path.isdir(folder_path):
        st.error(f"Folder not found: {folder_path}")
        return result

    all_text_sections = []

    # rglob("*") scans ALL files including inside subfolders
    for file in sorted(Path(folder_path).rglob("*")):
        if file.is_file():
            # Show relative path so subfolders are visible (e.g. "Certificates/DELF.pdf")
            rel_name = str(file.relative_to(folder_path))
            result["files_found"].append(rel_name)
            ext = file.suffix.lower()

            if ext == ".pdf":
                text = extract_pdf_text(str(file))
                result["pdfs"][rel_name] = text
                all_text_sections.append(f"=== PDF: {rel_name} ===\n{text}")

            elif ext in (".docx", ".doc"):
                text = extract_docx_text(str(file))
                result["docx_notes"][rel_name] = text
                all_text_sections.append(f"=== DOCX: {rel_name} ===\n{text}")

            elif ext in (".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"):
                size_mb = file.stat().st_size / (1024 * 1024)
                result["videos"].append({"name": rel_name, "size_mb": round(size_mb, 1)})

            else:
                result["other_files"].append(rel_name)

    if result["videos"]:
        video_lines = [f"  - {v['name']} ({v['size_mb']} MB)" for v in result["videos"]]
        all_text_sections.append("=== VIDEO FILES SUBMITTED ===\n" + "\n".join(video_lines))
    else:
        all_text_sections.append("=== VIDEO FILES SUBMITTED ===\nNone found.")

    result["raw_text_bundle"] = "\n\n".join(all_text_sections)
    return result


# ─── Helpers: Google Sheets / CSV ─────────────────────────────────────────────

def load_sheets_from_url(sheet_url: str) -> pd.DataFrame | None:
    try:
        match = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", sheet_url)
        if not match:
            return None
        sheet_id = match.group(1)
        gid_match = re.search(r"gid=(\d+)", sheet_url)
        gid = gid_match.group(1) if gid_match else "0"
        export_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
        df = pd.read_csv(export_url)
        return df
    except Exception:
        return None


def format_sheet_for_prompt(df: pd.DataFrame, selected_row_index: int | None = None) -> str:
    if df is None or df.empty:
        return "No form response data provided."

    lines = []
    if selected_row_index is not None and 0 <= selected_row_index < len(df):
        row = df.iloc[selected_row_index]
        lines.append(f"[ Form response — row {selected_row_index + 1} selected by reviewer ]")
        for col, val in row.items():
            if pd.notna(val) and str(val).strip():
                lines.append(f"  {col}: {val}")
    else:
        lines.append("[ All form responses included — reviewer did not select a specific row ]")
        for _, row in df.iterrows():
            lines.append("--- Entry ---")
            for col, val in row.items():
                if pd.notna(val) and str(val).strip():
                    lines.append(f"  {col}: {val}")

    return "\n".join(lines)


# ─── AI Analysis ──────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an expert HR assistant specializing in language coach recruitment.
You analyze coach applications and provide structured, evidence-based hiring recommendations.
You must always respond in valid JSON format exactly as specified."""


def build_analysis_prompt(
    coach_data: dict,
    form_text: str,
    language_type: str,
    extra_notes: str,
    video_spanish: dict,
    video_english: dict,
    upwork_link: str = "",
    cv_link: str = "",
) -> str:
    lang = language_type
    video_section = f"""
### HUMAN REVIEWER VIDEO ASSESSMENTS:
SPANISH VIDEO:
- Accent Quality: {video_spanish.get('accent', 'Not reviewed')}
- Audio Quality: {video_spanish.get('audio', 'Not reviewed')}
- Notes: {video_spanish.get('notes', 'None')}

ENGLISH VIDEO:
- Accent Quality: {video_english.get('accent', 'Not reviewed')}
- Audio Quality: {video_english.get('audio', 'Not reviewed')}
- Notes: {video_english.get('notes', 'None')}
"""

    type_of_spanish_instruction = ""
    if lang == "Spanish":
        type_of_spanish_instruction = """
IMPORTANT — TYPE OF SPANISH: Identify which variety of Spanish the coach speaks.
Look for clues in their country of origin, accent descriptions, vocabulary, and any explicit statements.
Types: Castilian (Spain), Mexican, Colombian, Argentine, Venezuelan, Peruvian, Chilean, Caribbean, Central American, or other Latin American.
"""

    return f"""You are evaluating a {lang} language coach applicant for an online coaching program.

## APPLICANT: {coach_data['coach_name']}
Upwork Profile: {upwork_link if upwork_link else "not provided"}
CV Link/File: {cv_link if cv_link else "see documents below"}

### WHAT WE REQUIRE FROM COACHES:
1. CV in English
2. Relevant certificates (degree or teaching certificate in {lang} or education)
3. TWO video introductions — one in {lang}, one in English
4. Completed: Coach Hiring Questionnaire + Coach Information Form
5. Completed program quiz (familiarity with our program and expectations)

### DOCUMENTS EXTRACTED FROM THEIR FOLDER:
{coach_data['raw_text_bundle']}

### GOOGLE FORMS / QUESTIONNAIRE RESPONSES:
{form_text}

{video_section}
{type_of_spanish_instruction}
### ADDITIONAL REVIEWER NOTES:
{extra_notes if extra_notes.strip() else "None provided."}

---

## YOUR TASK

Read EVERY document carefully. Extract every piece of relevant information. Do not skip any document.

Return a JSON object with EXACTLY this structure:

{{
  "coach_name": "Full name of the coach",
  "language": "{lang}",
  "overall_score": <integer 0-100>,
  "verdict": "<HIRE | CONSIDER | DO NOT HIRE>",
  "verdict_reason": "<2-3 sentence plain-English summary for the hiring team>",
  "scores": {{
    "native_language_origin": {{
      "score": <0-20>,
      "max": 20,
      "notes": "<Confirmed native {lang} speaker? Country of origin? Type of {lang} (e.g. Castilian, Mexican, Colombian)? Which document confirms this?>"
    }},
    "education_credentials": {{
      "score": <0-25>,
      "max": 25,
      "notes": "<List ALL certificates and degrees found across ALL documents. Are they related to {lang} teaching? (DELF/DALF/FLE/TCF for French; DELE/ELE/SIELE for Spanish). Quote exact certificate name and issuing institution.>"
    }},
    "teaching_experience": {{
      "score": <0-20>,
      "max": 20,
      "notes": "<Total years teaching {lang}? Number of students taught? Levels taught (A1-C2)? Online or in-person? Notable institutions or platforms?>"
    }},
    "english_proficiency": {{
      "score": <0-15>,
      "max": 15,
      "notes": "<English level (A1-C2)? Any English certificate? Assess from how the coach writes in English across all documents.>"
    }},
    "video_submission": {{
      "score": <0-10>,
      "max": 10,
      "notes": "<Spanish video: accent={video_spanish.get('accent','not reviewed')}, audio={video_spanish.get('audio','not reviewed')}. English video: accent={video_english.get('accent','not reviewed')}, audio={video_english.get('audio','not reviewed')}. Were BOTH videos submitted?>"
    }},
    "form_completeness": {{
      "score": <0-10>,
      "max": 10,
      "notes": "<Did they complete the Coach Hiring Questionnaire? Coach Information Form? Program quiz? Quality and thoroughness of answers. Teaching approach described?>"
    }},
    "rate_details": {{
      "score": <0-5>,
      "max": 5,
      "notes": "<IMPORTANT: Search every document and every form field for: rate, price, fee, hourly, per session, salary, tarif, prix, tarifa, precio, $/€/£/XAF/CFA, or any number followed by /hr /hour /session. Quote EXACT text and which document it was found in. If not found anywhere write: 'not found in any document'.>"
    }}
  }},
  "strengths": ["<strength 1>", "<strength 2>", "<strength 3>"],
  "concerns": ["<concern 1>", "<concern 2>"],
  "suggested_email_action": "<HIRE | CONSIDER | REJECT_INITIAL | REJECT_AFTER_STEPS>",
  "key_facts": {{
    "native_speaker_confirmed": "<yes / no / unclear>",
    "native_language": "<language>",
    "country_of_origin": "<country>",
    "type_of_spanish": "<Castilian / Mexican / Colombian / Argentine / Venezuelan / Latin American / N/A>",
    "years_teaching_language": "<e.g. '5 years', '3-5 years', 'not mentioned'>",
    "number_of_students": "<e.g. '200+ students', 'not mentioned'>",
    "levels_covered": "<e.g. 'A1 to C2', 'A1 to B2', 'not specified'>",
    "certificate_name": "<exact certificate name(s), e.g. 'DELF B2 + Licence FLE', 'none found'>",
    "certificate_relevant": "<yes / no / partial>",
    "english_level": "<CEFR: A1/A2/B1/B2/C1/C2 or 'estimated B2'>",
    "hourly_rate": "<exact amount found, e.g. '$25/hr', '€20/session', 'not mentioned'>",
    "degree": "<highest degree and field>",
    "teaching_methodology": "<brief description of their teaching approach>",
    "availability": "<full-time / part-time / hours mentioned, or 'not mentioned'>",
    "platform_experience": "<Zoom / Google Meet / Skype / other>",
    "specializations": "<e.g. 'Business Spanish, DELE exam prep' or 'not mentioned'>",
    "video_spanish_submitted": <true/false>,
    "video_english_submitted": <true/false>,
    "video_spanish_quality": "{video_spanish.get('accent', 'not reviewed')} accent / {video_spanish.get('audio', 'not reviewed')} audio",
    "video_english_quality": "{video_english.get('accent', 'not reviewed')} accent / {video_english.get('audio', 'not reviewed')} audio",
    "program_quiz_completed": "<yes / no / unclear>",
    "cv_submitted_in_english": "<yes / no / unclear>"
  }}
}}

Scoring guide:
- native_language_origin (0-20): 20=confirmed native {lang} speaker from {lang}-speaking country, 15=near-native, 10=advanced non-native, 5=intermediate
- education_credentials (0-25): 25=Masters/PhD + relevant cert, 20=Bachelor's + cert, 15=Teaching cert directly related to {lang}, 10=related degree, 5=partial evidence, 0=none
- teaching_experience (0-20): 20=5+ years online {lang} + A1-C2 + many students, 15=3-5 years, 10=1-3 years, 5=some, 0=none
- english_proficiency (0-15): 15=C1/C2 evident, 10=B2, 5=B1, 0=below B1
- video_submission (0-10): 10=BOTH videos (Spanish+English) + good quality, 7=one video or fair quality, 5=submitted but not reviewed, 0=no video
- form_completeness (0-10): 10=all 3 forms completed with strong answers, 7=2 forms, 5=1 form, 0=none
- rate_details (0-5): 5=rate clearly stated, 3=rate range, 0=not mentioned

Verdict thresholds: HIRE >= 75, CONSIDER 55-74, DO NOT HIRE < 55.

Be strict but fair. Base ALL scores on actual evidence found in the documents."""


def analyze_coach(
    coach_data: dict,
    form_text: str,
    language_type: str,
    extra_notes: str,
    video_spanish: dict,
    video_english: dict,
    api_key: str,
    upwork_link: str = "",
    cv_link: str = "",
) -> dict | None:
    client = anthropic.Anthropic(api_key=api_key)
    prompt = build_analysis_prompt(
        coach_data, form_text, language_type, extra_notes,
        video_spanish, video_english, upwork_link, cv_link
    )

    try:
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=3000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text.strip()

        if raw.startswith("```"):
            raw = re.sub(r"^```[a-z]*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)

        return json.loads(raw)

    except json.JSONDecodeError as e:
        st.error(f"Claude returned invalid JSON: {e}")
        st.code(raw, language="json")
        return None
    except anthropic.APIError as e:
        st.error(f"Claude API error: {e}")
        return None


# ─── Results Log ──────────────────────────────────────────────────────────────

def save_to_log(result: dict):
    facts = result.get("key_facts", {})
    row = {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "coach_name": result.get("coach_name", ""),
        "language": result.get("language", ""),
        "verdict": result.get("verdict", ""),
        "overall_score": result.get("overall_score", ""),
        "upwork_link": result.get("upwork_link", ""),
        "native_speaker": facts.get("native_speaker_confirmed", ""),
        "country_of_origin": facts.get("country_of_origin", ""),
        "type_of_spanish": facts.get("type_of_spanish", "N/A"),
        "years_teaching": facts.get("years_teaching_language", ""),
        "number_of_students": facts.get("number_of_students", ""),
        "levels_covered": facts.get("levels_covered", ""),
        "certificate_name": facts.get("certificate_name", ""),
        "certificate_relevant": facts.get("certificate_relevant", ""),
        "english_level": facts.get("english_level", ""),
        "hourly_rate": facts.get("hourly_rate", ""),
        "video_spanish_accent": facts.get("video_spanish_quality", "not reviewed"),
        "video_english_accent": facts.get("video_english_quality", "not reviewed"),
        "program_quiz_completed": facts.get("program_quiz_completed", ""),
        "verdict_reason": result.get("verdict_reason", ""),
    }
    file_exists = LOG_FILE.exists()
    with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=LOG_COLUMNS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


def load_log() -> pd.DataFrame | None:
    if not LOG_FILE.exists():
        return None
    try:
        df = pd.read_csv(LOG_FILE)
        return df if not df.empty else None
    except Exception:
        return None


# ─── Summary Text Generator (for copy/share) ──────────────────────────────────

def generate_summary_text(result: dict) -> str:
    facts = result.get("key_facts", {})
    lang = result.get("language", "")
    verdict = result.get("verdict", "")
    verdict_emoji = {"HIRE": "✅", "CONSIDER": "🟡", "DO NOT HIRE": "❌"}.get(verdict, "")

    videos = []
    if facts.get("video_spanish_submitted"):
        videos.append(f"Spanish ({facts.get('video_spanish_quality','not reviewed')})")
    if facts.get("video_english_submitted"):
        videos.append(f"English ({facts.get('video_english_quality','not reviewed')})")
    video_text = ", ".join(videos) if videos else "Not submitted"

    type_line = ""
    if lang == "Spanish":
        type_line = f"Type of Spanish: {facts.get('type_of_spanish', 'N/A')}\n"

    return (
        f"👤 Coach Name: {result.get('coach_name', 'N/A')}\n"
        f"🔗 Upwork Profile: {result.get('upwork_link', 'N/A')}\n"
        f"🌍 Country of Origin: {facts.get('country_of_origin', 'N/A')}\n"
        f"{type_line}"
        f"📚 Experience: {facts.get('years_teaching_language', 'N/A')} | "
        f"{facts.get('number_of_students', 'N/A')} students | "
        f"Levels: {facts.get('levels_covered', 'N/A')}\n"
        f"📄 CV: {result.get('cv_link', 'see folder')}\n"
        f"🎓 Certificate: {facts.get('certificate_name', 'N/A')} "
        f"(Relevant: {facts.get('certificate_relevant', 'N/A')})\n"
        f"🎥 Video: {video_text}\n"
        f"🇬🇧 English Level: {facts.get('english_level', 'N/A')}\n"
        f"💰 Rate: {facts.get('hourly_rate', 'N/A')}\n"
        f"\n📊 Score: {result.get('overall_score', 0)}/100\n"
        f"{verdict_emoji} Verdict: {verdict}\n"
        f"\n📝 Summary: {result.get('verdict_reason', '')}"
    )


# ─── HTML Report Generator ─────────────────────────────────────────────────────

def generate_html_report(result: dict) -> str:
    facts = result.get("key_facts", {})
    verdict = result.get("verdict", "")
    verdict_color = {"HIRE": "#155724", "CONSIDER": "#856404", "DO NOT HIRE": "#721c24"}.get(verdict, "#333")
    verdict_bg = {"HIRE": "#d4edda", "CONSIDER": "#fff3cd", "DO NOT HIRE": "#f8d7da"}.get(verdict, "#eee")
    score = result.get("overall_score", 0)
    scores = result.get("scores", {})

    def fact_row(label, value):
        if isinstance(value, bool):
            value = "Yes" if value else "No"
        return f"<tr><td style='padding:6px 12px; color:#888; font-weight:600; font-size:0.85rem;'>{label}</td><td style='padding:6px 12px; font-weight:700; color:#1e3a5f;'>{value}</td></tr>"

    scores_html = ""
    score_labels = {
        "native_language_origin": "Native Language & Origin",
        "education_credentials": "Education & Credentials",
        "teaching_experience": "Teaching Experience",
        "english_proficiency": "English Proficiency",
        "video_submission": "Video Submission (Spanish + English)",
        "form_completeness": "Form & Quiz Completeness",
        "form_quiz_performance": "Form & Quiz Performance",
        "rate_details": "Rate / Compensation",
    }
    for key, val in scores.items():
        s = val.get("score", 0)
        m = val.get("max", 10)
        n = val.get("notes", "")
        pct = int((s / m) * 100) if m else 0
        bar_color = "#2d6a4f" if pct >= 70 else "#e6a817" if pct >= 45 else "#c0392b"
        label = score_labels.get(key, key.replace("_", " ").title())
        scores_html += f"""
        <div style='margin-bottom:1rem; padding:1rem; background:#f8f9fa; border-radius:8px; border-left:4px solid {bar_color};'>
            <div style='display:flex; justify-content:space-between;'>
                <span style='font-weight:600; color:#1e3a5f;'>{label}</span>
                <span style='font-weight:700; color:{bar_color};'>{s}/{m}</span>
            </div>
            <div style='background:#e0e0e0; border-radius:4px; height:8px; margin:6px 0;'>
                <div style='background:{bar_color}; width:{pct}%; height:8px; border-radius:4px;'></div>
            </div>
            <div style='font-size:0.85rem; color:#555;'>{n}</div>
        </div>"""

    strengths_html = "".join(f"<li style='margin-bottom:4px;'>{s}</li>" for s in result.get("strengths", []))
    concerns_html = "".join(f"<li style='margin-bottom:4px; color:#721c24;'>{c}</li>" for c in result.get("concerns", []))

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Coach Analysis: {result.get('coach_name', '')}</title>
<style>
  body {{ font-family: Arial, sans-serif; max-width: 900px; margin: 0 auto; padding: 2rem; color: #333; }}
  h1, h2, h3 {{ color: #1e3a5f; }}
  table {{ border-collapse: collapse; width: 100%; }}
</style>
</head>
<body>
<div style='background:linear-gradient(135deg,#1e3a5f,#2d6a4f); color:white; padding:2rem; border-radius:12px; margin-bottom:2rem; text-align:center;'>
  <h1 style='margin:0; color:white;'>Coach Hiring Analysis</h1>
  <p style='margin:0.3rem 0 0; opacity:0.85;'>Generated {datetime.now().strftime("%B %d, %Y at %H:%M")}</p>
</div>

<div style='text-align:center; padding:2rem; background:#f8f9fa; border-radius:12px; margin-bottom:2rem;'>
  <div style='font-size:1.8rem; font-weight:700; color:#1e3a5f; margin-bottom:0.5rem;'>{result.get('coach_name', '')}</div>
  <div style='display:inline-block; background:{verdict_bg}; color:{verdict_color}; padding:0.5rem 2rem; border-radius:25px; font-size:1.3rem; font-weight:bold; margin-bottom:0.8rem;'>{verdict}</div>
  <div style='font-size:3rem; font-weight:800; color:#1e3a5f;'>{score}<span style='font-size:1.2rem;'>/100</span></div>
  <p style='color:#555;'>{result.get('verdict_reason', '')}</p>
</div>

<h2>Quick Summary</h2>
<table style='margin-bottom:2rem; background:#fff; border-radius:8px; overflow:hidden; border:2px solid {verdict_color};'>
  {fact_row("Coach Name", result.get("coach_name", "N/A"))}
  {fact_row("Upwork Profile", f'<a href="{result.get("upwork_link","")}">{result.get("upwork_link","N/A")}</a>' if result.get("upwork_link") else "N/A")}
  {fact_row("Country of Origin", facts.get("country_of_origin", "N/A"))}
  {fact_row("Type of Spanish", facts.get("type_of_spanish", "N/A"))}
  {fact_row("Experience", f'{facts.get("years_teaching_language","N/A")} | {facts.get("number_of_students","N/A")} students | Levels: {facts.get("levels_covered","N/A")}')}
  {fact_row("CV", f'<a href="{result.get("cv_link","")}">{result.get("cv_link","see folder")}</a>' if result.get("cv_link") else "See attached folder")}
  {fact_row("Certificate", f'{facts.get("certificate_name","N/A")} (Relevant: {facts.get("certificate_relevant","N/A")})')}
  {fact_row("Video in Spanish", facts.get("video_spanish_quality", "Not reviewed"))}
  {fact_row("Video in English", facts.get("video_english_quality", "Not reviewed"))}
  {fact_row("English Level", facts.get("english_level", "N/A"))}
  {fact_row("Rate", facts.get("hourly_rate", "N/A"))}
  {fact_row("Verdict", f'<strong style="color:{verdict_color};">{verdict} ({score}/100)</strong>')}
</table>

<h2>Detailed Profile</h2>
<table style='margin-bottom:2rem; background:#f8f9fa; border-radius:8px; overflow:hidden;'>
  {fact_row("Native Speaker", facts.get("native_speaker_confirmed", "N/A"))}
  {fact_row("Availability", facts.get("availability", "N/A"))}
  {fact_row("Platform Experience", facts.get("platform_experience", "N/A"))}
  {fact_row("Specializations", facts.get("specializations", "N/A"))}
  {fact_row("Teaching Methodology", facts.get("teaching_methodology", "N/A"))}
  {fact_row("Program Quiz Completed", facts.get("program_quiz_completed", "N/A"))}
  {fact_row("CV in English", facts.get("cv_submitted_in_english", "N/A"))}
</table>

<h2>Score Breakdown</h2>
{scores_html}

<div style='display:flex; gap:1rem; margin-bottom:2rem;'>
  <div style='flex:1; padding:1.2rem; background:#d4edda; border-radius:8px;'>
    <h3 style='margin-top:0; color:#155724;'>Strengths</h3>
    <ul style='margin:0; padding-left:1.2rem;'>{strengths_html}</ul>
  </div>
  <div style='flex:1; padding:1.2rem; background:#f8d7da; border-radius:8px;'>
    <h3 style='margin-top:0; color:#721c24;'>Concerns</h3>
    <ul style='margin:0; padding-left:1.2rem;'>{concerns_html if concerns_html else "<li>No major concerns</li>"}</ul>
  </div>
</div>

<p style='font-size:0.8rem; color:#aaa; text-align:center; margin-top:3rem;'>Generated by Coach Hiring Assistant</p>
</body>
</html>"""


# ─── Video Accent Analysis ────────────────────────────────────────────────────

def analyze_video_accent(video_path: str, language: str, api_key: str) -> dict:
    """Transcribe video with Whisper, then ask Claude to assess the accent."""
    try:
        import whisper
    except ImportError:
        return {"error": "whisper_not_installed"}

    try:
        with st.spinner("Loading speech recognition model (first time takes ~1 min)..."):
            model = whisper.load_model("base")

        with st.spinner("Transcribing audio from video..."):
            wresult = model.transcribe(video_path, fp16=False)

        transcript = wresult.get("text", "").strip()
        detected_lang = wresult.get("language", "unknown")

        if not transcript:
            return {"error": "No speech detected in video."}

        client = anthropic.Anthropic(api_key=api_key)
        lang_label = language  # "French" or "Spanish"

        with st.spinner("Claude is assessing the accent..."):
            message = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=800,
                messages=[{
                    "role": "user",
                    "content": f"""You are an expert linguist specializing in {lang_label}.

A language coach submitted a video. The speech-to-text system transcribed it and detected language: "{detected_lang}".

Full transcript:
---
{transcript[:3000]}
---

Based on this transcript, assess the coach's accent and language quality.
Respond ONLY in valid JSON:
{{
  "language_detected": "{detected_lang}",
  "is_target_language": <true/false>,
  "accent_quality": "<Excellent / Good / Fair / Poor>",
  "speaker_profile": "<e.g. Native French speaker, Cameroonian French speaker, Non-native with light accent>",
  "grammar_quality": "<Excellent / Good / Fair / Poor>",
  "fluency": "<Fluent / Mostly fluent / Some hesitations / Not fluent>",
  "pronunciation_notes": "<specific observations about pronunciation, clarity, rhythm>",
  "key_observations": ["<observation 1>", "<observation 2>", "<observation 3>"],
  "recommendation": "<1 sentence summary for the hiring team>"
}}"""
                }]
            )

        raw = message.content[0].text.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```[a-z]*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)

        accent_data = json.loads(raw)
        accent_data["transcript_excerpt"] = transcript[:400]
        return accent_data

    except json.JSONDecodeError:
        return {"error": "Could not parse accent analysis response."}
    except Exception as e:
        return {"error": str(e)}


# ─── UI: Render Results ────────────────────────────────────────────────────────

def render_verdict_badge(verdict: str) -> str:
    if verdict == "HIRE":
        return '<span class="hire-badge">✅ HIRE</span>'
    elif verdict == "CONSIDER":
        return '<span class="consider-badge">🟡 CONSIDER</span>'
    else:
        return '<span class="nohire-badge">❌ DO NOT HIRE</span>'


def render_summary_card(result: dict):
    """Render the top-level quick summary card matching the team's format."""
    facts = result.get("key_facts", {})
    verdict = result.get("verdict", "")
    score = result.get("overall_score", 0)
    verdict_color = {"HIRE": "#155724", "CONSIDER": "#856404", "DO NOT HIRE": "#721c24"}.get(verdict, "#333")
    verdict_bg = {"HIRE": "#d4edda", "CONSIDER": "#fff3cd", "DO NOT HIRE": "#f8d7da"}.get(verdict, "#eee")
    lang = result.get("language", "")

    upwork = result.get("upwork_link", "")
    cv = result.get("cv_link", "")

    upwork_html = f"<a href='{upwork}' target='_blank'>{upwork}</a>" if upwork else "N/A"
    cv_html = f"<a href='{cv}' target='_blank'>{cv}</a>" if cv else "See attached folder"

    videos_es = facts.get("video_spanish_quality", "Not reviewed")
    videos_en = facts.get("video_english_quality", "Not reviewed")
    video_es_icon = "✅" if facts.get("video_spanish_submitted") else "❌"
    video_en_icon = "✅" if facts.get("video_english_submitted") else "❌"

    type_row = ""
    if lang == "Spanish":
        type_row = f"""
        <tr><td style='padding:10px 16px; color:#666; font-weight:600; font-size:0.85rem; white-space:nowrap; background:#f8f9fa;'>🌎 Type of Spanish</td>
            <td style='padding:10px 16px; font-weight:700; color:#1e3a5f;'>{facts.get('type_of_spanish', 'N/A')}</td></tr>"""

    st.markdown("### 📋 Quick Summary")
    st.markdown(
        f"""<div style='border:2px solid {verdict_color}; border-radius:12px; overflow:hidden; margin-bottom:1.5rem;'>
<table style='width:100%; border-collapse:collapse;'>
  <tr><td style='padding:10px 16px; color:#666; font-weight:600; font-size:0.85rem; white-space:nowrap; background:#f8f9fa;'>👤 Coach Name</td>
      <td style='padding:10px 16px; font-weight:700; color:#1e3a5f; font-size:1.1rem;'>{result.get('coach_name','N/A')}</td></tr>
  <tr><td style='padding:10px 16px; color:#666; font-weight:600; font-size:0.85rem; white-space:nowrap; background:#f8f9fa;'>🔗 Upwork Profile</td>
      <td style='padding:10px 16px;'>{upwork_html}</td></tr>
  <tr><td style='padding:10px 16px; color:#666; font-weight:600; font-size:0.85rem; white-space:nowrap; background:#f8f9fa;'>🌍 Country of Origin</td>
      <td style='padding:10px 16px; font-weight:700; color:#1e3a5f;'>{facts.get('country_of_origin','N/A')}</td></tr>
  {type_row}
  <tr><td style='padding:10px 16px; color:#666; font-weight:600; font-size:0.85rem; white-space:nowrap; background:#f8f9fa;'>📚 Experience</td>
      <td style='padding:10px 16px;'>{facts.get('years_teaching_language','N/A')} &nbsp;|&nbsp; {facts.get('number_of_students','N/A')} students &nbsp;|&nbsp; Levels: <strong>{facts.get('levels_covered','N/A')}</strong></td></tr>
  <tr><td style='padding:10px 16px; color:#666; font-weight:600; font-size:0.85rem; white-space:nowrap; background:#f8f9fa;'>📄 CV</td>
      <td style='padding:10px 16px;'>{cv_html}</td></tr>
  <tr><td style='padding:10px 16px; color:#666; font-weight:600; font-size:0.85rem; white-space:nowrap; background:#f8f9fa;'>🎓 Certificate</td>
      <td style='padding:10px 16px;'><strong>{facts.get('certificate_name','N/A')}</strong> &nbsp;<span style='color:#888; font-size:0.85rem;'>(Relevant: {facts.get('certificate_relevant','N/A')})</span></td></tr>
  <tr><td style='padding:10px 16px; color:#666; font-weight:600; font-size:0.85rem; white-space:nowrap; background:#f8f9fa;'>🎥 Video (Spanish)</td>
      <td style='padding:10px 16px;'>{video_es_icon} {videos_es}</td></tr>
  <tr><td style='padding:10px 16px; color:#666; font-weight:600; font-size:0.85rem; white-space:nowrap; background:#f8f9fa;'>🎥 Video (English)</td>
      <td style='padding:10px 16px;'>{video_en_icon} {videos_en}</td></tr>
  <tr><td style='padding:10px 16px; color:#666; font-weight:600; font-size:0.85rem; white-space:nowrap; background:#f8f9fa;'>🇬🇧 English Level</td>
      <td style='padding:10px 16px; font-weight:700; color:#1e3a5f;'>{facts.get('english_level','N/A')}</td></tr>
  <tr><td style='padding:10px 16px; color:#666; font-weight:600; font-size:0.85rem; white-space:nowrap; background:#f8f9fa;'>💰 Rate</td>
      <td style='padding:10px 16px; font-weight:700; color:#1e3a5f;'>{facts.get('hourly_rate','N/A')}</td></tr>
  <tr style='background:{verdict_bg};'>
      <td style='padding:12px 16px; color:{verdict_color}; font-weight:700; font-size:0.9rem;'>📊 Verdict</td>
      <td style='padding:12px 16px; color:{verdict_color}; font-weight:800; font-size:1.1rem;'>{verdict} &nbsp;&nbsp; {score}/100</td></tr>
</table>
</div>""",
        unsafe_allow_html=True,
    )

    # Copy-to-clipboard button
    summary_text = generate_summary_text(result)
    st.text_area(
        "📋 Copy this summary to share with your team:",
        value=summary_text,
        height=230,
        key="summary_copy_box",
    )


def render_profile_card(result: dict):
    facts = result.get("key_facts", {})

    def tag(value):
        v = str(value).lower()
        if v in ("yes", "true"):
            return f'<span class="yes-tag">✅ {value}</span>'
        elif v in ("no", "false"):
            return f'<span class="no-tag">❌ {value}</span>'
        elif v in ("partial", "unclear"):
            return f'<span class="partial-tag">🟡 {value}</span>'
        return f'<span style="color:#1e3a5f; font-weight:700;">{value}</span>'

    def item(label, value):
        if isinstance(value, bool):
            value = "yes" if value else "no"
        return (
            f"<div class='profile-item'>"
            f"<div class='profile-label'>{label}</div>"
            f"<div class='profile-value'>{tag(value or 'N/A')}</div>"
            f"</div>"
        )

    lang = result.get("language", "")
    st.markdown("### 👤 Detailed Coach Profile")
    type_row = f"{item('Type of Spanish', facts.get('type_of_spanish', 'N/A'))}" if lang == "Spanish" else ""
    st.markdown(
        f"<div class='profile-card'>"
        f"<div class='profile-row'>"
        f"{item('Native Speaker', facts.get('native_speaker_confirmed', 'N/A'))}"
        f"{item('Country of Origin', facts.get('country_of_origin', 'N/A'))}"
        f"{type_row}"
        f"{item('Years Teaching', facts.get('years_teaching_language', 'N/A'))}"
        f"</div>"
        f"<div class='profile-row'>"
        f"{item('Students Taught', facts.get('number_of_students', 'N/A'))}"
        f"{item('Levels Covered', facts.get('levels_covered', 'N/A'))}"
        f"{item('English Level', facts.get('english_level', 'N/A'))}"
        f"{item('Hourly Rate', facts.get('hourly_rate', 'N/A'))}"
        f"</div>"
        f"<div class='profile-row'>"
        f"{item('Certificate', facts.get('certificate_name', 'N/A'))}"
        f"{item('Cert. Relevant', facts.get('certificate_relevant', 'N/A'))}"
        f"{item('Availability', facts.get('availability', 'N/A'))}"
        f"{item('Platform Experience', facts.get('platform_experience', 'N/A'))}"
        f"</div>"
        f"<div class='profile-row'>"
        f"{item('Spanish Video', facts.get('video_spanish_quality', 'Not reviewed'))}"
        f"{item('English Video', facts.get('video_english_quality', 'Not reviewed'))}"
        f"{item('Program Quiz', facts.get('program_quiz_completed', 'N/A'))}"
        f"{item('CV in English', facts.get('cv_submitted_in_english', 'N/A'))}"
        f"</div>"
        f"</div>",
        unsafe_allow_html=True,
    )


def render_results(result: dict):
    st.markdown("---")
    st.markdown("## 📊 Analysis Results")

    # Quick summary card + copy box (top priority)
    render_summary_card(result)

    st.markdown("<br>", unsafe_allow_html=True)

    # Detailed profile
    render_profile_card(result)

    st.markdown("<br>", unsafe_allow_html=True)

    # Score breakdown
    col_left, col_right = st.columns(2)
    scores = result.get("scores", {})
    score_items = list(scores.items())
    mid = (len(score_items) + 1) // 2

    score_labels = {
        "native_language_origin": "🌍 Native Language & Origin",
        "education_credentials": "🎓 Education & Credentials",
        "teaching_experience": "📚 Teaching Experience",
        "english_proficiency": "🇬🇧 English Proficiency",
        "video_submission": "🎥 Video Submission (Spanish + English)",
        "form_completeness": "📝 Form & Quiz Completeness",
        "form_quiz_performance": "📝 Form & Quiz Performance",
        "rate_details": "💰 Rate / Compensation",
    }

    for i, (key, val) in enumerate(score_items):
        col = col_left if i < mid else col_right
        with col:
            label = score_labels.get(key, key.replace("_", " ").title())
            score = val.get("score", 0)
            max_score = val.get("max", 10)
            notes = val.get("notes", "")
            pct = int((score / max_score) * 100)
            color = "#2d6a4f" if pct >= 70 else "#e6a817" if pct >= 45 else "#c0392b"
            st.markdown(
                f"<div class='score-card' style='border-left-color:{color};'>"
                f"<div style='display:flex; justify-content:space-between; align-items:center;'>"
                f"<span class='section-title' style='border:none; margin:0;'>{label}</span>"
                f"<span style='font-size:1.2rem; font-weight:700; color:{color};'>{score}/{max_score}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )
            st.progress(pct / 100)
            st.markdown(
                f"<p style='font-size:0.85rem; color:#555; margin:0;'>{notes}</p></div>",
                unsafe_allow_html=True,
            )

    st.markdown("<br>", unsafe_allow_html=True)

    # Strengths & Concerns
    col_s, col_c = st.columns(2)
    with col_s:
        st.markdown("### ✅ Strengths")
        for s in result.get("strengths", []):
            st.markdown(f"- {s}")
    with col_c:
        st.markdown("### ⚠️ Concerns")
        concerns = result.get("concerns", [])
        if concerns:
            for c in concerns:
                st.markdown(f"- {c}")
        else:
            st.markdown("_No major concerns identified._")

    st.markdown("<br>", unsafe_allow_html=True)

    # Suggested action
    action = result.get("suggested_email_action", "")
    action_map = {
        "HIRE": ("✅ Send Hire / Welcome Email", "#d4edda", "#155724"),
        "CONSIDER": ("🟡 Request Follow-up / Additional Info", "#fff3cd", "#856404"),
        "REJECT_INITIAL": ("❌ Send Initial Rejection Email", "#f8d7da", "#721c24"),
        "REJECT_AFTER_STEPS": ("❌ Send Rejection After Steps Email", "#f8d7da", "#721c24"),
    }
    action_text, bg, fg = action_map.get(action, ("📧 Review Manually", "#e2e3e5", "#383d41"))
    st.markdown(
        f"<div style='background:{bg}; color:{fg}; padding:1rem 1.5rem; "
        f"border-radius:8px; font-size:1.1rem; font-weight:600;'>"
        f"📧 Recommended Next Action: {action_text}</div>",
        unsafe_allow_html=True,
    )

    st.markdown("<br>", unsafe_allow_html=True)

    # Export buttons
    col_dl1, col_dl2 = st.columns(2)

    with col_dl1:
        json_str = json.dumps(result, indent=2)
        b64_json = base64.b64encode(json_str.encode()).decode()
        coach_slug = re.sub(r"[^a-zA-Z0-9_-]", "_", result.get("coach_name", "coach"))
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        st.markdown(
            f'<a href="data:application/json;base64,{b64_json}" download="analysis_{coach_slug}_{timestamp}.json" '
            f'style="display:inline-block; background:#1e3a5f; color:white; '
            f'padding:0.5rem 1.2rem; border-radius:6px; text-decoration:none; font-weight:600; width:100%; text-align:center; box-sizing:border-box;">'
            f"⬇️ Download JSON Report</a>",
            unsafe_allow_html=True,
        )

    with col_dl2:
        html_report = generate_html_report(result)
        b64_html = base64.b64encode(html_report.encode()).decode()
        st.markdown(
            f'<a href="data:text/html;base64,{b64_html}" download="report_{coach_slug}_{timestamp}.html" '
            f'style="display:inline-block; background:#2d6a4f; color:white; '
            f'padding:0.5rem 1.2rem; border-radius:6px; text-decoration:none; font-weight:600; width:100%; text-align:center; box-sizing:border-box;">'
            f"📄 Download HTML Report (Share with Team)</a>",
            unsafe_allow_html=True,
        )


# ─── Main App ──────────────────────────────────────────────────────────────────

def main():
    st.markdown(
        """<div class='main-header'>
        <h1 style='margin:0; font-size:2rem;'>🎓 Coach Hiring Assistant</h1>
        <p style='margin:0.5rem 0 0; opacity:0.85; font-size:1.05rem;'>
        Automated evaluation for French &amp; Spanish language coaches
        </p>
        </div>""",
        unsafe_allow_html=True,
    )

    # ── Tabs ──
    tab_analyze, tab_log = st.tabs(["🔍 Analyze Coach", "📋 Team Results Log"])

    # ══════════════════════════════════════════════════════════════════
    with tab_analyze:

        # ── Sidebar ──
        with st.sidebar:
            st.markdown("## ⚙️ Configuration")

            api_key = st.text_input(
                "Anthropic API Key",
                type="password",
                placeholder="sk-ant-...",
                help="Get your key at console.anthropic.com",
            )

            language_type = st.selectbox(
                "Coach Language",
                ["French", "Spanish"],
            )

            st.markdown("---")
            st.markdown("### 📁 Coach Folder")

            preset_base = st.selectbox(
                "Quick Select Base Folder",
                [
                    "-- custom path --",
                    r"C:\Users\USER\Desktop\French Coaches",
                    r"C:\Users\USER\Desktop\Spanish Coaches",
                ],
            )

            if preset_base != "-- custom path --":
                try:
                    subfolders = [
                        f.name
                        for f in Path(preset_base).iterdir()
                        if f.is_dir()
                    ]
                    selected_sub = st.selectbox("Select Coach Subfolder", ["-- select --"] + subfolders)
                    if selected_sub != "-- select --":
                        folder_path = str(Path(preset_base) / selected_sub)
                        st.success(f"Selected: `{selected_sub}`")
                    else:
                        folder_path = ""
                except Exception:
                    st.error("Could not list subfolders.")
                    folder_path = ""
            else:
                folder_path = st.text_input(
                    "Coach Folder Path",
                    placeholder=r"C:\Users\USER\Desktop\French Coaches\Coach Name",
                )

            st.markdown("---")
            st.markdown("### 📊 Google Forms Data")

            sheets_mode = st.radio(
                "How to provide form responses?",
                ["Upload CSV", "Google Sheets URL", "Skip"],
            )

            df_forms = None
            if sheets_mode == "Upload CSV":
                uploaded = st.file_uploader("Upload CSV export from Google Sheets", type=["csv"])
                if uploaded:
                    try:
                        df_forms = pd.read_csv(uploaded)
                        st.success(f"Loaded {len(df_forms)} rows from CSV")
                    except Exception as e:
                        st.error(f"Could not read CSV: {e}")

            elif sheets_mode == "Google Sheets URL":
                sheet_url = st.text_input(
                    "Google Sheets URL",
                    placeholder="https://docs.google.com/spreadsheets/d/...",
                )
                if sheet_url:
                    with st.spinner("Fetching sheet data..."):
                        df_forms = load_sheets_from_url(sheet_url)
                    if df_forms is not None:
                        st.success(f"Loaded {len(df_forms)} rows from Google Sheets")
                    else:
                        st.warning(
                            "Could not auto-fetch. Make sure the sheet is set to "
                            "'Anyone with the link can view'. Or use CSV upload instead."
                        )

            st.markdown("---")
            st.markdown("### 🔗 Coach Links")
            upwork_link = st.text_input(
                "Upwork Profile URL",
                placeholder="https://www.upwork.com/freelancers/...",
            )
            cv_link = st.text_input(
                "CV Link (Google Drive / Dropbox)",
                placeholder="https://drive.google.com/...",
                help="Optional — paste a link to their CV if you have one",
            )

            st.markdown("---")
            st.markdown("### 📋 Required Forms")
            st.caption("These are the forms coaches must complete:")
            st.markdown("🔹 [Coach Hiring Questionnaire](https://forms.gle/5wYvVKf1DtdxhmFk7)")
            st.markdown("🔹 [Coach Information Form](https://forms.gle/7c2UvHnse71JWgyRA)")
            st.markdown("🔹 [Program Quiz](https://forms.gle/wj6b4pu3vhMLhvS26)")

            st.markdown("---")
            st.markdown("### 💰 Rate (if known)")
            manual_rate = st.text_input(
                "Coach's rate (optional)",
                placeholder="e.g. $25/hr, €20/session",
                help="Fill in if the coach stated their rate separately (email, Upwork, etc.)",
            )

            st.markdown("---")
            st.markdown("### 🎥 Video Assessment")
            st.caption("Watch both videos, then rate each below.")

            st.markdown("**Spanish Video**")
            sp_accent = st.select_slider("Accent (Spanish)", options=["Not reviewed", "Poor", "Fair", "Good", "Excellent"], value="Not reviewed")
            sp_audio = st.select_slider("Audio (Spanish)", options=["Not reviewed", "Poor", "Fair", "Good", "Excellent"], value="Not reviewed")
            sp_notes = st.text_input("Spanish video notes", placeholder="e.g. Colombian accent, very clear...")

            st.markdown("**English Video**")
            en_accent = st.select_slider("Accent (English)", options=["Not reviewed", "Poor", "Fair", "Good", "Excellent"], value="Not reviewed")
            en_audio = st.select_slider("Audio (English)", options=["Not reviewed", "Poor", "Fair", "Good", "Excellent"], value="Not reviewed")
            en_notes = st.text_input("English video notes", placeholder="e.g. Fluent, B2 level, slight accent...")

            video_spanish = {"accent": sp_accent, "audio": sp_audio, "notes": sp_notes}
            video_english = {"accent": en_accent, "audio": en_audio, "notes": en_notes}
            # Keep a combined dict for backwards compatibility
            video_assessment = {
                "accent": sp_accent,
                "audio": sp_audio,
                "confidence": "Not reviewed",
                "notes": f"ES: {sp_notes} | EN: {en_notes}",
            }

            st.markdown("---")
            st.markdown("### 📝 Reviewer Notes")
            extra_notes = st.text_area(
                "Additional observations",
                placeholder="e.g. Very responsive to emails. Rate is negotiable...",
                height=80,
            )

        # ── Main Panel ──

        # Files preview
        if folder_path and os.path.isdir(folder_path):
            with st.expander("📂 Files Found in Coach Folder", expanded=True):
                all_files = list(Path(folder_path).rglob("*"))
                all_files = [f for f in all_files if f.is_file()]
                if all_files:
                    cols = st.columns(3)
                    for i, f in enumerate(sorted(all_files)):
                        ext = f.suffix.lower()
                        icon = (
                            "📄" if ext == ".pdf"
                            else "📝" if ext in (".docx", ".doc")
                            else "🎥" if ext in (".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v")
                            else "📁"
                        )
                        rel = str(f.relative_to(folder_path))
                        cols[i % 3].markdown(f"{icon} `{rel}`")
                else:
                    st.warning("No files found in this folder.")

        # Form row selector — most important fix for rate extraction
        selected_row_index = None
        if df_forms is not None and not df_forms.empty:
            with st.expander("📊 Form Responses — Select This Coach's Row", expanded=True):
                st.info("Pick the row that belongs to this coach. This ensures all their answers (including rate) are sent to Claude.")
                # Build display labels from all columns
                row_labels = []
                for i, row in df_forms.iterrows():
                    vals = [str(v) for v in row.values if pd.notna(v) and str(v).strip()]
                    label = f"Row {i+1}: " + " | ".join(vals[:4])
                    row_labels.append(label[:120])
                row_options = ["-- None selected (send all rows) --"] + row_labels
                chosen = st.selectbox("Coach's form row:", row_options)
                if chosen != "-- None selected (send all rows) --":
                    selected_row_index = row_labels.index(chosen)
                st.dataframe(df_forms, use_container_width=True)

        # Debug: show extracted text per file
        if folder_path and os.path.isdir(folder_path):
            with st.expander("🔍 Debug — Extracted Text from Each File", expanded=False):
                st.caption("Use this to verify the rate and other info are being read correctly from each file.")
                preview_data = scan_coach_folder(folder_path)
                for fname, text in preview_data["pdfs"].items():
                    st.markdown(f"**📄 {fname}**")
                    st.text_area("", value=text[:2000] + ("..." if len(text) > 2000 else ""), height=150, key=f"dbg_{fname}")
                for fname, text in preview_data["docx_notes"].items():
                    st.markdown(f"**📝 {fname}**")
                    st.text_area("", value=text[:2000] + ("..." if len(text) > 2000 else ""), height=150, key=f"dbg_{fname}")

        # Video accent auto-analysis
        if folder_path and os.path.isdir(folder_path) and api_key:
            video_files = [
                str(f) for f in Path(folder_path).rglob("*")
                if f.suffix.lower() in (".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v")
            ]
            if video_files:
                st.markdown("### 🎤 Automatic Accent Analysis")
                selected_video = st.selectbox("Select video to analyze:", video_files)
                if st.button("🎤 Auto-Analyze Accent from Video", use_container_width=True):
                    accent_result = analyze_video_accent(selected_video, language_type, api_key)
                    if "error" in accent_result:
                        if accent_result["error"] == "whisper_not_installed":
                            st.warning("Whisper is not installed. Run this command in your CMD window to enable accent analysis:")
                            st.code("pip install openai-whisper")
                        else:
                            st.error(f"Accent analysis error: {accent_result['error']}")
                    else:
                        st.session_state["accent_result"] = accent_result
                        st.session_state["auto_video_spanish"] = {
                            "accent": accent_result.get("accent_quality", "Not reviewed"),
                            "audio": sp_audio,
                            "notes": accent_result.get("recommendation", ""),
                        }

                if "accent_result" in st.session_state:
                    ar = st.session_state["accent_result"]
                    st.success("Accent analysis complete")
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Language Detected", ar.get("language_detected", "?").upper())
                    c2.metric("Accent Quality", ar.get("accent_quality", "?"))
                    c3.metric("Fluency", ar.get("fluency", "?"))
                    st.markdown(f"**Speaker Profile:** {ar.get('speaker_profile', '?')}")
                    st.markdown(f"**Grammar:** {ar.get('grammar_quality', '?')}  |  **Pronunciation:** {ar.get('pronunciation_notes', '?')}")
                    if ar.get("key_observations"):
                        for obs in ar["key_observations"]:
                            st.markdown(f"- {obs}")
                    st.info(f"Recommendation: {ar.get('recommendation', '')}")
                    with st.expander("📜 Transcript excerpt"):
                        st.text(ar.get("transcript_excerpt", ""))

        st.markdown("<br>", unsafe_allow_html=True)
        ready = api_key and folder_path and os.path.isdir(folder_path)

        if not api_key:
            st.info("👈 Enter your Anthropic API key in the sidebar to get started.")
        elif not folder_path or not os.path.isdir(folder_path):
            st.info("👈 Select or enter the coach's folder path in the sidebar.")

        if ready:
            if st.button("🔍 Analyze Coach Application", type="primary", use_container_width=True):
                with st.spinner("📂 Scanning coach folder..."):
                    coach_data = scan_coach_folder(folder_path)

                with st.spinner("📊 Processing form responses..."):
                    form_text = format_sheet_for_prompt(df_forms, selected_row_index)

                st.markdown("### 🗂️ Extraction Summary")
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("PDFs Found", len(coach_data["pdfs"]))
                c2.metric("DOCX Files", len(coach_data["docx_notes"]))
                c3.metric("Videos", len(coach_data["videos"]))
                c4.metric("Form Rows", len(df_forms) if df_forms is not None else 0)

                # Use auto accent analysis if available
                final_spanish = st.session_state.get("auto_video_spanish", video_spanish)

                with st.spinner("🤖 Claude is analyzing the application..."):
                    full_notes = extra_notes
                    if manual_rate.strip():
                        full_notes = f"COACH RATE (confirmed): {manual_rate}\n\n{extra_notes}"
                    if "accent_result" in st.session_state:
                        ar = st.session_state["accent_result"]
                        full_notes += (
                            f"\n\nAUTO ACCENT ANALYSIS: {ar.get('recommendation','')} | "
                            f"Speaker: {ar.get('speaker_profile','')} | "
                            f"Grammar: {ar.get('grammar_quality','')} | "
                            f"Fluency: {ar.get('fluency','')}"
                        )
                    result = analyze_coach(
                        coach_data, form_text, language_type,
                        full_notes, final_spanish, video_english, api_key,
                        upwork_link=upwork_link, cv_link=cv_link,
                    )

                if result:
                    # Attach upwork/cv links to result for display
                    result["upwork_link"] = upwork_link
                    result["cv_link"] = cv_link
                    save_to_log(result)
                    render_results(result)
                    st.session_state["last_result"] = result

        elif "last_result" in st.session_state and not ready:
            st.info("Previous result shown below. Configure and run a new analysis above.")
            render_results(st.session_state["last_result"])

    # ══════════════════════════════════════════════════════════════════
    with tab_log:
        st.markdown("## 📋 Team Results Log")
        st.markdown("Every coach analyzed is saved here automatically. Share the file or this view with your team.")

        df_log = load_log()

        if df_log is not None:
            # Summary stats
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Total Analyzed", len(df_log))
            col2.metric("Hire", len(df_log[df_log["verdict"] == "HIRE"]))
            col3.metric("Consider", len(df_log[df_log["verdict"] == "CONSIDER"]))
            col4.metric("Do Not Hire", len(df_log[df_log["verdict"] == "DO NOT HIRE"]))

            st.markdown("<br>", unsafe_allow_html=True)

            # Color-coded table
            def highlight_verdict(val):
                if val == "HIRE":
                    return "background-color: #d4edda; color: #155724; font-weight: bold;"
                elif val == "CONSIDER":
                    return "background-color: #fff3cd; color: #856404; font-weight: bold;"
                elif val == "DO NOT HIRE":
                    return "background-color: #f8d7da; color: #721c24; font-weight: bold;"
                return ""

            styled = df_log.style.applymap(highlight_verdict, subset=["verdict"])
            st.dataframe(styled, use_container_width=True, height=400)

            st.markdown("<br>", unsafe_allow_html=True)

            # Download log as CSV
            csv_data = df_log.to_csv(index=False).encode("utf-8")
            b64_csv = base64.b64encode(csv_data).decode()
            st.markdown(
                f'<a href="data:text/csv;base64,{b64_csv}" download="coach_results_log.csv" '
                f'style="display:inline-block; background:#1e3a5f; color:white; '
                f'padding:0.6rem 1.5rem; border-radius:6px; text-decoration:none; font-weight:600;">'
                f"⬇️ Download Full Log as Excel/CSV</a>",
                unsafe_allow_html=True,
            )
            st.markdown(
                f"<small style='color:#888;'>File also saved at: `{LOG_FILE}`</small>",
                unsafe_allow_html=True,
            )
        else:
            st.info("No coaches analyzed yet. Run your first analysis and it will appear here automatically.")


if __name__ == "__main__":
    main()
