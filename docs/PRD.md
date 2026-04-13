# Product Requirements Document
## 3D Printer Factory Production Simulator

**Version:** 1.0
**Date:** 2026-03-26
**Stack:** Python 3.11+, FastAPI, Streamlit, SQLite, SimPy

---

## 1. Overview

A local desktop simulation tool that models, day by day, the full production cycle of a factory manufacturing 3D printers. The user acts as production planner: reviewing demand, releasing orders to production, and issuing purchase orders. All simulation state persists in SQLite. Every action available in the UI is also exposed via a REST API.

---

## 2. Data Model

### 2.1 Entity Relationship Summary

```
Material ──< BOMLine >── PrinterModel
PrinterModel ──< ManufacturingOrder
Material ──< Inventory (1:1)
Supplier ──< SupplierProduct >── Material
SupplierProduct ──< PriceTier
ManufacturingOrder ──< ManufacturingOrderLine (per material consumed)
PurchaseOrder ──< PurchaseOrderLine >── SupplierProduct
SimulationState (singleton)
EventLog
```

### 2.2 Tables

#### `materials`
| Column | Type | Notes |
|---|---|---|
| id | TEXT PK | e.g. `kit_piezas` |
| name | TEXT | Display name |
| unit | TEXT | e.g. `unit`, `reel` |

#### `inventory`
| Column | Type | Notes |
|---|---|---|
| material_id | TEXT PK FK→materials | |
| quantity | INTEGER | Current stock (flat pool) |
| warehouse_capacity | INTEGER | NULL = unlimited |

#### `printer_models`
| Column | Type | Notes |
|---|---|---|
| id | TEXT PK | e.g. `P3D-Classic` |
| name | TEXT | |
| assembly_time_days | REAL | Fractional days of capacity consumed per unit |
| demand_mean | REAL | μ for daily Poisson/Normal demand |
| demand_variance | REAL | σ² for daily demand |

#### `bom_lines`
| Column | Type | Notes |
|---|---|---|
| printer_model_id | TEXT FK→printer_models | |
| material_id | TEXT FK→materials | |
| quantity_per_unit | INTEGER | |
| PRIMARY KEY | (printer_model_id, material_id) | |

#### `suppliers`
| Column | Type | Notes |
|---|---|---|
| id | TEXT PK | |
| name | TEXT | |
| lead_time_days | INTEGER | Fixed delivery lag |

#### `supplier_products`
| Column | Type | Notes |
|---|---|---|
| id | TEXT PK | |
| supplier_id | TEXT FK→suppliers | |
| material_id | TEXT FK→materials | |
| description | TEXT | |

#### `price_tiers`
| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK autoincrement | |
| supplier_product_id | TEXT FK→supplier_products | |
| min_quantity | INTEGER | Lower bound of tier (inclusive) |
| unit_price | REAL | Price per unit at this tier |
| lot_size | INTEGER | e.g. 20 (box), 1000 (pallet); NULL = any |
| label | TEXT | e.g. `box of 20`, `pallet of 1000` |

#### `manufacturing_orders`
| Column | Type | Notes |
|---|---|---|
| id | TEXT PK | UUID |
| printer_model_id | TEXT FK→printer_models | |
| quantity_ordered | INTEGER | Original demand |
| quantity_completed | INTEGER | Default 0 |
| status | TEXT | `pending` / `in_production` / `completed` / `blocked` |
| created_day | INTEGER | Simulation day generated |
| released_day | INTEGER | Day user released to production |
| completed_day | INTEGER | Day fully completed |

#### `purchase_orders`
| Column | Type | Notes |
|---|---|---|
| id | TEXT PK | UUID |
| supplier_product_id | TEXT FK→supplier_products | |
| quantity | INTEGER | |
| unit_price | REAL | Locked at order time |
| total_price | REAL | |
| issued_day | INTEGER | Simulation day issued |
| expected_arrival_day | INTEGER | issued_day + lead_time_days |
| status | TEXT | `in_transit` / `delivered` |

#### `event_log`
| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK autoincrement | |
| day | INTEGER | Simulation day |
| event_type | TEXT | See §2.3 |
| entity_type | TEXT | `manufacturing_order`, `purchase_order`, `inventory`, `simulation` |
| entity_id | TEXT | |
| payload | TEXT | JSON blob with details |
| timestamp | TEXT | ISO-8601 wall-clock time |

#### `simulation_state` (singleton, id=1)
| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | Always 1 |
| current_day | INTEGER | Starts at 1 |
| daily_capacity | INTEGER | Max printers assembled per day |
| capacity_used_today | INTEGER | Reset each Advance Day |

