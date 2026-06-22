from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm, cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable, KeepTogether
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import ListFlowable, ListItem

# ── Color palette ──────────────────────────────────────────────────────────────
DARK_BG      = colors.HexColor("#0D1117")
ACCENT_BLUE  = colors.HexColor("#2563EB")
ACCENT_CYAN  = colors.HexColor("#06B6D4")
ACCENT_GREEN = colors.HexColor("#10B981")
ACCENT_AMBER = colors.HexColor("#F59E0B")
ACCENT_RED   = colors.HexColor("#EF4444")
LIGHT_GRAY   = colors.HexColor("#F1F5F9")
MID_GRAY     = colors.HexColor("#94A3B8")
DARK_GRAY    = colors.HexColor("#1E293B")
WHITE        = colors.white
TEXT_DARK    = colors.HexColor("#0F172A")
SECTION_BG   = colors.HexColor("#EFF6FF")
CODE_BG      = colors.HexColor("#1E293B")
CODE_TEXT    = colors.HexColor("#E2E8F0")
BORDER_BLUE  = colors.HexColor("#BFDBFE")

PAGE_W, PAGE_H = A4

# ── Styles ─────────────────────────────────────────────────────────────────────
styles = getSampleStyleSheet()

def S(name, **kw):
    return ParagraphStyle(name, **kw)

COVER_TITLE = S("CoverTitle",
    fontName="Helvetica-Bold", fontSize=36, textColor=WHITE,
    leading=44, alignment=TA_CENTER, spaceAfter=8)

COVER_SUB = S("CoverSub",
    fontName="Helvetica", fontSize=14, textColor=colors.HexColor("#93C5FD"),
    leading=20, alignment=TA_CENTER, spaceAfter=4)

COVER_TAG = S("CoverTag",
    fontName="Helvetica-Bold", fontSize=11, textColor=ACCENT_CYAN,
    leading=16, alignment=TA_CENTER, spaceAfter=2)

H1 = S("H1",
    fontName="Helvetica-Bold", fontSize=22, textColor=ACCENT_BLUE,
    leading=28, spaceBefore=18, spaceAfter=10,
    borderPad=6)

H2 = S("H2",
    fontName="Helvetica-Bold", fontSize=15, textColor=DARK_GRAY,
    leading=20, spaceBefore=14, spaceAfter=6)

H3 = S("H3",
    fontName="Helvetica-Bold", fontSize=12, textColor=ACCENT_BLUE,
    leading=17, spaceBefore=10, spaceAfter=4)

BODY = S("Body",
    fontName="Helvetica", fontSize=10, textColor=TEXT_DARK,
    leading=16, spaceAfter=6, alignment=TA_JUSTIFY)

BODY_BOLD = S("BodyBold",
    fontName="Helvetica-Bold", fontSize=10, textColor=TEXT_DARK,
    leading=16, spaceAfter=4)

BULLET = S("Bullet",
    fontName="Helvetica", fontSize=10, textColor=TEXT_DARK,
    leading=15, spaceAfter=3, leftIndent=14, bulletIndent=0)

CODE = S("Code",
    fontName="Courier", fontSize=8.5, textColor=CODE_TEXT,
    leading=13, spaceAfter=2, leftIndent=8, backColor=CODE_BG,
    borderPad=4)

CODE_LABEL = S("CodeLabel",
    fontName="Courier-Bold", fontSize=8, textColor=ACCENT_CYAN,
    leading=12, leftIndent=8)

CAPTION = S("Caption",
    fontName="Helvetica-Oblique", fontSize=8.5, textColor=MID_GRAY,
    leading=12, alignment=TA_CENTER, spaceAfter=6)

NOTE = S("Note",
    fontName="Helvetica-Oblique", fontSize=9.5, textColor=colors.HexColor("#1D4ED8"),
    leading=14, spaceAfter=4, leftIndent=10)

TAG_STYLE = S("Tag",
    fontName="Helvetica-Bold", fontSize=9, textColor=WHITE,
    leading=12, alignment=TA_CENTER)

WEEK_TITLE = S("WeekTitle",
    fontName="Helvetica-Bold", fontSize=13, textColor=WHITE,
    leading=18, alignment=TA_CENTER)

MODULE_TITLE = S("ModuleTitle",
    fontName="Helvetica-Bold", fontSize=11, textColor=ACCENT_BLUE,
    leading=15, spaceBefore=8, spaceAfter=3)

STEP_LABEL = S("StepLabel",
    fontName="Helvetica-Bold", fontSize=10, textColor=ACCENT_GREEN,
    leading=14, spaceAfter=2)

TOC_ENTRY = S("TOC",
    fontName="Helvetica", fontSize=11, textColor=TEXT_DARK,
    leading=18, leftIndent=0)

TOC_SUB = S("TOCSub",
    fontName="Helvetica", fontSize=10, textColor=MID_GRAY,
    leading=16, leftIndent=16)

SECTION_NUM = S("SecNum",
    fontName="Helvetica-Bold", fontSize=11, textColor=ACCENT_BLUE,
    leading=18, leftIndent=0)

# ── Helpers ────────────────────────────────────────────────────────────────────

def sp(h=6): return Spacer(1, h)
def hr(color=BORDER_BLUE, thickness=1): return HRFlowable(width="100%", thickness=thickness, color=color, spaceAfter=4)

def badge(text, bg=ACCENT_BLUE):
    data = [[Paragraph(text, TAG_STYLE)]]
    t = Table(data, colWidths=[None])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), bg),
        ("ROUNDEDCORNERS", [4]),
        ("TOPPADDING", (0,0), (-1,-1), 3),
        ("BOTTOMPADDING", (0,0), (-1,-1), 3),
        ("LEFTPADDING", (0,0), (-1,-1), 8),
        ("RIGHTPADDING", (0,0), (-1,-1), 8),
    ]))
    return t

def info_box(text, bg=SECTION_BG, border=ACCENT_BLUE):
    data = [[Paragraph(text, NOTE)]]
    t = Table(data, colWidths=[PAGE_W - 4*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), bg),
        ("LINEAFTER", (0,0), (0,-1), 3, border),
        ("TOPPADDING", (0,0), (-1,-1), 8),
        ("BOTTOMPADDING", (0,0), (-1,-1), 8),
        ("LEFTPADDING", (0,0), (-1,-1), 12),
        ("RIGHTPADDING", (0,0), (-1,-1), 10),
    ]))
    return t

def code_block(lines, label=None):
    items = []
    if label:
        items.append(Paragraph(f"# {label}", CODE_LABEL))
    for line in lines:
        items.append(Paragraph(line.replace(" ", "&nbsp;"), CODE))
    data = [items] if len(items) == 1 else [[item] for item in items]
    # flatten into single cell
    content = "\n".join(
        (f"<font color='#06B6D4'># {label}</font>\n" if label else "") +
        "\n".join(lines)
        for _ in [1]
    )
    full_text = ("<font color='#06B6D4'># " + label + "</font>\n" if label else "") + "\n".join(
        l.replace("<", "&lt;").replace(">", "&gt;") for l in lines
    )
    data2 = [[Paragraph(full_text, CODE)]]
    t = Table(data2, colWidths=[PAGE_W - 4*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), CODE_BG),
        ("TOPPADDING", (0,0), (-1,-1), 10),
        ("BOTTOMPADDING", (0,0), (-1,-1), 10),
        ("LEFTPADDING", (0,0), (-1,-1), 12),
        ("RIGHTPADDING", (0,0), (-1,-1), 12),
        ("ROUNDEDCORNERS", [4]),
    ]))
    return t

def make_table(headers, rows, col_widths=None):
    header_row = [Paragraph(f"<b>{h}</b>", S("TH", fontName="Helvetica-Bold",
        fontSize=9.5, textColor=WHITE, leading=13, alignment=TA_CENTER)) for h in headers]
    body_rows = []
    for row in rows:
        body_rows.append([
            Paragraph(str(cell), S("TD", fontName="Helvetica", fontSize=9,
                textColor=TEXT_DARK, leading=13, alignment=TA_LEFT)) for cell in row
        ])
    all_rows = [header_row] + body_rows
    if col_widths is None:
        col_widths = [(PAGE_W - 4*cm) / len(headers)] * len(headers)
    t = Table(all_rows, colWidths=col_widths, repeatRows=1)
    ts = TableStyle([
        ("BACKGROUND", (0,0), (-1,0), ACCENT_BLUE),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [WHITE, LIGHT_GRAY]),
        ("GRID", (0,0), (-1,-1), 0.5, BORDER_BLUE),
        ("TOPPADDING", (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("LEFTPADDING", (0,0), (-1,-1), 8),
        ("RIGHTPADDING", (0,0), (-1,-1), 8),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("ROUNDEDCORNERS", [4]),
    ])
    t.setStyle(ts)
    return t

def week_header(week, title, color=ACCENT_BLUE):
    data = [[
        Paragraph(week, WEEK_TITLE),
        Paragraph(title, WEEK_TITLE),
    ]]
    t = Table(data, colWidths=[3*cm, PAGE_W - 7*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (0,0), color),
        ("BACKGROUND", (1,0), (1,0), DARK_GRAY),
        ("TOPPADDING", (0,0), (-1,-1), 10),
        ("BOTTOMPADDING", (0,0), (-1,-1), 10),
        ("LEFTPADDING", (0,0), (-1,-1), 12),
        ("RIGHTPADDING", (0,0), (-1,-1), 12),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
    ]))
    return t

