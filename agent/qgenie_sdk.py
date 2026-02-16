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
source code and identify bugs with high precision. You must detect:

1. Memory Management issues (buffer overflows, use-after-free, memory leaks, null pointer dereferences)
2. Concurrency issues (race conditions, deadlocks, missing locks)
3. Logic Errors (off-by-one, incorrect conditions, wrong operator usage)
4. Type Safety issues (integer overflow, implicit conversions, format string mismatches)
5. Resource Management (file handle leaks, socket leaks, missing cleanup)
6. API Misuse (incorrect function arguments, wrong return value handling)
7. Security vulnerabilities (SQL injection, command injection, path traversal)
8. Undefined Behavior (signed overflow, sequence point violations, strict aliasing)

For each bug found, provide:
- The exact line range (line_start, line_end)
- The buggy code snippet
- The corrected code snippet
- A clear technical description of root cause and impact
- Severity level (LOW, MEDIUM, HIGH)
- Category classification

Respond ONLY with valid JSON in this format:
{
  "bugs": [
    {
      "line_start": <int>,
      "line_end": <int>,
      "buggy_code": "<string>",
      "fixed_code": "<string>",
      "description": "<string>",
      "severity": "LOW|MEDIUM|HIGH",
      "category": "<string>"
    }
  ]
}

If no bugs are found, return {"bugs": []}."""

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

Identify ALL bugs in this code. Be thorough and precise with line numbers.
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
Focus on cross-module issues:
- Mismatched function signatures between declaration and definition
- Incorrect assumptions about shared state
- Race conditions on shared resources
- Dependency ordering issues
- ABI compatibility problems
- Header guard issues

Return findings as JSON with file paths included."""
        return prompt
