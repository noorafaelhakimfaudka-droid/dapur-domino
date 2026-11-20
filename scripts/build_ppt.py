"""Generate the 27-slide Data Science PowerPoint deck (`exports/Dapur_Domino_Data_Science.pptx`).

Reads measured metrics, tables, and verbatim Python code excerpts directly from the
verified repository artifacts (zero fabricated numbers, zero leaked internal PRD codes).
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any

import matplotlib  # type: ignore[import-not-found]

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # type: ignore[import-not-found]
import numpy as np
import pandas as pd
from lxml import etree  # type: ignore[import-untyped]
from pptx import Presentation  # type: ignore[import-not-found]
from pptx.dml.color import RGBColor  # type: ignore[import-not-found]
from pptx.enum.shapes import MSO_SHAPE  # type: ignore[import-not-found]
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN  # type: ignore[import-not-found]
from pptx.oxml.ns import qn  # type: ignore[import-not-found]
from pptx.util import Inches, Pt  # type: ignore[import-not-found]

# Visual identity matching user's warm cream-to-peach gradient prototype
C_BG_TOP = "FBF6EE"
C_BG_MID = "F9ECE0"
C_BG_BOT = "F5D9C6"

RGB_RED = RGBColor(0xD8, 0x43, 0x2B)
RGB_YEL = RGBColor(0xE9, 0xA2, 0x3B)
RGB_YEL_TXT = RGBColor(0xA6, 0x6B, 0x0A)
RGB_GRN = RGBColor(0x2F, 0x6F, 0x55)
RGB_INK = RGBColor(0x1F, 0x1A, 0x17)
RGB_MUT = RGBColor(0x7A, 0x6F, 0x66)
RGB_LINE = RGBColor(0xE8, 0xDC, 0xCB)
RGB_WHITE = RGBColor(0xFF, 0xFF, 0xFF)
RGB_ROW_ALT = RGBColor(0xFC, 0xF7, 0xF0)
RGB_NOTE_BG = RGBColor(0xFF, 0xF3, 0xE0)
RGB_CODE_BG = RGBColor(0x1E, 0x1B, 0x18)
RGB_CODE_FG = RGBColor(0xEA, 0xDF, 0xD0)
RGB_CODE_CAP = RGBColor(0xC9, 0xA4, 0x6B)
RGB_CODE_KW = RGBColor(0xF0, 0x91, 0x6F)
RGB_CODE_CMT = RGBColor(0x8B, 0x81, 0x77)
RGB_CODE_OUT = RGBColor(0x7C, 0xE3, 0x8B)
RGB_CODE_OUT_CAP = RGBColor(0x6C, 0xD4, 0xA2)

HEX_RED = "#D8432B"
HEX_YEL = "#E9A23B"
HEX_GRN = "#2F6F55"
HEX_INK = "#1F1A17"
HEX_MUT = "#7A6F66"
HEX_CREAM = "#FBF6EE"
HEX_GRID = "#EADFD0"

FONT_SERIF = "Georgia"
FONT_SANS = "Segoe UI"
FONT_MONO = "Consolas"

SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)
TOTAL_SLIDES = 32

PY_KEYWORDS = {
    "def",
    "return",
    "for",
    "in",
    "if",
    "elif",
    "else",
    "and",
    "or",
    "not",
    "import",
    "from",
    "as",
    "with",
    "raise",
    "None",
    "True",
    "False",
    "break",
    "continue",
}


def fmt_id_int(val: float | int) -> str:
    return f"{int(round(val)):,}".replace(",", ".")


def fmt_id_dec(val: float, digits: int = 2) -> str:
    return f"{val:,.{digits}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def clean_code_comment(line: str) -> str:
    """Strip internal PRD/VP codes from extracted comments if present."""
    cleaned = re.sub(
        r"\s*\((?:VP\d+|FR-[A-Z]\d+|NFR-\d+|DEV-\d+|Unit\s*\d+|J\.62DMI[^)]*)\)",
        "",
        line,
    )
    cleaned = re.sub(r"\b(?:VP\d+|FR-[A-Z]\d+|NFR-\d+|DEV-\d+):\s*", "", cleaned)
    cleaned = re.sub(r"\b(?:VP\d+|FR-[A-Z]\d+|NFR-\d+|DEV-\d+)\b", "", cleaned)
    return cleaned.rstrip()


def extract_function_snippet(
    file_path: Path,
    func_name: str,
    *,
    max_lines: int = 16,
    max_chars: int = 62,
    skip_markers: tuple[str, str] | None = None,
    skip_ranges: list[tuple[str, str]] | None = None,
    start_at: str | None = None,
) -> list[str]:
    """Extract verbatim core lines of a Python function from disk, skipping docstrings."""
    source = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    lines = source.splitlines()

    target_node: ast.FunctionDef | None = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            target_node = node
            break
    if target_node is None or target_node.end_lineno is None:
        raise KeyError(f"Function {func_name} not found in {file_path}")

    start_idx = target_node.lineno - 1
    end_idx = target_node.end_lineno
    body_first = target_node.body[0] if target_node.body else None
    doc_range: tuple[int, int] | None = None
    if (
        isinstance(body_first, ast.Expr)
        and isinstance(body_first.value, ast.Constant)
        and isinstance(body_first.value.value, str)
        and body_first.end_lineno is not None
    ):
        doc_range = (body_first.lineno - 1, body_first.end_lineno)

    active_skips: list[tuple[str, str]] = list(skip_ranges or [])
    if skip_markers is not None:
        active_skips.append(skip_markers)

    selected: list[str] = []
    active_end: str | None = None
    started = start_at is None
    for i in range(start_idx, end_idx):
        if doc_range and doc_range[0] <= i < doc_range[1]:
            continue
        raw = clean_code_comment(lines[i])
        if not started:
            if start_at is not None and start_at in raw:
                started = True
            else:
                continue
        if active_end is not None:
            if active_end in raw:
                active_end = None
            continue
        matched_end: str | None = None
        for start_m, end_m in active_skips:
            if start_m in raw:
                matched_end = None if start_m == end_m else end_m
                break
        if matched_end is not None or any(s_m == e_m and s_m in raw for s_m, e_m in active_skips):
            active_end = matched_end
            continue
        if not raw.strip():
            continue
        if len(raw) > max_chars:
            raw = raw[: max_chars - 1].rstrip() + "…"
        selected.append(raw)
        if len(selected) >= max_lines:
            break
    return selected


def apply_warm_gradient_background(slide: Any) -> None:
    """Apply diagonal #FBF6EE -> #F6DCCB gradient background + left terracotta stripe."""
    c_sld = slide._element.find(qn("p:cSld"))
    existing_bg = c_sld.find(qn("p:bg"))
    if existing_bg is not None:
        c_sld.remove(existing_bg)

    bg_xml = f"""
    <p:bg xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
          xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <p:bgPr>
        <a:gradFill flip="none" rotWithShape="1">
          <a:gsLst>
            <a:gs pos="0"><a:srgbClr val="{C_BG_TOP}"/></a:gs>
            <a:gs pos="55000"><a:srgbClr val="{C_BG_MID}"/></a:gs>
            <a:gs pos="100000"><a:srgbClr val="{C_BG_BOT}"/></a:gs>
          </a:gsLst>
          <a:lin ang="2700000" scaled="1"/>
        </a:gradFill>
        <a:effectLst/>
      </p:bgPr>
    </p:bg>
    """
    c_sld.insert(0, etree.fromstring(bg_xml))

    # Full-height terracotta left accent bar (0.105 in)
    bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(0.105), SLIDE_H)
    bar.fill.solid()
    bar.fill.fore_color.rgb = RGB_RED
    bar.line.fill.background()


def add_header_footer(
    slide: Any,
    section: str,
    title: str,
    page_num: int,
    *,
    subtitle: str = "",
) -> float:
    """Add uniform editorial header & footer; return top Y coordinate for body content."""
    apply_warm_gradient_background(slide)

    # Section kicker
    tb_k = slide.shapes.add_textbox(Inches(0.58), Inches(0.28), Inches(12.1), Inches(0.26))
    tf_k = tb_k.text_frame
    tf_k.margin_left = tf_k.margin_top = tf_k.margin_right = tf_k.margin_bottom = 0
    p_k = tf_k.paragraphs[0]
    r_k = p_k.add_run()
    r_k.text = section.upper()
    r_k.font.name = FONT_SANS
    r_k.font.size = Pt(10)
    r_k.font.bold = True
    r_k.font.color.rgb = RGB_RED

    # Main serif headline (auto-sized to guarantee clean single-line fit)
    tb_h = slide.shapes.add_textbox(Inches(0.58), Inches(0.52), Inches(12.22), Inches(0.48))
    tf_h = tb_h.text_frame
    tf_h.word_wrap = True
    tf_h.margin_left = tf_h.margin_top = tf_h.margin_right = tf_h.margin_bottom = 0
    p_h = tf_h.paragraphs[0]
    r_h = p_h.add_run()
    r_h.text = title
    r_h.font.name = FONT_SERIF
    r_h.font.size = Pt(20.0 if len(title) > 58 else 22.0)
    r_h.font.bold = True
    r_h.font.color.rgb = RGB_INK

    top_y = 1.12
    if subtitle:
        tb_s = slide.shapes.add_textbox(Inches(0.58), Inches(1.00), Inches(12.22), Inches(0.28))
        tf_s = tb_s.text_frame
        tf_s.word_wrap = True
        tf_s.margin_left = tf_s.margin_top = tf_s.margin_right = tf_s.margin_bottom = 0
        p_s = tf_s.paragraphs[0]
        r_s = p_s.add_run()
        r_s.text = subtitle
        r_s.font.name = FONT_SANS
        r_s.font.size = Pt(11)
        r_s.font.color.rgb = RGB_MUT
        top_y = 1.35

    # Hairline subtle rule under header
    rule = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(0.58), Inches(top_y - 0.05), Inches(12.18), Inches(0.014)
    )
    rule.fill.solid()
    rule.fill.fore_color.rgb = RGB_LINE
    rule.line.fill.background()

    # Footer
    tb_fl = slide.shapes.add_textbox(Inches(0.58), Inches(7.08), Inches(8.0), Inches(0.25))
    tf_fl = tb_fl.text_frame
    tf_fl.margin_left = tf_fl.margin_top = tf_fl.margin_right = tf_fl.margin_bottom = 0
    r_fl = tf_fl.paragraphs[0].add_run()
    r_fl.text = "Dapur Domino · Proyek Analisis Data Science"
    r_fl.font.name = FONT_SANS
    r_fl.font.size = Pt(9.5)
    r_fl.font.color.rgb = RGB_MUT

    tb_fr = slide.shapes.add_textbox(Inches(11.3), Inches(7.08), Inches(1.46), Inches(0.25))
    tf_fr = tb_fr.text_frame
    tf_fr.margin_left = tf_fr.margin_top = tf_fr.margin_right = tf_fr.margin_bottom = 0
    p_fr = tf_fr.paragraphs[0]
    p_fr.alignment = PP_ALIGN.RIGHT
    r_fr = p_fr.add_run()
    r_fr.text = f"{page_num} / {TOTAL_SLIDES}"
    r_fr.font.name = FONT_SANS
    r_fr.font.size = Pt(9.5)
    r_fr.font.bold = True
    r_fr.font.color.rgb = RGB_MUT

    return top_y + 0.06


def add_stat_card(
    slide: Any,
    x: float,
    y: float,
    w: float,
    h: float,
    value: str,
    label: str,
    *,
    accent: RGBColor = RGB_RED,
    val_size: float = 28,
) -> None:
    """Draw clean white KPI card with top accent bar matching screenshot."""
    card = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h)
    )
    card.adjustments[0] = 0.06
    card.fill.solid()
    card.fill.fore_color.rgb = RGB_WHITE
    card.line.color.rgb = RGB_LINE
    card.line.width = Pt(1)

    top_bar = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(x + 0.02), Inches(y), Inches(w - 0.04), Inches(0.06)
    )
    top_bar.fill.solid()
    top_bar.fill.fore_color.rgb = accent
    top_bar.line.fill.background()

    tb = slide.shapes.add_textbox(
        Inches(x + 0.16), Inches(y + 0.14), Inches(w - 0.32), Inches(h - 0.22)
    )
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    p1 = tf.paragraphs[0]
    r1 = p1.add_run()
    r1.text = value
    r1.font.name = FONT_SERIF
    r1.font.size = Pt(val_size)
    r1.font.bold = True
    r1.font.color.rgb = RGB_INK

    p2 = tf.add_paragraph()
    p2.space_before = Pt(3)
    r2 = p2.add_run()
    r2.text = label
    r2.font.name = FONT_SANS
    r2.font.size = Pt(10)
    r2.font.color.rgb = RGB_MUT


def add_note_box(
    slide: Any,
    x: float,
    y: float,
    w: float,
    h: float,
    text: str,
    *,
    title: str = "",
    accent: RGBColor = RGB_YEL,
    font_size: float = 10.5,
) -> None:
    """Add warm tinted insight/callout box with left accent bar."""
    box = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h)
    )
    box.adjustments[0] = 0.04
    box.fill.solid()
    box.fill.fore_color.rgb = RGB_NOTE_BG
    box.line.color.rgb = RGB_LINE
    box.line.width = Pt(0.75)

    bar = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(x), Inches(y + 0.02), Inches(0.065), Inches(h - 0.04)
    )
    bar.fill.solid()
    bar.fill.fore_color.rgb = accent
    bar.line.fill.background()

    tb = slide.shapes.add_textbox(
        Inches(x + 0.16), Inches(y + 0.08), Inches(w - 0.28), Inches(h - 0.16)
    )
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    p = tf.paragraphs[0]
    if title:
        rt = p.add_run()
        rt.text = title + " "
        rt.font.name = FONT_SANS
        rt.font.size = Pt(font_size)
        rt.font.bold = True
        rt.font.color.rgb = RGB_INK
    rb = p.add_run()
    rb.text = text
    rb.font.name = FONT_SANS
    rb.font.size = Pt(font_size)
    rb.font.color.rgb = RGB_INK


def add_code_panel(
    slide: Any,
    x: float,
    y: float,
    w: float,
    h: float,
    sections: list[tuple[str, list[str]]],
    *,
    font_size: float = 8.4,
) -> None:
    """Render dark #1E1B18 code card with caption & light syntax coloring."""
    card = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h)
    )
    card.adjustments[0] = 0.03
    card.fill.solid()
    card.fill.fore_color.rgb = RGB_CODE_BG
    card.line.color.rgb = RGBColor(0x3A, 0x33, 0x2C)
    card.line.width = Pt(1)

    tb = slide.shapes.add_textbox(
        Inches(x + 0.18), Inches(y + 0.14), Inches(w - 0.36), Inches(h - 0.24)
    )
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0

    first = True
    for cap, code_lines in sections:
        is_output = cap.startswith(">>>")
        p_cap = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        p_cap.space_before = Pt(0 if p_cap is tf.paragraphs[0] else 6)
        p_cap.space_after = Pt(2)
        rc = p_cap.add_run()
        rc.text = cap
        rc.font.name = FONT_MONO
        rc.font.size = Pt(font_size - 0.3)
        rc.font.bold = True
        rc.font.color.rgb = RGB_CODE_OUT_CAP if is_output else RGB_CODE_CAP

        for line in code_lines:
            p_ln = tf.add_paragraph()
            p_ln.space_before = Pt(0.4)
            p_ln.space_after = Pt(0.4)
            if is_output:
                ro = p_ln.add_run()
                ro.text = line
                ro.font.name = FONT_MONO
                ro.font.size = Pt(font_size)
                ro.font.color.rgb = RGB_CODE_OUT
                continue
            stripped = line.lstrip()
            if stripped.startswith("#"):
                r = p_ln.add_run()
                r.text = line
                r.font.name = FONT_MONO
                r.font.size = Pt(font_size)
                r.font.color.rgb = RGB_CODE_CMT
                continue

            # Split around inline comment if any
            code_part = line
            cmt_part = ""
            if "  #" in line:
                idx_c = line.index("  #")
                code_part = line[:idx_c]
                cmt_part = line[idx_c:]

            tokens = re.split(r"(\b[A-Za-z_][A-Za-z0-9_]*\b)", code_part)
            for tok in tokens:
                if not tok:
                    continue
                r = p_ln.add_run()
                r.text = tok
                r.font.name = FONT_MONO
                r.font.size = Pt(font_size)
                r.font.color.rgb = RGB_CODE_KW if tok in PY_KEYWORDS else RGB_CODE_FG
            if cmt_part:
                rcmt = p_ln.add_run()
                rcmt.text = cmt_part
                rcmt.font.name = FONT_MONO
                rcmt.font.size = Pt(font_size)
                rcmt.font.color.rgb = RGB_CODE_CMT


