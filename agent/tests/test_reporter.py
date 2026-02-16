"""Tests for the reporter module."""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from reporter import generate_report


def test_generate_report_creates_files():
    bugs = [
        {
            "id": "BUG-001",
            "files": ["src/utils.c"],
            "line_start": 12,
            "line_end": 18,
            "buggy_code": "char* copy_string(char* dest, char* src)",
            "fixed_code": "char* copy_string(char* dest, const char* src, size_t n)",
            "description": "Buffer overflow due to missing bounds check",
            "severity": "HIGH",
            "category": "Memory Management",
        }
    ]
    with tempfile.TemporaryDirectory() as tmpdir:
        result_path = generate_report(bugs, tmpdir)

        assert os.path.exists(result_path)
        assert os.path.exists(os.path.join(tmpdir, "report.json"))

        with open(os.path.join(tmpdir, "report.json")) as f:
            data = json.load(f)

        assert len(data["bugs"]) == 1
        assert data["bugs"][0]["id"] == "BUG-001"
        assert data["bugs"][0]["severity"] == "HIGH"


def test_generate_empty_report():
    with tempfile.TemporaryDirectory() as tmpdir:
        generate_report([], tmpdir)

        with open(os.path.join(tmpdir, "report.json")) as f:
            data = json.load(f)

        assert data["bugs"] == []


def test_report_json_schema():
    bugs = [
        {
            "id": "BUG-001",
            "files": ["main.c"],
            "line_start": 1,
            "line_end": 5,
            "buggy_code": "int x = 0;",
            "fixed_code": "int x = 1;",
            "description": "Incorrect initialization",
            "severity": "LOW",
            "category": "Logic Error",
        },
        {
            "id": "BUG-002",
            "files": ["utils.c", "utils.h"],
            "line_start": 10,
            "line_end": 15,
            "buggy_code": "free(ptr);",
            "fixed_code": "if (ptr) { free(ptr); ptr = NULL; }",
            "description": "Use after free possibility",
            "severity": "HIGH",
            "category": "Memory Management",
        },
    ]
    with tempfile.TemporaryDirectory() as tmpdir:
        generate_report(bugs, tmpdir)

        with open(os.path.join(tmpdir, "report.json")) as f:
            data = json.load(f)

        required_fields = [
            "id", "files", "line_start", "line_end",
            "buggy_code", "fixed_code", "description",
            "severity", "category",
        ]
        for bug in data["bugs"]:
            for field in required_fields:
                assert field in bug, f"Missing field: {field}"


if __name__ == "__main__":
    test_generate_report_creates_files()
    test_generate_empty_report()
    test_report_json_schema()
    print("All reporter tests passed!")
