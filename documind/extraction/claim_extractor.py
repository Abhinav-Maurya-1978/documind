import logging
import re
import uuid
from typing import List, Optional
from .models import ExtractedClaim, ReviewStatus, ValueType
from .normalizers import ValueNormalizer
from ..ingestion.pdf_processor import ProcessedDocument, ProcessedPage

logger = logging.getLogger(__name__)

class ClaimExtractor:
    """
    Deterministic rule-based extractor for enterprise document claims:
    totals, line items, dates, deadlines, identifiers, and obligations.
    """

    # Common patterns
    TOTAL_PATTERNS = [
        r"(?:grand\s+total|total\s+amount|total\s+payable|total\s+price|final\s+amount|net\s+total|total)\s*[:=\-]?\s*([^\n\r;]{0,15}?\b\d{1,3}(?:[,\s]\d{2,3})*(?:\.\d{1,2})?\b\s*(?:inr|usd|eur|gbp|rupees|rs\.?)?)",
        r"(?:amount\s+due|balance\s+due|payable\s+amount)\s*[:=\-]?\s*([^\n\r;]{0,15}?\b\d{1,3}(?:[,\s]\d{2,3})*(?:\.\d{1,2})?\b\s*(?:inr|usd|eur|gbp|rupees|rs\.?)?)",
    ]

    NAME_PATTERNS = [
        (r"(?:employee\s+name|applicant\s+name|candidate\s+name|student\s+name|person\s+name|individual\s+name|name)\s*[:=\-]\s*([A-Za-z\s\.\'\-]+?)(?:\r?\n|$)", "person_name"),
        (r"(?:vendor\s+name|supplier\s+name|company\s+name|client\s+name|customer\s+name|organization\s+name)\s*[:=\-]\s*([A-Za-z0-9\s\.\,\'\-]+?)(?:\r?\n|$)", "organization_name"),
    ]

    COMPENSATION_PATTERNS = [
        (r"(?:annual\s+ctc|ctc|annual\s+salary|annual\s+package)\s*[:=\-]?\s*([^\n\r;]{0,15}?\b\d{1,3}(?:[,\s]\d{2,3})*(?:\.\d{1,2})?\b\s*(?:inr|usd|eur|gbp|rupees|rs\.?)?)", "annual_compensation"),
        (r"(?:monthly\s+salary|monthly\s+stipend|monthly\s+pay|monthly\s+ctc)\s*[:=\-]?\s*([^\n\r;]{0,15}?\b\d{1,3}(?:[,\s]\d{2,3})*(?:\.\d{1,2})?\b\s*(?:inr|usd|eur|gbp|rupees|rs\.?)?)", "monthly_compensation"),
    ]

    DATE_PATTERNS = [
        (r"(?:date\s+of\s+birth|dob|birth\s+date)\s*[:=\-]?\s*([0-9a-zA-Z\s,/\.\-]+?)(?:\r?\n|$)", "date_of_birth"),
        (r"(?:order\s+date|po\s+date|date\s+of\s+order)\s*[:=\-]?\s*([0-9a-zA-Z\s,/\.\-]+?)(?:\r?\n|$)", "order_date"),
        (r"(?:invoice\s+date|billing\s+date|date\s+of\s+invoice)\s*[:=\-]?\s*([0-9a-zA-Z\s,/\.\-]+?)(?:\r?\n|$)", "invoice_date"),
        (r"(?:delivery\s+date|expected\s+delivery|shipment\s+date)\s*[:=\-]?\s*([0-9a-zA-Z\s,/\.\-]+?)(?:\r?\n|$)", "delivery_date"),
        (r"(?:due\s+date|payment\s+due\s+date|payable\s+by)\s*[:=\-]?\s*([0-9a-zA-Z\s,/\.\-]+?)(?:\r?\n|$)", "due_date"),
        (r"(?:effective\s+date|agreement\s+date|contract\s+date)\s*[:=\-]?\s*([0-9a-zA-Z\s,/\.\-]+?)(?:\r?\n|$)", "effective_date"),
    ]

    DEADLINE_PATTERNS = [
        (r"(?:delivery\s+(?:within|timeframe|period|deadline)|lead\s+time)\s*[:=\-]?\s*([^\n\.;,]+(?:\bdays\b|\bweeks\b|\bmonths\b))", "delivery_deadline"),
        (r"(?:payment\s+terms?|terms\s+of\s+payment)\s*[:=\-]?\s*([^\n\.;,]+(?:net\s*\d+|\bdays\b|advance|receipt))", "payment_terms"),
    ]

    IDENTIFIER_PATTERNS = [
        (r"(?:po\s*(?:number|no|#)?|purchase\s+order\s*(?:no|#)?)\s*[:=\-]?\s*([A-Za-z0-9\-_/]+)", "purchase_order_id"),
        (r"(?:invoice\s*(?:number|no|#)?|inv\s*(?:no|#)?)\s*[:=\-]?\s*([A-Za-z0-9\-_/]+)", "invoice_id"),
        (r"(?:quote\s*(?:number|no|#)?|quotation\s*(?:no|#)?)\s*[:=\-]?\s*([A-Za-z0-9\-_/]+)", "quotation_id"),
        (r"(?:tax\s*id|gstin|pan|vat\s*no|ein)\s*[:=\-]?\s*([A-Za-z0-9\-_/]+)", "tax_identifier"),
        (r"(?:vendor\s*id|supplier\s*id|customer\s*id)\s*[:=\-]?\s*([A-Za-z0-9\-_/]+)", "vendor_id"),
    ]

    # Line item pattern: e.g. "10 laptops @ ₹50,000" or "Quantity: 20 Monitors"
    LINE_ITEM_PATTERNS = [
        r"(?:item|description|product)?\s*[:=\-]?\s*(\d+)\s*(?:units?|pcs?|pieces?|nos?|x)?\s+(?:of\s+)?([A-Za-z0-9\s\-]+?)\s*(?:@|at|price|rate|cost|amount)?\s*([₹$€£Rs\.\w\s]*\d{1,3}(?:[,\s]\d{2,3})*(?:\.\d{1,2})?)?",
        r"(?:quantity|qty)\s*[:=\-]?\s*(\d+)\s*(?:units?|pcs?|pieces?|nos?)?\s+(?:for\s+)?([A-Za-z0-9\s\-]+)",
    ]

    def __init__(self, llm_config: Optional[dict] = None):
        self.llm_config = llm_config or {}

    def extract_document_claims(self, doc: ProcessedDocument) -> List[ExtractedClaim]:
        """Extracts structured claims from all pages of a processed document."""
        all_claims: List[ExtractedClaim] = []

        # Find document broad entity/ID to link claims
        doc_entity = self._infer_document_entity(doc)

        for page in doc.pages:
            if not page.text:
                continue

            claims = self._extract_page_claims(
                page=page,
                doc_name=doc.display_name,
                default_entity=doc_entity
            )
            all_claims.extend(claims)

        return all_claims

    def _infer_document_entity(self, doc: ProcessedDocument) -> str:
        """Determines best entity name (e.g. 'PO-104' or filename)."""
        first_page_text = doc.pages[0].text if doc.pages else ""
        for pat, _ in self.IDENTIFIER_PATTERNS:
            m = re.search(pat, first_page_text, re.IGNORECASE)
            if m:
                val = m.group(1).strip()
                if len(val) >= 3:
                    return f"{doc.display_name} ({val})"
        return doc.display_name

    def _extract_page_claims(self, page: ProcessedPage, doc_name: str, default_entity: str) -> List[ExtractedClaim]:
        claims: List[ExtractedClaim] = []
        text = page.text
        lines = [line.strip() for line in text.split("\n") if line.strip()]

        # 1. Extract Identifiers
        for pat, attr in self.IDENTIFIER_PATTERNS:
            for match in re.finditer(pat, text, re.IGNORECASE):
                val = match.group(1).strip()
                if not val or len(val) < 2 or val.lower() in ("date", "total", "amount"):
                    continue

                snippet = self._get_context_snippet(text, match.start(), match.end())
                claims.append(
                    ExtractedClaim(
                        claim_id=str(uuid.uuid4())[:8],
                        entity=default_entity,
                        attribute=attr,
                        original_value=val,
                        normalized_value=ValueNormalizer.normalize_identifier(val),
                        value_type=ValueType.IDENTIFIER if attr != "tax_identifier" else ValueType.TAX_ID,
                        source_document=doc_name,
                        page_number=page.page_number,
                        evidence=snippet,
                        char_start=match.start(),
                        char_end=match.end(),
                        confidence=0.95,
                    )
                )

        # 1b. Extract Names (Person and Organization)
        for pat, attr in self.NAME_PATTERNS:
            for match in re.finditer(pat, text, re.IGNORECASE):
                val = match.group(1).strip()
                if not val or len(val) < 2:
                    continue
                snippet = self._get_context_snippet(text, match.start(), match.end())
                claims.append(
                    ExtractedClaim(
                        claim_id=str(uuid.uuid4())[:8],
                        entity=default_entity,
                        attribute=attr,
                        original_value=val,
                        normalized_value=re.sub(r"\s+", " ", val).strip().title(),
                        value_type=ValueType.PERSON_NAME if attr == "person_name" else ValueType.TEXT,
                        source_document=doc_name,
                        page_number=page.page_number,
                        evidence=snippet,
                        char_start=match.start(),
                        char_end=match.end(),
                        confidence=0.95,
                    )
                )

        # 1c. Extract Compensation / Salary
        for pat, attr in self.COMPENSATION_PATTERNS:
            for match in re.finditer(pat, text, re.IGNORECASE):
                raw_val = match.group(1).strip()
                norm_res = ValueNormalizer.normalize_monetary(raw_val)
                if norm_res["valid"]:
                    annual_equiv = norm_res["normalized"] if attr == "annual_compensation" else (norm_res["normalized"] * 12)
                    snippet = self._get_context_snippet(text, match.start(), match.end())
                    claims.append(
                        ExtractedClaim(
                            claim_id=str(uuid.uuid4())[:8],
                            entity=default_entity,
                            attribute="annual_compensation",
                            original_value=raw_val,
                            normalized_value=annual_equiv,
                            value_type=ValueType.COMPENSATION,
                            unit=norm_res["currency"],
                            source_document=doc_name,
                            page_number=page.page_number,
                            evidence=snippet,
                            char_start=match.start(),
                            char_end=match.end(),
                            confidence=0.95,
                        )
                    )

        # 2. Extract Total Amounts
        for pat in self.TOTAL_PATTERNS:
            for match in re.finditer(pat, text, re.IGNORECASE):
                raw_val = match.group(1).strip()
                norm_res = ValueNormalizer.normalize_monetary(raw_val)
                if norm_res["valid"]:
                    snippet = self._get_context_snippet(text, match.start(), match.end())
                    claims.append(
                        ExtractedClaim(
                            claim_id=str(uuid.uuid4())[:8],
                            entity=default_entity,
                            attribute="total_amount",
                            original_value=raw_val,
                            normalized_value=norm_res["normalized"],
                            value_type=ValueType.MONETARY,
                            unit=norm_res["currency"],
                            source_document=doc_name,
                            page_number=page.page_number,
                            evidence=snippet,
                            char_start=match.start(),
                            char_end=match.end(),
                            confidence=0.95,
                        )
                    )

        # 3. Extract Dates
        for pat, attr in self.DATE_PATTERNS:
            for match in re.finditer(pat, text, re.IGNORECASE):
                raw_val = match.group(1).strip()
                norm_res = ValueNormalizer.normalize_date(raw_val)
                if norm_res["valid"]:
                    snippet = self._get_context_snippet(text, match.start(), match.end())
                    claims.append(
                        ExtractedClaim(
                            claim_id=str(uuid.uuid4())[:8],
                            entity=default_entity,
                            attribute=attr,
                            original_value=raw_val,
                            normalized_value=norm_res["normalized"],
                            value_type=ValueType.DATE,
                            source_document=doc_name,
                            page_number=page.page_number,
                            evidence=snippet,
                            char_start=match.start(),
                            char_end=match.end(),
                            confidence=0.9 if not norm_res["is_ambiguous"] else 0.7,
                            review_status=ReviewStatus.REQUIRES_REVIEW if norm_res["is_ambiguous"] else ReviewStatus.EXTRACTED,
                        )
                    )

        # 4. Extract Deadlines and Payment Terms
        for pat, attr in self.DEADLINE_PATTERNS:
            for match in re.finditer(pat, text, re.IGNORECASE):
                raw_val = match.group(1).strip()
                norm_res = ValueNormalizer.normalize_deadline(raw_val)
                snippet = self._get_context_snippet(text, match.start(), match.end())
                claims.append(
                    ExtractedClaim(
                        claim_id=str(uuid.uuid4())[:8],
                        entity=default_entity,
                        attribute=attr,
                        original_value=raw_val,
                        normalized_value=norm_res["days"] if norm_res["valid"] else raw_val,
                        value_type=ValueType.DEADLINE if attr == "delivery_deadline" else ValueType.PAYMENT_TERM,
                        unit="days" if norm_res["valid"] else None,
                        source_document=doc_name,
                        page_number=page.page_number,
                        evidence=snippet,
                        char_start=match.start(),
                        char_end=match.end(),
                        confidence=0.9,
                    )
                )

        # 5. Extract Line Items (e.g. 10 Laptops, 20 Monitors)
        for line in lines:
            # Check for line item descriptions
            for pat in self.LINE_ITEM_PATTERNS:
                m = re.search(pat, line, re.IGNORECASE)
                if m:
                    qty_str = m.group(1)
                    item_desc = m.group(2).strip()

                    # Filter out non-items (like dates or totals mistaken for items)
                    if len(item_desc) < 3 or item_desc.lower() in ("days", "total", "subtotal", "tax", "gst", "page"):
                        continue

                    # Clean item description
                    item_desc = re.sub(r"[\s,;]+", " ", item_desc).strip()
                    try:
                        qty_num = float(qty_str)
                    except ValueError:
                        continue

                    # Find position in original text
                    char_idx = text.find(line)
                    snippet = line
                    claims.append(
                        ExtractedClaim(
                            claim_id=str(uuid.uuid4())[:8],
                            entity=default_entity,
                            attribute=f"line_item_qty:{item_desc.lower()}",
                            line_item=item_desc,
                            original_value=f"{qty_str} {item_desc}",
                            normalized_value=qty_num,
                            value_type=ValueType.QUANTITY,
                            unit="units",
                            source_document=doc_name,
                            page_number=page.page_number,
                            evidence=snippet,
                            char_start=char_idx if char_idx != -1 else 0,
                            char_end=(char_idx + len(line)) if char_idx != -1 else len(line),
                            confidence=0.9,
                        )
                    )

        # Deduplicate identical claims on the same page
        unique_claims = []
        seen = set()
        for c in claims:
            key = (c.attribute, str(c.normalized_value), c.page_number)
            if key not in seen:
                seen.add(key)
                unique_claims.append(c)

        return unique_claims

    def _get_context_snippet(self, full_text: str, start: int, end: int, window: int = 60) -> str:
        """Extracts the surrounding sentence or line around a match."""
        # Find newline before and after
        line_start = full_text.rfind("\n", 0, start)
        line_start = 0 if line_start == -1 else line_start + 1

        line_end = full_text.find("\n", end)
        line_end = len(full_text) if line_end == -1 else line_end

        snippet = full_text[line_start:line_end].strip()
        if len(snippet) < 15:
            # Expand context
            ctx_start = max(0, start - window)
            ctx_end = min(len(full_text), end + window)
            snippet = full_text[ctx_start:ctx_end].strip()

        return snippet
