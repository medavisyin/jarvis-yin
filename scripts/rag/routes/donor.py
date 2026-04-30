"""Cryos donor analysis API — Flask blueprint (extracted from agent.py)."""

import json
import os
import sys
from datetime import datetime

from flask import Blueprint, Response, jsonify, request

# Ensure scripts/ is importable when this module loads standalone
_scripts_dir = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
)
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)
from config import REPORTS_ROOT  # noqa: E402

# Match agent.py defaults for donor LLM reasoning
OLLAMA_MODEL = os.environ.get("RAG_AGENT_MODEL", "qwen3.5:4b")
OLLAMA_HOST = "http://localhost:11434"

donor_bp = Blueprint("donor", __name__)


def _score_donor(donor: dict, recipient_cmv: str = "negative") -> dict:
    """Score a donor based on clinical criteria. Returns score breakdown."""
    scores = {}
    total = 0.0

    mot_score = 0
    stock = donor.get("stock", [])
    if isinstance(stock, list):
        for s in stock:
            t = s.get("type", "") if isinstance(s, dict) else str(s)
            if "MOT30" in t:
                mot_score = max(mot_score, 3)
            elif "MOT20" in t:
                mot_score = max(mot_score, 2)
            elif "MOT10" in t:
                mot_score = max(mot_score, 1)
    motility = donor.get("motility", "")
    if "IUI" in motility:
        mot_score += 0.5
    scores["sperm_quality"] = round(min(mot_score, 3.5) / 3.5 * 30, 1)
    total += scores["sperm_quality"]

    cmv = donor.get("cmv_status", "").lower()
    if recipient_cmv == "negative":
        scores["cmv_match"] = 20.0 if "neg" in cmv else 0.0
    else:
        scores["cmv_match"] = 20.0
    total += scores["cmv_match"]

    gen = donor.get("genetic_matching", "").lower()
    scores["genetic_screening"] = 10.0 if gen == "yes" else 0.0
    total += scores["genetic_screening"]

    stock_total = 0
    if isinstance(stock, list):
        for s in stock:
            details = s.get("details", "") if isinstance(s, dict) else ""
            nums = [int(x) for x in str(details).split() if x.isdigit()]
            stock_total += sum(nums)
    if stock_total >= 10:
        scores["stock_availability"] = 15.0
    elif stock_total >= 5:
        scores["stock_availability"] = 10.0
    elif stock_total >= 1:
        scores["stock_availability"] = 5.0
    else:
        scores["stock_availability"] = 0.0
    total += scores["stock_availability"]

    id_rel = donor.get("id_release", donor.get("id_option", "")).lower()
    scores["id_release"] = 5.0 if "yes" in id_rel or "release" in id_rel else 0.0
    total += scores["id_release"]

    face = donor.get("cryos_face_matching", "").lower()
    scores["face_matching"] = 5.0 if face == "yes" else 0.0
    total += scores["face_matching"]

    profile = donor.get("profile_type", "").lower()
    scores["profile_depth"] = 5.0 if profile == "extended" else 2.0
    total += scores["profile_depth"]

    height_str = donor.get("height__cm", "0")
    try:
        height = int(height_str)
    except (ValueError, TypeError):
        height = 0
    if 175 <= height <= 190:
        scores["physical_preference"] = 10.0
    elif 170 <= height <= 195:
        scores["physical_preference"] = 7.0
    elif height > 0:
        scores["physical_preference"] = 4.0
    else:
        scores["physical_preference"] = 0.0
    total += scores["physical_preference"]

    scores["total"] = round(total, 1)
    return scores


