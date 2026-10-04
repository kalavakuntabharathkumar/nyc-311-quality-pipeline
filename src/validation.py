"""
Great Expectations Validation Runner for NYC 311 Data

Executes validation suite against raw and curated data,
producing HTML data docs and checkpoint results.
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from pathlib import Path

import great_expectations as gx
from great_expectations.checkpoint import Checkpoint
from great_expectations.core import ExpectationSuite
from great_expectations.data_context import FileDataContext
import structlog

logger = structlog.get_logger(__name__)


def get_gx_context(project_root: str = ".") -> FileDataContext:
    """Initialize Great Expectations Data Context."""
    gx_dir = Path(project_root) / "great_expectations"
    context = gx.get_context(context_root_dir=str(gx_dir))
    return context

def build_expectation_suite() -> Dict[str, Any]:
    """
    Build the expectation suite configuration for NYC 311 data.
    Returns dict that can be saved as JSON suite.
    """
    suite = {
        "expectation_suite_name": "nyc_311_suite",
        "expectations": [
            # unique_key - primary key
            {
                "expectation_type": "expect_column_values_to_not_be_null",
                "kwargs": {"column": "unique_key"},
                "meta": {"dimension": "completeness", "severity": "critical"}
            },
            {
                "expectation_type": "expect_column_values_to_be_unique",
                "kwargs": {"column": "unique_key"},
                "meta": {"dimension": "uniqueness", "severity": "critical"}
            },
            
            # created_date - required timestamp
            {
                "expectation_type": "expect_column_values_to_not_be_null",
                "kwargs": {"column": "created_date"},
                "meta": {"dimension": "completeness", "severity": "critical"}
            },
            {
                "expectation_type": "expect_column_values_to_match_strftime_format",
                "kwargs": {"column": "created_date", "strftime_format": "%Y-%m-%dT%H:%M:%S.%f"},
                "meta": {"dimension": "format", "severity": "warning"}
            },
            
            # closed_date - nullable but must be >= created_date when present
            {
                "expectation_type": "expect_column_values_to_be_between",
                "kwargs": {"column": "closed_date", "min_value": "{{ created_date }}", "parse_strings_as_datetimes": True},
                "meta": {"dimension": "referential_integrity", "severity": "warning"}
            },
            
            # agency - required, must exist in reference list
            {
                "expectation_type": "expect_column_values_to_not_be_null",
                "kwargs": {"column": "agency"},
                "meta": {"dimension": "completeness", "severity": "critical"}
            },
            {
                "expectation_type": "expect_column_values_to_be_in_set",
                "kwargs": {
                    "column": "agency",
                    "value_set": [
                        "NYPD", "DOB", "DOHMH", "DSNY", "DOT", "DPR", "DEP", "HPD",
                        "DOF", "DCA", "DOITT", "FDNY", "LAW", "OATH", "TLC", "NYCHA"
                    ]
                },
                "meta": {"dimension": "referential_integrity", "severity": "warning"}
            },
            
            # agency_name
            {
                "expectation_type": "expect_column_values_to_not_be_null",
                "kwargs": {"column": "agency_name"},
                "meta": {"dimension": "completeness", "severity": "warning"}
            },
            
            # complaint_type - required, controlled vocabulary
            {
                "expectation_type": "expect_column_values_to_not_be_null",
                "kwargs": {"column": "complaint_type"},
                "meta": {"dimension": "completeness", "severity": "critical"}
            },
            
            # descriptor
            {
                "expectation_type": "expect_column_values_to_not_be_null",
                "kwargs": {"column": "descriptor", "mostly": 0.9},
                "meta": {"dimension": "completeness", "severity": "warning"}
            },
            
            # location_type
            {
                "expectation_type": "expect_column_values_to_be_in_set",
                "kwargs": {
                    "column": "location_type",
                    "value_set": ["Address", "Intersection", "Block Face", "Latitude/Longitude", "N/A"]
                },
                "meta": {"dimension": "validity", "severity": "warning"}
            },
            
            # incident_zip - 5 digit format when present
            {
                "expectation_type": "expect_column_values_to_match_regex",
                "kwargs": {"column": "incident_zip", "regex": "^\\d{5}$", "mostly": 0.85},
                "meta": {"dimension": "validity", "severity": "warning"}
            },
            
            # borough - required, controlled values
            {
                "expectation_type": "expect_column_values_to_not_be_null",
                "kwargs": {"column": "borough"},
                "meta": {"dimension": "completeness", "severity": "critical"}
            },
            {
                "expectation_type": "expect_column_values_to_be_in_set",
                "kwargs": {
                    "column": "borough",
                    "value_set": ["MANHATTAN", "BRONX", "BROOKLYN", "QUEENS", "STATEN ISLAND", "UNSPECIFIED"]
                },
                "meta": {"dimension": "referential_integrity", "severity": "critical"}
            },
            
            # latitude/longitude - NYC bounds when present
            {
                "expectation_type": "expect_column_values_to_be_between",
                "kwargs": {"column": "latitude", "min_value": 40.47, "max_value": 40.92, "mostly": 0.7},
                "meta": {"dimension": "validity", "severity": "warning"}
            },
            {
                "expectation_type": "expect_column_values_to_be_between",
                "kwargs": {"column": "longitude", "min_value": -74.26, "max_value": -73.70, "mostly": 0.7},
                "meta": {"dimension": "validity", "severity": "warning"}
            },
            
            # status
            {
                "expectation_type": "expect_column_values_to_be_in_set",
                "kwargs": {
                    "column": "status",
                    "value_set": ["Open", "Closed", "In Progress", "Pending"]
                },
                "meta": {"dimension": "validity", "severity": "warning"}
            },
            
            # resolution_description
            {
                "expectation_type": "expect_column_values_to_not_be_null",
                "kwargs": {"column": "resolution_description", "mostly": 0.8},
                "meta": {"dimension": "completeness", "severity": "info"}
            },
            
            # Table-level expectations
            {
                "expectation_type": "expect_table_row_count_to_be_between",
                "kwargs": {"min_value": 1000, "max_value": 10000000},
                "meta": {"dimension": "volume", "severity": "warning"}
            },
        ],
        "meta": {
            "created_at": datetime.utcnow().isoformat(),
            "version": "1.0",
            "description": "NYC 311 Service Requests validation suite - 15 columns profiled"
        }
    }
    return suite

def save_suite_to_file(suite: Dict[str, Any], path: str) -> None:
    """Save expectation suite to JSON file."""
    with open(path, "w") as f:
        json.dump(suite, f, indent=2)
    logger.info("suite_saved", path=path)

def run_validation(context: FileDataContext, suite_name: str = "nyc_311_suite",
                   batch_identifier: str = None) -> Dict[str, Any]:
    """Run validation checkpoint and return results."""
    
    # Get or create datasource
    datasource_name = "nyc_311_postgres"
    try:
        datasource = context.get_datasource(datasource_name)
    except:
        datasource = context.sources.add_postgres(
            name=datasource_name,
            connection_string=os.getenv("GE_POSTGRES_CONN", "postgresql+psycopg2://pipeline_user:secure_password@localhost:5432/nyc_311")
        )
    
    # Add table asset
    asset_name = "raw_nyc_311_requests"
    try:
        asset = datasource.get_asset(asset_name)
    except:
        asset = datasource.add_table_asset(
            name=asset_name,
            table_name="nyc_311_requests",
            schema_name="raw"
        )
    
    # Build batch request
    batch_request = asset.build_batch_request(
        options={"partitioner": "created_date"} if batch_identifier else {}
    )
    
    # Get suite
    suite = context.get_expectation_suite(suite_name)
    
    # Create validator
    validator = context.get_validator(
        batch_request=batch_request,
        expectation_suite=suite
    )
    
    # Run validation
    results = validator.validate()
    
    # Build summary
    summary = {
        "success": results.success,
        "statistics": results.statistics,
        "run_id": str(results.run_id),
        "evaluated_expectations": len(results.results),
        "successful_expectations": sum(1 for r in results.results if r.success),
        "failed_expectations": sum(1 for r in results.results if not r.success),
        "timestamp": datetime.utcnow().isoformat(),
    }
    
    # Log failures
    for result in results.results:
        if not result.success:
            logger.warning(
                "expectation_failed",
                expectation_type=result.expectation_config.expectation_type,
                column=result.expectation_config.kwargs.get("column"),
                observed_value=result.result.get("observed_value"),
            )
    
    logger.info("validation_complete", **summary)
    return summary

def run_checkpoint(context: FileDataContext, checkpoint_name: str = "daily_checkpoint") -> Dict[str, Any]:
    """Run a named checkpoint."""
    checkpoint = context.get_checkpoint(checkpoint_name)
    result = checkpoint.run()
    
    summary = {
        "success": result.success,
        "run_id": str(result.run_id),
        "run_time": result.run_time.isoformat(),
        "validation_results": []
    }
    
    for vr in result.run_results.values():
        validation_result = vr["validation_result"]
        summary["validation_results"].append({
            "batch_id": str(vr["batch_spec"]),
            "success": validation_result.success,
            "statistics": validation_result.statistics,
        })
    
    logger.info("checkpoint_complete", success=summary["success"])
    return summary

def generate_data_docs(context: FileDataContext) -> str:
    """Build and return path to data docs site."""
    context.build_data_docs()
    site_path = Path(context.root_directory) / "uncommitted" / "data_docs" / "local_site" / "index.html"
    logger.info("data_docs_generated", path=str(site_path))
    return str(site_path)


def main():
    """CLI entry point for validation."""
    import argparse
    import yaml
    
    parser = argparse.ArgumentParser(description="Run Great Expectations validation")
    parser.add_argument("--suite", default="nyc_311_suite", help="Expectation suite name")
    parser.add_argument("--checkpoint", help="Checkpoint name to run")
    parser.add_argument("--build-suite", action="store_true", help="Build and save suite definition")
    parser.add_argument("--data-docs", action="store_true", help="Generate data docs")
    
    args = parser.parse_args()
    
    context = get_gx_context()
    
    if args.build_suite:
        suite = build_expectation_suite()
        save_suite_to_file(suite, "great_expectations/expectations/nyc_311_suite.json")
        # Also add to context
        context.add_or_update_expectation_suite(ExpectationSuite(**suite))
        print(f"Suite '{args.suite}' built and saved.")
    
    if args.checkpoint:
        result = run_checkpoint(context, args.checkpoint)
        print(f"Checkpoint result: {'PASS' if result['success'] else 'FAIL'}")
    else:
        result = run_validation(context, args.suite)
        print(f"Validation result: {'PASS' if result['success'] else 'FAIL'}")
        print(f"  Evaluated: {result['evaluated_expectations']}")
        print(f"  Passed: {result['successful_expectations']}")
        print(f"  Failed: {result['failed_expectations']}")
    
    if args.data_docs:
        path = generate_data_docs(context)
        print(f"Data docs generated: {path}")


if __name__ == "__main__":
    main()