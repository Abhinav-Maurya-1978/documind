import re
from typing import Dict, List
try:
    from rapidfuzz import fuzz
except ImportError:
    class fuzz:
        @staticmethod
        def partial_ratio(s1: str, s2: str) -> float:
            return 100.0 if s1.lower() in s2.lower() else 50.0

from ..extraction.models import ComparisonFinding, FindingSeverity, FindingStatus, ReviewStatus
from ..ingestion.pdf_processor import ProcessedDocument

class EvidenceVerifier:
    """
    Verifies every cited quotation against original extracted page text.
    Rejects or flags unsupported claims and fabricated page references.
    """

    def __init__(self, fuzzy_threshold: float = 80.0):
        self.fuzzy_threshold = fuzzy_threshold

    def verify_findings(
        self,
        findings: List[ComparisonFinding],
        documents: Dict[str, ProcessedDocument]
    ) -> List[ComparisonFinding]:
        verified_findings: List[ComparisonFinding] = []

        for finding in findings:
            all_claims_verified = True

            for claim in finding.claims:
                # Missing information claim has no text to ground
                if claim.normalized_value is None or "[NOT SPECIFIED]" in claim.original_value:
                    continue

                is_grounded, match_method = self._verify_claim_evidence(claim, documents)

                if is_grounded:
                    claim.review_status = ReviewStatus.VERIFIED
                else:
                    claim.review_status = ReviewStatus.UNVERIFIED
                    all_claims_verified = False

            if all_claims_verified:
                finding.evidence_verified = True
            else:
                finding.evidence_verified = False
                # If a contradiction cannot be verified in the actual page text,
                # safeguard against hallucination: downgrade to UNCERTAIN
                if finding.status == FindingStatus.CONTRADICTION:
                    finding.status = FindingStatus.UNCERTAIN
                    finding.severity = FindingSeverity.MEDIUM
                    finding.explanation += (
                        " [GROUNDING WARNING: One or more evidence citations could not be verified "
                        "in the original page text. Flagged for human review.]"
                    )

            verified_findings.append(finding)

        return verified_findings

    def _verify_claim_evidence(
        self,
        claim,
        documents: Dict[str, ProcessedDocument]
    ) -> tuple[bool, str]:
        doc = documents.get(claim.source_document)
        if not doc:
            return False, "document_not_found"

        # 1-based page lookup
        target_page = None
        for page in doc.pages:
            if page.page_number == claim.page_number:
                target_page = page
                break

        if not target_page or not target_page.text:
            return False, "page_not_found_or_empty"

        page_text = target_page.text
        evidence = claim.evidence.strip()

        # 1. Exact substring check (normalized spaces)
        norm_page = re.sub(r"\s+", " ", page_text.lower())
        norm_ev = re.sub(r"\s+", " ", evidence.lower())
        if norm_ev in norm_page:
            return True, "exact_match"

        # 2. Check original_value match inside page
        norm_orig = re.sub(r"\s+", " ", str(claim.original_value).lower())
        if norm_orig in norm_page:
            return True, "value_match"

        # 3. Fuzzy partial ratio match for OCR imperfections or line breaks
        similarity = fuzz.partial_ratio(norm_ev, norm_page)
        if similarity >= self.fuzzy_threshold:
            return True, f"fuzzy_match_{similarity:.1f}"

        return False, "unverified"
