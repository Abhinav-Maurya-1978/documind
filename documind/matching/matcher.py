from typing import Dict, List, Set
from .candidate_finder import CandidateFinder, ClaimPair
from ..extraction.models import ExtractedClaim, ValueType

class ClaimMatcher:
    """Orchestrates candidate pairing and identifies expected missing attributes."""

    def __init__(self, candidate_finder: CandidateFinder = None):
        self.candidate_finder = candidate_finder or CandidateFinder()

    def match_claims(self, claims: List[ExtractedClaim], documents: List[str]) -> List[ClaimPair]:
        # 1. Find matched candidate pairs
        pairs = self.candidate_finder.find_candidate_pairs(claims)

        # 2. Check for missing information across document pairs
        missing_pairs = self._detect_missing_claims(claims, documents)
        pairs.extend(missing_pairs)

        return pairs

    def _detect_missing_claims(self, claims: List[ExtractedClaim], documents: List[str]) -> List[ClaimPair]:
        """
        Detects attributes present in one document but absent in another (e.g. tax identifier, PO number).
        Generates pairs with a synthetic 'missing' claim to represent the absence.
        """
        if len(documents) < 2:
            return []

        # Map doc -> set of attributes present
        doc_attrs: Dict[str, Set[str]] = {d: set() for d in documents}
        doc_claims_by_attr: Dict[str, Dict[str, ExtractedClaim]] = {d: {} for d in documents}

        # Key attributes we care about for cross-document completeness
        CRITICAL_ATTRIBUTES = {"tax_identifier", "delivery_deadline", "payment_terms", "total_amount"}

        for c in claims:
            if c.source_document in doc_attrs:
                doc_attrs[c.source_document].add(c.attribute)
                doc_claims_by_attr[c.source_document][c.attribute] = c

        missing_pairs: List[ClaimPair] = []

        for i in range(len(documents)):
            for j in range(i + 1, len(documents)):
                doc_a = documents[i]
                doc_b = documents[j]

                # If doc_a has critical attribute but doc_b does not
                for attr in CRITICAL_ATTRIBUTES:
                    if attr in doc_attrs[doc_a] and attr not in doc_attrs[doc_b]:
                        c_a = doc_claims_by_attr[doc_a][attr]
                        # Create representation of missing claim
                        c_b_missing = ExtractedClaim(
                            claim_id="missing_" + c_a.claim_id,
                            entity=doc_b,
                            attribute=attr,
                            original_value="[NOT SPECIFIED]",
                            normalized_value=None,
                            value_type=c_a.value_type,
                            source_document=doc_b,
                            page_number=1,
                            evidence="Attribute not found anywhere in document.",
                            confidence=1.0,
                        )
                        missing_pairs.append(
                            ClaimPair(
                                claim_a=c_a,
                                claim_b=c_b_missing,
                                match_type="missing_attribute",
                                similarity_score=0.5,
                            )
                        )

        return missing_pairs
