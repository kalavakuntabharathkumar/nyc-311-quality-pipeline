"""
Database connection management and schema initialization for NYC 311 pipeline.

Handles:
- SQLAlchemy engine/session management with connection pooling
- Raw schema creation (raw.nyc_311_requests)
- Curated schema management (delegated to dbt)
- Idempotent upsert operations for incremental loads
"""

import os
import logging
from contextlib import contextmanager
from typing import Generator, Optional, List, Dict, Any
from datetime import datetime

from sqlalchemy import (
    create_engine,
    Engine,
    text,
    MetaData,
    Table,
    Column,
    String,
    DateTime,
    Integer,
    Float,
    Boolean,
    Text,
    Index,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
from sqlalchemy.exc import SQLAlchemyError, OperationalError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

import structlog

logger = structlog.get_logger(__name__)


def get_database_url(config: dict) -> str:
    """Build PostgreSQL connection URL from config."""
    db = config["database"]
    password = os.getenv("PGPASSWORD", db.get("password", ""))
    return f"postgresql+psycopg2://{db['user']}:{password}@{db['host']}:{db['port']}/{db['database']}"


def create_engine_with_pool(config: dict) -> Engine:
    """Create SQLAlchemy engine with connection pooling."""
    url = get_database_url(config)
    engine = create_engine(
        url,
        poolclass=QueuePool,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
        pool_recycle=3600,
        echo=config.get("database", {}).get("echo_sql", False),
    )
    
    # Log slow queries
    @event.listens_for(engine, "before_cursor_execute")
    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        conn.info.setdefault("query_start_time", []).append(datetime.utcnow())
    
    @event.listens_for(engine, "after_cursor_execute")
    def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        total = datetime.utcnow() - conn.info["query_start_time"].pop(-1)
        if total.total_seconds() > 5:
            logger.warning("slow_query", duration_seconds=total.total_seconds(), query=statement[:200])
    
    return engine


class DatabaseManager:
    """Manages database connections and schema operations."""
    
    def __init__(self, config: dict):
        self.config = config
        self.engine: Optional[Engine] = None
        self.SessionLocal: Optional[sessionmaker] = None
        self._metadata = MetaData()
    
    def initialize(self) -> None:
        """Initialize engine and create raw schema if not exists."""
        self.engine = create_engine_with_pool(self.config)
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False)
        self._create_raw_schema()
        logger.info("database_initialized")
    
    def _create_raw_schema(self) -> None:
        """Create raw schema and nyc_311_requests table."""
        with self.engine.begin() as conn:
            # Create schemas
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS raw"))
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS curated"))
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS staging"))
            
            # Raw table with all API fields as text initially
            # dbt will handle typed transformations
            raw_table_sql = """
            CREATE TABLE IF NOT EXISTS raw.nyc_311_requests (
                unique_key VARCHAR(50) PRIMARY KEY,
                created_date TIMESTAMPTZ,
                closed_date TIMESTAMPTZ,
                agency VARCHAR(100),
                agency_name VARCHAR(200),
                complaint_type VARCHAR(200),
                descriptor VARCHAR(500),
                location_type VARCHAR(50),
                incident_zip VARCHAR(10),
                incident_address VARCHAR(500),
                street_name VARCHAR(200),
                cross_street_1 VARCHAR(200),
                cross_street_2 VARCHAR(200),
                city VARCHAR(100),
                borough VARCHAR(50),
                latitude DOUBLE PRECISION,
                longitude DOUBLE PRECISION,
                location JSONB,
                status VARCHAR(50),
                resolution_description TEXT,
                resolution_action_updated_date TIMESTAMPTZ,
                community_board VARCHAR(10),
                council_district VARCHAR(10),
                census_tract VARCHAR(20),
                bin VARCHAR(20),
                bbl VARCHAR(20),
                nta VARCHAR(10),
                raw_payload JSONB,
                ingested_at TIMESTAMPTZ DEFAULT NOW(),
                batch_id VARCHAR(50)
            )
            """
            conn.execute(text(raw_table_sql))
            
            # Indexes for incremental query performance
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_nyc311_created_date 
                ON raw.nyc_311_requests (created_date DESC)
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_nyc311_agency 
                ON raw.nyc_311_requests (agency)
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_nyc311_borough 
                ON raw.nyc_311_requests (borough)
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_nyc311_status 
                ON raw.nyc_311_requests (status)
            """))
            
            logger.info("raw_schema_created")
    
    @contextmanager
    def session(self) -> Generator[Session, None, None]:
        """Provide a transactional scope around a series of operations."""
        if not self.SessionLocal:
            self.initialize()
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    
    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(OperationalError),
        reraise=True
    )
    def upsert_records(self, records: List[Dict[str, Any]], batch_id: str) -> int:
        """
        Upsert records into raw.nyc_311_requests.
        Returns number of records inserted/updated.
        """
        if not records:
            return 0
        
        # Add ingestion metadata
        for record in records:
            record["ingested_at"] = datetime.utcnow()
            record["batch_id"] = batch_id
        
        # Build upsert query using ON CONFLICT
        columns = list(records[0].keys())
        column_names = ", ".join(columns)
        placeholders = ", ".join([f":{col}" for col in columns])
        update_cols = ", ".join([f"{col} = EXCLUDED.{col}" for col in columns if col != "unique_key"])
        
        sql = f"""
        INSERT INTO raw.nyc_311_requests ({column_names})
        VALUES ({placeholders})
        ON CONFLICT (unique_key) DO UPDATE SET {update_cols}
        """
        
        with self.session() as session:
            result = session.execute(text(sql), records)
            logger.info("upsert_complete", record_count=len(records), batch_id=batch_id)
            return len(records)
    
    def get_max_created_date(self) -> Optional[datetime]:
        """Get maximum created_date for incremental loading."""
        with self.session() as session:
            result = session.execute(text("""
                SELECT MAX(created_date) FROM raw.nyc_311_requests
            """)).scalar()
            return result
    
    def get_record_count(self, since: Optional[datetime] = None) -> int:
        """Get record count, optionally filtered by date."""
        with self.session() as session:
            if since:
                result = session.execute(text("""
                    SELECT COUNT(*) FROM raw.nyc_311_requests WHERE created_date >= :since
                """), {"since": since}).scalar()
            else:
                result = session.execute(text("SELECT COUNT(*) FROM raw.nyc_311_requests")).scalar()
            return result or 0
    
    def execute_raw_sql(self, sql: str, params: Optional[dict] = None) -> Any:
        """Execute raw SQL for maintenance tasks."""
        with self.session() as session:
            return session.execute(text(sql), params or {})
    
    def close(self) -> None:
        """Close engine connections."""
        if self.engine:
            self.engine.dispose()
            logger.info("database_closed")


def init_database(config: dict) -> DatabaseManager:
    """Factory function to initialize database manager."""
    db = DatabaseManager(config)
    db.initialize()
    return db


if __name__ == "__main__":
    import yaml
    import sys
    
    logging.basicConfig(level=logging.INFO)
    
    with open("config.yaml", "r") as f:
        config = yaml.safe_load(f)
    
    if len(sys.argv) > 1 and sys.argv[1] == "init":
        db = init_database(config)
        print(f"Database initialized. Raw table count: {db.get_record_count()}")
        db.close()
    else:
        print("Usage: python -m src.database init")