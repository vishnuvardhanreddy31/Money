"""
QGenie SDK Client - OpenAI-compatible wrapper for QGenie API.

The QGenie SDK provides an interface similar to the OpenAI API for
code analysis and debugging tasks.
"""

import json
import logging
from openai import OpenAI

logger = logging.getLogger(__name__)

QGENIE_BASE_URL = "https://qgenie-api.qualcomm.com/v1"


class QGenieClient:
    """Client for the QGenie SDK, wrapping OpenAI-compatible endpoints."""

    def __init__(self, api_key: str, base_url: str = QGENIE_BASE_URL):
        self.api_key = api_key
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
        )
        self.model = "qgenie-coder"

    def analyze_code(self, code: str, filepath: str, context: str = "") -> dict:
        """Analyze a code snippet for bugs using QGenie.

        Args:
            code: The source code to analyze.
            filepath: Path of the file being analyzed.
            context: Additional context (e.g., related files, headers).

        Returns:
            A dict with detected bugs and suggested fixes.
        """
        system_prompt = self._build_system_prompt()
        user_prompt = self._build_analysis_prompt(code, filepath, context)

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content
            return json.loads(content)
        except Exception as e:
            logger.error("QGenie API call failed for %s: %s", filepath, e)
            return {"bugs": []}

    def analyze_cross_module(self, files_content: dict, dependency_map: dict) -> dict:
        """Analyze cross-module dependencies for architectural bugs.

        Args:
            files_content: Dict mapping filepath -> source code.
            dependency_map: Dict mapping filepath -> list of dependencies.

        Returns:
            A dict with detected cross-module bugs.
        """
        system_prompt = self._build_system_prompt()
        user_prompt = self._build_cross_module_prompt(files_content, dependency_map)

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content
            return json.loads(content)
        except Exception as e:
            logger.error("QGenie cross-module analysis failed: %s", e)
            return {"bugs": []}

    def _build_system_prompt(self) -> str:
        return """You are an expert C/C++ code debugging agent. Your task is to analyze
source code and identify REAL, CONFIRMED bugs with the highest possible precision.
Precision is critical: only report bugs you are confident are genuine issues.
Do NOT report stylistic preferences, best-practice suggestions, or speculative issues.

You must detect these categories of bugs:

1. Memory Management (buffer overflows, use-after-free, double-free, memory leaks, null pointer dereferences)
2. Concurrency (race conditions, deadlocks, missing synchronization on shared state)
3. Logic Errors (off-by-one, incorrect conditions, wrong operator, missing null terminator)
4. Type Safety (integer overflow/underflow, implicit narrowing conversions, format string mismatches)
5. Resource Management (file handle leaks, socket leaks, missing cleanup on error paths)
6. API Misuse (incorrect function arguments, unchecked return values, wrong calling conventions)
7. Security (format string attacks, command injection, path traversal, unbounded input)
8. Undefined Behavior (signed overflow, sequence point violations, strict aliasing violations)

For each bug found, you MUST provide ALL of the following:
- "line_start" and "line_end": The exact line numbers (1-indexed) of the buggy code
- "buggy_code": The exact code snippet that contains the bug (verbatim from the source)
- "fixed_code": A corrected version of the code that resolves the bug completely
- "description": A detailed technical explanation with THREE parts:
    (a) ROOT CAUSE: What exactly is wrong and why it is a bug
    (b) IMPACT: What can happen at runtime (crash, data corruption, security exploit, etc.)
    (c) FIX RATIONALE: Why the suggested fix resolves the issue
- "explanation": A concise plain-language summary suitable for a developer unfamiliar with the bug pattern
- "severity": One of "LOW", "MEDIUM", or "HIGH" based on:
    HIGH = crash, security vulnerability, data corruption, or undefined behavior
    MEDIUM = resource leak, logic error with limited impact, potential data loss
    LOW = minor issue, defensive coding improvement, edge case handling
- "category": One of "Memory Management", "Concurrency", "Logic Error", "Type Safety",
              "Resource Management", "API Misuse", "Security", "Undefined Behavior"
- "confidence": One of "HIGH", "MEDIUM", or "LOW" indicating how certain you are this is a real bug
    HIGH = definitely a bug based on code evidence
    MEDIUM = likely a bug but depends on runtime context
    LOW = possible issue that may not manifest in practice

Respond ONLY with valid JSON in this format:
{
  "bugs": [
    {
      "line_start": <int>,
      "line_end": <int>,
      "buggy_code": "<string>",
      "fixed_code": "<string>",
      "description": "<string>",
      "explanation": "<string>",
      "severity": "LOW|MEDIUM|HIGH",
      "category": "<string>",
      "confidence": "LOW|MEDIUM|HIGH"
    }
  ]
}

If no bugs are found, return {"bugs": []}.
Only report bugs with MEDIUM or HIGH confidence."""

    def _build_analysis_prompt(self, code: str, filepath: str, context: str) -> str:
        prompt = f"""Analyze the following C/C++ source file for bugs.

File: {filepath}
```
{code}
```"""
        if context:
            prompt += f"""

Additional context (related headers/dependencies):
```
{context}
```"""
        prompt += """

Instructions:
1. Read the code line by line, tracking variable state, allocations, and control flow.
2. For each function, check: parameter validation, return value handling, bounds checking,
   null checks, resource cleanup on all exit paths, and thread safety.
3. Identify ALL real bugs — not style issues or best-practice suggestions.
4. For each bug, provide the exact buggy code verbatim, a corrected version, a detailed
   description (root cause, impact, fix rationale), and a plain-language explanation.
5. Be precise with line numbers (1-indexed from the start of the file).
6. Only report bugs you are confident about (MEDIUM or HIGH confidence).

Return your findings as JSON."""
        return prompt

    def _build_cross_module_prompt(self, files_content: dict, dependency_map: dict) -> str:
        prompt = "Analyze the following multi-module C/C++ codebase for cross-module bugs.\n\n"
        prompt += "== Dependency Map ==\n"
        for filepath, deps in dependency_map.items():
            prompt += f"{filepath} depends on: {', '.join(deps)}\n"

        prompt += "\n== Source Files ==\n"
        for filepath, code in files_content.items():
            prompt += f"\n--- {filepath} ---\n```\n{code}\n```\n"

        prompt += """
Focus on cross-module issues that cannot be detected by analyzing files in isolation:
- Mismatched function signatures between declaration and definition
- Incorrect assumptions about shared state across modules
- Race conditions on shared resources accessed from multiple modules
- Dependency ordering issues and initialization races
- ABI compatibility problems between compilation units
- Header guard issues causing multiple definitions
- Buffer size mismatches between caller and callee across modules
- Resource ownership confusion (who allocates vs who frees)

For each cross-module bug found:
1. List ALL files involved in the bug
2. Provide the buggy code from the caller or most relevant location
3. Provide a corrected version
4. Explain the root cause, impact, and fix rationale in the description
5. Include a plain-language explanation of the cross-module interaction that causes the bug

Return findings as JSON with file paths included."""
        return prompt
