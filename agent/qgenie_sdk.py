"""
QGenie SDK Client - OpenAI-compatible wrapper for QGenie API.

The QGenie SDK provides an interface similar to the OpenAI API for
code analysis and debugging tasks. Supports fallback models, rate
limiting, and response caching.
"""

import hashlib
import json
import logging
import threading
import time
from typing import List, Optional

from openai import OpenAI

logger = logging.getLogger(__name__)

QGENIE_BASE_URL = "https://qgenie-api.qualcomm.com/v1"


class RateLimiter:
    """Token-bucket rate limiter for API requests.

    Ensures no more than ``max_requests`` are made within a sliding
    window of ``period`` seconds.
    """

    def __init__(self, max_requests: int = 10, period: float = 60.0):
        self.max_requests = max_requests
        self.period = period
        self._timestamps: List[float] = []
        self._lock = threading.Lock()

    def wait(self):
        """Block until a request is allowed under the rate limit."""
        with self._lock:
            now = time.monotonic()
            # Remove timestamps outside the current window
            self._timestamps = [
                t for t in self._timestamps if now - t < self.period
            ]
            if len(self._timestamps) >= self.max_requests:
                sleep_time = self.period - (now - self._timestamps[0])
                if sleep_time > 0:
                    logger.info(
                        "Rate limit reached (%d/%d). Waiting %.1fs...",
                        len(self._timestamps),
                        self.max_requests,
                        sleep_time,
                    )
                    self._lock.release()
                    time.sleep(sleep_time)
                    self._lock.acquire()
                    now = time.monotonic()
                    self._timestamps = [
                        t for t in self._timestamps if now - t < self.period
                    ]
            self._timestamps.append(time.monotonic())


class ResponseCache:
    """In-memory cache for API responses keyed by content hash.

    Avoids redundant API calls when the same code and context are
    analyzed more than once (e.g., across L1/L2 tiers).
    """

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._cache: dict = {}
        self._hits = 0
        self._misses = 0

    @staticmethod
    def _make_key(model: str, system_prompt: str, user_prompt: str) -> str:
        raw = f"{model}|{system_prompt}|{user_prompt}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, model: str, system_prompt: str, user_prompt: str) -> Optional[dict]:
        if not self.enabled:
            return None
        key = self._make_key(model, system_prompt, user_prompt)
        result = self._cache.get(key)
        if result is not None:
            self._hits += 1
            logger.debug("Cache hit (hits=%d, misses=%d)", self._hits, self._misses)
        else:
            self._misses += 1
        return result

    def put(self, model: str, system_prompt: str, user_prompt: str, value: dict):
        if not self.enabled:
            return
        key = self._make_key(model, system_prompt, user_prompt)
        self._cache[key] = value

    @property
    def stats(self) -> dict:
        return {"hits": self._hits, "misses": self._misses, "size": len(self._cache)}


class QGenieClient:
    """Client for the QGenie SDK, wrapping OpenAI-compatible endpoints.

    Supports fallback models, per-minute rate limiting, and response
    caching to reduce token consumption.

    Args:
        api_key: API key for authentication.
        base_url: Base URL of the QGenie API.
        fallback_models: Optional list of model names to try when the
            primary model fails.
        max_requests_per_minute: Maximum API requests per 60-second window.
            Set to 0 to disable rate limiting.
        enable_cache: If True, identical requests are served from an
            in-memory cache instead of calling the API again.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = QGENIE_BASE_URL,
        fallback_models: Optional[List[str]] = None,
        max_requests_per_minute: int = 0,
        enable_cache: bool = True,
    ):
        self.api_key = api_key
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
        )
        self.model = "qgenie-coder"
        self.fallback_models = fallback_models or []
        self.rate_limiter = (
            RateLimiter(max_requests=max_requests_per_minute, period=60.0)
            if max_requests_per_minute > 0
            else None
        )
        self.cache = ResponseCache(enabled=enable_cache)

    def _call_api(self, model: str, system_prompt: str, user_prompt: str) -> dict:
        """Make a single API call with the given model.

        Raises on failure so the caller can attempt fallback models.
        """
        if self.rate_limiter:
            self.rate_limiter.wait()

        response = self.client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        return json.loads(content)

    def _call_with_fallback(
        self, system_prompt: str, user_prompt: str, label: str
    ) -> dict:
        """Try the primary model, then each fallback model in order.

        Args:
            system_prompt: System prompt for the API call.
            user_prompt: User prompt for the API call.
            label: Human-readable label used in log messages.

        Returns:
            Parsed JSON response dict, or ``{"bugs": []}`` if all
            models fail.
        """
        # Check cache first
        cached = self.cache.get(self.model, system_prompt, user_prompt)
        if cached is not None:
            logger.info("Cache hit for %s — skipping API call", label)
            return cached

        models_to_try = [self.model] + self.fallback_models
        for model in models_to_try:
            try:
                logger.debug("Trying model '%s' for %s", model, label)
                result = self._call_api(model, system_prompt, user_prompt)
                self.cache.put(self.model, system_prompt, user_prompt, result)
                if model != self.model:
                    logger.info(
                        "Fallback model '%s' succeeded for %s", model, label
                    )
                return result
            except Exception as e:
                logger.warning(
                    "Model '%s' failed for %s: %s", model, label, e
                )
        logger.error("All models failed for %s", label)
        return {"bugs": []}

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
        return self._call_with_fallback(system_prompt, user_prompt, filepath)

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
        label = "cross-module[%s]" % ",".join(files_content.keys())
        return self._call_with_fallback(system_prompt, user_prompt, label)

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
