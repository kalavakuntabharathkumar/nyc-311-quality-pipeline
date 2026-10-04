"""
Main pipeline orchestration script for NYC 311 Data Quality Pipeline.

Runs the complete ETL process:
1. Incremental/full ingestion from NYC Open Data API
2. Great Expectations validation
3. dbt transformation (via subprocess)
4. Data quality reporting
"""

import sys
import subprocess
import logging
from datetime import datetime
from typing import Optional
from pathlib import Path

import yaml
import structlog

from src.database import DatabaseManager, init_database
from src.ingestion import create_ingestion_pipeline, IngestionPipeline
from src.validation import get_gx_context, run_checkpoint, generate_data_docs

logger = structlog.get_logger(__name__)


def load_config(config_path: str = "config.yaml") -> dict:
    """Load configuration from YAML file."""
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def run_dbt(command: str, project_dir: str = "dbt_project", target: str = "dev") -> bool:
    """Run dbt command and return success status."""
    try:
        result = subprocess.run(
            ["dbt", command, "--project-dir", project_dir, "--target", target],
            capture_output=True,
            text=True,
            timeout=1800,  # 30 min timeout
        )
        if result.returncode != 0:
            logger.error("dbt_failed", command=command, stderr=result.stderr[-2000:])
            return False
        logger.info("dbt_success", command=command)
        return True
    except subprocess.TimeoutExpired:
        logger.error("dbt_timeout", command=command)
        return False
    except FileNotFoundError:
        logger.error("dbt_not_found", message="dbt not installed or not in PATH")
        return False


def run_pipeline(
    config: dict,
    full_load: bool = False,
    start_date: Optional[datetime] = None,
    skip_validation: bool = False,
    skip_dbt: bool = False,
) -> dict:
    """Run the complete pipeline."""
    results = {
        "ingestion": None,
        "validation": None,
        "dbt": None,
        "overall_success": False,
        "start_time": datetime.utcnow(),
        "end_time": None,
    }
    
    # Initialize database
    db = init_database(config)
    
    try:
        # Step 1: Ingestion
        logger.info("pipeline_step_start", step="ingestion")
        pipeline = create_ingestion_pipeline(db, config)
        
        if full_load:
            if not start_date:
                start_date = datetime(2023, 1, 1)
            ingestion_stats = pipeline.run_full(start_date)
        else:
            ingestion_stats = pipeline.run_incremental()
        
        results["ingestion"] = {
            "records_fetched": ingestion_stats.total_fetched,
            "records_upserted": ingestion_stats.total_upserted,
            "records_failed": ingestion_stats.total_failed,
            "batches": ingestion_stats.batches_processed,
            "duration_seconds": ingestion_stats.duration_seconds,
            "success": ingestion_stats.total_failed == 0,
        }
        
        if not results["ingestion"]["success"]:
            logger.error("ingestion_failed", errors=ingestion_stats.errors)
            return results
        
        # Step 2: Validation
        if not skip_validation:
            logger.info("pipeline_step_start", step="validation")
            context = get_gx_context()
            validation_result = run_checkpoint(context, "daily_checkpoint")
            results["validation"] = validation_result
            
            if not validation_result["success"]:
                logger.warning("validation_failed_but_continuing", result=validation_result)
                # Don't fail pipeline on validation warnings, but log
        
        # Step 3: dbt Transformations
        if not skip_dbt:
            logger.info("pipeline_step_start", step="dbt_run")
            dbt_success = run_dbt("run")
            results["dbt"] = {"run_success": dbt_success}
            
            if dbt_success:
                logger.info("pipeline_step_start", step="dbt_test")
                test_success = run_dbt("test")
                results["dbt"]["test_success"] = test_success
                
                logger.info("pipeline_step_start", step="dbt_docs")
                run_dbt("docs generate")
            else:
                logger.error("dbt_run_failed")
                return results
        
        results["overall_success"] = True
        
    except Exception as e:
        logger.exception("pipeline_error", error=str(e))
        results["error"] = str(e)
    
    finally:
        db.close()
        results["end_time"] = datetime.utcnow()
        results["total_duration_seconds"] = (
            results["end_time"] - results["start_time"]
        ).total_seconds()
    
    return results


def main():
    """CLI entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="NYC 311 Data Quality Pipeline")
    parser.add_argument("--config", default="config.yaml", help="Config file path")
    parser.add_argument("--full", action="store_true", help="Run full historical load")
    parser.add_argument("--start-date", help="Start date for full load (YYYY-MM-DD)")
    parser.add_argument("--incremental", action="store_true", help="Run incremental load (default)")
    parser.add_argument("--skip-validation", action="store_true", help="Skip Great Expectations validation")
    parser.add_argument("--skip-dbt", action="store_true", help="Skip dbt transformations")
    parser.add_argument("--validation-only", action="store_true", help="Run only validation")
    
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer()
        ]
    )
    
    config = load_config(args.config)
    
    if args.validation_only:
        context = get_gx_context()
        result = run_checkpoint(context, "daily_checkpoint")
        generate_data_docs(context)
        sys.exit(0 if result["success"] else 1)
    
    full_load = args.full
    start_date = None
    if args.start_date:
        start_date = datetime.fromisoformat(args.start_date)
    
    results = run_pipeline(
        config,
        full_load=full_load,
        start_date=start_date,
        skip_validation=args.skip_validation,
        skip_dbt=args.skip_dbt,
    )
    
    # Print summary
    print("\n" + "="*60)
    print("PIPELINE EXECUTION SUMMARY")
    print("="*60)
    print(f"Overall: {'SUCCESS' if results['overall_success'] else 'FAILED'}")
    print(f"Duration: {results['total_duration_seconds']:.1f} seconds")
    
    if results["ingestion"]:
        ing = results["ingestion"]
        print(f"\nIngestion: {'PASS' if ing['success'] else 'FAIL'}")
        print(f"  Records fetched: {ing['records_fetched']:,}")
        print(f"  Records upserted: {ing['records_upserted']:,}")
        print(f"  Records failed: {ing['records_failed']:,}")
        print(f"  Batches: {ing['batches']}")
        print(f"  Duration: {ing['duration_seconds']:.1f}s")
    
    if results["validation"]:
        val = results["validation"]
        print(f"\nValidation: {'PASS' if val['success'] else 'FAIL'}")
        print(f"  Expectations evaluated: {val.get('evaluated_expectations', 'N/A')}")
    
    if results["dbt"]:
        dbt = results["dbt"]
        print(f"\ndbt Run: {'PASS' if dbt.get('run_success') else 'FAIL'}")
        print(f"  Tests: {'PASS' if dbt.get('test_success') else 'FAIL/SKIPPED'}")
    
    sys.exit(0 if results["overall_success"] else 1)


if __name__ == "__main__":
    main()