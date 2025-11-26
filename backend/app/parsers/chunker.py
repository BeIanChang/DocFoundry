from typing import List, Dict


def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> List[Dict]:
    """Split text into overlapping chunks.

    Returns a list of dicts: {"text": <chunk_text>, "start_pos": <int>, "end_pos": <int>}
    """
    if not text:
        return []

    chunks = []
    start = 0
    text_len = len(text)

    # normalize whitespace to reduce chance of odd splits
    # keep original indexes by operating on the original text

    while start < text_len:
        end = start + chunk_size
        if end >= text_len:
            end = text_len
        chunk = text[start:end]
        chunks.append({"text": chunk, "start_pos": start, "end_pos": end})
        if end == text_len:
            break
        start = end - overlap
        if start < 0:
            start = 0

    return chunks
