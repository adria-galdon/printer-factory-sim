from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.database import init_db
from api.routers import catalog, inventory, log, orders, purchase, simulation


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create tables and seed data on startup (idempotent)."""
    init_db(seed=True)
    yield


app = FastAPI(
    title="3D Printer Factory Simulator",
    description=(
        "Day-by-day production simulation: inventory management, "
        "purchasing, and manufacturing order planning."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# Allow the Streamlit UI (runs on a different port) to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501", "http://127.0.0.1:8501"],
    allow_methods=["*"],
    allow_headers=["*"],
)

PREFIX = "/api/v1"

app.include_router(catalog.router,    prefix=PREFIX)
app.include_router(inventory.router,  prefix=PREFIX)
app.include_router(orders.router,     prefix=PREFIX)
app.include_router(purchase.router,   prefix=PREFIX)
app.include_router(simulation.router, prefix=PREFIX)
app.include_router(log.router,        prefix=PREFIX)


@app.get("/", include_in_schema=False)
def root():
    return {"message": "3D Printer Factory Simulator API", "docs": "/docs"}
