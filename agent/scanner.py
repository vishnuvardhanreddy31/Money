"""
Code Scanner - Finds and parses C/C++ source files, builds dependency maps,
and provides static pattern hints for common bug patterns.
"""

import os
import re
import logging
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

C_CPP_EXTENSIONS = {".c", ".h", ".cpp", ".hpp", ".cc", ".hh", ".cxx", ".hxx"}

INCLUDE_PATTERN = re.compile(r'#include\s*[<"]([^>"]+)[>"]')

# Static patterns for common C/C++ bugs — used to generate hints for the LLM
_BUG_PATTERNS = [
    (re.compile(r'\bprintf\s*\(\s*[a-zA-Z_]\w*\s*\)'), "Potential format string vulnerability: user-controlled argument as printf format string"),
    (re.compile(r'\bscanf\s*\(\s*"%s"'), "Unbounded scanf %s: missing field width allows buffer overflow"),
    (re.compile(r'\bstrcpy\s*\('), "Unbounded strcpy: no length check, potential buffer overflow"),
    (re.compile(r'\bgets\s*\('), "Use of gets(): always a buffer overflow vulnerability"),
    (re.compile(r'\bmalloc\s*\([^)]+\)\s*;(?!\s*if)'), "malloc result used without NULL check"),
    (re.compile(r'\bfree\s*\(\s*(\w+)\s*\)(?!.*\1\s*=\s*NULL)'), "free() without setting pointer to NULL: risk of use-after-free"),
    (re.compile(r'\b(\w+)\s*/\s*(\w+)(?!.*==\s*0)'), "Potential division by zero: divisor not checked"),
    (re.compile(r'\bmemcpy\s*\([^,]+,[^,]+,[^)]+\)(?!.*if\s*\()'), "memcpy without bounds validation: potential buffer overflow"),
]


def detect_static_hints(content: str, filepath: str) -> List[Dict[str, str]]:
    """Scan source code for common bug patterns using regex.

    These hints are not definitive bugs but guide the LLM to focus on
    likely problem areas for higher precision.

    Args:
        content: The source code to scan.
        filepath: Path of the file being scanned.

    Returns:
        List of hint dicts with 'line', 'pattern', and 'hint' keys.
    """
    hints = []
    lines = content.split("\n")
    for line_num, line in enumerate(lines, 1):
        for pattern, hint_text in _BUG_PATTERNS:
            if pattern.search(line):
                hints.append({
                    "line": line_num,
                    "pattern": line.strip(),
                    "hint": hint_text,
                })
    return hints


def scan_directory(input_path: str) -> Dict[str, str]:
    """Scan directory recursively for C/C++ source files.

    Args:
        input_path: Root directory to scan.

    Returns:
        Dict mapping relative file path -> file content.
    """
    files = {}
    for root, _dirs, filenames in os.walk(input_path):
        for filename in filenames:
            ext = os.path.splitext(filename)[1].lower()
            if ext in C_CPP_EXTENSIONS:
                full_path = os.path.join(root, filename)
                rel_path = os.path.relpath(full_path, input_path)
                try:
                    with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                        files[rel_path] = f.read()
                except OSError as e:
                    logger.warning("Could not read %s: %s", full_path, e)
    logger.info("Scanned %d C/C++ files from %s", len(files), input_path)
    return files


def build_dependency_map(files: Dict[str, str]) -> Dict[str, List[str]]:
    """Build a dependency map based on #include directives.

    Args:
        files: Dict mapping filepath -> source code.

    Returns:
        Dict mapping filepath -> list of included file paths.
    """
    dep_map = {}
    file_basenames = {}
    for filepath in files:
        basename = os.path.basename(filepath)
        file_basenames[basename] = filepath

    for filepath, content in files.items():
        includes = INCLUDE_PATTERN.findall(content)
        resolved = []
        for inc in includes:
            inc_basename = os.path.basename(inc)
            if inc_basename in file_basenames:
                resolved.append(file_basenames[inc_basename])
            else:
                resolved.append(inc)
        dep_map[filepath] = resolved

    return dep_map


def get_file_context(
    filepath: str,
    files: Dict[str, str],
    dep_map: Dict[str, List[str]],
    max_context_files: int = 3,
) -> str:
    """Get context from dependencies of a file.

    Args:
        filepath: The file to get context for.
        files: All scanned files.
        dep_map: Dependency map.
        max_context_files: Maximum number of dependency files to include.

    Returns:
        Concatenated content of dependency files.
    """
    context_parts = []
    deps = dep_map.get(filepath, [])
    count = 0
    for dep in deps:
        if dep in files and count < max_context_files:
            context_parts.append(f"// --- {dep} ---\n{files[dep]}")
            count += 1
    return "\n\n".join(context_parts)


def chunk_files_for_analysis(
    files: Dict[str, str], max_chars: int = 15000
) -> List[Dict[str, str]]:
    """Group small files together for batch analysis.

    Args:
        files: Dict mapping filepath -> source code.
        max_chars: Maximum characters per chunk.

    Returns:
        List of file groups, each a dict of filepath -> content.
    """
    chunks = []
    current_chunk = {}
    current_size = 0

    for filepath, content in files.items():
        file_size = len(content)
        if file_size > max_chars:
            chunks.append({filepath: content})
        elif current_size + file_size > max_chars:
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = {filepath: content}
            current_size = file_size
        else:
            current_chunk[filepath] = content
            current_size += file_size

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def detect_module_boundaries(
    files: Dict[str, str], dep_map: Dict[str, List[str]]
) -> List[List[str]]:
    """Identify groups of tightly-coupled files (modules).

    Args:
        files: All scanned files.
        dep_map: Dependency map.

    Returns:
        List of modules, each a list of filepaths.
    """
    visited = set()
    modules = []

    def dfs(node: str, module: List[str]):
        if node in visited or node not in files:
            return
        visited.add(node)
        module.append(node)
        for dep in dep_map.get(node, []):
            dfs(dep, module)
        for other, deps in dep_map.items():
            if node in deps:
                dfs(other, module)

    for filepath in files:
        if filepath not in visited:
            module = []
            dfs(filepath, module)
            if module:
                modules.append(module)

    return modules
