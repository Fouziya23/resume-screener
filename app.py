from flask import Flask, request, render_template, jsonify
from PyPDF2 import PdfReader
from docx import Document
from rapidfuzz import fuzz
import re
import os

app = Flask(__name__)

# ── Stop words (no nltk needed) ──────────────────────────────────────────────
STOP_WORDS = set([
    "a","an","the","and","or","but","in","on","at","to","for","of","with",
    "by","from","is","are","was","were","be","been","being","have","has",
    "had","do","does","did","will","would","could","should","may","might",
    "shall","can","need","must","am","it","its","this","that","these","those",
    "we","our","you","your","they","their","i","my","he","she","his","her",
    "as","if","so","not","no","nor","yet","both","either","each","more",
    "most","other","some","such","than","then","when","where","who","which",
    "how","all","any","few","into","through","during","before","after",
    "above","below","between","out","off","over","under","again","further",
    "there","here","just","also","about","up","down","what","only","same"
])

# ── Key skills to always check ────────────────────────────────────────────────
SKILL_ALIASES = {
    "sql": ["sql", "mysql", "postgresql", "mssql", "sql server", "t-sql", "pl/sql"],
    "python": ["python", "pandas", "numpy", "matplotlib", "seaborn", "scikit-learn"],
    "power bi": ["power bi", "powerbi", "dax", "power query"],
    "tableau": ["tableau"],
    "excel": ["excel", "vlookup", "pivot table", "xlookup", "index match"],
    "machine learning": ["machine learning", "ml", "random forest", "classification", "regression", "predictive modeling"],
    "statistics": ["statistics", "statistical analysis", "hypothesis testing", "p-value", "regression"],
    "data visualization": ["data visualization", "dashboard", "visualization", "charts", "reporting"],
    "communication": ["communication", "stakeholder", "presentation", "storytelling"],
    "etl": ["etl", "data pipeline", "data warehouse", "data integration"],
    "r": ["r programming", " r ", "ggplot", "dplyr"],
    "spark": ["spark", "pyspark", "hadoop", "big data"],
    "azure": ["azure", "aws", "cloud", "gcp"],
    "git": ["git", "github", "version control"],
}

ATS_BREAKERS = [
    ("tables", r"<w:tbl>"),
    ("images", r"<wp:inline|<wp:anchor"),
    ("headers/footers", r"<w:hdr>|<w:ftr>"),
    ("text boxes", r"<w:txbxContent>"),
]

IMPORTANT_SECTIONS = [
    "experience", "education", "skills", "projects",
    "summary", "objective", "certifications", "work experience"
]

# ── Text extraction ───────────────────────────────────────────────────────────
def extract_text_from_pdf(file):
    reader = PdfReader(file)
    return " ".join(page.extract_text() or "" for page in reader.pages)

def extract_text_from_docx(file):
    doc = Document(file)
    return " ".join(p.text for p in doc.paragraphs)

def extract_text(file):
    name = file.filename.lower()
    if name.endswith(".pdf"):
        return extract_text_from_pdf(file)
    elif name.endswith(".docx"):
        return extract_text_from_docx(file)
    return ""

# ── Keyword extraction from JD ────────────────────────────────────────────────
def extract_keywords(text):
    text = text.lower()
    # extract multi-word skill phrases first
    phrases = []
    for canonical, aliases in SKILL_ALIASES.items():
        for alias in aliases:
            if alias.strip() in text:
                phrases.append(canonical)
                break

    # extract single meaningful words
    words = re.findall(r'\b[a-zA-Z][a-zA-Z0-9\+\#\.]*\b', text)
    keywords = [w.lower() for w in words if w.lower() not in STOP_WORDS and len(w) > 2]

    # frequency count
    freq = {}
    for kw in keywords:
        freq[kw] = freq.get(kw, 0) + 1

    # top keywords by frequency, skip very common resume words
    skip = {"experience", "work", "team", "role", "company", "job", "position",
            "candidate", "required", "preferred", "including", "responsibilities",
            "qualifications", "requirements", "ability", "strong", "good", "using",
            "knowledge", "understanding", "working", "based", "across", "within"}

    top_words = [k for k, v in sorted(freq.items(), key=lambda x: -x[1])
                 if k not in skip and v >= 1][:30]

    all_keywords = list(dict.fromkeys(phrases + top_words))
    return all_keywords

