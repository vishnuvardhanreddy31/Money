# QGenie Code Debugging Agent

Autonomous code-debugging agent for the **QGenie Summit Hackathon**. Analyzes C/C++ codebases to detect, trace, fix, and explain bugs.

## Architecture

```
agent.py          – Main entry point (CLI + orchestration)
qgenie_sdk.py     – QGenie SDK client (OpenAI-compatible wrapper)
scanner.py        – C/C++ file scanner and dependency mapper
analyzer.py       – Multi-tier bug analysis (L1/L2/L3)
reporter.py       – Report generation (report.json)
Dockerfile        – Container packaging
```

## Workflow

1. **Detect** – Scan the input directory for C/C++ source files
2. **Trace** – Build dependency maps and identify module boundaries
3. **Fix** – Run multi-tier analysis using QGenie SDK:
   - **L1 (Foundational):** Single-file bugs (logic errors, memory issues)
   - **L2 (Advanced Logic):** Bugs spanning multiple functions with dependency context
   - **L3 (Architectural):** Cross-module issues (race conditions, state problems)
4. **Explain** – Generate `report.json` with fixes and technical explanations

## Bug Categories

- Memory Management (buffer overflow, use-after-free, memory leaks)
- Concurrency (race conditions, deadlocks)
- Logic Errors (off-by-one, incorrect conditions)
- Type Safety (integer overflow, format string mismatches)
- Resource Management (file handle leaks)
- API Misuse (incorrect arguments, wrong return handling)
- Security (injection, path traversal)
- Undefined Behavior (signed overflow, aliasing violations)

## Usage

### Direct Execution

```bash
python agent.py <input_code_path> <output_result_path> <qgenie_api_key>
```

### Docker

```bash
# Build
docker build -t qgenie-debug-agent ./agent

# Run
docker run --rm \
  -v /host/input:/data/input \
  -v /host/output:/data/output \
  qgenie-debug-agent \
  /data/input /data/output <qgenie_api_key>
```

## Output Format

The agent generates `report.json` in the output directory:

```json
{
  "bugs": [
    {
      "id": "BUG-001",
      "files": ["src/utils.c"],
      "line_start": 12,
      "line_end": 18,
      "buggy_code": "char* copy_string(...)",
      "fixed_code": "char* copy_string(...)",
      "description": "Buffer overflow due to missing bounds check...",
      "severity": "HIGH",
      "category": "Memory Management"
    }
  ]
}
```

## Requirements

- Python 3.11+
- QGenie API key
- Linux-compatible environment
