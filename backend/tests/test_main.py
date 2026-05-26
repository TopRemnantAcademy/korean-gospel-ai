from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)


def test_read_root():
    """기본 루트 엔드포인트가 정상적으로 200 OK를 반환하고 기본 정보를 담고 있는지 검증."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "korean-gospel-rag"
    assert "version" in data
    assert "endpoints" in data
