"""
Bug Analyzer - Multi-tier bug detection using QGenie SDK.

Implements L1 (single-file), L2 (multi-function), and L3 (cross-module) analysis.
"""

import logging
from typing import Dict, List

from qgenie_sdk import QGenieClient
from scanner import (
    build_dependency_map,
    detect_module_boundaries,
    detect_static_hints,
    get_file_context,
)

logger = logging.getLogger(__name__)


class BugAnalyzer:
    """Multi-tier bug analyzer using QGenie SDK."""

    def __init__(self, client: QGenieClient, files: Dict[str, str]):
        """Initialize the analyzer.

        Args:
            client: QGenie SDK client instance.
            files: Dict mapping filepath -> source code.
        """
        self.client = client
        self.files = files
        self.dep_map = build_dependency_map(files)
        self.modules = detect_module_boundaries(files, self.dep_map)
        self.all_bugs: List[dict] = []
        self._bug_counter = 0

    def run_full_analysis(self) -> List[dict]:
        """Run all analysis tiers and return consolidated bug list."""
        logger.info("Starting full analysis on %d files", len(self.files))

        logger.info("=== L1: Single-file analysis ===")
        self._run_l1_analysis()

        logger.info("=== L2: Multi-function analysis ===")
        self._run_l2_analysis()

        logger.info("=== L3: Cross-module analysis ===")
        self._run_l3_analysis()

        self._deduplicate_bugs()
        logger.info("Analysis complete. Total bugs found: %d", len(self.all_bugs))
        return self.all_bugs

    def _run_l1_analysis(self):
        """L1: Analyze each file individually for simple logic bugs."""
        for filepath, content in self.files.items():
            if not content.strip():
                continue
            logger.info("L1 analyzing: %s", filepath)

            # Generate static hints to guide the LLM toward real bugs
            hints = detect_static_hints(content, filepath)
            hint_context = ""
            if hints:
                hint_lines = [
                    f"  Line {h['line']}: {h['hint']} — {h['pattern']}"
                    for h in hints
                ]
                hint_context = (
                    "Static analysis hints (potential issues to verify):\n"
                    + "\n".join(hint_lines)
                )
                logger.info(
                    "  Found %d static hints for %s", len(hints), filepath
                )

            result = self.client.analyze_code(
                code=content,
                filepath=filepath,
                context=hint_context,
            )
            self._process_results(result, [filepath])

    def _run_l2_analysis(self):
        """L2: Analyze files with their dependency context."""
        for filepath, content in self.files.items():
            if not content.strip():
                continue
            context = get_file_context(filepath, self.files, self.dep_map)
            if not context:
                continue
            logger.info("L2 analyzing: %s (with dependency context)", filepath)
            result = self.client.analyze_code(
                code=content,
                filepath=filepath,
                context=context,
            )
            self._process_results(result, [filepath])

    def _run_l3_analysis(self):
        """L3: Analyze cross-module dependencies for architectural bugs."""
        for module in self.modules:
            if len(module) < 2:
                continue

            module_files = {fp: self.files[fp] for fp in module if fp in self.files}
            module_deps = {fp: self.dep_map.get(fp, []) for fp in module}

            total_chars = sum(len(c) for c in module_files.values())
            if total_chars > 50000:
                logger.warning(
                    "Module too large (%d chars), splitting for analysis",
                    total_chars,
                )
                continue

            logger.info("L3 analyzing module: %s", module)
            result = self.client.analyze_cross_module(module_files, module_deps)
            self._process_results(result, module)

    def _process_results(self, result: dict, filepaths: List[str]):
        """Process API results and add to bug list.

        Args:
            result: Parsed JSON result from QGenie.
            filepaths: Files associated with the analysis.
        """
        bugs = result.get("bugs", [])
        for bug in bugs:
            # Filter out low-confidence results for higher precision
            confidence = bug.get("confidence", "MEDIUM").upper()
            if confidence not in ("HIGH", "MEDIUM", "LOW"):
                confidence = "MEDIUM"
            if confidence == "LOW":
                logger.debug(
                    "Skipping low-confidence bug in %s (line %d): %s",
                    filepaths,
                    bug.get("line_start", 0),
                    bug.get("description", "")[:80],
                )
                continue

            # Normalize severity
            severity = bug.get("severity", "MEDIUM").upper()
            if severity not in ("LOW", "MEDIUM", "HIGH"):
                severity = "MEDIUM"

            # Normalize category
            category = bug.get("category", "Logic Error")
            valid_categories = {
                "Memory Management", "Concurrency", "Logic Error",
                "Type Safety", "Resource Management", "API Misuse",
                "Security", "Undefined Behavior",
            }
            if category not in valid_categories:
                category = "Logic Error"

            # Require non-empty buggy_code and fixed_code for actionable results
            buggy_code = bug.get("buggy_code", "")
            fixed_code = bug.get("fixed_code", "")
            description = bug.get("description", "")

            if not buggy_code.strip() or not description.strip():
                logger.debug(
                    "Skipping bug with missing buggy_code or description in %s",
                    filepaths,
                )
                continue

            self._bug_counter += 1
            bug_entry = {
                "id": f"BUG-{self._bug_counter:03d}",
                "files": bug.get("files", filepaths),
                "line_start": bug.get("line_start", 0),
                "line_end": bug.get("line_end", 0),
                "buggy_code": buggy_code,
                "fixed_code": fixed_code,
                "description": description,
                "explanation": bug.get("explanation", ""),
                "severity": severity,
                "category": category,
                "confidence": confidence,
            }
            self.all_bugs.append(bug_entry)

    def _deduplicate_bugs(self):
        """Remove duplicate bugs based on file, line range, and buggy code.

        When duplicates are found, the entry with the higher confidence is kept.
        """
        confidence_rank = {"HIGH": 2, "MEDIUM": 1, "LOW": 0}
        seen = {}
        for bug in self.all_bugs:
            key = (
                tuple(sorted(bug["files"])),
                bug["line_start"],
                bug["line_end"],
                bug["buggy_code"][:100],
            )
            if key not in seen:
                seen[key] = bug
            else:
                existing = seen[key]
                existing_rank = confidence_rank.get(existing.get("confidence", "MEDIUM"), 1)
                new_rank = confidence_rank.get(bug.get("confidence", "MEDIUM"), 1)
                if new_rank > existing_rank:
                    seen[key] = bug

        unique_bugs = list(seen.values())
        removed = len(self.all_bugs) - len(unique_bugs)
        if removed > 0:
            logger.info("Removed %d duplicate bugs", removed)

        self.all_bugs = unique_bugs

        for i, bug in enumerate(self.all_bugs):
            bug["id"] = f"BUG-{i + 1:03d}"