### 2.3 Event Types
```
demand.generated
order.released
order.partially_completed
order.completed
order.blocked
purchase.issued
purchase.delivered
inventory.consumed
inventory.restocked
day.advanced
simulation.reset
simulation.imported
```

---

## 3. Architecture

```
┌──────────────────────────────────────────────────────┐
│                    Streamlit UI                      │
│  (pages: Dashboard, Orders, Purchasing, Log, Config) │
└─────────────────────┬────────────────────────────────┘
                      │ HTTP (localhost)
┌─────────────────────▼────────────────────────────────┐
│                  FastAPI App                         │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────┐ │
│  │   Routers   │  │   Services   │  │  Schemas    │ │
│  │  /orders    │  │  simulation  │  │  Pydantic   │ │
│  │  /purchase  │  │  inventory   │  │  models     │ │
│  │  /inventory │  │  purchasing  │  └─────────────┘ │
│  │  /catalog   │  │  demand      │                  │
│  │  /simulation│  └──────┬───────┘                  │
│  │  /log       │         │                          │
│  │  /io        │  ┌──────▼───────┐                  │
│  └─────────────┘  │  SimPy Engine│                  │
│                   │  (day cycle) │                  │
│                   └──────┬───────┘                  │
└──────────────────────────┼───────────────────────────┘
                           │ SQLAlchemy (sync)
┌──────────────────────────▼───────────────────────────┐
│                   SQLite DB                          │
│              printer_factory.db                      │
└──────────────────────────────────────────────────────┘
```

### 3.1 Key Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| SimPy role | Orchestrates the daily event sequence within `advance_day` | Gives deterministic, ordered event processing without full async complexity |
| Single process | FastAPI + Streamlit share the same SQLite file | Sufficient for local tool; avoids IPC complexity |
| Streamlit calls FastAPI | UI talks to API via `httpx` | Enforces API completeness per R8; single source of truth |
| Synchronous SQLAlchemy | `create_engine` (not async) | SQLite + single process; simplifies session management |
| Pydantic v2 | Schema + validation layer | FastAPI native; clear separation of DB models (SQLAlchemy) vs API models (Pydantic) |

---

## 4. Project Structure

```
printer-factory-sim/
├── api/
│   ├── main.py               # FastAPI app, lifespan, CORS
│   ├── database.py           # SQLAlchemy engine, session factory
│   ├── models.py             # ORM models
│   ├── schemas.py            # Pydantic schemas (request/response)
│   ├── routers/
│   │   ├── orders.py         # Manufacturing orders
│   │   ├── purchase.py       # Purchase orders
│   │   ├── inventory.py      # Inventory read
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
├── requirements.txt
└── README.md
```

---

## 5. API Endpoints

All endpoints are prefixed `/api/v1`.

### 5.1 Simulation Control
| Method | Path | Description |
|---|---|---|
| GET | `/simulation/state` | Current day, capacity used/total |
| POST | `/simulation/advance` | Run one day cycle; returns event summary |
| POST | `/simulation/reset` | Wipe all state, re-seed from config |

### 5.2 Manufacturing Orders
| Method | Path | Description |
|---|---|---|
| GET | `/orders` | List all orders (filterable by status) |
| GET | `/orders/{id}` | Order detail + BOM breakdown |
| POST | `/orders/{id}/release` | Release pending order to production |
| GET | `/orders/{id}/bom` | Material requirements for this order |

### 5.3 Purchase Orders
| Method | Path | Description |
|---|---|---|
| GET | `/purchase` | List all POs (filterable by status) |
| POST | `/purchase` | Issue a new PO `{supplier_product_id, quantity}` |
| GET | `/purchase/{id}` | PO detail |

### 5.4 Inventory
| Method | Path | Description |
|---|---|---|
| GET | `/inventory` | All materials with current stock |
| GET | `/inventory/{material_id}` | Single material stock |

### 5.5 Catalog
| Method | Path | Description |
|---|---|---|
| GET | `/catalog/suppliers` | All suppliers |
| GET | `/catalog/suppliers/{id}/products` | Products for a supplier |
| GET | `/catalog/products` | All supplier products with price tiers |
| GET | `/catalog/models` | All printer models with BOM |

### 5.6 Event Log
| Method | Path | Description |
|---|---|---|
| GET | `/log` | Paginated event log (filter by day, event_type) |
| GET | `/log/summary` | Aggregated counts per event type per day |

### 5.7 Import / Export
| Method | Path | Description |
|---|---|---|
| GET | `/io/export` | Full state as JSON (inventory + orders + POs + log) |
| POST | `/io/import` | Replace state from uploaded JSON |

---

## 6. Day Simulation Cycle (`advance_day`)

