"""
NYC 311 API Ingestion Module

Handles:
- SODA API client with pagination and rate limiting
- Incremental loading using created_date cursor
- Error handling with exponential backoff retries
- Dead letter queue for failed batches
- Batch streaming to avoid memory pressure
"""

import os
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Generator, List, Dict, Any, Optional
from dataclasses import dataclass
from urllib.parse import urlencode

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import structlog

from src.database import DatabaseManager

logger = structlog.get_logger(__name__)


@dataclass
class IngestionConfig:
    base_url: str
    app_token: Optional[str] = None
    batch_size: int = 50000
    max_retries: int = 3
    retry_backoff_seconds: float = 5.0
    timeout_seconds: int = 60
    lookback_days: int = 7


@dataclass
class IngestionStats:
    total_fetched: int = 0
    total_upserted: int = 0
    total_failed: int = 0
    batches_processed: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    errors: List[str] = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []
    
    @property
    def duration_seconds(self) -> float:
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0


class NYC311APIClient:
    """Client for NYC Open Data 311 Service Requests API."""
    
    def __init__(self, config: IngestionConfig):
        self.config = config
        self.session = self._create_session()
    
    def _create_session(self) -> requests.Session:
        """Create requests session with retry strategy."""
        session = requests.Session()
        retry_strategy = Retry(
            total=self.config.max_retries,
            backoff_factor=self.config.retry_backoff_seconds,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
            raise_on_status=False
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session
    
    def _build_params(self, since: Optional[datetime] = None, limit: int = None, offset: int = 0) -> dict:
        """Build SODA API query parameters."""
        params = {
            "$limit": limit or self.config.batch_size,
            "$offset": offset,
            "$order": "created_date ASC",  # Deterministic ordering for pagination
            "$select": "unique_key,created_date,closed_date,agency,agency_name,complaint_type,descriptor,location_type,incident_zip,incident_address,street_name,cross_street_1,cross_street_2,city,borough,latitude,longitude,location,status,resolution_description,resolution_action_updated_date,community_board,council_district,census_tract,bin,bbl,nta",
        }
        
        if since:
            # SODA expects ISO 8601 format
            since_str = since.strftime("%Y-%m-%dT%H:%M:%S")
            params["$where"] = f"created_date >= '{since_str}'"
        
        if self.config.app_token:
            params["$$app_token"] = self.config.app_token
        
        return params
    
    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type((requests.RequestException, requests.Timeout)),
        reraise=True
    )
    def fetch_batch(self, since: Optional[datetime] = None, offset: int = 0) -> List[Dict[str, Any]]:
        """Fetch a single batch of records from the API."""
        params = self._build_params(since=since, offset=offset)
        url = f"{self.config.base_url}?{urlencode(params)}"
        
        logger.debug("api_request", url=url[:200])
        response = self.session.get(url, timeout=self.config.timeout_seconds)
        
        if response.status_code == 429:
            # Rate limited - respect Retry-After header
            retry_after = int(response.headers.get("Retry-After", self.config.retry_backoff_seconds))
            logger.warning("rate_limited", retry_after=retry_after)
            time.sleep(retry_after)
            raise requests.RequestException("Rate limited")
        
        response.raise_for_status()
        data = response.json()
        
        logger.debug("api_response", record_count=len(data))
        return data
    
    def fetch_incremental(self, since: Optional[datetime] = None) -> Generator[List[Dict[str, Any]], None, None]:
        """Generator yielding batches of records since a given date."""
        offset = 0
        while True:
            batch = self.fetch_batch(since=since, offset=offset)
            if not batch:
                break
            yield batch
            offset += len(batch)
            # Safety check - API max offset is typically 50000
            if offset >= 1000000:
                logger.warning("offset_limit_reached", offset=offset)
                break
    
    def close(self):
        self.session.close()


