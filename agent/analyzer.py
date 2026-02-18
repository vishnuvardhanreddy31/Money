"""
Bug Analyzer - Multi-tier bug detection using QGenie SDK.

Implements L1 (single-file), L2 (multi-function), and L3 (cross-module) analysis.
Handles large codebases by splitting oversized files and modules into manageable
chunks before sending them to the API.
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

# Maximum characters per file before it is split into chunks for analysis.
MAX_FILE_CHARS = 30000

# Maximum total characters per cross-module analysis request.
MAX_MODULE_CHARS = 50000


def _split_file_into_chunks(content: str, filepath: str, max_chars: int = MAX_FILE_CHARS) -> List[dict]:
    """Split a large file into overlapping chunks at function boundaries.

    Each chunk is returned as a dict with ``code``, ``filepath`` (annotated
    with the chunk index), and ``offset`` (the 1-based starting line number
    within the original file).

    Args:
        content: Full source code of the file.
        filepath: Original file path.
        max_chars: Approximate maximum characters per chunk.

    Returns:
        A list of chunk dicts.  For files smaller than *max_chars* the
        list contains a single entry covering the whole file.
    """
    if len(content) <= max_chars:
        return [{"code": content, "filepath": filepath, "offset": 1}]

    lines = content.split("\n")
    chunks: List[dict] = []
    current_lines: List[str] = []
    current_chars = 0
    chunk_start_line = 1

    for i, line in enumerate(lines, 1):
        current_lines.append(line)
        current_chars += len(line) + 1  # +1 for newline

        if current_chars >= max_chars:
            chunk_code = "\n".join(current_lines)
            chunks.append({
                "code": chunk_code,
                "filepath": f"{filepath} [chunk {len(chunks) + 1}]",
                "offset": chunk_start_line,
            })
            current_lines = []
            current_chars = 0
            chunk_start_line = i + 1

    if current_lines:
        chunk_code = "\n".join(current_lines)
        chunks.append({
            "code": chunk_code,
            "filepath": f"{filepath} [chunk {len(chunks) + 1}]",
            "offset": chunk_start_line,
        })

    logger.info("Split %s into %d chunks for analysis", filepath, len(chunks))
    return chunks


class BugAnalyzer:
    """Multi-tier bug analyzer using QGenie SDK.

    Automatically splits large files and modules into smaller chunks so
    that the agent can handle arbitrarily large codebases.
    """

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
        """L1: Analyze each file individually for simple logic bugs.

        Large files are automatically split into chunks so that they
        stay within API token limits.
        """
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

            chunks = _split_file_into_chunks(content, filepath)
            for chunk in chunks:
                result = self.client.analyze_code(
                    code=chunk["code"],
                    filepath=chunk["filepath"],
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
        """L3: Analyze cross-module dependencies for architectural bugs.

        Modules exceeding ``MAX_MODULE_CHARS`` are split into smaller
        sub-groups so they can still be analyzed instead of being skipped
        entirely.
        """
        for module in self.modules:
            if len(module) < 2:
                continue

            module_files = {fp: self.files[fp] for fp in module if fp in self.files}
            module_deps = {fp: self.dep_map.get(fp, []) for fp in module}

            total_chars = sum(len(c) for c in module_files.values())
            if total_chars > MAX_MODULE_CHARS:
                logger.info(
                    "Module too large (%d chars), splitting into sub-groups",
                    total_chars,
                )
                self._analyze_large_module(module_files, module_deps)
            else:
                logger.info("L3 analyzing module: %s", module)
                result = self.client.analyze_cross_module(module_files, module_deps)
                self._process_results(result, module)

    def _analyze_large_module(self, module_files: Dict[str, str], module_deps: Dict[str, List[str]]):
        """Split a large module into sub-groups and analyze each pair.

        Each file is paired with its direct dependencies to form
        sub-groups small enough for the API.
        """
        analyzed_pairs: set = set()
        for filepath in module_files:
            deps = [d for d in module_deps.get(filepath, []) if d in module_files]
            if not deps:
                continue
            pair_key = tuple(sorted([filepath] + deps))
            if pair_key in analyzed_pairs:
                continue
            analyzed_pairs.add(pair_key)

            sub_files = {fp: module_files[fp] for fp in pair_key if fp in module_files}
            sub_deps = {fp: module_deps.get(fp, []) for fp in pair_key}
            sub_chars = sum(len(c) for c in sub_files.values())

            if sub_chars > MAX_MODULE_CHARS:
                logger.warning(
                    "Sub-group still too large (%d chars), skipping: %s",
                    sub_chars, pair_key,
                )
                continue

            logger.info("L3 analyzing sub-group: %s", list(pair_key))
            result = self.client.analyze_cross_module(sub_files, sub_deps)
            self._process_results(result, list(pair_key))

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

            # Require non-empty buggy_code, fixed_code, and description for actionable results
            buggy_code = bug.get("buggy_code", "")
            fixed_code = bug.get("fixed_code", "")
            description = bug.get("description", "")

            if not buggy_code.strip() or not fixed_code.strip() or not description.strip():
                logger.debug(
                    "Skipping bug with missing buggy_code, fixed_code, or description in %s",
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
