from documind.evidence.verifier import EvidenceVerifier
from documind.extraction.models import ComparisonFinding, ExtractedClaim, FindingSeverity, FindingStatus, ReviewStatus, ValueType
from documind.ingestion.pdf_processor import ProcessedDocument, ProcessedPage

def test_grounded_evidence_verification():
    verifier = EvidenceVerifier()

    p_doc = ProcessedDocument(
        document_id="d1",
        display_name="PO_sample.pdf",
        file_path="dummy.pdf",
        total_pages=1,
        pages=[ProcessedPage(page_number=1, text="Total Amount payable is Rs. 50,000 only.", extraction_method="text")],
    )

    claim = ExtractedClaim(
        claim_id="c1",
        entity="Order",
        attribute="total_amount",
        original_value="Rs. 50,000",
        normalized_value=50000.0,
        value_type=ValueType.MONETARY,
        source_document="PO_sample.pdf",
        page_number=1,
        evidence="Total Amount payable is Rs. 50,000 only.",
    )

    finding = ComparisonFinding(
        finding_id="f1",
        status=FindingStatus.CONTRADICTION,
        severity=FindingSeverity.HIGH,
        attribute="total_amount",
        topic="Total Amount",
        explanation="Contradiction",
        claims=[claim],
    )

    verified = verifier.verify_findings([finding], {"PO_sample.pdf": p_doc})
    assert verified[0].evidence_verified is True
    assert claim.review_status == ReviewStatus.VERIFIED

def test_unverified_hallucination_rejected():
    verifier = EvidenceVerifier()

    p_doc = ProcessedDocument(
        document_id="d1",
        display_name="PO_sample.pdf",
        file_path="dummy.pdf",
        total_pages=1,
        pages=[ProcessedPage(page_number=1, text="This document contains no financial terms.", extraction_method="text")],
    )

    claim = ExtractedClaim(
        claim_id="c1",
        entity="Order",
        attribute="total_amount",
        original_value="Rs. 99,999",
        normalized_value=99999.0,
        value_type=ValueType.MONETARY,
        source_document="PO_sample.pdf",
        page_number=1,
        evidence="A totally fabricated quote that does not exist on page 1.",
    )

    finding = ComparisonFinding(
        finding_id="f1",
        status=FindingStatus.CONTRADICTION,
        severity=FindingSeverity.HIGH,
        attribute="total_amount",
        topic="Total Amount",
        explanation="Contradiction",
        claims=[claim],
    )

    verified = verifier.verify_findings([finding], {"PO_sample.pdf": p_doc})
    assert verified[0].evidence_verified is False
    assert verified[0].status == FindingStatus.UNCERTAIN  # Safeguarded against hallucination
    assert claim.review_status == ReviewStatus.UNVERIFIED