def add_clean_table(
    slide: Any,
    x: float,
    y: float,
    w: float,
    h: float,
    headers: list[str],
    rows: list[list[str]],
    col_widths: list[float],
    *,
    font_size: float = 9.5,
    header_size: float = 9.5,
    bold_cols: set[int] | None = None,
    right_cols: set[int] | None = None,
    cell_color_fn: Any = None,
) -> None:
    """Create a clean crisp table with dark ink header, warm alternating rows, no ugly blue grid."""
    bold_cols = bold_cols or set()
    right_cols = right_cols or set()
    n_rows = 1 + len(rows)
    n_cols = len(headers)

    tbl_shape = slide.shapes.add_table(n_rows, n_cols, Inches(x), Inches(y), Inches(w), Inches(h))
    tbl = tbl_shape.table
    tbl.first_row = False
    tbl.horz_banding = False

    # Clear Office default blue table style XML tags if present
    tbl_pr = tbl._tbl.find(qn("a:tblPr"))
    if tbl_pr is not None:
        style_id = tbl_pr.find(qn("a:tableStyleId"))
        if style_id is not None:
            tbl_pr.remove(style_id)

    for idx, cw in enumerate(col_widths):
        tbl.columns[idx].width = Inches(cw)

    # Header row
    for c_idx, hdr in enumerate(headers):
        cell = tbl.cell(0, c_idx)
        cell.fill.solid()
        cell.fill.fore_color.rgb = RGB_INK
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        cell.margin_left = Inches(0.08)
        cell.margin_right = Inches(0.08)
        cell.margin_top = Inches(0.04)
        cell.margin_bottom = Inches(0.04)
        p = cell.text_frame.paragraphs[0]
        p.alignment = PP_ALIGN.RIGHT if c_idx in right_cols else PP_ALIGN.LEFT
        r = p.add_run()
        r.text = hdr
        r.font.name = FONT_SANS
        r.font.size = Pt(header_size)
        r.font.bold = True
        r.font.color.rgb = RGB_WHITE

    # Body rows
    for r_idx, row in enumerate(rows, start=1):
        bg_rgb = RGB_WHITE if r_idx % 2 == 1 else RGB_ROW_ALT
        for c_idx, val in enumerate(row):
            cell = tbl.cell(r_idx, c_idx)
            cell.fill.solid()
            cell.fill.fore_color.rgb = bg_rgb
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.margin_left = Inches(0.08)
            cell.margin_right = Inches(0.08)
            cell.margin_top = Inches(0.03)
            cell.margin_bottom = Inches(0.03)

            # Bottom hairline border on cell
            tc_pr = cell._tc.get_or_add_tcPr()
            for tag in ("a:lnL", "a:lnR", "a:lnT"):
                old = tc_pr.find(qn(tag))
                if old is not None:
                    tc_pr.remove(old)
                tc_pr.append(
                    etree.fromstring(
                        f'<{tag} xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
                        "<a:noFill/></"
                        f"{tag}>"
                    )
                )
            old_b = tc_pr.find(qn("a:lnB"))
            if old_b is not None:
                tc_pr.remove(old_b)
            tc_pr.append(
                etree.fromstring(
                    '<a:lnB xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'
                    ' w="6350">'
                    '<a:solidFill><a:srgbClr val="E8DCCB"/></a:solidFill></a:lnB>'
                )
            )

            p = cell.text_frame.paragraphs[0]
            p.alignment = PP_ALIGN.RIGHT if c_idx in right_cols else PP_ALIGN.LEFT
            r = p.add_run()
            r.text = str(val)
            r.font.name = FONT_SANS
            r.font.size = Pt(font_size)
            is_bold = c_idx in bold_cols
            txt_rgb = RGB_INK
            if cell_color_fn is not None:
                override = cell_color_fn(r_idx - 1, c_idx, str(val))
                if override is not None:
                    txt_rgb, extra_bold = override
                    is_bold = is_bold or extra_bold
            r.font.bold = is_bold
            r.font.color.rgb = txt_rgb


def _style_mpl_ax(ax: Any) -> None:
    ax.set_facecolor("#FFFFFF")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(HEX_GRID)
    ax.spines["bottom"].set_color(HEX_GRID)
    ax.tick_params(colors=HEX_INK, labelsize=9)
    ax.grid(axis="x", linestyle="--", linewidth=0.6, color=HEX_GRID, alpha=0.8)
    ax.set_axisbelow(True)


def render_charts(chart_dir: Path, data: dict[str, Any]) -> dict[str, Path]:
    """Render high-DPI clean charts directly from verified CSV artifacts."""
    chart_dir.mkdir(parents=True, exist_ok=True)
    plt.rcParams["font.sans-serif"] = ["Segoe UI", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    paths: dict[str, Path] = {}

    # 1. Slide 4 chart: Price CV% across 10 commodities
    eda_p = data["eda_prices"].sort_values("cv_pct", ascending=True)
    fig, ax = plt.subplots(figsize=(5.6, 3.85), dpi=220)
    fig.patch.set_facecolor("#FFFFFF")
    _style_mpl_ax(ax)
    colors = [HEX_RED if v >= 15 else (HEX_YEL if v >= 6 else HEX_GRN) for v in eda_p["cv_pct"]]
    bars = ax.barh(eda_p["commodity_name"], eda_p["cv_pct"], color=colors, height=0.62)
    for bar, v in zip(bars, eda_p["cv_pct"], strict=True):
        ax.text(
            bar.get_width() + 0.35,
            bar.get_y() + bar.get_height() / 2,
            f"{fmt_id_dec(float(v), 2)}%",
            va="center",
            fontsize=8.5,
            color=HEX_INK,
            fontweight="bold",
        )
    ax.set_xlim(0, 24.5)
    ax.set_title(
        "Seberapa Liar Harga Naik-Turun Selama 3 Tahun? (CV%)",
        fontsize=10.5,
        fontweight="bold",
        color=HEX_INK,
        loc="left",
        pad=10,
    )
    ax.set_xlabel("Besar goyangan harga dibanding rata-ratanya (%)", fontsize=8.5, color=HEX_MUT)
    fig.tight_layout(pad=1.0)
    p4 = chart_dir / "chart_s4_cv.png"
    fig.savefig(p4, facecolor="#FFFFFF")
    plt.close(fig)
    paths["s4_cv"] = p4

    # 2. Slide 5 chart: Zipf concentration in recipes
    fig, ax = plt.subplots(figsize=(5.2, 2.3), dpi=220)
    fig.patch.set_facecolor("#FFFFFF")
    _style_mpl_ax(ax)
    cats = ["Top-10 Bahan", "Peringkat 11–50", "1.284 Bahan Lainnya"]
    shares = [40.64, 80.40 - 40.64, 100.0 - 80.40]
    cols = [HEX_RED, HEX_YEL, HEX_GRN]
    bars = ax.barh(cats[::-1], shares[::-1], color=cols[::-1], height=0.52)
    for bar, v in zip(bars, shares[::-1], strict=True):
        ax.text(
            bar.get_width() + 0.8,
            bar.get_y() + bar.get_height() / 2,
            f"{fmt_id_dec(v, 1)}%",
            va="center",
            fontsize=9,
            color=HEX_INK,
            fontweight="bold",
        )
    ax.set_xlim(0, 50)
    ax.set_title(
        "Segelintir Bumbu Menguasai Dapur Indonesia (Pola Zipf)",
        fontsize=10.2,
        fontweight="bold",
        color=HEX_INK,
        loc="left",
        pad=8,
    )
    fig.tight_layout(pad=0.8)
    p5 = chart_dir / "chart_s5_zipf.png"
    fig.savefig(p5, facecolor="#FFFFFF")
    plt.close(fig)
    paths["s5_zipf"] = p5

    # 3. Slide 7 chart: Stationarity Level vs Log-Return
    m1_l = data["m1_sum"].get("levels", data["m1_sum"])
    levels = ["Nasional\n(10 seri)", "Provinsi\n(340 seri)", "Kota/Kab\n(1.049 seri)"]
    raw_pcts = [
        100.0 * m1_l["national"]["stationarity_vp4"]["level_stationary_both"] / 10,
        100.0 * m1_l["province"]["stationarity_vp4"]["level_stationary_both"] / 340,
        100.0 * m1_l["city"]["stationarity_vp4"]["level_stationary_both"] / 1049,
    ]
    ret_pcts = [
        m1_l["national"]["stationarity_vp4"]["return_stationary_both_pct"],
        m1_l["province"]["stationarity_vp4"]["return_stationary_both_pct"],
        m1_l["city"]["stationarity_vp4"]["return_stationary_both_pct"],
    ]
    x_idx = np.arange(len(levels))
    w_bar = 0.34
    fig, ax = plt.subplots(figsize=(5.5, 3.3), dpi=220)
    fig.patch.set_facecolor("#FFFFFF")
    ax.set_facecolor("#FFFFFF")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", linestyle="--", linewidth=0.6, color=HEX_GRID, alpha=0.8)
    ax.set_axisbelow(True)
    b1 = ax.bar(
        x_idx - w_bar / 2, raw_pcts, width=w_bar, label="Harga Rupiah Mentah", color="#C9BFB3"
    )
    b2 = ax.bar(
        x_idx + w_bar / 2, ret_pcts, width=w_bar, label="% Gerak Harian (Log-Return)", color=HEX_GRN
    )
    for bars_grp in (b1, b2):
        for bar in bars_grp:
            h_v = bar.get_height()
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                h_v + 1.8,
                f"{fmt_id_dec(h_v, 1)}%",
                ha="center",
                fontsize=8.5,
                fontweight="bold",
                color=HEX_INK,
            )
    ax.set_xticks(x_idx)
    ax.set_xticklabels(levels, fontsize=9, color=HEX_INK)
    ax.set_ylim(0, 114)
    ax.set_title(
        "Persentase Seri Aman Dimodelkan (Lolos 2 Pintu ADF+KPSS)",
        fontsize=10.2,
        fontweight="bold",
        color=HEX_INK,
        loc="left",
        pad=10,
    )
    ax.legend(frameon=False, fontsize=8.5, loc="upper left")
    fig.tight_layout(pad=0.9)
    p7 = chart_dir / "chart_s7_stationarity.png"
    fig.savefig(p7, facecolor="#FFFFFF")
    plt.close(fig)
    paths["s7_stat"] = p7

    # 4. Slide 12 chart: 8 validation scenarios skill comparison
    sc = data["scen_ts"].iloc[::-1].reset_index(drop=True)
    labels_sc = []
    for _, r in sc.iterrows():
        desc = str(r["scenario_description"])
        reg = "Bebas Musim" if "Seasonally" in desc else "Mentah"
        star = " (Dipilih)" if "DIPILIH" in desc else ""
        alpha_str = fmt_id_dec(float(r["ridge_alpha"]), 3).rstrip("0").rstrip(",")
        labels_sc.append(f"Jeda {int(r['lag_order'])} hr · Rem {alpha_str} · {reg}{star}")

    y_pos = np.arange(len(sc))
    h_b = 0.36
    fig, ax = plt.subplots(figsize=(5.6, 3.65), dpi=220)
    fig.patch.set_facecolor("#FFFFFF")
    _style_mpl_ax(ax)
    ax.axvline(0, color=HEX_INK, linewidth=0.9)
    ax.barh(
        y_pos + h_b / 2,
        sc["mean_skill_vs_ar_pct"],
        height=h_b,
        label="Unggul vs Riwayat Sendiri (AR)",
        color=HEX_GRN,
    )
    ax.barh(
        y_pos - h_b / 2,
        sc["mean_skill_vs_naive_pct"],
        height=h_b,
        label="Unggul vs Harga Kemarin (Naive)",
        color=HEX_YEL,
    )
    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels_sc, fontsize=7.6)
    ax.set_xlim(-7.6, 7.2)
    ax.set_xlabel("Selisih Kesalahan Prediksi vs Tebakan Polos (%)", fontsize=8.5, color=HEX_MUT)
    ax.set_title(
        "Adu 8 Setelan Model di Ruang Simulasi (Hari 400–500)",
        fontsize=10,
        fontweight="bold",
        color=HEX_INK,
        loc="left",
        pad=22,
    )
    ax.legend(
        frameon=False,
        fontsize=7.9,
        loc="lower left",
        bbox_to_anchor=(0.0, 1.005),
        ncol=2,
    )
    fig.tight_layout(pad=0.8)
    p12 = chart_dir / "chart_s12_scen.png"
    fig.savefig(p12, facecolor="#FFFFFF", bbox_inches="tight", pad_inches=0.10)
    plt.close(fig)
    paths["s12_scen"] = p12

    # 5. Slide 15 chart: Idul Fitri 2026 surge
    eid = data["eid"]
    eid26 = eid.loc[eid["event"] == "Idul_Fitri_2026"].sort_values("pct_change_to_peak")
    fig, ax = plt.subplots(figsize=(5.4, 3.85), dpi=220)
    fig.patch.set_facecolor("#FFFFFF")
    _style_mpl_ax(ax)
    ax.axvline(0, color=HEX_INK, linewidth=0.9)
    ecols = [
        HEX_RED if v >= 10 else (HEX_YEL if v > 0 else HEX_GRN) for v in eid26["pct_change_to_peak"]
    ]
    bars = ax.barh(eid26["commodity_name"], eid26["pct_change_to_peak"], color=ecols, height=0.6)
    for bar, v in zip(bars, eid26["pct_change_to_peak"], strict=True):
        off = 0.45 if v >= 0 else -0.45
        ha = "left" if v >= 0 else "right"
        ax.text(
            bar.get_width() + off,
            bar.get_y() + bar.get_height() / 2,
            f"{'+' if v > 0 else ''}{fmt_id_dec(float(v), 2)}%",
            va="center",
            ha=ha,
            fontsize=8.2,
            fontweight="bold",
            color=HEX_INK,
        )
    ax.set_xlim(-5.5, 24.0)
    ax.set_title(
        "Lonjakan Harga Puncak Lebaran 2026 vs Hari Normal (%)",
        fontsize=10,
        fontweight="bold",
        color=HEX_INK,
        loc="left",
        pad=8,
    )
    fig.tight_layout(pad=0.9)
    p15 = chart_dir / "chart_s15_eid.png"
    fig.savefig(p15, facecolor="#FFFFFF")
    plt.close(fig)
    paths["s15_eid"] = p15

    # 6. Slide 18 chart: Walk-forward Out-of-Sample Skill vs AR(5)
    wfs = data["wf_seas"].sort_values("skill_vs_ar_pct", ascending=True)
    fig, ax = plt.subplots(figsize=(5.6, 4.0), dpi=220)
    fig.patch.set_facecolor("#FFFFFF")
    _style_mpl_ax(ax)
    ax.axvline(0, color=HEX_INK, linewidth=0.9)
    wcols = [HEX_GRN if v > 0 else HEX_RED for v in wfs["skill_vs_ar_pct"]]
    bars = ax.barh(wfs["commodity_name"], wfs["skill_vs_ar_pct"], color=wcols, height=0.6)
    for bar, v in zip(bars, wfs["skill_vs_ar_pct"], strict=True):
        off = 0.4 if v >= 0 else -0.4
        ha = "left" if v >= 0 else "right"
        ax.text(
            bar.get_width() + off,
            bar.get_y() + bar.get_height() / 2,
            f"{'+' if v > 0 else ''}{fmt_id_dec(float(v), 2)}%",
            va="center",
            ha=ha,
            fontsize=8.2,
            fontweight="bold",
            color=HEX_INK,
        )
    ax.set_xlim(-13.5, 20.0)
    ax.set_title(
        "Domino vs Riwayat Sendiri (296 Hari Ujian · Bebas Musim)",
        fontsize=10,
        fontweight="bold",
        color=HEX_INK,
        loc="left",
        pad=8,
    )
    fig.tight_layout(pad=0.9)
    p18 = chart_dir / "chart_s18_wf.png"
    fig.savefig(p18, facecolor="#FFFFFF")
    plt.close(fig)
    paths["s18_wf"] = p18

    # 7. Slide 20 chart: Substitusi Error Taxonomy breakdown
    err_df = data["err_tax"]
    counts = err_df["error_category"].value_counts()
    lbls = []
    for k in counts.index:
        sk = str(k)
        if "HIT" in sk:
            lbls.append("Tepat Sasaran Top-5")
        elif "Varian" in sk:
            lbls.append("Varian Bentuk Sama")
        else:
            lbls.append("Konteks Serumpun")
    vals = [int(v) for v in counts.values]
    fig, ax = plt.subplots(figsize=(5.5, 2.35), dpi=220)
    fig.patch.set_facecolor("#FFFFFF")
    _style_mpl_ax(ax)
    ec_cols = [
        HEX_RED if "Varian" in lbl else (HEX_YEL if "Konteks" in lbl else HEX_GRN) for lbl in lbls
    ]
    bars = ax.barh(lbls[::-1], vals[::-1], color=ec_cols[::-1], height=0.52)
    for bar, v in zip(bars, vals[::-1], strict=True):
        ax.text(
            bar.get_width() + 0.25,
            bar.get_y() + bar.get_height() / 2,
            f"{v}/25 ({int(round(100 * v / 25))}%)",
            va="center",
            fontsize=8.5,
            fontweight="bold",
            color=HEX_INK,
        )
    ax.set_xlim(0, 14.5)
    ax.set_title(
        "Bedah 25 Soal Acuan Pengganti Bahan",
        fontsize=10.5,
        fontweight="bold",
        color=HEX_INK,
        loc="left",
        pad=8,
    )
    fig.tight_layout(pad=0.8)
    p20 = chart_dir / "chart_s20_err.png"
    fig.savefig(p20, facecolor="#FFFFFF", bbox_inches="tight", pad_inches=0.10)
    plt.close(fig)
    paths["s20_err"] = p20

    return paths


