"""Render design/DESIGN.md to a one-page PDF.

Usage:
    python scripts/make_design_pdf.py --name "Your Full Name" --email you@example.com

Produces design/<Name>_<Email>_Eightfold.pdf (spaces in the name become
underscores), matching the required deliverable filename.
"""

import argparse
import os
import re

from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(HERE, "design", "DESIGN.md")


def _inline(text: str) -> str:
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"`(.+?)`", r'<font face="Courier">\1</font>', text)
    return text


def build(name: str, email: str) -> str:
    title_style = ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=12,
                                 leading=14, spaceAfter=2)
    sub_style = ParagraphStyle("sub", fontName="Helvetica", fontSize=7.5,
                               leading=9, textColor="#555555", spaceAfter=4)
    h2 = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=8.5,
                        leading=10, spaceBefore=4, spaceAfter=1)
    body = ParagraphStyle("body", fontName="Helvetica", fontSize=7.2,
                          leading=8.6, alignment=TA_LEFT, spaceAfter=1)
    bullet = ParagraphStyle("bullet", parent=body, leftIndent=8)

    story = []
    pending_bullets = []

    def flush_bullets():
        if pending_bullets:
            story.append(ListFlowable(
                [ListItem(Paragraph(b, bullet), leftIndent=8, value="•")
                 for b in pending_bullets],
                bulletType="bullet", start="•", leftIndent=10, spaceAfter=2,
            ))
            pending_bullets.clear()

    with open(SRC, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    for raw in lines:
        line = raw.rstrip()
        if not line:
            flush_bullets()
            continue
        if line.startswith("# "):
            flush_bullets()
            story.append(Paragraph(_inline(line[2:]), title_style))
            story.append(Paragraph(f"{name} &lt;{email}&gt;", sub_style))
        elif line.startswith("## "):
            flush_bullets()
            story.append(Paragraph(_inline(line[3:]), h2))
        elif re.match(r"^(\-|\d+\.)\s+", line):
            content = re.sub(r"^(\-|\d+\.)\s+", "", line)
            pending_bullets.append(_inline(content))
        else:
            flush_bullets()
            story.append(Paragraph(_inline(line), body))
    flush_bullets()

    safe_name = name.strip().replace(" ", "_")
    safe_email = email.strip().replace("@", "_at_") if "@" in email and False else email.strip()
    out_path = os.path.join(HERE, "design", f"{safe_name}_{safe_email}_Eightfold.pdf")
    doc = SimpleDocTemplate(
        out_path, pagesize=LETTER,
        leftMargin=0.55 * inch, rightMargin=0.55 * inch,
        topMargin=0.5 * inch, bottomMargin=0.5 * inch,
    )
    doc.build(story)
    return out_path


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="Your Full Name")
    ap.add_argument("--email", default="your.email@example.com")
    args = ap.parse_args()
    print("wrote", build(args.name, args.email))