@donor_bp.route("/api/donor-analysis", methods=["GET"])
def api_donor_analysis():
    """Return all donors with scores."""
    recipient_cmv = request.args.get("recipient_cmv", "negative")
    donors_file = os.path.join(REPORTS_ROOT, datetime.now().strftime("%Y-%m-%d"), "cryos-donors.json")
    if not os.path.exists(donors_file):
        all_dates = sorted([d for d in os.listdir(REPORTS_ROOT)
                           if os.path.isfile(os.path.join(REPORTS_ROOT, d, "cryos-donors.json"))],
                          reverse=True)
        if all_dates:
            donors_file = os.path.join(REPORTS_ROOT, all_dates[0], "cryos-donors.json")
        else:
            return jsonify({"error": "No donor data found. Run parse-cryos-donors.py first."}), 404

    with open(donors_file, "r", encoding="utf-8") as f:
        donors = json.load(f)
    results = []
    for d in donors:
        scores = _score_donor(d, recipient_cmv)
        results.append({**d, "_scores": scores, "_total_score": scores["total"]})

    results.sort(key=lambda x: x["_total_score"], reverse=True)
    return jsonify({
        "donors": results,
        "count": len(results),
        "source_file": donors_file,
        "scoring_weights": {
            "sperm_quality": "30 (MOT level + IUI prep)",
            "cmv_match": "20 (critical for CMV-neg recipients)",
            "stock_availability": "15 (vial count)",
            "genetic_screening": "10 (carrier screening available)",
            "physical_preference": "10 (height 175-190cm optimal)",
            "id_release": "5 (identity disclosure at 18)",
            "face_matching": "5 (Cryos face matching available)",
            "profile_depth": "5 (Extended vs Basic profile)",
        }
    })


