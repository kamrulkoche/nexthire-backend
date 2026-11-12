"""Writing leads to CSV, Excel and PDF.

Files are built in memory and streamed to the caller; nothing is written to
disk, and no copy is kept (see ``LeadExport``).

Every format carries the same columns, and a "Source: Google Maps" note as
attribution for the Places content.
"""

import csv
import io
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, List, Optional, Sequence

from ...domain.enums import ExportFormat
from ..schemas.lead_finder_schema import LeadSchema

ATTRIBUTION = "Business data: Google Maps (Places API)."

MEDIA_TYPES = {
    ExportFormat.CSV: "text/csv; charset=utf-8",
    ExportFormat.XLSX: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ExportFormat.PDF: "application/pdf",
}


@dataclass(frozen=True)
class Column:
    """One exported column: its header and how to read it from a lead."""

    header: str
    value: Callable[[LeadSchema], object]
    width: int  # characters in Excel; relative weight in the PDF


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.1f}"
    return str(value)


COLUMNS: List[Column] = [
    Column("Business Name", lambda lead: lead.name or "", 34),
    Column("Phone", lambda lead: lead.phone or "", 18),
    Column("Phone (E.164)", lambda lead: lead.phone_normalized or "", 17),
    Column("Category", lambda lead: lead.category or "", 20),
    Column("District", lambda lead: lead.district or "", 14),
    Column("Upazila", lambda lead: lead.upazila or "", 14),
    Column("Area", lambda lead: lead.area or "", 14),
    Column("Address", lambda lead: lead.address or "", 44),
    Column("Website", lambda lead: lead.website or "", 28),
    Column("Rating", lambda lead: lead.rating, 7),
    Column("Reviews", lambda lead: lead.review_count, 8),
    Column("Google Maps", lambda lead: lead.google_maps_url or "", 30),
    Column("Place ID", lambda lead: lead.place_id, 28),
    Column(
        "Duplicate Phone", lambda lead: "Yes" if lead.is_duplicate_phone else "", 10
    ),
    Column(
        "Lead Status",
        lambda lead: (
            lead.saved_status.value.replace("_", " ").title()
            if lead.saved_status
            else ""
        ),
        13,
    ),
]

#: The narrower set the PDF prints (a landscape page cannot hold all 15).
PDF_COLUMNS = [
    "Business Name",
    "Phone",
    "Category",
    "District",
    "Address",
    "Website",
    "Rating",
]


def file_name(prefix: str, export_format: ExportFormat, now: datetime) -> str:
    """``leads-hospital-20261106-1432.xlsx`` — safe characters only."""
    safe = "".join(ch if ch.isalnum() else "-" for ch in prefix.lower()).strip("-")
    safe = "-".join(part for part in safe.split("-") if part)[:60] or "leads"
    return f"{safe}-{now:%Y%m%d-%H%M}.{export_format.value}"


def build_export(
    export_format: ExportFormat, leads: Sequence[LeadSchema], title: str, now: datetime
) -> bytes:
    """The file's bytes in the requested format."""
    if export_format == ExportFormat.CSV:
        return _csv(leads)
    if export_format == ExportFormat.XLSX:
        return _xlsx(leads, title, now)
    return _pdf(leads, title, now)


def _csv(leads: Sequence[LeadSchema]) -> bytes:
    """UTF-8 with a BOM, so Excel opens Bengali text correctly."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([column.header for column in COLUMNS])
    for lead in leads:
        writer.writerow([_csv_safe(_text(column.value(lead))) for column in COLUMNS])
    return ("\ufeff" + buffer.getvalue()).encode("utf-8")


def _csv_safe(value: str) -> str:
    """Defuse spreadsheet formula injection from third-party text.

    A business name beginning with ``=``, ``+``, ``-`` or ``@`` would run as a
    formula when the CSV is opened in Excel. A phone number's leading ``+`` is
    the one legitimate case, and it is kept.
    """
    if (
        value
        and value[0] in "=-@\t\r"
        or (value.startswith("+") and not value[1:2].isdigit())
    ):
        return "'" + value
    return value


def _xlsx(leads: Sequence[LeadSchema], title: str, now: datetime) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "Leads"
    header_fill = PatternFill("solid", fgColor="1D3AC4")
    sheet.append([column.header for column in COLUMNS])
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = header_fill
        cell.alignment = Alignment(vertical="center")
    for lead in leads:
        row = []
        for column in COLUMNS:
            value = column.value(lead)
            # Every string is stored as TEXT (data_type "s"): openpyxl would
            # otherwise turn a leading "=" into a formula.
            row.append(
                value
                if isinstance(value, (int, float)) or value is None
                else str(value)
            )
        sheet.append(row)
    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            if isinstance(cell.value, str):
                cell.data_type = "s"
    for index, column in enumerate(COLUMNS, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = column.width
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions

    info = workbook.create_sheet("About")
    info.append(["Export", title])
    info.append(["Generated (UTC)", now.strftime("%Y-%m-%d %H:%M")])
    info.append(["Rows", len(leads)])
    info.append(["Source", ATTRIBUTION])
    info.column_dimensions["A"].width = 18
    info.column_dimensions["B"].width = 60

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


#: TrueType fonts with wide Unicode coverage, tried in order. fpdf2's built-in
#: fonts are Latin-1 only; a business name in Bengali needs a real font.
_FONT_CANDIDATES = [
    os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "Nirmala.ttf"),
    os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "arial.ttf"),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
]


def _unicode_font() -> Optional[str]:
    for path in _FONT_CANDIDATES:
        if os.path.isfile(path):
            return path
    return None


def _pdf(leads: Sequence[LeadSchema], title: str, now: datetime) -> bytes:
    from fpdf import FPDF
    from fpdf.fonts import FontFace

    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=12)
    font_path = _unicode_font()
    if font_path:
        pdf.add_font("Body", "", font_path)
        pdf.add_font("Body", "B", font_path)
        family = "Body"

        def clean(value: str) -> str:
            return value

    else:
        family = "Helvetica"

        def clean(value: str) -> str:
            # Latin-1 only without a Unicode font: replace what cannot print
            # rather than failing the whole export.
            return value.encode("latin-1", "replace").decode("latin-1")

    pdf.add_page()
    pdf.set_font(family, "B", 14)
    pdf.cell(0, 8, clean(title), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(family, "", 8)
    pdf.cell(
        0,
        5,
        clean(
            f"{len(leads)} businesses - generated {now:%Y-%m-%d %H:%M} UTC - {ATTRIBUTION}"
        ),
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(2)

    selected = [column for column in COLUMNS if column.header in PDF_COLUMNS]
    widths = tuple(column.width for column in selected)
    pdf.set_font(family, "", 7)
    headings = FontFace(
        emphasis="BOLD", color=(255, 255, 255), fill_color=(29, 58, 196)
    )
    with pdf.table(
        col_widths=widths,
        headings_style=headings,
        line_height=4.2,
        text_align="LEFT",
        first_row_as_headings=True,
    ) as table:
        header = table.row()
        for column in selected:
            header.cell(column.header)
        for lead in leads:
            row = table.row()
            for column in selected:
                row.cell(clean(_text(column.value(lead)))[:180])
    output = pdf.output()
    return bytes(output)
