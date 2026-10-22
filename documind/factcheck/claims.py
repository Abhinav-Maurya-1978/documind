import logging
import re
from typing import Any, Dict, List, Optional
from .llm import query_llm_json
from ..ingestion.pdf_processor import ProcessedDocument, ProcessedPage

logger = logging.getLogger(__name__)

CLAIM_EXTRACTION_PROMPT = """You are an objective Fact-Checking Claim Extraction system.
Analyze the provided document text (organized by page) and extract atomic, checkable factual claims.

Factual claims to include:
- Specific numbers, statistics, percentages, and measurements.
- Historical, biographical, scientific, legal, and current event claims.
- Named entities, organizational affiliations, dates, deadlines, and definitions.

DO NOT include:
- Subjective opinions, personal sentiments, or editorial views.
- Future predictions, speculative forecasts, or hypothetical statements.
- Vague generalizations or metaphors.

RULES FOR EACH CLAIM:
1. "claim": State the atomic factual proposition clearly and independently.
2. "page_number": The exact 1-based page number where this information appears.
3. "quote": An EXACT, verbatim sentence or phrase from that page supporting the claim. Do NOT paraphrase the quote.

Output a strict JSON array of objects with keys: "claim", "page_number", "quote".

DOCUMENT TEXT:
{document_content}
"""

class ClaimExtractorService:
    """Extracts verifiable claims from document pages and validates quotes against source text."""

    def __init__(self, max_claims: int = 12):
        self.max_claims = max_claims

    def extract_claims(self, doc: ProcessedDocument, config: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        # Format document pages into readable prompt
        page_texts = []
        for p in doc.pages:
            if p.text and p.text.strip():
                page_texts.append(f"--- PAGE {p.page_number} ---\n{p.text.strip()}")

        if not page_texts:
            return []

        doc_content = "\n\n".join(page_texts)
        # Limit prompt context length safely if document is very large
        if len(doc_content) > 30000:
            doc_content = doc_content[:30000] + "\n...[Content truncated for length]..."

        prompt = CLAIM_EXTRACTION_PROMPT.format(document_content=doc_content)
        raw_claims = query_llm_json(prompt, config=config)

        if not isinstance(raw_claims, list):
            if isinstance(raw_claims, dict) and "claims" in raw_claims and isinstance(raw_claims["claims"], list):
                raw_claims = raw_claims["claims"]
            else:
                logger.warning(f"Unexpected claim extraction response format: {type(raw_claims)}")
                return []

        # Validate each claim against original page text
        verified_claims = []
        pages_by_num = {p.page_number: p.text for p in doc.pages}

        for idx, item in enumerate(raw_claims):
            if not isinstance(item, dict):
                continue

            claim_text = item.get("claim", "").strip()
            page_num = item.get("page_number")
            quote_text = item.get("quote", "").strip()

            if not claim_text or not quote_text or not page_num:
                continue

            try:
                page_num_int = int(page_num)
            except (ValueError, TypeError):
                continue

            page_text = pages_by_num.get(page_num_int, "")
            if not page_text:
                continue

            # Hard Requirement: Check quote is exact substring of extracted page text
            # Allow normalized whitespace (newlines/spaces collapsed) for robust substring matching
            norm_page = re.sub(r"\s+", " ", page_text.lower())
            norm_quote = re.sub(r"\s+", " ", quote_text.lower())

            if norm_quote in norm_page:
                verified_claims.append({
                    "id": f"claim_{len(verified_claims) + 1}",
                    "claim": claim_text,
                    "page_number": page_num_int,
                    "quote": quote_text,
                })
            else:
                # Substring not found; drop claim to guarantee 100% quotation grounding
                logger.info(f"Dropped ungrounded claim quote: '{quote_text}' on page {page_num_int}")

            if len(verified_claims) >= self.max_claims:
                break

        return verified_claims
