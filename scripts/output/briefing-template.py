"""
AI Industry Briefing PDF Generator — Data-driven template.

The rendering engine is static. The agent writes ONLY a JSON data file,
then runs this script with the data file path as argument.

Usage:
  1. Agent writes briefing data to a JSON file (e.g., briefing-data.json)
  2. Run: python briefing-template.py briefing-data.json
  3. Output: C:/reports/ai/<YYYY-MM-DD>/ai-briefing.pdf

The JSON data file schema is documented at the bottom of this script.

Dependencies: pip install reportlab
"""
import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.lib.enums import TA_CENTER

from config import REPORTS_ROOT

TODAY = date.today().strftime("%Y-%m-%d")
OUTPUT_DIR = os.path.join(REPORTS_ROOT, TODAY)
OUTPUT = os.path.join(OUTPUT_DIR, "ai-briefing.pdf")

_base = getSampleStyleSheet()

STYLES = {
    "title": ParagraphStyle("BriefTitle", parent=_base["Title"],
        fontSize=26, leading=32, textColor=HexColor("#1a1a2e"), spaceAfter=6),
    "subtitle": ParagraphStyle("BriefSubtitle", parent=_base["Normal"],
        fontSize=13, leading=16, textColor=HexColor("#555555"),
        alignment=TA_CENTER, spaceAfter=20),
    "h1": ParagraphStyle("H1", parent=_base["Heading1"],
        fontSize=18, leading=22, textColor=HexColor("#0f3460"),
        spaceBefore=18, spaceAfter=10),
    "h2": ParagraphStyle("H2", parent=_base["Heading2"],
        fontSize=14, leading=17, textColor=HexColor("#16213e"),
        spaceBefore=12, spaceAfter=6),
    "h3": ParagraphStyle("H3", parent=_base["Heading3"],
        fontSize=12, leading=15, textColor=HexColor("#1a1a2e"),
        spaceBefore=8, spaceAfter=4),
    "body": ParagraphStyle("Body", parent=_base["Normal"],
        fontSize=10, leading=14, textColor=HexColor("#333333"), spaceAfter=4),
    "bullet": ParagraphStyle("Bullet", parent=_base["Normal"],
        fontSize=10, leading=14, textColor=HexColor("#333333"),
        leftIndent=16, bulletIndent=6, spaceAfter=3),
    "link": ParagraphStyle("Link", parent=_base["Normal"],
        fontSize=8, textColor=HexColor("#0066cc"), spaceAfter=8),
    "source": ParagraphStyle("Source", parent=_base["Normal"],
        fontSize=9, textColor=HexColor("#888888"), spaceAfter=2),
    "footer": ParagraphStyle("Footer", parent=_base["Normal"],
        fontSize=8, textColor=HexColor("#999999"),
        alignment=TA_CENTER, spaceBefore=20),
    "source_list": ParagraphStyle("SourceList", parent=_base["Normal"],
        fontSize=10, textColor=HexColor("#555555"), alignment=TA_CENTER),
    "commentary": ParagraphStyle("Commentary", parent=_base["Normal"],
        fontSize=9.5, leading=13, textColor=HexColor("#2d6a4f"),
        leftIndent=8, rightIndent=8, spaceBefore=4, spaceAfter=2,
        backColor=HexColor("#f0f7f4"), borderPadding=4),
    "prediction": ParagraphStyle("Prediction", parent=_base["Normal"],
        fontSize=9.5, leading=13, textColor=HexColor("#6b4e00"),
        leftIndent=8, rightIndent=8, spaceBefore=2, spaceAfter=6,
        backColor=HexColor("#fff9e6"), borderPadding=4),
    "personal_header": ParagraphStyle("PersonalHeader", parent=_base["Heading1"],
        fontSize=18, leading=22, textColor=HexColor("#7b2d8e"),
        spaceBefore=18, spaceAfter=10),
    "personal_sub": ParagraphStyle("PersonalSub", parent=_base["Heading3"],
        fontSize=12, leading=15, textColor=HexColor("#7b2d8e"),
        spaceBefore=8, spaceAfter=4),
    "personal_bullet": ParagraphStyle("PersonalBullet", parent=_base["Normal"],
        fontSize=10, leading=14, textColor=HexColor("#4a1259"),
        leftIndent=16, bulletIndent=6, spaceAfter=3,
        backColor=HexColor("#f9f0fc"), borderPadding=3),
    "skill_header": ParagraphStyle("SkillHeader", parent=_base["Heading1"],
        fontSize=18, leading=22, textColor=HexColor("#1a6b3e"),
        spaceBefore=18, spaceAfter=10),
    "skill_sub": ParagraphStyle("SkillSub", parent=_base["Heading3"],
        fontSize=12, leading=15, textColor=HexColor("#1a6b3e"),
        spaceBefore=8, spaceAfter=4),
    "skill_body": ParagraphStyle("SkillBody", parent=_base["Normal"],
        fontSize=10, leading=14, textColor=HexColor("#1a4d2e"),
        leftIndent=8, rightIndent=8, spaceAfter=3,
        backColor=HexColor("#e8f5e9"), borderPadding=4),
}

