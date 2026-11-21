"""Token usage, cost, and fail-fast behaviour of the model layer. No network calls."""

from types import SimpleNamespace

import pytest

import httpx

from app.agent.llm import GeminiLLM, LLMError, Usage, network_error, timeout_error, usage_from_response
from app.agent.pricing import cost_usd
from app.config import Settings


def test_cost_uses_list_price_per_million_tokens():
    usage = Usage(model="gemini-3.8-flash", tokens_in=1_000_000, tokens_out=1_000_000)
    assert cost_usd(usage) == pytest.approx(0.75 + 3.75)


def test_lite_model_is_cheaper_than_flash_for_the_same_call():
    flash = cost_usd(Usage(model="gemini-3.8-flash", tokens_in=800, tokens_out=60))
    lite = cost_usd(Usage(model="gemini-3.5-flash-lite", tokens_in=800, tokens_out=60))
    assert 0 < lite < flash


def test_unknown_model_costs_zero_instead_of_guessing():
    assert cost_usd(Usage(model="some-new-model", tokens_in=500, tokens_out=500)) == 0.0


def test_usage_counts_thinking_tokens_as_output():
    meta = SimpleNamespace(prompt_token_count=120, candidates_token_count=30, thoughts_token_count=50)
    usage = usage_from_response(SimpleNamespace(usage_metadata=meta), "gemini-3.8-flash")
    assert usage == Usage(model="gemini-3.8-flash", tokens_in=120, tokens_out=80)


def test_missing_usage_metadata_reports_zero_tokens():
    usage = usage_from_response(SimpleNamespace(usage_metadata=None), "gemini-3.8-flash")
    assert (usage.tokens_in, usage.tokens_out) == (0, 0)


def test_timeout_becomes_retryable_error():
    err = timeout_error(20.0)
    assert isinstance(err, LLMError)
    assert err.retryable and err.code == "model_timeout"


class _ScriptedGemini(GeminiLLM):
    """GeminiLLM with the network call replaced by a per-model script."""

    def __init__(self, outcomes: dict[str, list], *, answer: str = "flash", fallback: str | None = None) -> None:
        super().__init__("test-key", "lite", answer, timeout_s=1.0, fallback_model=fallback)
        self.outcomes = outcomes
        self.calls: list[str] = []

    async def _call(self, model, contents, config):
        self.calls.append(model)
        outcome = self.outcomes[model].pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        meta = SimpleNamespace(prompt_token_count=10, candidates_token_count=5, thoughts_token_count=0)
        return SimpleNamespace(text=outcome, usage_metadata=meta)


BUSY = LLMError("Gemini error 503", retryable=True, code="model_unavailable")


async def test_busy_answer_model_falls_back_to_the_small_model():
    llm = _ScriptedGemini({"flash": [BUSY], "lite": ["Answer [refunds:1:0]"]})
    reply = await llm.generate("system", "prompt")
    assert llm.calls == ["flash", "lite"]
    assert reply.value == "Answer [refunds:1:0]" and reply.usage.model == "lite"


async def test_non_retryable_answer_error_does_not_fall_back():
    fatal = LLMError("Gemini error 400", retryable=False, code="model_unavailable")
    llm = _ScriptedGemini({"flash": [fatal], "lite": ["unused"]})
    with pytest.raises(LLMError):
        await llm.generate("system", "prompt")
    assert llm.calls == ["flash"]


async def test_fallback_failure_surfaces_the_error():
    llm = _ScriptedGemini({"flash": [BUSY], "lite": [BUSY]})
    with pytest.raises(LLMError):
        await llm.generate("system", "prompt")


async def test_busy_classify_model_falls_back_to_the_answer_model():
    label = '{"intent": "policy_question", "search_query": "refunds"}'
    llm = _ScriptedGemini({"lite": [BUSY], "flash": [label]})
    reply = await llm.classify("How do refunds work?", "")
    assert llm.calls == ["lite", "flash"]
    assert reply.value.intent == "policy_question" and reply.usage.model == "flash"


async def test_timeout_does_not_fall_back_so_waits_do_not_stack():
    slow = timeout_error(1.0)
    llm = _ScriptedGemini({"flash": [slow], "lite": ["unused"]})
    with pytest.raises(LLMError) as err:
        await llm.generate("system", "prompt")
    assert err.value.code == "model_timeout" and llm.calls == ["flash"]


def test_network_failure_becomes_retryable_error():
    err = network_error(httpx.ConnectError("refused"))
    assert err.retryable and err.code == "model_unreachable"


class _RecordingGemini(_ScriptedGemini):
    def __init__(self, outcomes: dict[str, list], thinking: str | None) -> None:
        GeminiLLM.__init__(self, "test-key", "lite", "flash", timeout_s=1.0, answer_thinking_level=thinking)
        self.outcomes = outcomes
        self.calls: list[str] = []
        self.configs: list = []

    async def _call(self, model, contents, config):
        self.configs.append(config)
        return await super()._call(model, contents, config)


async def test_thinking_level_applies_to_the_answer_model_only():
    llm = _RecordingGemini({"flash": [BUSY], "lite": ["Answer [refunds:1:0]"]}, thinking="low")
    await llm.generate("system", "prompt")
    flash_config, lite_config = llm.configs
    assert flash_config.thinking_config.thinking_level.lower() == "low"
    assert lite_config.thinking_config is None


async def test_no_thinking_level_leaves_the_model_default():
    llm = _RecordingGemini({"flash": ["Answer [refunds:1:0]"]}, thinking=None)
    await llm.generate("system", "prompt")
    assert llm.configs[0].thinking_config is None


def test_lite_answers_by_default_with_flash_as_the_fallback():  # review H2, log P11
    s = Settings(_env_file=None)
    assert (s.gemini_classify_model, s.gemini_answer_model, s.gemini_fallback_model) == (
        "gemini-3.5-flash-lite", "gemini-3.5-flash-lite", "gemini-3.8-flash")


async def test_fallback_model_backs_up_both_calls_when_one_model_does_both():
    label = '{"intent": "policy_question", "search_query": "refunds"}'
    llm = _ScriptedGemini({"lite": [BUSY, BUSY], "flash": [label, "Answer [refunds:1:0]"]}, answer="lite",
                          fallback="flash")
    await llm.classify("How do refunds work?", "")
    reply = await llm.generate("system", "prompt")
    assert llm.calls == ["lite", "flash", "lite", "flash"]
    assert reply.usage.model == "flash"
