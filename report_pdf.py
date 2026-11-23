#!/usr/bin/env python3
"""Build the one-page report PDF with ReportLab.

ReportLab is pure Python, so the Windows app can bundle it without the GTK
libraries WeasyPrint needs. The layout follows the same sections as the
HTML report: header, counts, banner, table, and footer.
"""

from __future__ import annotations

from pathlib import Path

from make_report import (
    CATEGORY_META,
    TITLE_DEFAULT,
    _zone,
    footer_text,
    format_generated,
    normalize_items,
)


def _fonts() -> tuple[str, str]:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    regular = Path(r"C:\Windows\Fonts\segoeui.ttf")
    bold = Path(r"C:\Windows\Fonts\segoeuib.ttf")
    if regular.is_file() and bold.is_file():
        if "ReportBody" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("ReportBody", str(regular)))
            pdfmetrics.registerFont(TTFont("ReportBody-Bold", str(bold)))
        return "ReportBody", "ReportBody-Bold"
    return "Helvetica", "Helvetica-Bold"


def write_report_pdf(data: dict, output: Path) -> Path:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    body, bold = _fonts()
    zone = _zone(data.get("timezone"))
    generated, _stamp = format_generated(data.get("generated_at"), zone)
    student = data.get("student") or "Student"
    school = data.get("school") or ""
    title = data.get("title") or TITLE_DEFAULT
    scope = data.get("scope") or ""
    missing = list(data.get("missing") or [])
    late = list(data.get("late") or [])
    messages = list(data.get("teacher_messages") or [])
    rows = normalize_items(data, zone)
    navy = colors.HexColor("#1b365d")
    ink = colors.HexColor("#1a2332")
    muted = colors.HexColor("#4a5568")
    line = colors.HexColor("#d5dde6")
    missing_color = colors.HexColor("#2f855a") if not missing else colors.HexColor("#c53030")

    def style(name: str, **kwargs) -> ParagraphStyle:
        defaults = dict(fontName=body, textColor=ink, leading=13)
        defaults.update(kwargs)
        return ParagraphStyle(name, **defaults)

    title_style = style("title", fontName=bold, fontSize=16, leading=19, textColor=navy)
    kicker_style = style("kicker", fontName=bold, fontSize=8, leading=10, textColor=navy)
    sub_style = style("sub", fontSize=9, leading=12, textColor=muted)
    count_style = style("count", fontName=bold, fontSize=18, leading=21, alignment=1)
    label_style = style("label", fontSize=8, leading=10, textColor=muted, alignment=1)
    banner_style = style("banner", fontSize=10, leading=13)
    header_style = style("th", fontName=bold, fontSize=8, leading=10, textColor=colors.white)
    cell_style = style("td", fontSize=8.5, leading=11)
    small_style = style("small", fontSize=8, leading=10, textColor=muted)
    footer = footer_text(data)

    def esc(value: object) -> str:
        text = "" if value is None else str(value)
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    kicker = f"{school} Canvas" if school else "Canvas"
    bits = [part for part in (school, scope, f"Generated {generated}") if part]
    subtitle = "  |  ".join(bits)
    story = [
        Paragraph(esc(kicker).upper(), kicker_style),
        Spacer(1, 4),
        Paragraph(esc(f"{student} — {title}"), title_style),
        Spacer(1, 2),
        Paragraph(esc(subtitle), sub_style),
        Spacer(1, 12),
    ]

    def tile(count: int, caption: str) -> list:
        return [
            Paragraph(str(count), count_style),
            Paragraph(esc(caption), label_style),
        ]

    tiles = Table(
        [[tile(len(missing), "Missing"), tile(len(late), "Late"), tile(len(messages), "Teacher messages")]],
        colWidths=[2.4 * inch, 2.4 * inch, 2.5 * inch],
    )
    tiles.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                ("BOX", (0, 0), (0, 0), 0.6, line),
                ("BOX", (1, 0), (1, 0), 0.6, line),
                ("BOX", (2, 0), (2, 0), 0.6, line),
                ("LINEBEFORE", (0, 0), (0, 0), 4, missing_color),
                ("LINEBEFORE", (1, 0), (1, 0), 4, colors.HexColor("#c05621")),
                ("LINEBEFORE", (2, 0), (2, 0), 4, colors.HexColor("#2b6cb0")),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("RIGHTPADDING", (0, 0), (1, 0), 14),
            ]
        )
    )
    story.append(tiles)
    story.append(Spacer(1, 10))
    if missing:
        word = "assignment" if len(missing) == 1 else "assignments"
        banner = f"<b>Action needed.</b>  {len(missing)} missing {word} in this date range."
        banner_bg = colors.HexColor("#fffaf0")
    else:
        banner = "<b>All clear.</b>  No missing assignments in this date range."
        banner_bg = colors.HexColor("#eaf8ef")
    banner_table = Table([[Paragraph(banner, banner_style)]], colWidths=[7.3 * inch])
    banner_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), banner_bg),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.append(banner_table)
    story.append(Spacer(1, 12))
    story.append(Paragraph("ASSIGNMENTS AND MESSAGES", kicker_style))
    story.append(Spacer(1, 6))

    header = [
        Paragraph(esc(text), header_style)
        for text in ("Category", "Course", "Assignment", "Due", "Score", "Comment")
    ]
    table_rows = [header]
    pill_colors = {
        "missing": "#9b2c2c",
        "late": "#7b341e",
        "teacher_message": "#2b6cb0",
    }
    if not rows:
        table_rows.append(
            [Paragraph("No missing or late assignments, and no teacher messages.", cell_style)]
            + [Paragraph("", cell_style) for _ in range(5)]
        )
    for row in rows:
        meta = CATEGORY_META.get(row["category"], CATEGORY_META["missing"])
        due = f"{row.get('due_prefix') or ''}{row.get('due') or ''}".strip() or "—"
        score = row.get("score") or "—"
        comment = row.get("comment") or "—"
        cat = Paragraph(
            f'<font color="{pill_colors.get(row["category"], "#1b365d")}"><b>{esc(meta["bw_label"])}</b></font>',
            cell_style,
        )
        table_rows.append(
            [
                cat,
                Paragraph(esc(row.get("course") or "—"), cell_style),
                Paragraph(esc(row.get("assignment") or "—"), cell_style),
                Paragraph(esc(due), cell_style),
                Paragraph(esc(score), cell_style),
                Paragraph(esc(comment), small_style),
            ]
        )
    table = Table(
        table_rows,
        colWidths=[0.85 * inch, 1.15 * inch, 1.55 * inch, 0.95 * inch, 0.55 * inch, 2.25 * inch],
        repeatRows=1,
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), navy),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), bold),
                ("BACKGROUND", (0, 1), (-1, -1), colors.white),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f7fa")]),
                ("GRID", (0, 0), (-1, -1), 0.3, line),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 8))
    story.append(
        Paragraph(
            "MISSING means not submitted and past due.  LATE means submitted after the due date.  "
            "MESSAGE is a teacher comment or Canvas message.",
            small_style,
        )
    )

    def draw_page(canvas, doc) -> None:
        canvas.saveState()
        width, height = letter
        canvas.setFillColor(navy)
        canvas.rect(0, height - 10, width, 10, fill=1, stroke=0)
        canvas.setFillColor(muted)
        canvas.setFont(body, 8)
        canvas.drawString(0.58 * inch, 0.38 * inch, footer)
        canvas.drawRightString(width - 0.58 * inch, 0.38 * inch, f"Page {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(
        str(output),
        pagesize=letter,
        leftMargin=0.55 * inch,
        rightMargin=0.55 * inch,
        topMargin=0.48 * inch,
        bottomMargin=0.58 * inch,
        title=f"{student} — {title}",
    )
    doc.build(story, onFirstPage=draw_page, onLaterPages=draw_page)
    return output
