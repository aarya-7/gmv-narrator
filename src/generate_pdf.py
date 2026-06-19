"""
Generates a professional PDF report of all GMV anomalies.
Output: outputs/GMV_Anomaly_Report.pdf
"""
import json
import re
import pathlib
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, Table,
    TableStyle, HRFlowable, PageBreak, KeepTogether
)
from reportlab.platypus.flowables import Flowable

# ── Colour palette ──────────────────────────────────────────────────────────
NAVY      = colors.HexColor("#0D1B2A")
SLATE     = colors.HexColor("#1B2A3B")
ACCENT    = colors.HexColor("#2563EB")   # blue
SPIKE_CLR = colors.HexColor("#16A34A")   # green
DROP_CLR  = colors.HexColor("#DC2626")   # red
HIGH_CLR  = colors.HexColor("#B91C1C")   # dark red
MED_CLR   = colors.HexColor("#D97706")   # amber
ACTION_BG = colors.HexColor("#FFFBEB")   # pale amber
WHAT_BG   = colors.HexColor("#EFF6FF")   # pale blue
WHY_BG    = colors.HexColor("#F0FDF4")   # pale green
RULE_CLR  = colors.HexColor("#E5E7EB")   # light grey
TEXT      = colors.HexColor("#111827")
SUBTEXT   = colors.HexColor("#6B7280")

NARRATIVES = pathlib.Path(__file__).parent.parent / "outputs" / "narratives"
OUTPUT     = pathlib.Path(__file__).parent.parent / "outputs" / "GMV_Anomaly_Report.pdf"

W, H = A4
MARGIN = 18 * mm


# ── Custom flowables ────────────────────────────────────────────────────────
class ColorBar(Flowable):
    """Full-width coloured rule (used as section header backgrounds)."""
    def __init__(self, height, color, width=None):
        super().__init__()
        self._height = height
        self._color  = color
        self._width  = width

    def wrap(self, avail_w, avail_h):
        self._width = avail_w
        return avail_w, self._height

    def draw(self):
        self.canv.setFillColor(self._color)
        self.canv.rect(0, 0, self._width, self._height, fill=1, stroke=0)


class BadgeFlowable(Flowable):
    """Rounded-rect badge (direction/severity)."""
    def __init__(self, text, bg_color, text_color=colors.white, font_size=8):
        super().__init__()
        self._text  = text
        self._bg    = bg_color
        self._tc    = text_color
        self._fs    = font_size
        self._pad_x = 6
        self._pad_y = 3

    def wrap(self, avail_w, avail_h):
        self._w = len(self._text) * self._fs * 0.62 + self._pad_x * 2
        self._h = self._fs + self._pad_y * 2
        return self._w, self._h

    def draw(self):
        c = self.canv
        c.setFillColor(self._bg)
        c.roundRect(0, 0, self._w, self._h, 3, fill=1, stroke=0)
        c.setFillColor(self._tc)
        c.setFont("Helvetica-Bold", self._fs)
        c.drawCentredString(self._w / 2, self._pad_y + 1, self._text)


