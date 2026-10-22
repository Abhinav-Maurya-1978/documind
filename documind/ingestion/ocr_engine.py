import io
import logging
import shutil
from typing import Optional, Tuple
from PIL import Image

logger = logging.getLogger(__name__)

class OCREngine:
    """OCR processor using pytesseract with fallback handling and confidence estimation."""

    def __init__(self, tesseract_cmd: str = "tesseract", enabled: bool = True):
        self.enabled = enabled
        self.tesseract_cmd = tesseract_cmd
        self._available = False
        self._init_engine()

    def _init_engine(self):
        """Check if pytesseract and tesseract binary are available."""
        if not self.enabled:
            logger.info("OCR is disabled in configuration.")
            self._available = False
            return

        try:
            import pytesseract
            if self.tesseract_cmd and shutil.which(self.tesseract_cmd):
                pytesseract.pytesseract.tesseract_cmd = self.tesseract_cmd
                # Verify execution
                ver = pytesseract.get_tesseract_version()
                logger.info(f"Tesseract OCR initialized successfully. Version: {ver}")
                self._available = True
            else:
                # Check default command
                ver = pytesseract.get_tesseract_version()
                logger.info(f"Tesseract OCR found on system PATH. Version: {ver}")
                self._available = True
        except Exception as e:
            logger.warning(
                f"Tesseract OCR is not available on this system ({e}). "
                "Scanned PDFs will be flagged and processed with digital text extraction only."
            )
            self._available = False

    @property
    def is_available(self) -> bool:
        return self._available

    def process_image(self, image_bytes: bytes) -> Tuple[str, float, str]:
        """
        Runs OCR on raw image bytes.
        Returns: (extracted_text, confidence_score_0_to_1, status_code)
        status_code: 'ocr_success', 'ocr_empty', 'ocr_unavailable', or 'ocr_failed'
        """
        if not self._available:
            return "", 0.0, "ocr_unavailable"

        try:
            import pytesseract
            img = Image.open(io.BytesIO(image_bytes))

            # Get detailed OCR data for confidence score calculation
            data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
            n_boxes = len(data["text"])
            valid_confs = []
            words = []

            for i in range(n_boxes):
                text = data["text"][i].strip()
                conf = float(data["conf"][i])
                if text and conf >= 0:
                    words.append(text)
                    valid_confs.append(conf)

            full_text = " ".join(words)
            if not full_text:
                return "", 0.0, "ocr_empty"

            avg_conf = (sum(valid_confs) / len(valid_confs)) / 100.0 if valid_confs else 0.0
            return full_text, round(avg_conf, 3), "ocr_success"

        except Exception as e:
            logger.error(f"OCR processing error: {e}")
            return "", 0.0, "ocr_failed"
