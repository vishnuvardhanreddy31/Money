"""Tests for the scanner module."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scanner import (
    scan_directory,
    build_dependency_map,
    get_file_context,
    detect_module_boundaries,
    chunk_files_for_analysis,
)


def _populate_dir(tmpdir, structure):
    """Populate a directory with files from a structure dict."""
    for relpath, content in structure.items():
        full_path = os.path.join(tmpdir, relpath)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w") as f:
            f.write(content)


def test_scan_directory_finds_c_files():
    with tempfile.TemporaryDirectory() as tmpdir:
        _populate_dir(tmpdir, {
            "main.c": '#include <stdio.h>\nint main() { return 0; }',
            "utils.h": '#ifndef UTILS_H\n#define UTILS_H\nvoid helper();\n#endif',
            "utils.c": '#include "utils.h"\nvoid helper() {}',
            "readme.txt": "Not a C file",
        })
        files = scan_directory(tmpdir)
        assert "main.c" in files
        assert "utils.h" in files
        assert "utils.c" in files
        assert "readme.txt" not in files
        assert len(files) == 3


def test_scan_directory_handles_subdirectories():
    with tempfile.TemporaryDirectory() as tmpdir:
        _populate_dir(tmpdir, {
            "src/main.cpp": 'int main() {}',
            "src/lib/helper.hpp": 'void help();',
            "include/api.h": '#pragma once',
        })
        files = scan_directory(tmpdir)
        assert len(files) == 3
        paths = list(files.keys())
        assert any("main.cpp" in p for p in paths)
        assert any("helper.hpp" in p for p in paths)
        assert any("api.h" in p for p in paths)


def test_scan_empty_directory():
    with tempfile.TemporaryDirectory() as tmpdir:
        files = scan_directory(tmpdir)
        assert files == {}


def test_build_dependency_map():
    files = {
        "main.c": '#include "utils.h"\n#include <stdio.h>\nint main() {}',
        "utils.h": '#ifndef UTILS_H\n#define UTILS_H\nvoid helper();\n#endif',
        "utils.c": '#include "utils.h"\nvoid helper() {}',
    }
    dep_map = build_dependency_map(files)
    assert "utils.h" in dep_map["main.c"]
    assert "utils.h" in dep_map["utils.c"]
    assert "stdio.h" in dep_map["main.c"]


def test_get_file_context():
    files = {
        "main.c": '#include "utils.h"\nint main() {}',
        "utils.h": 'void helper();',
    }
    dep_map = build_dependency_map(files)
    context = get_file_context("main.c", files, dep_map)
    assert "helper" in context


def test_detect_module_boundaries():
    files = {
        "a.c": '#include "a.h"',
        "a.h": "void a();",
        "b.c": '#include "b.h"',
        "b.h": "void b();",
    }
    dep_map = build_dependency_map(files)
    modules = detect_module_boundaries(files, dep_map)
    assert len(modules) == 2
    for module in modules:
        assert len(module) == 2


def test_chunk_files():
    files = {f"file{i}.c": "x" * 100 for i in range(10)}
    chunks = chunk_files_for_analysis(files, max_chars=350)
    total_files = sum(len(c) for c in chunks)
    assert total_files == 10


def test_chunk_large_file():
    files = {"big.c": "x" * 20000, "small.c": "y" * 50}
    chunks = chunk_files_for_analysis(files, max_chars=15000)
    assert len(chunks) >= 2


if __name__ == "__main__":
    test_scan_directory_finds_c_files()
    test_scan_directory_handles_subdirectories()
    test_scan_empty_directory()
    test_build_dependency_map()
    test_get_file_context()
    test_detect_module_boundaries()
    test_chunk_files()
    test_chunk_large_file()
    print("All scanner tests passed!")