Executed sequentially by the SimPy engine on `POST /simulation/advance`:

```
1. DEMAND GENERATION
   └─ For each printer model, sample demand (Normal/Poisson with configured μ, σ²)
   └─ Create ManufacturingOrder records with status=pending
   └─ Log demand.generated

2. PURCHASE ARRIVALS
   └─ Find all POs where expected_arrival_day == current_day
   └─ Add quantity to inventory for each material
   └─ Mark PO as delivered
   └─ Log purchase.delivered, inventory.restocked

3. PRODUCTION RUN
   └─ Collect all orders with status in (in_production, pending+released)
   └─ Sort by created_day ASC (FIFO)
   └─ For each order (until daily_capacity exhausted):
       a. Check available stock vs BOM requirements
       b. Compute max_producible = min(remaining_capacity, stock-constrained units)
       c. Consume materials proportionally
       d. Increment quantity_completed
       e. If fully complete → status=completed
       f. If partial → status=in_production (or blocked if 0 producible)
       g. Log order.partially_completed / order.completed / order.blocked
          and inventory.consumed

4. DAY CLOSE
   └─ Increment current_day
   └─ Reset capacity_used_today = 0
   └─ Log day.advanced
```

---

## 7. Streamlit UI Pages

### Dashboard
- KPI cards: current day, capacity used today, open orders, in-transit POs, total inventory units
- Inventory table with warning highlights (stock < 7-day demand estimate)
- Pending orders list with BOM shortfall indicators

### Orders
- Full order table with status badges
- Per-order BOM breakdown panel
- "Release to Production" button per pending order

### Purchasing
- Supplier selector → product list with price tiers
- Quantity input (with tier price calculator)
- Issue PO button
- In-transit POs table with expected arrival day

### Log
- Filterable event log table (by day range, event type)
- Line chart: units completed per day
- Bar chart: inventory levels over time

### Config
- View/edit demand parameters (μ, σ²) per model
- View BOM per model
- Export / Import JSON buttons
- Reset simulation button

---

## 8. Seed Configuration (`initial_config.json`)

```json
{
  "simulation": { "daily_capacity": 10, "warehouse_capacity": 5000 },
  "materials": [
    { "id": "kit_piezas",   "name": "Kit de piezas impresas",  "unit": "unit" },
    { "id": "extrusor",     "name": "Extrusor",                "unit": "unit" },
    { "id": "electronica",  "name": "Kit electrónico",         "unit": "unit" },
    { "id": "cama_caliente","name": "Cama caliente",           "unit": "unit" },
    { "id": "estructura",   "name": "Estructura metálica",     "unit": "unit" },
    { "id": "cables",       "name": "Kit de cables",           "unit": "unit" }
  ],
  "printer_models": [
    {
      "id": "P3D-Classic",
      "name": "P3D Classic",
      "assembly_time_days": 0.5,
      "demand_mean": 3,
      "demand_variance": 1,
      "bom": [
        { "material_id": "kit_piezas",    "quantity_per_unit": 1 },
        { "material_id": "extrusor",      "quantity_per_unit": 1 },
        { "material_id": "electronica",   "quantity_per_unit": 1 },
        { "material_id": "cama_caliente", "quantity_per_unit": 1 },
        { "material_id": "estructura",    "quantity_per_unit": 1 },
        { "material_id": "cables",        "quantity_per_unit": 1 }
      ]
    },
    {
      "id": "P3D-Pro",
      "name": "P3D Pro",
      "assembly_time_days": 1.0,
      "demand_mean": 2,
      "demand_variance": 1,
      "bom": [
        { "material_id": "kit_piezas",    "quantity_per_unit": 2 },
        { "material_id": "extrusor",      "quantity_per_unit": 2 },
        { "material_id": "electronica",   "quantity_per_unit": 1 },
        { "material_id": "cama_caliente", "quantity_per_unit": 1 },
        { "material_id": "estructura",    "quantity_per_unit": 1 },
        { "material_id": "cables",        "quantity_per_unit": 2 }
      ]
    }
  ],
  "suppliers": [
    {
      "id": "SUP-01",
      "name": "Proveedor Genérico A",
      "lead_time_days": 3,
      "products": [
        {
          "id": "SP-001", "material_id": "kit_piezas",
          "description": "Kit piezas estándar",
          "price_tiers": [
            { "min_quantity": 1,    "unit_price": 15.00, "lot_size": 1,    "label": "unidad" },
            { "min_quantity": 20,   "unit_price": 12.50, "lot_size": 20,   "label": "caja de 20" },
            { "min_quantity": 1000, "unit_price":  9.00, "lot_size": 1000, "label": "palet de 1000" }
          ]
        },
        {
          "id": "SP-002", "material_id": "extrusor",
          "description": "Extrusor estándar",
          "price_tiers": [
            { "min_quantity": 1,  "unit_price": 25.00, "lot_size": 1,  "label": "unidad" },
            { "min_quantity": 20, "unit_price": 20.00, "lot_size": 20, "label": "caja de 20" }
          ]
        }
      ]
    },
    {
      "id": "SUP-02",
      "name": "Proveedor Premium B",
      "lead_time_days": 1,
      "products": [
        {
          "id": "SP-003", "material_id": "electronica",
          "description": "Kit electrónico premium",
          "price_tiers": [
            { "min_quantity": 1,  "unit_price": 45.00, "lot_size": 1,  "label": "unidad" },
            { "min_quantity": 10, "unit_price": 38.00, "lot_size": 10, "label": "caja de 10" }
          ]
        }
      ]
    }
  ]
}
```

