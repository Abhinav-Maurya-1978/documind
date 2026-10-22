import io
import json
import pytest
from unittest.mock import MagicMock, patch

from app import create_app
from config import Config
from documind.ingestion.pdf_processor import ProcessedDocument, ProcessedPage
from documind.factcheck.llm import query_llm_json
from documind.factcheck.claims import ClaimExtractorService
from documind.factcheck.judge import ClaimJudgeService
from documind.factcheck.sources import SourceRetriever
from documind.factcheck.routes import is_rate_limited, _ip_request_history

class FactCheckTestConfig(Config):
    TESTING = True
    DATABASE_URL = "sqlite:///:memory:"
    GEMINI_API_KEY = "test_gemini_key"
    GEMINI_MODEL = "gemini-2.0-flash-lite"
    LLM_PROVIDER = "gemini"
    FACTCHECK_API_KEY = "test_factcheck_key"
    TAVILY_API_KEY = "test_tavily_key"
    FACTCHECK_MAX_CLAIMS = 5

@pytest.fixture
def client():
    app = create_app(FactCheckTestConfig)
    with app.test_client() as client:
        yield client

# 1. LLM Provider Switching & Errors
def test_llm_provider_switching():
    # Test groq stub
    with pytest.raises(ValueError) as exc_groq:
        query_llm_json("prompt", config={"LLM_PROVIDER": "groq"})
    assert "Groq provider is not configured" in str(exc_groq.value)

    # Test unknown provider
    with pytest.raises(ValueError) as exc_unk:
        query_llm_json("prompt", config={"LLM_PROVIDER": "unsupported_ai"})
    assert "Unsupported LLM provider" in str(exc_unk.value)

    # Test missing key for gemini
    with pytest.raises(ValueError) as exc_key:
        query_llm_json("prompt", config={"LLM_PROVIDER": "gemini", "GEMINI_API_KEY": ""})
    assert "GEMINI_API_KEY is not configured" in str(exc_key.value)

# 2. 429 Rate Limit Retry Handling
@patch("requests.post")
def test_llm_429_retry_handling(mock_post):
    # Mock HTTP 429 response
    mock_resp_429 = MagicMock()
    mock_resp_429.status_code = 429
    mock_resp_429.headers = {"Retry-After": "1"}

    mock_post.return_value = mock_resp_429

    with pytest.raises(RuntimeError) as exc_429:
        query_llm_json("test prompt", config={"GEMINI_API_KEY": "dummy_key", "GEMINI_MODEL": "test-model"})
    assert "rate limit hit (429)" in str(exc_429.value).lower()
    # Verified it retried (initial + 2 retries = 3 attempts)
    assert mock_post.call_count == 3

# 3. Claim Quote Exact Substring Verification
@patch("documind.factcheck.claims.query_llm_json")
def test_claim_quote_verification(mock_llm):
    service = ClaimExtractorService(max_claims=5)
    page_text = "The Eiffel Tower in Paris was completed on March 31, 1889. It was designed by Gustave Eiffel."
    doc = ProcessedDocument(
        document_id="doc1",
        display_name="paris.pdf",
        file_path="dummy.pdf",
        total_pages=1,
        pages=[ProcessedPage(page_number=1, text=page_text, extraction_method="text")]
    )

    # LLM returns one grounded quote and one hallucinated quote
    mock_llm.return_value = [
        {
            "claim": "The Eiffel Tower was completed on March 31, 1889.",
            "page_number": 1,
            "quote": "The Eiffel Tower in Paris was completed on March 31, 1889."
        },
        {
            "claim": "The Eiffel Tower is made entirely of gold.",
            "page_number": 1,
            "quote": "This sentence does not exist anywhere in the text."
        }
    ]

    claims = service.extract_claims(doc)
    # The hallucinated quote must be dropped
    assert len(claims) == 1
    assert claims[0]["claim"] == "The Eiffel Tower was completed on March 31, 1889."
    assert claims[0]["page_number"] == 1
    assert claims[0]["id"] == "claim_1"

# 4. No Evidence Rule: Returns Unverifiable WITHOUT calling LLM
@patch("documind.factcheck.judge.query_llm_json")
def test_judge_no_evidence_rule(mock_llm):
    judge = ClaimJudgeService()
    # Empty evidence items
    result = judge.judge_claim("Mount Everest is the highest mountain", [])

    assert result["verdict"] == "Unverifiable"
    assert "No relevant factual evidence found" in result["reason"]
    assert result["evidence_ids"] == []
    # LLM must NEVER be called
    mock_llm.assert_not_called()

