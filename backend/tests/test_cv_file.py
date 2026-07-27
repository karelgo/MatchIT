import io

import pytest
from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.services.cvfile import MAX_PDF_BYTES, CVFileError, extract_pdf_text
from tests.conftest import auth_headers, create_specialist
from tests.test_enrichment import CV_TEXT, cv_extraction


def pdf_with_text(text: str) -> bytes:
    buffer = io.BytesIO()
    page = canvas.Canvas(buffer, pagesize=A4)
    y = 800
    for line in text.split(". "):
        page.drawString(40, y, line[:110])
        y -= 14
        if y < 40:
            page.showPage()
            y = 800
    page.save()
    return buffer.getvalue()


def blank_pdf() -> bytes:
    buffer = io.BytesIO()
    page = canvas.Canvas(buffer, pagesize=A4)
    page.showPage()  # a page with no text layer — what a scan looks like
    page.save()
    return buffer.getvalue()


def encrypted_pdf() -> bytes:
    writer = PdfWriter()
    writer.append(PdfReader(io.BytesIO(pdf_with_text(CV_TEXT))))
    writer.encrypt("secret")
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


# ---- extraction unit tests ----


def test_text_pdf_round_trips():
    text = extract_pdf_text(pdf_with_text(CV_TEXT))
    assert "40TB" in text
    assert "Microsoft" in text


def test_non_pdf_is_rejected_with_a_clear_message():
    with pytest.raises(CVFileError, match="not a PDF"):
        extract_pdf_text(b"\x89PNG\r\n\x1a\n not a pdf at all")


def test_scanned_pdf_without_text_layer_is_rejected():
    with pytest.raises(CVFileError, match="scanned"):
        extract_pdf_text(blank_pdf())


def test_encrypted_pdf_is_rejected():
    with pytest.raises(CVFileError, match="password"):
        extract_pdf_text(encrypted_pdf())


def test_oversize_pdf_is_rejected_before_parsing():
    oversized = b"%PDF-1.7" + b"\x00" * (MAX_PDF_BYTES + 10)
    with pytest.raises(CVFileError, match="5 MB"):
        extract_pdf_text(oversized)


# ---- API ----


async def test_pdf_upload_enriches_the_profile(client, fake_chat):
    tokens, _ = await create_specialist(client, email="pdfcv@example.com")

    fake_chat.responses.append(cv_extraction())
    response = await client.post(
        "/api/v1/specialists/me/enrich/cv-file",
        headers=auth_headers(tokens),
        files={"file": ("cv.pdf", pdf_with_text(CV_TEXT), "application/pdf")},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["source"] == "cv"
    assert body["profile"]["headline"] == "Data architect specialising in Microsoft Fabric"
    # the extracted text, not the raw bytes, reached the model
    assert "40TB" in fake_chat.calls[-1]["user"]


async def test_scanned_pdf_upload_returns_actionable_422(client, fake_chat):
    tokens, _ = await create_specialist(client, email="pdfscan@example.com")
    calls_before = len(fake_chat.calls)
    response = await client.post(
        "/api/v1/specialists/me/enrich/cv-file",
        headers=auth_headers(tokens),
        files={"file": ("scan.pdf", blank_pdf(), "application/pdf")},
    )
    assert response.status_code == 422
    assert "scanned" in response.json()["detail"]
    assert len(fake_chat.calls) == calls_before, "no model call for an unreadable file"


async def test_non_pdf_upload_is_rejected(client):
    tokens, _ = await create_specialist(client, email="pdfpng@example.com")
    response = await client.post(
        "/api/v1/specialists/me/enrich/cv-file",
        headers=auth_headers(tokens),
        files={"file": ("cv.png", b"\x89PNG\r\n\x1a\n....", "image/png")},
    )
    assert response.status_code == 422
    assert "not a PDF" in response.json()["detail"]


async def test_pdf_upload_requires_a_specialist(client):
    from tests.conftest import register

    tokens = await register(client, email="pdf-hm@example.com", role="hiring_manager")
    response = await client.post(
        "/api/v1/specialists/me/enrich/cv-file",
        headers=auth_headers(tokens),
        files={"file": ("cv.pdf", pdf_with_text(CV_TEXT), "application/pdf")},
    )
    assert response.status_code == 403
