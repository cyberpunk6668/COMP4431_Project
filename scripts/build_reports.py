"""Build the two Chinese PDF reports from their editable Markdown sources.

Optional dependency: reportlab (not required to run the web application).
Uses local CJK TrueType fonts on Windows; no network access is needed.
"""
from __future__ import annotations

import os
import re
import textwrap
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable, Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate,
    Spacer, Table, TableStyle,
)

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output" / "pdf"
NAVY = colors.HexColor("#172B3A")
TEAL = colors.HexColor("#24776B")
INK = colors.HexColor("#2D3F4B")
MUTED = colors.HexColor("#667985")
RULE = colors.HexColor("#D9E3E4")
PALE = colors.HexColor("#EFF5F3")


def fonts():
    folder = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    custom = os.getenv("FINPILOT_REPORT_FONT")
    body = Path(custom) if custom else folder / "simsun.ttc"
    heading = folder / "simhei.ttf"
    if not body.exists():
        raise RuntimeError("Set FINPILOT_REPORT_FONT to a CJK TrueType font path.")
    pdfmetrics.registerFont(TTFont("CJK", str(body), subfontIndex=0))
    pdfmetrics.registerFont(TTFont("CJKBold", str(heading if heading.exists() else body), subfontIndex=0))
    pdfmetrics.registerFontFamily("CJK", normal="CJK", bold="CJKBold", italic="CJK", boldItalic="CJKBold")


def styles():
    result = {}
    for name, size, leading, color in (
        ("body", 10.2, 17, INK), ("h2", 16.5, 24, NAVY),
        ("h3", 12, 19, TEAL), ("small", 8.8, 14, MUTED),
        ("cell", 8.6, 13.6, INK), ("th", 8.8, 14, colors.white),
        ("code", 8.4, 13, INK), ("cover", 31, 43, NAVY),
        ("subtitle", 13.5, 22, MUTED),
    ):
        result[name] = ParagraphStyle(name, fontName="CJKBold" if name in ("h2", "h3", "cover", "th") else "CJK",
                                      fontSize=size, leading=leading, textColor=color,
                                      wordWrap="CJK", spaceAfter=6, alignment=TA_LEFT,
                                      allowWidows=0, allowOrphans=0)
    result["h2"].spaceBefore = 16
    result["h2"].spaceAfter = 9
    result["h2"].keepWithNext = True
    result["h3"].spaceBefore = 9
    result["h3"].keepWithNext = True
    result["code"].backColor = PALE
    result["code"].borderPadding = 8
    return result


def inline(value: str) -> str:
    value = escape(value)
    value = re.sub(r"`([^`]+)`", r'<font color="#24776B">\1</font>', value)
    value = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", value)
    value = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<link href="\2" color="#24776B">\1</link>', value)
    return value


def parse_markdown(path: Path, ss: dict, width: float):
    lines = path.read_text(encoding="utf-8").splitlines()
    # The first title and two cover metadata paragraphs are repeated on the cover.
    start = next((i for i, line in enumerate(lines) if line.startswith("## ")), 1)
    body, paragraph, code, table = [], [], [], []
    in_code = False

    def flush_paragraph():
        if paragraph:
            body.append(Paragraph(inline(" ".join(paragraph)), ss["body"]))
            paragraph.clear()

    def flush_table():
        if not table:
            return
        rows = []
        for line in table:
            cells = [x.strip() for x in line.strip().strip("|").split("|")]
            if all(re.fullmatch(r":?-+:?", x) for x in cells):
                continue
            rows.append(cells)
        if not rows:
            table.clear()
            return
        count = max(len(r) for r in rows)
        if count == 3 and rows[0][0] == "编号":
            weights = [0.10, 0.34, 0.56]
        elif count == 3:
            weights = [0.27, 0.43, 0.30]
        elif count == 4:
            weights = [0.09, 0.26, 0.35, 0.30]
        else:
            weights = [1 / count] * count
        cells = [[Paragraph(inline(x), ss["th" if i == 0 else "cell"]) for x in r] for i, r in enumerate(rows)]
        t = Table(cells, colWidths=[width * w for w in weights], repeatRows=1, hAlign="LEFT", rowSplitRange=(3, -2) if len(rows) > 4 else None)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("LINEBELOW", (0, 0), (-1, 0), 0.7, TEAL),
            ("LINEBELOW", (0, -1), (-1, -1), 0.4, RULE),
        ]))
        # Keep section titles attached to the actual table rather than a spacer;
        # a leading Spacer breaks Paragraph.keepWithNext across page boundaries.
        body.extend([t, Spacer(1, 8)])
        table.clear()

    for line in lines[start:]:
        if line.startswith("```"):
            flush_paragraph()
            flush_table()
            if in_code:
                wrapped = []
                for c in code:
                    wrapped.extend(textwrap.wrap(c, 88, subsequent_indent="  ", replace_whitespace=False) or [""])
                body.append(KeepTogether([Paragraph("<br/>".join(escape(c).replace(" ", "&#160;") for c in wrapped), ss["code"])]))
                code.clear()
            in_code = not in_code
            continue
        if in_code:
            code.append(line)
            continue
        if line.startswith("|"):
            flush_paragraph()
            table.append(line)
            continue
        flush_table()
        if not line.strip():
            flush_paragraph()
        elif line.startswith("### "):
            flush_paragraph()
            body.append(Paragraph(inline(line[4:]), ss["h3"]))
        elif line.startswith("## "):
            flush_paragraph()
            body.append(Paragraph(inline(line[3:]), ss["h2"]))
        elif re.fullmatch(r"!\[([^\]]+)\]\(([^)]+)\)", line.strip()):
            flush_paragraph()
            match = re.fullmatch(r"!\[([^\]]+)\]\(([^)]+)\)", line.strip())
            picture = (path.parent / match[2]).resolve()
            if picture.is_file():
                iw, ih = ImageReader(str(picture)).getSize()
                target_width = width
                target_height = min(ih * width / iw, 370)
                target_width = target_height * iw / ih
                figure = Image(str(picture), target_width, target_height)
                figure.keepWithNext = True
                gap = Spacer(1, 5)
                gap.keepWithNext = True
                # Direct flowables let a preceding section title stay with the
                # figure; nested KeepTogether wrappers can orphan that title.
                body.extend([figure, gap, Paragraph(inline(match[1]), ss["small"]), Spacer(1, 10)])
        elif re.match(r"^(\d+\. |- )", line):
            flush_paragraph()
            body.append(Paragraph(inline(line), ss["body"]))
        else:
            paragraph.append(line.strip())
    flush_paragraph()
    flush_table()
    return body