# 5. Evidence ID Validation and Source Attachment
@patch("documind.factcheck.judge.query_llm_json")
def test_judge_evidence_id_validation(mock_llm):
    judge = ClaimJudgeService()
    evidence_items = [
        {"evidence_id": 1, "title": "Wiki: Everest", "url": "https://wiki.org/Everest", "snippet": "Everest is Earth's highest mountain above sea level.", "source_type": "wikipedia"},
        {"evidence_id": 2, "title": "Wiki: K2", "url": "https://wiki.org/K2", "snippet": "K2 is the second-highest mountain.", "source_type": "wikipedia"},
    ]

    # Model returns valid evidence ID 1, plus invalid ID 99
    mock_llm.return_value = {
        "verdict": "Supported",
        "reason": "Wikipedia directly confirms Mount Everest is the highest mountain.",
        "evidence_ids": [1, 99]
    }

    result = judge.judge_claim("Mount Everest is the highest mountain", evidence_items)
    assert result["verdict"] == "Supported"
    # Invalid ID 99 must be filtered out
    assert result["evidence_ids"] == [1]
    assert len(result["sources"]) == 1
    assert result["sources"][0]["url"] == "https://wiki.org/Everest"

# 6. Source Retriever with Mocked APIs
@patch("requests.get")
def test_source_retriever_wikipedia(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "query": {
            "search": [
                {
                    "title": "Apollo 11",
                    "snippet": "Apollo 11 was the spaceflight that first landed humans on the Moon in <span class=\"searchmatch\">1969</span>."
                }
            ]
        }
    }
    mock_get.return_value = mock_resp

    retriever = SourceRetriever(factcheck_api_key="", tavily_api_key="")
    evidence = retriever.retrieve_evidence("Apollo 11 landed in 1969")

    assert len(evidence) >= 1
    assert evidence[0]["evidence_id"] == 1
    assert "Wikipedia: Apollo 11" in evidence[0]["title"]
    assert "https://en.wikipedia.org/wiki/Apollo_11" in evidence[0]["url"]
    assert "<span" not in evidence[0]["snippet"]  # HTML stripped

# 7. Flask Factcheck Routes
def test_factcheck_index_page(client):
    res = client.get("/factcheck")
    assert res.status_code == 200
    assert b"Document AI Fact Checker" in res.data
    assert b"AI-generated results. Verify with a human." in res.data

@patch("documind.factcheck.claims.ClaimExtractorService.extract_claims")
def test_factcheck_extract_endpoint(mock_extract, client):
    mock_extract.return_value = [
        {"id": "claim_1", "claim": "Sample fact", "page_number": 1, "quote": "Sample quote"}
    ]
    # Create PDF with valid text using PyMuPDF
    import pymupdf
    pdf_doc = pymupdf.open()
    page = pdf_doc.new_page()
    page.insert_text((50, 50), "Sample fact text on page 1 of document.")
    pdf_bytes = pdf_doc.tobytes()
    pdf_doc.close()

    data = {"document": (io.BytesIO(pdf_bytes), "sample.pdf")}

    res = client.post("/api/factcheck/extract", data=data, content_type="multipart/form-data")
    assert res.status_code == 200
    json_data = res.get_json()
    assert json_data["success"] is True
    assert len(json_data["claims"]) == 1
    assert json_data["claims"][0]["id"] == "claim_1"

@patch("documind.factcheck.sources.SourceRetriever.retrieve_evidence")
@patch("documind.factcheck.judge.ClaimJudgeService.judge_claim")
def test_factcheck_verify_endpoint(mock_judge, mock_retriever, client):
    mock_retriever.return_value = [
        {"evidence_id": 1, "title": "Wiki", "url": "https://wiki.org", "snippet": "Evidence text", "source_type": "wikipedia"}
    ]
    mock_judge.return_value = {
        "verdict": "Supported",
        "reason": "Verified fact.",
        "evidence_ids": [1],
        "sources": [{"title": "Wiki", "url": "https://wiki.org", "snippet": "Evidence text", "source_type": "wikipedia"}]
    }

    payload = {
        "id": "claim_1",
        "claim": "Water boils at 100 degrees Celsius",
        "page_number": 1,
        "quote": "Water boils at 100 C."
    }

    res = client.post("/api/factcheck/verify", json=payload)
    assert res.status_code == 200
    json_data = res.get_json()
    assert json_data["verdict"] == "Supported"
    assert json_data["reason"] == "Verified fact."
    assert len(json_data["sources"]) == 1

# 8. Rate Limiter Test
def test_rate_limiter():
    ip = "192.168.1.100"
    _ip_request_history[ip].clear()
    for _ in range(35):
        assert is_rate_limited(ip) is False
    # 36th request in window must be rate limited
    assert is_rate_limited(ip) is True
