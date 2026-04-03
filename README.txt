============================================
  COACH HIRING ASSISTANT
  Automated evaluation for French & Spanish coaches
============================================

WHAT IT DOES
------------
- Reads the coach's folder (CV, certificates, transcripts, notes)
- Extracts text from PDFs and Word documents automatically
- Detects submitted video files
- Loads Google Forms responses (via CSV upload or Google Sheets URL)
- Uses AI (Claude) to score and give a hire/don't hire recommendation
- Shows a full report with scores, strengths, concerns, and next action


FIRST-TIME SETUP (do this once)
---------------------------------
Step 1: Install Python
  - Go to: https://www.python.org/downloads/
  - Download Python 3.10 or newer
  - Run the installer
  - IMPORTANT: Check "Add python.exe to PATH" before clicking Install
  - Restart your computer after installation

Step 2: Get an Anthropic API Key
  - Go to: https://console.anthropic.com/
  - Sign up / log in
  - Go to "API Keys" and create a new key
  - Copy the key (starts with sk-ant-...)
  - Keep it safe — you'll paste it into the app each time

Step 3: Run setup
  - Double-click setup.bat (do this only once)
  - Wait for packages to install


RUNNING THE APP
---------------
  - Double-click run.bat
  - The app opens automatically in your browser at http://localhost:8501


HOW TO USE
----------
1. Paste your Anthropic API key in the sidebar
2. Select "French" or "Spanish" as the coach language
3. Choose the coach's folder from the dropdown (or paste the path)
4. Provide Google Forms data:
   - Option A: Export your Google Sheet as CSV (File > Download > CSV)
               and upload it in the sidebar
   - Option B: Paste the Google Sheets URL (sheet must be set to
               "Anyone with the link can view")
   - Option C: Skip if you don't have form data yet
5. Add any personal notes you have about the coach (optional)
6. Click "Analyze Coach Application"
7. Review the full report and scoring

SCORING SYSTEM
--------------
  80-100  =>  HIRE
  55-79   =>  CONSIDER (flag for review)
  0-54    =>  DO NOT HIRE

Scoring categories:
  - Native Language & Origin     (0-20 pts)
  - Education & Credentials      (0-25 pts)
  - Teaching Experience          (0-20 pts)
  - English Proficiency          (0-15 pts)
  - Video Submission             (0-10 pts)
  - Form & Quiz Performance      (0-10 pts)

FOLDER STRUCTURE EXPECTED
--------------------------
Each coach should have their own folder, e.g.:

  French Coaches/
    Coach Name (Country) (Platform)/
      CV.pdf
      Certificate.pdf
      Transcript.pdf
      Note.docx
      Video_Fr.mp4
      Video_En.mp4

  Spanish Coaches/
    Coach Name (Country) (Platform)/
      CV.pdf
      ...

FILES SUPPORTED
---------------
  PDFs       - CV, certificates, transcripts, degree documents
  DOCX/DOC   - Notes, additional documents
  Videos     - mp4, mov, avi, mkv, webm, m4v
               (The AI checks if both language videos are present)

TIPS
----
- The more files in the folder, the better the analysis
- Add your own notes in the "Reviewer Notes" box for personal observations
- Download the JSON report after each analysis to keep records
- Run a new analysis for each coach; results don't carry over


============================================
  Questions? Ask your team's AI assistant.
============================================
