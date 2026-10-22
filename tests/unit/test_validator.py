import io
import pytest
from pathlib import Path
from documind.ingestion.validator import DocumentValidator, ValidationError

def test_valid_pdf_stream(tmp_path):
    validator = DocumentValidator(upload_folder=str(tmp_path))
    # Fake minimal valid PDF
    pdf_bytes = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
    stream = io.BytesIO(pdf_bytes)

    saved_path, display_name = validator.validate_and_save_stream(stream, "sample_contract.pdf")
    assert Path(saved_path).exists()
    assert display_name == "sample_contract.pdf"
    assert saved_path.suffix == ".pdf"

def test_invalid_extension(tmp_path):
    validator = DocumentValidator(upload_folder=str(tmp_path))
    stream = io.BytesIO(b"%PDF-1.4 content")
    with pytest.raises(ValidationError) as exc:
        validator.validate_and_save_stream(stream, "malicious_script.exe")
    assert "Invalid file extension" in str(exc.value)

def test_invalid_magic_bytes(tmp_path):
    validator = DocumentValidator(upload_folder=str(tmp_path))
    # Text file disguised as PDF
    stream = io.BytesIO(b"Hello world, I am not a real PDF file!")
    with pytest.raises(ValidationError) as exc:
        validator.validate_and_save_stream(stream, "fake.pdf")
    assert "invalid magic header" in str(exc.value)

def test_empty_file_rejected(tmp_path):
    validator = DocumentValidator(upload_folder=str(tmp_path))
    stream = io.BytesIO(b"")
    with pytest.raises(ValidationError) as exc:
        validator.validate_and_save_stream(stream, "empty.pdf")
    assert "is empty" in str(exc.value)

def test_oversized_file_rejected(tmp_path):
    # Set limit to 1 KB
    validator = DocumentValidator(upload_folder=str(tmp_path), max_file_size=1024)
    oversized = b"%PDF-1.4\n" + b"X" * 2000
    stream = io.BytesIO(oversized)
    with pytest.raises(ValidationError) as exc:
        validator.validate_and_save_stream(stream, "large.pdf")
    assert "exceeds" in str(exc.value)