def module_box(number, title, goal, steps, acceptance, nutanix_concept, color=ACCENT_BLUE):
    items = []

    # Header
    hdr_data = [[
        Paragraph(f"Module {number}", S("MN", fontName="Helvetica-Bold", fontSize=10,
            textColor=WHITE, leading=13)),
        Paragraph(title, S("MT", fontName="Helvetica-Bold", fontSize=11,
            textColor=WHITE, leading=14)),
    ]]
    hdr = Table(hdr_data, colWidths=[2.2*cm, PAGE_W - 6.2*cm])
    hdr.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (0,0), color),
        ("BACKGROUND", (1,0), (1,0), DARK_GRAY),
        ("TOPPADDING", (0,0), (-1,-1), 8),
        ("BOTTOMPADDING", (0,0), (-1,-1), 8),
        ("LEFTPADDING", (0,0), (-1,-1), 10),
        ("RIGHTPADDING", (0,0), (-1,-1), 10),
    ]))

    # Body
    body_lines = []
    body_lines.append(Paragraph(f"<b>Goal:</b> {goal}", BODY))
    body_lines.append(sp(4))
    body_lines.append(Paragraph("<b>Build Steps:</b>", BODY_BOLD))
    for i, step in enumerate(steps, 1):
        body_lines.append(Paragraph(f"  {i}. {step}", BULLET))
    body_lines.append(sp(4))
    body_lines.append(Paragraph(
        f"<b><font color='#10B981'>Acceptance Test:</font></b> {acceptance}", BODY))
    body_lines.append(sp(3))
    body_lines.append(Paragraph(
        f"<b><font color='#2563EB'>Nutanix Concept:</font></b> {nutanix_concept}", BODY))

    body_data = [[body_lines]]
    body_tbl = Table([[item] for item in body_lines], colWidths=[PAGE_W - 4.2*cm])
    body_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), LIGHT_GRAY),
        ("TOPPADDING", (0,0), (-1,-1), 2),
        ("BOTTOMPADDING", (0,0), (-1,-1), 2),
        ("LEFTPADDING", (0,0), (-1,-1), 10),
        ("RIGHTPADDING", (0,0), (-1,-1), 10),
    ]))

    wrapper_data = [[hdr], [body_tbl]]
    wrapper = Table(wrapper_data, colWidths=[PAGE_W - 4*cm])
    wrapper.setStyle(TableStyle([
        ("LINEBELOW", (0,-1), (-1,-1), 0, WHITE),
        ("TOPPADDING", (0,0), (-1,-1), 0),
        ("BOTTOMPADDING", (0,0), (-1,-1), 0),
        ("LEFTPADDING", (0,0), (-1,-1), 0),
        ("RIGHTPADDING", (0,0), (-1,-1), 0),
        ("BOX", (0,0), (-1,-1), 1, color),
    ]))
    return wrapper

# ── Page callbacks ─────────────────────────────────────────────────────────────

def cover_page(canvas, doc):
    canvas.saveState()
    # Dark gradient background
    canvas.setFillColor(DARK_BG)
    canvas.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    # Top accent bar
    canvas.setFillColor(ACCENT_BLUE)
    canvas.rect(0, PAGE_H - 8*mm, PAGE_W, 8*mm, fill=1, stroke=0)
    # Bottom bar
    canvas.setFillColor(DARK_GRAY)
    canvas.rect(0, 0, PAGE_W, 14*mm, fill=1, stroke=0)
    # Decorative circles
    canvas.setFillColor(colors.HexColor("#1E3A5F"))
    canvas.circle(PAGE_W - 30*mm, PAGE_H - 60*mm, 55*mm, fill=1, stroke=0)
    canvas.setFillColor(colors.HexColor("#172554"))
    canvas.circle(20*mm, 40*mm, 40*mm, fill=1, stroke=0)
    # Footer text
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(MID_GRAY)
    canvas.drawCentredString(PAGE_W/2, 10*mm, "NanoFabric Project Guide  ·  Targeted at Nutanix Engineering Roles  ·  2025–2026")
    canvas.restoreState()

def later_page(canvas, doc):
    canvas.saveState()
    # Top stripe
    canvas.setFillColor(ACCENT_BLUE)
    canvas.rect(0, PAGE_H - 5*mm, PAGE_W, 5*mm, fill=1, stroke=0)
    # Header text
    canvas.setFont("Helvetica-Bold", 8)
    canvas.setFillColor(ACCENT_BLUE)
    canvas.drawString(2*cm, PAGE_H - 3*mm, "NanoFabric")
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(MID_GRAY)
    canvas.drawRightString(PAGE_W - 2*cm, PAGE_H - 3*mm, "Distributed Storage Project Guide")
    # Bottom line + page num
    canvas.setStrokeColor(BORDER_BLUE)
    canvas.setLineWidth(0.5)
    canvas.line(2*cm, 12*mm, PAGE_W - 2*cm, 12*mm)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(MID_GRAY)
    canvas.drawCentredString(PAGE_W/2, 8*mm, f"Page {doc.page}")
    canvas.restoreState()

# ── Build content ──────────────────────────────────────────────────────────────

