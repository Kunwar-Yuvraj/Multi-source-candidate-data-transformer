"""Generate the sample resume PDF used as the unstructured input.

Run once to (re)create the binary fixture under samples/resumes/.

    python scripts/make_sample_resumes.py
"""

import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "samples", "resumes")

JANE_LINES = [
    "Jane Doe",
    "jane.doe@example.com | +1 415 555 0132 | San Francisco, CA",
    "https://linkedin.com/in/janedoe | https://github.com/janedoe",
    "",
    "Experience",
    "Senior Software Engineer at Acme Corp, Mar 2021 - present",
    "Software Engineer at Initech, 2018 - 2021",
    "",
    "Education",
    "B.S. in Computer Science, UC Berkeley, 2016",
    "",
    "Skills",
    "Python, TypeScript, React, Node.js, AWS, Docker, PostgreSQL",
]


def make_pdf():
    from reportlab.lib.pagesizes import LETTER
    from reportlab.pdfgen import canvas

    path = os.path.join(OUT, "jane_doe_resume.pdf")
    c = canvas.Canvas(path, pagesize=LETTER)
    width, height = LETTER
    y = height - 72
    for line in JANE_LINES:
        c.drawString(72, y, line)
        y -= 18
    c.showPage()
    c.save()
    print("wrote", path)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    make_pdf()