def load_all_project_data(repo_root: Path) -> dict[str, Any]:
    """Load all verified artifacts from the latest Nov 18 runs and analysis directory."""
    analysis_dir = repo_root / "artifacts" / "analysis"
    runs_dir = repo_root / "artifacts" / "runs"
    m1_dir = sorted(runs_dir.glob("m1_*"))[-1]
    m2_dir = sorted(runs_dir.glob("m2_*"))[-1]
    m3_dir = sorted(runs_dir.glob("m3_*"))[-1]
    m4_dir = sorted(runs_dir.glob("m4_*"))[-1]

    return {
        "repo_root": repo_root,
        "bo": pd.read_csv(analysis_dir / "business_objectives.csv"),
        "tdo": pd.read_csv(analysis_dir / "technical_objectives.csv"),
        "eda_prices": pd.read_csv(analysis_dir / "eda_prices_stats.csv"),
        "eda_corr": pd.read_csv(analysis_dir / "eda_returns_corr.csv"),
        "eda_recipes": pd.read_csv(analysis_dir / "eda_recipes_stats.csv"),
        "val_rep": pd.read_csv(analysis_dir / "data_validation_report.csv"),
        "sel_mat": pd.read_csv(analysis_dir / "data_selection_matrix.csv"),
        "cln_aud": pd.read_csv(analysis_dir / "data_cleaning_audit.csv"),
        "fea_aud": pd.read_csv(analysis_dir / "feature_engineering_audit.csv"),
        "scen_ts": pd.read_csv(analysis_dir / "scenarios_timeseries_val.csv"),
        "scen_br": pd.read_csv(analysis_dir / "scenarios_bridge_sensitivity.csv"),
        "registry": pd.read_csv(analysis_dir / "model_registry.csv"),
        "err_tax": pd.read_csv(analysis_dir / "vp3_error_taxonomy.csv"),
        "rev_dec": pd.read_csv(analysis_dir / "model_review_decisions.csv"),
        "lifecycle": json.loads(
            (analysis_dir / "lifecycle_summary.json").read_text(encoding="utf-8")
        ),
        "m1_sum": json.loads((m1_dir / "m1_summary.json").read_text(encoding="utf-8")),
        "m2_sum": json.loads((m2_dir / "m2_summary.json").read_text(encoding="utf-8")),
        "m3_sum": json.loads((m3_dir / "m3_summary.json").read_text(encoding="utf-8")),
        "m4_sum": json.loads((m4_dir / "m4_summary.json").read_text(encoding="utf-8")),
        "edges_raw": pd.read_csv(m2_dir / "commodity_edges_raw_train.csv"),
        "prov_sum": pd.read_csv(m2_dir / "spatial_province_summary.csv"),
        "city_sum": pd.read_csv(m2_dir / "spatial_city_summary.csv"),
        "eid": pd.read_csv(m2_dir / "case_study_idul_fitri.csv"),
        "wf_raw": pd.read_csv(m2_dir / "walk_forward_raw.csv"),
        "wf_seas": pd.read_csv(m2_dir / "walk_forward_seasonal_adj.csv"),
        "stat_nat": pd.read_csv(m1_dir / "stationarity_national.csv"),
        "stage_resources": {
            "m1": json.loads((m1_dir / "manifest.json").read_text(encoding="utf-8")).get(
                "resources", {}
            ),
            "m2": json.loads((m2_dir / "manifest.json").read_text(encoding="utf-8")).get(
                "resources", {}
            ),
            "m3": json.loads((m3_dir / "manifest.json").read_text(encoding="utf-8")).get(
                "resources", {}
            ),
            "m4": json.loads((m4_dir / "manifest.json").read_text(encoding="utf-8")).get(
                "resources", {}
            ),
        },
        "bridge_eval": pd.read_csv(m4_dir / "bridge_eval_summary.csv"),
    }