def build():
    import os
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs")
    os.makedirs(output_dir, exist_ok=True)
    pdf_path = os.path.join(output_dir, "NanoFabric_Project_Guide.pdf")

    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2.2*cm, bottomMargin=2.2*cm,
        title="NanoFabric — Distributed Storage Project Guide",
        author="Claude / Anthropic",
    )

    story = []

    # ── COVER ──────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 55*mm))
    story.append(Paragraph("NanoFabric", COVER_TITLE))
    story.append(sp(4))
    story.append(Paragraph("Build a Tiny Nutanix to Get Hired by Nutanix", COVER_SUB))
    story.append(sp(14))

    # Badges row
    badges_data = [[
        Paragraph("DISTRIBUTED SYSTEMS", TAG_STYLE),
        Paragraph("SELF-HEALING STORAGE", TAG_STYLE),
        Paragraph("NUTANIX-ALIGNED", TAG_STYLE),
    ]]
    badges_tbl = Table(badges_data, colWidths=[5*cm, 5.5*cm, 5*cm])
    badges_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (0,0), ACCENT_BLUE),
        ("BACKGROUND", (1,0), (1,0), ACCENT_CYAN),
        ("BACKGROUND", (2,0), (2,0), ACCENT_GREEN),
        ("TOPPADDING", (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING", (0,0), (-1,-1), 6),
        ("RIGHTPADDING", (0,0), (-1,-1), 6),
        ("ROUNDEDCORNERS", [4]),
    ]))
    story.append(badges_tbl)
    story.append(sp(20))

    cover_meta = [
        ["Language", "Python 3.11+"],
        ["Framework", "FastAPI + Docker"],
        ["Duration", "4 Weeks (~1–2 hrs/day)"],
        ["Difficulty", "Intermediate → Advanced"],
        ["Target Role", "MTS / SRE / Support / QA at Nutanix"],
    ]
    meta_tbl = Table(cover_meta, colWidths=[4.5*cm, 8*cm])
    meta_tbl.setStyle(TableStyle([
        ("TEXTCOLOR", (0,0), (0,-1), ACCENT_CYAN),
        ("TEXTCOLOR", (1,0), (1,-1), WHITE),
        ("FONTNAME", (0,0), (0,-1), "Helvetica-Bold"),
        ("FONTNAME", (1,0), (1,-1), "Helvetica"),
        ("FONTSIZE", (0,0), (-1,-1), 10),
        ("LEADING", (0,0), (-1,-1), 16),
        ("TOPPADDING", (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ("LEFTPADDING", (0,0), (-1,-1), 8),
        ("LINEBELOW", (0,0), (-1,-2), 0.5, colors.HexColor("#1E3A5F")),
        ("ALIGN", (0,0), (-1,-1), "LEFT"),
    ]))
    story.append(meta_tbl)

    story.append(PageBreak())

    # ── TABLE OF CONTENTS ──────────────────────────────────────────────────────
    story.append(Paragraph("Table of Contents", H1))
    story.append(hr())
    story.append(sp(6))

    toc_items = [
        ("01", "Introduction & Project Vision", ""),
        ("02", "Prerequisites & Preparation", ""),
        ("03", "Tech Stack Deep Dive", ""),
        ("04", "Architecture Overview", ""),
        ("05", "4-Week Roadmap", ""),
        ("06", "Module-by-Module Build Guide", ""),
        ("  06.1", "Module 0 — Project Scaffolding", ""),
        ("  06.2", "Module 1 — Local Storage Engine", ""),
        ("  06.3", "Module 2 — Cluster Membership & Heartbeats", ""),
        ("  06.4", "Module 3 — Distributed Metadata", ""),
        ("  06.5", "Module 4 — Replication Factor & Life of a Write", ""),
        ("  06.6", "Module 5 — Quorum & Split-Brain Prevention", ""),
        ("  06.7", "Module 6 — Self-Healing / Re-Protection", ""),
        ("  06.8", "Module 7 — Dashboard (Prism)", ""),
        ("  06.9", "Module 8 — Chaos Tests", ""),
        ("07", "Key Implementation Code Snippets", ""),
        ("08", "Nutanix Concept Mapping Table", ""),
        ("09", "Featurising for Hiring", ""),
        ("10", "Interview Preparation", ""),
        ("11", "Resources & Next Steps", ""),
    ]
    for num, title, _ in toc_items:
        is_sub = num.startswith("  ")
        if is_sub:
            row = [[
                Paragraph(num.strip(), TOC_SUB),
                Paragraph(title, TOC_SUB),
            ]]
        else:
            row = [[
                Paragraph(f"<b>{num}</b>", SECTION_NUM),
                Paragraph(f"<b>{title}</b>", S("TOCMain", fontName="Helvetica-Bold",
                    fontSize=11, textColor=TEXT_DARK, leading=18)),
            ]]
        tbl = Table(row[0:1] if False else row, colWidths=[2*cm, PAGE_W - 6*cm])
        tbl.setStyle(TableStyle([
            ("TOPPADDING", (0,0), (-1,-1), 2),
            ("BOTTOMPADDING", (0,0), (-1,-1), 2),
            ("LEFTPADDING", (0,0), (-1,-1), 0),
            ("LINEBELOW", (0,0), (-1,-1), 0.3, LIGHT_GRAY if is_sub else BORDER_BLUE),
        ]))
        story.append(tbl)

    story.append(PageBreak())

    # ── SECTION 1: INTRODUCTION ────────────────────────────────────────────────
    story.append(Paragraph("01 — Introduction & Project Vision", H1))
    story.append(hr())
    story.append(sp(4))
    story.append(Paragraph(
        "NanoFabric is a miniature, self-healing distributed storage cluster you build on your own "
        "laptop. It replicates the core internals of Nutanix's Distributed Storage Fabric (DSF / AOS) "
        "— the same technology that makes Nutanix's HCI platform fault-tolerant and self-managing. "
        "When you can sit across from a Nutanix interviewer and say 'I rebuilt the core concepts of AOS, "
        "Curator, and Prism myself,' and then show a running demo where you kill a node and watch data "
        "heal — you will be remembered.", BODY))
    story.append(sp(6))
    story.append(info_box(
        "Core Promise: After 4 weeks, you will have a running cluster where killing a node causes "
        "automatic re-replication with zero data loss — visible in a browser dashboard. This single "
        "demo covers Chapters 6 & 7 of the Nutanix Bible in code."
    ))
    story.append(sp(8))

    story.append(Paragraph("Why This Project Works for Hiring", H2))
    goals = [
        ("Signals Depth", "Not a CRUD app — a real distributed systems project tackling consensus, replication, and fault-tolerance."),
        ("Demoable in 30 Seconds", "Kill node → data heals. Recruiters and HMs remember it."),
        ("Unlocks Interview Loops", "Every design decision becomes a 20-minute discussion where you set the agenda."),
        ("Maps to Real Product", "You can say 'my Curator is like Nutanix's Curator' — and mean it precisely."),
    ]
    for title, desc in goals:
        story.append(Paragraph(f"<b>{title}:</b> {desc}", BULLET))
    story.append(sp(6))

    story.append(Paragraph("The Two-Track Strategy", H2))
    story.append(Paragraph(
        "Run both tracks in parallel for the strongest possible portfolio:", BODY))
    track_data = [
        ["Track", "What", "Proves"],
        ["A — NanoFabric\n(Primary)", "Build a toy distributed block-storage cluster that replicates, survives failures, and self-heals — with a web dashboard.", "Deep internals understanding. Engineering / SRE signal."],
        ["B — Nutanix CE Lab\n(Parallel)", "Deploy and operate a real Nutanix Community Edition cluster; sit the NCA certification exam.", "Can run the actual product. Solutions / Support / Ops signal."],
    ]
    story.append(make_table(
        track_data[0], track_data[1:],
        col_widths=[3.5*cm, 8*cm, 5.5*cm]
    ))

    story.append(PageBreak())

    # ── SECTION 2: PREREQUISITES ───────────────────────────────────────────────
    story.append(Paragraph("02 — Prerequisites & Preparation", H1))
    story.append(hr())
    story.append(sp(4))

    story.append(Paragraph("Before You Write a Single Line of Code", H2))
    story.append(Paragraph(
        "Spend 2–3 days on setup and foundational reading. This investment pays back every "
        "hour of the build month with fewer dead-ends and richer interview answers.", BODY))
    story.append(sp(6))

    story.append(Paragraph("System Requirements", H2))
    sys_reqs = [
        ["Requirement", "Minimum", "Recommended"],
        ["OS", "Windows 10 / macOS 12 / Ubuntu 22", "Ubuntu 22 or macOS 14 (native containers)"],
        ["RAM", "8 GB", "16 GB+ (for 5-node Docker cluster)"],
        ["Disk", "20 GB free", "50 GB SSD free"],
        ["Python", "3.10", "3.11+ (better async, better errors)"],
        ["Docker", "Docker Desktop 4.x", "Docker Desktop + Compose v2"],
        ["Node.js", "18 LTS", "20 LTS (for React dashboard)"],
        ["Git", "Any recent", "Git 2.40+"],
    ]
    story.append(make_table(sys_reqs[0], sys_reqs[1:], col_widths=[4*cm, 5.5*cm, 7.5*cm]))
    story.append(sp(8))

    story.append(Paragraph("Software to Install (Day 0 Checklist)", H2))
    installs = [
        ("Python 3.11+", "python.org or pyenv", "Core runtime"),
        ("Docker + Docker Compose v2", "docker.com/desktop", "Simulates a real cluster on one machine"),
        ("Node.js 20 LTS + npm", "nodejs.org", "React dashboard build toolchain"),
        ("Git + GitHub account", "git-scm.com", "Version control + portfolio visibility"),
        ("VS Code (recommended)", "code.visualstudio.com", "With Python, Docker, REST Client extensions"),
        ("Postman or httpie", "postman.com / httpie.io", "Test your FastAPI endpoints manually"),
    ]
    inst_data = [["Tool", "Get From", "Purpose"]] + list(installs)
    story.append(make_table(inst_data[0], inst_data[1:], col_widths=[4.5*cm, 6*cm, 6.5*cm]))
    story.append(sp(8))

    story.append(Paragraph("Foundational Reading (Complete Before Week 1)", H2))
    readings = [
        "Nutanix Bible (nutanixbible.com) — Chapters on DSF, the write path (oplog → extent store), Curator, and Prism. Read these before starting code.",
        "The Raft Paper — 'In Search of an Understandable Consensus Algorithm' (raft.github.io). Skim it once now, read again after Module 3.",
        "Visual Raft Explainer — thesecretlivesofdata.com/raft — 10 minutes, animated, essential mental model.",
        "FastAPI Docs — fastapi.tiangolo.com — Getting Started and Concurrency sections (2 hours).",
        "Docker Getting Started — docs.docker.com/get-started — If Docker is new to you, do the first 4 parts.",
        "MIT 6.5840 Lab 2 description — Even just reading the spec gives you the mental model for Raft implementation.",
    ]
    for r in readings:
        story.append(Paragraph(f"• {r}", BULLET))
    story.append(sp(6))

    story.append(info_box(
        "Python Knowledge Needed: async/await, classes, file I/O, HTTP basics. "
        "You do NOT need to know distributed systems already — that's what this project teaches you."
    ))

    story.append(PageBreak())

    # ── SECTION 3: TECH STACK ─────────────────────────────────────────────────
    story.append(Paragraph("03 — Tech Stack Deep Dive", H1))
    story.append(hr())
    story.append(sp(4))
    story.append(Paragraph(
        "Every tool below earns its place. Here's what it is, why you're using it, "
        "and what Nutanix concept it maps to.", BODY))
    story.append(sp(6))

    stack_data = [
        ["Tool", "What It Is", "Role in NanoFabric", "Nutanix Concept"],
        ["Python 3.11+", "High-level language with excellent async support.", "Core language for all node logic, write paths, metadata, self-healing.", "AOS is C++/Go in production — concepts transfer 100%."],
        ["FastAPI", "Modern async Python web framework. Auto-generates OpenAPI docs. Fast as NodeJS.", "Node-to-node HTTP API: replica shipping, heartbeats, metadata queries, client write/read.", "East-west network between CVMs (Chapter 5.3 of Nutanix Bible)."],
        ["uvicorn", "ASGI server — runs FastAPI. Non-blocking, production-quality.", "Start each node's HTTP server. Handles concurrent requests from other nodes.", "The network stack each CVM runs."],
        ["Docker + Compose v2", "Containers + multi-container orchestration.", "Each node = one container. docker compose up --scale node=5 gives you a real 5-node cluster.", "Physical nodes in a Nutanix cluster. Killing a container = killing a node."],
        ["Local file system (append-only log)", "Files + Python file I/O.", "The oplog (write journal) per node. Writes land here first before being compacted to the extent store.", "Nutanix oplog — the write journal in each CVM's storage engine."],
        ["SQLite (per-node)", "Embedded SQL DB; zero deps.", "The extent store: permanent block storage after oplog flush. Also used for node-local metadata cache.", "Extent store — permanent on-disk block storage."],
        ["Python dict (in-memory)", "RAM dictionary.", "Read cache tier in front of disk. Cache hits avoid disk reads.", "Unified Cache / Content Cache — RAM→SSD→HDD tiering."],
        ["Metadata Service (custom)", "A replicated key-value map + gossip protocol you build.", "Maps block_id → {copies: [node_ids], version: n}. Replicated across nodes for resilience.", "Cassandra / Medusa — Nutanix's distributed metadata store."],
        ["React 18 + Vite", "UI library + blazing-fast dev server.", "The browser dashboard: node health grid, block heatmap, live write animation, Kill/Add buttons.", "Prism Element — the management console."],
        ["Recharts", "Composable chart library for React.", "Live graphs: IOPS, latency, under-replicated block count over time.", "Prism monitoring charts."],
        ["pytest + pytest-asyncio", "Python testing framework with async support.", "Unit tests + chaos tests: kill node mid-write, partition cluster, assert zero data loss.", "X-Ray — Nutanix's failure-injection benchmarking tool."],
        ["httpx (async HTTP client)", "Async-first HTTP client for Python.", "Used inside node code to ship replicas and send heartbeats to other nodes asynchronously.", "The inter-CVM network calls."],
    ]
    story.append(make_table(stack_data[0], stack_data[1:],
        col_widths=[3*cm, 4*cm, 5*cm, 5*cm]))
    story.append(sp(6))

    story.append(Paragraph("Stretch / Level-Up Swaps (Optional)", H2))
    stretches = [
        ("Replace FastAPI with gRPC + Protobuf", "How production distributed systems actually talk. Nutanix uses this internally."),
        ("Rewrite the storage I/O engine in Go", "Go is the language of Kubernetes, etcd, Docker. Signals serious systems engineering."),
        ("Replace hand-rolled metadata with real Raft (raft-cluster library)", "True consensus — the hardest and most-interviewed distributed systems topic."),
        ("Add Prometheus metrics + Grafana dashboard", "Production observability — shows you understand the operations side too."),
        ("Deploy on Kubernetes with Helm", "Nutanix is heavily cloud-native; K8s fluency is a strong hiring signal."),
    ]
    for name, reason in stretches:
        story.append(Paragraph(f"<b>{name}:</b> {reason}", BULLET))

    story.append(PageBreak())

    # ── SECTION 4: ARCHITECTURE ───────────────────────────────────────────────
    story.append(Paragraph("04 — Architecture Overview", H1))
    story.append(hr())
    story.append(sp(4))

    story.append(Paragraph("Component Map", H2))

    # ASCII arch diagram as styled table
    arch_lines = [
        "┌─────────────────────────────────────────────────┐",
        "│           DASHBOARD  ('Prism')                  │",
        "│   node grid · heatmap · RF slider · Kill ▮      │",
        "└─────────────────────┬───────────────────────────┘",
        "                      │ REST / HTTP",
        "┌─────────────────────▼───────────────────────────┐",
        "│             METADATA SERVICE                     │",
        "│   block_id → [node_ids, version]  (replicated)  │",
        "└──────┬──────────────────────┬────────────┬──────┘",
        "       │ east-west heartbeats + replica ship │",
        "┌──────▼─────┐    ┌───────────▼──┐    ┌─────▼──────┐",
        "│   NODE 1   │    │    NODE 2    │    │   NODE 3   │",
        "│ oplog      │    │ oplog        │    │ oplog      │",
        "│ extent_db  │    │ extent_db    │    │ extent_db  │",
        "│ RAM cache  │    │ RAM cache    │    │ RAM cache  │",
        "└────────────┘    └──────────────┘    └────────────┘",
        "  (container)        (container)         (container)",
    ]
    arch_text = "\n".join(arch_lines)
    arch_data = [[Paragraph(arch_text, S("Arch", fontName="Courier", fontSize=8,
        textColor=ACCENT_CYAN, leading=11, backColor=CODE_BG))]]
    arch_tbl = Table(arch_data, colWidths=[PAGE_W - 4*cm])
    arch_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), CODE_BG),
        ("TOPPADDING", (0,0), (-1,-1), 12),
        ("BOTTOMPADDING", (0,0), (-1,-1), 12),
        ("LEFTPADDING", (0,0), (-1,-1), 14),
        ("RIGHTPADDING", (0,0), (-1,-1), 14),
        ("BOX", (0,0), (-1,-1), 1, ACCENT_BLUE),
    ]))
    story.append(arch_tbl)
    story.append(sp(8))

    story.append(Paragraph("Recommended Folder Structure", H2))
    folder_lines = [
        "nanofabric/",
        "├── README.md                  ← Your portfolio centerpiece",
        "├── docker-compose.yml         ← Spins up N nodes + metadata + dashboard",
        "├── nanofabric/",
        "│   ├── node/",
        "│   │   ├── storage_engine.py  ← Module 1: oplog + extent store + RAM cache",
        "│   │   ├── node_server.py     ← Module 2: FastAPI HTTP API + heartbeats",
        "│   │   └── replication.py     ← Module 4: RF write path, replica shipping",
        "│   ├── metadata/",
        "│   │   └── metadata_service.py← Module 3: block→node map, gossip/replication",
        "│   ├── cluster/",
        "│   │   ├── membership.py      ← Module 2: who's alive",
        "│   │   ├── quorum.py          ← Module 5: majority voting, partition handling",
        "│   │   └── curator.py         ← Module 6: self-healing / re-protection",
        "│   └── client/",
        "│       └── client.py          ← A tiny 'VM' that writes/reads blocks",
        "├── dashboard/                 ← Module 7: React + Vite",
        "│   ├── src/",
        "│   │   ├── App.jsx",
        "│   │   ├── components/",
        "│   │   └── api.js",
        "│   └── package.json",
        "├── tests/",
        "│   ├── test_storage.py",
        "│   ├── test_replication.py",
        "│   └── test_chaos.py          ← Module 8: kill-a-node, partition, fill-disk",
        "└── docs/",
        "    ├── architecture.md",
        "    └── life_of_a_write.md     ← Narrate it; your interview crib sheet",
    ]
    folder_text = "\n".join(folder_lines)
    folder_data = [[Paragraph(folder_text, S("Folder", fontName="Courier", fontSize=8,
        textColor=CODE_TEXT, leading=11))]]
    folder_tbl = Table(folder_data, colWidths=[PAGE_W - 4*cm])
    folder_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), CODE_BG),
        ("TOPPADDING", (0,0), (-1,-1), 12),
        ("BOTTOMPADDING", (0,0), (-1,-1), 12),
        ("LEFTPADDING", (0,0), (-1,-1), 14),
        ("RIGHTPADDING", (0,0), (-1,-1), 14),
        ("BOX", (0,0), (-1,-1), 1, DARK_GRAY),
    ]))
    story.append(folder_tbl)

    story.append(PageBreak())

    # ── SECTION 5: 4-WEEK ROADMAP ─────────────────────────────────────────────
    story.append(Paragraph("05 — 4-Week Roadmap", H1))
    story.append(hr())
    story.append(sp(4))
    story.append(Paragraph(
        "~1–2 focused hours per day. Each week ends with something working and demo-able. "
        "If you fall behind, protect Weeks 1–3 (the MVP). Week 4 is the polish that makes it shine.", BODY))
    story.append(sp(8))

    weeks = [
        ("WEEK 0", "Setup & Foundations (2–3 Days)", ACCENT_BLUE,
         ["Install Python 3.11, Docker, Node.js, Git — verify each runs",
          "Create GitHub repo 'nanofabric' with README skeleton and folder structure",
          "Read Nutanix Bible: DSF, oplog, extent store, Curator, Prism sections",
          "Skim Raft paper and watch thesecretlivesofdata.com/raft animation",
          "Start Nutanix CE download (Track B) — it's large, do it now",
          "Run a FastAPI 'Hello World' in Docker — verify your toolchain works"],
         "Docker container runs a FastAPI endpoint. GitHub repo exists."),

        ("WEEK 1", "Single Node + Cluster Membership", ACCENT_GREEN,
         ["Module 0: Full project scaffolding, Makefile, .env config",
          "Module 1: StorageEngine class — oplog (append-only file) + SQLite extent store + RAM cache dict",
          "Durability test: write 100 blocks, restart process, read all back correctly",
          "Module 2: FastAPI node server with /write, /read, /status endpoints",
          "Heartbeat system: nodes ping metadata service every second",
          "Failure detection: mark node DOWN after 3 missed heartbeats (~3 seconds)"],
         "3 nodes start, heartbeat, one gets killed — others detect DOWN within 3s."),

        ("WEEK 2", "Distributed Metadata + Replication", ACCENT_AMBER,
         ["Module 3: MetadataService — block_id → {copies: [node_ids], version: n}",
          "Gossip replication: metadata service state copied to all nodes for resilience",
          "Module 4: RF write path — local write first (data locality), then synchronous replica shipping",
          "RF2 and RF3 modes with toggle in config",
          "Write acknowledgement: client only gets OK after ALL RF copies confirmed",
          "Integration test: write a block, inspect 2–3 nodes, confirm all copies present"],
         "RF2/RF3 synchronous writes work. You can narrate 'the life of a write' and demo it."),

        ("WEEK 3", "Quorum + Self-Healing (MVP Done)", ACCENT_RED,
         ["Module 5: Quorum check before writes — majority of nodes must be reachable",
          "Network partition simulation: block traffic between node groups",
          "Minority group refuses writes; majority keeps serving — no contradictory data",
          "Module 6: Curator background task — scans metadata for under-replicated blocks",
          "Auto re-replication: surviving nodes copy under-replicated blocks to healthy peers",
          "Node rejoin: handle node coming back — metadata sync, drop excess copies",
          "Chaos test: RF2, write data, kill a node, assert all blocks back to RF2 copies"],
         "Kill a node → every block re-replicates to healthy nodes → zero data loss. RECORD THIS."),

        ("WEEK 4", "Dashboard + Polish + Presentation", ACCENT_CYAN,
         ["Module 7: React + Vite dashboard — node health grid (green/red), block heatmap",
          "Live write animation showing data fanning to replica nodes",
          "Kill Node / Add Node buttons wired to actual cluster API",
          "Recharts: live IOPS, latency, under-replicated count graphs",
          "Module 8: pytest chaos suite — kill mid-write, partition, fill-disk assertions",
          "Docker Compose: docker compose up brings up full 5-node cluster + dashboard",
          "Record 60–90s demo video/GIF (the single highest-leverage deliverable)",
          "Write docs/life_of_a_write.md — your interview crib sheet",
          "Polish README: architecture diagram, concept-mapping table, demo GIF at top",
          "Track B: Sit the NCA certification exam"],
         "Anyone can run 'docker compose up' and see your full working cluster with dashboard."),
    ]

    for week_code, week_title, color, tasks, done_when in weeks:
        story.append(week_header(week_code, week_title, color))
        story.append(sp(4))
        for task in tasks:
            story.append(Paragraph(f"  ☐  {task}", BULLET))
        story.append(sp(3))
        story.append(info_box(f"Done When: {done_when}",
            bg=colors.HexColor("#F0FDF4"), border=ACCENT_GREEN))
        story.append(sp(10))

    story.append(PageBreak())

    # ── SECTION 6: MODULE-BY-MODULE BUILD GUIDE ───────────────────────────────
    story.append(Paragraph("06 — Module-by-Module Build Guide", H1))
    story.append(hr())
    story.append(sp(4))
    story.append(info_box(
        "MVP = Modules 0–6. Completing these gives you a CLI-driven, 3-node, RF=3, "
        "self-healing KV store — a genuinely impressive project on its own. "
        "Modules 7–8 make it recruiter-stopping."
    ))
    story.append(sp(8))

    # Module 0
    story.append(Paragraph("Module 0 — Project Scaffolding", H2))
    story.append(Paragraph("<b>Goal:</b> A clean, runnable project structure that builds and tests.", BODY))
    story.append(sp(4))
    story.append(Paragraph("Steps:", BODY_BOLD))

    m0_steps = [
        ("Create the repo", [
            "mkdir nanofabric && cd nanofabric",
            "git init && git remote add origin https://github.com/YOU/nanofabric",
            "python3 -m venv venv && source venv/bin/activate",
        ]),
        ("Install core dependencies", [
            "pip install fastapi uvicorn httpx pytest pytest-asyncio",
            "pip install 'python-dotenv' pydantic",
            "pip freeze > requirements.txt",
        ]),
        ("Create the folder structure", [
            "mkdir -p nanofabric/{node,metadata,cluster,client}",
            "mkdir -p tests docs dashboard",
            "touch nanofabric/__init__.py nanofabric/node/__init__.py",
        ]),
        ("Create .env config", [
            "NODE_ID=node1",
            "NODE_HOST=0.0.0.0",
            "NODE_PORT=8001",
            "METADATA_URL=http://metadata:8000",
            "RF=3  # replication factor",
            "DATA_DIR=./data",
        ]),
    ]
    for step_name, lines in m0_steps:
        story.append(Paragraph(f"<b>{step_name}:</b>", STEP_LABEL))
        code_text = "\n".join(f"$ {l}" if not l.startswith("#") and "=" not in l else l for l in lines)
        data = [[Paragraph(code_text, CODE)]]
        t = Table(data, colWidths=[PAGE_W - 4*cm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,-1), CODE_BG),
            ("TOPPADDING", (0,0), (-1,-1), 8),
            ("BOTTOMPADDING", (0,0), (-1,-1), 8),
            ("LEFTPADDING", (0,0), (-1,-1), 12),
            ("RIGHTPADDING", (0,0), (-1,-1), 12),
        ]))
        story.append(t)
        story.append(sp(4))

    story.append(Paragraph(
        "<b>Done When:</b> python -m pytest tests/ runs (even with one trivial test that passes).", BODY))
    story.append(sp(10))

    # Module 1
    story.append(Paragraph("Module 1 — Local Storage Engine", H2))
    story.append(Paragraph(
        "<b>Goal:</b> A single node can durably store and retrieve blocks. Data survives process restart.", BODY))
    story.append(sp(4))
    story.append(Paragraph("The Two-Layer Write Path:", BODY_BOLD))
    story.append(Paragraph(
        "Writes land in the <b>oplog</b> first (an append-only file — fast, sequential). "
        "A background thread flushes committed entries to the <b>extent store</b> (SQLite — permanent, queryable). "
        "Reads check the RAM cache, then extent store, then oplog.", BODY))
    story.append(sp(4))

    code1 = """# nanofabric/node/storage_engine.py
import sqlite3, json, os, threading
from pathlib import Path

class StorageEngine:
    def __init__(self, data_dir: str, node_id: str):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.node_id = node_id
        self._cache: dict = {}          # RAM read cache (in-memory tier)
        self._lock = threading.Lock()
        self._init_oplog()
        self._init_extent_store()
        self._replay_oplog()            # recover from crash

    def _init_oplog(self):
        self.oplog_path = self.data_dir / "oplog.jsonl"
        self.oplog = open(self.oplog_path, "a", buffering=1)  # line-buffered

    def _init_extent_store(self):
        self.db = sqlite3.connect(
            str(self.data_dir / "extent_store.db"), check_same_thread=False)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS blocks "
            "(block_id TEXT PRIMARY KEY, data BLOB, version INTEGER)")
        self.db.commit()

    def _replay_oplog(self):
        \"\"\"On startup, replay the oplog to rebuild in-memory state.\"\"\"
        if not self.oplog_path.exists():
            return
        with open(self.oplog_path) as f:
            for line in f:
                entry = json.loads(line.strip())
                if entry["op"] == "write":
                    self._apply_to_extent(entry["block_id"],
                                          entry["data"], entry["version"])

    def _apply_to_extent(self, block_id, data, version):
        self.db.execute(
            "INSERT OR REPLACE INTO blocks VALUES (?,?,?)",
            (block_id, data, version))
        self.db.commit()
        self._cache[block_id] = data     # warm the cache

    def write(self, block_id: str, data: str, version: int = 1) -> bool:
        with self._lock:
            # Step 1: Write to oplog first (durability guarantee)
            entry = {"op": "write", "block_id": block_id,
                     "data": data, "version": version}
            self.oplog.write(json.dumps(entry) + "\\n")
            self.oplog.flush()
            os.fsync(self.oplog.fileno())   # force to disk
            # Step 2: Apply to extent store + cache
            self._apply_to_extent(block_id, data, version)
        return True

    def read(self, block_id: str) -> str | None:
        # Tier 1: RAM cache
        if block_id in self._cache:
            return self._cache[block_id]
        # Tier 2: Extent store
        row = self.db.execute(
            "SELECT data FROM blocks WHERE block_id=?", (block_id,)).fetchone()
        if row:
            self._cache[block_id] = row[0]   # promote to cache
            return row[0]
        return None

    def delete(self, block_id: str) -> bool:
        with self._lock:
            self._cache.pop(block_id, None)
            self.db.execute("DELETE FROM blocks WHERE block_id=?", (block_id,))
            self.db.commit()
        return True

    def list_blocks(self) -> list[str]:
        rows = self.db.execute("SELECT block_id FROM blocks").fetchall()
        return [r[0] for r in rows]"""

    data = [[Paragraph(code1, CODE)]]
    t = Table(data, colWidths=[PAGE_W - 4*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), CODE_BG),
        ("TOPPADDING", (0,0), (-1,-1), 10),
        ("BOTTOMPADDING", (0,0), (-1,-1), 10),
        ("LEFTPADDING", (0,0), (-1,-1), 12),
        ("RIGHTPADDING", (0,0), (-1,-1), 12),
        ("BOX", (0,0), (-1,-1), 1, DARK_GRAY),
    ]))
    story.append(t)
    story.append(sp(4))
    story.append(Paragraph(
        "<b>Done When:</b> Write 100 blocks, stop the process (kill -9), restart it, "
        "read all 100 blocks back correctly. Durability confirmed.", BODY))
    story.append(sp(8))

    # Module 2
    story.append(Paragraph("Module 2 — Cluster Membership & Heartbeats", H2))
    story.append(Paragraph(
        "<b>Goal:</b> Multiple nodes form a cluster. Each advertises liveness; dead nodes are "
        "automatically detected within ~3 seconds.", BODY))
    story.append(sp(4))

    code2 = """# nanofabric/node/node_server.py  (key excerpts)
from fastapi import FastAPI
import httpx, asyncio, os, time
from .storage_engine import StorageEngine

app = FastAPI()
NODE_ID = os.getenv("NODE_ID", "node1")
METADATA_URL = os.getenv("METADATA_URL", "http://metadata:8000")
engine = StorageEngine(data_dir=f"./data/{NODE_ID}", node_id=NODE_ID)

@app.on_event("startup")
async def startup():
    # Register with the metadata service
    async with httpx.AsyncClient() as c:
        await c.post(f"{METADATA_URL}/nodes/register",
                     json={"node_id": NODE_ID,
                           "address": f"http://{NODE_ID}:{os.getenv('PORT','8001')}"})
    # Start heartbeat background task
    asyncio.create_task(heartbeat_loop())

async def heartbeat_loop():
    \"\"\"Send heartbeat to metadata service every 1 second.\"\"\"
    while True:
        try:
            async with httpx.AsyncClient(timeout=2.0) as c:
                await c.post(f"{METADATA_URL}/nodes/heartbeat",
                             json={"node_id": NODE_ID, "ts": time.time()})
        except Exception:
            pass   # if metadata unreachable, keep trying
        await asyncio.sleep(1.0)

@app.get("/status")
async def status():
    return {"node_id": NODE_ID, "blocks": len(engine.list_blocks()), "alive": True}

@app.post("/write")
async def write_local(block_id: str, data: str, version: int = 1):
    \"\"\"Called by the primary node to write a replica to this node.\"\"\"
    ok = engine.write(block_id, data, version)
    return {"ok": ok}

@app.get("/read/{block_id}")
async def read_local(block_id: str):
    data = engine.read(block_id)
    if data is None:
        return {"found": False}
    return {"found": True, "data": data}"""

    data = [[Paragraph(code2, CODE)]]
    t = Table(data, colWidths=[PAGE_W - 4*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), CODE_BG),
        ("TOPPADDING", (0,0), (-1,-1), 10),
        ("BOTTOMPADDING", (0,0), (-1,-1), 10),
        ("LEFTPADDING", (0,0), (-1,-1), 12),
        ("RIGHTPADDING", (0,0), (-1,-1), 12),
        ("BOX", (0,0), (-1,-1), 1, DARK_GRAY),
    ]))
    story.append(t)
    story.append(sp(4))
    story.append(Paragraph(
        "<b>Done When:</b> Start 3 nodes, kill one container, confirm the metadata service "
        "marks it DOWN within ~3 seconds (3 missed heartbeats × 1s interval).", BODY))
    story.append(sp(8))

    # Module 3
    story.append(Paragraph("Module 3 — Distributed Metadata Service", H2))
    story.append(Paragraph(
        "<b>Goal:</b> A metadata service tracks which nodes hold copies of each block. "
        "It knows which nodes are alive. Its state is replicated so it's not a single point of failure.", BODY))
    story.append(sp(4))

    code3 = """# nanofabric/metadata/metadata_service.py  (key excerpts)
from fastapi import FastAPI
import time, threading

app = FastAPI()
HEARTBEAT_TIMEOUT = 3.0  # seconds

# In-memory cluster state (replicated to nodes via gossip in Module 3b)
nodes: dict = {}        # node_id -> {address, last_seen, status}
block_map: dict = {}    # block_id -> {copies: [node_ids], version: int}
_lock = threading.Lock()

@app.post("/nodes/register")
async def register(node_id: str, address: str):
    with _lock:
        nodes[node_id] = {"address": address, "last_seen": time.time(),
                          "status": "UP"}
    return {"registered": node_id}

@app.post("/nodes/heartbeat")
async def heartbeat(node_id: str, ts: float):
    with _lock:
        if node_id in nodes:
            nodes[node_id]["last_seen"] = ts
            nodes[node_id]["status"] = "UP"
    return {"ok": True}

@app.get("/nodes")
async def get_nodes():
    now = time.time()
    with _lock:
        for nid, info in nodes.items():
            if now - info["last_seen"] > HEARTBEAT_TIMEOUT:
                info["status"] = "DOWN"
    return nodes

@app.post("/blocks/record")
async def record_block(block_id: str, copies: list[str], version: int):
    with _lock:
        block_map[block_id] = {"copies": copies, "version": version}
    return {"recorded": block_id}

@app.get("/blocks/{block_id}")
async def get_block(block_id: str):
    return block_map.get(block_id, {})

@app.get("/blocks/under-replicated")
async def under_replicated(rf: int = 3):
    \"\"\"Return blocks with fewer than RF healthy copies — the Curator's input.\"\"\"
    alive = {nid for nid, info in nodes.items() if info["status"] == "UP"}
    result = {}
    for bid, info in block_map.items():
        healthy_copies = [n for n in info["copies"] if n in alive]
        if len(healthy_copies) < rf:
            result[bid] = {"healthy_copies": healthy_copies,
                           "needed": rf - len(healthy_copies)}
    return result"""

    data = [[Paragraph(code3, CODE)]]
    t = Table(data, colWidths=[PAGE_W - 4*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), CODE_BG),
        ("TOPPADDING", (0,0), (-1,-1), 10),
        ("BOTTOMPADDING", (0,0), (-1,-1), 10),
        ("LEFTPADDING", (0,0), (-1,-1), 12),
        ("RIGHTPADDING", (0,0), (-1,-1), 12),
        ("BOX", (0,0), (-1,-1), 1, DARK_GRAY),
    ]))
    story.append(t)
    story.append(sp(4))
    story.append(Paragraph(
        "<b>Done When:</b> Write a block, query /blocks/{block_id}, see exactly which "
        "node IDs hold copies. Query /nodes, see health status with accurate UP/DOWN.", BODY))

    story.append(PageBreak())

    # Module 4
    story.append(Paragraph("Module 4 — Replication Factor & The Life of a Write", H2))
    story.append(info_box(
        "This is THE star module. The entire 'life of a write' narrative — "
        "the single most important interview answer — is implemented here."
    ))
    story.append(sp(6))
    story.append(Paragraph(
        "<b>Goal:</b> Every write is stored on RF distinct nodes synchronously. "
        "The client only receives OK after ALL copies are confirmed.", BODY))
    story.append(sp(4))

    code4 = """# nanofabric/node/replication.py — The Life of a Write
import httpx, asyncio
from .storage_engine import StorageEngine

async def replicated_write(
    block_id: str,
    data: str,
    local_engine: StorageEngine,
    metadata_url: str,
    node_id: str,
    rf: int = 3,
) -> dict:
    \"\"\"
    The complete write path — mirrors Nutanix AOS exactly:
    Step 1: Write to local oplog (data locality — I/O served from local CVM)
    Step 2: Choose RF-1 other healthy nodes (balanced placement)
    Step 3: Ship copies to each replica node SYNCHRONOUSLY
    Step 4: Only acknowledge OK after ALL RF copies are confirmed
    Step 5: Record placement in metadata service
    \"\"\"

    # Step 1: Data locality — write to THIS node first
    version = 1  # use a real clock/lamport timestamp in production
    local_engine.write(block_id, data, version)

    # Step 2: Pick RF-1 other healthy nodes
    async with httpx.AsyncClient() as c:
        resp = await c.get(f"{metadata_url}/nodes")
        all_nodes = resp.json()

    alive_others = [
        (nid, info["address"])
        for nid, info in all_nodes.items()
        if info["status"] == "UP" and nid != node_id
    ]

    if len(alive_others) < rf - 1:
        # Not enough nodes — could raise or write with degraded RF
        raise RuntimeError(
            f"Only {len(alive_others)} other nodes alive; need {rf-1} replicas")

    # Pick by load (simplified: random; in prod use consistent hashing)
    import random
    chosen = random.sample(alive_others, rf - 1)

    # Step 3: Ship replicas SYNCHRONOUSLY — ALL must succeed
    async def ship(nid: str, address: str) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as c:
                r = await c.post(f"{address}/write",
                                 params={"block_id": block_id,
                                         "data": data, "version": version})
                return r.status_code == 200 and r.json().get("ok")
        except Exception:
            return False

    results = await asyncio.gather(*[ship(nid, addr) for nid, addr in chosen])

    if not all(results):
        # Step 4: FAIL — not all copies acknowledged
        raise RuntimeError("Replica write failed — not all copies acknowledged")

    # Step 4: All copies confirmed — now record in metadata
    all_copies = [node_id] + [nid for nid, _ in chosen]
    async with httpx.AsyncClient() as c:
        await c.post(f"{metadata_url}/blocks/record",
                     params={"block_id": block_id, "version": version},
                     json=all_copies)

    # Step 5: Return success to client
    return {"ok": True, "block_id": block_id, "copies": all_copies, "rf": rf}"""

    data = [[Paragraph(code4, CODE)]]
    t = Table(data, colWidths=[PAGE_W - 4*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), CODE_BG),
        ("TOPPADDING", (0,0), (-1,-1), 10),
        ("BOTTOMPADDING", (0,0), (-1,-1), 10),
        ("LEFTPADDING", (0,0), (-1,-1), 12),
        ("RIGHTPADDING", (0,0), (-1,-1), 12),
        ("BOX", (0,0), (-1,-1), 1, DARK_GRAY),
    ]))
    story.append(t)
    story.append(sp(4))
    story.append(Paragraph(
        "<b>Done When:</b> Write a block with RF=2. Inspect both node containers' "
        "extent_store.db — confirm the block exists in both. Confirm the client waited "
        "for both copies before returning OK.", BODY))

    story.append(PageBreak())

    # Module 5
    story.append(Paragraph("Module 5 — Quorum & Split-Brain Prevention", H2))
    story.append(Paragraph(
        "<b>Goal:</b> The cluster only accepts writes when a majority of nodes (quorum) "
        "are reachable. A partitioned minority group must refuse writes to prevent "
        "divergent data (split-brain).", BODY))
    story.append(sp(4))

    code5 = """# nanofabric/cluster/quorum.py
import httpx

async def check_quorum(metadata_url: str, required_ratio: float = 0.5) -> bool:
    \"\"\"
    Returns True if > 50% of registered nodes are UP.
    Write operations MUST call this first.
    This is why Nutanix (and Raft) require an odd number of nodes (3, 5, 7):
    you always get a clear majority.
    \"\"\"
    async with httpx.AsyncClient(timeout=2.0) as c:
        resp = await c.get(f"{metadata_url}/nodes")
        nodes = resp.json()

    total = len(nodes)
    alive = sum(1 for n in nodes.values() if n["status"] == "UP")

    if total == 0:
        return False
    return (alive / total) > required_ratio   # strict majority

# In node_server.py, wrap writes:
@app.post("/client/write")
async def client_write(block_id: str, data: str):
    from nanofabric.cluster.quorum import check_quorum
    if not await check_quorum(METADATA_URL):
        return {"ok": False, "error": "No quorum — cluster is partitioned or degraded"}
    result = await replicated_write(block_id, data, engine, METADATA_URL, NODE_ID, rf=RF)
    return result"""

    data = [[Paragraph(code5, CODE)]]
    t = Table(data, colWidths=[PAGE_W - 4*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), CODE_BG),
        ("TOPPADDING", (0,0), (-1,-1), 10),
        ("BOTTOMPADDING", (0,0), (-1,-1), 10),
        ("LEFTPADDING", (0,0), (-1,-1), 12),
        ("RIGHTPADDING", (0,0), (-1,-1), 12),
        ("BOX", (0,0), (-1,-1), 1, DARK_GRAY),
    ]))
    story.append(t)
    story.append(sp(4))
    story.append(Paragraph(
        "<b>Done When:</b> 3-node cluster, partition into groups of 2 and 1. "
        "Group of 2 keeps accepting writes. Group of 1 returns error 'No quorum'. "
        "No contradictory data exists after partition heals.", BODY))
    story.append(sp(8))

    # Module 6
    story.append(Paragraph("Module 6 — Self-Healing / Re-Protection (The Curator)", H2))
    story.append(info_box(
        "This is your headline feature. This is what wins interviews. "
        "When you can demo 'kill a node, watch it heal' live — you've demonstrated "
        "the core value proposition of Nutanix HCI in code."
    ))
    story.append(sp(6))
    story.append(Paragraph(
        "<b>Goal:</b> When a node dies, a background Curator task detects under-replicated "
        "blocks and automatically re-replicates them to healthy nodes. RF is fully restored "
        "with zero data loss.", BODY))
    story.append(sp(4))

    code6 = """# nanofabric/cluster/curator.py — Your Nutanix Curator
import httpx, asyncio, logging

logger = logging.getLogger("curator")

async def curator_loop(metadata_url: str, rf: int = 3, interval: float = 5.0):
    \"\"\"
    Background self-healing task. Runs on the 'leader' node continuously.
    Every interval seconds:
    1. Ask metadata service for under-replicated blocks
    2. For each, find a healthy node that has a copy
    3. Ship a copy to a healthy node that DOESN'T have one
    4. Update metadata — RF restored
    This is exactly what Nutanix's Curator MapReduce service does.
    \"\"\"
    while True:
        try:
            await _heal_under_replicated(metadata_url, rf)
        except Exception as e:
            logger.error(f"Curator error: {e}")
        await asyncio.sleep(interval)

async def _heal_under_replicated(metadata_url: str, rf: int):
    async with httpx.AsyncClient(timeout=5.0) as c:
        # Get under-replicated blocks
        resp = await c.get(f"{metadata_url}/blocks/under-replicated",
                           params={"rf": rf})
        under_rep = resp.json()   # {block_id: {healthy_copies, needed}}

        if not under_rep:
            return  # cluster is healthy

        # Get all alive nodes
        nodes_resp = await c.get(f"{metadata_url}/nodes")
        all_nodes = nodes_resp.json()
        alive_nodes = {nid: info for nid, info in all_nodes.items()
                       if info["status"] == "UP"}

        for block_id, info in under_rep.items():
            healthy_copies = info["healthy_copies"]
            needed = info["needed"]

            # Find nodes that DON'T have this block and are alive
            candidates = [nid for nid in alive_nodes
                          if nid not in healthy_copies]

            if not candidates or not healthy_copies:
                logger.warning(f"Cannot heal {block_id}: no candidates or no source")
                continue

            # Fetch data from a healthy copy
            source_id = healthy_copies[0]
            source_addr = all_nodes[source_id]["address"]
            data_resp = await c.get(f"{source_addr}/read/{block_id}")
            if not data_resp.json().get("found"):
                logger.warning(f"Source {source_id} cannot serve {block_id}")
                continue
            block_data = data_resp.json()["data"]

            # Ship to 'needed' candidates
            for target_id in candidates[:needed]:
                target_addr = alive_nodes[target_id]["address"]
                wr = await c.post(f"{target_addr}/write",
                                  params={"block_id": block_id, "data": block_data,
                                          "version": 1})
                if wr.status_code == 200:
                    # Update metadata
                    healthy_copies.append(target_id)
                    await c.post(f"{metadata_url}/blocks/record",
                                 params={"block_id": block_id, "version": 1},
                                 json=healthy_copies)
                    logger.info(f"Healed {block_id} → {target_id}")"""

    data = [[Paragraph(code6, CODE)]]
    t = Table(data, colWidths=[PAGE_W - 4*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), CODE_BG),
        ("TOPPADDING", (0,0), (-1,-1), 10),
        ("BOTTOMPADDING", (0,0), (-1,-1), 10),
        ("LEFTPADDING", (0,0), (-1,-1), 12),
        ("RIGHTPADDING", (0,0), (-1,-1), 12),
        ("BOX", (0,0), (-1,-1), 1, ACCENT_RED),
    ]))
    story.append(t)
    story.append(sp(4))
    story.append(Paragraph(
        "<b>Done When:</b> RF=3, write 50 blocks, kill one node container. "
        "Within 10 seconds, query /blocks/under-replicated — it returns empty. "
        "Every block is back to 3 copies. A GET on any block_id still returns data. "
        "<b>Record this as a video immediately.</b>", BODY))

    story.append(PageBreak())

    # Module 7 + 8
    story.append(Paragraph("Module 7 — The Dashboard ('Prism')", H2))
    story.append(Paragraph(
        "<b>Goal:</b> A React browser dashboard that visualizes the cluster live and lets you "
        "trigger kills and adds with a button click. This is your demo video subject.", BODY))
    story.append(sp(4))

    dashboard_features = [
        ("Node Health Grid", "Green/red cards per node, showing heartbeat status, block count, last-seen time."),
        ("Block Placement Heatmap", "Grid showing which blocks live on which nodes — updates in real-time."),
        ("Live Write Animation", "When a write is triggered, animate it fanning out from primary to replicas."),
        ("RF Slider", "Change replication factor from 2 to 5 — cluster adapts automatically."),
        ("Kill Node / Add Node Buttons", "One click kills a container (triggers self-healing). One click brings it back."),
        ("Under-Replicated Count Chart", "Recharts line graph: spikes when node dies, drops back to zero as Curator heals."),
        ("IOPS & Latency Meters", "Live write/read throughput and p50 latency."),
    ]
    feat_data = [["Feature", "Description"]] + list(dashboard_features)
    story.append(make_table(feat_data[0], feat_data[1:], col_widths=[5*cm, 12*cm]))
    story.append(sp(6))
    story.append(Paragraph("Key React snippet — polling node status:", BODY_BOLD))
    code7 = """// dashboard/src/api.js
const API = "http://localhost:8000";   // metadata service gateway

export const fetchNodes = () =>
  fetch(`${API}/nodes`).then(r => r.json());

export const killNode = (nodeId) =>
  fetch(`${API}/admin/kill/${nodeId}`, {method: "POST"}).then(r => r.json());

// dashboard/src/components/NodeGrid.jsx
import { useEffect, useState } from "react";
import { fetchNodes } from "../api";

export default function NodeGrid() {
  const [nodes, setNodes] = useState({});
  useEffect(() => {
    const id = setInterval(() => fetchNodes().then(setNodes), 1000);
    return () => clearInterval(id);
  }, []);
  return (
    <div className="grid grid-cols-3 gap-4">
      {Object.entries(nodes).map(([id, info]) => (
        <div key={id} className={`rounded-xl p-4 shadow
          ${info.status === "UP" ? "bg-green-100 border-green-400"
                                 : "bg-red-100 border-red-400"} border-2`}>
          <h3 className="font-bold text-lg">{id}</h3>
          <p className="text-sm">Status: <b>{info.status}</b></p>
          <p className="text-sm">Blocks: {info.block_count ?? "—"}</p>
        </div>
      ))}
    </div>
  );
}"""
    data = [[Paragraph(code7, CODE)]]
    t = Table(data, colWidths=[PAGE_W - 4*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), CODE_BG),
        ("TOPPADDING", (0,0), (-1,-1), 10),
        ("BOTTOMPADDING", (0,0), (-1,-1), 10),
        ("LEFTPADDING", (0,0), (-1,-1), 12),
        ("RIGHTPADDING", (0,0), (-1,-1), 12),
        ("BOX", (0,0), (-1,-1), 1, DARK_GRAY),
    ]))
    story.append(t)
    story.append(sp(8))

    story.append(Paragraph("Module 8 — Chaos Tests", H2))
    story.append(Paragraph(
        "<b>Goal:</b> Automated tests that prove your cluster handles failures correctly. "
        "These are the tests that make hiring managers say 'this person thinks like an SRE.'", BODY))
    story.append(sp(4))
    code8 = """# tests/test_chaos.py
import pytest, httpx, asyncio, time

BASE = "http://localhost:8000"   # metadata / gateway

@pytest.mark.asyncio
async def test_no_data_loss_on_node_death():
    \"\"\"Write 20 blocks with RF=2, kill one node, assert all blocks still readable.\"\"\"
    async with httpx.AsyncClient(base_url=BASE, timeout=10) as c:
        # Write 20 blocks
        block_ids = [f"chaos-block-{i}" for i in range(20)]
        for bid in block_ids:
            r = await c.post("/client/write",
                             params={"block_id": bid, "data": f"value-{bid}"})
            assert r.json()["ok"], f"Write failed for {bid}"

        # Kill node1 (the first replica node)
        await c.post("/admin/kill/node1")

        # Wait for Curator to heal (up to 30 seconds)
        for _ in range(30):
            await asyncio.sleep(1)
            under = await c.get("/blocks/under-replicated", params={"rf": 2})
            if not under.json():
                break  # healed!

        assert not under.json(), "Curator did not restore RF=2 within 30 seconds"

        # Confirm all blocks are still readable
        for bid in block_ids:
            r = await c.get(f"/client/read/{bid}")
            assert r.json()["found"], f"Block {bid} lost after node death!"
            assert r.json()["data"] == f"value-{bid}", "Data corruption detected!"

@pytest.mark.asyncio
async def test_no_split_brain_on_partition():
    \"\"\"Partition cluster 2-vs-1; minority must reject writes.\"\"\"
    async with httpx.AsyncClient(base_url=BASE, timeout=10) as c:
        await c.post("/admin/partition", json={"group_a": ["node1","node2"],
                                               "group_b": ["node3"]})
        await asyncio.sleep(2)
        # node3 (minority) should refuse writes
        r = await c.post("/client/write",
                         params={"block_id": "split-test", "data": "oops"},
                         headers={"X-Target-Node": "node3"})
        assert not r.json().get("ok"), "Minority node accepted write — split-brain!"
        await c.post("/admin/heal-partition")"""

    data = [[Paragraph(code8, CODE)]]
    t = Table(data, colWidths=[PAGE_W - 4*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), CODE_BG),
        ("TOPPADDING", (0,0), (-1,-1), 10),
        ("BOTTOMPADDING", (0,0), (-1,-1), 10),
        ("LEFTPADDING", (0,0), (-1,-1), 12),
        ("RIGHTPADDING", (0,0), (-1,-1), 12),
        ("BOX", (0,0), (-1,-1), 1, DARK_GRAY),
    ]))
    story.append(t)

    story.append(PageBreak())

    # ── SECTION 8: NUTANIX CONCEPT MAP ────────────────────────────────────────
    story.append(Paragraph("08 — Nutanix Concept Mapping Table", H1))
    story.append(hr())
    story.append(sp(4))
    story.append(Paragraph(
        "Put this table in your README and memorise it. "
        "Being able to map every component to its Nutanix equivalent "
        "proves you understand the real product, not just your toy.", BODY))
    story.append(sp(6))

    mapping = [
        ["NanoFabric Component", "Nutanix Equivalent", "What It Does"],
        ["StorageEngine oplog", "AOS oplog / Write journal", "Append-only write journal — fast, sequential, durable writes"],
        ["StorageEngine extent_store (SQLite)", "AOS Extent Store", "Permanent block storage on disk; data survives reboots"],
        ["RAM cache dict", "Unified / Content Cache", "In-memory read tier; RAM → SSD → HDD tiering"],
        ["node_server.py FastAPI", "Stargate (I/O manager)", "Handles all client and inter-node I/O; the write/read path"],
        ["replication.py RF write path", "AOS RF2/RF3 replication", "Synchronous replication to N nodes; ack only after all confirm"],
        ["metadata_service.py", "Cassandra / Medusa", "Distributed metadata: block → node placement index"],
        ["membership.py heartbeats", "Cluster health monitoring", "Detects node failures via missed heartbeats"],
        ["quorum.py", "Zeus / Zookeeper", "Cluster config, leader election, quorum enforcement"],
        ["curator.py background loop", "Curator (self-healing)", "Re-replicates under-protected data after node failures"],
        ["Docker container per node", "Physical node + CVM", "Each container = one converged compute+storage node"],
        ["Docker Compose cluster", "Nutanix cluster of nodes", "N nodes forming one shared storage fabric"],
        ["React dashboard", "Prism Element", "Web UI for cluster monitoring and operations"],
        ["Recharts graphs", "Prism monitoring charts", "Live IOPS, latency, capacity, health visualizations"],
        ["pytest chaos tests", "X-Ray failure injection", "Automated failure scenarios validating durability and healing"],
    ]
    story.append(make_table(mapping[0], mapping[1:], col_widths=[5*cm, 5*cm, 7*cm]))

    story.append(PageBreak())

    # ── SECTION 9: FEATURISING FOR HIRING ────────────────────────────────────
    story.append(Paragraph("09 — Featurising for Hiring", H1))
    story.append(hr())
    story.append(sp(4))
    story.append(Paragraph(
        "The code is half the work. This section is what turns a good project into a "
        "hiring magnet. None of these take more than a few hours — but they 10x the impact.", BODY))
    story.append(sp(6))

    features = [
        ("1. The 60–90 Second Demo Video", ACCENT_RED,
         "Record your terminal or dashboard: cluster running → click 'Kill Node' → it goes red → "
         "under-replicated count spikes → self-healing restores it → a read of any block still returns data. "
         "Loop it as a GIF. Embed it at the very top of your README. "
         "This is the single highest-leverage thing you can create."),

        ("2. README with Concept-Mapping Table", ACCENT_BLUE,
         "Your README is your resume bullet made visible. Include: one-line pitch, "
         "architecture diagram, the concept-mapping table from Section 8, a 'Quick Start' "
         "section (docker compose up → working cluster in 30 seconds), and links to the "
         "blog post and demo video. A recruiter should understand the project in 90 seconds."),

        ("3. docs/life_of_a_write.md", ACCENT_GREEN,
         "Write the write path in plain English, step by step, as if explaining to a "
         "senior Nutanix engineer. Include your code's function names at each step. "
         "This document is your interview prep — practice saying it out loud until it's "
         "completely smooth. It will be asked."),

        ("4. A Blog Post or LinkedIn Article", ACCENT_AMBER,
         "'I built a miniature Nutanix to understand HCI internals.' Walk through your "
         "architecture decisions, the self-healing demo, and what you learned. "
         "800–1,200 words. Post to dev.to or LinkedIn. Nutanix engineers and hiring "
         "managers genuinely engage with this. It generates inbound interest."),

        ("5. Resume Bullets", DARK_GRAY,
         "Example bullets (rewrite in your voice): "
         "'Built NanoFabric, a distributed storage cluster implementing RF2/RF3 synchronous replication, "
         "quorum-based split-brain prevention, and automatic self-healing — surviving simulated node "
         "failures with zero data loss (Python, FastAPI, Docker, React).' "
         "And: 'Implemented a Curator-style background re-replication service; validated by chaos tests "
         "asserting zero data loss on node death.'"),
    ]

    for title, color, body in features:
        data = [[
            Paragraph(title, S("FT", fontName="Helvetica-Bold", fontSize=11,
                textColor=WHITE, leading=14)),
        ]]
        hdr = Table(data, colWidths=[PAGE_W - 4*cm])
        hdr.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,-1), color),
            ("TOPPADDING", (0,0), (-1,-1), 8),
            ("BOTTOMPADDING", (0,0), (-1,-1), 8),
            ("LEFTPADDING", (0,0), (-1,-1), 12),
        ]))
        body_data = [[Paragraph(body, BODY)]]
        body_tbl = Table(body_data, colWidths=[PAGE_W - 4*cm])
        body_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,-1), LIGHT_GRAY),
            ("TOPPADDING", (0,0), (-1,-1), 8),
            ("BOTTOMPADDING", (0,0), (-1,-1), 8),
            ("LEFTPADDING", (0,0), (-1,-1), 12),
            ("RIGHTPADDING", (0,0), (-1,-1), 12),
        ]))
        wrapper = Table([[hdr],[body_tbl]], colWidths=[PAGE_W - 4*cm])
        wrapper.setStyle(TableStyle([
            ("TOPPADDING", (0,0), (-1,-1), 0),
            ("BOTTOMPADDING", (0,0), (-1,-1), 0),
            ("LEFTPADDING", (0,0), (-1,-1), 0),
            ("RIGHTPADDING", (0,0), (-1,-1), 0),
            ("BOX", (0,0), (-1,-1), 1.5, color),
        ]))
        story.append(wrapper)
        story.append(sp(8))

    story.append(PageBreak())

    # ── SECTION 10: INTERVIEW PREP ────────────────────────────────────────────
    story.append(Paragraph("10 — Interview Preparation", H1))
    story.append(hr())
    story.append(sp(4))

    story.append(Paragraph(
        "Every module you build unlocks real answers to real interview questions. "
        "Here are the questions this project directly prepares you for:", BODY))
    story.append(sp(6))

    qa_pairs = [
        ("Walk me through the life of a write in your system.",
         "Module 4 — data locality → choose replicas → synchronous replication → ack after all copies → "
         "record in metadata. Map each step to AOS: Stargate, oplog, extent store, Cassandra."),
        ("How does your system detect and handle node failures?",
         "Module 2 + 6 — heartbeats every 1s, DOWN after 3 missed. Then Curator scans metadata "
         "for under-replicated blocks and re-replicates to healthy nodes."),
        ("What's quorum and why does it matter?",
         "Module 5 — majority-node availability required before writes. Prevents split-brain where "
         "two partitioned groups write conflicting data. Why 3+ nodes: guaranteed majority always exists."),
        ("Explain your consistency model. What CAP tradeoffs did you make?",
         "CP system — choose consistency over availability. Writes fail if quorum can't be reached. "
         "Data is never lost or corrupted, but the cluster may become write-unavailable during partitions."),
        ("How is data placed across nodes? Why not a simple hash?",
         "Random balanced selection from healthy nodes (upgradeable to consistent hashing). "
         "Consistent hashing minimizes data movement when nodes join/leave — describe the ring."),
        ("What breaks first at scale? How would you improve this?",
         "The metadata service becomes a bottleneck at millions of blocks. Real solution: "
         "Nutanix shards metadata across Cassandra nodes with Paxos for consistency. "
         "I'd replace my dict with an etcd or sharded Redis."),
        ("How did you test failure scenarios?",
         "Module 8 — pytest chaos tests: kill node mid-write, assert zero data loss; "
         "partition cluster 2-vs-1, assert minority refuses writes; "
         "fill a disk, assert rebalancing kicks in."),
        ("What's the difference between your Curator and Nutanix's real Curator?",
         "Same job: scan for under-replicated data, trigger re-replication. Real Curator "
         "is a distributed MapReduce service running across CVMs, handles erasure coding, "
         "dedup, compression, disk balancing. Mine is a single background loop — same concept, "
         "simplified implementation."),
    ]

    for q, a in qa_pairs:
        story.append(Paragraph(f"Q: {q}", S("Q", fontName="Helvetica-Bold", fontSize=10,
            textColor=DARK_GRAY, leading=14, spaceBefore=6, spaceAfter=2,
            leftIndent=0, borderPad=4)))
        story.append(Paragraph(f"A: {a}", S("A", fontName="Helvetica", fontSize=10,
            textColor=TEXT_DARK, leading=14, spaceAfter=4, leftIndent=14)))
        story.append(hr(color=LIGHT_GRAY, thickness=0.5))

    story.append(sp(6))
    story.append(info_box(
        "Prep Tip: Prepare a 2-minute and a 10-minute version of 'tell me about NanoFabric.' "
        "The 2-minute version covers: what it does, the self-healing demo, and one key design decision. "
        "The 10-minute version walks through the full architecture and every Nutanix mapping. "
        "Practice both out loud until they feel completely natural."
    ))

    story.append(PageBreak())

    # ── SECTION 11: RESOURCES ─────────────────────────────────────────────────
    story.append(Paragraph("11 — Resources & Next Steps", H1))
    story.append(hr())
    story.append(sp(4))

    resources = [
        ("ESSENTIAL — Read These First", ACCENT_RED, [
            ("Nutanix Bible", "nutanixbible.com", "The canonical free deep-dive on Nutanix architecture. Read the DSF, oplog, Curator, and Prism sections before you start coding."),
            ("The Raft Paper", "raft.github.io", "'In Search of an Understandable Consensus Algorithm.' Skim first, read deeply after Module 3. Prime interview material."),
            ("Visual Raft", "thesecretlivesofdata.com/raft", "10-minute animated explainer. Essential mental model for leader election and log replication."),
            ("Designing Data-Intensive Applications", "DDIA by Martin Kleppmann", "The field bible. Replication, partitioning, and consistency chapters map 1:1 to your design decisions."),
        ]),
        ("CORE BUILD REFERENCES", ACCENT_BLUE, [
            ("FastAPI Docs", "fastapi.tiangolo.com", "Complete framework reference. Focus on async endpoints, background tasks, and Pydantic models."),
            ("Docker Compose v2", "docs.docker.com/compose", "Especially: networks, health checks, and scaling (--scale flag for multi-node clusters)."),
            ("httpx (async HTTP)", "www.python-httpx.org", "Your inter-node communication library. Async client, timeouts, error handling."),
            ("pytest-asyncio", "pytest-asyncio.readthedocs.io", "For testing async FastAPI code. Essential for your chaos tests."),
        ]),
        ("DISTRIBUTED SYSTEMS DEPTH", ACCENT_GREEN, [
            ("MIT 6.5840 / 6.824", "pdos.csail.mit.edu/6.824", "Labs literally build Raft and a replicated KV store. Even reading the lab specs gives deep mental models."),
            ("raft-cluster (PyPI)", "pypi.org/project/raft-cluster", "Python Raft implementation if you want to upgrade from hand-rolled metadata to true consensus."),
            ("CAP Theorem Explained", "search 'CAP theorem Martin Kleppmann'", "Understanding CP vs AP is essential for interview discussions about your consistency choices."),
        ]),
        ("DASHBOARD & TOOLING", ACCENT_AMBER, [
            ("React + Vite", "vitejs.dev", "Fastest React dev setup. Create with: npm create vite@latest dashboard -- --template react"),
            ("Recharts", "recharts.org", "Composable charts for React. Use LineChart for the under-replicated count time series."),
            ("Tailwind CSS", "tailwindcss.com", "Utility-first CSS. Fastest way to make your dashboard look professional."),
        ]),
    ]

    for section_title, color, items in resources:
        story.append(Paragraph(section_title, S("ResHdr", fontName="Helvetica-Bold",
            fontSize=12, textColor=color, leading=16, spaceBefore=10, spaceAfter=4)))
        res_data = [["Resource", "Where", "Why It Matters"]] + [
            [name, url, desc] for name, url, desc in items
        ]
        story.append(make_table(res_data[0], res_data[1:],
            col_widths=[4*cm, 5*cm, 8*cm]))
        story.append(sp(6))

    story.append(sp(4))
    story.append(hr())
    story.append(sp(6))

    story.append(Paragraph("Your First Three Actions — Do These Today", H2))
    actions = [
        "Create the GitHub repo 'nanofabric' with README skeleton and the folder structure from Section 4.",
        "Run pip install fastapi uvicorn httpx pytest and confirm a FastAPI 'Hello World' runs in Docker.",
        "Read the Nutanix Bible sections on DSF, the oplog → extent store write path, and Curator. This reading shapes everything.",
    ]
    for i, action in enumerate(actions, 1):
        data = [[
            Paragraph(str(i), S("AN", fontName="Helvetica-Bold", fontSize=16,
                textColor=WHITE, leading=20, alignment=TA_CENTER)),
            Paragraph(action, BODY),
        ]]
        t = Table(data, colWidths=[1.2*cm, PAGE_W - 5.2*cm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (0,0), ACCENT_BLUE),
            ("BACKGROUND", (1,0), (1,0), SECTION_BG),
            ("TOPPADDING", (0,0), (-1,-1), 10),
            ("BOTTOMPADDING", (0,0), (-1,-1), 10),
            ("LEFTPADDING", (0,0), (-1,-1), 10),
            ("RIGHTPADDING", (0,0), (-1,-1), 10),
            ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
            ("BOX", (0,0), (-1,-1), 1, BORDER_BLUE),
        ]))
        story.append(t)
        story.append(sp(6))

    story.append(sp(8))
    story.append(hr(color=ACCENT_BLUE, thickness=2))
    story.append(sp(6))
    story.append(Paragraph(
        "By the time NanoFabric heals itself on screen, you won't just know Nutanix — "
        "you'll have rebuilt its beating heart. That's what gets you hired.",
        S("Final", fontName="Helvetica-BoldOblique", fontSize=12,
          textColor=ACCENT_BLUE, leading=18, alignment=TA_CENTER)))

    # ── BUILD ──────────────────────────────────────────────────────────────────
    doc.build(story,
              onFirstPage=cover_page,
              onLaterPages=later_page)
    print("PDF built successfully.")

build()