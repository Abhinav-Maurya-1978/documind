from pathlib import Path
from documind.ingestion.pdf_processor import PDFProcessor
from documind.extraction.claim_extractor import ClaimExtractor
from documind.matching.matcher import ClaimMatcher
from documind.detection.contradiction_engine import ContradictionEngine
from documind.evidence.verifier import EvidenceVerifier
from documind.extraction.models import FindingStatus

def test_full_cross_document_pipeline():
    fixtures_dir = Path(__file__).resolve().parent.parent / "fixtures"
    po_path = fixtures_dir / "PO_101.pdf"
    inv_path = fixtures_dir / "INV_101.pdf"

    assert po_path.exists()
    assert inv_path.exists()

    proc = PDFProcessor()
    doc_po = proc.process_pdf(str(po_path), "PO_101.pdf", "doc_po")
    doc_inv = proc.process_pdf(str(inv_path), "INV_101.pdf", "doc_inv")

    assert doc_po.total_pages == 1
    assert doc_inv.total_pages == 1
    assert len(doc_po.pages[0].text) > 50

    extractor = ClaimExtractor()
    claims_po = extractor.extract_document_claims(doc_po)
    claims_inv = extractor.extract_document_claims(doc_inv)

    assert len(claims_po) > 0
    assert len(claims_inv) > 0

    all_claims = claims_po + claims_inv
    matcher = ClaimMatcher()
    pairs = matcher.match_claims(all_claims, ["PO_101.pdf", "INV_101.pdf"])
    assert len(pairs) > 0

    engine = ContradictionEngine()
    findings = engine.analyze_pairs(pairs)

    verifier = EvidenceVerifier()
    verified = verifier.verify_findings(findings, {"PO_101.pdf": doc_po, "INV_101.pdf": doc_inv})

    contradictions = [f for f in verified if f.status == FindingStatus.CONTRADICTION]
    assert len(contradictions) >= 2  # Monetary discrepancy (Rs 50k vs 55k) and Deadline (30 vs 45 days)

    # Every contradiction must have verified evidence
    for c in contradictions:
        assert c.evidence_verified is True
        for cl in c.claims:
            assert cl.evidence != ""
            assert cl.page_number >= 1
