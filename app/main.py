"""StockFlow API: the IND8 returns floor over HTTP.

Every action returns the full floor snapshot, so the UI always renders
from one consistent, server-owned state.
"""

from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.warehouse import DomainError, Warehouse

app = FastAPI(
    title="StockFlow API",
    description="IND8 returns floor: unload, process, tranship and liquidation.",
    version="0.4.0",
)

warehouse = Warehouse.seeded()


class DistributeRequest(BaseModel):
    station: int


class RouteRequest(BaseModel):
    destination: Literal["yellow_tote", "liquidation"]


def act(action) -> dict:
    """Run a floor action and return the new snapshot, mapping rule violations to HTTP errors."""
    try:
        action()
    except DomainError as error:
        raise HTTPException(status_code=error.status, detail=error.message) from error
    return warehouse.snapshot()


@app.get("/")
def read_root() -> dict[str, str]:
    """Confirm the API is running."""
    return {"message": "Welcome to StockFlow API", "docs": "/docs", "app": "/dashboard"}


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/dashboard", include_in_schema=False)
def dashboard() -> FileResponse:
    """Serve the IND8 floor app (single page with its own navigation)."""
    return FileResponse(Path(__file__).parent / "static" / "dashboard.html")


# ---------- read ----------
@app.get("/api/state")
def get_state() -> dict:
    """The whole floor: trucks, boxes, items, totes, outbound, pallets, events, summary and XP."""
    return warehouse.snapshot()


@app.get("/api/events")
def get_events(after: int = 0) -> list[dict]:
    """Events newer than `after`, oldest first, for live activity feeds."""
    return [e for e in warehouse.snapshot()["events"] if e["id"] > after]


# ---------- unload ----------
@app.post("/api/trucks")
def schedule_truck() -> dict:
    return act(warehouse.schedule_truck)


@app.post("/api/trucks/{truck_id}/check-in")
def check_in(truck_id: str) -> dict:
    return act(lambda: warehouse.check_in(truck_id))


@app.post("/api/trucks/{truck_id}/unload")
def unload(truck_id: str) -> dict:
    return act(lambda: warehouse.unload(truck_id))


@app.post("/api/boxes/distribute-all")
def distribute_all() -> dict:
    return act(warehouse.distribute_all)


@app.post("/api/boxes/{box_id}/distribute")
def distribute(box_id: str, body: DistributeRequest) -> dict:
    return act(lambda: warehouse.distribute(box_id, body.station))


# ---------- process ----------
@app.post("/api/boxes/{box_id}/open")
def open_box(box_id: str) -> dict:
    return act(lambda: warehouse.open_box(box_id))


@app.post("/api/items/{item_id}/route")
def route_item(item_id: str, body: RouteRequest) -> dict:
    return act(lambda: warehouse.route_item(item_id, body.destination))


@app.post("/api/totes/close")
def close_tote() -> dict:
    return act(warehouse.close_tote)


# ---------- tranship ----------
@app.post("/api/totes/load-all")
def load_all_totes() -> dict:
    return act(warehouse.load_all_totes)


@app.post("/api/totes/{tote_id}/load")
def load_tote(tote_id: str) -> dict:
    return act(lambda: warehouse.load_tote(tote_id))


@app.post("/api/outbound/ship")
def ship_outbound() -> dict:
    return act(warehouse.ship_outbound)


# ---------- liquidation ----------
@app.post("/api/liquidation/ship")
def ship_liquidation() -> dict:
    return act(warehouse.ship_liquidation)


# ---------- demo ----------
@app.post("/api/reset")
def reset() -> dict:
    """Start a fresh shift with new sample trucks."""
    global warehouse
    warehouse = Warehouse.seeded()
    return warehouse.snapshot()
