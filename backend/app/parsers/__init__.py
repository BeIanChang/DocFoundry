"""Lightweight parser package exposing parse_file lazily.

We avoid importing heavy parser dependencies at package-import time so the dev
image (which may not have pypdf) doesn't crash during module import.
"""

def parse_file(filename: str, raw_bytes: bytes) -> str:
	# import inside the function so missing optional deps don't break imports
	from .pdf_parser import parse_file as _parse_file

	return _parse_file(filename, raw_bytes)

__all__ = ["parse_file"]
