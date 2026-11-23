#!/usr/bin/env python3
"""Build the report PDF with ReportLab so it matches the WeasyPrint original.

The Windows app bundles Source Sans 3 (SIL Open Font License) and does not
need the GTK libraries WeasyPrint uses.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

from reportlab.lib.colors import Color, HexColor, white
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Flowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from make_report import (
    CATEGORY_META,
    TITLE_DEFAULT,
    _zone,
    footer_text,
    format_generated,
    normalize_items,
)

NAVY = HexColor("#1b365d")
INK = HexColor("#1a2332")
MUTED = HexColor("#4a5568")
PALE = HexColor("#a0aec0")
LINE = HexColor("#d5dde6")
RULE = HexColor("#cbd5e0")
ZEBRA = HexColor("#f4f7fa")
TILE_BG = HexColor("#f8fafc")

PILL = {
    "missing": (HexColor("#9b2c2c"), HexColor("#c53030"), HexColor("#fed7d7")),
    "late": (HexColor("#7b341e"), HexColor("#c05621"), HexColor("#feebc8")),
    "teacher_message": (HexColor("#1a365d"), HexColor("#2b6cb0"), HexColor("#bee3f8")),
}
ACCENT = {
    "missing": HexColor("#c53030"),
    "missing_zero": HexColor("#2f855a"),
    "late": HexColor("#c05621"),
    "message": HexColor("#2b6cb0"),
}


def font_dir() -> Path:
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass) / "assets" / "fonts"
    return Path(__file__).resolve().parent / "assets" / "fonts"


def font_names() -> tuple[str, str, str]:
    """Return regular, semibold, and bold face names."""
    folder = font_dir()
    files = {
        "SourceSans": folder / "SourceSans3-Regular.ttf",
        "SourceSans-Semibold": folder / "SourceSans3-Semibold.ttf",
        "SourceSans-Bold": folder / "SourceSans3-Bold.ttf",
    }
    if all(path.is_file() for path in files.values()):
        registered = set(pdfmetrics.getRegisteredFontNames())
        for name, path in files.items():
            if name not in registered:
                pdfmetrics.registerFont(TTFont(name, str(path)))
        return "SourceSans", "SourceSans-Semibold", "SourceSans-Bold"
    return "Helvetica", "Helvetica-Bold", "Helvetica-Bold"


def _esc(value: object) -> str:
    text = "" if value is None else str(value)
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class TrackedText(Flowable):
    """Uppercase label with letter spacing, used for the small-caps lines."""

    def __init__(self, text: str, font: str, size: float, color: Color, tracking: float = 0.7) -> None:
        super().__init__()
        self.text = text.upper()
        self.font = font
        self.size = size
        self.color = color
        self.tracking = tracking
        self._width = 0.0

    def wrap(self, avail_width: float, avail_height: float) -> tuple[float, float]:
        base = pdfmetrics.stringWidth(self.text, self.font, self.size)
        extra = self.tracking * max(0, len(self.text) - 1)
        self._width = min(avail_width, base + extra)
        self.width = avail_width
        self.height = self.size + 3
        return avail_width, self.height

    def draw(self) -> None:
        text = self.canv.beginText()
        text.setTextOrigin(0, 1.5)
        text.setFont(self.font, self.size)
        text.setFillColor(self.color)
        text.setCharSpace(self.tracking)
        text.textOut(self.text)
        self.canv.drawText(text)


class Pill(Flowable):
    def __init__(self, text: str, kind: str, font: str) -> None:
        super().__init__()
        self.text = text.upper()
        self.kind = kind
        self.font = font
        self.font_size = 7.4
        ink, border, fill = PILL[kind]
        self.ink = ink
        self.border = border
        self.fill = fill

    def wrap(self, avail_width: float, avail_height: float) -> tuple[float, float]:
        text_width = pdfmetrics.stringWidth(self.text, self.font, self.font_size)
        self.width = text_width + 12
        self.height = 13
        return self.width, self.height

    def draw(self) -> None:
        self.canv.setLineWidth(0.7)
        self.canv.setStrokeColor(self.border)
        self.canv.setFillColor(self.fill)
        self.canv.roundRect(0, 0, self.width, self.height, 2, fill=1, stroke=1)
        self.canv.setFillColor(self.ink)
        self.canv.setFont(self.font, self.font_size)
        self.canv.drawCentredString(self.width / 2, 3.1, self.text)


class TileRow(Flowable):
    def __init__(self, tiles: list[tuple[str, str, Color]], bold: str, semi: str) -> None:
        super().__init__()
        self.tiles = tiles
        self.bold = bold
        self.semi = semi
        self._width = 0.0
        self.height = 58

    def wrap(self, avail_width: float, avail_height: float) -> tuple[float, float]:
        self._width = avail_width
        self.width = avail_width
        return avail_width, self.height

    def draw(self) -> None:
        count = len(self.tiles)
        gap = 10
        box = (self._width - gap * (count - 1)) / count
        for index, (number, label, accent) in enumerate(self.tiles):
            x = index * (box + gap)
            self.canv.setFillColor(TILE_BG)
            self.canv.setStrokeColor(LINE)
            self.canv.setLineWidth(0.8)
            self.canv.roundRect(x, 0, box, self.height, 4, fill=1, stroke=1)
            self.canv.setFillColor(accent)
            self.canv.rect(x + 0.6, 3, 4.2, self.height - 6, fill=1, stroke=0)
            self.canv.setFillColor(INK)
            self.canv.setFont(self.bold, 26)
            self.canv.drawString(x + 16, 24, number)
            text = self.canv.beginText()
            text.setTextOrigin(x + 16, 10)
            text.setFont(self.semi, 8)
            text.setFillColor(MUTED)
            text.setCharSpace(0.7)
            text.textOut(label.upper())
            self.canv.drawText(text)


class BannerBar(Flowable):
    def __init__(self, clear: bool, message: str, regular: str, bold: str) -> None:
        super().__init__()
        self.clear = clear
        self.message = message
        self.regular = regular
        self.bold = bold
        self.tag = "ALL CLEAR" if clear else "ACTION NEEDED"
        self._width = 0.0
        self.height = 28

    def wrap(self, avail_width: float, avail_height: float) -> tuple[float, float]:
        self._width = avail_width
        self.width = avail_width
        return avail_width, self.height

    def draw(self) -> None:
        if self.clear:
            fill, border, ink = HexColor("#eaf8ef"), HexColor("#9ae6b4"), HexColor("#1c4532")
        else:
            fill, border, ink = HexColor("#fffaf0"), HexColor("#fbd38d"), HexColor("#7b341e")
        self.canv.setFillColor(fill)
        self.canv.setStrokeColor(border)
        self.canv.setLineWidth(0.9)
        self.canv.roundRect(0, 0, self._width, self.height, 4, fill=1, stroke=1)
        tag_width = pdfmetrics.stringWidth(self.tag, self.bold, 7.2) + 10
        self.canv.setStrokeColor(ink)
        self.canv.setFillColor(fill)
        self.canv.setLineWidth(0.7)
        self.canv.roundRect(8, 7, tag_width, 14, 2, fill=0, stroke=1)
        self.canv.setFillColor(ink)
        self.canv.setFont(self.bold, 7.2)
        self.canv.drawCentredString(8 + tag_width / 2, 10.2, self.tag)
        self.canv.setFont(self.regular, 10.5)
        self.canv.drawString(8 + tag_width + 8, 9.2, self.message)


def _paragraph(text: str, font: str, size: float, color: Color, leading: float | None = None) -> Paragraph:
    style = ParagraphStyle(
        "cell",
        fontName=font,
        fontSize=size,
        leading=leading or size + 3,
        textColor=color,
    )
    return Paragraph(text, style)


def _dash(font: str) -> Paragraph:
    return _paragraph("—", font, 10, PALE, 13)


def _build_story(data: dict, regular: str, semi: str, bold: str) -> list:
    zone = _zone(data.get("timezone"))
    generated, _stamp = format_generated(data.get("generated_at"), zone)
    student = str(data.get("student") or "Student")
    school = str(data.get("school") or "")
    title = str(data.get("title") or TITLE_DEFAULT)
    scope = str(data.get("scope") or "")
    missing = list(data.get("missing") or [])
    late = list(data.get("late") or [])
    messages = list(data.get("teacher_messages") or [])
    rows = normalize_items(data, zone)
    kicker = f"{school} Canvas" if school else "Canvas"
    subtitle_bits = [bit for bit in (school, scope, f"Generated {generated}") if bit]
    subtitle = f' <font color="#a0aec0">|</font> '.join(_esc(bit) for bit in subtitle_bits)
    story: list = [
        TrackedText(kicker, semi, 8, NAVY, tracking=1.1),
        Spacer(1, 3),
        _paragraph(_esc(f"{student} — {title}"), bold, 20.5, NAVY, 24),
        Spacer(1, 4),
        _paragraph(subtitle, regular, 9.5, MUTED, 13),
        Spacer(1, 12),
        TileRow(
            [
                (str(len(missing)), "Missing", ACCENT["missing_zero"] if not missing else ACCENT["missing"]),
                (str(len(late)), "Late", ACCENT["late"]),
                (str(len(messages)), "Teacher messages", ACCENT["message"]),
            ],
            bold,
            semi,
        ),
        Spacer(1, 10),
    ]
    if missing:
        word = "assignment" if len(missing) == 1 else "assignments"
        story.append(BannerBar(False, f"{len(missing)} missing {word} in this date range.", regular, bold))
    else:
        story.append(BannerBar(True, "No missing assignments in this date range.", regular, bold))
    story.append(Spacer(1, 12))
    story.append(TrackedText("Assignments and messages", semi, 8, NAVY, tracking=1.0))
    story.append(Spacer(1, 5))

    header = [
        _paragraph(_esc(label), semi, 7.3, white, 9)
        for label in ("CATEGORY", "COURSE", "ASSIGNMENT", "DUE", "SCORE", "TEACHER COMMENT/MESSAGE")
    ]
    table_rows: list[list] = [header]
    if not rows:
        table_rows.append(
            [_paragraph("No missing or late assignments, and no teacher messages.", regular, 10, MUTED, 13)]
            + [""] * 5
        )
    for row in rows:
        kind = row["category"]
        due = f"{row.get('due_prefix') or ''}{row.get('due') or ''}".strip()
        score = row.get("score") or ""
        comment = row.get("comment") or ""
        table_rows.append(
            [
                Pill(CATEGORY_META[kind]["bw_label"], kind, bold),
                _paragraph(_esc(row.get("course") or ""), regular, 10, INK, 13) if row.get("course") else _dash(regular),
                _paragraph(_esc(row.get("assignment") or ""), regular, 10, INK, 13) if row.get("assignment") else _dash(regular),
                _paragraph(_esc(due), regular, 10, INK, 13) if due else _dash(regular),
                _paragraph(_esc(score), semi, 10, INK, 13) if score else _dash(regular),
                _paragraph(_esc(comment), regular, 9.5, INK, 12.5) if comment else _dash(regular),
            ]
        )
    table = Table(
        table_rows,
        colWidths=[0.95 * inch, 1.05 * inch, 1.55 * inch, 1.22 * inch, 0.55 * inch, 2.02 * inch],
        repeatRows=1,
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), white),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, ZEBRA]),
                ("FONTNAME", (0, 0), (-1, 0), semi),
                ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),
                ("VALIGN", (0, 1), (-1, -1), "TOP"),
                ("ALIGN", (0, 1), (0, -1), "LEFT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, 0), 5),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
                ("TOPPADDING", (0, 1), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 1), (-1, -1), 6),
                ("LINEBELOW", (0, 1), (-1, -2), 0.3, HexColor("#e2e8f0")),
                ("BOX", (0, 0), (-1, -1), 0.8, HexColor("#c5d0dc")),
                ("LEFTPADDING", (0, 1), (0, -1), 6),
                ("RIGHTPADDING", (0, 1), (0, -1), 4),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 8))
    legend = []
    for kind, caption in (
        ("missing", "not submitted, past due"),
        ("late", "submitted after the due date"),
        ("teacher_message", "teacher comment or Canvas message"),
    ):
        legend.append(Pill(CATEGORY_META[kind]["bw_label"], kind, bold))
        legend.append(_paragraph(_esc(caption), regular, 8, MUTED, 10))
    legend_table = Table([legend], colWidths=[58, 118, 42, 150, 62, 170])
    legend_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("ALIGN", (0, 0), (0, 0), "LEFT"),
            ]
        )
    )
    story.append(legend_table)
    notes = [str(note) for note in (data.get("notes") or []) if note]
    if notes:
        story.append(Spacer(1, 8))
        body = "<br/>".join(_esc(note) for note in notes)
        story.append(_paragraph(f"<b>Notes</b><br/>{body}", regular, 9, MUTED, 12))
    return story


def _draw_chrome(canvas, doc, total_pages: int, footer: str, regular: str) -> None:
    canvas.saveState()
    width, height = letter
    canvas.setFillColor(NAVY)
    canvas.rect(0, height - 8, width, 8, fill=1, stroke=0)
    line_y = 0.46 * inch
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.6)
    canvas.line(0.58 * inch, line_y + 12, width - 0.58 * inch, line_y + 12)
    canvas.setFillColor(MUTED)
    canvas.setFont(regular, 8)
    canvas.drawString(0.58 * inch, line_y, footer)
    canvas.setFillColor(HexColor("#718096"))
    canvas.drawRightString(
        width - 0.58 * inch,
        line_y,
        f"Page {canvas.getPageNumber()} of {total_pages}",
    )
    canvas.restoreState()


def write_report_pdf(data: dict, output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    regular, semi, bold = font_names()
    footer = footer_text(data)

    def build() -> list:
        return _build_story(data, regular, semi, bold)

    counter = {"pages": 0}

    def count_pages(canvas, doc) -> None:
        counter["pages"] = max(counter["pages"], canvas.getPageNumber())

    probe = io.BytesIO()
    probe_doc = SimpleDocTemplate(
        probe,
        pagesize=letter,
        leftMargin=0.58 * inch,
        rightMargin=0.58 * inch,
        topMargin=0.42 * inch,
        bottomMargin=0.62 * inch,
        title=str(data.get("student") or "Student"),
    )
    probe_doc.build(build(), onFirstPage=count_pages, onLaterPages=count_pages)
    total = counter["pages"] or 1

    def draw(canvas, doc) -> None:
        _draw_chrome(canvas, doc, total, footer, regular)

    document = SimpleDocTemplate(
        str(output),
        pagesize=letter,
        leftMargin=0.58 * inch,
        rightMargin=0.58 * inch,
        topMargin=0.42 * inch,
        bottomMargin=0.62 * inch,
        title=f"{data.get('student') or 'Student'} — {data.get('title') or TITLE_DEFAULT}",
    )
    document.build(build(), onFirstPage=draw, onLaterPages=draw)
    return output
