from dataclasses import dataclass
from typing import Any, Dict, Optional
from ..extraction.models import ExtractedClaim, FindingSeverity, FindingStatus, ReviewStatus, ValueType

@dataclass
class ComparisonRuleResult:
    status: FindingStatus
    severity: FindingSeverity
    explanation: str
    requires_human_review: bool
    confidence: float
    details: Dict[str, Any]

class ContradictionRules:
    """Deterministic decision-support comparison rules."""

    @classmethod
    def evaluate_pair(cls, c1: ExtractedClaim, c2: ExtractedClaim, match_type: str) -> ComparisonRuleResult:
        # 1. Missing information check
        if c1.normalized_value is None or c2.normalized_value is None:
            return cls._evaluate_missing_info(c1, c2)

        # 1a. Timeline overlap comparison
        if c1.value_type == ValueType.TIMELINE and c2.value_type == ValueType.TIMELINE:
            return cls._evaluate_timeline_overlap(c1, c2)

        # 1b. Person and Entity Name comparison
        if c1.value_type == ValueType.PERSON_NAME or c2.value_type == ValueType.PERSON_NAME:
            return cls._evaluate_person_name(c1, c2)

        # 1c. Compensation comparison
        if c1.value_type == ValueType.COMPENSATION or c2.value_type == ValueType.COMPENSATION:
            return cls._evaluate_compensation(c1, c2)

        # 2. Monetary rules
        if c1.value_type == ValueType.MONETARY or c2.value_type == ValueType.MONETARY:
            return cls._evaluate_monetary(c1, c2)

        # 3. Date rules
        if c1.value_type == ValueType.DATE or c2.value_type == ValueType.DATE:
            return cls._evaluate_date(c1, c2)

        # 4. Quantity / Line items
        if c1.value_type == ValueType.QUANTITY or c2.value_type == ValueType.QUANTITY:
            return cls._evaluate_quantity(c1, c2)

        # 5. Deadlines & terms
        if c1.value_type in (ValueType.DEADLINE, ValueType.PAYMENT_TERM) or c2.value_type in (ValueType.DEADLINE, ValueType.PAYMENT_TERM):
            return cls._evaluate_deadline(c1, c2)

        # 6. Identifiers (PO numbers, Tax IDs)
        if c1.value_type in (ValueType.IDENTIFIER, ValueType.TAX_ID) or c2.value_type in (ValueType.IDENTIFIER, ValueType.TAX_ID):
            return cls._evaluate_identifier(c1, c2)

        # Default string/generic comparison
        if str(c1.normalized_value).strip().lower() == str(c2.normalized_value).strip().lower():
            return ComparisonRuleResult(
                status=FindingStatus.CONSISTENT,
                severity=FindingSeverity.INFO,
                explanation=f"Both documents align on '{c1.attribute}'.",
                requires_human_review=False,
                confidence=0.90,
                details={},
            )

        return ComparisonRuleResult(
            status=FindingStatus.CONTRADICTION,
            severity=FindingSeverity.MEDIUM,
            explanation=f"Potential discrepancy in '{c1.attribute}': '{c1.original_value}' vs '{c2.original_value}'.",
            requires_human_review=True,
            confidence=0.75,
            details={},
        )

    @classmethod
    def _evaluate_timeline_overlap(cls, c1: ExtractedClaim, c2: ExtractedClaim) -> ComparisonRuleResult:
        t1 = c1.normalized_value
        t2 = c2.normalized_value

        if not isinstance(t1, dict) or not isinstance(t2, dict):
            return ComparisonRuleResult(
                status=FindingStatus.CONSISTENT,
                severity=FindingSeverity.INFO,
                explanation="Timeline periods are consistent.",
                requires_human_review=False,
                confidence=0.85,
                details={},
            )

        s1_y, s1_m = t1.get("start_year"), t1.get("start_month", 1)
        e1_y, e1_m = t1.get("end_year"), t1.get("end_month", 12)
        s2_y, s2_m = t2.get("start_year"), t2.get("start_month", 1)
        e2_y, e2_m = t2.get("end_year"), t2.get("end_month", 12)

        if not (s1_y and e1_y and s2_y and e2_y):
            return ComparisonRuleResult(
                status=FindingStatus.CONSISTENT,
                severity=FindingSeverity.INFO,
                explanation="Timeline periods align.",
                requires_human_review=False,
                confidence=0.85,
                details={},
            )

        start1 = s1_y * 12 + s1_m
        end1 = e1_y * 12 + e1_m
        start2 = s2_y * 12 + s2_m
        end2 = e2_y * 12 + e2_m

        overlap_start = max(start1, start2)
        overlap_end = min(end1, end2)
        has_overlap = overlap_start <= overlap_end

        commit1 = t1.get("commitment", "unspecified")
        commit2 = t2.get("commitment", "unspecified")
        act1 = t1.get("activity_type")
        act2 = t2.get("activity_type")
        role1 = t1.get("role") or act1
        role2 = t2.get("role") or act2

        if has_overlap:
            overlap_months = (overlap_end - overlap_start) + 1
            is_dual_fulltime = (commit1 == "full-time" or "regular" in str(c1.original_value).lower()) and \
                               (commit2 == "full-time" or "regular" in str(c2.original_value).lower())

            is_edu_emp_conflict = (act1 == "education" and act2 == "employment") or (act1 == "employment" and act2 == "education")

            if is_dual_fulltime and is_edu_emp_conflict:
                emp_doc = c1.source_document if act1 == "employment" else c2.source_document
                emp_role = role1 if act1 == "employment" else role2
                emp_period = f"{s1_y}-{e1_y}" if act1 == "employment" else f"{s2_y}-{e2_y}"

                edu_doc = c2.source_document if act1 == "employment" else c1.source_document
                edu_role = role2 if act1 == "employment" else role1
                edu_period = f"{s2_y}-{e2_y}" if act1 == "employment" else f"{s1_y}-{e1_y}"

                return ComparisonRuleResult(
                    status=FindingStatus.CONTRADICTION,
                    severity=FindingSeverity.CRITICAL,
                    explanation=(
                        f"Mutually Exclusive Timeline Conflict: '{emp_doc}' claims candidate worked full-time as '{emp_role}' "
                        f"({emp_period}). Simultaneously, '{edu_doc}' asserts the candidate was enrolled as a regular full-time "
                        f"student ({edu_role}, {edu_period}), overlapping by {overlap_months} months. "
                        "Concurrent full-time corporate employment during regular full-time undergraduate university degree is physically and regulatory incompatible."
                    ),
                    requires_human_review=True,
                    confidence=0.98,
                    details={"overlap_months": overlap_months, "t1": c1.original_value, "t2": c2.original_value},
                )

            return ComparisonRuleResult(
                status=FindingStatus.UNCERTAIN,
                severity=FindingSeverity.MEDIUM,
                explanation=(
                    f"Timeline overlap detected ({overlap_months} months): '{c1.original_value}' overlaps with '{c2.original_value}'. "
                    "Requires human auditor review to confirm compatibility."
                ),
                requires_human_review=True,
                confidence=0.85,
                details={"overlap_months": overlap_months},
            )

        return ComparisonRuleResult(
            status=FindingStatus.CONSISTENT,
            severity=FindingSeverity.INFO,
            explanation=f"Sequential timeline: '{c1.original_value}' and '{c2.original_value}' occur in non-conflicting periods.",
            requires_human_review=False,
            confidence=0.92,
            details={},
        )

    @classmethod
    def _evaluate_person_name(cls, c1: ExtractedClaim, c2: ExtractedClaim) -> ComparisonRuleResult:
        n1 = str(c1.normalized_value).strip().lower()
        n2 = str(c2.normalized_value).strip().lower()

        if n1 == n2:
            return ComparisonRuleResult(
                status=FindingStatus.CONSISTENT,
                severity=FindingSeverity.INFO,
                explanation=f"Person names match: '{c1.original_value}' across both documents.",
                requires_human_review=False,
                confidence=0.98,
                details={"name": c1.original_value},
            )

        return ComparisonRuleResult(
            status=FindingStatus.CONTRADICTION,
            severity=FindingSeverity.CRITICAL,
            explanation=(
                f"Critical Identity Mismatch: '{c1.source_document}' specifies name '{c1.original_value}' "
                f"whereas '{c2.source_document}' specifies name '{c2.original_value}'. "
                "When associated with common identifiers (such as PAN or Aadhaar), this indicates potential identity theft or document falsification."
            ),
            requires_human_review=True,
            confidence=0.99,
            details={"name1": c1.original_value, "name2": c2.original_value},
        )

    @classmethod
    def _evaluate_compensation(cls, c1: ExtractedClaim, c2: ExtractedClaim) -> ComparisonRuleResult:
        v1 = float(c1.normalized_value)
        v2 = float(c2.normalized_value)
        curr = (c1.unit or "INR").upper()

        diff = abs(v1 - v2)
        if diff < 1.0:
            return ComparisonRuleResult(
                status=FindingStatus.CONSISTENT,
                severity=FindingSeverity.INFO,
                explanation=f"Annualized compensation figures match: {curr} {v1:,.2f}.",
                requires_human_review=False,
                confidence=0.95,
                details={"val1": v1, "val2": v2},
            )

        pct_diff = (diff / max(v1, v2)) * 100.0 if max(v1, v2) > 0 else 0.0
        return ComparisonRuleResult(
            status=FindingStatus.CONTRADICTION,
            severity=FindingSeverity.HIGH,
            explanation=(
                f"Compensation conflict: '{c1.source_document}' states {c1.original_value} ({curr} {v1:,.2f}/yr annualized) "
                f"whereas '{c2.source_document}' states {c2.original_value} ({curr} {v2:,.2f}/yr annualized). "
                f"Annual discrepancy: {curr} {diff:,.2f} ({pct_diff:.1f}% variance)."
            ),
            requires_human_review=True,
            confidence=0.95,
            details={"annual_val1": v1, "annual_val2": v2, "diff": diff},
        )

    @classmethod
    def _evaluate_missing_info(cls, c1: ExtractedClaim, c2: ExtractedClaim) -> ComparisonRuleResult:
        present = c1 if c1.normalized_value is not None else c2
        missing = c2 if c1.normalized_value is not None else c1

        return ComparisonRuleResult(
            status=FindingStatus.MISSING_INFO,
            severity=FindingSeverity.LOW,
            explanation=(
                f"Attribute '{present.attribute}' is specified in '{present.source_document}' "
                f"('{present.original_value}') but is absent in '{missing.source_document}'. "
                "This indicates missing information, not a direct contradiction."
            ),
            requires_human_review=True,
            confidence=0.95,
            details={"present_in": present.source_document, "absent_in": missing.source_document},
        )

    @classmethod
    def _evaluate_monetary(cls, c1: ExtractedClaim, c2: ExtractedClaim) -> ComparisonRuleResult:
        # Currency check
        curr1 = (c1.unit or "UNKNOWN").upper()
        curr2 = (c2.unit or "UNKNOWN").upper()

        if curr1 != "UNKNOWN" and curr2 != "UNKNOWN" and curr1 != curr2:
            return ComparisonRuleResult(
                status=FindingStatus.UNCERTAIN,
                severity=FindingSeverity.HIGH,
                explanation=(
                    f"Different currencies detected: '{c1.source_document}' specifies {curr1} {c1.original_value} "
                    f"while '{c2.source_document}' specifies {curr2} {c2.original_value}. "
                    "Cannot confirm contradiction without confirmed foreign exchange rates."
                ),
                requires_human_review=True,
                confidence=0.85,
                details={"currency_1": curr1, "currency_2": curr2},
            )

        val1 = float(c1.normalized_value)
        val2 = float(c2.normalized_value)

        diff = abs(val1 - val2)
        if diff < 0.01:
            return ComparisonRuleResult(
                status=FindingStatus.CONSISTENT,
                severity=FindingSeverity.INFO,
                explanation=f"Monetary amounts match: {curr1} {val1:,.2f} across both documents.",
                requires_human_review=False,
                confidence=0.99,
                details={"val1": val1, "val2": val2, "diff": 0.0},
            )
        else:
            pct_diff = (diff / max(val1, val2)) * 100.0 if max(val1, val2) > 0 else 0
            severity = FindingSeverity.CRITICAL if diff > 1000 or pct_diff > 10 else FindingSeverity.HIGH
            return ComparisonRuleResult(
                status=FindingStatus.CONTRADICTION,
                severity=severity,
                explanation=(
                    f"Monetary discrepancy detected: '{c1.source_document}' specifies {c1.original_value} "
                    f"whereas '{c2.source_document}' specifies {c2.original_value} "
                    f"(Variance: {curr1} {diff:,.2f} / {pct_diff:.1f}%)."
                ),
                requires_human_review=True,
                confidence=0.98,
                details={"val1": val1, "val2": val2, "diff": diff, "pct_diff": pct_diff},
            )

    @classmethod
    def _evaluate_date(cls, c1: ExtractedClaim, c2: ExtractedClaim) -> ComparisonRuleResult:
        is_ambiguous = (
            c1.review_status == ReviewStatus.REQUIRES_REVIEW or
            c2.review_status == ReviewStatus.REQUIRES_REVIEW
        )

        d1 = str(c1.normalized_value)
        d2 = str(c2.normalized_value)

        if d1 == d2:
            return ComparisonRuleResult(
                status=FindingStatus.CONSISTENT,
                severity=FindingSeverity.INFO,
                explanation=f"Dates match: {d1} across both documents.",
                requires_human_review=is_ambiguous,
                confidence=0.95 if not is_ambiguous else 0.70,
                details={"parsed_date": d1, "is_ambiguous": is_ambiguous},
            )

        # Dates differ
        if is_ambiguous:
            # Check if an alternative DD/MM vs MM/DD permutation could match
            # E.g., if d2 is YYYY-MM-DD, try swapping month and day
            parts2 = d2.split("-")
            can_match_alternative = False
            if len(parts2) == 3:
                try:
                    alt_d2 = f"{parts2[0]}-{int(parts2[2]):02d}-{int(parts2[1]):02d}"
                    if alt_d2 == d1:
                        can_match_alternative = True
                except Exception:
                    pass

            parts1 = d1.split("-")
            if len(parts1) == 3:
                try:
                    alt_d1 = f"{parts1[0]}-{int(parts1[2]):02d}-{int(parts1[1]):02d}"
                    if alt_d1 == d2:
                        can_match_alternative = True
                except Exception:
                    pass

            if can_match_alternative:
                return ComparisonRuleResult(
                    status=FindingStatus.UNCERTAIN,
                    severity=FindingSeverity.MEDIUM,
                    explanation=(
                        f"Potential date alignment depending on format interpretation ('{c1.original_value}' vs '{c2.original_value}'). "
                        "Numeric date format is ambiguous between DD/MM and MM/DD. Requires human auditor review."
                    ),
                    requires_human_review=True,
                    confidence=0.70,
                    details={"d1": d1, "d2": d2, "ambiguity_flag": True},
                )

        # If neither permutation matches, it is an undeniable contradiction
        severity = FindingSeverity.CRITICAL if c1.attribute == "date_of_birth" else FindingSeverity.HIGH
        return ComparisonRuleResult(
            status=FindingStatus.CONTRADICTION,
            severity=severity,
            explanation=(
                f"Date conflict detected for '{c1.attribute.replace('_', ' ').title()}': '{c1.source_document}' states {c1.original_value} "
                f"({d1}) whereas '{c2.source_document}' states {c2.original_value} ({d2})."
            ),
            requires_human_review=True,
            confidence=0.95,
            details={"d1": d1, "d2": d2},
        )

    @classmethod
    def _evaluate_quantity(cls, c1: ExtractedClaim, c2: ExtractedClaim) -> ComparisonRuleResult:
        q1 = float(c1.normalized_value)
        q2 = float(c2.normalized_value)

        item1 = (c1.line_item or "").lower().strip()
        item2 = (c2.line_item or "").lower().strip()

        # If items are named and differ significantly, they are different line items
        if item1 and item2 and item1 != item2:
            return ComparisonRuleResult(
                status=FindingStatus.CONSISTENT,
                severity=FindingSeverity.INFO,
                explanation=f"Separate line items: '{c1.original_value}' and '{c2.original_value}'. No conflict.",
                requires_human_review=False,
                confidence=0.90,
                details={"item1": item1, "item2": item2},
            )

        if abs(q1 - q2) < 0.001:
            return ComparisonRuleResult(
                status=FindingStatus.CONSISTENT,
                severity=FindingSeverity.INFO,
                explanation=f"Quantities align for line item ({q1:g} {c1.unit or 'units'}).",
                requires_human_review=False,
                confidence=0.95,
                details={"qty": q1},
            )

        return ComparisonRuleResult(
            status=FindingStatus.CONTRADICTION,
            severity=FindingSeverity.HIGH,
            explanation=(
                f"Quantity contradiction for line item '{c1.line_item or 'item'}': "
                f"'{c1.source_document}' specifies {q1:g} whereas '{c2.source_document}' specifies {q2:g}."
            ),
            requires_human_review=True,
            confidence=0.95,
            details={"qty1": q1, "qty2": q2, "diff": abs(q1 - q2)},
        )

    @classmethod
    def _evaluate_deadline(cls, c1: ExtractedClaim, c2: ExtractedClaim) -> ComparisonRuleResult:
        try:
            d1 = int(c1.normalized_value)
            d2 = int(c2.normalized_value)
            if d1 == d2:
                return ComparisonRuleResult(
                    status=FindingStatus.CONSISTENT,
                    severity=FindingSeverity.INFO,
                    explanation=f"Deadlines match ({d1} days) across both documents.",
                    requires_human_review=False,
                    confidence=0.95,
                    details={"days": d1},
                )
            else:
                return ComparisonRuleResult(
                    status=FindingStatus.CONTRADICTION,
                    severity=FindingSeverity.HIGH,
                    explanation=(
                        f"Deadline contradiction: '{c1.source_document}' states {c1.original_value} ({d1} days) "
                        f"whereas '{c2.source_document}' specifies {c2.original_value} ({d2} days)."
                    ),
                    requires_human_review=True,
                    confidence=0.92,
                    details={"days1": d1, "days2": d2, "variance_days": abs(d1 - d2)},
                )
        except (ValueError, TypeError):
            if str(c1.normalized_value).strip().lower() == str(c2.normalized_value).strip().lower():
                return ComparisonRuleResult(
                    status=FindingStatus.CONSISTENT,
                    severity=FindingSeverity.INFO,
                    explanation=f"Terms match: '{c1.original_value}'.",
                    requires_human_review=False,
                    confidence=0.88,
                    details={},
                )
            return ComparisonRuleResult(
                status=FindingStatus.CONTRADICTION,
                severity=FindingSeverity.MEDIUM,
                explanation=(
                    f"Terms discrepancy: '{c1.source_document}' specifies '{c1.original_value}' "
                    f"while '{c2.source_document}' specifies '{c2.original_value}'."
                ),
                requires_human_review=True,
                confidence=0.85,
                details={},
            )

    @classmethod
    def _evaluate_identifier(cls, c1: ExtractedClaim, c2: ExtractedClaim) -> ComparisonRuleResult:
        id1 = str(c1.normalized_value).upper()
        id2 = str(c2.normalized_value).upper()

        if id1 == id2:
            return ComparisonRuleResult(
                status=FindingStatus.CONSISTENT,
                severity=FindingSeverity.INFO,
                explanation=f"Identifiers match ({c1.original_value}) across documents.",
                requires_human_review=False,
                confidence=0.99,
                details={"id": id1},
            )

        return ComparisonRuleResult(
            status=FindingStatus.CONTRADICTION,
            severity=FindingSeverity.CRITICAL,
            explanation=(
                f"Identifier mismatch for {c1.attribute}: '{c1.source_document}' states '{c1.original_value}' "
                f"whereas '{c2.source_document}' states '{c2.original_value}'."
            ),
            requires_human_review=True,
            confidence=0.95,
            details={"id1": id1, "id2": id2},
        )
