from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Literal

app = FastAPI(
    title="StockFlow API",
    description="A learning project for returns-center inventory and order management.",
    version="0.1.0",
)

Condition = Literal["new", "used_like_new", "used", "damaged"]
Disposition = Literal["pending_inspection", "restock", "repair", "liquidate", "discard"]


class ReturnItem(BaseModel):
    id: int
    product_name: str = Field(min_length=1, max_length=120)
    condition: Condition
    disposition: Disposition = "pending_inspection"
    quantity: int = Field(default=1, ge=1, le=1000)


# Temporary in-memory sample data. This resets whenever the server restarts.
returns: dict[int, ReturnItem] = {
    1: ReturnItem(
        id=1,
        product_name="Wireless Mouse",
        condition="new",
        disposition="pending_inspection",
        quantity=2,
    )
}


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
    """List sample returned items."""
    return list(returns.values())


@app.get("/returns/{return_id}", response_model=ReturnItem)
def get_return(return_id: int) -> ReturnItem:
    """Fetch one returned item by its ID."""
    item = returns.get(return_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Return item not found")
    return item
