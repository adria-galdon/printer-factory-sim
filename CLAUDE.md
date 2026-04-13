# CLAUDE.md — 3D Printer Factory Production Simulator

## Current State
**M0 in progress — scaffolding and DB setup**

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11+ |
| API | FastAPI + Uvicorn |
| UI | Streamlit |
| Database | SQLite via SQLAlchemy (sync, not async) |
| Simulation engine | SimPy |
| API client (UI→API) | httpx |
| Validation | Pydantic v2 |
| Testing | pytest |

---

## Project Structure

```
printer-factory-sim/
├── api/
│   ├── main.py               # FastAPI app, lifespan, CORS
│   ├── database.py           # SQLAlchemy engine, session factory
│   ├── models.py             # ORM models (SQLAlchemy)
│   ├── schemas.py            # Pydantic schemas (request/response)
│   ├── routers/
│   │   ├── orders.py         # Manufacturing orders
│   │   ├── purchase.py       # Purchase orders
│   │   ├── inventory.py      # Inventory reads
│   │   ├── catalog.py        # Suppliers, products, price tiers
│   │   ├── simulation.py     # Advance day, reset, state
│   │   ├── log.py            # Event log query
│   │   └── io.py             # Import / export JSON
│   └── services/
│       ├── simulation.py     # advance_day() orchestrator (SimPy)
│       ├── demand.py         # Random demand generation
│       ├── production.py     # Order fulfillment logic
│       ├── purchasing.py     # PO issuance + arrival
│       └── inventory.py      # Stock checks, consume, restock
├── ui/
│   ├── app.py                # Streamlit entrypoint
│   ├── api_client.py         # httpx wrapper for all API calls
│   └── pages/
│       ├── 1_Dashboard.py
│       ├── 2_Orders.py
│       ├── 3_Purchasing.py
│       ├── 4_Log.py
│       └── 5_Config.py
├── seed/
│   └── initial_config.json   # BOM, models, suppliers, warehouse config
├── tests/
│   ├── test_simulation.py
│   ├── test_production.py
│   └── test_purchasing.py
├── printer_factory.db        # Auto-created on first run
├── CLAUDE.md
├── PRD.md
├── requirements.txt
└── README.md
```

---

## Architecture

- **Streamlit calls FastAPI** via `httpx` — the UI never touches the DB directly. This enforces API parity (R8): every action available in the UI is also available via the REST API.
- **FastAPI** handles all business logic through service modules. Routers are thin — they validate input and delegate to services.
- **SimPy** orchestrates the daily event sequence inside `advance_day()`. Event order: demand generation → purchase arrivals → production run → day close.
- **SQLAlchemy sync** sessions — one session per request via a FastAPI dependency. No async ORM; SQLite + single process makes this unnecessary.
- **Pydantic v2** schemas are separate from SQLAlchemy ORM models. Never return ORM objects directly from routers.

---

## Data Model Summary

Key relationships:
- `printer_models` ←→ `materials` via `bom_lines` (many-to-many; shared components across models)
- `inventory` is 1:1 with `materials` — flat quantity pool, no per-lot traceability
- `supplier_products` has child `price_tiers` — multiple pricing tiers per product (box, pallet, etc.)
- `manufacturing_orders` tracks `quantity_ordered` vs `quantity_completed` for multi-day partial fulfillment
- `simulation_state` is a singleton row (id=1) — holds `current_day`, `daily_capacity`, `capacity_used_today`
- `event_log` records every state transition with a JSON `payload` blob

Order statuses: `pending` → `in_production` → `completed` (or `blocked` if stock is zero)
Purchase order statuses: `in_transit` → `delivered`

---

## Day Simulation Cycle

`POST /api/v1/simulation/advance` triggers this sequence via SimPy:

1. **Demand generation** — sample Normal(μ, σ²) clipped at 0 per printer model → create `ManufacturingOrder` records
2. **Purchase arrivals** — deliver all POs where `expected_arrival_day == current_day` → restock inventory
3. **Production run** — FIFO across released orders; consume materials; track partial completion against daily capacity cap
4. **Day close** — increment `current_day`, reset `capacity_used_today`

---

## API Conventions

- All endpoints prefixed `/api/v1`
- Return Pydantic response models — never raw ORM objects
- Use HTTP 409 for business logic conflicts (e.g., releasing an already-released order)
- Use HTTP 422 (FastAPI default) for validation errors
- All list endpoints support `status` filter query param where applicable
- Event log entries are written by service functions, not routers

---

## Coding Conventions

- **One concern per service** — `demand.py` only generates demand; `production.py` only handles fulfillment logic
- **No business logic in routers** — routers validate, call one service function, return the result
- **No direct DB access in UI** — `ui/api_client.py` is the only place that calls the API; pages import from there
- **Seed data** lives in `seed/initial_config.json` and is loaded by `database.py` on first run (when DB is empty)
- **Tests** use a separate in-memory SQLite DB — never the development `printer_factory.db`
- Keep SimPy usage simple — use it for ordered event sequencing within `advance_day`, not for long-running processes

---

## Running the Project

```bash
# Install dependencies
pip install -r requirements.txt

# Start the API (auto-creates and seeds DB on first run)
uvicorn api.main:app --reload --port 8000

# Start the UI (in a separate terminal)
streamlit run ui/app.py

# API docs
open http://localhost:8000/docs

# Run tests
pytest tests/
```