# ── Style registry ──────────────────────────────────────────────────────────
def make_styles():
    base = getSampleStyleSheet()

    def ps(name, **kw):
        return ParagraphStyle(name, parent=base["Normal"], **kw)

    return {
        "cover_title": ps("cover_title", fontSize=32, leading=38,
                           textColor=colors.white, fontName="Helvetica-Bold",
                           alignment=TA_LEFT),
        "cover_sub":   ps("cover_sub",   fontSize=14, leading=18,
                           textColor=colors.HexColor("#93C5FD"),
                           fontName="Helvetica", alignment=TA_LEFT),
        "cover_body":  ps("cover_body",  fontSize=10, leading=14,
                           textColor=colors.HexColor("#CBD5E1"),
                           fontName="Helvetica", alignment=TA_LEFT),
        "section_hdr": ps("section_hdr", fontSize=18, leading=22,
                           textColor=colors.white, fontName="Helvetica-Bold",
                           alignment=TA_LEFT),
        "date_hdr":    ps("date_hdr",    fontSize=22, leading=26,
                           textColor=colors.white, fontName="Helvetica-Bold"),
        "metric_val":  ps("metric_val",  fontSize=20, leading=24,
                           textColor=TEXT, fontName="Helvetica-Bold",
                           alignment=TA_CENTER),
        "metric_lbl":  ps("metric_lbl",  fontSize=8, leading=10,
                           textColor=SUBTEXT, fontName="Helvetica",
                           alignment=TA_CENTER),
        "box_label":   ps("box_label",   fontSize=9, leading=11,
                           textColor=ACCENT, fontName="Helvetica-Bold",
                           spaceAfter=3),
        "box_body":    ps("box_body",    fontSize=9.5, leading=14,
                           textColor=TEXT, fontName="Helvetica"),
        "tbl_hdr":     ps("tbl_hdr",     fontSize=8, leading=10,
                           textColor=colors.white, fontName="Helvetica-Bold",
                           alignment=TA_CENTER),
        "tbl_cell":    ps("tbl_cell",    fontSize=8.5, leading=11,
                           textColor=TEXT, fontName="Helvetica"),
        "tbl_cell_c":  ps("tbl_cell_c",  fontSize=8.5, leading=11,
                           textColor=TEXT, fontName="Helvetica",
                           alignment=TA_CENTER),
        "toc_date":    ps("toc_date",    fontSize=10, leading=13,
                           textColor=TEXT, fontName="Helvetica-Bold"),
        "toc_sub":     ps("toc_sub",     fontSize=9,  leading=12,
                           textColor=SUBTEXT, fontName="Helvetica"),
        "footer":      ps("footer",      fontSize=7, leading=9,
                           textColor=SUBTEXT, fontName="Helvetica",
                           alignment=TA_CENTER),
    }


# ── Parse markdown file ─────────────────────────────────────────────────────
def parse_md(path: pathlib.Path):
    text = path.read_text()

    # extract JSON block
    m = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    ctx = json.loads(m.group(1)) if m else {}

    # extract narrative sections
    sections = {}
    for label in ("WHAT HAPPENED", "WHY", "RECOMMENDED ACTION"):
        pat = rf"\*\*{re.escape(label)}\*\*\s*(.*?)(?=\*\*[A-Z]|\Z)"
        m2 = re.search(pat, text, re.DOTALL)
        if m2:
            sections[label] = m2.group(1).strip()

    return ctx, sections


