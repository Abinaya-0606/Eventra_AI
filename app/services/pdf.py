"""PDF generation with ReportLab. Standard fonts are used, so text is limited to Latin characters:
anything else is replaced with '?' and money is written as 'Rs.' (the standard fonts have no rupee sign)."""
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (KeepTogether, ListFlowable, ListItem, PageBreak, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

NAVY, INDIGO, SOFT, LINE = colors.HexColor("#0f172a"), colors.HexColor("#4f46e5"), colors.HexColor("#eef2ff"), colors.HexColor("#e2e8f0")


def safe(text) -> str:
    """Escape for ReportLab markup and drop characters the standard fonts cannot draw."""
    clean = str(text).encode("cp1252", "replace").decode("cp1252")
    return escape(clean)


def rs(amount: float) -> str:
    return f"Rs. {amount:,.0f}" if float(amount).is_integer() else f"Rs. {amount:,.2f}"


def _styles():
    base = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=base["BodyText"], fontName="Helvetica", fontSize=10.5, leading=15, alignment=TA_JUSTIFY, spaceAfter=6)
    return {
        "body": body,
        "h": ParagraphStyle("h", parent=base["Heading2"], fontName="Helvetica-Bold", fontSize=14, textColor=INDIGO, spaceBefore=14, spaceAfter=6),
        "cell": ParagraphStyle("cell", parent=body, alignment=0, fontSize=9.5, leading=12.5, spaceAfter=0),
        "cellb": ParagraphStyle("cellb", parent=body, alignment=0, fontSize=9.5, leading=12.5, spaceAfter=0, fontName="Helvetica-Bold"),
        "title": ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=28, leading=34, textColor=NAVY, alignment=TA_CENTER, spaceAfter=10),
        "kicker": ParagraphStyle("kicker", fontName="Helvetica-Bold", fontSize=12, textColor=INDIGO, alignment=TA_CENTER, spaceAfter=6),
        "center": ParagraphStyle("center", parent=body, alignment=TA_CENTER, fontSize=12, leading=18),
        "small": ParagraphStyle("small", parent=body, alignment=TA_CENTER, fontSize=9, textColor=colors.HexColor("#64748b")),
    }


def _bullets(items, st):
    return ListFlowable([ListItem(Paragraph(safe(i), st["body"]), leftIndent=14) for i in items], bulletType="bullet", start="•", leftIndent=14)


