import io
import json
import pytest
from app import create_app
from config import Config

class TestConfig(Config):
    TESTING = True
    DATABASE_URL = "sqlite:///:memory:"
    AUTO_CLEANUP_UPLOADS = True

@pytest.fixture
def client():
    app = create_app(TestConfig)
    with app.test_client() as client:
        yield client

def test_health_endpoint(client):
    res = client.get("/health")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "healthy"
    assert data["service"] == "DocuMind"

def test_index_dashboard(client):
    res = client.get("/")
    assert res.status_code == 200
    assert b"DocuMind" in res.data
    assert b"AI-Powered Cross-Document Contradiction Auditor" in res.data

def test_demo_samples_api(client):
    res = client.get("/api/demo-samples")
    assert res.status_code == 200
    data = res.get_json()
    assert "samples" in data
    assert len(data["samples"]) == 2

def test_audit_rejection_single_file(client):
    # Only 1 file provided
    data = {
        "documents": (io.BytesIO(b"%PDF-1.4\nsample"), "doc1.pdf")
    }
    res = client.post("/api/audit", data=data, content_type="multipart/form-data")
    assert res.status_code == 400
    json_data = res.get_json()
    assert "at least two (2) PDF documents" in json_data["error"]

def test_history_page(client):
    res = client.get("/history")
    assert res.status_code == 200
    assert b"Audit Session History" in res.data
