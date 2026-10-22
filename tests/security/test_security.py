import io
import pytest
from documind.ingestion.validator import DocumentValidator, ValidationError

def test_path_traversal_sanitization(tmp_path):
    validator = DocumentValidator(upload_folder=str(tmp_path))
    stream = io.BytesIO(b"%PDF-1.4\nvalid pdf body")

    # Attacker attempts directory traversal filename
    malicious_filename = "../../../../../etc/passwd.pdf"
    saved_path, display_name = validator.validate_and_save_stream(stream, malicious_filename)

    # Saved path must reside strictly inside tmp_path
    assert tmp_path in saved_path.parents
    assert ".." not in str(saved_path)
    assert not display_name.startswith("..")

def test_non_pdf_file_execution_prevention(tmp_path):
    validator = DocumentValidator(upload_folder=str(tmp_path))
    # Python script pretending to be pdf
    stream = io.BytesIO(b"import os; os.system('echo hacked')")
    with pytest.raises(ValidationError):
        validator.validate_and_save_stream(stream, "exploit.pdf")

def test_null_byte_injection(tmp_path):
    validator = DocumentValidator(upload_folder=str(tmp_path))
    stream = io.BytesIO(b"%PDF-1.4\nvalid")
    malicious_name = "legit.pdf\x00.exe"
    # werkzeug secure_filename or validator should reject or strip null byte safely
    with pytest.raises(ValidationError) as exc:
        validator.validate_and_save_stream(stream, malicious_name)
    assert "Invalid file extension" in str(exc.value) or "invalid" in str(exc.value).lower()
