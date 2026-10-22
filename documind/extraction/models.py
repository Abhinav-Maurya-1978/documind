import enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class ValueType(str, enum.Enum):
    MONETARY = "monetary"
    DATE = "date"
    QUANTITY = "quantity"
    DEADLINE = "deadline"
    IDENTIFIER = "identifier"
    PAYMENT_TERM = "payment_term"
    DELIVERY_TERM = "delivery_term"
    TAX_ID = "tax_id"
    TEXT = "text"

class FindingStatus(str, enum.Enum):
    CONTRADICTION = "contradiction"
    CONSISTENT = "consistent"
    MISSING_INFO = "missing_info"
    UNCERTAIN = "uncertain"

class FindingSeverity(str, enum.Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"

class ReviewStatus(str, enum.Enum):
    EXTRACTED = "extracted"
    VERIFIED = "verified"
    REQUIRES_REVIEW = "requires_review"
    UNVERIFIED = "unverified"

class ExtractedClaim(BaseModel):
    claim_id: str
    entity: str = Field(..., description="Subject or entity name (e.g., PO-101, Invoice INV-202, Acme Corp)")
    attribute: str = Field(..., description="Normalized property name (e.g., total_amount, order_date, delivery_deadline)")
    original_value: str = Field(..., description="Exact original raw value string as written in the text")
    normalized_value: Any = Field(..., description="Standardized canonical value (float, ISO date string, int)")
    value_type: ValueType = Field(..., description="Category of the claim value")
    unit: Optional[str] = Field(None, description="Currency or measurement unit (INR, USD, days, units)")
    line_item: Optional[str] = Field(None, description="Specific line item descriptor if applicable")
    obligation: Optional[str] = Field(None, description="Contractual obligation or condition if applicable")
    source_document: str = Field(..., description="Display filename of the document")
    page_number: int = Field(..., ge=1, description="1-based source page number")
    evidence: str = Field(..., description="Exact snippet of surrounding text supporting this claim")
    char_start: Optional[int] = Field(None, description="Start offset in page text")
    char_end: Optional[int] = Field(None, description="End offset in page text")
    confidence: float = Field(1.0, ge=0.0, le=1.0)
    review_status: ReviewStatus = Field(ReviewStatus.EXTRACTED)

class ComparisonFinding(BaseModel):
    finding_id: str
    status: FindingStatus
    severity: FindingSeverity
    attribute: str
    topic: str
    explanation: str
    claims: List[ExtractedClaim]
    discrepancy_details: Optional[Dict[str, Any]] = None
    requires_human_review: bool = True
    confidence: float = 0.95
    evidence_verified: bool = False

class AuditSummary(BaseModel):
    total_documents: int
    total_pages: int
    total_claims_extracted: int
    total_comparisons: int
    contradictions_count: int
    consistent_count: int
    missing_info_count: int
    uncertain_count: int
    has_warnings: bool = False
    warnings: List[str] = Field(default_factory=list)

class AuditSessionResult(BaseModel):
    session_id: str
    created_at: str
    status: str
    summary: AuditSummary
    findings: List[ComparisonFinding]
    documents: List[Dict[str, Any]]
