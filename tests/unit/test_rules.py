from documind.detection.rules import ContradictionRules
from documind.extraction.models import ExtractedClaim, FindingStatus, ValueType, ReviewStatus

def make_claim(attr, orig_val, norm_val, val_type, unit=None, doc="doc1.pdf", page=1, review=ReviewStatus.EXTRACTED):
    return ExtractedClaim(
        claim_id="c1",
        entity="Order PO-1",
        attribute=attr,
        original_value=orig_val,
        normalized_value=norm_val,
        value_type=val_type,
        unit=unit,
        source_document=doc,
        page_number=page,
        evidence=f"Evidence text for {orig_val}",
        review_status=review,
    )

def test_monetary_contradiction():
    c1 = make_claim("total_amount", "Rs. 50,000", 50000.0, ValueType.MONETARY, "INR", doc="PO.pdf")
    c2 = make_claim("total_amount", "Rs. 55,000", 55000.0, ValueType.MONETARY, "INR", doc="INV.pdf")

    res = ContradictionRules.evaluate_pair(c1, c2, "exact_attribute")
    assert res.status == FindingStatus.CONTRADICTION
    assert res.requires_human_review is True

def test_monetary_consistent():
    c1 = make_claim("total_amount", "$ 1,000", 1000.0, ValueType.MONETARY, "USD", doc="PO.pdf")
    c2 = make_claim("total_amount", "$ 1,000.00", 1000.0, ValueType.MONETARY, "USD", doc="INV.pdf")

    res = ContradictionRules.evaluate_pair(c1, c2, "exact_attribute")
    assert res.status == FindingStatus.CONSISTENT
    assert res.requires_human_review is False

def test_currency_mismatch_uncertain():
    c1 = make_claim("total_amount", "$ 500", 500.0, ValueType.MONETARY, "USD", doc="PO.pdf")
    c2 = make_claim("total_amount", "Rs. 500", 500.0, ValueType.MONETARY, "INR", doc="INV.pdf")

    res = ContradictionRules.evaluate_pair(c1, c2, "exact_attribute")
    assert res.status == FindingStatus.UNCERTAIN
    assert "Different currencies" in res.explanation

def test_ambiguous_date_flagged_uncertain():
    c1 = make_claim("order_date", "01/02/2026", "2026-02-01", ValueType.DATE, review=ReviewStatus.REQUIRES_REVIEW)
    c2 = make_claim("order_date", "02/01/2026", "2026-01-02", ValueType.DATE)

    res = ContradictionRules.evaluate_pair(c1, c2, "exact_attribute")
    assert res.status == FindingStatus.UNCERTAIN
    assert res.details.get("ambiguity_flag") is True

def test_missing_info_not_contradiction():
    c1 = make_claim("tax_identifier", "GSTIN123", "GSTIN123", ValueType.TAX_ID, doc="PO.pdf")
    c2 = make_claim("tax_identifier", "[NOT SPECIFIED]", None, ValueType.TAX_ID, doc="INV.pdf")

    res = ContradictionRules.evaluate_pair(c1, c2, "missing_attribute")
    assert res.status == FindingStatus.MISSING_INFO
