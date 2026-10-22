import logging
import os
import sys
import uuid
from pathlib import Path
from flask import Flask, jsonify, redirect, render_template, request, url_for
from werkzeug.exceptions import RequestEntityTooLarge

from config import Config
from documind.ingestion import DocumentValidator, OCREngine, PDFProcessor, ValidationError
from documind.extraction import ClaimExtractor
from documind.matching import ClaimMatcher
from documind.detection import ContradictionEngine
from documind.evidence import EvidenceVerifier
from documind.storage import Database

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("documind")

def create_app(config_class=Config) -> Flask:
    """Application factory."""
    app = Flask(__name__)
    app.config.from_object(config_class)
    config_class.init_app()

    # Initialize core services
    ocr_engine = OCREngine(
        tesseract_cmd=app.config["TESSERACT_CMD"],
        enabled=app.config["ENABLE_OCR"]
    )
    pdf_processor = PDFProcessor(
        ocr_engine=ocr_engine,
        max_pages=app.config["MAX_PAGES_PER_DOC"]
    )
    validator = DocumentValidator(
        upload_folder=app.config["UPLOAD_FOLDER"],
        max_file_size=app.config["MAX_CONTENT_LENGTH"],
        max_pages=app.config["MAX_PAGES_PER_DOC"],
    )
    claim_extractor = ClaimExtractor(
        llm_config={
            "provider": app.config["LLM_PROVIDER"],
            "api_key": app.config["LLM_API_KEY"],
            "model": app.config["LLM_MODEL"],
        }
    )
    claim_matcher = ClaimMatcher()
    contradiction_engine = ContradictionEngine()
    evidence_verifier = EvidenceVerifier()
    db = Database(db_url=app.config["DATABASE_URL"])

    @app.route("/")
    def index():
        """Main dashboard."""
        stats = db.get_global_stats()
        recent_audits = db.list_audits(limit=5)
        return render_template(
            "index.html",
            stats=stats,
            recent_audits=recent_audits,
            ocr_available=ocr_engine.is_available,
        )

    @app.route("/health")
    def health():
        """Health check endpoint for Render and monitoring."""
        return jsonify({
            "status": "healthy",
            "service": "DocuMind",
            "version": "1.0.0",
            "ocr_enabled": app.config["ENABLE_OCR"],
            "ocr_available": ocr_engine.is_available,
            "database": "connected",
        }), 200

    @app.route("/api/audit", methods=["POST"])
    def run_audit():
        """Main endpoint for document uploading and cross-document contradiction auditing."""
        if "documents" not in request.files:
            return jsonify({"error": "No document files provided. Please select at least two PDF documents."}), 400

        files = request.files.getlist("documents")
        valid_files = [f for f in files if f.filename and f.filename.strip()]

        if len(valid_files) < 2:
            return jsonify({
                "error": "Cross-document contradiction auditing requires at least two (2) PDF documents to compare."
            }), 400

        if len(valid_files) > app.config["MAX_DOCUMENTS_PER_AUDIT"]:
            return jsonify({
                "error": f"Maximum of {app.config['MAX_DOCUMENTS_PER_AUDIT']} documents can be audited in a single session."
            }), 400

        session_id = f"aud_{uuid.uuid4().hex[:12]}"
        saved_paths = []
        processed_docs = {}
        all_claims = []
        doc_metadata = []
        session_warnings = []

        try:
            # Step 1 & 2: Ingest, validate, and extract text page-by-page
            for file_item in valid_files:
                original_filename = file_item.filename
                try:
                    saved_path, display_name = validator.validate_and_save_stream(
                        file_item.stream,
                        original_filename
                    )
                    saved_paths.append(saved_path)

                    doc_id = f"doc_{uuid.uuid4().hex[:8]}"
                    p_doc = pdf_processor.process_pdf(
                        file_path=str(saved_path),
                        display_name=display_name,
                        document_id=doc_id,
                    )
                    processed_docs[display_name] = p_doc
                    session_warnings.extend(p_doc.warnings)

                    doc_metadata.append({
                        "document_id": doc_id,
                        "display_name": display_name,
                        "total_pages": p_doc.total_pages,
                        "status": p_doc.status,
                        "warnings": p_doc.warnings,
                    })

                except ValidationError as ve:
                    return jsonify({"error": f"Validation error: {str(ve)}"}), 400
                except Exception as e:
                    logger.exception(f"Processing error for {original_filename}")
                    return jsonify({"error": f"Error processing '{original_filename}': {str(e)}"}), 500

            # Step 3: Extract structured claims
            for doc_name, p_doc in processed_docs.items():
                claims = claim_extractor.extract_document_claims(p_doc)
                all_claims.extend(claims)

            # Step 4: Candidate claim matching
            doc_names = list(processed_docs.keys())
            candidate_pairs = claim_matcher.match_claims(all_claims, doc_names)

            # Step 5: Contradiction & consistency classification
            findings = contradiction_engine.analyze_pairs(candidate_pairs)

            # Step 6: Grounding and evidence verification
            verified_findings = evidence_verifier.verify_findings(findings, processed_docs)

            # Step 7: Generate audit summary
            total_pages = sum(d.total_pages for d in processed_docs.values())
            summary = contradiction_engine.generate_summary(
                findings=verified_findings,
                total_docs=len(processed_docs),
                total_pages=total_pages,
                total_claims=len(all_claims),
                warnings=session_warnings,
            )

            # Step 8: Persist audit in database
            findings_dicts = [f.model_dump() for f in verified_findings]
            summary_dict = summary.model_dump()

            db.save_audit(
                session_id=session_id,
                summary=summary_dict,
                findings=findings_dicts,
                documents=doc_metadata,
                status="completed",
            )

            return jsonify({
                "success": True,
                "session_id": session_id,
                "redirect_url": url_for("view_audit", session_id=session_id),
                "summary": summary_dict,
                "findings": findings_dicts,
                "documents": doc_metadata,
            }), 200

        finally:
            # Step 9: Retention cleanup if configured
            if app.config["AUTO_CLEANUP_UPLOADS"]:
                for sp in saved_paths:
                    try:
                        if Path(sp).exists():
                            Path(sp).unlink()
                    except Exception as ce:
                        logger.warning(f"Failed to cleanup temp file {sp}: {ce}")

    @app.route("/audit/<session_id>")
    def view_audit(session_id: str):
        """Audit result view with interactive contradiction cards and evidence inspect."""
        audit_data = db.get_audit(session_id)
        if not audit_data:
            return render_template(
                "error.html",
                error_code=404,
                title="Audit Session Not Found",
                message=f"No audit session found with identifier '{session_id}'.",
            ), 404

        return render_template(
            "audit.html",
            session=audit_data,
            summary=audit_data["summary"],
            findings=audit_data["findings"],
            documents=audit_data["documents"],
        )

    @app.route("/api/audit/<session_id>")
    def get_audit_api(session_id: str):
        """API to fetch audit session JSON data."""
        audit_data = db.get_audit(session_id)
        if not audit_data:
            return jsonify({"error": "Audit session not found"}), 404
        return jsonify(audit_data), 200

    @app.route("/history")
    def history():
        """Audit history dashboard."""
        audits = db.list_audits(limit=100)
        return render_template("history.html", audits=audits)

    @app.route("/api/history")
    def get_history_api():
        """API to fetch recent audit history."""
        audits = db.list_audits(limit=100)
        return jsonify(audits), 200

    @app.route("/api/demo-samples")
    def get_demo_samples():
        """Returns base64 encoded synthetic test PDFs for one-click competition testing."""
        import base64
        fixtures_dir = Path(__file__).resolve().parent / "tests" / "fixtures"
        po_path = fixtures_dir / "PO_101.pdf"
        inv_path = fixtures_dir / "INV_101.pdf"

        # Generate on-the-fly if not found
        if not po_path.exists() or not inv_path.exists():
            from scripts.generate_test_documents import generate_all_fixtures
            generate_all_fixtures()

        with open(po_path, "rb") as f:
            po_b64 = base64.b64encode(f.read()).decode("utf-8")
        with open(inv_path, "rb") as f:
            inv_b64 = base64.b64encode(f.read()).decode("utf-8")

        return jsonify({
            "samples": [
                {"filename": "PO_101.pdf", "data": po_b64},
                {"filename": "INV_101.pdf", "data": inv_b64},
            ]
        })

    @app.errorhandler(RequestEntityTooLarge)
    def handle_file_too_large(e):
        return jsonify({
            "error": f"Upload payload exceeds maximum allowable size of {app.config['MAX_CONTENT_LENGTH'] // (1024 * 1024)} MB."
        }), 413

    @app.errorhandler(404)
    def handle_not_found(e):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Resource not found"}), 404
        return render_template(
            "error.html",
            error_code=404,
            title="Page Not Found",
            message="The requested page could not be located.",
        ), 404

    @app.errorhandler(500)
    def handle_internal_error(e):
        logger.exception("Internal application error")
        if request.path.startswith("/api/"):
            return jsonify({"error": "An internal server error occurred while processing your request."}), 500
        return render_template(
            "error.html",
            error_code=500,
            title="Internal Server Error",
            message="An unexpected server error occurred. Please try again or check document formats.",
        ), 500

    return app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
