"""OCR Service for resume parsing.

Handles conversion of PDF/Image files to text using Tesseract.
"""

import io
import logging

import pytesseract
from pdf2image import convert_from_bytes
from PIL import Image

logger = logging.getLogger(__name__)


def extract_text_from_file(file_content: bytes, content_type: str) -> str:
    """Extract text from file content (PDF or Image)."""
    try:
        text = ""

        if "pdf" in content_type:
            # Convert PDF to images
            try:
                images = convert_from_bytes(file_content)
                for image in images:
                    text += pytesseract.image_to_string(image) + "\n"
            except Exception as e:
                logger.error(f"Error extracting text from PDF: {e}")
                # Fallback: Try to read as text if it's not a scanned PDF?
                # Or just raise. For now, let's assume valid PDF.
                raise

        elif "image" in content_type:
            try:
                image = Image.open(io.BytesIO(file_content))
                text = pytesseract.image_to_string(image)
            except Exception as e:
                logger.error(f"Error extracting text from Image: {e}")
                raise

        else:
            # Try to read as plain text if it's none of the above
            try:
                text = file_content.decode("utf-8", errors="ignore")
            except Exception:
                raise ValueError(f"Unsupported content type: {content_type}")

        return text.strip()

    except Exception as e:
        logger.error(f"OCR failed: {e}")
        return ""