@donor_bp.route("/api/donor-analysis/ai-reason", methods=["POST"])
def api_donor_ai_reason():
    """Use a strong LLM (qwen3-vl:8b) to analyze and reason about top donors. Returns SSE stream."""
    data = request.get_json(silent=True) or {}
    top_n = data.get("top_n", 20)
    recipient_cmv = data.get("recipient_cmv", "negative")

    donors_file = os.path.join(REPORTS_ROOT, datetime.now().strftime("%Y-%m-%d"), "cryos-donors.json")
    if not os.path.exists(donors_file):
        all_dates = sorted([d for d in os.listdir(REPORTS_ROOT)
                           if os.path.isfile(os.path.join(REPORTS_ROOT, d, "cryos-donors.json"))],
                          reverse=True)
        if all_dates:
            donors_file = os.path.join(REPORTS_ROOT, all_dates[0], "cryos-donors.json")
        else:
            return jsonify({"error": "No donor data found."}), 404

    with open(donors_file, "r", encoding="utf-8") as f:
        donors = json.load(f)
    scored = []
    for d in donors:
        scores = _score_donor(d, recipient_cmv)
        scored.append({**d, "_scores": scores, "_total_score": scores["total"]})
    scored.sort(key=lambda x: x["_total_score"], reverse=True)
    top = scored[:top_n]

    summary_lines = [f"Top {top_n} Cryos Sperm Donors (recipient CMV: {recipient_cmv}):"]
    for i, d in enumerate(top, 1):
        sc = d["_scores"]
        stock_count = 0
        for s in d.get("stock", []):
            if isinstance(s, dict):
                nums = [int(x) for x in str(s.get("details", "")).split() if x.isdigit()]
                stock_count += sum(nums)
        summary_lines.append(
            f"{i}. ID={d.get('donor_id','')} Score={d['_total_score']:.0f}/100 "
            f"Race={d.get('race','')} Ethnicity={d.get('ethnicity','')} Height={d.get('height__cm','')}cm "
            f"Eyes={d.get('eye_colour','')} Hair={d.get('hair_colour','')} Blood={d.get('blood_type','')} "
            f"CMV={d.get('cmv_status','')} ShipFrom={d.get('shipped_from','')} Profile={d.get('profile_type','')} "
            f"Stock={stock_count} vials | "
            f"Quality={sc.get('sperm_quality',0)}/30 CMV={sc.get('cmv_match',0)}/20 "
            f"Stock={sc.get('stock_availability',0)}/15 Genetic={sc.get('genetic_screening',0)}/10 "
            f"Physical={sc.get('physical_preference',0)}/10"
        )

    prompt = "\n".join(summary_lines) + (
        "\n\nYou are a fertility consultant AI. Analyze these top donors in detail. For each donor:\n"
        "1. Explain WHY they scored high (which criteria contributed most)\n"
        "2. Note any concerns or trade-offs\n"
        "3. Highlight unique advantages\n\n"
        "Then provide your FINAL RECOMMENDATION: pick the best 5 donors and explain your reasoning "
        "considering sperm quality (MOT level), health matching (CMV), stock availability, "
        "genetic screening, physical characteristics, and profile completeness.\n\n"
        "Be thorough and clinical. Do NOT invent data not provided."
    )

    def generate():
        import requests as req
        try:
            resp = req.post(
                f"{OLLAMA_HOST}/api/chat",
                json={
                    "model": OLLAMA_MODEL,
                    "messages": [
                        {"role": "system", "content": "You are a clinical donor analysis expert. Be thorough and precise."},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": True,
                    "think": False,
                    "options": {"num_predict": 8192, "temperature": 0.3},
                },
                stream=True, timeout=600,
            )
            full_text = ""
            for line in resp.iter_lines():
                if line:
                    try:
                        chunk = json.loads(line)
                        token = chunk.get("message", {}).get("content", "")
                        if token:
                            full_text += token
                            yield f"data: {json.dumps({'type':'token','content':token})}\n\n"
                        if chunk.get("done"):
                            yield f"data: {json.dumps({'type':'done','content':full_text})}\n\n"
                            break
                    except json.JSONDecodeError:
                        pass
        except Exception as e:
            yield f"data: {json.dumps({'type':'error','message':str(e)})}\n\n"

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@donor_bp.route("/api/donor-analysis/pdf", methods=["POST"])
def api_donor_analysis_pdf():
    """Generate a PDF report of top donors."""
    data = request.get_json(silent=True) or {}
    top_n = data.get("top_n", 20)
    recipient_cmv = data.get("recipient_cmv", "negative")
    reason_text = data.get("reason_text", "")
    language = data.get("language", "en")

    donors_file = os.path.join(REPORTS_ROOT, datetime.now().strftime("%Y-%m-%d"), "cryos-donors.json")
    if not os.path.exists(donors_file):
        all_dates = sorted([d for d in os.listdir(REPORTS_ROOT)
                           if os.path.isfile(os.path.join(REPORTS_ROOT, d, "cryos-donors.json"))],
                          reverse=True)
        if all_dates:
            donors_file = os.path.join(REPORTS_ROOT, all_dates[0], "cryos-donors.json")
        else:
            return jsonify({"error": "No donor data found."}), 404

    with open(donors_file, "r", encoding="utf-8") as f:
        donors = json.load(f)
    scored = []
    for d in donors:
        scores = _score_donor(d, recipient_cmv)
        scored.append({**d, "_scores": scores, "_total_score": scores["total"]})
    scored.sort(key=lambda x: x["_total_score"], reverse=True)
    top = scored[:top_n]

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
    except ImportError:
        return jsonify({"error": "reportlab not installed"}), 500

    today = datetime.now().strftime("%Y-%m-%d")
    pdf_dir = os.path.join(REPORTS_ROOT, today)
    os.makedirs(pdf_dir, exist_ok=True)
    pdf_path = os.path.join(pdf_dir, f"donor-analysis-top{top_n}.pdf")

    doc = SimpleDocTemplate(pdf_path, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = []

    zh = language == "zh"
    if zh:
        try:
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.cidfonts import UnicodeCIDFont
            pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
            for s in styles.byName.values():
                s.fontName = "STSong-Light"
        except Exception:
            pass

    title_text = f"Cryos 捐赠者分析 - 前 {top_n} 名" if zh else f"Cryos Donor Analysis - Top {top_n}"
    sub_text = f"生成日期: {today} | 接受者 CMV: {recipient_cmv}" if zh else f"Generated: {today} | Recipient CMV: {recipient_cmv}"
    elements.append(Paragraph(title_text, styles["Title"]))
    elements.append(Paragraph(sub_text, styles["Normal"]))
    elements.append(Spacer(1, 12))

    if reason_text:
        rec_title = "推荐摘要:" if zh else "Recommendation Summary:"
        elements.append(Paragraph(rec_title, styles["Heading2"]))
        for line in reason_text.split("\n"):
            if line.strip():
                elements.append(Paragraph(line.strip(), styles["Normal"]))
        elements.append(Spacer(1, 12))

    if zh:
        header = ["排名", "ID", "评分", "种族", "身高", "眼睛", "头发",
                  "血型", "CMV", "发货地", "MOT", "库存"]
    else:
        header = ["Rank", "ID", "Score", "Race", "Height", "Eyes", "Hair",
                  "Blood", "CMV", "Ship From", "MOT", "Stock"]
    from reportlab.lib.styles import ParagraphStyle
    link_style = ParagraphStyle("link", parent=styles["Normal"], fontSize=7,
                                textColor=colors.HexColor("#1a73e8"), alignment=1)
    if zh:
        link_style.fontName = "STSong-Light"

    table_data = [header]
    for rank, d in enumerate(top, 1):
        stock_count = 0
        mot_best = ""
        for s in d.get("stock", []):
            if isinstance(s, dict):
                details = s.get("details", "")
                nums = [int(x) for x in str(details).split() if x.isdigit()]
                stock_count += sum(nums)
                if not mot_best:
                    mot_best = s.get("type", "")
        did = d.get("donor_id", "")
        profile_url = f"https://www.cryosinternational.com/en-gb/dk-shop/private/dk-donor-profile/?name={did}"
        id_cell = Paragraph(f'<a href="{profile_url}" color="blue">{did}</a>', link_style)
        table_data.append([
            str(rank), id_cell, f"{d['_total_score']:.0f}",
            d.get("race", ""), d.get("height__cm", ""), d.get("eye_colour", ""),
            d.get("hair_colour", ""), d.get("blood_type", ""), d.get("cmv_status", ""),
            d.get("shipped_from", ""), mot_best, str(stock_count),
        ])

    t = Table(table_data, repeatRows=1)
    table_style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2a2d3a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f0f5")]),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]
    if zh:
        table_style.append(("FONTNAME", (0, 0), (-1, -1), "STSong-Light"))
    t.setStyle(TableStyle(table_style))
    elements.append(t)
    elements.append(Spacer(1, 20))

    crit_title = "评分标准:" if zh else "Scoring Criteria:"
    elements.append(Paragraph(crit_title, styles["Heading3"]))
    if zh:
        criteria = [
            "精子质量 (30分): MOT30+=3, MOT20=2, MOT10=1; IUI-ready加分",
            "CMV匹配 (20分): 接受者CMV阴性时至关重要",
            "库存量 (15分): 10+管=15, 5+=10, 1+=5",
            "遗传筛查 (10分): 携带者筛查可用",
            "身体偏好 (10分): 身高175-190cm最佳",
            "身份公开 (5分): 18岁后身份披露选项",
            "面部匹配 (5分): Cryos面部匹配可用",
            "档案深度 (5分): Extended=5, Basic=2",
        ]
    else:
        criteria = [
            "Sperm Quality (30pts): MOT30+=3, MOT20=2, MOT10=1; IUI-ready bonus",
            "CMV Match (20pts): Critical if recipient is CMV-negative",
            "Stock Availability (15pts): 10+ vials=15, 5+=10, 1+=5",
            "Genetic Screening (10pts): Carrier screening available",
            "Physical Preference (10pts): Height 175-190cm optimal",
            "ID Release (5pts): Identity disclosure option",
            "Face Matching (5pts): Cryos face matching available",
            "Profile Depth (5pts): Extended=5, Basic=2",
        ]
    for c in criteria:
        elements.append(Paragraph(f"- {c}", styles["Normal"]))

    doc.build(elements)
    return jsonify({
        "pdf_path": pdf_path,
        "pdf_url": f"/api/toolbar/audio-file/{today}/donor-analysis-top{top_n}.pdf",
    })
