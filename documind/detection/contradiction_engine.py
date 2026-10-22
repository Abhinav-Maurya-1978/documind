import uuid
from typing import List, Tuple
from .rules import ContradictionRules
from ..matching.candidate_finder import ClaimPair
from ..extraction.models import AuditSummary, ComparisonFinding, FindingStatus

class ContradictionEngine:
    """Classifies matched claim comparisons into actionable audit findings."""

    def __init__(self):
        self.rules = ContradictionRules()

    def analyze_pairs(self, pairs: List[ClaimPair]) -> List[ComparisonFinding]:
        findings: List[ComparisonFinding] = []

        for pair in pairs:
            c1 = pair.claim_a
            c2 = pair.claim_b

            rule_res = self.rules.evaluate_pair(c1, c2, match_type=pair.match_type)

            topic = f"{c1.attribute.replace('_', ' ').title()}: {c1.source_document} vs {c2.source_document}"
            finding = ComparisonFinding(
                finding_id=f"find_{uuid.uuid4().hex[:8]}",
                status=rule_res.status,
                severity=rule_res.severity,
                attribute=c1.attribute,
                topic=topic,
                explanation=rule_res.explanation,
                claims=[c1, c2],
                discrepancy_details=rule_res.details,
                requires_human_review=rule_res.requires_human_review,
                confidence=rule_res.confidence,
                evidence_verified=False,  # Updated during evidence verification milestone
            )
            findings.append(finding)

        return findings

    def generate_summary(
        self,
        findings: List[ComparisonFinding],
        total_docs: int,
        total_pages: int,
        total_claims: int,
        warnings: List[str] = None
    ) -> AuditSummary:
        warnings = warnings or []
        contradictions = sum(1 for f in findings if f.status == FindingStatus.CONTRADICTION)
        consistent = sum(1 for f in findings if f.status == FindingStatus.CONSISTENT)
        missing_info = sum(1 for f in findings if f.status == FindingStatus.MISSING_INFO)
        uncertain = sum(1 for f in findings if f.status == FindingStatus.UNCERTAIN)

        return AuditSummary(
            total_documents=total_docs,
            total_pages=total_pages,
            total_claims_extracted=total_claims,
            total_comparisons=len(findings),
            contradictions_count=contradictions,
            consistent_count=consistent,
            missing_info_count=missing_info,
            uncertain_count=uncertain,
            has_warnings=len(warnings) > 0,
            warnings=warnings,
        )