# ── Page templates ──────────────────────────────────────────────────────────
def build_doc():
    doc = BaseDocTemplate(
        str(OUTPUT),
        pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN, bottomMargin=MARGIN,
        title="GMV Anomaly Intelligence Report",
        author="GMV Narrator Pipeline",
    )

    def footer_cb(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(SUBTEXT)
        canvas.drawCentredString(W / 2, 10 * mm,
            f"GMV Anomaly Intelligence Report  ·  Generated {datetime.now().strftime('%B %d, %Y')}  ·  Page {doc.page}")
        canvas.restoreState()

    frame = Frame(MARGIN, 14 * mm, W - 2 * MARGIN, H - MARGIN - 14 * mm, id="main")
    doc.addPageTemplates([
        PageTemplate(id="normal", frames=[frame], onPage=footer_cb),
    ])
    return doc


# ── Cover page ───────────────────────────────────────────────────────────────
def cover_page(styles, anomalies):
    spikes = sum(1 for a in anomalies if a["ctx"].get("direction") == "spike")
    drops  = sum(1 for a in anomalies if a["ctx"].get("direction") == "drop")
    highs  = sum(1 for a in anomalies if a["ctx"].get("severity") == "high")

    story = []

    # Dark background rectangle drawn via canvas — use a tall ColorBar instead
    story.append(ColorBar(82 * mm, NAVY))

    # Overlay title on white below… actually let's build cover as a table
    # to keep background. Use a full-page table approach.
    story = []

    # Navy header block
    header_data = [[
        Paragraph("GMV Anomaly<br/>Intelligence Report", styles["cover_title"])
    ]]
    header_tbl = Table(header_data, colWidths=[W - 2 * MARGIN])
    header_tbl.setStyle(TableStyle([
        ("BACKGROUND",  (0,0), (-1,-1), NAVY),
        ("TOPPADDING",  (0,0), (-1,-1), 20),
        ("BOTTOMPADDING",(0,0),(-1,-1), 16),
        ("LEFTPADDING", (0,0), (-1,-1), 14),
        ("RIGHTPADDING",(0,0), (-1,-1), 14),
    ]))
    story.append(header_tbl)
    story.append(Spacer(1, 4 * mm))

    # Sub-header row
    sub_data = [[
        Paragraph("Olist Brazilian E-Commerce  ·  Jan 2017 – Aug 2018", styles["cover_sub"]),
        Paragraph(f"Generated {datetime.now().strftime('%B %d, %Y')}", ParagraphStyle(
            "sub_r", parent=styles["cover_sub"],
            alignment=TA_RIGHT, textColor=SUBTEXT))
    ]]
    sub_tbl = Table(sub_data, colWidths=[(W - 2*MARGIN)*0.6, (W - 2*MARGIN)*0.4])
    sub_tbl.setStyle(TableStyle([("VALIGN", (0,0), (-1,-1), "MIDDLE")]))
    story.append(sub_tbl)
    story.append(HRFlowable(width="100%", thickness=1, color=RULE_CLR, spaceAfter=6*mm))

    # Summary stats cards
    stat_style = ParagraphStyle("stat_n", parent=styles["metric_val"], fontSize=28)
    lbl_style  = styles["metric_lbl"]
    card_data  = [[
        Paragraph(str(len(anomalies)), stat_style),
        Paragraph(str(spikes), ParagraphStyle("stat_s", parent=stat_style, textColor=SPIKE_CLR)),
        Paragraph(str(drops),  ParagraphStyle("stat_d", parent=stat_style, textColor=DROP_CLR)),
        Paragraph(str(highs),  ParagraphStyle("stat_h", parent=stat_style, textColor=HIGH_CLR)),
    ], [
        Paragraph("Total Anomalies", lbl_style),
        Paragraph("Spikes ▲", ParagraphStyle("lbl_s", parent=lbl_style, textColor=SPIKE_CLR)),
        Paragraph("Drops ▼",  ParagraphStyle("lbl_d", parent=lbl_style, textColor=DROP_CLR)),
        Paragraph("High Severity", ParagraphStyle("lbl_h", parent=lbl_style, textColor=HIGH_CLR)),
    ]]
    cw = (W - 2 * MARGIN) / 4
    card_tbl = Table(card_data, colWidths=[cw]*4)
    card_tbl.setStyle(TableStyle([
        ("ALIGN",       (0,0), (-1,-1), "CENTER"),
        ("VALIGN",      (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING",  (0,0), (-1,-1), 8),
        ("BOTTOMPADDING",(0,0),(-1,-1), 8),
        ("BOX",         (0,0), (0,-1), 0.5, RULE_CLR),
        ("BOX",         (1,0), (1,-1), 0.5, RULE_CLR),
        ("BOX",         (2,0), (2,-1), 0.5, RULE_CLR),
        ("BOX",         (3,0), (3,-1), 0.5, RULE_CLR),
        ("BACKGROUND",  (0,0), (-1,-1), colors.HexColor("#F9FAFB")),
        ("ROUNDEDCORNERS", [3]),
    ]))
    story.append(card_tbl)
    story.append(Spacer(1, 8 * mm))

    # Methodology note
    story.append(HRFlowable(width="100%", thickness=1, color=RULE_CLR, spaceBefore=2))
    story.append(Spacer(1, 4 * mm))
    meth = (
        "<b>Methodology.</b>  Anomalies are detected using a rolling 28-day median + "
        "Median Absolute Deviation (MAD) on the detrended daily GMV residual. A day is flagged "
        "when |robust z-score| ≥ 3.5, where z = 0.6745 × residual / MAD. "
        "Segment attribution decomposes each flagged day's total delta into per-segment dollar "
        "contributions versus that segment's own 28-day baseline.  "
        "<b>Three synthetic shocks</b> were injected into the dataset "
        "(2017-05-16, 2017-07-21, 2018-06-30) to validate the detection pipeline — "
        "these are disclosed and identifiable by their extreme segment-level magnitudes. "
        "All narratives are LLM-generated (Claude Sonnet) from pre-computed facts only; "
        "no numbers are invented."
    )
    story.append(Paragraph(meth, ParagraphStyle(
        "meth", parent=styles["box_body"], fontSize=8.5, textColor=SUBTEXT,
        backColor=colors.HexColor("#F9FAFB"), borderPad=8, leading=13)))
    story.append(PageBreak())

    return story


# ── Anomaly index (ToC) ─────────────────────────────────────────────────────
def toc_page(styles, anomalies):
    story = []

    # Section header
    hdr_data = [[Paragraph("Anomaly Index", styles["section_hdr"])]]
    hdr_tbl  = Table(hdr_data, colWidths=[W - 2 * MARGIN])
    hdr_tbl.setStyle(TableStyle([
        ("BACKGROUND",  (0,0), (-1,-1), SLATE),
        ("TOPPADDING",  (0,0), (-1,-1), 10),
        ("BOTTOMPADDING",(0,0),(-1,-1), 10),
        ("LEFTPADDING", (0,0), (-1,-1), 12),
    ]))
    story.append(hdr_tbl)
    story.append(Spacer(1, 5 * mm))

    # Column headers
    col_hdrs = ["Date", "Direction", "Severity", "Z-Score", "% vs Baseline",
                "Top Driver", "Decomposed By"]
    col_w    = [(W-2*MARGIN)*f for f in [0.12, 0.10, 0.10, 0.09, 0.13, 0.28, 0.18]]

    rows = [[Paragraph(h, styles["tbl_hdr"]) for h in col_hdrs]]
    for a in anomalies:
        ctx = a["ctx"]
        dir_color = SPIKE_CLR if ctx["direction"] == "spike" else DROP_CLR
        sev_color = HIGH_CLR  if ctx["severity"]  == "high"  else MED_CLR
        top_seg   = ctx["top_drivers"][0]["segment"] if ctx.get("top_drivers") else "—"
        rows.append([
            Paragraph(ctx["date"], styles["tbl_cell"]),
            Paragraph(f"{'▲' if ctx['direction']=='spike' else '▼'} {ctx['direction'].title()}",
                      ParagraphStyle("dc", parent=styles["tbl_cell_c"], textColor=dir_color,
                                     fontName="Helvetica-Bold")),
            Paragraph(ctx["severity"].title(),
                      ParagraphStyle("sc", parent=styles["tbl_cell_c"], textColor=sev_color,
                                     fontName="Helvetica-Bold")),
            Paragraph(f"{ctx['z_score']:+.2f}", styles["tbl_cell_c"]),
            Paragraph(f"{ctx['pct_change']:+.1f}%",
                      ParagraphStyle("pc", parent=styles["tbl_cell_c"],
                                     textColor=SPIKE_CLR if ctx["pct_change"] > 0 else DROP_CLR,
                                     fontName="Helvetica-Bold")),
            Paragraph(top_seg.replace("_", " ").title(), styles["tbl_cell"]),
            Paragraph(ctx.get("decomposed_by", "—").title(), styles["tbl_cell_c"]),
        ])

    toc_tbl = Table(rows, colWidths=col_w, repeatRows=1)
    toc_tbl.setStyle(TableStyle([
        ("BACKGROUND",   (0,0), (-1,0), NAVY),
        ("ALIGN",        (0,0), (-1,-1), "CENTER"),
        ("VALIGN",       (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING",   (0,0), (-1,-1), 5),
        ("BOTTOMPADDING",(0,0), (-1,-1), 5),
        ("LEFTPADDING",  (0,0), (-1,-1), 4),
        ("RIGHTPADDING", (0,0), (-1,-1), 4),
        ("ROWBACKGROUNDS",(0,1),(-1,-1), [colors.white, colors.HexColor("#F9FAFB")]),
        ("GRID",         (0,0), (-1,-1), 0.4, RULE_CLR),
        ("LINEBELOW",    (0,0), (-1,0), 1.5, ACCENT),
    ]))
    story.append(toc_tbl)
    story.append(PageBreak())
    return story


# ── Single anomaly page ─────────────────────────────────────────────────────
def anomaly_section(styles, ctx, sections, idx, total):
    story = []
    direction = ctx.get("direction", "spike")
    severity  = ctx.get("severity",  "medium")
    dir_color = SPIKE_CLR if direction == "spike" else DROP_CLR
    sev_color = HIGH_CLR  if severity  == "high"  else MED_CLR
    dir_sym   = "▲" if direction == "spike" else "▼"

    # ── Header bar ────────────────────────────────────────────────────────
    hdr_inner = Table([[
        Paragraph(f"{dir_sym}  {ctx['date']}", styles["date_hdr"]),
        Table([[
            Paragraph(f"{direction.upper()}",
                      ParagraphStyle("dh", parent=styles["tbl_hdr"],
                                     textColor=dir_color, fontSize=9)),
            Paragraph(f"{severity.upper()} SEVERITY",
                      ParagraphStyle("sh", parent=styles["tbl_hdr"],
                                     textColor=sev_color, fontSize=9)),
        ]], colWidths=[28*mm, 38*mm],
           style=[("BACKGROUND",(0,0),(0,-1), colors.HexColor("#0D2137")),
                  ("BACKGROUND",(1,0),(1,-1), colors.HexColor("#0D2137")),
                  ("BOX",(0,0),(0,-1),1, dir_color),
                  ("BOX",(1,0),(1,-1),1, sev_color),
                  ("TOPPADDING",(0,0),(-1,-1),4),
                  ("BOTTOMPADDING",(0,0),(-1,-1),4),
                  ("ALIGN",(0,0),(-1,-1),"CENTER"),
                  ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
                  ("LEFTPADDING",(0,0),(-1,-1),4),
                  ("RIGHTPADDING",(0,0),(-1,-1),4),
                  ("ROUNDEDCORNERS",[3]),
                  ("COLPADDING", (0,0),(-1,-1), 3)]),
    ]], colWidths=[(W-2*MARGIN)*0.6, (W-2*MARGIN)*0.4])
    hdr_inner.setStyle(TableStyle([
        ("ALIGN", (1,0), (1,0), "RIGHT"),
        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
    ]))

    hdr_wrap = Table([[hdr_inner]], colWidths=[W - 2 * MARGIN])
    hdr_wrap.setStyle(TableStyle([
        ("BACKGROUND",  (0,0),(-1,-1), NAVY),
        ("TOPPADDING",  (0,0),(-1,-1), 10),
        ("BOTTOMPADDING",(0,0),(-1,-1), 10),
        ("LEFTPADDING", (0,0),(-1,-1), 12),
        ("RIGHTPADDING",(0,0),(-1,-1), 12),
    ]))
    story.append(hdr_wrap)
    story.append(Spacer(1, 3 * mm))

    # ── Metrics strip ──────────────────────────────────────────────────────
    pct = ctx.get("pct_change", 0)
    pct_color = SPIKE_CLR if pct > 0 else DROP_CLR
    metrics = [
        (f"R$ {ctx['actual_value']:,.0f}",  "Actual GMV"),
        (f"R$ {ctx['baseline_value']:,.0f}", "28-Day Baseline"),
        (f"{pct:+.1f}%", "vs Baseline"),
        (f"{ctx['z_score']:+.2f}", "Robust Z-Score"),
    ]
    m_vals = [Paragraph(v,
                        ParagraphStyle("mv", parent=styles["metric_val"],
                                       textColor=pct_color if i == 2 else TEXT))
              for i, (v, _) in enumerate(metrics)]
    m_lbls = [Paragraph(l, styles["metric_lbl"]) for _, l in metrics]

    metric_tbl = Table([m_vals, m_lbls], colWidths=[(W-2*MARGIN)/4]*4)
    metric_tbl.setStyle(TableStyle([
        ("ALIGN",       (0,0), (-1,-1), "CENTER"),
        ("VALIGN",      (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING",  (0,0), (-1,-1), 6),
        ("BOTTOMPADDING",(0,0),(-1,-1), 6),
        ("LINEAFTER",   (0,0), (2,-1), 0.5, RULE_CLR),
        ("BACKGROUND",  (0,0), (-1,-1), colors.HexColor("#F9FAFB")),
        ("BOX",         (0,0), (-1,-1), 0.5, RULE_CLR),
    ]))
    story.append(metric_tbl)
    story.append(Spacer(1, 4 * mm))

    # ── Drivers table ──────────────────────────────────────────────────────
    drivers = ctx.get("top_drivers", [])
    drv_label = Paragraph(
        f"TOP SEGMENT DRIVERS  ·  decomposed by {ctx.get('decomposed_by','').upper()}",
        ParagraphStyle("drv_lbl", parent=styles["box_label"], fontSize=8,
                       textColor=colors.white))
    drv_hdr_tbl = Table([[drv_label]], colWidths=[W - 2*MARGIN])
    drv_hdr_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0),(-1,-1), SLATE),
        ("TOPPADDING", (0,0),(-1,-1), 5),
        ("BOTTOMPADDING",(0,0),(-1,-1), 5),
        ("LEFTPADDING",(0,0),(-1,-1), 8),
    ]))
    story.append(drv_hdr_tbl)

    drv_col_hdrs = ["Segment", "GMV Delta (R$)", "Contribution to Move", "Segment % vs Baseline", "Dir."]
    drv_col_w    = [(W-2*MARGIN)*f for f in [0.28, 0.18, 0.22, 0.22, 0.10]]
    drv_rows = [[Paragraph(h, styles["tbl_hdr"]) for h in drv_col_hdrs]]
    for d in drivers:
        cpct = float(d.get("contribution_pct") or 0)
        spct = float(d.get("pct_change") or 0)
        d_sym = "▲" if d.get("direction") == "up" else "▼"
        d_col = SPIKE_CLR if d.get("direction") == "up" else DROP_CLR
        drv_rows.append([
            Paragraph(str(d.get("segment","")).replace("_"," ").title(), styles["tbl_cell"]),
            Paragraph(f"{float(d.get('gmv_delta',0)):+,.0f}",
                      ParagraphStyle("dd", parent=styles["tbl_cell_c"],
                                     textColor=d_col, fontName="Helvetica-Bold")),
            Paragraph(f"{cpct:+.1f}%", styles["tbl_cell_c"]),
            Paragraph(f"{spct:+.1f}%",
                      ParagraphStyle("sd", parent=styles["tbl_cell_c"],
                                     textColor=SPIKE_CLR if spct>0 else DROP_CLR)),
            Paragraph(d_sym,
                      ParagraphStyle("ds", parent=styles["tbl_cell_c"],
                                     textColor=d_col, fontName="Helvetica-Bold", fontSize=11)),
        ])

    drv_tbl = Table(drv_rows, colWidths=drv_col_w, repeatRows=1)
    drv_tbl.setStyle(TableStyle([
        ("BACKGROUND",   (0,0), (-1,0), NAVY),
        ("ALIGN",        (0,0), (-1,-1), "CENTER"),
        ("VALIGN",       (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING",   (0,0), (-1,-1), 4),
        ("BOTTOMPADDING",(0,0), (-1,-1), 4),
        ("LEFTPADDING",  (0,0), (0,-1), 6),
        ("ALIGN",        (0,0), (0,-1), "LEFT"),
        ("ROWBACKGROUNDS",(0,1),(-1,-1), [colors.white, colors.HexColor("#F9FAFB")]),
        ("GRID",         (0,0), (-1,-1), 0.3, RULE_CLR),
        ("LINEBELOW",    (0,0), (-1,0), 1, ACCENT),
    ]))
    story.append(drv_tbl)
    story.append(Spacer(1, 4 * mm))

    # ── Narrative boxes ────────────────────────────────────────────────────
    box_configs = [
        ("WHAT HAPPENED", WHAT_BG,   ACCENT,    "what"),
        ("WHY",           WHY_BG,    SPIKE_CLR, "why"),
        ("RECOMMENDED ACTION", ACTION_BG, MED_CLR, "action"),
    ]

    for label, bg, lbl_color, key in box_configs:
        text = sections.get(label, "")
        if not text:
            continue
        # clean markdown bold markers
        text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)

        box_lbl = Paragraph(label, ParagraphStyle(
            f"lbl_{key}", parent=styles["box_label"],
            textColor=lbl_color, fontSize=8.5, spaceBefore=0, spaceAfter=0))
        box_body = Paragraph(text, styles["box_body"])

        box_data = [[box_lbl], [box_body]]
        box_tbl  = Table(box_data, colWidths=[W - 2*MARGIN - 4*mm])
        box_tbl.setStyle(TableStyle([
            ("BACKGROUND",   (0,0), (-1,-1), bg),
            ("TOPPADDING",   (0,0), (-1,-1), 7),
            ("BOTTOMPADDING",(0,0), (-1,-1), 7),
            ("LEFTPADDING",  (0,0), (-1,-1), 10),
            ("RIGHTPADDING", (0,0), (-1,-1), 10),
            ("LINEAFTER",    (0,0), (-1,-1), 3, lbl_color),
        ]))
        story.append(box_tbl)
        story.append(Spacer(1, 2 * mm))

    # historical note
    hist = ctx.get("historical_note")
    if hist:
        story.append(Paragraph(
            f"<i>📅 {hist}</i>",
            ParagraphStyle("hist", parent=styles["box_body"], fontSize=8,
                           textColor=SUBTEXT, leftIndent=6)))

    # page break between anomalies (not after last)
    if idx < total - 1:
        story.append(PageBreak())

    return story


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    styles = make_styles()

    # Load and sort all anomaly files
    files = sorted(NARRATIVES.glob("*.md"))
    anomalies = []
    for f in files:
        ctx, sections = parse_md(f)
        if ctx:
            anomalies.append({"ctx": ctx, "sections": sections, "file": f})
    anomalies.sort(key=lambda x: x["ctx"]["date"])

    doc = build_doc()
    story = []

    # Cover
    story += cover_page(styles, anomalies)

    # ToC
    story += toc_page(styles, anomalies)

    # One section per anomaly
    for i, a in enumerate(anomalies):
        # Wrap each anomaly in KeepTogether for the header+metrics block
        section = anomaly_section(styles, a["ctx"], a["sections"], i, len(anomalies))
        # First 3 flowables should stay together (header + metrics + driver label)
        story += section

    doc.build(story)
    print(f"PDF written → {OUTPUT}")


if __name__ == "__main__":
    main()
