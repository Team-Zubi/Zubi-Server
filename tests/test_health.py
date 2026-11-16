from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root() -> None:
    res = client.get("/")
    assert res.status_code == 200


def test_health() -> None:
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"
