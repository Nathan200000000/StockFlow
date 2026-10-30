# StockFlow

StockFlow is a returns-center floor system for **IND8, Home of the Thunder**, built with Python and FastAPI. It follows every returned item from the truck it arrives on to the place it leaves: back on sale, or out to liquidation. Every action is recorded as an event, and the work is gamified with XP and levels.

All sample data is synthetic and is not connected to any employer system or proprietary data.

## The floor

```
Inbound truck (from another organization)
  -> Unload: check in at a dock door, unload boxes to staging
  -> Distribute boxes to process stations
  -> Process: open each box and route every item
       clean   -> yellow tote (sellable)
       damaged -> liquidation pallet
  -> Tranship: full yellow totes -> outbound truck -> shipped to be sold
  -> Liquidation: pallet -> shipped to the liquidation partner
```

Rules enforced by the server:

- A truck must be at a door before it is unloaded, and there are 4 doors.
- A station can have only one open box at a time.
- Damaged items can never go into a yellow tote.
- Yellow totes close automatically at 8 items (or can be closed early) and move to tranship.
- An outbound truck holds 10 totes.

## The app

Open `/dashboard`. The sidebar switches between screens without scrolling:

| Screen | What you do there |
|---|---|
| Dashboard | Welcome, your level and XP, KPIs, floor flow overview, items-processed chart, latest activity |
| Inventory | Inbound trucks from other organizations, and stock on hand by location and product |
| Unload | Dock doors, the yard, check-in, unloading, and sending staged boxes to stations |
| Process | Four stations: open boxes and route items to a yellow tote or liquidation |
| Tranship | Load full yellow totes onto the outbound truck and ship it |
| Liquidation | The open pallet, liquidation reasons, and shipped pallets |
| Activity | Live log of every event on the floor, with filters |

## Code layout

- `app/warehouse.py` – the domain model and rules (no web dependencies; tested directly)
- `app/main.py` – FastAPI routes; every action returns the full floor snapshot
- `app/static/dashboard.html` – the single-page app
- `tests/test_main.py` – API and domain tests

## API

| Method | Path | Action |
|---|---|---|
| GET | `/api/state` | Full floor snapshot |
| GET | `/api/events?after=ID` | Events newer than an ID |
| POST | `/api/trucks` | Schedule an inbound truck |
| POST | `/api/trucks/{id}/check-in` | Check a truck in at a free door |
| POST | `/api/trucks/{id}/unload` | Unload its boxes to staging |
| POST | `/api/boxes/{id}/distribute` | Send a box to a station (`{"station": 1}`) |
| POST | `/api/boxes/distribute-all` | Balance all staged boxes across stations |
| POST | `/api/boxes/{id}/open` | Open a box at its station |
| POST | `/api/items/{id}/route` | `{"destination": "yellow_tote" \| "liquidation"}` |
| POST | `/api/totes/close` | Close the current yellow tote early |
| POST | `/api/totes/{id}/load` | Load a full tote onto the outbound truck |
| POST | `/api/totes/load-all` | Load every full tote that fits |
| POST | `/api/outbound/ship` | Ship the outbound truck to be sold |
| POST | `/api/liquidation/ship` | Send the pallet to liquidation |
| POST | `/api/reset` | Start a new shift |

## Run locally

1. Install Python 3.11 or newer.
2. Create and activate a virtual environment.
3. Install dependencies:

   ```bash
   python -m pip install -r requirements.txt
   ```

4. Start the server from the repository root:

   ```bash
   uvicorn app.main:app --reload
   ```

5. Open `http://127.0.0.1:8000/dashboard`. API docs are at `/docs`.

## Run tests

```bash
pytest
```

## Next steps

- PostgreSQL persistence and transaction-safe concurrent updates
- Associate sign-in and per-person XP
- AWS deployment
