from flask import Flask, request, render_template
from PyPDF2 import PdfReader
from docx import Document
from colorama import Fore, init
import os

init(autoreset=True)
app = Flask(__name__)

# Common job titles with suggested skills
JOB_DATA = {
    "Data Analyst": ["sql", "excel", "python", "tableau", "statistics"],
    "Frontend Developer": ["javascript", "react", "html", "css", "typescript"],
    "Backend Developer": ["python", "java", "node.js", "sql", "docker"],
    "UX Designer": ["figma", "sketch", "adobe xd", "user research", "wireframing"],
    "Product Manager": ["agile", "scrum", "jira", "market research", "roadmapping"]
}

@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "POST":
        # Get inputs
        name = request.form["name"]
        job_title = request.form["job_title"]
        skills = request.form["skills"].split(",")
        
        # Handle custom job title
        if job_title == "other":
            job_title = request.form.get("custom_job", "Custom Role")
        
        # Process resume
        resume = request.files["resume"]
        text = ""
        
        if resume.filename.endswith(".pdf"):
            text = " ".join(page.extract_text().lower() for page in PdfReader(resume).pages)
        elif resume.filename.endswith(".docx"):
            text = " ".join(p.text.lower() for p in Document(resume).paragraphs)
        
        # Calculate matches
        required_skills = [s.strip().lower() for s in skills]
        matched = [s for s in required_skills if s in text]
        missing = [s for s in required_skills if s not in text]
        score = f"{len(matched)}/{len(required_skills)}"
        percentage = int((len(matched) / len(required_skills)) * 100)

        return render_template(
            "result.html",
            name=name,
            job_title=job_title,
            matched_skills=matched,
            missing_skills=missing,
            match_score=score,
            match_percentage=percentage
        )
    
    return render_template("index.html", job_data=JOB_DATA)

if __name__ == "__main__":
    app.run(debug=True)