class IngestionPipeline:
    """Orchestrates the full ingestion process."""
    
    def __init__(self, db: DatabaseManager, config: IngestionConfig):
        self.db = db
        self.config = config
        self.client = NYC311APIClient(config)
        self.stats = IngestionStats()
        self.dead_letter_queue: List[Dict[str, Any]] = []
    
    def run_incremental(self) -> IngestionStats:
        """Run incremental ingestion for the lookback window."""
        self.stats.start_time = datetime.utcnow()
        
        # Determine lookback window
        since = self.db.get_max_created_date()
        if since:
            # Subtract lookback days to catch late-arriving updates
            since = since - timedelta(days=self.config.lookback_days)
            logger.info("incremental_ingestion_start", since=since.isoformat())
        else:
            # First run - fetch last 30 days by default
            since = datetime.utcnow() - timedelta(days=30)
            logger.info("initial_ingestion_start", since=since.isoformat())
        
        batch_id = f"batch_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}
        
        try:
            for batch in self.client.fetch_incremental(since=since):
                self.stats.batches_processed += 1
                self.stats.total_fetched += len(batch)
                
                try:
                    upserted = self.db.upsert_records(batch, batch_id)
                    self.stats.total_upserted += upserted
                    logger.info("batch_processed", batch_num=self.stats.batches_processed, records=len(batch))
                except Exception as e:
                    self.stats.total_failed += len(batch)
                    self.stats.errors.append(f"Batch {self.stats.batches_processed}: {str(e)}")
                    # Add to dead letter queue
                    for record in batch:
                        record["_error"] = str(e)
                        record["_batch_id"] = batch_id
                    self.dead_letter_queue.extend(batch)
                    logger.error("batch_failed", batch_num=self.stats.batches_processed, error=str(e))
        
        finally:
            self.client.close()
            self.stats.end_time = datetime.utcnow()
        
        self._log_summary()
        return self.stats
    
    def run_full(self, start_date: datetime) -> IngestionStats:
        """Run full historical ingestion from a start date."""
        self.stats.start_time = datetime.utcnow()
        logger.info("full_ingestion_start", start_date=start_date.isoformat())
        
        batch_id = f"full_load_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}
        
        try:
            for batch in self.client.fetch_incremental(since=start_date):
                self.stats.batches_processed += 1
                self.stats.total_fetched += len(batch)
                
                try:
                    upserted = self.db.upsert_records(batch, batch_id)
                    self.stats.total_upserted += upserted
                    
                    if self.stats.batches_processed % 10 == 0:
                        logger.info("progress", batches=self.stats.batches_processed, total_records=self.stats.total_upserted)
                except Exception as e:
                    self.stats.total_failed += len(batch)
                    self.stats.errors.append(f"Batch {self.stats.batches_processed}: {str(e)}")
                    for record in batch:
                        record["_error"] = str(e)
                    self.dead_letter_queue.extend(batch)
        
        finally:
            self.client.close()
            self.stats.end_time = datetime.utcnow()
        
        self._log_summary()
        return self.stats
    
    def _log_summary(self) -> None:
        logger.info(
            "ingestion_complete",
            total_fetched=self.stats.total_fetched,
            total_upserted=self.stats.total_upserted,
            total_failed=self.stats.total_failed,
            batches=self.stats.batches_processed,
            duration_seconds=round(self.stats.duration_seconds, 2),
            records_per_second=round(self.stats.total_upserted / max(self.stats.duration_seconds, 1), 2)
        )
        
        if self.dead_letter_queue:
            logger.warning("dead_letter_records", count=len(self.dead_letter_queue))
            # Could write to file/table for later inspection
    
    def get_dead_letter_records(self) -> List[Dict[str, Any]]:
        return self.dead_letter_queue


def create_ingestion_pipeline(db: DatabaseManager, config: dict) -> IngestionPipeline:
    """Factory function to create ingestion pipeline from config."""
    ingestion_config = IngestionConfig(
        base_url=config["api"]["base_url"],
        app_token=config["api"].get("app_token"),
        batch_size=config["api"].get("batch_size", 50000),
        max_retries=config["pipeline"].get("max_retries", 3),
        retry_backoff_seconds=config["pipeline"].get("retry_backoff_seconds", 5.0),
        lookback_days=config["pipeline"].get("lookback_days", 7),
    )
    return IngestionPipeline(db, ingestion_config)


if __name__ == "__main__":
    import yaml
    import sys
    
    logging.basicConfig(level=logging.INFO)
    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.INFO))
    
    with open("config.yaml", "r") as f:
        config = yaml.safe_load(f)
    
    db = DatabaseManager(config)
    db.initialize()
    
    pipeline = create_ingestion_pipeline(db, config)
    
    if len(sys.argv) > 1 and sys.argv[1] == "full":
        start_date = datetime(2023, 1, 1)
        if len(sys.argv) > 2:
            start_date = datetime.fromisoformat(sys.argv[2])
        stats = pipeline.run_full(start_date)
    else:
        stats = pipeline.run_incremental()
    
    print(f"Ingestion complete: {stats.total_upserted} records upserted in {stats.duration_seconds:.1f}s")
    db.close()