def _table(rows, widths, st, header=True, total_row=False):
    data = [[Paragraph(safe(c), st["cellb"] if (header and r == 0) or (total_row and r == len(rows) - 1) else st["cell"]) for c in row]
            for r, row in enumerate(rows)]
    table = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    style = [("GRID", (0, 0), (-1, -1), 0.5, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]
    if header:
        style.append(("BACKGROUND", (0, 0), (-1, 0), SOFT))
    if total_row:
        style.append(("BACKGROUND", (0, -1), (-1, -1), SOFT))
    table.setStyle(TableStyle(style))
    return table


def build_proposal_pdf(view: dict) -> bytes:
    st, cover = _styles(), view["cover"]
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2.2 * cm, rightMargin=2.2 * cm, topMargin=2.2 * cm, bottomMargin=2.2 * cm,
                            title=safe(f"Event Proposal - {cover['title']}"), author=safe(cover["organizer"]))
    width = A4[0] - 4.4 * cm

    def footer(canvas, d):
        canvas.saveState()
        canvas.setFont("Helvetica", 8.5)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(2.2 * cm, 1.3 * cm, safe(f"Event Proposal - {cover['title']}")[:80])
        canvas.drawRightString(A4[0] - 2.2 * cm, 1.3 * cm, f"Eventra AI  |  Page {d.page}")
        canvas.restoreState()

    def cover_page(canvas, d):
        canvas.saveState()
        canvas.setFillColor(NAVY)
        canvas.rect(0, A4[1] - 5.5 * cm, A4[0], 5.5 * cm, stroke=0, fill=1)
        canvas.setFillColor(INDIGO)
        canvas.rect(0, A4[1] - 5.8 * cm, A4[0], 0.3 * cm, stroke=0, fill=1)
        canvas.setFillColor(colors.white)
        mid = A4[0] / 2
        if cover["college"]:
            canvas.setFont("Helvetica-Bold", 15)
            canvas.drawCentredString(mid, A4[1] - 2.9 * cm, safe(cover["college"]).upper()[:70])
        canvas.setFont("Helvetica", 12)
        canvas.drawCentredString(mid, A4[1] - 4.1 * cm, "EVENT PROPOSAL")
        canvas.restoreState()

    story = [Spacer(1, 7 * cm), Paragraph(safe(cover["title"]), st["title"]),
              Paragraph(safe(cover["event_type"]), st["center"]), Spacer(1, 1.2 * cm)]
    facts = [["Date", f"{cover['date']}  at  {cover['start_time']}"], ["Venue", cover["venue"]],
             ["Expected participants", str(cover["participants"])], ["Duration", f"{cover['duration_hours']} hour(s)"],
             ["Submitted by", cover["organizer"] + (f", {cover['department']}" if cover["department"] else "")]]
    story.append(_table(facts, [5.2 * cm, width - 5.2 * cm], st, header=False))
    story += [Spacer(1, 1.5 * cm), Paragraph(f"Status: {safe(cover['status']).capitalize()}", st["small"]), PageBreak()]

    def section(n, title, *flow):
        story.append(KeepTogether([Paragraph(f"{n}. {title}", st["h"]), *flow[:1]]))
        story.extend(flow[1:])

    section(1, "Introduction", Paragraph(safe(view["introduction"]), st["body"]))
    section(2, "Objectives", _bullets(view["objectives"], st))
    section(3, "Event Description", Paragraph(safe(view["description"]), st["body"]))
    section(4, "Target Participants", Paragraph(safe(view["target_participants"]), st["body"]))
    if view["schedule"]:
        rows = [["Time", "Activity", "Details"]] + [[r["time_label"], r["title"], r["description"]] for r in view["schedule"]]
        section(5, "Event Schedule", _table(rows, [2.6 * cm, 6 * cm, width - 8.6 * cm], st))
    else:
        section(5, "Event Schedule", Paragraph("The detailed schedule will be finalised and shared before the event.", st["body"]))
    b = view["budget"]
    rows = [["Item", "Estimated amount"]] + [[l["label"], rs(l["amount"])] for l in b["lines"]] + [["Total estimated budget", rs(b["total"])]]
    section(6, "Budget Breakdown", _table(rows, [width - 5 * cm, 5 * cm], st, total_row=True),
            Paragraph("All amounts are estimates and may change.", st["small"]))
    section(7, "Required Resources", _bullets(view["required_resources"], st))
    section(8, "Organizing Committee", _table([["Role", "Responsibilities"]] + [[c["role"], c["responsibilities"]] for c in view["committee"]],
                                               [4.6 * cm, width - 4.6 * cm], st))
    section(9, "Expected Outcomes", _bullets(view["expected_outcomes"], st))
    story += [Spacer(1, 1 * cm), Paragraph(safe(f"Prepared by {cover['organizer']}" + (f", {cover['department']}" if cover["department"] else "")), st["small"])]

    doc.build(story, onFirstPage=cover_page, onLaterPages=footer)
    return buf.getvalue()


# =====================================================================
# Phase 5: reports
# =====================================================================
from reportlab.graphics.charts.barcharts import VerticalBarChart  # noqa: E402
from reportlab.graphics.charts.piecharts import Pie  # noqa: E402
from reportlab.graphics.shapes import Drawing, String  # noqa: E402