def page_chrome(canvas, doc, kind):
    canvas.saveState()
    w, h = A4
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.5)
    if doc.page > 1:
        canvas.line(22 * mm, h - 17.5 * mm, w - 22 * mm, h - 17.5 * mm)
        canvas.setFont("CJK", 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(22 * mm, h - 14 * mm, "FinPilot  /  " + kind)
    canvas.line(22 * mm, 17 * mm, w - 22 * mm, 17 * mm)
    canvas.setFont("CJK", 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(22 * mm, 12 * mm, "COMP4431  ·  2026/27  ·  v2.0")
    canvas.drawRightString(w - 22 * mm, 12 * mm, f"{doc.page:02d}")
    canvas.restoreState()


def build(source: str, filename: str, kind: str, title: str, abstract: str, details: str):
    ss = styles()
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / filename
    doc = SimpleDocTemplate(str(target), pagesize=A4,
                            rightMargin=22 * mm, leftMargin=22 * mm,
                            topMargin=24 * mm, bottomMargin=23 * mm,
                            title=title, author="FinPilot Project Team", subject="COMP4431 financial education chatbot")
    cover = [Spacer(1, 23 * mm), Paragraph("FINPILOT", ss["h3"]),
             Spacer(1, 10 * mm), Paragraph(title, ss["cover"]),
             Spacer(1, 7 * mm), Paragraph("金融领域知识问答与财务计算助手", ss["subtitle"]),
             Spacer(1, 11 * mm), HRFlowable(width="100%", thickness=1.3, color=TEAL),
             Spacer(1, 12 * mm), Paragraph(abstract, ss["body"]),
             Spacer(1, 14 * mm), Paragraph(details, ss["small"]),
             Spacer(1, 6 * mm), Paragraph("编制日期  2026-11-10<br/>版本  2.0<br/>用途  课程项目实现、复现与演示", ss["small"]),
             PageBreak()]
    story = cover + parse_markdown(ROOT / "docs" / source, ss, doc.width)
    doc.build(story, onFirstPage=lambda c, d: page_chrome(c, d, kind), onLaterPages=lambda c, d: page_chrome(c, d, kind))
    print(target)


if __name__ == "__main__":
    fonts()
    build("technical_documentation.md", "FinPilot_Technical_Documentation_ZH.pdf", "TECHNICAL DOCUMENTATION", "技术文档",
          "记录系统架构、知识检索、DeepSeek、本地 LoRA 实验、2D/3D Avatar、财务公式与安全边界，支持从源码复现和审查 v2 实现。",
          "实现方式：FastAPI、SQLite、原生前端、Three.js、PEFT LoRA、本地检索与确定性计算。<br/>验证证据以实际测试输出为准。")
    build("functional_report.md", "FinPilot_Functional_Report_ZH.pdf", "FUNCTIONAL REPORT", "功能报告",
          "说明 v2 已实现功能、Avatar 状态联动、模型适配实验、界面升级和实际验证结果，保留基线证据及已知限制。",
          "交付目标：金融领域有效沟通、可追溯来源、可靠计算与可复现演示。<br/>适用范围：金融教育与本机课程演示。")
