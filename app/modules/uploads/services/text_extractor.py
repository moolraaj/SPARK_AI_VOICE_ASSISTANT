import io

SCANNED_PDF_MARKER = "__SCANNED_PDF__"


def extract_raw_text_from_bytes(file_bytes: bytes, ext: str) -> str:
    """
    Lightweight, fast in-memory raw text extractor for domain classification
    without writing files to disk prematurely.
    Returns SCANNED_PDF_MARKER if a PDF has no selectable text layer (scanned/image PDF).
    """
    text = ""
    try:
        if ext == ".pdf":
            try:
                import pypdf
                reader = pypdf.PdfReader(io.BytesIO(file_bytes))
                for page in reader.pages[:10]:
                    page_text = page.extract_text() or ""
                    text += page_text + " "

                # If ALL pages returned empty text -> scanned/image-based PDF
                if not text.strip():
                    return SCANNED_PDF_MARKER

            except Exception:
                return SCANNED_PDF_MARKER

        elif ext in [".xlsx", ".xls"]:
            try:
                import openpyxl
                wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
                for sheet in wb.worksheets:
                    for row in sheet.iter_rows(values_only=True):
                        row_str = " ".join([str(cell) for cell in row if cell is not None])
                        text += row_str + " "
            except Exception:
                text = file_bytes.decode("utf-8", errors="ignore")

        elif ext == ".csv":
            text = file_bytes.decode("utf-8", errors="ignore")

    except Exception:
        text = file_bytes.decode("utf-8", errors="ignore")

    return text.strip()