PALETTE = ["#4f46e5", "#0ea5e9", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#64748b", "#ec4899"]


def _bar_chart(labels, series, width, height=170, whole=False):
    d = Drawing(width, height)
    chart = VerticalBarChart()
    chart.x, chart.y, chart.width, chart.height = 40, 28, width - 60, height - 50
    chart.data = series
    chart.categoryAxis.categoryNames = [safe(l) for l in labels]
    chart.categoryAxis.labels.fontSize = 7.5
    chart.valueAxis.labels.fontSize = 7.5
    chart.valueAxis.valueMin = 0
    top = max((max(s) for s in series if s), default=0)
    chart.valueAxis.valueMax = top * 1.15 if top else 1
    chart.valueAxis.valueStep = max(1, -(-int(top) // 5)) if whole and top else None   # whole numbers for counts
    chart.bars.strokeColor = None
    for i in range(len(series)):
        chart.bars[i].fillColor = colors.HexColor(PALETTE[i % len(PALETTE)])
    d.add(chart)
    return d


def _pie(items, width, height=170):
    """items = [(label, value)]; zero values are skipped. Returns a Drawing (legend written as text rows)."""
    items = [(l, v) for l, v in items if v > 0]
    d = Drawing(width, height)
    if not items:
        d.add(String(width / 2, height / 2, "No data", textAnchor="middle", fontSize=10))
        return d
    pie = Pie()
    pie.x, pie.y, pie.width, pie.height = 10, 15, height - 30, height - 30
    pie.data = [v for _, v in items]
    pie.labels = None
    pie.slices.strokeColor = colors.white
    for i in range(len(items)):
        pie.slices[i].fillColor = colors.HexColor(PALETTE[i % len(PALETTE)])
    d.add(pie)
    total = sum(v for _, v in items)
    y = height - 20
    for i, (label, value) in enumerate(items[:8]):
        from reportlab.graphics.shapes import Rect
        d.add(Rect(height, y - 1, 8, 8, fillColor=colors.HexColor(PALETTE[i % len(PALETTE)]), strokeColor=None))
        d.add(String(height + 14, y, safe(f"{label[:26]} ({value / total:.0%})"), fontSize=8))
        y -= 15
    return d


def _glue(story):
    """Keep every section heading on the same page as the thing that follows it."""
    out, i = [], 0
    while i < len(story):
        item = story[i]
        if isinstance(item, Paragraph) and item.style.name == "h" and i + 1 < len(story):
            out.append(KeepTogether([item, story[i + 1]]))
            i += 2
        else:
            out.append(item)
            i += 1
    return out


def _report_doc(buf, title, author):
    return SimpleDocTemplate(buf, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm,
                             title=safe(title), author=safe(author))


def _footer(label):
    def draw(canvas, d):
        canvas.saveState()
        canvas.setFont("Helvetica", 8.5)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(2 * cm, 1.2 * cm, safe(label)[:90])
        canvas.drawRightString(A4[0] - 2 * cm, 1.2 * cm, f"Eventra AI  |  Page {d.page}")
        canvas.restoreState()
    return draw


def build_analytics_pdf(data: dict, who: str, generated: str, scope_label: str) -> bytes:
    st, buf = _styles(), BytesIO()
    width = A4[0] - 4 * cm
    t = data["totals"]
    doc = _report_doc(buf, f"Event Analytics Report {data['year']}", who)
    story = [Paragraph(f"Event Analytics Report - {data['year']}", st["title"].clone("t2", fontSize=22, leading=28, alignment=0)),
             Paragraph(safe(f"{scope_label}. Prepared for {who} on {generated}."), st["small"].clone("s2", alignment=0)), Spacer(1, 10)]
    kpis = [["Total events", str(t["events"]), "Completed", str(t["completed"])],
            ["Pending approval", str(t["pending"]), "Approved", str(t["approved"])],
            ["Total estimated budget", rs(t["budget"]), "Average budget per event", rs(t["average_budget"])],
            ["Participants (expected)", str(t["participants"]), "Budget planned in breakdowns", rs(t["planned"])]]
    story.append(_table(kpis, [4.3 * cm, 3.7 * cm, 5 * cm, width - 13 * cm], st, header=False))
    story.append(Paragraph("Rejected events are not counted in budget and participant totals.", st["small"].clone("s3", alignment=0)))

    story.append(Paragraph("Events per month", st["h"]))
    story.append(_bar_chart([m["month"] for m in data["monthly"]], [[m["events"] for m in data["monthly"]]], width, whole=True))
    story.append(Paragraph("Estimated budget per month (Rs.)", st["h"]))
    story.append(_bar_chart([m["month"] for m in data["monthly"]], [[m["budget"] for m in data["monthly"]]], width))

    story.append(Paragraph("Event categories", st["h"]))
    story.append(_pie([(x["label"], x["count"]) for x in data["types"]], width))
    story.append(Paragraph("Event status", st["h"]))
    story.append(_pie([(x["label"], x["count"]) for x in data["status"]], width))

    story.append(Paragraph("Budget analysis", st["h"]))
    if data["comparison"]:
        rows = [["Event", "Estimated budget", "Saved breakdown total", "Difference"]]
        for c in data["comparison"]:
            diff = "-" if c["planned"] is None else rs(c["budget"] - c["planned"])
            rows.append([c["name"], rs(c["budget"]), "Not saved" if c["planned"] is None else rs(c["planned"]), diff])
        story.append(_table(rows, [width - 11.4 * cm, 3.8 * cm, 4.2 * cm, 3.4 * cm], st))
        story.append(Paragraph("Difference = estimated budget minus the saved breakdown. Largest 8 events by budget.", st["small"].clone("s4", alignment=0)))
    else:
        story.append(Paragraph("No events in this year.", st["body"]))
    cats = [["Category", "Total planned"]] + [[c["label"], rs(c["amount"])] for c in data["categories"]]
    story += [Spacer(1, 8), _table(cats, [width - 5 * cm, 5 * cm], st)]

    tk = data["tasks"]
    story += [Paragraph("Tasks", st["h"]), _table([["To do", "In progress", "Done"], [str(tk["todo"]), str(tk["in_progress"]), str(tk["done"])]],
                                                  [width / 3] * 3, st)]
    doc.build(_glue(story), onFirstPage=_footer(f"Analytics {data['year']}"), onLaterPages=_footer(f"Analytics {data['year']}"))
    return buf.getvalue()


def build_event_report_pdf(r: dict) -> bytes:
    """r: event, owner, generated, schedule[(time,title,desc)], budget{label: amount}, tasks[(title, assignee, status, deadline)],
    alerts[{level,title,detail}], risks[{title, severity, prevention}]"""
    st, buf = _styles(), BytesIO()
    width = A4[0] - 4 * cm
    e = r["event"]
    doc = _report_doc(buf, f"Event Report - {e.name}", r["owner"])
    story = [Paragraph(safe(e.name), st["title"].clone("t3", fontSize=22, leading=28, alignment=0)),
             Paragraph(safe(f"{e.event_type} - Event report generated on {r['generated']}"), st["small"].clone("s5", alignment=0)), Spacer(1, 10)]
    facts = [["Status", e.status.capitalize()], ["Date", f"{e.event_date} at {e.start_time}"], ["Venue", e.venue or "Not chosen"],
             ["Duration", f"{e.duration_hours} hour(s)"], ["Participants", str(e.participants)], ["Estimated budget", rs(e.budget)],
             ["Organizer", r["owner"]]]
    story.append(_table(facts, [4.5 * cm, width - 4.5 * cm], st, header=False))

    story.append(Paragraph("Budget", st["h"]))
    if r["budget"]:
        total = sum(r["budget"].values())
        rows = [["Category", "Amount", "Share of budget"]] + [[k, rs(v), f"{v / e.budget:.0%}" if e.budget else "-"] for k, v in r["budget"].items()]
        rows.append(["Total in breakdown", rs(total), f"{total / e.budget:.0%}" if e.budget else "-"])
        story.append(_table(rows, [width - 8 * cm, 4 * cm, 4 * cm], st, total_row=True))
        story.append(Paragraph(safe(f"Remaining from estimated budget: {rs(e.budget - total)}" if total <= e.budget else
                                    f"Over the estimated budget by {rs(total - e.budget)}"), st["body"]))
        story.append(_pie([(k, v) for k, v in r["budget"].items()], width))
    else:
        story.append(Paragraph("No budget breakdown has been saved for this event.", st["body"]))

    story.append(Paragraph("Tasks", st["h"]))
    if r["tasks"]:
        done = sum(1 for t in r["tasks"] if t[2] == "Done")
        story.append(Paragraph(f"{done} of {len(r['tasks'])} tasks done.", st["body"]))
        story.append(_table([["Task", "Assigned to", "Status", "Deadline"]] + [[a, b or "Unassigned", c, d or "-"] for a, b, c, d in r["tasks"]],
                            [width - 10.5 * cm, 3.5 * cm, 3.2 * cm, 3.8 * cm], st))
    else:
        story.append(Paragraph("No tasks have been added.", st["body"]))

    story.append(Paragraph("Schedule", st["h"]))
    story.append(_table([["Time", "Activity", "Details"]] + [[a, b, c] for a, b, c in r["schedule"]], [2.4 * cm, 6 * cm, width - 8.4 * cm], st)
                 if r["schedule"] else Paragraph("No schedule has been saved.", st["body"]))

    story.append(Paragraph("Risks and warnings", st["h"]))
    rows = [[a["level"].capitalize(), a["title"], a["detail"]] for a in r["alerts"]] + \
           [[x["severity"].capitalize(), x["title"], "Prevention: " + x["prevention"]] for x in r["risks"]]
    story.append(_table([["Level", "Issue", "Details"]] + rows, [2.2 * cm, 5.3 * cm, width - 7.5 * cm], st)
                 if rows else Paragraph("No warnings found from the saved data.", st["body"]))
    doc.build(_glue(story), onFirstPage=_footer(f"Event report - {e.name}"), onLaterPages=_footer(f"Event report - {e.name}"))
    return buf.getvalue()
