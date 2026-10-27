from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root_returns_welcome_message():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["message"] == "Welcome to StockFlow API"


def test_health_check_is_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_list_returns_includes_sample_item():
    response = client.get("/returns")
    assert response.status_code == 200
    items = response.json()
    assert len(items) >= 1
    assert items[0]["product_name"] == "Wireless Mouse"
    assert items[0]["disposition"] == "pending_inspection"


def test_unknown_return_id_is_not_found():
    response = client.get("/returns/99999")
    assert response.status_code == 404
