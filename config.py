import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

class Config:
    """Base application configuration."""
    SECRET_KEY = os.environ.get("SECRET_KEY", secrets.token_hex(32))
    FLASK_ENV = os.environ.get("FLASK_ENV", "production")
    DEBUG = os.environ.get("FLASK_DEBUG", "0") in ("1", "true", "True")

    # Storage paths
    INSTANCE_DIR = BASE_DIR / "instance"
    UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", str(BASE_DIR / "uploads"))
    DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{INSTANCE_DIR}/documind.db")

    # Resource & Security Limits
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH", 32 * 1024 * 1024))  # 32 MB
    MAX_PAGES_PER_DOC = int(os.environ.get("MAX_PAGES_PER_DOC", 50))
    MAX_DOCUMENTS_PER_AUDIT = int(os.environ.get("MAX_DOCUMENTS_PER_AUDIT", 10))
    ALLOWED_EXTENSIONS = {"pdf"}

    # OCR Configuration
    ENABLE_OCR = os.environ.get("ENABLE_OCR", "true").lower() in ("1", "true", "yes")
    TESSERACT_CMD = os.environ.get("TESSERACT_CMD", "tesseract")

    # Retention Policy
    AUTO_CLEANUP_UPLOADS = os.environ.get("AUTO_CLEANUP_UPLOADS", "true").lower() in ("1", "true", "yes")

    # Optional LLM Enhancement & Fact Checker Configuration
    LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "gemini").lower()
    LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
    LLM_MODEL = os.environ.get("LLM_MODEL", "")

    # Gemini & Fact-Checking Providers (Free Tier APIs)
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
    GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
    FACTCHECK_API_KEY = os.environ.get("FACTCHECK_API_KEY", "")
    TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")
    FACTCHECK_MAX_CLAIMS = int(os.environ.get("FACTCHECK_MAX_CLAIMS", 12))

    @classmethod
    def init_app(cls):
        """Ensure necessary directories exist."""
        cls.INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
        Path(cls.UPLOAD_FOLDER).mkdir(parents=True, exist_ok=True)
