"""Unit tests for ingestion module."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

from src.ingestion import (
    NYC311APIClient,
    IngestionConfig,
    IngestionPipeline,
    IngestionStats,
)
from src.database import DatabaseManager


class TestIngestionConfig:
    def test_default_values(self):
        config = IngestionConfig(base_url="https://test.com")
        assert config.batch_size == 50000
        assert config.max_retries == 3
        assert config.lookback_days == 7
    
    def test_custom_values(self):
        config = IngestionConfig(
            base_url="https://test.com",
            batch_size=1000,
            max_retries=5,
            lookback_days=14
        )
        assert config.batch_size == 1000
        assert config.max_retries == 5
        assert config.lookback_days == 14


class TestNYC311APIClient:
    @pytest.fixture
    def config(self):
        return IngestionConfig(base_url="https://test.com", batch_size=100)
    
    @pytest.fixture
    def client(self, config):
        return NYC311APIClient(config)
    
    def test_build_params_without_since(self, client):
        params = client._build_params(limit=50, offset=0)
        assert params["$limit"] == 50
        assert params["$offset"] == 0
        assert params["$order"] == "created_date ASC"
        assert "$where" not in params
    
    def test_build_params_with_since(self, client):
        since = datetime(2024, 1, 15, 10, 30, 0)
        params = client._build_params(since=since, limit=50)
        assert "$where" in params
        assert "2024-01-15T10:30:00" in params["$where"]
    
    def test_build_params_with_app_token(self, config):
        config.app_token = "test-token"
        client = NYC311APIClient(config)
        params = client._build_params()
        assert params["$$app_token"] == "test-token"
    
    @patch('src.ingestion.requests.Session.get')
    def test_fetch_batch_success(self, mock_get, client):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"unique_key": "1", "created_date": "2024-01-01"}]
        mock_get.return_value = mock_response
        
        batch = client.fetch_batch(offset=0)
        assert len(batch) == 1
        assert batch[0]["unique_key"] == "1"
    
    @patch('src.ingestion.requests.Session.get')
    def test_fetch_batch_rate_limited(self, mock_get, client):
        mock_response = Mock()
        mock_response.status_code = 429
        mock_response.headers = {"Retry-After": "1"}
        mock_get.return_value = mock_response
        
        with pytest.raises(Exception):
            client.fetch_batch(offset=0)
    
    def test_close(self, client):
        client.close()  # Should not raise


class TestIngestionPipeline:
    @pytest.fixture
    def mock_db(self):
        db = Mock(spec=DatabaseManager)
        db.get_max_created_date.return_value = datetime(2024, 1, 1)
        db.upsert_records.return_value = 100
        return db
    
    @pytest.fixture
    def config(self):
        return IngestionConfig(base_url="https://test.com", batch_size=100, lookback_days=1)
    
    @pytest.fixture
    def pipeline(self, mock_db, config):
        return IngestionPipeline(mock_db, config)
    
    @patch('src.ingestion.NYC311APIClient')
    def test_run_incremental(self, mock_client_class, pipeline, mock_db):
        mock_client = Mock()
        mock_client.fetch_incremental.return_value = [
            [{"unique_key": "1", "created_date": "2024-01-02"} for _ in range(50)],
            [{"unique_key": "2", "created_date": "2024-01-02"} for _ in range(50)],
        ]
        mock_client_class.return_value = mock_client
        pipeline.client = mock_client
        
        stats = pipeline.run_incremental()
        
        assert stats.total_fetched == 100
        assert stats.total_upserted == 200  # 2 batches * 100 (mock return)
        assert stats.batches_processed == 2
        assert stats.duration_seconds > 0
    
    @patch('src.ingestion.NYC311APIClient')
    def test_run_incremental_with_failure(self, mock_client_class, pipeline, mock_db):
        mock_client = Mock()
        mock_client.fetch_incremental.return_value = [
            [{"unique_key": "1"}],
            [{"unique_key": "2"}],
        ]
        mock_db.upsert_records.side_effect = [100, Exception("DB error")]
        mock_client_class.return_value = mock_client
        pipeline.client = mock_client
        
        stats = pipeline.run_incremental()
        
        assert stats.total_fetched == 2
        assert stats.total_upserted == 100
        assert stats.total_failed == 1
        assert len(stats.errors) == 1
        assert len(pipeline.dead_letter_queue) == 1
    
    def test_get_dead_letter_records(self, pipeline):
        pipeline.dead_letter_queue = [{"unique_key": "1", "_error": "test"}]
        assert len(pipeline.get_dead_letter_records()) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])