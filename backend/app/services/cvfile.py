"""PDF → text for CV enrichment.

A thin adapter in front of the CV extractor, which takes text. The failure modes
here are user-facing, so each gets a distinct, actionable message: an encrypted
file, a non-PDF, and — the common one — a scanned CV with no text layer, which
looks like a valid PDF but extracts to nothing.
"""

import io

from pypdf import PdfReader
from pypdf.errors import PyPdfError

MAX_PDF_BYTES = 5 * 1024 * 1024
MAX_PAGES = 30  # a CV, not a book — also bounds work on a malicious file
MIN_EXTRACTED_CHARS = 100  # matches CVEnrichmentRequest's minimum


class CVFileError(Exception):
    """The file cannot be turned into CV text; the message is user-facing."""


def extract_pdf_text(data: bytes) -> str:
    if not data.startswith(b"%PDF-"):
        raise CVFileError("This file is not a PDF.")
    if len(data) > MAX_PDF_BYTES:
        raise CVFileError("PDF is larger than 5 MB; export a smaller version.")

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise CVFileError("This PDF is password-protected; remove the password first.")
        pages = reader.pages[:MAX_PAGES]
        text = "\n\n".join(page.extract_text() or "" for page in pages).strip()
    except CVFileError:
        raise
    except (PyPdfError, ValueError, KeyError) as error:
        raise CVFileError("This PDF could not be read; try re-exporting it.") from error

    if len(text) < MIN_EXTRACTED_CHARS:
        raise CVFileError(
            "No readable text found — this looks like a scanned document. "
            "Export the CV as a text PDF, or paste the text directly."
        )
    return text
