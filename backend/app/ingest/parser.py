"""Parse uploaded documents (txt/md/pdf) into locatable sections.

Sections keep their heading and page so every downstream claim can cite
"document, section, page". Heading heuristics cover the conventions of
credit documentation: "Section 7.1", "NOTE 4", schedules, and all-caps
headings.
"""

import io
import re

from app.agent.state import DocSection, ParsedDoc

_HEADING_PATTERNS = [
    re.compile(r"^\s*section\s+\d+(\.\d+)*", re.IGNORECASE),
    re.compile(r"^\s*note\s+\d+", re.IGNORECASE),
    re.compile(r"^\s*(schedule|annex|exhibit|article)\s+", re.IGNORECASE),
]
_ALL_CAPS = re.compile(r"^[A-Z0-9][A-Z0-9 \-&(),./'’—–]{5,}$")

# Legal drafting often writes subsections as a single paragraph:
# "Section 9.4 Measurement; Supersession. Financial covenants are tested..."
# Split those so the citation points at "Section 9.4 ...", not the parent.
_NUMBERED_INLINE = re.compile(
    r"^(?P<title>(?:section|note|article|schedule|annex|exhibit)\s+\d+(?:\.\d+)*[^.\n]{0,60}\.)\s+(?P<rest>\S.*)$",
    re.IGNORECASE,
)


def _is_heading(line: str) -> bool:
    stripped = line.strip()
    if not stripped or len(stripped) > 90:
        return False
    if any(p.match(stripped) for p in _HEADING_PATTERNS):
        return True
    return bool(_ALL_CAPS.match(stripped))


def infer_kind(filename: str) -> str:
    name = filename.lower()
    if "agreement" in name or "contract" in name or "credit" in name:
        return "credit_agreement"
    if "report" in name or "financial" in name or "10q" in name:
        return "financial_report"
    if "treasury" in name or "transaction" in name or "pack" in name:
        return "treasury_pack"
    return "other"


def parse_text(doc_id: str, filename: str, raw: str, page: int | None = None) -> ParsedDoc:
    sections: list[DocSection] = []
    title = "Preamble"
    buffer: list[str] = []

    def flush() -> None:
        text = "\n".join(buffer).strip()
        if text:
            sections.append(
                DocSection(
                    section_id=f"{doc_id}#{len(sections)}",
                    title=title,
                    page=page,
                    text=text,
                )
            )

    for line in raw.splitlines():
        stripped = line.strip()
        if _is_heading(stripped):
            flush()
            buffer = []
            title = stripped
            continue
        if len(stripped) > 90:
            inline = _NUMBERED_INLINE.match(stripped)
            if inline:
                flush()
                title = inline.group("title").strip()
                buffer = [inline.group("rest")]
                continue
        buffer.append(line)
    flush()

    return ParsedDoc(
        doc_id=doc_id, filename=filename, kind=infer_kind(filename), sections=sections
    )


def parse_pdf(doc_id: str, filename: str, data: bytes) -> ParsedDoc:
    import pdfplumber

    sections: list[DocSection] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if not text.strip():
                continue
            page_doc = parse_text(doc_id, filename, text, page=page_number)
            for section in page_doc.sections:
                section.section_id = f"{doc_id}#{len(sections)}"
                sections.append(section)

    return ParsedDoc(
        doc_id=doc_id, filename=filename, kind=infer_kind(filename), sections=sections
    )


def parse_upload(doc_id: str, filename: str, data: bytes) -> ParsedDoc:
    if filename.lower().endswith(".pdf"):
        return parse_pdf(doc_id, filename, data)
    return parse_text(doc_id, filename, data.decode("utf-8", errors="replace"))
