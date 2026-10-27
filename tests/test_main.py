from fastapi.testclient import TestClient

from app.main import app, audit_events, returns, sellable_inventory

client = TestClient(app)


def setup_function():
    # Reset mutable in-memory state so tests do not depend on execution order.
    returns.clear()
    returns[1] = __import__("app.main", fromlist=["ReturnItem"]).ReturnItem(
        id=1,
        product_name="Wireless Mouse",
        condition="new",
        disposition="pending_inspection",
        quantity=2,
    )
    sellable_inventory.clear()
    audit_events.clear()
    module = __import__("app.main", fromlist=["next_return_id"])
    module.next_return_id = 2
    module.next_event_id = 1


def test_root_returns_welcome_message():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["message"] == "Welcome to StockFlow API"


def test_health_check_is_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_pending_return_is_not_sellable():
    response = client.get("/inventory")
    assert response.status_code == 200
    assert response.json()["sellable_stock"] == {}


def test_create_return_starts_pending_inspection():
    response = client.post(
        "/returns",
        json={"product_name": "USB-C Cable", "condition": "new", "quantity": 3},
    )
    assert response.status_code == 201
    assert response.json()["disposition"] == "pending_inspection"
    assert response.json()["quantity"] == 3
    assert client.get("/inventory").json()["sellable_stock"] == {}


def test_restock_decision_adds_sellable_inventory_and_audit_log():
    created = client.post(
        "/returns",
        json={"product_name": "Keyboard", "condition": "new", "quantity": 4},
    ).json()

    response = client.post(
        f"/returns/{created['id']}/disposition",
        json={"disposition": "restock", "reason": "Inspected and works correctly"},
    )

    assert response.status_code == 200
    assert response.json()["disposition"] == "restock"
    assert client.get("/inventory").json()["sellable_stock"]["Keyboard"] == 4
    logs = client.get("/audit-logs").json()
    assert any(log["event_type"] == "disposition_decided" for log in logs)


def test_damaged_item_cannot_be_restocked():
    created = client.post(
        "/returns",
        json={"product_name": "Cracked Screen", "condition": "damaged", "quantity": 1},
    ).json()

    response = client.post(
        f"/returns/{created['id']}/disposition",
        json={"disposition": "restock", "reason": "Attempted restock"},
    )

    assert response.status_code == 422
    assert client.get("/inventory").json()["sellable_stock"] == {}


def test_disposition_cannot_be_changed_twice():
    created = client.post(
        "/returns",
        json={"product_name": "Headphones", "condition": "new", "quantity": 1},
    ).json()
    url = f"/returns/{created['id']}/disposition"
    payload = {"disposition": "repair", "reason": "Needs a new cable"}
    assert client.post(url, json=payload).status_code == 200
    assert client.post(url, json=payload).status_code == 409


def test_unknown_return_id_is_not_found():
    response = client.get("/returns/99999")
    assert response.status_code == 404
