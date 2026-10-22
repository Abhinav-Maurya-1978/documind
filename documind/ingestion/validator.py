import os
import uuid
from pathlib import Path
from werkzeug.utils import secure_filename

class ValidationError(Exception):
    """Custom exception raised for invalid document uploads."""
    pass

class DocumentValidator:
    """Security and format validator for incoming documents."""

    PDF_MAGIC_BYTES = b"%PDF-"
    DEFAULT_MAX_FILE_SIZE = 32 * 1024 * 1024  # 32 MB
    DEFAULT_MAX_PAGES = 50

    def __init__(self, upload_folder: str, max_file_size: int = DEFAULT_MAX_FILE_SIZE, max_pages: int = DEFAULT_MAX_PAGES):
        self.upload_folder = Path(upload_folder)
        self.upload_folder.mkdir(parents=True, exist_ok=True)
        self.max_file_size = max_file_size
        self.max_pages = max_pages

    def validate_file_metadata(self, filename: str, content_length: int = None) -> str:
        """Validates extension and basic metadata. Returns cleaned original filename."""
        if not filename or filename.strip() == "":
            raise ValidationError("File has no name.")

        safe_name = secure_filename(filename)
        if not safe_name:
            safe_name = f"document_{uuid.uuid4().hex[:8]}.pdf"

        ext = Path(safe_name).suffix.lower()
        if ext != ".pdf":
            raise ValidationError(f"Invalid file extension '{ext}'. Only standard PDF files are supported.")

        if content_length and content_length > self.max_file_size:
            raise ValidationError(
                f"File '{filename}' exceeds maximum allowed size of {self.max_file_size // (1024 * 1024)} MB."
            )

        return safe_name

    def validate_and_save_stream(self, file_stream, original_filename: str) -> tuple[Path, str]:
        """
        Validates PDF magic bytes, file size, saves to a secure isolated server-generated filename,
        and returns (saved_path, safe_display_name).
        """
        display_name = self.validate_file_metadata(original_filename)

        # Read beginning to verify magic header
        header = file_stream.read(1024)
        if not header:
            raise ValidationError(f"File '{display_name}' is empty.")

        if not header.startswith(self.PDF_MAGIC_BYTES):
            # Check if %PDF- is within first 1024 bytes (some PDF generators have leading BOM or newlines)
            if self.PDF_MAGIC_BYTES not in header[:1024]:
                raise ValidationError(f"File '{display_name}' does not appear to be a valid PDF (invalid magic header).")

        # Generate unique server filename to prevent path traversal or collision
        unique_name = f"{uuid.uuid4().hex}_{display_name}"
        target_path = self.upload_folder / unique_name

        # Write out with size tracking to enforce limit during write
        total_size = len(header)
        with open(target_path, "wb") as f:
            f.write(header)
            while chunk := file_stream.read(65536):
                total_size += len(chunk)
                if total_size > self.max_file_size:
                    f.close()
                    if target_path.exists():
                        target_path.unlink()
                    raise ValidationError(
                        f"File '{display_name}' exceeds size limit of {self.max_file_size // (1024 * 1024)} MB."
                    )
                f.write(chunk)

        return target_path, display_name
