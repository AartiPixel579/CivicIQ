"""
Standalone Scheduled Crawler & Incremental Knowledge Base Updater CLI.
Runs outside the FastAPI chat request lifecycle (via cron, GitHub Actions, or admin CLI).

Usage:
    python -m backend.scripts.run_crawler --department engineering
"""

import argparse
import json
import logging
import sys

from backend.scripts.incremental_ingest import run_incremental_ingestion

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def main() -> int:
    parser = argparse.ArgumentParser(description="CivicIQ Incremental Website Crawler & Indexer")
    parser.add_argument("--department", default="engineering", help="Department ID to crawl and update")
    parser.add_argument("--root-url", default=None, help="Optional override for trusted root URL")
    args = parser.parse_args()

    report = run_incremental_ingestion(
        department_id=args.department,
        root_url_override=args.root_url,
    )
    print(json.dumps(report, indent=2))
    return 0 if report.get("status") == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())
