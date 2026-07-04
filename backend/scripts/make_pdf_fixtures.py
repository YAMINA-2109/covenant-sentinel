"""Generate realistic PDF versions of the demo fixtures (dev tooling).

Reads the .txt fixtures and typesets them as lender-file PDFs (headers,
footers, page numbers) into fixtures/pdf/. The PDFs are what we upload in
the demo video; the .txt versions remain for quick judge reproduction.

Usage:    .venv\\Scripts\\python.exe scripts\\make_pdf_fixtures.py
Requires: pip install fpdf2   (dev-only dependency, see requirements-dev.txt)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fpdf import FPDF  # noqa: E402

from app.ingest.parser import _NUMBERED_INLINE, _is_heading  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
OUT_DIR = FIXTURES / "pdf"
FONT_REGULAR = Path(r"C:\Windows\Fonts\arial.ttf")
FONT_BOLD = Path(r"C:\Windows\Fonts\arialbd.ttf")

DOCS = [
    ("acme_credit_agreement.txt", "acme_credit_agreement.pdf", "Credit Agreement — ACME Industries S.A.S."),
    ("acme_q2_2026_financial_report.txt", "acme_q2_2026_financial_report.pdf", "Quarterly Financial Report — Q2 2026"),
    ("acme_treasury_pack_q2_2026.txt", "acme_treasury_pack_q2_2026.pdf", "Treasury Pack — Q2 2026"),
]


class FixturePDF(FPDF):
    def __init__(self, doc_title: str) -> None:
        super().__init__(format="A4")
        self.doc_title = doc_title
        self.set_margins(22, 20, 22)
        self.set_auto_page_break(auto=True, margin=22)

    def header(self) -> None:
        self.set_font("Body", "", 7.5)
        self.set_text_color(120, 120, 120)
        self.cell(83, 5, self.doc_title, align="L", new_x="RIGHT", new_y="TOP")
        self.cell(83, 5, "CONFIDENTIAL — Lender relationship file", align="R", new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(200, 200, 200)
        self.line(22, self.get_y() + 1, 188, self.get_y() + 1)
        self.ln(5)
        self.set_text_color(20, 20, 20)
        self.set_x(self.l_margin)

    def footer(self) -> None:
        self.set_y(-16)
        self.set_font("Body", "", 7.5)
        self.set_text_color(120, 120, 120)
        self.cell(0, 6, f"Page {self.page_no()} of {{nb}}", align="C")


def render(txt_name: str, pdf_name: str, title: str) -> None:
    raw = (FIXTURES / txt_name).read_text(encoding="utf-8")
    pdf = FixturePDF(title)
    pdf.add_font("Body", "", str(FONT_REGULAR))
    pdf.add_font("Body", "B", str(FONT_BOLD))
    pdf.alias_nb_pages()
    pdf.add_page()
    pdf.set_font("Body", "", 9.5)

    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            pdf.ln(2.2)
            continue
        pdf.set_x(pdf.l_margin)
        inline = _NUMBERED_INLINE.match(stripped) if len(stripped) > 90 else None
        if _is_heading(stripped):
            pdf.ln(1.5)
            pdf.set_font("Body", "B", 10.5)
            pdf.multi_cell(0, 5.6, stripped, new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Body", "", 9.5)
        elif inline:
            pdf.ln(1.2)
            pdf.set_font("Body", "B", 9.5)
            pdf.multi_cell(0, 5.2, inline.group("title").strip(), new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Body", "", 9.5)
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(0, 5.0, inline.group("rest").strip(), new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.multi_cell(0, 5.0, stripped, new_x="LMARGIN", new_y="NEXT")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pdf.output(str(OUT_DIR / pdf_name))
    print(f"wrote {OUT_DIR / pdf_name}")


if __name__ == "__main__":
    for txt_name, pdf_name, title in DOCS:
        render(txt_name, pdf_name, title)