---

## 9. Development Plan & Milestones

### M0 — Foundation (Days 1–2)
- [ ] Repo scaffold: `api/`, `ui/`, `seed/`, `tests/`
- [ ] `requirements.txt` (fastapi, uvicorn, sqlalchemy, pydantic, simpy, streamlit, httpx, pytest)
- [ ] `database.py`: SQLAlchemy engine, session factory, `Base`
- [ ] `models.py`: all ORM models
- [ ] DB init script: create tables + load `initial_config.json`
- [ ] `schemas.py`: Pydantic request/response models

**Exit criteria:** `python -m api.database` creates a fully seeded DB.

### M1 — Core API: Catalog & Inventory (Days 3–4)
- [ ] `routers/catalog.py`: GET suppliers, products, price tiers, printer models + BOMs
- [ ] `routers/inventory.py`: GET all inventory, GET single material
- [ ] `routers/simulation.py`: GET state
- [ ] Unit tests for catalog and inventory reads

**Exit criteria:** All catalog and inventory endpoints return correct data from seeded DB; Swagger UI functional at `/docs`.

### M2 — Simulation Engine (Days 5–7)
- [ ] `services/demand.py`: sample demand per model (Normal, clipped ≥0)
- [ ] `services/purchasing.py`: PO issuance, arrival processing
- [ ] `services/production.py`: FIFO partial-fill logic, capacity tracking
- [ ] `services/simulation.py`: SimPy-orchestrated `advance_day()`
- [ ] `routers/simulation.py`: POST `/advance`, POST `/reset`
- [ ] `routers/log.py`: GET log, GET summary
- [ ] Unit tests for each service in isolation

**Exit criteria:** 10 consecutive `advance_day()` calls produce consistent, logged state transitions.

### M3 — Orders & Purchasing API (Day 8)
- [ ] `routers/orders.py`: list, detail, BOM breakdown, release
- [ ] `routers/purchase.py`: list, issue PO, detail
- [ ] Integration tests: release → advance → order progresses

**Exit criteria:** Full order lifecycle (demand → release → partial production → completion) exercised via API.

### M4 — Import / Export (Day 9)
- [ ] `routers/io.py`: GET export, POST import
- [ ] JSON schema for export format
- [ ] Test: export → reset → import → state matches

**Exit criteria:** Round-trip export/import produces identical simulation state.

### M5 — Streamlit UI (Days 10–12)
- [ ] `ui/api_client.py`: typed wrappers for all API calls
- [ ] Dashboard page
- [ ] Orders page with release action
- [ ] Purchasing page with tier calculator
- [ ] Log page with charts
- [ ] Config / IO page

**Exit criteria:** Full user workflow operable through UI without touching the API directly.

### M6 — Polish & Docs (Day 13)
- [ ] README: setup, run instructions, architecture diagram
- [ ] Error handling: meaningful HTTP errors (409 for duplicate release, 422 for bad quantities)
- [ ] Streamlit error toasts for API failures
- [ ] Final test pass; coverage ≥ 80% on services

---

## 10. Open Questions / Risks

| # | Issue | Recommendation |
|---|---|---|
| 1 | Demand distribution | Use Normal(μ, σ) clipped at 0; Poisson is an option if μ=variance is acceptable |
| 2 | Capacity model for multi-day orders | Track `assembly_time_days` per unit; deduct fractional capacity; round down to whole units produced per day |
| 3 | Concurrent Streamlit sessions | SQLite `check_same_thread=False` + connection pooling; single-user tool so contention is negligible |
| 4 | SimPy necessity | SimPy adds value if future events (machine breakdowns, rush orders) are added; for current scope it mainly provides structured event ordering — keep it but keep usage simple |
