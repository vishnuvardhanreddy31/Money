#!/usr/bin/env python3
"""
QGenie Code Debugging Agent

Autonomous agent for detecting, tracing, fixing, and explaining bugs in
C/C++ codebases. Built for the QGenie Summit Hackathon.

Usage:
    python agent.py <input_code_path> <output_result_path> <qgenie_api_key>

Docker execution:
    docker run --rm \\
        -v /host/input:/data/input \\
        -v /host/output:/data/output \\
        my-agent-image \\
        /data/input /data/output qgenie_api_key
"""

import logging
import sys
import time

from analyzer import BugAnalyzer
from qgenie_sdk import QGenieClient
from reporter import generate_report
from scanner import scan_directory

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("agent")


def main():
    if len(sys.argv) != 4:
        print(
            "Usage: python agent.py <input_code_path> <output_result_path> <qgenie_api_key>",
            file=sys.stderr,
        )
        sys.exit(1)

    input_code_path = sys.argv[1]
    output_result_path = sys.argv[2]
    qgenie_api_key = sys.argv[3]

    logger.info("QGenie Code Debugging Agent starting...")
    logger.info("Input path: %s", input_code_path)
    logger.info("Output path: %s", output_result_path)

    start_time = time.time()

    # Step 1: Detect - Scan the codebase
    logger.info("Step 1/4: DETECT - Scanning codebase for C/C++ files...")
    files = scan_directory(input_code_path)
    if not files:
        logger.warning("No C/C++ files found in %s", input_code_path)
        generate_report([], output_result_path)
        logger.info("Empty report generated.")
        return

    # Step 2: Trace - Initialize QGenie SDK and analyze
    logger.info("Step 2/4: TRACE - Initializing QGenie SDK and mapping dependencies...")
    client = QGenieClient(api_key=qgenie_api_key)

    # Step 3: Fix - Run multi-tier bug analysis
    logger.info("Step 3/4: FIX - Running multi-tier bug analysis...")
    analyzer = BugAnalyzer(client=client, files=files)
    bugs = analyzer.run_full_analysis()

    # Step 4: Explain - Generate report with explanations
    logger.info("Step 4/4: EXPLAIN - Generating report with fixes and explanations...")
    report_path = generate_report(bugs, output_result_path)

    elapsed = time.time() - start_time
    logger.info("Agent completed in %.2f seconds", elapsed)
    logger.info("Report: %s", report_path)
    logger.info("Bugs detected: %d", len(bugs))


if __name__ == "__main__":
    main()
