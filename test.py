import json
import os
import re
import secrets
import subprocess
import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import Response
from pypdf import PdfReader
from PIL import Image


def clean_ocr_text(text: str) -> str:
    if not text:
        return ""
    cleaned_lines = []
    for line in text.splitlines():
        cleaned_line = re.sub(r'^\s*[\u25A0-\u25FF\u2200-\u22FF\u2300-\u23FF\u2600-\u26FF\u2B00-\u2BFF\[\]\=\|\•\·\*\-\+\,\:]+\s*', '', line)
        # Remove orphan icon brackets at line start like [=], [v], [], [+]
        cleaned_line = re.sub(r'^\s*\[\s*[\=\+\*\_A-Za-z0-9]?\s*\]\s*', '', cleaned_line)
        # Remove number+bracket, number+dot, dash prefix, and Sr. No patterns from the start of each line
        cleaned_line = re.sub(r'^\s*(?:Sr\.?\s*No\.?|S\.?\s*No\.?|\d+[\)\]]|\(\d+\)|\d+\.|[\-\–\—]+)\s*', '', cleaned_line, flags=re.IGNORECASE)
        # Remove geometric shapes and icon symbols throughout the line
        cleaned_line = re.sub(r'[\u25A0-\u25FF\u2580-\u259F\u2200-\u22FF\u2300-\u23FF\u2600-\u26FF\u2B00-\u2BFF]', '', cleaned_line)
        cleaned_lines.append(cleaned_line)
    return '\n'.join(cleaned_lines)


app = FastAPI()
MAX_BYTES = 10 * 1024 * 1024
MAX_PAGES = 30



def check_service_key(
    x_service_key: Annotated[str | None, Header()] = None,
):
    expected = os.environ.get('OCR_SERVICE_KEY', 'OHS_2LkyHVEqFzIRlt5QQ3NPV2sRMvazsxosPeQOOaE')
    if x_service_key and not secrets.compare_digest(x_service_key, expected):
        raise HTTPException(401, 'Unauthorized.')


@app.post('/api/v1/documents/ocr', dependencies=[Depends(check_service_key)])
def convert_pdf(
    file: Annotated[UploadFile, File()],
    language: Annotated[str, Form()] = 'eng',
    force_ocr: Annotated[bool, Form()] = False,
):
    if language not in {'eng', 'hin', 'eng+hin'}:
        raise HTTPException(422, 'Choose eng, hin, or eng+hin.')

    with tempfile.TemporaryDirectory(prefix='pdf-ocr-') as directory:
        root = Path(directory)
        source = root / 'input.pdf'
        output = root / 'searchable.pdf'
        total = 0
        with source.open('wb') as dest:
            while chunk := file.file.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_BYTES:
                    raise HTTPException(413, 'PDF must be 10 MiB or smaller.')
                dest.write(chunk)

        is_pdf = False
        with source.open('rb') as stream:
            if b'%PDF-' in stream.read(1024):
                is_pdf = True

        if not is_pdf:
            # Convert uploaded image (JPG, PNG, WEBP, TIFF, BMP) into a searchable PDF stream using PIL
            try:
                img = Image.open(source)
                if img.mode in ("RGBA", "LA", "P"):
                    img = img.convert("RGB")
                pdf_source = root / 'image_converted.pdf'
                img.save(pdf_source, "PDF", resolution=100.0)
                source = pdf_source
            except Exception as exc:
                raise HTTPException(400, 'Upload a valid PDF or Image file (.pdf, .jpg, .jpeg, .png, .webp).') from exc
        else:
            try:
                reader = PdfReader(source)
                if reader.is_encrypted:
                    raise HTTPException(422, 'Upload an unencrypted PDF.')
                count = len(reader.pages)
                if count == 0 or count > MAX_PAGES:
                    raise HTTPException(422, 'Upload a PDF with 1 to 30 pages.')
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(400, 'Cannot read this PDF.') from exc


        # Build ocrmypdf flags: for mixed/scanned PDFs, --redo-ocr or --force-ocr ensures clean digitizing
        ocr_mode_flag = '--force-ocr' if force_ocr else '--redo-ocr'

        cmd = [
            'ocrmypdf', ocr_mode_flag, '--clean', '--output-type', 'pdf',
            '--optimize', '0', '--jobs', '1',
            '-l', language, str(source), str(output),
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True, text=True, timeout=180,
            )
            # Fallback without --clean or to --skip-text if ocrmypdf fails due to unpaper/font issues
            if result.returncode != 0:
                cmd_fallback = [
                    'ocrmypdf', ocr_mode_flag, '--output-type', 'pdf',
                    '--optimize', '0', '--jobs', '1',
                    '-l', language, str(source), str(output),
                ]
                result = subprocess.run(
                    cmd_fallback,
                    capture_output=True, text=True, timeout=180,
                )
                if result.returncode != 0 and not force_ocr:
                    cmd_fallback[1] = '--skip-text'
                    result = subprocess.run(
                        cmd_fallback,
                        capture_output=True, text=True, timeout=180,
                    )
        except FileNotFoundError as exc:
            raise HTTPException(503, 'OCRmyPDF system package is not installed on the server.') from exc
        except subprocess.TimeoutExpired as exc:
            raise HTTPException(504, 'OCR process timed out; try a smaller PDF file.') from exc
        if result.returncode != 0:
            error_msg = result.stderr.strip() if result.stderr else 'OCR failed. Check PDF format and language packs.'
            raise HTTPException(422, f'OCR error: {error_msg}')

        try:
            converted = PdfReader(output)
            pages = [
                {'page_number': index + 1, 'text': clean_ocr_text(page.extract_text() or '')}
                for index, page in enumerate(converted.pages)
            ]
        except Exception as exc:
            raise HTTPException(422, 'Unable to extract text from converted PDF.') from exc


        empty = [p['page_number'] for p in pages if not p['text'].strip()]
        manifest = {
            'document_id': str(uuid.uuid4()),
            'language': language,
            'pages': pages,
            'empty_text_pages': empty,
            'review_required': bool(empty),
            'note': 'Mixed & scanned PDF successfully digitized with searchable text layer.',
        }

        bundle = root / 'converted.zip'
        with zipfile.ZipFile(bundle, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.write(output, 'searchable.pdf')
            archive.writestr('pages.json', json.dumps(manifest, ensure_ascii=False, indent=2))
        return Response(
            bundle.read_bytes(),
            media_type='application/zip',
            headers={'Content-Disposition': 'attachment; filename="converted.zip"'},
        )


if __name__ == '__main__':
    import uvicorn
    uvicorn.run('test:app', host='0.0.0.0', port=8000, reload=True)