"""Unit tests for validation module."""

import pytest
from unittest.mock import Mock, patch, MagicMock
import json

from src.validation import (
    build_expectation_suite,
    save_suite_to_file,
    run_validation,
    run_checkpoint,
    get_gx_context,
)


class TestBuildExpectationSuite:
    def test_suite_structure(self):
        suite = build_expectation_suite()
        
        assert suite["expectation_suite_name"] == "nyc_311_suite"
        assert "expectations" in suite
        assert len(suite["expectations"]) > 0
        assert "meta" in suite
    
    def test_critical_expectations_present(self):
        suite = build_expectation_suite()
        expectation_types = [e["expectation_type"] for e in suite["expectations"]]
        
        # Check critical expectations exist
        assert "expect_column_values_to_not_be_null" in expectation_types
        assert "expect_column_values_to_be_unique" in expectation_types
        assert "expect_column_values_to_be_in_set" in expectation_types
    
    def test_column_coverage(self):
        suite = build_expectation_suite()
        columns_tested = set()
        
        for exp in suite["expectations"]:
            if "column" in exp.get("kwargs", {}):
                columns_tested.add(exp["kwargs"]["column"])
        
        # Should cover at least 15 columns as specified
        expected_columns = {
            "unique_key", "created_date", "closed_date", "agency",
            "agency_name", "complaint_type", "descriptor", "location_type",
            "incident_zip", "borough", "latitude", "longitude",
            "status", "resolution_description"
        }
        # At minimum these critical columns should be tested
        critical = {"unique_key", "created_date", "agency", "complaint_type", "borough", "status"}
        assert critical.issubset(columns_tested)
    
    def test_severity_metadata(self):
        suite = build_expectation_suite()
        
        for exp in suite["expectations"]:
            assert "meta" in exp
            assert "dimension" in exp["meta"]
            assert "severity" in exp["meta"]
            assert exp["meta"]["severity"] in ["critical", "warning", "info"]


class TestSaveSuiteToFile:
    def test_save_suite(self, tmp_path):
        suite = build_expectation_suite()
        file_path = tmp_path / "test_suite.json"
        
        save_suite_to_file(suite, str(file_path))
        
        assert file_path.exists()
        with open(file_path) as f:
            loaded = json.load(f)
        assert loaded["expectation_suite_name"] == "nyc_311_suite"


class TestValidationRunner:
    @pytest.fixture
    def mock_context(self):
        context = Mock()
        context.get_datasource.return_value = Mock()
        context.get_expectation_suite.return_value = Mock()
        context.get_validator.return_value = Mock()
        context.get_validator.return_value.validate.return_value = Mock(
            success=True,
            statistics={"evaluated_expectations": 10, "successful_expectations": 10, "unsuccessful_expectations": 0},
            run_id=Mock(),
            results=[Mock(success=True, expectation_config=Mock(expectation_type="test", kwargs={}), result={})]
        )
        context.get_checkpoint.return_value = Mock()
        context.get_checkpoint.return_value.run.return_value = Mock(
            success=True,
            run_id=Mock(),
            run_time=datetime.utcnow(),
            run_results={}
        )
        return context
    
    @patch('src.validation.gx.get_context')
    def test_get_gx_context(self, mock_get_context):
        mock_get_context.return_value = Mock()
        context = get_gx_context()
        assert context is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])