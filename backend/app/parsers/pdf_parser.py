import io
import os
from pypdf import PdfReader


def parse_file(filename: str, raw_bytes: bytes) -> str:
    """Simple parser for PDF/TXT/HTML. Returns extracted text as string."""
    _, ext = os.path.splitext(filename.lower())
    if ext == '.pdf':
        stream = io.BytesIO(raw_bytes)
        reader = PdfReader(stream)
        texts = []
        for p in reader.pages:
            try:
                texts.append(p.extract_text() or "")
            except Exception:
                continue
        return "\n".join(texts)
    elif ext in ('.txt', '.text'):
        return raw_bytes.decode('utf-8', errors='ignore')
    elif ext in ('.html', '.htm'):
        # naive strip tags — placeholder
        s = raw_bytes.decode('utf-8', errors='ignore')
        # very naive: remove tags
        import re
        return re.sub(r'<[^>]+>', ' ', s)
    else:
        # try to decode as text
        try:
            return raw_bytes.decode('utf-8', errors='ignore')
        except Exception:
            raise ValueError('Unsupported file type or unreadable bytes')
