"""Extract text from an uploaded PDF bank statement.

This deliberately does no financial parsing itself — no transaction
regexing, no category matching. It hands raw (truncated) text to the
chat model, which is far better suited to summarizing varied bank
statement formats than a hand-rolled parser would be, and the model
is instructed to state its estimate back to the client for
confirmation rather than treating it as ground truth.
"""

from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader

MAX_CHARS = 8000  # keep the prompt bounded regardless of statement length


def extract_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(BytesIO(pdf_bytes))
    pages_text = []
    for page in reader.pages:
        pages_text.append(page.extract_text() or "")
    full_text = "\n".join(pages_text).strip()

    if not full_text:
        raise ValueError(
            "Could not extract text from this PDF — it may be a scanned "
            "image rather than a text-based statement."
        )

    if len(full_text) > MAX_CHARS:
        full_text = full_text[:MAX_CHARS] + "\n[...truncated...]"

    return full_text
