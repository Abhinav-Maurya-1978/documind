import io
import logging
import os
import time
from collections import defaultdict
from pathlib import Path
from flask import Blueprint, current_app, jsonify, render_template, request
from werkzeug.utils import secure_filename

from ..ingestion.validator import DocumentValidator, ValidationError
from ..ingestion.pdf_processor import PDFProcessor
from .claims import ClaimExtractorService
from .sources import SourceRetriever
from .judge import ClaimJudgeService

logger = logging.getLogger(__name__)

factcheck_bp = Blueprint("factcheck", __name__)

# Simple in-memory sliding window rate limiter per client IP
# Format: ip -> list of timestamps
_ip_request_history = defaultdict(list)
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX_REQUESTS = 35  # requests per minute per IP

def is_rate_limited(ip: str) -> bool:
    """Enforces simple per-IP sliding window rate limiting."""
    now = time.time()
    timestamps = _ip_request_history[ip]
    # Prune timestamps older than window
    _ip_request_history[ip] = [t for t in timestamps if now - t < RATE_LIMIT_WINDOW]
    if len(_ip_request_history[ip]) >= RATE_LIMIT_MAX_REQUESTS:
        return True
    _ip_request_history[ip].append(now)
    return False

@factcheck_bp.route("/factcheck")
def index():
    """Fact Checker page."""
    gemini_key = current_app.config.get("GEMINI_API_KEY", "").strip()
    factcheck_key = current_app.config.get("FACTCHECK_API_KEY", "").strip()
    tavily_key = current_app.config.get("TAVILY_API_KEY", "").strip()

    missing_keys = []
    if not gemini_key:
        missing_keys.append("GEMINI_API_KEY")
    if not factcheck_key:
        missing_keys.append("FACTCHECK_API_KEY (optional, for Google Fact Check Tools)")

    return render_template(
        "factcheck.html",
        missing_keys=missing_keys,
        has_gemini_key=bool(gemini_key),
        has_factcheck_key=bool(factcheck_key),
        has_tavily_key=bool(tavily_key),
        max_claims=current_app.config.get("FACTCHECK_MAX_CLAIMS", 12),
    )

@factcheck_bp.route("/api/factcheck/extract", methods=["POST"])
def extract_claims_endpoint():
    """Validates single PDF in-memory, extracts text, and returns checkable factual claims."""
    client_ip = request.remote_addr or "127.0.0.1"
    if is_rate_limited(client_ip):
        return jsonify({"error": "Rate limit exceeded. Please wait a minute before submitting further requests."}), 429

    # Check API key presence for extraction
    gemini_key = current_app.config.get("GEMINI_API_KEY", "").strip()
    if not gemini_key:
        return jsonify({
            "error": "GEMINI_API_KEY is not configured in the server environment. Please set GEMINI_API_KEY to enable factual claim extraction."
        }), 400

    # Ensure single file provided
    file_item = None
    if "document" in request.files:
        file_item = request.files["document"]
    elif "documents" in request.files:
        file_list = request.files.getlist("documents")
        if file_list:
            file_item = file_list[0]

    if not file_item or not file_item.filename or file_item.filename.strip() == "":
        return jsonify({"error": "No PDF document uploaded. Please select one PDF file."}), 400

    original_filename = file_item.filename

    # Reuse existing validator rules
    validator = DocumentValidator(
        upload_folder=current_app.config["UPLOAD_FOLDER"],
        max_file_size=current_app.config["MAX_CONTENT_LENGTH"],
        max_pages=current_app.config["MAX_PAGES_PER_DOC"]
    )

    saved_path = None
    try:
        # Validate magic header and file bounds
        saved_path, display_name = validator.validate_and_save_stream(
            file_item.stream,
            original_filename
        )

        # Reuse existing PDFProcessor
        pdf_processor = PDFProcessor(max_pages=current_app.config["MAX_PAGES_PER_DOC"])
        doc = pdf_processor.process_pdf(
            file_path=str(saved_path),
            display_name=display_name,
            document_id="factcheck_doc"
        )

        # Check if text exists
        if not doc.full_text.strip():
            return jsonify({
                "error": f"Document '{display_name}' contains no readable digital text. If this is a scanned document, OCR is required."
            }), 400

        # Extract claims using LLM and quote verification
        max_claims = current_app.config.get("FACTCHECK_MAX_CLAIMS", 12)
        claim_service = ClaimExtractorService(max_claims=max_claims)
        claims = claim_service.extract_claims(doc, config=current_app.config)

        if not claims:
            return jsonify({
                "error": "No verifiable factual claims (numbers, dates, entities, statistics) could be identified in this document."
            }), 400

        return jsonify({
            "success": True,
            "filename": display_name,
            "total_pages": doc.total_pages,
            "claims": claims,
        }), 200

    except ValidationError as ve:
        return jsonify({"error": f"Validation error: {str(ve)}"}), 400
    except RuntimeError as re_err:
        return jsonify({"error": str(re_err)}), 429 if "429" in str(re_err) else 500
    except Exception as e:
        logger.exception(f"Fact-check extraction failed for {original_filename}")
        return jsonify({"error": f"Error extracting claims: {str(e)}"}), 500
    finally:
        # Hard Rule: Discard immediately from disk. Do not store.
        if saved_path and Path(saved_path).exists():
            try:
                Path(saved_path).unlink()
            except Exception as ce:
                logger.warning(f"Failed to cleanup temp file {saved_path}: {ce}")

@factcheck_bp.route("/api/factcheck/verify", methods=["POST"])
def verify_claim_endpoint():
    """Stateless verification of ONE claim against free web sources."""
    client_ip = request.remote_addr or "127.0.0.1"
    if is_rate_limited(client_ip):
        return jsonify({"error": "Rate limit exceeded. Please wait a moment before verifying the next claim."}), 429

    data = request.get_json(silent=True) or {}
    claim_text = data.get("claim", "").strip()
    claim_id = data.get("id", "claim_1")
    page_number = data.get("page_number", 1)
    quote = data.get("quote", "")

    if not claim_text:
        return jsonify({"error": "Missing 'claim' in request payload."}), 400

    try:
        # 1. Retrieve evidence from free web sources
        retriever = SourceRetriever(
            factcheck_api_key=current_app.config.get("FACTCHECK_API_KEY"),
            tavily_api_key=current_app.config.get("TAVILY_API_KEY"),
        )
        evidence_items = retriever.retrieve_evidence(claim_text)

        # 2. Judge claim with LLM based strictly on retrieved snippets
        judge = ClaimJudgeService()
        result = judge.judge_claim(claim_text, evidence_items, config=current_app.config)

        return jsonify({
            "success": True,
            "id": claim_id,
            "claim": claim_text,
            "verdict": result["verdict"],
            "reason": result["reason"],
            "page_number": page_number,
            "quote": quote,
            "sources": result["sources"],
        }), 200

    except RuntimeError as re_err:
        return jsonify({"error": str(re_err)}), 429 if "429" in str(re_err) else 500
    except Exception as e:
        logger.exception(f"Fact-check verification failed for claim: {claim_text[:50]}")
        return jsonify({
            "success": True,
            "id": claim_id,
            "claim": claim_text,
            "verdict": "Unverifiable",
            "reason": f"Verification error: {str(e)}",
            "page_number": page_number,
            "quote": quote,
            "sources": [],
        }), 200
