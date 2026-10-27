# StockFlow

StockFlow is a returns-center inventory and order management system built with Python, FastAPI, and PostgreSQL. It tracks returns, product conditions, inventory, and orders while ensuring reliable transactions and audit logs. Built with synthetic data, with plans for automated testing and AWS deployment.

## Current status

The first milestone includes a FastAPI service for recording returned items, recording inspection/disposition decisions, viewing sellable inventory, and reading audit logs. Data is currently stored in memory and resets when the server restarts. PostgreSQL persistence, order reservations, and transaction-safe concurrent updates are planned next.

## Run locally

1. Install Python 3.11 or newer.
2. Create and activate a virtual environment.
3. Install dependencies:

   ```bash
   python -m pip install -r requirements.txt
   ```

4. Start the API from the repository root:

   ```bash
   uvicorn app.main:app --reload
   ```

5. Open `http://127.0.0.1:8000/docs` to explore the interactive API documentation.

## Run tests

```bash
pytest
```

## Planned features

- Return inspection and explicit disposition decisions before restocking
- Inventory tracking that separates sellable and non-sellable stock
- Order management and safe stock reservations
- Database transactions and audit logs
- Automated tests and eventual AWS deployment

All sample records are synthetic and are not connected to any employer system or proprietary data.