# ── Fuzzy keyword matching ────────────────────────────────────────────────────
def match_keywords(resume_text, keywords):
    resume_lower = resume_text.lower()
    matched = []
    missing = []

    for kw in keywords:
        # direct match first
        if kw.lower() in resume_lower:
            matched.append(kw)
            continue
        # fuzzy match
        score = fuzz.partial_ratio(kw.lower(), resume_lower)
        if score >= 85:
            matched.append(kw)
        else:
            missing.append(kw)

    return matched, missing

# ── Section detection ─────────────────────────────────────────────────────────
def detect_sections(resume_text):
    text_lower = resume_text.lower()
    found = []
    missing = []
    for section in IMPORTANT_SECTIONS:
        if section in text_lower:
            found.append(section.title())
        else:
            missing.append(section.title())
    return found, missing

# ── Word count / length check ─────────────────────────────────────────────────
def check_length(resume_text):
    words = len(resume_text.split())
    if words < 200:
        return "Too short", "danger"
    elif words > 900:
        return "May be too long (aim for 1 page)", "warning"
    else:
        return "Good length", "success"

# ── Contact info check ────────────────────────────────────────────────────────
def check_contact(resume_text):
    checks = {
        "Email": bool(re.search(r'[\w\.-]+@[\w\.-]+\.\w+', resume_text)),
        "Phone": bool(re.search(r'[\+\d][\d\s\-\(\)]{8,}', resume_text)),
        "LinkedIn": bool(re.search(r'linkedin', resume_text, re.I)),
        "GitHub": bool(re.search(r'github', resume_text, re.I)),
    }
    return checks

# ── Score calculator ──────────────────────────────────────────────────────────
def calculate_score(matched, total_keywords, sections_found, total_sections, contact_checks, length_status):
    keyword_score = (len(matched) / max(total_keywords, 1)) * 50
    section_score = (len(sections_found) / max(total_sections, 1)) * 25
    contact_score = (sum(contact_checks.values()) / len(contact_checks)) * 15
    length_score = 10 if length_status == "Good length" else 5
    total = int(keyword_score + section_score + contact_score + length_score)
    return min(total, 100)

def score_label(score):
    if score >= 80:
        return "Strong Match", "success"
    elif score >= 60:
        return "Good Match", "info"
    elif score >= 40:
        return "Moderate Match", "warning"
    else:
        return "Weak Match", "danger"

# ── Routes ────────────────────────────────────────────────────────────────────
@app.route("/", methods=["GET"])
def home():
    return render_template("index.html")

@app.route("/scan", methods=["POST"])
def scan():
    resume_file = request.files.get("resume")
    jd_text = request.form.get("jd_text", "").strip()
    candidate_name = request.form.get("name", "Candidate").strip()

    if not resume_file or not jd_text:
        return render_template("index.html", error="Please upload a resume and paste the job description.")

    resume_text = extract_text(resume_file)
    if not resume_text.strip():
        return render_template("index.html", error="Could not read resume. Make sure it's a text-based PDF or DOCX.")

    # Analysis
    keywords = extract_keywords(jd_text)
    matched, missing = match_keywords(resume_text, keywords)
    sections_found, sections_missing = detect_sections(resume_text)
    length_status, length_color = check_length(resume_text)
    contact_checks = check_contact(resume_text)
    score = calculate_score(matched, len(keywords), sections_found,
                            len(IMPORTANT_SECTIONS), contact_checks, length_status)
    label, label_color = score_label(score)

    # Top missing keywords to add (max 10)
    top_missing = missing[:10]

    return render_template("result.html",
        name=candidate_name,
        score=score,
        label=label,
        label_color=label_color,
        matched=matched,
        missing=missing,
        top_missing=top_missing,
        sections_found=sections_found,
        sections_missing=sections_missing,
        length_status=length_status,
        length_color=length_color,
        contact_checks=contact_checks,
        total_keywords=len(keywords),
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=True)
