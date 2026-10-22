import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional
import pymupdf  # PyMuPDF

from .ocr_engine import OCREngine
from .validator import ValidationError

logger = logging.getLogger(__name__)

@dataclass
class ProcessedPage:
    page_number: int  # 1-based
    text: str
    extraction_method: str  # 'text', 'ocr', 'blank', 'ocr_unavailable', 'unreadable'
    ocr_confidence: Optional[float] = None
    char_count: int = 0
    warnings: List[str] = field(default_factory=list)

@dataclass
class ProcessedDocument:
    document_id: str
    display_name: str
    file_path: str
    total_pages: int
    pages: List[ProcessedPage] = field(default_factory=list)
    status: str = "success"  # 'success', 'partial', 'failed'
    warnings: List[str] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        return "\n\n".join(f"--- Page {p.page_number} ---\n{p.text}" for p in self.pages if p.text)

class PDFProcessor:
    """Extracts text and structured page information from PDF files with OCR fallback."""

    def __init__(self, ocr_engine: Optional[OCREngine] = None, max_pages: int = 50):
        self.ocr_engine = ocr_engine or OCREngine()
        self.max_pages = max_pages

    def process_pdf(self, file_path: str, display_name: str, document_id: str) -> ProcessedDocument:
        path = Path(file_path)
        if not path.exists():
            raise ValidationError(f"Document file not found at: {file_path}")

        try:
            doc = pymupdf.open(str(path))
        except Exception as e:
            raise ValidationError(f"Failed to open '{display_name}': Corrupted or malformed PDF ({str(e)})")

        if doc.is_encrypted:
            doc.close()
            raise ValidationError(f"Document '{display_name}' is password-protected or encrypted.")

        total_pages = len(doc)
        if total_pages == 0:
            doc.close()
            raise ValidationError(f"Document '{display_name}' has 0 pages (empty file).")

        if total_pages > self.max_pages:
            doc.close()
            raise ValidationError(
                f"Document '{display_name}' has {total_pages} pages, which exceeds the limit of {self.max_pages} pages."
            )

        processed_pages: List[ProcessedPage] = []
        doc_warnings: List[str] = []

        for page_idx in range(total_pages):
            page_num = page_idx + 1
            page = doc[page_idx]

            # 1. Attempt standard digital text extraction
            text = page.get_text("text").strip()
            images = page.get_images()

            if len(text) >= 25:
                # Page has direct readable text
                processed_pages.append(
                    ProcessedPage(
                        page_number=page_num,
                        text=text,
                        extraction_method="text",
                        char_count=len(text),
                    )
                )
            elif images:
                # Likely a scanned or image-based page: attempt OCR
                logger.info(f"Page {page_num} in '{display_name}' appears scanned ({len(images)} images, {len(text)} chars). Triggering OCR.")
                pix = page.get_pixmap(dpi=150)
                img_bytes = pix.tobytes("png")

                ocr_text, ocr_conf, ocr_status = self.ocr_engine.process_image(img_bytes)

                if ocr_status == "ocr_success" and ocr_text:
                    # Combine any existing digital text with OCR
                    combined_text = f"{text}\n{ocr_text}".strip() if text else ocr_text
                    processed_pages.append(
                        ProcessedPage(
                            page_number=page_num,
                            text=combined_text,
                            extraction_method="ocr",
                            ocr_confidence=ocr_conf,
                            char_count=len(combined_text),
                        )
                    )
                elif ocr_status == "ocr_unavailable":
                    warning_msg = f"Page {page_num} is a scanned image but OCR is unavailable on this server."
                    doc_warnings.append(warning_msg)
                    processed_pages.append(
                        ProcessedPage(
                            page_number=page_num,
                            text=text,
                            extraction_method="ocr_unavailable",
                            char_count=len(text),
                            warnings=[warning_msg],
                        )
                    )
                else:
                    # OCR empty or failed
                    warning_msg = f"Page {page_num} contains images but no readable text could be recognized."
                    doc_warnings.append(warning_msg)
                    processed_pages.append(
                        ProcessedPage(
                            page_number=page_num,
                            text=text,
                            extraction_method="scanned_empty",
                            char_count=len(text),
                            warnings=[warning_msg],
                        )
                    )
            elif len(text) > 0:
                # Sparse text page
                processed_pages.append(
                    ProcessedPage(
                        page_number=page_num,
                        text=text,
                        extraction_method="text_sparse",
                        char_count=len(text),
                    )
                )
            else:
                # Completely blank page
                processed_pages.append(
                    ProcessedPage(
                        page_number=page_num,
                        text="",
                        extraction_method="blank",
                        char_count=0,
                        warnings=[f"Page {page_num} is blank."],
                    )
                )

        doc.close()

        status = "success"
        if doc_warnings:
            status = "partial" if any(p.char_count > 0 for p in processed_pages) else "warning"

        return ProcessedDocument(
            document_id=document_id,
            display_name=display_name,
            file_path=str(path),
            total_pages=total_pages,
            pages=processed_pages,
            status=status,
            warnings=doc_warnings,
        )