def build_presentation(repo_root: Path, out_pptx: Path) -> None:
    """Assemble the complete 27-slide PowerPoint presentation."""
    data = load_all_project_data(repo_root)
    chart_dir = repo_root / "exports" / "_charts_tmp"
    charts = render_charts(chart_dir, data)

    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H
    blank_layout = prs.slide_layouts[6]

    src = repo_root / "src" / "dapur_domino"

    # =========================================================================
    # SLIDE 1: COVER (matching user's screenshot closely)
    # =========================================================================
    s1 = prs.slides.add_slide(blank_layout)
    apply_warm_gradient_background(s1)

    tb_k = s1.shapes.add_textbox(Inches(0.75), Inches(1.35), Inches(7.2), Inches(0.32))
    r_k = tb_k.text_frame.paragraphs[0].add_run()
    r_k.text = "PROYEK DATA SCIENCE · PERAMALAN HARGA & REKOMENDASI KULINER"
    r_k.font.name = FONT_SANS
    r_k.font.size = Pt(11.5)
    r_k.font.bold = True
    r_k.font.color.rgb = RGB_RED

    tb_title = s1.shapes.add_textbox(Inches(0.72), Inches(1.68), Inches(7.0), Inches(2.5))
    tf_t = tb_title.text_frame
    tf_t.word_wrap = True
    p_t = tf_t.paragraphs[0]
    p_t.line_spacing = 0.96
    r_t = p_t.add_run()
    r_t.text = "Dapur\nDomino"
    r_t.font.name = FONT_SERIF
    r_t.font.size = Pt(78)
    r_t.font.bold = True
    r_t.font.color.rgb = RGB_INK

    tb_lead = s1.shapes.add_textbox(Inches(0.75), Inches(4.28), Inches(6.6), Inches(1.2))
    tf_l = tb_lead.text_frame
    tf_l.word_wrap = True
    p_l = tf_l.paragraphs[0]
    p_l.line_spacing = 1.28
    r_l = p_l.add_run()
    r_l.text = (
        "Melacak efek berantai kenaikan harga pangan nasional dan menyarankan "
        "pengganti bahan masakan Nusantara yang cocok di rasa serta aman di dompet."
    )
    r_l.font.name = FONT_SANS
    r_l.font.size = Pt(17)
    r_l.font.color.rgb = RGB_INK

    tb_sub = s1.shapes.add_textbox(Inches(0.75), Inches(5.55), Inches(6.5), Inches(0.7))
    tf_sub = tb_sub.text_frame
    tf_sub.word_wrap = True
    r_sub = tf_sub.paragraphs[0].add_run()
    r_sub.text = (
        "Rambatan harga harian · peta jaringan 69.915 resep · AI lokal (Word2Vec) · "
        "berjalan ringan di laptop tanpa cloud/LLM."
    )
    r_sub.font.name = FONT_SANS
    r_sub.font.size = Pt(12)
    r_sub.font.color.rgb = RGB_MUT

    # 2x2 KPI block on the right (exact mirror of screenshot)
    add_stat_card(
        s1,
        8.15,
        1.48,
        2.25,
        1.42,
        "1.141.526",
        "catatan harga pasar BI",
        accent=RGB_RED,
        val_size=26,
    )
    add_stat_card(
        s1, 10.56, 1.48, 2.15, 1.42, "796", "hari pasar aktif", accent=RGB_YEL, val_size=26
    )
    add_stat_card(
        s1, 8.15, 3.08, 2.25, 1.42, "69.915", "resep masakan Nusantara", accent=RGB_GRN, val_size=26
    )
    add_stat_card(
        s1,
        10.56,
        3.08,
        2.15,
        1.42,
        "8",
        "model lokal konsisten (seed 42)",
        accent=RGB_RED,
        val_size=26,
    )
    add_note_box(
        s1,
        8.15,
        4.72,
        4.56,
        1.15,
        (
            "10 bahan pokok di level Nasional, 34 Provinsi, & 105 Kota "
            "(Nov 2023 – Nov 2026), terhubung ke 1.334 bahan masakan standar."
        ),
        title="Cakupan:",
        accent=RGB_YEL,
        font_size=10.5,
    )

    # =========================================================================
    # SLIDE 2: PERUMUSAN OBJEKTIF BISNIS (no BO-1..BO-4!)
    # =========================================================================
    s2 = prs.slides.add_slide(blank_layout)
    y0 = add_header_footer(
        s2,
        "Unit 1 · J.62DMI00.001.1 · Menentukan Objektif Bisnis",
        "Empat tujuan usaha: masalah siapa yang ingin kita bantu?",
        2,
        subtitle=(
            "Sebelum menyentuh data, keluhan pembeli pasar, warung, & juru masak "
            "dikunci menjadi janji target angka."
        ),
    )
    bo_rows = [
        [
            "Rumah Tangga & Konsumen",
            "Asal pilih pengganti saat bahan pokok mahal hingga rasa rusak atau tetap boros",
            "Saran pengganti yang pas di resep & stabil harganya (30 hari terakhir)",
            "Cakupan >= 25% pemakaian dapur; 0 harga ngarang di luar daftar BI",
        ],
        [
            "UMKM Kuliner & Warung",
            "Telat sadar saat kenaikan harga satu bahan merembet ke bahan & kota lain",
            "Peta rambatan harga antar-bahan pokok & daerah pemicu awal",
            "Sinyal hoki maksimal 5%; klaim hanya jika menang di data ujian baru",
        ],
        [
            "Juru Masak Harian",
            "Bahan sisa di kulkas terbuang karena bingung memadukan bumbu yang klop",
            "Saran bumbu pelengkap & resep dari 1–5 bahan sisa di kulkas",
            "Akurasi 5 saran teratas unggul nyata atas tebakan bumbu terpopuler",
        ],
        [
            "Integritas Riset Ilmiah",
            "Risiko model curang mengintip masa depan atau mengaku menang sepihak",
            "Segel ketat data ujian, cek sidik jari file mentah, & laporan kekalahan jujur",
            "100% berkas tercek SHA-256; 0% bocor data ujian; bisa diulang persis (seed 42)",
        ],
    ]
    add_clean_table(
        s2,
        0.58,
        y0,
        12.18,
        4.45,
        [
            "Siapa yang Dibantu",
            "Masalah di Lapangan",
            "Solusi yang Dibangun",
            "Ukuran Sukses (KPI)",
        ],
        bo_rows,
        [2.3, 3.0, 3.58, 3.3],
        font_size=10,
        bold_cols={0},
    )
    add_note_box(
        s2,
        0.58,
        6.02,
        12.18,
        0.82,
        (
            "Seluruh eksperimen berjalan 100% lokal di laptop biasa (RAM <= 8 GB), "
            "tanpa bantuan cloud LLM, serta menolak keras mengarang harga buatan "
            "untuk bahan di luar catatan resmi Bank Indonesia."
        ),
        title="Pagar Batasan Proyek:",
        accent=RGB_RED,
        font_size=10.5,
    )

    # =========================================================================
    # SLIDE 3: TUJUAN TEKNIS DATA SCIENCE (no TDO-1..7 or VP1..7!)
    # =========================================================================
    s3 = prs.slides.add_slide(blank_layout)
    y0 = add_header_footer(
        s3,
        "Unit 2 · J.62DMI00.002.1 · Menentukan Tujuan Teknis Data Science",
        "Mengubah keluhan dapur menjadi 7 target Ilmuwan Data",
        3,
    )
    tdo_rows = [
        [
            "Merapikan tulisan resep",
            "Hapus satuan takaran & 236 kamus sinonim",
            ">= 90,0% bersih (cek 300 baris)",
            "90,33% (271/300)",
        ],
        [
            "Saran bumbu isi kulkas",
            "Jaringan pasangan & skor cocok (Cond. PMI)",
            "> Tebakan populer (CI 95% pisah)",
            "45,50% vs 40,88%",
        ],
        [
            "Cari pengganti bahan",
            "AI peta makna Word2Vec + penalti sepanci",
            "Uji 25 soal kuliner & bedah gagal",
            "24,0% (6/25) · MRR 0,21",
        ],
        [
            "Cek keamanan data harga",
            "Ubah ke % gerak harian + cek 2 pintu",
            "Mayoritas seri lolos keduanya",
            "90,0% Nas · 98,2% Prov",
        ],
        [
            "Saring domino kebetulan",
            "Tes rambatan + kontrol FDR + 20× kocok acak",
            "Sinyal palsu acak <= 5%",
            "3,44% palsu · 100% tahan",
        ],
        [
            "Uji ramalan hari depan",
            "Prediksi berjalan Ridge ARX(5) vs AR(5)",
            "Menang adil per bahan (DM test)",
            "Unggul di 3/10 bahan",
        ],
        [
            "Gabung rasa & dompet",
            "60% cocok resep + 40% harga tenang 30 hr",
            ">= 25% dapur; 0 harga palsu",
            "27,74% pemakaian dapur",
        ],
    ]
    add_clean_table(
        s3,
        0.58,
        y0,
        6.85,
        5.35,
        ["Tujuan Teknis", "Pendekatan Algoritma", "Target / Baseline", "Hasil Terukur"],
        tdo_rows,
        [1.7, 1.9, 1.75, 1.5],
        font_size=9.2,
        bold_cols={0, 3},
    )
    add_code_panel(
        s3,
        7.62,
        y0,
        5.14,
        5.35,
        [
            (
                "src/dapur_domino/prices/stationarity.py · Statsmodels ADF & KPSS",
                extract_function_snippet(
                    src / "prices" / "stationarity.py",
                    "test_series_stationarity",
                    max_lines=10,
                    max_chars=56,
                    skip_markers=("    with warnings", "            kpss_note"),
                    start_at="adf_stat, adf_p",
                ),
            ),
            (
                "src/dapur_domino/recipes/embedding.py · Gensim Neural Word2Vec",
                extract_function_snippet(
                    src / "recipes" / "embedding.py",
                    "train_ingredient_embeddings",
                    max_lines=9,
                    max_chars=56,
                    start_at="return Word2Vec(",
                ),
            ),
            (
                "src/dapur_domino/evaluation/walk_forward.py · NumPy Ridge Algebra",
                extract_function_snippet(
                    src / "evaluation" / "walk_forward.py",
                    "_fit_ridge",
                    max_lines=8,
                    max_chars=56,
                ),
            ),
        ],
        font_size=7.6,
    )

    # =========================================================================
    # SLIDE 4: EDA DERET WAKTU HARGA (real chart + stats table + real code)
    # =========================================================================
    s4 = prs.slides.add_slide(blank_layout)
    y0 = add_header_footer(
        s4,
        "Unit 3 · J.62DMI00.005.1 · Menelaah Data",
        "Cabai bergejolak hampir 7× lipat (20,8%), beras paling tenang (2,96%)",
        4,
        subtitle=(
            "Mengintip seberapa liar harga 10 bahan pokok naik-turun selama "
            "796 hari pasar aktif (Nov 2023 – Nov 2026)."
        ),
    )
    # Left top: chart PNG; Left bottom: concise takeaway stats
    pic4 = s4.shapes.add_picture(str(charts["s4_cv"]), Inches(0.58), Inches(y0), width=Inches(6.25))
    _ = pic4
    add_note_box(
        s4,
        0.58,
        5.68,
        6.25,
        1.20,
        (
            "Daging Sapi paling mahal per kilo (Rp 138 rb), tapi goyangannya amat jinak "
            "(3,45%). Sebaliknya Bawang Merah paling sering bikin kaget melonjak tiba-tiba "
            "(skewness +4,17) — membuktikan Rupiah mentah tak bisa disamakan langsung."
        ),
        title="Watak Harga di Pasar:",
        accent=RGB_YEL,
        font_size=9.7,
    )
    add_code_panel(
        s4,
        7.05,
        y0,
        5.71,
        5.42,
        [
            (
                "src/dapur_domino/evaluation/lifecycle.py · Hitung Goyangan & Arah Lonjakan",
                extract_function_snippet(
                    src / "evaluation" / "lifecycle.py",
                    "analyze_price_distributions",
                    max_lines=17,
                    max_chars=66,
                    skip_ranges=[
                        ('                "comcat_id":', '                "std_idr":'),
                        ('                "min_idr":', '                "return_std_daily_pct":'),
                    ],
                    start_at="q25 = float(",
                ),
            ),
            (
                ">>> OUTPUT NYATA (eda_prices_stats.csv · 796 hari aktif)",
                [
                    "Cabai Rawit  | mean=Rp 61.035 | cv=20,80% | skew=+1,04",
                    "Cabai Merah  | mean=Rp 54.101 | cv=19,95% | skew=+0,96",
                    "Bawang Merah | mean=Rp 42.186 | cv=16,17% | skew=+4,17",
                    "Daging Sapi  | mean=Rp138.707 | cv= 3,45% | skew=-1,86",
                    "Beras        | mean=Rp 15.598 | cv= 2,96% | skew=+0,70",
                ],
            ),
        ],
        font_size=7.4,
    )

    # =========================================================================
    # SLIDE 5: EDA KORPUS RESEP NUSANTARA
    # =========================================================================
    s5 = prs.slides.add_slide(blank_layout)
    y0 = add_header_footer(
        s5,
        "Unit 3 · J.62DMI00.005.1 · Menelaah Data",
        "Jumlah bahan resep seimbang; 50 bumbu inti kuasai 80% dapur",
        5,
        subtitle=(
            "Memastikan soal uji (3.496 resep) sebanding dengan buku latihan (66.419 resep) "
            "& melihat bumbu paling populer."
        ),
    )
    add_stat_card(
        s5,
        0.58,
        y0,
        2.75,
        1.30,
        "13,02",
        "rata-rata bahan/resep · Latih (tengah 13)",
        accent=RGB_RED,
        val_size=26,
    )
    add_stat_card(
        s5,
        3.50,
        y0,
        2.75,
        1.30,
        "13,06",
        "rata-rata bahan/resep · Uji (tengah 13)",
        accent=RGB_YEL,
        val_size=26,
    )
    add_stat_card(
        s5,
        0.58,
        y0 + 1.46,
        2.75,
        1.30,
        "40,64%",
        "seluruh catatan resep dikuasai 10 bumbu",
        accent=RGB_GRN,
        val_size=26,
    )
    add_stat_card(
        s5,
        3.50,
        y0 + 1.46,
        2.75,
        1.30,
        "80,40%",
        "seluruh catatan resep dikuasai 50 bumbu",
        accent=RGB_RED,
        val_size=26,
    )

    s5.shapes.add_picture(
        str(charts["s5_zipf"]), Inches(0.58), Inches(y0 + 2.92), width=Inches(5.67)
    )

    eda_r_rows = [
        ["Jumlah bahan / resep (Latih)", "66.419", "13,02", "13,00", "22,00"],
        ["Jumlah bahan / resep (Uji)", "3.496", "13,06", "13,00", "22,00"],
        ["Frekuensi muncul tiap bahan", "1.334", "587,38", "46,00", "1.341,20"],
        ["Kedekatan pasangan bumbu", "11.938", "0,1518", "0,1139", "0,3800"],
        ["Ukuran geng rasa (komunitas)", "82", "16,27", "1,00", "100,60"],
    ]
    add_clean_table(
        s5,
        6.50,
        y0,
        6.26,
        3.65,
        ["Yang Diperiksa di Resep", "Jumlah", "Rata-rata", "Tengah", "Batas 95%"],
        eda_r_rows,
        [2.5, 0.9, 0.96, 0.9, 1.0],
        font_size=9.5,
        bold_cols={0},
        right_cols={1, 2, 3, 4},
    )
    add_note_box(
        s5,
        6.50,
        5.32,
        6.26,
        1.48,
        (
            "Rata-rata bahan di resep latih & ujian kembar (13,02 vs 13,06), artinya "
            "ujian nanti adil tanpa soal aneh (tak ada pergeseran distribusi). Selain itu, "
            "dominasi 50 bumbu inti membuat data harga 10 bahan BI berdampak besar ke dapur."
        ),
        title="Mengapa Ini Penting?",
        accent=RGB_GRN,
        font_size=10,
    )

    # =========================================================================
    # SLIDE 6: VALIDASI KUALITAS DATA
    # =========================================================================
    s6 = prs.slides.add_slide(blank_layout)
    y0 = add_header_footer(
        s6,
        "Unit 4 · J.62DMI00.006.1 · Memvalidasi Data",
        "Enam saringan mutu data: sidik jari berkas, libur, & lonjakan",
        6,
    )
    val_rows = [
        [
            "Sidik jari keutuhan file (SHA-256)",
            "379 berkas mentah · 0 berkas rusak/berubah",
            "VALID",
        ],
        [
            "Tanggal pasar buka vs libur",
            "804 hari kerja → 796 pasar buka (8 libur disaring)",
            "VALID",
        ],
        [
            "Kota yang datanya sering kosong",
            "Nas 10/10, Prov 340/340, Kota 1.049/1.099 (50 >20% dibuang)",
            "VALID",
        ],
        [
            "Catatan lonjakan 1 hari ekstrem",
            "|gerak| > 0,65: Nas 0, Prov 9, Kota 66 titik dicatat",
            "TERCATAT",
        ],
        [
            "Tes keamanan 2 pintu (ADF+KPSS)",
            "% Gerak harian lulus: Nas 90%, Prov 98,24%, Kota 98,00%",
            "VALID",
        ],
        [
            "Cek mata manusia pada teks resep",
            "271 / 300 baris sampel uji acak bersih sempurna (90,33%)",
            "VALID",
        ],
    ]

    def _val_color(_r: int, c: int, val: str) -> tuple[RGBColor, bool] | None:
        if c == 2:
            return (RGB_GRN if "VALID" in val else RGB_YEL_TXT, True)
        return None

    add_clean_table(
        s6,
        0.58,
        y0,
        6.82,
        5.35,
        ["Saringan Mutu Data", "Bukti Pemeriksaan Nyata", "Status"],
        val_rows,
        [2.25, 3.62, 0.95],
        font_size=9.5,
        bold_cols={0},
        cell_color_fn=_val_color,
    )
    add_code_panel(
        s6,
        7.60,
        y0,
        5.16,
        5.35,
        [
            (
                "src/dapur_domino/ingest/manifest.py · Cek Sidik Jari SHA-256",
                extract_function_snippet(
                    src / "ingest" / "manifest.py",
                    "verify_raw_manifest",
                    max_lines=8,
                    max_chars=62,
                    start_at="actual_size =",
                ),
            ),
            (
                "src/dapur_domino/cleaning/prices.py · Libur, Bolong, & Lonjakan",
                extract_function_snippet(
                    src / "cleaning" / "prices.py",
                    "clean_price_wide_panel",
                    max_lines=12,
                    max_chars=62,
                    skip_ranges=[
                        ("    series_audit = pd.DataFrame", "    )"),
                        ("    outlier_rows:", "    outlier_rows:"),
                        ("            index=retained_wide", "            columns=retained_wide"),
                    ],
                    start_at="date_missing_frac =",
                ),
            ),
            (
                ">>> OUTPUT NYATA (verify_raw_manifest & m1_summary.json)",
                [
                    "raw_manifest : 379/379 OK (0 mismatch, 0 missing)",
                    "market_days  : 804 -> 796 aktif (8 libur disaring)",
                    "city_series  : 1.099 -> 1.049 bersih (50 dibuang)",
                    "outliers_log : nas=0 | prov=9 | kota=66 titik",
                ],
            ),
        ],
        font_size=7.0,
    )

    # =========================================================================
    # SLIDE 7: VALIDASI ASUMSI STASIONERITAS GANDA (ADF + KPSS)
    # =========================================================================
    s7 = prs.slides.add_slide(blank_layout)
    y0 = add_header_footer(
        s7,
        "Unit 4 · J.62DMI00.006.1 · Memvalidasi Data",
        "Harga Rupiah mentah menipu model; % gerak harian aman dimodelkan",
        7,
    )
    s7.shapes.add_picture(str(charts["s7_stat"]), Inches(0.58), Inches(y0), width=Inches(5.85))
    add_note_box(
        s7,
        0.58,
        5.18,
        5.85,
        1.65,
        (
            "Dua harga yang sama-sama merangkak naik karena inflasi gampang dikira "
            "saling memengaruhi! Karena itu data wajib diubah menjadi % gerak harian "
            "(log-return) lalu lolos 2 pintu serentak (ADF & KPSS) — melompat dari "
            "0% menjadi 90% Nasional & 98%+ Daerah."
        ),
        title="Kenapa Rupiah Mentah Dilarang?",
        accent=RGB_GRN,
        font_size=10,
    )
    add_code_panel(
        s7,
        6.62,
        y0,
        6.14,
        5.42,
        [
            (
                "src/dapur_domino/prices/stationarity.py · Hitung % Gerak Harian",
                extract_function_snippet(
                    src / "prices" / "stationarity.py",
                    "compute_log_returns",
                    max_lines=8,
                    max_chars=70,
                    start_at="positive = wide_prices",
                ),
            ),
            (
                "src/dapur_domino/prices/stationarity.py · Pemeriksaan Keamanan 2 Pintu",
                extract_function_snippet(
                    src / "prices" / "stationarity.py",
                    "test_series_stationarity",
                    max_lines=13,
                    max_chars=70,
                    skip_ranges=[
                        ("    kpss_note:", "        warnings.simplefilter"),
                        ("        if caught:", "            kpss_note ="),
                    ],
                    start_at="adf_stat, adf_p",
                ),
            ),
            (
                ">>> OUTPUT NYATA (stationarity_national/province/city.csv)",
                [
                    "Harga Mentah  -> stationary_both: 0/10 Nasional (0,0%)",
                    "Gerak Harian  -> Nasional : 9/10 (90,0% · Gula KPSS=0,010)",
                    "Gerak Harian  -> Provinsi : 334/340 (98,24% lolos 2 pintu)",
                    "Gerak Harian  -> Kota     : 1.028/1.049 (98,00% lolos)",
                ],
            ),
        ],
        font_size=7.3,
    )

    # =========================================================================
    # SLIDE 8: PENENTUAN OBJEK DATA & PARTISI KRONOLOGIS
    # =========================================================================
    s8 = prs.slides.add_slide(blank_layout)
    y0 = add_header_footer(
        s8,
        "Unit 5 · J.62DMI00.007.1 · Menentukan Objek Data",
        "Memilih data harian tepat & menyegel 'amplop ujian' masa depan",
        8,
    )
    # Visual 3-stage chronological bar
    segments = [
        ("Belajar Awal [0:400] · 400 hari · Latih pola awal & musiman", 6.14, RGB_GRN),
        ("Simulasi [400:500] · 100 hr · Adu setelan", 1.54, RGB_YEL),
        ("Amplop Ujian Tersegel [500:796] · 296 hari · 1× Uji Akhir", 4.50, RGB_RED),
    ]
    cx = 0.58
    for txt_s, width_s, col_s in segments:
        blk = s8.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE,
            Inches(cx),
            Inches(y0),
            Inches(width_s - 0.06),
            Inches(0.68),
        )
        blk.adjustments[0] = 0.08
        blk.fill.solid()
        blk.fill.fore_color.rgb = col_s
        blk.line.fill.background()
        tf_b = blk.text_frame
        tf_b.word_wrap = True
        p_b = tf_b.paragraphs[0]
        p_b.alignment = PP_ALIGN.CENTER
        r_b = p_b.add_run()
        r_b.text = txt_s
        r_b.font.name = FONT_SANS
        r_b.font.size = Pt(9.5)
        r_b.font.bold = True
        r_b.font.color.rgb = RGB_WHITE
        cx += width_s

    sel_rows = [
        [
            "Harga Harian (PIHPS Bank Indonesia)",
            "Dipilih (Utama)",
            "1.141.526 baris",
            "Satu-satunya sumber resmi harian Pasar Tradisional di Nas, 34 Prov, & 105 Kota.",
        ],
        [
            "Indeks Bulanan (Open Data Bapanas)",
            "Pembanding Saja",
            "130 baris sampel",
            "Berbentuk bulanan, sehingga rambatan cepat 1–5 hari kerja tidak mungkin terlihat.",
        ],
        [
            "Seri Kota yang Bolong > 20%",
            "Dibuang (50/1.099)",
            "1.049 seri kota bersih",
            "Menambal kekosongan panjang menciptakan harga beku palsu yang menipu model.",
        ],
        [
            "Kumpulan Resep Nusantara",
            "Dipilih (Terpisah)",
            "66.419 Latih / 3.496 Uji",
            "Resep ujian disegel terpisah agar jaringan bumbu & Word2Vec tak pernah mencontek.",
        ],
        [
            "Batas Kosakata (>= 20 resep)",
            "Dipilih 1.334 bahan",
            "91,91% total pemakaian",
            "Menyapu salah ketik sekali pakai sambil mempertahankan >91% isi dapur & hemat RAM.",
        ],
    ]
    add_clean_table(
        s8,
        0.58,
        y0 + 0.88,
        12.18,
        4.45,
        ["Bahan Baku Data", "Keputusan", "Volume Dipakai", "Alasan Praktis"],
        sel_rows,
        [3.1, 1.9, 2.0, 5.18],
        font_size=9.5,
        bold_cols={0, 1},
    )

    # =========================================================================
    # SLIDE 9: PEMBERSIHAN DATA HARGA & NORMALISASI TEKS RESEP
    # =========================================================================
    s9 = prs.slides.add_slide(blank_layout)
    y0 = add_header_footer(
        s9,
        "Unit 6 · J.62DMI00.008.1 · Membersihkan Data",
        "Lima tahap merapikan data harga & catatan resep (90,33% bersih)",
        9,
    )
    cln_rows = [
        [
            "1. Ubah teks harga jadi angka",
            "Hapus koma '58,450' & arti '-'",
            "1,14 jt catatan harga bersih",
        ],
        [
            "2. Buang hari libur & ganda",
            "Tanggal pasar tutup (>=90% kosong)",
            "804 hari → 796 pasar buka",
        ],
        [
            "3. Tambal bolong pendek",
            "Buang kota >20%; tambal <= 3 hr",
            "1.049 kota bersih; 50 dibuang",
        ],
        [
            "4. Bersihkan kalimat resep",
            "Hapus angka, satuan (sdm, gr), kurung",
            "852.568 baris resep distandarkan",
        ],
        [
            "5. Pecah kembar & sinonim",
            "Pisah 'garam gula' + 236 singkatan",
            "1.334 bahan standar (90,33% lolos)",
        ],
    ]
    add_clean_table(
        s9,
        0.58,
        y0,
        6.52,
        3.95,
        ["Tahap Pembersihan", "Masalah Mentah & Aturan", "Hasil Setelah Dirapikan"],
        cln_rows,
        [2.0, 2.45, 2.07],
        font_size=9.4,
        bold_cols={0},
    )
    add_note_box(
        s9,
        0.58,
        5.56,
        6.52,
        1.25,
        (
            "Pemeriksaan langsung oleh mata manusia atas 300 baris acak dari resep uji "
            "mencatat 271/300 (90,33%) bersih sempurna; 29 baris sisa berasal dari bahasa "
            "tangan ekstrem ('sejempol', 'buang tulang daunnya') dan dicatat apa adanya."
        ),
        title="Bukti Cek Manual:",
        accent=RGB_YEL,
        font_size=9.8,
    )
    add_code_panel(
        s9,
        7.30,
        y0,
        5.46,
        5.40,
        [
            (
                "src/dapur_domino/ingest/pihps.py · Ubah '58,450' & '-' jadi Angka",
                extract_function_snippet(
                    src / "ingest" / "pihps.py",
                    "parse_pihps_price",
                    max_lines=6,
                    max_chars=64,
                    start_at="text = str(raw_val)",
                ),
            ),
            (
                "src/dapur_domino/cleaning/ingredients.py · Pisah 'garam gula' & Sinonim",
                extract_function_snippet(
                    src / "cleaning" / "ingredients.py",
                    "normalize_ingredient_line",
                    max_lines=4,
                    max_chars=64,
                    start_at="text = re.sub",
                ),
            ),
            (
                "src/dapur_domino/cleaning/ingredients.py · Hapus Satuan & 236 Sinonim",
                extract_function_snippet(
                    src / "cleaning" / "ingredients.py",
                    "_clean_single_fragment",
                    max_lines=7,
                    max_chars=64,
                    skip_ranges=[
                        ("    text = text.replace", "        return None"),
                        ("    while len(norm_tokens)", "        norm_tokens.pop(0)"),
                    ],
                    start_at="text = re.sub(rf\"\\b{_UNIT_PATTERN}",
                ),
            ),
            (
                ">>> OUTPUT NYATA (parse_pihps_price & vp1_eval_sample_300.csv)",
                [
                    "parse_pihps_price('58,450') -> 58450.0 | '-' -> None",
                    "'1/2 kol (3 ribu) (potong)' -> ['kubis']",
                    "'3 siung bawang putih iris' -> ['bawang putih']",
                    "cek_manual_300_baris        -> 271/300 = 90,33% bersih",
                ],
            ),
        ],
        font_size=7.0,
    )

    # =========================================================================
    # SLIDE 10: REKAYASA FITUR DERET WAKTU (KALENDER, FOURIER, LEBARAN)
    # =========================================================================
    s10 = prs.slides.add_slide(blank_layout)
    y0 = add_header_footer(
        s10,
        "Unit 7 · J.62DMI00.009.1 · Mengkonstruksi Data",
        "Mengupas bias Lebaran & hari raya tanpa mengintip masa depan",
        10,
    )
    add_note_box(
        s10,
        0.58,
        y0,
        4.75,
        1.15,
        (
            "Patokan(1), Hari(Sen–Kam), Gelombang Musim Tahunan "
            "(Fourier k=1,2), 14 hr Pra-Libur, 7 hr Pasca-Libur"
        ),
        title="11 Penanda Tanggal:",
        accent=RGB_RED,
        font_size=10.0,
    )
    add_stat_card(
        s10,
        0.58,
        y0 + 1.32,
        2.28,
        1.38,
        "11",
        "penanda hari, musim, & hari raya",
        accent=RGB_RED,
        val_size=28,
    )
    add_stat_card(
        s10,
        3.05,
        y0 + 1.32,
        2.28,
        1.38,
        "0%",
        "bocor ujian: belajar di [:500] saja",
        accent=RGB_GRN,
        val_size=28,
    )
    add_note_box(
        s10,
        0.58,
        y0 + 2.88,
        4.75,
        2.45,
        (
            "Ibarat es krim & orang berenang yang sama-sama naik saat panas terik: "
            "menjelang Lebaran, cabai & daging sapi naik serentak bukan karena saling "
            "memicu, melainkan karena gelombang belanja Hari Raya!\n\nBesarnya efek "
            "hari raya hanya dipelajari dari 500 hari awal sebelum disisihkan."
        ),
        title="Mengapa Bias Ini Dikupas?",
        accent=RGB_YEL,
        font_size=9.7,
    )
    add_code_panel(
        s10,
        5.55,
        y0,
        7.21,
        5.42,
        [
            (
                "src/dapur_domino/prices/seasonality.py · Bangun 11 Penanda Kalender",
                extract_function_snippet(
                    src / "prices" / "seasonality.py",
                    "build_calendar_design_matrix",
                    max_lines=13,
                    max_chars=74,
                    skip_ranges=[
                        ("        date_arr =", "            post_flag = np.maximum"),
                        ("                post_flag, ((date_arr", "            )"),
                    ],
                    start_at="dow = dates.dayofweek",
                ),
            ),
            (
                "src/dapur_domino/prices/seasonality.py · Ukur Bias di [:500] Lalu Kupas",
                extract_function_snippet(
                    src / "prices" / "seasonality.py",
                    "residualize_calendar_seasonality",
                    max_lines=10,
                    max_chars=74,
                    skip_ranges=[("        if int(valid.sum())", "            continue")],
                    start_at="x_train = x_all[:train_end_idx]",
                ),
            ),
            (
                ">>> OUTPUT NYATA (residualize_calendar_seasonality · 0% leakage)",
                [
                    "X_all.shape = (796, 11) | fit_only = X_all[:500] (500 hari awal)",
                    "test_window [500:796]   = 0% tersentuh saat menghitung koefisien beta",
                    "retensi_rantai_domino   = 50/50 (100% bertahan) + 6 rantai baru = 56",
                ],
            ),
        ],
        font_size=7.2,
    )

    # =========================================================================
    # SLIDE 11: ENAM KELOMPOK KONSTRUKSI FITUR
    # =========================================================================
    s11 = prs.slides.add_slide(blank_layout)
    y0 = add_header_footer(
        s11,
        "Unit 7 · J.62DMI00.009.1 · Mengkonstruksi Data",
        "Enam racikan fitur siap pakai untuk model harga, resep, & dompet",
        11,
    )
    fea_rows = [
        [
            "% Gerak harga harian",
            "Persen naik-turun dibanding kemarin · ln(Pt / Pt-1)",
            "796 × 1.399 seri",
            "Agar beras & daging sapi adil dibandingkan dalam % harian",
        ],
        [
            "Papan 11 penanda tanggal",
            "Sen–Kam, siklus panen tahunan, & H-14..H+7 Lebaran",
            "796 × 11 fitur",
            "Kebiasaan Lebaran hanya dipelajari di 500 hari awal (0% bocor)",
        ],
        [
            "Catatan 5 hari ke belakang",
            "Harga sendiri 1–5 hr lalu + pemicu 1–5 hr lalu",
            "1 + 5 + (5×pemicu)",
            "Menebak hari ini murni pakai catatan kemarin & sebelumnya",
        ],
        [
            "Ikatan erat pasangan bumbu",
            "Seberapa sering berduaan melebihi kebetulan (NPMI)",
            "1.334 bahan · 11.938 tali",
            "Dibangun hanya dari 66.419 resep latih (buta resep uji)",
        ],
        [
            "Peta koordinat makna bumbu",
            "64 angka posisi + penalti bila sering sepanci",
            "1.334 × 64 dimensi",
            "Mencari kembaran fungsi tanpa menyarankan garam ganti bawang",
        ],
        [
            "Skor ketenangan dompet",
            "Hukuman skor jika 30 hr naik / goyang · 0,6 rasa + 0,4 harga",
            "10 bahan BI × wilayah",
            "Bahan di luar pantauan BI tetap dibiarkan kosong jujur",
        ],
    ]
    add_clean_table(
        s11,
        0.58,
        y0,
        12.18,
        5.35,
        ["Kelompok Fitur", "Wujud & Cara Kerja Sederhana", "Ukuran", "Tujuan & Kunci Anti-Bocor"],
        fea_rows,
        [2.35, 3.65, 1.85, 4.33],
        font_size=9.8,
        bold_cols={0},
    )

    # =========================================================================
    # SLIDE 12: EKSPERIMEN 8 SKENARIO MODEL DERET WAKTU (VAL [400:500])
    # =========================================================================
    s12 = prs.slides.add_slide(blank_layout)
    y0 = add_header_footer(
        s12,
        "Unit 8 · J.62DMI00.012.1 · Membangun Skenario Model",
        "Adu 8 setelan di simulasi [400:500]: rem Ridge selamatkan model",
        12,
        subtitle=(
            "Amplop ujian [500:796] tetap disegel saat memilih panjang riwayat "
            "(1–5 hari) dan kekuatan rem penahan hafalan (α)."
        ),
    )
    s12.shapes.add_picture(str(charts["s12_scen"]), Inches(0.58), Inches(y0), width=Inches(6.05))
    add_note_box(
        s12,
        0.58,
        5.32,
        6.05,
        1.52,
        (
            "1) Lihat 1 hari ke belakang terlalu singkat (kalah −1,26% vs AR).\n"
            "2) Lihat 5 hari nyaris tanpa rem (α=0,001) bertingkah seperti murid penghafal "
            "soal: OVERFITTING parah (−6,64% vs Naive)!\n"
            "3) Jeda 5 hari + rem α=1,0 + Bebas Musim (Dipilih) unggul di kedua baseline "
            "(+4,16% & +1,59%)."
        ),
        title="Pelajaran Simulasi:",
        accent=RGB_RED,
        font_size=9.4,
    )
    add_code_panel(
        s12,
        6.82,
        y0,
        5.94,
        5.42,
        [
            (
                "src/dapur_domino/evaluation/lifecycle.py · Adu 8 Skenario [400:500]",
                extract_function_snippet(
                    src / "evaluation" / "lifecycle.py",
                    "evaluate_timeseries_modeling_scenarios",
                    max_lines=13,
                    max_chars=66,
                    start_at="for scen_id, label",
                ),
            ),
            (
                "src/dapur_domino/evaluation/walk_forward.py · Susun Kolom Riwayat 5 Hari",
                extract_function_snippet(
                    src / "evaluation" / "walk_forward.py",
                    "evaluate_walk_forward_domino",
                    max_lines=8,
                    max_chars=66,
                    start_at="y_all = y_series[lag:]",
                ),
            ),
            (
                ">>> OUTPUT NYATA (scenarios_timeseries_val.csv · jendela [400:500])",
                [
                    "S01 lag=1 a=1.0 raw : vs AR=-1,26% | vs Naive=-4,20%",
                    "S03 lag=5 a=0.001   : vs AR=+1,06% | vs Naive=-6,64% [OVERFIT]",
                    "S08 lag=5 a=1.0 adj : vs AR=+4,16% | vs Naive=+1,59% [DIPILIH]",
                ],
            ),
        ],
        font_size=7.2,
    )

    # =========================================================================
    # SLIDE 13: ADU 4 MODEL PELENGKAP + SENSITIVITAS BOBOT JEMBATAN
    # =========================================================================
    s13 = prs.slides.add_slide(blank_layout)
    y0 = add_header_footer(
        s13,
        "Unit 8 · J.62DMI00.012.1 · Membangun Skenario Model",
        "Memilih otak terbaik isi kulkas & uji bobot rasa vs harga",
        13,
    )
    vp2_rows = [
        ["Cocok Bersyarat · Cond. PMI (Dipilih)", "45,50%", "[43,85%, 47,17%]", "56,29%"],
        ["Tebak Terpopuler Saja (Baseline)", "40,88%", "[39,25%, 42,53%]", "54,58%"],
        ["Pasangan Murni (NPMI tanpa prior)", "23,82%", "[22,43%, 25,27%]", "32,32%"],
        ["AI Pengganti (Word2Vec konteks)", "7,63%", "[6,79%, 8,56%]", "11,01%"],
    ]
    add_clean_table(
        s13,
        0.58,
        y0,
        6.20,
        2.95,
        ["Model Tebak Bumbu Hilang (3.459 resep)", "Top-5", "Rentang 95%", "Top-10"],
        vp2_rows,
        [2.85, 0.90, 1.55, 0.90],
        font_size=9.5,
        bold_cols={0, 1},
        right_cols={1, 3},
    )
    add_note_box(
        s13,
        0.58,
        4.60,
        6.20,
        2.15,
        (
            "Mengapa Word2Vec kalah jauh untuk 'Isi Kulkasku' (ibarat lemari baju)?\n"
            "• Cond. PMI mencari bumbu yang dipakai BERSAMA di 1 panci (Kemeja + Celana) "
            "berdasar 66.419 resep.\n"
            "• Word2Vec mencari bahan PENGGANTI seposisi yang justru jarang bertemu sepanci "
            "(Kemeja ↔ Kaus) — pasnya dipakai untuk 'Ganti Bahan'!"
        ),
        title="Beda Teman vs Pengganti:",
        accent=RGB_GRN,
        font_size=9.7,
    )

    bw_rows = [
        ["100% Resep : 0% Harga", "5 / 14", "0,8248", "0,9378", "0,8777"],
        ["80% Resep : 20% Harga", "5 / 14", "0,8248", "0,9378", "0,8777"],
        ["60% Resep : 40% Harga (Dipilih)", "5 / 14", "0,8248", "0,9378", "0,8777"],
        ["50% Resep : 50% Harga", "5 / 14", "0,8248", "0,9378", "0,8777"],
        ["30% Resep : 70% Harga", "5 / 14", "0,8248", "0,9378", "0,8777"],
    ]
    add_clean_table(
        s13,
        7.00,
        y0,
        5.76,
        3.25,
        ["Uji Geser Bobot Jembatan", "Tercakup", "Skor Rasa", "Harga", "Seimbang"],
        bw_rows,
        [2.30, 0.85, 0.85, 0.88, 0.88],
        font_size=9.3,
        bold_cols={0},
        right_cols={1, 2, 3, 4},
    )
    add_note_box(
        s13,
        7.00,
        4.90,
        5.76,
        1.85,
        (
            "Dari 14 bahan berpeta BI, baru 5 bahan yang punya kandidat pengganti berpeta BI "
            "pula. Karena itu menggeser bobot tak membuat peringkat goyah (stabil 0,8777) — "
            "pembatas utamanya ialah jumlah 10 komoditas BI. Bobot 60% rasa : 40% harga dipilih."
        ),
        title="Kenapa Nilainya Tetap Sama?",
        accent=RGB_YEL,
        font_size=9.7,
    )

    # =========================================================================
    # SLIDE 14: JARINGAN DOMINO GRANGER + FDR + PERMUTASI ANTI-KEBETULAN
    # =========================================================================
    s14 = prs.slides.add_slide(blank_layout)
    y0 = add_header_footer(
        s14,
        "Unit 9 · J.62DMI00.013.1 · Membangun Model",
        "Melacak efek domino & membuktikan sinyalnya bukan kebetulan",
        14,
    )
    add_stat_card(
        s14,
        0.58,
        y0,
        1.95,
        1.15,
        "50 / 90",
        "rantai kuat (gerak mentah)",
        accent=RGB_RED,
        val_size=22,
    )
    add_stat_card(
        s14, 2.66, y0, 1.95, 1.15, "56 / 90", "bertahan pasca-Lebaran", accent=RGB_YEL, val_size=22
    )
    add_stat_card(
        s14, 4.74, y0, 2.00, 1.15, "3,44%", "sinyal hoki saat dikocok", accent=RGB_GRN, val_size=22
    )

    edges_top = (
        data["edges_raw"].loc[data["edges_raw"]["significant"]].sort_values("q_value").head(6)
    )
    e_rows = [
        [
            f"{r['source_name']} → {r['target_name']}",
            f"{int(r['best_xcorr_lag'])} hr",
            fmt_id_dec(float(r["f_stat"]), 2),
            f"{float(r['q_value']):.1e}",
        ]
        for _, r in edges_top.iterrows()
    ]
    add_clean_table(
        s14,
        0.58,
        y0 + 1.32,
        6.16,
        2.95,
        ["Pemicu Awal → Terdampak (500 hari awal)", "Jeda", "Kuat (F)", "Lolos q"],
        e_rows,
        [3.35, 0.80, 0.90, 1.11],
        font_size=9.3,
        bold_cols={0},
        right_cols={1, 2, 3},
    )
    add_note_box(
        s14,
        0.58,
        5.86,
        6.16,
        1.00,
        (
            "Semua 50 rantai awal (100%) tetap bertahan walau bias Lebaran dibersihkan. "
            "Saat tanggal dikocok melingkar 20× (np.roll) untuk membunuh sinyal asli, "
            "yang lolos kebetulan anjlok jadi hanya 3,1/90 (3,44% <= 5%)."
        ),
        title="Bukti Bukan Hoki:",
        accent=RGB_GRN,
        font_size=9.5,
    )
    add_code_panel(
        s14,
        6.94,
        y0,
        5.82,
        5.42,
        [
            (
                "src/dapur_domino/prices/domino.py · Adu Penebak Tertutup vs Terbuka",
                extract_function_snippet(
                    src / "prices" / "domino.py",
                    "granger_ftest",
                    max_lines=9,
                    max_chars=66,
                    start_at="beta_r, *_",
                ),
            ),
            (
                "src/dapur_domino/prices/domino.py · Saringan Kebetulan (FDR) & Kocok 20×",
                extract_function_snippet(
                    src / "prices" / "domino.py",
                    "benjamini_hochberg_fdr",
                    max_lines=7,
                    max_chars=66,
                    start_at="order = np.argsort",
                ),
            ),
            (
                "src/dapur_domino/prices/domino.py · Uji Kocok Kalender 20× (np.roll)",
                extract_function_snippet(
                    src / "prices" / "domino.py",
                    "run_circular_shift_permutation_control",
                    max_lines=6,
                    max_chars=66,
                    start_at="shift = int(rng.integers",
                ),
            ),
            (
                ">>> OUTPUT NYATA (m2_summary.json · 500 hari awal)",
                [
                    "raw_sig=50/90 | seasonal_adj=56/90 (100% bertahan)",
                    "top_edge: Minyak Goreng -> Daging Ayam (F=9,79, q=5.3e-07)",
                    "20x np.roll false_edges: 3,1/90 = 3,44% (<= batas 5%)",
                ],
            ),
        ],
        font_size=6.9,
    )

    # =========================================================================
    # SLIDE 15: SPASIAL 34 PROVINSI / 105 KOTA + LEBARAN 2026
    # =========================================================================
    s15 = prs.slides.add_slide(blank_layout)
    y0 = add_header_footer(
        s15,
        "Unit 9 · J.62DMI00.013.1 · Membangun Model",
        "Kota Solo jadi barometer cabai nasional; cabai melonjak Lebaran",
        15,
    )
    prov_rows = [
        [
            str(r["commodity_name"]),
            str(r["top_leader_province"]),
            f"{int(r['top_leader_out_degree'])} / 33",
        ]
        for _, r in data["prov_sum"]
        .sort_values("top_leader_out_degree", ascending=False)
        .head(6)
        .iterrows()
    ]
    add_clean_table(
        s15,
        0.58,
        y0,
        5.85,
        2.85,
        ["Bahan Pokok", "Provinsi Pemimpin (34 Prov)", "Mendahului"],
        prov_rows,
        [2.0, 2.4, 1.45],
        font_size=9.5,
        bold_cols={0, 1},
        right_cols={2},
    )
    city_rows = [
        [
            str(r["commodity_name"]),
            str(r["top_leader_city"]),
            f"{int(r['top_leader_out_degree'])} / 104",
        ]
        for _, r in data["city_sum"].iterrows()
    ]
    add_clean_table(
        s15,
        0.58,
        y0 + 3.05,
        5.85,
        1.75,
        ["Bahan Pokok", "Kota/Kab Pemimpin (105 Kota)", "Mendahului"],
        city_rows,
        [2.0, 2.4, 1.45],
        font_size=9.5,
        bold_cols={0, 1},
        right_cols={2},
    )
    add_note_box(
        s15,
        0.58,
        6.18,
        5.85,
        0.72,
        (
            "Kota Surakarta (Solo) menjadi pasar barometer utama Cabai Merah "
            "(77 kota) & Cabai Rawit (75 kota) sebagai simpul distribusi Jawa."
        ),
        title="Peta Regional:",
        accent=RGB_YEL,
        font_size=9.5,
    )
    s15.shapes.add_picture(str(charts["s15_eid"]), Inches(6.65), Inches(y0), width=Inches(6.10))

    # =========================================================================
    # SLIDE 16: GRAF LOUVAIN (82 KOMUNITAS) & SKIP-GRAM WORD2VEC
    # =========================================================================
    s16 = prs.slides.add_slide(blank_layout)
    y0 = add_header_footer(
        s16,
        "Unit 9 · J.62DMI00.013.1 · Membangun Model",
        "Membentuk 82 geng rasa masakan & AI pemeta makna bahan",
        16,
    )
    add_stat_card(
        s16, 0.58, y0, 2.22, 1.32, "1.334", "bahan masakan standar", accent=RGB_RED, val_size=26
    )
    add_stat_card(
        s16,
        2.94,
        y0,
        2.22,
        1.32,
        "11.938",
        "tali pasangan erat bumbu",
        accent=RGB_YEL,
        val_size=26,
    )
    add_stat_card(
        s16,
        0.58,
        y0 + 1.46,
        2.22,
        1.32,
        "82",
        "geng rasa alami (Louvain)",
        accent=RGB_GRN,
        val_size=26,
    )
    add_stat_card(
        s16,
        2.94,
        y0 + 1.46,
        2.22,
        1.32,
        "64",
        "angka koordinat makna bahan",
        accent=RGB_RED,
        val_size=26,
    )
    add_note_box(
        s16,
        0.58,
        y0 + 2.96,
        4.58,
        2.35,
        (
            "Dilatih murni di 66.419 resep latih (seed=42, workers=1) tanpa "
            "menyentuh resep ujian:\n"
            "1) Louvain otomatis mengelompokkan bumbu sambal, gulai, tumis, & kue "
            "menjadi 82 geng rasa.\n"
            "2) Word2Vec memberi tiap bahan 64 koordinat posisi berdasar bumbu "
            "tetangganya untuk mencari pengganti seprofesi."
        ),
        title="Dua Otak Kuliner:",
        accent=RGB_GRN,
        font_size=9.7,
    )
    add_code_panel(
        s16,
        5.36,
        y0,
        7.40,
        5.42,
        [
            (
                "src/dapur_domino/recipes/network.py · Hitung Kedekatan Pasangan Bumbu (NPMI)",
                extract_function_snippet(
                    src / "recipes" / "network.py",
                    "build_ingredient_cooccurrence_graph",
                    max_lines=8,
                    max_chars=76,
                    start_at="p_a = item_counts[a]",
                ),
            ),
            (
                "src/dapur_domino/recipes/network.py · Kelompokkan Otomatis ke 82 Geng Rasa",
                extract_function_snippet(
                    src / "recipes" / "network.py",
                    "build_ingredient_cooccurrence_graph",
                    max_lines=5,
                    max_chars=76,
                    start_at="partition: dict",
                ),
            ),
            (
                "src/dapur_domino/recipes/embedding.py · Latih AI Makna Bahan Word2Vec",
                extract_function_snippet(
                    src / "recipes" / "embedding.py",
                    "train_ingredient_embeddings",
                    max_lines=9,
                    max_chars=76,
                    skip_markers=("    if not sentences:", "        raise ValueError"),
                    start_at="sentences = [sorted",
                ),
            ),
            (
                ">>> OUTPUT NYATA (m3_summary.json · 66.419 resep latih, seed=42)",
                [
                    "graph: 1.334 bahan standar | 11.938 tali NPMI (>=0,05) | 82 geng Louvain",
                    "w2v  : vocab=1.334 x 64 dimensi | sg=1 | workers=1 | RAM=313,6 MB",
                ],
            ),
        ],
        font_size=7.2,
    )

    # =========================================================================
    # SLIDE 17: REGISTRI 8 MODEL & PROFIL EFISIENSI RAM
    # =========================================================================
    s17 = prs.slides.add_slide(blank_layout)
    y0 = add_header_footer(
        s17,
        "Unit 9 · J.62DMI00.013.1 · Membangun Model",
        "Delapan komponen model lokal: rapi tercatat & enteng di RAM 8 GB",
        17,
        subtitle=(
            "Seluruh alur (seed=42) diukur nyata di laptop standar — selesai ~2,6 menit "
            "dan tidak sampai 10% kapasitas RAM 8.192 MB."
        ),
    )
    reg_labels: dict[str, tuple[str, str]] = {
        "Panel Log-Return & Dual Stationarity Screener (ADF + KPSS)": (
            "1. Mesin % Gerak & Cek 2 Pintu",
            "Ubah Rupiah ke gerak harian & cek aman (ADF+KPSS)",
        ),
        "Calendar-Fourier-Holiday OLS Seasonal Residualizer": (
            "2. Pengupas Efek Hari & Lebaran",
            "Sisihkan efek hari kerja, musim, & H-14..H+7 Lebaran",
        ),
        "Directed Granger Causality Network + Benjamini-Hochberg FDR": (
            "3. Pencari Efek Domino Berantai",
            "Uji 90 pasangan + saring hoki FDR + 20× kocok kalender",
        ),
        "Expanding-Window Domino ARX(5) Ridge Forecaster": (
            "4. Peramal Berjalan Ridge ARX(5)",
            "Regresi ber-rem Ridge belajar ulang tiap pagi hari",
        ),
        "NPMI Co-occurrence Graph & Louvain Flavor Community Detector": (
            "5. Peta Bumbu & 82 Geng Rasa",
            "Graf kedekatan bumbu (NPMI) & pengelompokan Louvain",
        ),
        "Conditional Co-occurrence PMI Complement Recommender": (
            "6. Penebak Pelengkap Isi Kulkas",
            "Skor kelaziman + kecocokan bersyarat sepanci (Cond. PMI)",
        ),
        "Skip-Gram Word2Vec + Complement-Penalized Substitution Scorer": (
            "7. AI Pemeta Makna Bahan + Penalti",
            "Word2Vec 64 angka posisi + penalti teman sepanci",
        ),
        "Price-Aware Hybrid Substitution Scorer": (
            "8. Jembatan Skor Sadar-Harga",
            "60% cocok resep + 40% harga tenang 30 hari resmi BI",
        ),
    }
    reg_rows = []
    for _, r in data["registry"].iterrows():
        raw_name = str(r["model_name"])
        raw_fam = str(r["algorithm_family"])
        disp_name, disp_fam = reg_labels.get(raw_name, (raw_name, raw_fam))
        reg_rows.append(
            [
                disp_name,
                disp_fam,
                str(r["key_hyperparameters"]),
                fmt_id_dec(float(r["duration_sec"]), 2),
                fmt_id_dec(float(r["peak_ram_mb"]), 1),
            ]
        )
    add_clean_table(
        s17,
        0.58,
        y0,
        12.18,
        5.25,
        [
            "Komponen Model",
            "Cara Kerja / Pendekatan",
            "Setelan Utama Terkunci",
            "Durasi (dtk)",
            "Puncak RAM (MB)",
        ],
        reg_rows,
        [3.2, 2.8, 4.18, 0.95, 1.05],
        font_size=9.2,
        bold_cols={0},
        right_cols={3, 4},
    )

    # =========================================================================
    # SLIDE 18: EVALUASI WALK-FORWARD OUT-OF-SAMPLE (296 HARI UJI)
    # =========================================================================
    s18 = prs.slides.add_slide(blank_layout)
    y0 = add_header_footer(
        s18,
        "Unit 10 · J.62DMI00.014.1 · Mengevaluasi Hasil Pemodelan",
        "Ujian maraton 296 hari baru: menang di minyak–sapi–beras, kalah di cabai",
        18,
    )
    s18.shapes.add_picture(str(charts["s18_wf"]), Inches(0.58), Inches(y0), width=Inches(6.25))
    add_note_box(
        s18,
        0.58,
        5.68,
        6.25,
        1.20,
        (
            "Minyak Goreng (+13,47% Raw DM p=0,0022; +14,79% vs AR5 Musiman), Daging Sapi "
            "(+12,32% Raw / +10,00% Musiman), & Beras (+6,62% Musiman, p=0,0173) lolos VP6. "
            "Sebaliknya Cabai & Bawang lebih akurat memakai AR(5) akibat hujan & panen lokal."
        ),
        title="Vonis Jujur 296 Hari Ujian:",
        accent=RGB_RED,
        font_size=9.6,
    )
    add_code_panel(
        s18,
        7.05,
        y0,
        5.71,
        5.42,
        [
            (
                "src/dapur_domino/evaluation/walk_forward.py · Regresi Ber-rem Ridge",
                extract_function_snippet(
                    src / "evaluation" / "walk_forward.py",
                    "_fit_ridge",
                    max_lines=7,
                    max_chars=66,
                ),
            ),
            (
                "src/dapur_domino/evaluation/walk_forward.py · Latih Ulang Tiap Pagi",
                extract_function_snippet(
                    src / "evaluation" / "walk_forward.py",
                    "evaluate_walk_forward_domino",
                    max_lines=7,
                    max_chars=66,
                    start_at="beta_ar = _fit_ridge",
                ),
            ),
            (
                "src/dapur_domino/evaluation/walk_forward.py · Wasit Pembanding (DM Test)",
                extract_function_snippet(
                    src / "evaluation" / "walk_forward.py",
                    "diebold_mariano_test",
                    max_lines=8,
                    max_chars=66,
                    skip_markers=("    if var_d <= 1e-24:", "        return 0.0, 1.0"),
                    start_at="d = (errors_model**2)",
                ),
            ),
            (
                ">>> OUTPUT NYATA (walk_forward_raw & seasonal_adj · 296 hari uji)",
                [
                    "Minyak Goreng : +13,47% Raw (DM p=0,0022 LULUS) | +14,79% Musiman",
                    "Daging Sapi   : +10,00% Musiman / +12,32% Raw | Beras +6,62% (p=0,0173)",
                    "Cabai Rawit   :  -6,96% | Bawang Merah -7,84% [MUNDUR AR5]",
                ],
            ),
        ],
        font_size=7.0,
    )

    # =========================================================================
    # SLIDE 19: EVALUASI PELENGKAP (CI 95%) & SUBSTITUSI (RECALL, MRR, NDCG)
    # =========================================================================
    s19 = prs.slides.add_slide(blank_layout)
    y0 = add_header_footer(
        s19,
        "Unit 10 · J.62DMI00.014.1 · Mengevaluasi Hasil Pemodelan",
        "Rapor jalur kuliner: isi kulkas menang sah; pengganti 24% & siap dibedah",
        19,
    )
    add_clean_table(
        s19,
        0.58,
        y0,
        5.60,
        2.55,
        ["Metode Tebak Bumbu Hilang (3.459)", "Top-5", "Rentang 95%", "Top-10"],
        vp2_rows,
        [2.50, 0.85, 1.40, 0.85],
        font_size=9.2,
        bold_cols={0, 1},
        right_cols={1, 3},
    )
    add_stat_card(
        s19,
        0.58,
        y0 + 2.74,
        1.78,
        1.32,
        "24,0%",
        "Tepat di 5 Besar (6 dari 25 soal)",
        accent=RGB_RED,
        val_size=24,
    )
    add_stat_card(
        s19,
        2.48,
        y0 + 2.74,
        1.78,
        1.32,
        "0,2100",
        "Poin posisi juara (MRR @10)",
        accent=RGB_YEL,
        val_size=24,
    )
    add_stat_card(
        s19,
        4.38,
        y0 + 2.74,
        1.80,
        1.32,
        "9,37%",
        "Kualitas urutan Top-5 (NDCG)",
        accent=RGB_GRN,
        val_size=24,
    )
    add_note_box(
        s19,
        0.58,
        5.55,
        5.60,
        1.25,
        (
            "Untuk isi kulkas, Conditional PMI (45,50%, rentang [43,85%–47,17%]) unggul "
            "telak tanpa bersentuhan dengan tebakan terpopuler [39,25%–42,53%]. "
            "Sedangkan skor pengganti 24,0% dibedah satu per satu di slide berikut."
        ),
        title="Makna Angka Rapor:",
        accent=RGB_YEL,
        font_size=9.6,
    )
    add_code_panel(
        s19,
        6.38,
        y0,
        6.38,
        5.42,
        [
            (
                "src/dapur_domino/recipes/network.py · Skor Isi Kulkasku (Cond. PMI)",
                extract_function_snippet(
                    src / "recipes" / "network.py",
                    "recommend_complements_conditional",
                    max_lines=7,
                    max_chars=70,
                    skip_ranges=[
                        ("        matches:", "        matches:"),
                        ("            matches.append", "            continue"),
                    ],
                    start_at="log_prior = ",
                ),
            ),
            (
                "src/dapur_domino/evaluation/lifecycle.py · Hitung Poin Peringkat MRR & NDCG",
                extract_function_snippet(
                    src / "evaluation" / "lifecycle.py",
                    "evaluate_vp3_ranking_and_error_taxonomy",
                    max_lines=9,
                    max_chars=70,
                    skip_ranges=[
                        ("        rr_list.append", "        rr_list.append"),
                        ("            k: int,", "        ) -> float:"),
                    ],
                    start_at="rr = 1.0 /",
                ),
            ),
            (
                "src/dapur_domino/evaluation/recipe_eval.py · Margin Kepastian (Wilson 95%)",
                extract_function_snippet(
                    src / "evaluation" / "recipe_eval.py",
                    "wilson_confidence_interval",
                    max_lines=6,
                    max_chars=70,
                    start_at="p = successes",
                ),
            ),
            (
                ">>> OUTPUT NYATA (m3_summary.json & vp3_error_taxonomy.csv)",
                [
                    "Isi Kulkas (n=3.459): Cond.PMI=45,50% [43,85–47,17%] vs Pop=40,88%",
                    "Pengganti  (n=25)   : Recall@5=24,0% (6/25) | MRR=0,2100 | NDCG=9,37%",
                ],
            ),
        ],
        font_size=6.8,
    )

    # =========================================================================
    # SLIDE 20: TAKSONOMI ERROR SUBSTITUSI & PARETO CAKUPAN
    # =========================================================================
    s20 = prs.slides.add_slide(blank_layout)
    y0 = add_header_footer(
        s20,
        "Unit 10 · J.62DMI00.014.1 · Mengevaluasi Hasil Pemodelan",
        "Autopsi 19 tebakan meleset: beda tulisan, bukan AI ngawur",
        20,
    )
    s20.shapes.add_picture(str(charts["s20_err"]), Inches(0.58), Inches(y0), width=Inches(5.85))

    err_rows = [
        ["bawang bombay", "cuka putih, kaldu daging, jamur shiitake", "Tetangga Tumis Serumpun"],
        ["bawang merah", "ajinomoto, bawang merah bawang putih, di", "Varian + Kata Sisa ('di')"],
        ["kemiri", "miri, lombok keriting, kunci", "Singkatan Daerah ('miri')"],
        ["santan", "santan dari kelapa, sun, santan dr kelapa", "Varian Bahan Sama"],
        ["gula merah", "blok gula merah, bulatan gula merah", "Varian Bahan Sama"],
        ["gula pasir", "kaldu bubuk non msg, gula penyedap", "Tetangga Resep Serumpun"],
    ]
    add_clean_table(
        s20,
        0.58,
        y0 + 2.68,
        6.60,
        2.72,
        ["Bahan Target", "3 Tebakan Teratas AI (Word2Vec)", "Akar Masalahnya"],
        err_rows,
        [1.45, 3.35, 1.80],
        font_size=8.8,
        bold_cols={0},
    )
    add_stat_card(
        s20,
        7.42,
        y0,
        2.55,
        1.48,
        "1,05%",
        "jumlah kata bahan berpeta BI (14/1.334)",
        accent=RGB_YEL,
        val_size=28,
    )
    add_stat_card(
        s20,
        10.16,
        y0,
        2.60,
        1.48,
        "27,74%",
        "total pemakaian dapur tercakup (217.380)",
        accent=RGB_GRN,
        val_size=28,
    )
    add_note_box(
        s20,
        7.42,
        y0 + 1.68,
        5.34,
        3.72,
        (
            "Hasil Autopsi 19 Tebakan Gagal:\n"
            "1) AI-nya sehat — 10 dari 19 tebakan gagal justru menyebut variasi bentuk/merek "
            "benda yang sama ('santan dari kelapa', 'blok gula merah') plus dialek Jawa "
            "('miri' = kemiri) yang belum digabung.\n"
            "2) Kata pendek seperti 'di' & merek 'ajinomoto' masih lolos pembersih teks.\n\n"
            "Dampak Besar di Dapur:\n"
            "Berkat pola Zipf, cuma 14 bahan terhubung BI langsung mencakup lebih dari "
            "seperempat (27,74%) aktivitas memasak di 66.419 resep!"
        ),
        title="Temuan Ilmuwan Data:",
        accent=RGB_RED,
        font_size=9.6,
    )

    # =========================================================================
    # SLIDE 21: SKORING HIBRIDA SADAR-HARGA & KEJUJURAN UNMAPPED
    # =========================================================================
    s21 = prs.slides.add_slide(blank_layout)
    y0 = add_header_footer(
        s21,
        "Unit 10 · J.62DMI00.014.1 · Mengevaluasi Hasil Pemodelan",
        "Mengawinkan rasa masakan & kestabilan harga tanpa mengarang rupiah",
        21,
    )
    add_note_box(
        s21,
        0.58,
        y0,
        6.25,
        0.88,
        (
            "Harga Tenang = skor terpotong bila 30 hr naik / goyang liar   |   "
            "Skor Akhir = 60% Cocok Resep + 40% Harga Tenang"
        ),
        title="Cara Penilaian:",
        accent=RGB_RED,
        font_size=9.5,
    )
    br_rows = []
    for _, r in data["bridge_eval"].iterrows():
        st_raw = str(r["top_price_status"])
        st_id = "Dipantau BI" if st_raw == "mapped" else "Tanpa data BI"
        sc_txt = (
            fmt_id_dec(float(r["top_combined_score"]), 4)
            if pd.notna(r["top_combined_score"])
            else "— (hanya resep)"
        )
        br_rows.append([str(r["target_ingredient"]), str(r["top_candidate"]), st_id, sc_txt])

    def _br_color(_r: int, c: int, val: str) -> tuple[RGBColor, bool] | None:
        if c == 2:
            return (RGB_GRN if "Dipantau" in val else RGB_RED, True)
        return None

    add_clean_table(
        s21,
        0.58,
        y0 + 1.02,
        6.25,
        4.35,
        ["Bahan Target", "Kandidat Teratas", "Status Harga BI", "Skor Gabungan"],
        br_rows,
        [1.55, 1.95, 1.35, 1.40],
        font_size=8.8,
        bold_cols={0},
        right_cols={3},
        cell_color_fn=_br_color,
    )
    add_code_panel(
        s21,
        7.05,
        y0,
        5.71,
        5.40,
        [
            (
                "src/dapur_domino/bridge/scoring.py · Cek Naik & Goyangan 30 Hari",
                extract_function_snippet(
                    src / "bridge" / "scoring.py",
                    "compute_commodity_price_metrics",
                    max_lines=6,
                    max_chars=64,
                    start_at="latest_px = float",
                ),
            ),
            (
                "src/dapur_domino/bridge/scoring.py · Gabung Skor & Jujur Saat Kosong",
                extract_function_snippet(
                    src / "bridge" / "scoring.py",
                    "score_price_aware_substitutions",
                    max_lines=15,
                    max_chars=64,
                    skip_ranges=[
                        (
                            '                    "target_ingredient":',
                            '                    "direct_npmi":',
                        ),
                        (
                            '                    "comcat_id":',
                            '                    "volatility_30d":',
                        ),
                    ],
                    start_at="sim_score = float",
                ),
            ),
            (
                ">>> OUTPUT NYATA (bridge_eval_summary.csv · 18 Nov 2026)",
                [
                    "cabai rawit -> cabai rawit merah [mapped]   score=0,8707",
                    "cabai merah keriting -> cabai merah [mapped] score=0,8284",
                    "santan -> santan dari kelapa    [unmapped]  score=None",
                ],
            ),
        ],
        font_size=7.1,
    )

    # =========================================================================
    # SLIDE 22: MATRIKS KEPUTUSAN PRODUKSI PER KOMODITAS (GO / NO-GO)
    # =========================================================================
    s22 = prs.slides.add_slide(blank_layout)
    y0 = add_header_footer(
        s22,
        "Unit 11 · J.62DMI00.015.1 · Melakukan Proses Review Pemodelan",
        "Keputusan rilis produksi per bahan: kapan Domino, kapan mundur",
        22,
    )
    rev_rows = []
    for _, r in data["rev_dec"].iterrows():
        dec = str(r["review_decision"])
        if "DEPLOY" in dec:
            dec_short = "Pakai Domino ARX(5)"
        elif "AR5" in dec:
            dec_short = "Mundur ke AR(5)"
        else:
            dec_short = "Mundur ke Naive"
        raw_v = float(r["skill_vs_ar_raw_pct"])
        seas_v = float(r["skill_vs_ar_seasonal_pct"])
        rev_rows.append(
            [
                str(r["commodity_name"]),
                f"{'+' if raw_v > 0 else ''}{fmt_id_dec(raw_v, 2)}%",
                f"{'+' if seas_v > 0 else ''}{fmt_id_dec(seas_v, 2)}%",
                dec_short,
            ]
        )

    def _rev_color(_r: int, c: int, val: str) -> tuple[RGBColor, bool] | None:
        if c == 3:
            if "Pakai Domino" in val:
                return (RGB_GRN, True)
            if "AR(5)" in val:
                return (RGB_YEL_TXT, True)
            return (RGB_RED, True)
        return None

    add_clean_table(
        s22,
        0.58,
        y0,
        5.85,
        3.95,
        ["Bahan Pokok", "Mentah", "Bebas Musim", "Keputusan Rilis"],
        rev_rows,
        [1.75, 1.15, 1.15, 1.80],
        font_size=9.2,
        bold_cols={0},
        right_cols={1, 2},
        cell_color_fn=_rev_color,
    )
    add_stat_card(
        s22, 0.58, 5.45, 1.85, 1.32, "3 / 10", "Pakai Domino ARX(5)", accent=RGB_GRN, val_size=23
    )
    add_stat_card(
        s22,
        2.58,
        5.45,
        1.85,
        1.32,
        "5 / 10",
        "Mundur ke Riwayat (AR5)",
        accent=RGB_YEL,
        val_size=23,
    )
    add_stat_card(
        s22, 4.58, 5.45, 1.85, 1.32, "2 / 10", "Mundur Harga Kemarin", accent=RGB_RED, val_size=23
    )
    add_code_panel(
        s22,
        6.62,
        y0,
        6.14,
        5.42,
        [
            (
                "src/dapur_domino/evaluation/walk_forward.py · Ukur Error & Wasit DM",
                extract_function_snippet(
                    src / "evaluation" / "walk_forward.py",
                    "evaluate_walk_forward_domino",
                    max_lines=12,
                    max_chars=68,
                    skip_ranges=[("        mae_naive =", "        mae_domino =")],
                    start_at="rmse_ar = float",
                ),
            ),
            (
                "src/dapur_domino/evaluation/lifecycle.py · Aturan Rilis & Tombol Mundur",
                extract_function_snippet(
                    src / "evaluation" / "lifecycle.py",
                    "build_model_review_decision_matrix",
                    max_lines=10,
                    max_chars=68,
                    skip_ranges=[
                        ("            decision =", "            decision ="),
                        ("            review_rationale =", "            next_action ="),
                        ('                "Tambahkan', "            )"),
                    ],
                    start_at="if r_valid and s_valid:",
                ),
            ),
            (
                ">>> OUTPUT NYATA (model_review_decisions.csv · 10 bahan pokok)",
                [
                    "DEPLOY Domino ARX(5) : 3/10 (Beras, Daging Sapi, Minyak Goreng)",
                    "FALLBACK AR(5)       : 5/10 (Cabai Merah/Rawit, Bawang M/P, Gula)",
                    "FALLBACK Naive Last  : 2/10 (Daging Ayam, Telur Ayam)",
                ],
            ),
        ],
        font_size=6.9,
    )

    # =========================================================================
    # SLIDE 23: REVIEW KETERBATASAN & RENCANA ITERASI BERIKUTNYA
    # =========================================================================
    s23 = prs.slides.add_slide(blank_layout)
    y0 = add_header_footer(
        s23,
        "Unit 11 · J.62DMI00.015.1 · Melakukan Proses Review Pemodelan",
        "Mengakui 4 batasan model secara jujur & peta kerja Iterasi Ke-2",
        23,
    )
    add_note_box(
        s23,
        0.58,
        y0,
        3.88,
        5.25,
        "• Merapikan teks resep: 90,33% bersih (cek manual 271/300).\n\n"
        "• Saran isi kulkas: 45,50% Top-5 mengalahkan tebakan populer 40,88%.\n\n"
        "• Keamanan harga: 90,0%–98,2% seri lolos 2 pintu pasca diubah ke % harian.\n\n"
        "• Kontrol hoki: saat kalender dikocok, sinyal acak tinggal 3,44% (<= 5%).\n\n"
        "• Cakupan dapur: 27,74% pemakaian resep terhubung harga BI.",
        title="Capaian Terbukti Nyata\n\n",
        accent=RGB_GRN,
        font_size=10.1,
    )
    add_note_box(
        s23,
        4.72,
        y0,
        3.88,
        5.25,
        (
            "• Pola domino baru membuktikan sinyal muncul lebih dulu, belum membuktikan "
            "sebab-akibat penuh pabrik/BBM.\n\n"
            "• Domino ARX(5) baru unggul di 3/10 bahan pokok (Minyak, Sapi, Beras); "
            "cabai & bawang lebih pas diramal AR(5).\n\n"
            "• Baru 5/14 bahan BI punya kandidat berharga BI pula; sisanya tetap kosong.\n\n"
            "• Satuan pasar (Rp/kg) tidak setara takaran sendok/siung resep."
        ),
        title="Batasan Jujur Model\n\n",
        accent=RGB_RED,
        font_size=10.1,
    )
    add_note_box(
        s23,
        8.86,
        y0,
        3.90,
        5.25,
        (
            "1) Satukan Frasa Seinduk:\n"
            "Gabungkan variasi tulisan ('santan dari kelapa' → 'santan', 'blok gula merah' "
            "→ 'gula merah', 'miri' → 'kemiri') & blokir kata 2 huruf ('di', 'sy').\n\n"
            "2) Tambah Data Cuaca BMKG:\n"
            "Masukkan curah hujan harian sentra panen Jateng/Jatim agar model cabai & "
            "bawang peka terhadap guncangan kebun.\n\n"
            "3) Audit Tiap Kuartal:\n"
            "Perbarui data PIHPS tiap 3 bulan untuk memantau pergeseran arah rambatan."
        ),
        title="Rencana Iterasi Ke-2\n\n",
        accent=RGB_YEL,
        font_size=10.0,
    )

    # =========================================================================
    # SLIDE 24: KOMUNIKASI HASIL (DASHBOARD STREAMLIT 4 HALAMAN)
    # =========================================================================
    s24 = prs.slides.add_slide(blank_layout)
    y0 = add_header_footer(
        s24,
        "Unit 11 · J.62DMI00.015.1 · Melakukan Proses Review Pemodelan",
        "Menyampaikan hasil riset ke masyarakat awam lewat 4 modul visual",
        24,
        subtitle=(
            "Seluruh angka & grafik berasal dari hasil uji nyata proyek, dikemas ke bahasa "
            "sehari-hari agar langsung bisa dipakai ibu rumah tangga & warung."
        ),
    )
    cards_24 = [
        (
            "Ganti bahan",
            (
                "Menyarankan bahan pengganti yang nyambung rasanya di masakan (60%) dan "
                "tenang harganya sebulan terakhir (40%), lengkap dengan tren 90 hari. "
                "Bahan di luar pantauan BI tetap ditulis jujur 'Tanpa data BI'."
            ),
            RGB_RED,
        ),
        (
            "Isi kulkasku",
            (
                "Cukup pilih 1–5 bahan sisa di kulkas untuk mendapat saran bumbu pelengkap "
                "paling pas beserta resep masakan Nusantara lengkap—memisahkan bahan "
                "yang sudah ada vs yang perlu dibeli."
            ),
            RGB_YEL,
        ),
        (
            "Efek domino",
            (
                "Menunjukkan bahan mana yang paling sering memicu bahan lain, perbandingan "
                "dua grafik harga, peta kota barometer seperti Solo untuk cabai, serta "
                "lonjakan harga menjelang Lebaran."
            ),
            RGB_GRN,
        ),
        (
            "Metodologi",
            (
                "Menjelaskan cara kerja 4 langkah sistem secara terbuka, kapan model "
                "berhasil atau mundur, kejujuran batasannya, bukti cek sidik jari file "
                "data, serta pemakaian RAM laptop."
            ),
            RGB_INK,
        ),
    ]
    cw_24 = 2.86
    gap_24 = 0.24
    for idx, (c_title, c_body, c_acc) in enumerate(cards_24):
        cx24 = 0.58 + idx * (cw_24 + gap_24)
        card = s24.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE, Inches(cx24), Inches(y0), Inches(cw_24), Inches(4.85)
        )
        card.adjustments[0] = 0.04
        card.fill.solid()
        card.fill.fore_color.rgb = RGB_WHITE
        card.line.color.rgb = RGB_LINE
        card.line.width = Pt(1)
        tbar = s24.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, Inches(cx24 + 0.02), Inches(y0), Inches(cw_24 - 0.04), Inches(0.08)
        )
        tbar.fill.solid()
        tbar.fill.fore_color.rgb = c_acc
        tbar.line.fill.background()

        tb = s24.shapes.add_textbox(
            Inches(cx24 + 0.20), Inches(y0 + 0.24), Inches(cw_24 - 0.40), Inches(4.40)
        )
        tf = tb.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
        p1 = tf.paragraphs[0]
        r1 = p1.add_run()
        r1.text = c_title
        r1.font.name = FONT_SERIF
        r1.font.size = Pt(17)
        r1.font.bold = True
        r1.font.color.rgb = RGB_INK

        p2 = tf.add_paragraph()
        p2.space_before = Pt(12)
        p2.line_spacing = 1.32
        r2 = p2.add_run()
        r2.text = c_body
        r2.font.name = FONT_SANS
        r2.font.size = Pt(11)
        r2.font.color.rgb = RGB_INK

    # =========================================================================
    # SLIDE 25–27: LAMPIRAN ASESOR DATA SCIENCE (AUDIT, FORMULASI, TATA KELOLA)
    # =========================================================================
    s25 = prs.slides.add_slide(blank_layout)
    y0 = add_header_footer(
        s25,
        "Lampiran · Audit Angka Lengkap",
        "Lampiran A · Rapor lengkap 10 bahan: goyangan, keamanan, & hasil DM",
        25,
        subtitle=(
            "Bukti angka penuh selama 796 hari aktif, uji 2 pintu pada gerak harian, "
            "dan nilai wasit pembanding (296 hari uji)."
        ),
    )
    stat_by_cat = {str(r["comcat_id"]): r for _, r in data["stat_nat"].iterrows()}
    wfr_by_cat = {str(r["target"]): r for _, r in data["wf_raw"].iterrows()}
    wfs_by_cat = {str(r["target"]): r for _, r in data["wf_seas"].iterrows()}

    lamp_a_rows: list[list[str]] = []
    for _, er in data["eda_prices"].sort_values("cv_pct", ascending=False).iterrows():
        cid = str(er["comcat_id"])
        sr = stat_by_cat[cid]
        rr = wfr_by_cat[cid]
        sr_w = wfs_by_cat[cid]
        min_max_txt = f"{fmt_id_int(er['min_idr'])} – {fmt_id_int(er['max_idr'])}"
        sk_ku = (
            f"{'+' if float(er['return_skewness']) > 0 else ''}"
            f"{fmt_id_dec(float(er['return_skewness']), 2)} / "
            f"{fmt_id_dec(float(er['return_kurtosis']), 2)}"
        )
        adf_kpss = (
            f"{fmt_id_dec(float(sr['return_adf_pvalue']), 3)} / "
            f"{fmt_id_dec(float(sr['return_kpss_pvalue']), 3)}"
        )
        dm_p_txt = (
            f"{fmt_id_dec(float(rr['dm_pvalue_vs_ar']), 4)} / "
            f"{fmt_id_dec(float(sr_w['dm_pvalue_vs_ar']), 4)}"
        )
        lamp_a_rows.append(
            [
                str(er["commodity_name"]),
                fmt_id_int(er["mean_idr"]),
                min_max_txt,
                f"{fmt_id_dec(float(er['cv_pct']), 2)}%",
                sk_ku,
                adf_kpss,
                dm_p_txt,
            ]
        )

    def _lamp_a_color(r: int, c: int, val: str) -> tuple[RGBColor, bool] | None:
        if c == 5 and "/ 0,010" in val:
            return (RGB_RED, True)
        if c == 6:
            p_raw, p_seas = (float(x.strip().replace(",", ".")) for x in val.split("/"))
            if p_raw < 0.05 or p_seas < 0.05:
                return (RGB_GRN, True)
        _ = r
        return None

    add_clean_table(
        s25,
        0.58,
        y0,
        12.18,
        5.05,
        [
            "Bahan Pokok",
            "Rata-rata (Rp)",
            "Termurah – Termahal",
            "Goyang%",
            "Arah / Kejutan",
            "Uji ADF / KPSS",
            "Wasit DM (Mentah / Musim)",
        ],
        lamp_a_rows,
        [1.80, 1.15, 2.35, 0.78, 1.75, 2.15, 2.20],
        font_size=8.9,
        bold_cols={0, 3},
        right_cols={1, 3},
        cell_color_fn=_lamp_a_color,
    )

    s26 = prs.slides.add_slide(blank_layout)
    y0 = add_header_footer(
        s26,
        "Lampiran · Ringkasan Cara Kerja Teknis",
        "Lampiran B · Daftar lengkap metode, setelan utama, & alasan pilih",
        26,
        subtitle=(
            "Referensi teknis singkat lengkap dengan kunci acak (seed=42) dan alasan "
            "praktis pemilihan tiap algoritma."
        ),
    )
    lamp_b_rows = [
        [
            "% Gerak & Tes 2 Pintu",
            "r_t = ln(Pt/Pt-1); cek ganda ADF & KPSS",
            "alpha=0,05; autolag='AIC'",
            "Samakan skala Rupiah & cegah korelasi palsu akibat inflasi bersama.",
        ],
        [
            "Kupas Efek Kalender",
            "Pisahkan Sen–Kam, kurva tahunan, & H-14..H+7",
            "Belajar hanya di [:500]",
            "Cegah ilusi kenaikan berjamaah menjelang Lebaran/Natal.",
        ],
        [
            "Domino + Kontrol Hoki",
            "Adu riwayat Granger + FDR + 20× kocok kalender",
            "lag=5; FDR=0,05; seed=42",
            "Buang kebetulan dari 90 tes sekaligus (tinggal 3,44% sisi acak).",
        ],
        [
            "Peramal Ridge Berjalan",
            "beta = (X^T X + alpha·I)^{-1} X^T y; I[0,0]=0",
            "rem=1,0; latih >=500; h=1 hr",
            "Rem L2 mencegah hafalan noise (tanpa rem langsung anjlok -6,64%).",
        ],
        [
            "Graf Bumbu & Louvain",
            "Tali NPMI antar-bumbu & kelompok geng rasa",
            "min 20 resep; NPMI>=0,05",
            "Redam bias garam/bawang & bentuk 82 komunitas rasa alami.",
        ],
        [
            "Pelengkap vs Pengganti",
            "Cond. PMI (bersama) vs Word2Vec (seposisi)",
            "dim=64, win=10, ep=10",
            "Isi kulkas butuh teman sepanci; ganti bahan butuh kembaran fungsi.",
        ],
        [
            "Wasit & Margin Uji",
            "Wilson 95% CI; uji DM 2-arah; MRR; NDCG",
            "uji 296 hr & 3.496 resep",
            "Membuktikan kemenangan bukan hoki & mengukur kualitas urutan.",
        ],
        [
            "Jembatan Sadar-Harga",
            "Penalti eksponensial 30 hr; 0,6 rasa + 0,4 harga",
            "lookback=30 hr aktif BI",
            "Dorong kandidat stabil & tetap jujur kosong saat di luar daftar BI.",
        ],
    ]
    add_clean_table(
        s26,
        0.58,
        y0,
        12.18,
        5.05,
        [
            "Komponen Model",
            "Inti Cara Kerja / Formula",
            "Setelan Terkunci",
            "Mengapa Metode Ini Dipilih",
        ],
        lamp_b_rows,
        [2.25, 3.25, 2.38, 4.30],
        font_size=8.6,
        bold_cols={0},
    )

    s27 = prs.slides.add_slide(blank_layout)
    y0 = add_header_footer(
        s27,
        "Lampiran · Tata Kelola & Efisiensi",
        "Lampiran C · Jaminan anti-bocor ujian, keutuhan data, & bukti RAM",
        27,
        subtitle=(
            "Protokol agar hasil tidak pernah mencontek masa depan, dapat diulang persis "
            "sama, dan enteng di laptop RAM 8 GB."
        ),
    )
    gov_rows = [
        [
            "Cek Keutuhan File Mentah",
            "379 berkas PIHPS & resep lulus cek sidik jari SHA-256 (0 rusak)",
            "Menjamin data historis tak terpotong atau berubah diam-diam.",
        ],
        [
            "Pagar Waktu Harga Ketat",
            "Belajar Awal [0:400] · Simulasi [400:500] · Amplop Ujian [500:796]",
            "Pemilihan jeda & rem dikunci jauh sebelum membuka amplop ujian akhir.",
        ],
        [
            "Pemisahan Resep Ujian",
            "66.419 resep latih dipisah total dari 3.496 resep uji sejak awal",
            "Graf bumbu, komunitas Louvain, & Word2Vec buta total terhadap resep uji.",
        ],
        [
            "Hasil Bisa Diulang Identik",
            "Kunci seed=42 & workers=1 di semua proses acak dan Word2Vec",
            "Siapa pun yang menjalankan ulang akan mendapat angka persis sama.",
        ],
        [
            "Kejujuran Output & Mundur",
            "0 harga ngarang luar BI; aturan mundur eksplisit ke AR(5)/Naive",
            "Menolak klaim palsu pada 7/10 bahan ketika domino tidak membantu.",
        ],
    ]
    add_clean_table(
        s27,
        0.58,
        y0,
        12.18,
        3.15,
        ["Aturan Penjaminan Riset", "Bukti Pelaksanaan", "Manfaat Nyata"],
        gov_rows,
        [2.65, 4.65, 4.88],
        font_size=9.1,
        bold_cols={0},
    )

    total_dur = sum(float(res.get("duration_sec", 0.0)) for res in data["stage_resources"].values())
    peak_ram = float(data["registry"]["peak_ram_mb"].max())

    add_stat_card(
        s27,
        0.58,
        y0 + 3.40,
        2.75,
        1.55,
        f"{fmt_id_dec(peak_ram, 1)} MB",
        "Puncak RAM (< 10% batas 8 GB)",
        accent=RGB_RED,
        val_size=24,
    )
    add_stat_card(
        s27,
        3.53,
        y0 + 3.40,
        2.75,
        1.55,
        f"{fmt_id_dec(total_dur, 1)} dtk",
        "Total waktu 4 tahap pipeline lokal",
        accent=RGB_GRN,
        val_size=24,
    )
    add_note_box(
        s27,
        6.48,
        y0 + 3.40,
        6.28,
        1.55,
        (
            "• Notebook Eksplorasi: notebooks/01_eda_dan_pemodelan_dapur_domino.ipynb "
            "(visualisasi EDA & evaluasi lengkap).\n"
            "• Berjalan 100% lokal (NumPy, Pandas, SciPy, Statsmodels, NetworkX, "
            "Louvain, & Gensim Word2Vec) tanpa cloud/LLM.\n"
            "• Reprodusibilitas penuh: dijalankan ulang dengan seed=42 menghasilkan angka identik."
        ),
        title="Jejak Portofolio & Reprodusibilitas:\n",
        accent=RGB_YEL,
        font_size=9.4,
    )

    # =========================================================================
    # SLIDE 28: LAMPIRAN D — PETA BUKTI 11 UNIT KOMPETENSI BNSP DATA SCIENTIST
    # =========================================================================
    s28 = prs.slides.add_slide(blank_layout)
    y0 = add_header_footer(
        s28,
        "Lampiran · Verifikasi Portofolio BNSP Ilmuwan Data",
        "Lampiran D · Peta bukti 11 Unit Kompetensi SKKNI Data Scientist",
        28,
        subtitle=(
            "Pemetaan langsung setiap unit kompetensi resmi BNSP ke slide presentasi, "
            "fungsi kode Python asli, dan bukti output terukur."
        ),
    )
    skkni_rows = [
        [
            "1",
            "J.62DMI00.001.1",
            "Menentukan Objektif Bisnis",
            "Slide 2",
            "build_business_objectives_matrix() -> 4 KPI usaha, >=25% dapur, RAM <=8 GB",
        ],
        [
            "2",
            "J.62DMI00.002.1",
            "Menentukan Tujuan Teknis Data Science",
            "Slide 3",
            "build_technical_ds_objectives_matrix() -> 7 target teknis & baseline adil",
        ],
        [
            "3",
            "J.62DMI00.005.1",
            "Menelaah Data",
            "Slide 4–5, 30",
            (
                "analyze_price_distributions() & analyze_recipe_corpus_distributions() "
                "-> CV 20,8%, Zipf 80,4%"
            ),
        ],
        [
            "4",
            "J.62DMI00.006.1",
            "Memvalidasi Data",
            "Slide 6–7, 30",
            (
                "verify_raw_manifest() & test_series_stationarity() "
                "-> 379 SHA-256 OK, ADF+KPSS 90–98,2%"
            ),
        ],
        [
            "5",
            "J.62DMI00.007.1",
            "Menentukan Objek Data",
            "Slide 8, 30",
            (
                "build_data_selection_matrix() -> 1.141.526 baris PIHPS, "
                "sekat [0:400]/[400:500]/[500:796]"
            ),
        ],
        [
            "6",
            "J.62DMI00.008.1",
            "Membersihkan Data",
            "Slide 9, 29",
            (
                "clean_price_wide_panel() & normalize_ingredient_line() "
                "-> 796 hr aktif, 271/300 (90,33%) bersih"
            ),
        ],
        [
            "7",
            "J.62DMI00.009.1",
            "Mengkonstruksi Data",
            "Slide 10–11, 30",
            (
                "build_calendar_design_matrix() & residualize_calendar_seasonality() "
                "-> 11 fitur, 0% bocor"
            ),
        ],
        [
            "8",
            "J.62DMI00.012.1",
            "Membangun Skenario Model",
            "Slide 12–13, 31",
            (
                "evaluate_timeseries_modeling_scenarios() "
                "-> 8 skenario, alpha=1,0 cegah overfit -6,64%"
            ),
        ],
        [
            "9",
            "J.62DMI00.013.1",
            "Membangun Model",
            "Slide 14–17, 31",
            (
                "granger_ftest(), benjamini_hochberg_fdr(), Louvain 82 geng, "
                "Word2Vec 64d (796,1 MB RAM)"
            ),
        ],
        [
            "10",
            "J.62DMI00.014.1",
            "Mengevaluasi Hasil Pemodelan",
            "Slide 18–21, 32",
            (
                "evaluate_walk_forward_domino(), diebold_mariano_test(), wilson_ci() "
                "-> 296 hr uji, 3/10 lulus"
            ),
        ],
        [
            "11",
            "J.62DMI00.015.1",
            "Melakukan Proses Review Pemodelan",
            "Slide 22–24, 32",
            (
                "build_model_review_decision_matrix() -> aturan Go/Fallback "
                "(3 Domino, 5 AR5, 2 Naive) & Iterasi 2"
            ),
        ],
    ]
    add_clean_table(
        s28,
        0.58,
        y0,
        12.18,
        5.25,
        [
            "No",
            "Kode Unit",
            "Judul Unit Kompetensi",
            "Slide",
            "Fungsi Kode Python & Bukti Output Terukur",
        ],
        skkni_rows,
        [0.48, 1.55, 2.85, 1.15, 6.15],
        font_size=8.4,
        bold_cols={0, 1, 2},
    )

    # =========================================================================
    # SLIDE 29: LAMPIRAN E — BEDAH KODE LENGKAP UNIT 6 (DATA CLEANING)
    # =========================================================================
    s29 = prs.slides.add_slide(blank_layout)
    y0 = add_header_footer(
        s29,
        "Unit 6 · J.62DMI00.008.1 · Membersihkan Data (Bedah Kode Lengkap)",
        "Lampiran E · Kode lengkap, penjelasan cara kerja, & output data cleaning",
        29,
        subtitle=(
            "Pembersihan harga PIHPS (libur, seri kosong >20%, tambal <=3 hari) serta "
            "normalisasi 852.568 baris teks resep & 236 sinonim."
        ),
    )
    add_code_panel(
        s29,
        0.58,
        y0,
        6.22,
        5.35,
        [
            (
                "src/dapur_domino/cleaning/prices.py · clean_price_wide_panel()",
                extract_function_snippet(
                    src / "cleaning" / "prices.py",
                    "clean_price_wide_panel",
                    max_lines=14,
                    max_chars=66,
                    skip_ranges=[
                        ("    series_audit = pd.DataFrame", "    )"),
                        ("    outlier_rows:", "    outlier_rows:"),
                        ("            index=retained_wide", "            columns=retained_wide"),
                    ],
                    start_at="date_missing_frac =",
                ),
            ),
            (
                "src/dapur_domino/cleaning/ingredients.py · normalize_ingredient_line()",
                extract_function_snippet(
                    src / "cleaning" / "ingredients.py",
                    "normalize_ingredient_line",
                    max_lines=14,
                    max_chars=66,
                    start_at="text = html.unescape",
                ),
            ),
        ],
        font_size=6.8,
    )
    add_code_panel(
        s29,
        6.96,
        y0,
        5.80,
        5.35,
        [
            (
                ">>> CARA KERJA KODE DATA CLEANING (BAHASA SEDERHANA)",
                [
                    "1) date_missing_frac >= 0.90: membuang 8 tanggal libur nasional",
                    "   saat >=90% pasar tutup sehingga 804 hari -> 796 hari aktif.",
                    "2) raw_missing_pct <= 0.20: membuang 50 seri kota yang bolong",
                    "   parah (>20%) agar tidak menciptakan harga beku palsu.",
                    "3) ffill(limit=3): menambal harga kosong maksimal 3 hari kerja.",
                    "4) re.sub & re.split: menghapus tag HTML, isi kurung, satuan",
                    "   takaran (sdm, gr, siung), memecah 'garam gula' yang menempel,",
                    "   lalu memetakan 236 kamus singkatan ('baput'->'bawang putih').",
                ],
            ),
            (
                ">>> OUTPUT EKSEKUSI NYATA · Unit 6 (J.62DMI00.008.1)",
                [
                    "Input Harga  : '58,450' -> 58450.0 | '-' -> None (1.141.526 baris)",
                    "Panel Bersih : Nas 10/10 | Prov 340/340 | Kota 1.049/1.099 seri",
                    "Input Resep  : '1/2 kol (3 ribu) (potong)' -> ['kubis']",
                    "Input Resep  : '3 siung bawang putih iris' -> ['bawang putih']",
                    "Input Resep  : '1 sdt garam gula'          -> ['garam','gula pasir']",
                    "Audit Manual : 271 / 300 baris uji bersih sempurna (90,33% >= 90%)",
                ],
            ),
        ],
        font_size=7.0,
    )

    # =========================================================================
    # SLIDE 30: LAMPIRAN F — BEDAH KODE UNIT 3, 4, 5, & 7 (EDA, VALIDASI, FITUR)
    # =========================================================================
    s30 = prs.slides.add_slide(blank_layout)
    y0 = add_header_footer(
        s30,
        "Unit 3, 4, 5, & 7 · J.62DMI00.005.1–009.1 · Telaah, Validasi, & Konstruksi Data",
        "Lampiran F · Kode lengkap, penjelasan, & output validasi serta fitur",
        30,
        subtitle=(
            "Transformasi persen gerak harian, uji 2 pintu ADF+KPSS, dan pengupasan "
            "11 fitur kalender/Lebaran yang belajar murni di [:500] hari awal."
        ),
    )
    add_code_panel(
        s30,
        0.58,
        y0,
        6.22,
        5.35,
        [
            (
                "src/dapur_domino/prices/stationarity.py · test_series_stationarity()",
                extract_function_snippet(
                    src / "prices" / "stationarity.py",
                    "test_series_stationarity",
                    max_lines=14,
                    max_chars=66,
                    skip_ranges=[
                        ("    kpss_note:", "        warnings.simplefilter"),
                        ("        if caught:", "            kpss_note ="),
                    ],
                    start_at="adf_stat, adf_p",
                ),
            ),
            (
                "src/dapur_domino/prices/seasonality.py · residualize_calendar_seasonality()",
                extract_function_snippet(
                    src / "prices" / "seasonality.py",
                    "residualize_calendar_seasonality",
                    max_lines=12,
                    max_chars=66,
                    skip_ranges=[("        if int(valid.sum())", "            continue")],
                    start_at="x_train = x_all[:train_end_idx]",
                ),
            ),
        ],
        font_size=6.9,
    )
    add_code_panel(
        s30,
        6.96,
        y0,
        5.80,
        5.35,
        [
            (
                ">>> CARA KERJA KODE VALIDASI & KONSTRUKSI (BAHASA SEDERHANA)",
                [
                    "1) compute_log_returns: mengubah Rupiah ke persen gerak harian",
                    "   ln(Pt / Pt-1) agar beras (Rp 15 rb) & sapi (Rp 138 rb) setara.",
                    "2) adfuller & kpss: menguji 2 pintu sekaligus — ADF memastikan",
                    "   tidak melayang acak (p<0,05) & KPSS memastikan datar (p>=0,05).",
                    "3) x_train = x_all[:500]: mengunci agar efek hari kerja, musim,",
                    "   dan lonjakan H-14..H+7 Lebaran HANYA dipelajari dari 500 hari",
                    "   awal (0% mengintip 296 hari ujian), lalu dikupas (y - X@beta).",
                ],
            ),
            (
                ">>> OUTPUT EKSEKUSI NYATA · Unit 3, 4, 5, & 7",
                [
                    "EDA Harga & Resep : Cabai Rawit CV=20,80% | Resep Latih 13,02 vs Uji 13,06",
                    "SHA-256 Manifest  : 379/379 berkas mentah valid (0 rusak/berubah)",
                    "ADF+KPSS Mentah   : 0/10 Nasional (0,0% — tertipu tren inflasi)",
                    "ADF+KPSS LogReturn: Nas 9/10 (90,0%) | Prov 98,24% | Kota 98,00%",
                    "Partisi & Fitur   : [0:400] + [400:500] + [500:796] | 11 fitur (0% bocor)",
                ],
            ),
        ],
        font_size=7.0,
    )

    # =========================================================================
    # SLIDE 31: LAMPIRAN G — BEDAH KODE UNIT 8 & 9 (PEMODELAN DOMINO & KULINER)
    # =========================================================================
    s31 = prs.slides.add_slide(blank_layout)
    y0 = add_header_footer(
        s31,
        "Unit 8 & 9 · J.62DMI00.012.1 & 013.1 · Skenario & Pembangunan Model",
        "Lampiran G · Kode lengkap, penjelasan, & output pemodelan utama",
        31,
        subtitle=(
            "Deteksi efek domino Granger + saringan FDR + kocok kalender 20×, serta "
            "pembangunan graf bumbu NPMI, 82 komunitas Louvain, & Skip-Gram Word2Vec."
        ),
    )
    add_code_panel(
        s31,
        0.58,
        y0,
        6.22,
        5.35,
        [
            (
                "src/dapur_domino/prices/domino.py · granger_ftest() & benjamini_hochberg_fdr()",
                extract_function_snippet(
                    src / "prices" / "domino.py",
                    "granger_ftest",
                    max_lines=10,
                    max_chars=66,
                    start_at="beta_r, *_",
                ),
            ),
            (
                "src/dapur_domino/recipes/embedding.py · train_ingredient_embeddings() & rank",
                extract_function_snippet(
                    src / "recipes" / "embedding.py",
                    "rank_substitution_candidates",
                    max_lines=14,
                    max_chars=66,
                    start_at="neighbors = model.wv",
                ),
            ),
        ],
        font_size=6.8,
    )
    add_code_panel(
        s31,
        6.96,
        y0,
        5.80,
        5.35,
        [
            (
                ">>> CARA KERJA KODE PEMODELAN (BAHASA SEDERHANA)",
                [
                    "1) granger_ftest: mengadu error tebakan tanpa pemicu (rss_r)",
                    "   melawan error dengan pemicu 1–5 hari lalu (rss_u). Jika error",
                    "   turun tajam dan lolos saringan BH-FDR <=5%, dicatat sebagai rantai.",
                    "2) np.roll 20x: mengocok urutan tanggal untuk membuktikan bahwa",
                    "   sinyal yang lolos saat tanggal diacak hanya 3,44% (bukan hoki).",
                    "3) Word2Vec + penalti (1 - npmi): mencari bahan yang konteksnya",
                    "   mirip (cosine_sim tinggi) tapi jarang dimasak sepanci.",
                ],
            ),
            (
                ">>> OUTPUT EKSEKUSI NYATA · Unit 8 & 9",
                [
                    "8 Skenario [400:500]: alpha=0,001 overfit (-6,64%) -> alpha=1,0 (+4,16%)",
                    "Domino Granger+FDR  : 50/90 rantai mentah -> 56/90 bebas musim (100% tahan)",
                    "Kocok Kalender 20x  : 3,1/90 sisi kebetulan (3,44% <= batas 5%)",
                    "Barometer Daerah    : Solo pimpin Cabai Merah (77 kota) & Rawit (75 kota)",
                    "Model Resep (M3)    : 1.334 bahan, 11.938 tali, 82 geng Louvain, Word2Vec 64d",
                ],
            ),
        ],
        font_size=7.0,
    )

    # =========================================================================
    # SLIDE 32: LAMPIRAN H — BEDAH KODE UNIT 10 & 11 (EVALUASI & REVIEW MODEL)
    # =========================================================================
    s32 = prs.slides.add_slide(blank_layout)
    y0 = add_header_footer(
        s32,
        "Unit 10 & 11 · J.62DMI00.014.1 & 015.1 · Evaluasi & Review Pemodelan",
        "Lampiran H · Kode lengkap, penjelasan, & output evaluasi serta review",
        32,
        subtitle=(
            "Peramalan berjalan Ridge 296 hari uji, wasit Diebold-Mariano, jembatan "
            "sadar-harga tanpa harga karangan, serta aturan keputusan Go/Fallback."
        ),
    )
    add_code_panel(
        s32,
        0.58,
        y0,
        6.22,
        5.35,
        [
            (
                "src/dapur_domino/evaluation/walk_forward.py · _fit_ridge() & DM Test",
                extract_function_snippet(
                    src / "evaluation" / "walk_forward.py",
                    "_fit_ridge",
                    max_lines=8,
                    max_chars=66,
                ),
            ),
            (
                "src/dapur_domino/bridge/scoring.py · score_price_aware_substitutions()",
                extract_function_snippet(
                    src / "bridge" / "scoring.py",
                    "score_price_aware_substitutions",
                    max_lines=15,
                    max_chars=66,
                    skip_ranges=[
                        (
                            '                    "target_ingredient":',
                            '                    "direct_npmi":',
                        ),
                        (
                            '                    "comcat_id":',
                            '                    "volatility_30d":',
                        ),
                    ],
                    start_at="sim_score = float",
                ),
            ),
        ],
        font_size=6.8,
    )
    add_code_panel(
        s32,
        6.96,
        y0,
        5.80,
        5.35,
        [
            (
                ">>> CARA KERJA KODE EVALUASI & REVIEW (BAHASA SEDERHANA)",
                [
                    "1) _fit_ridge: menyelesaikan (X^T X + alpha*I) beta = X^T y tiap",
                    "   pagi selama 296 hari ujian tanpa menghukum konstanta dasar.",
                    "2) diebold_mariano_test: menguji selisih kuadrat error Domino vs",
                    "   AR(5) agar klaim kemenangan sah secara statistik (p < 0,05).",
                    "3) if cand_map is not None: menggabungkan 60% rasa + 40% harga",
                    "   tenang hanya bila dipantau BI; jika tidak, wajib 'unmapped'.",
                    "4) Aturan Review: hanya rilis Domino jika menang; sisanya fallback.",
                ],
            ),
            (
                ">>> OUTPUT EKSEKUSI NYATA · Unit 10 & 11",
                [
                    "Ujian 296 Hari (DM) : Minyak +13,47% Raw (LULUS), Sapi +10,00%, Beras +6,62%",
                    "Ujian Isi Kulkas    : Cond.PMI 45,50% [43,85–47,17%] vs Populer 40,88%",
                    "Ujian Substitusi    : Recall@5=24,0% (10/19 gagal karena varian nama sama)",
                    "Jembatan 60/40      : cabai rawit->cabai rawit merah 0,8707 | santan->None",
                    "Keputusan Produksi  : 3/10 Domino ARX(5) | 5/10 Mundur AR(5) | 2/10 Naive",
                ],
            ),
        ],
        font_size=7.0,
    )

    out_pptx.parent.mkdir(parents=True, exist_ok=True)
    target_out = out_pptx
    try:
        prs.save(str(target_out))
    except PermissionError:
        target_out = out_pptx.with_name("_Dapur_Domino_32slides_staging.pptx")
        prs.save(str(target_out))
    size_kb = target_out.stat().st_size / 1024
    print(f"SAVED_PPTX: {target_out.resolve()} ({size_kb:.1f} KB, {len(prs.slides)} slides)")


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    out_pptx = repo_root / "exports" / "Dapur_Domino_Data_Science.pptx"
    build_presentation(repo_root, out_pptx)


if __name__ == "__main__":
    main()
