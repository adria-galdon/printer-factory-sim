"""
SQLAlchemy engine, session factory, and DB initialisation.

Run as a script to create all tables and load seed data:
    python -m api.database
"""

import json
import logging
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from api.models import (
    Base,
    BOMLine,
    Inventory,
    Material,
    PriceTier,
    PrinterModel,
    SimulationState,
    Supplier,
    SupplierProduct,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Engine & session factory
# ---------------------------------------------------------------------------

DB_PATH = Path(__file__).parent.parent / "printer_factory.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)

# Enable WAL mode and foreign-key enforcement for every new connection
@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_conn, _connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency — yields a DB session and closes it afterwards."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------

SEED_PATH = Path(__file__).parent.parent / "seed" / "initial_config.json"


def _load_seed(db: Session, config: dict) -> None:
    """Populate all reference tables from the seed config dict."""

    sim_cfg = config["simulation"]

    # SimulationState singleton
    if not db.get(SimulationState, 1):
        db.add(SimulationState(
            id=1,
            current_day=1,
            daily_capacity=sim_cfg["daily_capacity"],
            capacity_used_today=0,
        ))
        logger.info("Created SimulationState (daily_capacity=%d)", sim_cfg["daily_capacity"])

    # Materials + Inventory
    warehouse_cap = sim_cfg.get("warehouse_capacity")
    for m in config["materials"]:
        if not db.get(Material, m["id"]):
            db.add(Material(id=m["id"], name=m["name"], unit=m["unit"]))
            db.add(Inventory(
                material_id=m["id"],
                quantity=0,
                warehouse_capacity=warehouse_cap,
            ))
            logger.info("Created material: %s", m["id"])

    db.flush()

    # Printer models + BOMs
    for pm in config["printer_models"]:
        if not db.get(PrinterModel, pm["id"]):
            db.add(PrinterModel(
                id=pm["id"],
                name=pm["name"],
                assembly_time_days=pm["assembly_time_days"],
                demand_mean=pm["demand_mean"],
                demand_variance=pm["demand_variance"],
            ))
            for line in pm["bom"]:
                db.add(BOMLine(
                    printer_model_id=pm["id"],
                    material_id=line["material_id"],
                    quantity_per_unit=line["quantity_per_unit"],
                ))
            logger.info("Created printer model: %s (%d BOM lines)", pm["id"], len(pm["bom"]))

    db.flush()

    # Suppliers + SupplierProducts + PriceTiers
    for sup in config["suppliers"]:
        if not db.get(Supplier, sup["id"]):
            db.add(Supplier(
                id=sup["id"],
                name=sup["name"],
                lead_time_days=sup["lead_time_days"],
            ))
            for prod in sup["products"]:
                db.add(SupplierProduct(
                    id=prod["id"],
                    supplier_id=sup["id"],
                    material_id=prod["material_id"],
                    description=prod["description"],
                ))
                for tier in prod["price_tiers"]:
                    db.add(PriceTier(
                        supplier_product_id=prod["id"],
                        min_quantity=tier["min_quantity"],
                        unit_price=tier["unit_price"],
                        lot_size=tier.get("lot_size"),
                        label=tier.get("label"),
                    ))
            logger.info(
                "Created supplier: %s (%d products)", sup["id"], len(sup["products"])
            )

    db.commit()
    logger.info("Seed data loaded successfully.")


# ---------------------------------------------------------------------------
# Public init function
# ---------------------------------------------------------------------------

def init_db(seed: bool = True) -> None:
    """Create all tables.  If *seed* is True and the DB is empty, load seed data."""
    Base.metadata.create_all(bind=engine)
    logger.info("Tables created (or already exist).")

    if not seed:
        return

    with SessionLocal() as db:
        # Only seed if SimulationState doesn't exist yet (fresh DB)
        if db.get(SimulationState, 1) is not None:
            logger.info("DB already seeded — skipping.")
            return

        if not SEED_PATH.exists():
            logger.warning("Seed file not found at %s — skipping seed.", SEED_PATH)
            return

        config = json.loads(SEED_PATH.read_text(encoding="utf-8"))
        _load_seed(db, config)


# ---------------------------------------------------------------------------
# Script entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s  %(message)s",
    )
    logger.info("Initialising database at %s", DB_PATH)
    init_db(seed=True)
    logger.info("Done.")
