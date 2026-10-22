from dataclasses import dataclass
from typing import List, Optional
try:
    from rapidfuzz import fuzz
except ImportError:
    # Graceful fallback if rapidfuzz is still installing
    class fuzz:
        @staticmethod
        def token_sort_ratio(s1: str, s2: str) -> float:
            s1_words = set(s1.lower().split())
            s2_words = set(s2.lower().split())
            if not s1_words or not s2_words:
                return 0.0
            return (len(s1_words & s2_words) / len(s1_words | s2_words)) * 100.0

from ..extraction.models import ExtractedClaim, ValueType

@dataclass
class ClaimPair:
    claim_a: ExtractedClaim
    claim_b: ExtractedClaim
    match_type: str  # 'exact_attribute', 'fuzzy_line_item', 'identifier_linked', 'semantic'
    similarity_score: float

class CandidateFinder:
    """Finds candidate pairs of claims referring to the same topic across different documents."""

    def __init__(self, min_similarity_threshold: float = 0.65):
        self.min_similarity_threshold = min_similarity_threshold

    def find_candidate_pairs(self, claims: List[ExtractedClaim]) -> List[ClaimPair]:
        pairs: List[ClaimPair] = []
        n = len(claims)

        for i in range(n):
            for j in range(i + 1, n):
                c1 = claims[i]
                c2 = claims[j]

                # We primarily compare claims across DIFFERENT documents
                if c1.source_document == c2.source_document:
                    continue

                pair = self._evaluate_candidate_pair(c1, c2)
                if pair:
                    pairs.append(pair)

        return pairs

    def _evaluate_candidate_pair(self, c1: ExtractedClaim, c2: ExtractedClaim) -> Optional[ClaimPair]:
        # 1. Exact attribute match (e.g., both are 'total_amount', 'order_date', 'delivery_deadline')
        if c1.attribute == c2.attribute and not c1.attribute.startswith("line_item_qty:"):
            return ClaimPair(
                claim_a=c1,
                claim_b=c2,
                match_type="exact_attribute",
                similarity_score=1.0,
            )

        # 2. Line item quantity comparison:
        # Check if they are both line_item_qty, and compare their item descriptions!
        if c1.attribute.startswith("line_item_qty:") and c2.attribute.startswith("line_item_qty:"):
            desc1 = c1.line_item or c1.attribute.split(":", 1)[1]
            desc2 = c2.line_item or c2.attribute.split(":", 1)[1]

            score = fuzz.token_sort_ratio(desc1.lower(), desc2.lower()) / 100.0
            if score >= self.min_similarity_threshold:
                return ClaimPair(
                    claim_a=c1,
                    claim_b=c2,
                    match_type="fuzzy_line_item",
                    similarity_score=score,
                )
            else:
                # Crucial requirement: DIFFERENT line items (e.g. 10 laptops vs 20 monitors)
                # must NOT be paired as conflicting claims!
                return None

        # 3. Compatible deadline/terms attributes
        deadline_attrs = {"delivery_deadline", "delivery_date"}
        if c1.attribute in deadline_attrs and c2.attribute in deadline_attrs:
            return ClaimPair(
                claim_a=c1,
                claim_b=c2,
                match_type="semantic",
                similarity_score=0.85,
            )

        date_attrs = {"order_date", "invoice_date", "agreement_date", "effective_date"}
        if c1.attribute in date_attrs and c2.attribute in date_attrs and c1.attribute != c2.attribute:
            return ClaimPair(
                claim_a=c1,
                claim_b=c2,
                match_type="semantic_date",
                similarity_score=0.85,
            )

        payment_attrs = {"payment_terms", "due_date"}
        if c1.attribute in payment_attrs and c2.attribute in payment_attrs:
            return ClaimPair(
                claim_a=c1,
                claim_b=c2,
                match_type="semantic",
                similarity_score=0.80,
            )

        # 4. Same Value Type with high text similarity in evidence
        if c1.value_type == c2.value_type and c1.value_type in (ValueType.IDENTIFIER, ValueType.TAX_ID):
            if c1.attribute == c2.attribute:
                return ClaimPair(
                    claim_a=c1,
                    claim_b=c2,
                    match_type="identifier_linked",
                    similarity_score=0.90,
                )

        return None
