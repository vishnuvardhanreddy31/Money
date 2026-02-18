"""Tests for the qgenie_sdk module — rate limiting, caching, and fallback."""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from qgenie_sdk import RateLimiter, ResponseCache, QGenieClient


# ---------------------------------------------------------------------------
# RateLimiter tests
# ---------------------------------------------------------------------------

def test_rate_limiter_allows_within_limit():
    """Requests within the limit should not be delayed."""
    rl = RateLimiter(max_requests=5, period=60.0)
    start = time.monotonic()
    for _ in range(5):
        rl.wait()
    elapsed = time.monotonic() - start
    assert elapsed < 1.0, f"Expected no delay, got {elapsed:.2f}s"


def test_rate_limiter_blocks_when_exceeded():
    """Exceeding the limit should block until the window moves."""
    rl = RateLimiter(max_requests=2, period=0.5)
    rl.wait()
    rl.wait()
    start = time.monotonic()
    rl.wait()  # should block ~0.5s
    elapsed = time.monotonic() - start
    assert elapsed >= 0.3, f"Expected delay >=0.3s, got {elapsed:.2f}s"


# ---------------------------------------------------------------------------
# ResponseCache tests
# ---------------------------------------------------------------------------

def test_cache_hit_and_miss():
    cache = ResponseCache(enabled=True)
    result = {"bugs": [{"id": "BUG-001"}]}

    assert cache.get("m", "sys", "usr") is None
    cache.put("m", "sys", "usr", result)
    cached = cache.get("m", "sys", "usr")
    assert cached is not None
    assert cached["bugs"][0]["id"] == "BUG-001"


def test_cache_disabled():
    cache = ResponseCache(enabled=False)
    cache.put("m", "sys", "usr", {"bugs": []})
    assert cache.get("m", "sys", "usr") is None


def test_cache_stats():
    cache = ResponseCache(enabled=True)
    cache.put("m", "s", "u", {"bugs": []})
    cache.get("m", "s", "u")  # hit
    cache.get("m", "s", "other")  # miss
    stats = cache.stats
    assert stats["hits"] == 1
    assert stats["misses"] == 1
    assert stats["size"] == 1


# ---------------------------------------------------------------------------
# QGenieClient fallback model tests
# ---------------------------------------------------------------------------

class _FakeOpenAIClient:
    """Minimal stand-in for ``openai.OpenAI`` to test client behaviour."""

    def __init__(self, fail_models=None):
        """
        Args:
            fail_models: set of model names that should raise on ``create``.
        """
        self.fail_models = fail_models or set()
        self.calls = []

    @property
    def chat(self):
        return self

    @property
    def completions(self):
        return self

    def create(self, *, model, messages, temperature, response_format):
        self.calls.append(model)
        if model in self.fail_models:
            raise RuntimeError(f"Model {model} unavailable")

        class _Msg:
            content = '{"bugs": [{"id": "BUG-001", "model_used": "%s"}]}' % model

        class _Choice:
            message = _Msg()

        class _Resp:
            choices = [_Choice()]

        return _Resp()


def _make_client(fail_models=None, fallback_models=None, enable_cache=True):
    """Create a ``QGenieClient`` backed by the fake OpenAI client."""
    client = QGenieClient.__new__(QGenieClient)
    client.api_key = "test-key"
    client.model = "qgenie-coder"
    client.fallback_models = fallback_models or []
    client.rate_limiter = None
    client.cache = ResponseCache(enabled=enable_cache)
    client.client = _FakeOpenAIClient(fail_models=fail_models or set())
    return client


def test_primary_model_success():
    c = _make_client()
    result = c.analyze_code("int main(){}", "main.c")
    assert result["bugs"][0]["model_used"] == "qgenie-coder"
    assert c.client.calls == ["qgenie-coder"]


def test_fallback_on_primary_failure():
    c = _make_client(
        fail_models={"qgenie-coder"},
        fallback_models=["fallback-1", "fallback-2"],
    )
    result = c.analyze_code("int main(){}", "main.c")
    assert result["bugs"][0]["model_used"] == "fallback-1"
    assert c.client.calls == ["qgenie-coder", "fallback-1"]


def test_second_fallback():
    c = _make_client(
        fail_models={"qgenie-coder", "fallback-1"},
        fallback_models=["fallback-1", "fallback-2"],
    )
    result = c.analyze_code("int main(){}", "main.c")
    assert result["bugs"][0]["model_used"] == "fallback-2"


def test_all_models_fail():
    c = _make_client(
        fail_models={"qgenie-coder", "fb"},
        fallback_models=["fb"],
    )
    result = c.analyze_code("int main(){}", "main.c")
    assert result == {"bugs": []}


def test_caching_avoids_duplicate_calls():
    c = _make_client()
    r1 = c.analyze_code("int main(){}", "main.c")
    r2 = c.analyze_code("int main(){}", "main.c")
    assert r1 == r2
    # The underlying OpenAI client should have been called only once
    assert len(c.client.calls) == 1


def test_cross_module_with_fallback():
    c = _make_client(
        fail_models={"qgenie-coder"},
        fallback_models=["backup"],
    )
    result = c.analyze_cross_module(
        {"a.c": "void a(){}", "b.c": "void b(){}"},
        {"a.c": [], "b.c": ["a.c"]},
    )
    assert len(result["bugs"]) == 1
    assert result["bugs"][0]["model_used"] == "backup"


# ---------------------------------------------------------------------------
# Analyzer large-file splitting tests
# ---------------------------------------------------------------------------

from analyzer import _split_file_into_chunks


def test_split_small_file_unchanged():
    content = "int main() { return 0; }"
    chunks = _split_file_into_chunks(content, "main.c", max_chars=1000)
    assert len(chunks) == 1
    assert chunks[0]["filepath"] == "main.c"
    assert chunks[0]["offset"] == 1


def test_split_large_file_produces_chunks():
    # Create a file well over the threshold
    lines = [f"int var_{i} = {i};" for i in range(500)]
    content = "\n".join(lines)
    chunks = _split_file_into_chunks(content, "big.c", max_chars=500)
    assert len(chunks) > 1
    # All chunks should reference the original filename
    for chunk in chunks:
        assert "big.c" in chunk["filepath"]


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_rate_limiter_allows_within_limit()
    test_rate_limiter_blocks_when_exceeded()
    test_cache_hit_and_miss()
    test_cache_disabled()
    test_cache_stats()
    test_primary_model_success()
    test_fallback_on_primary_failure()
    test_second_fallback()
    test_all_models_fail()
    test_caching_avoids_duplicate_calls()
    test_cross_module_with_fallback()
    test_split_small_file_unchanged()
    test_split_large_file_produces_chunks()
    print("All qgenie_sdk tests passed!")