def hr():
    return HRFlowable(width="100%", thickness=0.5, color=HexColor("#cccccc"),
                      spaceBefore=8, spaceAfter=8)

def make_table(data, col_widths=None):
    if col_widths is None:
        col_widths = [130, 75, 230, 55]
    tbl = Table(data, colWidths=col_widths)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HexColor("#0f3460")),
        ("TEXTCOLOR", (0, 0), (-1, 0), HexColor("#ffffff")),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("ALIGN", (1, 0), (1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.4, HexColor("#cccccc")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor("#f8f8f8"), HexColor("#ffffff")]),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    return tbl


def build(data):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    doc = SimpleDocTemplate(
        OUTPUT, pagesize=A4,
        leftMargin=20*mm, rightMargin=20*mm,
        topMargin=20*mm, bottomMargin=20*mm
    )
    story = []
    S = STYLES

    sources_used = data.get("sources_used", [])
    sources_unavailable = data.get("sources_unavailable", [])

    # Title
    story.append(Spacer(1, 40))
    story.append(Paragraph("AI Industry Briefing", S["title"]))
    story.append(Paragraph(TODAY, S["subtitle"]))
    story.append(Paragraph(
        f"Sources: {', '.join(sources_used)}", S["source_list"]
    ))
    story.append(Spacer(1, 10))
    story.append(hr())

    # Week in Review (if present)
    wir = data.get("week_in_review")
    if wir:
        story.append(Paragraph("Week in Review", S["h1"]))
        if wir.get("dominant_themes"):
            story.append(Paragraph("Dominant Themes This Week", S["h3"]))
            for t in wir["dominant_themes"]:
                story.append(Paragraph(
                    f"&bull; <b>{t['theme']}</b>: appeared in {t['mentions']} briefings, trend: {t['trend']}",
                    S["bullet"]
                ))
        if wir.get("new_this_week"):
            story.append(Paragraph("New This Week", S["h3"]))
            for t in wir["new_this_week"]:
                story.append(Paragraph(
                    f"&bull; <b>{t['topic']}</b> (first seen {t['first_seen']}): {t['significance']}",
                    S["bullet"]
                ))
        if wir.get("continuing"):
            story.append(Paragraph("Continuing Trends", S["h3"]))
            for t in wir["continuing"]:
                story.append(Paragraph(
                    f"&bull; <b>{t['topic']}</b>: {t['evolution']}",
                    S["bullet"]
                ))
        if wir.get("faded"):
            story.append(Paragraph("What Faded", S["h3"]))
            for t in wir["faded"]:
                story.append(Paragraph(
                    f"&bull; <b>{t['topic']}</b>: {t.get('note', 'Not mentioned this week')}",
                    S["bullet"]
                ))
        story.append(hr())

    # Per-Source Sections
    for source in data.get("per_source_data", []):
        story.append(Paragraph(
            f"{source['name']} <font size=8 color='#888888'>({source['category']})</font>",
            S["h1"]
        ))
        for i, item in enumerate(source["items"], 1):
            story.append(Paragraph(f"{i}. {item['title']}", S["h2"]))
            date_str = f" | <b>Date:</b> {item['date']}" if item.get("date") else ""
            story.append(Paragraph(
                f"<b>Source:</b> {source['name']}{date_str}", S["source"]
            ))
            if item.get("summary"):
                story.append(Paragraph(item["summary"], S["body"]))
            for pt in item.get("points", []):
                story.append(Paragraph(f"&bull; {pt}", S["bullet"]))
            if item.get("url"):
                story.append(Paragraph(
                    f'<link href="{item["url"]}">{item["url"]}</link>', S["link"]
                ))
            if item.get("commentary"):
                story.append(Paragraph(
                    f'<b>Analyst Note:</b> {item["commentary"]}', S["commentary"]
                ))
            if item.get("prediction"):
                story.append(Paragraph(
                    f'<b>Impact Forecast:</b> {item["prediction"]}', S["prediction"]
                ))
        story.append(hr())

    # GitHub Trending / Tools table
    tools_data = data.get("tools_data", [])
    if tools_data:
        story.append(Paragraph("GitHub Trending &amp; Developer Tools", S["h1"]))
        table_data = [["Project", "Stars (Today)", "Description", "Language"]] + tools_data
        story.append(make_table(table_data))
        story.append(Spacer(1, 6))
        story.append(Paragraph(
            f"<i>Source: GitHub Trending (daily) — {TODAY}</i>", S["source"]
        ))
        story.append(hr())

    # Industry Pulse
    company_moves = data.get("company_moves", [])
    community_buzz = data.get("community_buzz", [])
    cross_cutting = data.get("cross_cutting_analysis", "")
    big_picture = data.get("big_picture_forecast", "")
    if company_moves or community_buzz:
        story.append(Paragraph("Industry Pulse", S["h1"]))
        if company_moves:
            story.append(Paragraph("Company Moves &amp; Funding", S["h3"]))
            for m in company_moves:
                story.append(Paragraph(f"&bull; {m}", S["bullet"]))
        if community_buzz:
            story.append(Paragraph("Community Buzz &amp; Culture", S["h3"]))
            for b in community_buzz:
                story.append(Paragraph(f"&bull; {b}", S["bullet"]))
        if cross_cutting:
            story.append(Spacer(1, 8))
            story.append(Paragraph(cross_cutting, S["commentary"]))
        if big_picture:
            story.append(Paragraph(big_picture, S["prediction"]))
        story.append(hr())

    # What This Means For Me (MANDATORY)
    pr = data.get("personal_relevance")
    if pr:
        story.append(Paragraph("What This Means For Me", S["personal_header"]))
        story.append(Paragraph(
            "<i>Personalized for: Java backend developer | Medical imaging / medtech (DICOM, FHIR, radiology) | "
            "Java, Spring, Vaadin, FHIR, DICOM stack</i>", S["source"]
        ))
        story.append(Spacer(1, 6))
        if pr.get("direct"):
            story.append(Paragraph("Direct Relevance (may affect your work)", S["personal_sub"]))
            for d in pr["direct"]:
                story.append(Paragraph(f"&bull; {d}", S["personal_bullet"]))
        if pr.get("watch"):
            story.append(Paragraph("Worth Watching (6-12 month horizon)", S["personal_sub"]))
            for w in pr["watch"]:
                story.append(Paragraph(f"&bull; {w}", S["personal_bullet"]))
        if pr.get("learn"):
            story.append(Paragraph("Skill Development Opportunity", S["personal_sub"]))
            for item in pr["learn"]:
                story.append(Paragraph(f"&bull; {item}", S["personal_bullet"]))
        story.append(hr())

    # Skill Radar (MANDATORY)
    skill_radar = data.get("skill_radar", [])
    if skill_radar:
        story.append(Paragraph("Skill Radar", S["skill_header"]))
        story.append(Paragraph(
            "<i>AI knowledge &amp; hands-on learning from today's news — tailored to Java/Spring/medtech</i>",
            S["source"]
        ))
        story.append(Spacer(1, 6))
        for sr in skill_radar:
            sr_type = sr.get("type", "Tool")
            type_tag = f' <font size=8 color="#888888">[{sr_type}]</font>'
            story.append(Paragraph(f"{sr.get('name', '')}{type_tag}", S["skill_sub"]))
            if sr.get("key_insight"):
                story.append(Paragraph(
                    f"<b>Key insight:</b> {sr['key_insight']}", S["skill_body"]
                ))
            if sr.get("why"):
                story.append(Paragraph(
                    f"<b>Why learn this:</b> {sr['why']}", S["skill_body"]
                ))
            if sr.get("get_started"):
                story.append(Paragraph(
                    f'<b>Get started:</b> <link href="{sr["get_started"]}">{sr["get_started"]}</link>',
                    S["skill_body"]
                ))
            if sr.get("time"):
                story.append(Paragraph(
                    f"<b>Time investment:</b> {sr['time']}", S["skill_body"]
                ))
            if sr.get("applies_to"):
                story.append(Paragraph(
                    f"<b>Applies to:</b> {sr['applies_to']}", S["skill_body"]
                ))
            story.append(Spacer(1, 4))
        story.append(hr())

    # Footer
    unavail = ""
    if sources_unavailable:
        unavail = f"<br/>Unavailable: {', '.join(sources_unavailable)}"
    story.append(Paragraph(
        f"Generated by AI Briefing Skill on {TODAY}<br/>"
        f"Sources: {', '.join(sources_used)}{unavail}",
        S["footer"]
    ))

    doc.build(story)
    print(f"PDF saved to: {OUTPUT}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python briefing-template.py <data.json>")
        print("The agent writes a JSON data file, this script renders it to PDF.")
        sys.exit(1)

    data_path = sys.argv[1]
    with open(data_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    build(data)


# ============================================================
# JSON DATA FILE SCHEMA (for agent reference)
# ============================================================
# {
#   "sources_used": ["Source 1", "Source 2", ...],
#   "sources_unavailable": ["Source X"],
#   "week_in_review": null | {
#     "dominant_themes": [{"theme": "...", "mentions": 5, "trend": "growing"}],
#     "new_this_week": [{"topic": "...", "first_seen": "April 3", "significance": "..."}],
#     "continuing": [{"topic": "...", "evolution": "..."}],
#     "faded": [{"topic": "...", "note": "..."}]
#   },
#   "per_source_data": [
#     {
#       "name": "Source Name",
#       "category": "Deep Tech &amp; Papers",
#       "items": [
#         {
#           "title": "...",
#           "date": "April 6, 2026",
#           "summary": "...",
#           "points": ["point 1", "point 2"],
#           "url": "https://...",
#           "commentary": "Analyst note...",
#           "prediction": "Impact forecast..."
#         }
#       ]
#     }
#   ],
#   "tools_data": [["repo/name", "stars (+today)", "description", "language"]],
#   "company_moves": ["<b>Company</b>: description"],
#   "community_buzz": ["<b>Topic</b>: description"],
#   "cross_cutting_analysis": "HTML-formatted analyst note",
#   "big_picture_forecast": "HTML-formatted forecast",
#   "personal_relevance": {
#     "direct": ["item 1", "item 2"],
#     "watch": ["item 1", "item 2"],
#     "learn": ["item 1", "item 2"]
#   },
#   "skill_radar": [
#     {
#       "name": "Per-Layer Embeddings",
#       "type": "Concept",
#       "key_insight": "Instead of dense computation, parameters act as lookup tables...",
#       "why": "Understanding this helps evaluate which models can run on clinic hardware",
#       "get_started": "https://www.reddit.com/r/LocalLLaMA/comments/...",
#       "time": "15 min read",
#       "applies_to": "Evaluating edge-deployable AI for radiology workstations"
#     },
#     {
#       "name": "Block's goose agent",
#       "type": "Tool",
#       "key_insight": "Open-source AI agent that can execute, edit, and test code",
#       "why": "Could automate repetitive Java/Spring backend tasks",
#       "get_started": "https://github.com/block/goose",
#       "time": "1 hour to try",
#       "applies_to": "Automating FHIR resource generation and test suites"
#     }
#   ]
# }
