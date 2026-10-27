from datetime import datetime, timezone
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(
    title="StockFlow API",
    description="A learning project for returns-center inventory and order management.",
    version="0.2.0",
)

Condition = Literal["new", "used_like_new", "used", "damaged"]
Disposition = Literal["pending_inspection", "restock", "repair", "liquidate", "discard"]


class ReturnItemCreate(BaseModel):
    product_name: str = Field(min_length=1, max_length=120)
    condition: Condition
    quantity: int = Field(default=1, ge=1, le=1000)


class ReturnItem(BaseModel):
    id: int
    product_name: str
    condition: Condition
    disposition: Disposition = "pending_inspection"
    quantity: int


class DispositionDecision(BaseModel):
    disposition: Literal["restock", "repair", "liquidate", "discard"]
    reason: str = Field(min_length=3, max_length=300)


class AuditEvent(BaseModel):
    event_id: int
    return_id: int
    event_type: str
    details: str
    created_at: str


# In-memory storage for the first milestone. Data resets when the server restarts.
# PostgreSQL persistence is a planned next step.
returns: dict[int, ReturnItem] = {
    1: ReturnItem(
        id=1,
        product_name="Wireless Mouse",
        condition="new",
        disposition="pending_inspection",
        quantity=2,
    )
}
sellable_inventory: dict[str, int] = {}
audit_events: list[AuditEvent] = []
next_return_id = 2
next_event_id = 1


def record_audit_event(return_id: int, event_type: str, details: str) -> None:
    global next_event_id
    audit_events.append(
        AuditEvent(
            event_id=next_event_id,
            return_id=return_id,
            event_type=event_type,
            details=details,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
    )
    next_event_id += 1


@app.get("/")
def read_root() -> dict[str, str]:
    """Confirm the API is running."""
    return {"message": "Welcome to StockFlow API", "docs": "/docs"}


@app.get("/health")
def health_check() -> dict[str, str]:
    """Simple health endpoint for local checks and future deployment."""
    return {"status": "ok"}


@app.get("/returns", response_model=list[ReturnItem])
def list_returns() -> list[ReturnItem]:
    """List returned items awaiting or completing inspection."""
    return list(returns.values())


@app.post("/returns", response_model=ReturnItem, status_code=201)
def create_return(payload: ReturnItemCreate) -> ReturnItem:
    """Record a returned item; it is never sellable before a decision."""
    global next_return_id
    item = ReturnItem(
        id=next_return_id,
        product_name=payload.product_name,
        condition=payload.condition,
        disposition="pending_inspection",
        quantity=payload.quantity,
    )
    returns[item.id] = item
    record_audit_event(item.id, "return_received", f"Received {item.quantity} x {item.product_name}")
    next_return_id += 1
    return item


@app.get("/returns/{return_id}", response_model=ReturnItem)
def get_return(return_id: int) -> ReturnItem:
    """Fetch one returned item by its ID."""
    item = returns.get(return_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Return item not found")
    return item


@app.post("/returns/{return_id}/disposition", response_model=ReturnItem)
def decide_disposition(return_id: int, decision: DispositionDecision) -> ReturnItem:
    """Record an inspection decision; only restock decisions increase sellable stock."""
    item = returns.get(return_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Return item not found")
    if item.disposition != "pending_inspection":
        raise HTTPException(
            status_code=409,
            detail="A disposition has already been recorded for this return",
        )
    if decision.disposition == "restock" and item.condition == "damaged":
        raise HTTPException(
            status_code=422,
            detail="Damaged items cannot be restocked; choose another disposition",
        )

    updated_item = item.model_copy(update={"disposition": decision.disposition})
    returns[return_id] = updated_item

    if decision.disposition == "restock":
        sellable_inventory[item.product_name] = (
            sellable_inventory.get(item.product_name, 0) + item.quantity
        )

    record_audit_event(
        return_id,
        "disposition_decided",
        f"Disposition={decision.disposition}; reason={decision.reason}; quantity={item.quantity}",
    )
    return updated_item


@app.get("/inventory")
def get_inventory() -> dict[str, dict[str, int]]:
    """Show sellable inventory only; items pending inspection are excluded."""
    return {
        "sellable_stock": dict(sorted(sellable_inventory.items())),
    }


@app.get("/audit-logs", response_model=list[AuditEvent])
def get_audit_logs() -> list[AuditEvent]:
    """List recorded return and disposition events in creation order."""
    return list(audit_events)
