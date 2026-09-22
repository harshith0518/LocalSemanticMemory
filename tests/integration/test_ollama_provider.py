"""The local Ollama backup is selected deliberately and never falls through to cloud routes."""

import json

import httpx
import pytest

from jarvis.config import OLLAMA_BASE_URL, OllamaSettings
from jarvis.errors import ApplicationError
from jarvis.providers import FreeChatProvider, NvidiaExtractor, NvidiaResponder, OllamaProvider


def local_ollama_env(monkeypatch, *, enabled="true", private_direct="false"):
    monkeypatch.setenv("JARVIS_INFERENCE_PROVIDER", "ollama")
    monkeypatch.setenv("JARVIS_OLLAMA_ENABLED", enabled)
    monkeypatch.setenv("JARVIS_OLLAMA_BASE_URL", OLLAMA_BASE_URL)
    monkeypatch.setenv("JARVIS_OLLAMA_API_KEY", "ollama")
    monkeypatch.setenv("JARVIS_OLLAMA_EXTRACTOR_MODEL", "qwen3:4b")
    monkeypatch.setenv("JARVIS_OLLAMA_RESPONDER_MODEL", "qwen3:4b")
    monkeypatch.setenv("JARVIS_OLLAMA_EMBEDDING_MODEL", "qwen3-embedding:0.6b")
    monkeypatch.setenv("JARVIS_OLLAMA_PRIVATE_DIRECT", private_direct)


def schema_messages(*_args, **_kwargs):
    return [
        {"role": "system", "content": "Return only JSON."},
        {"role": "user", "content": json.dumps({"OUTPUT_SCHEMA": {"type": "object"}})},
    ]


def test_ollama_is_an_explicit_local_route_with_structured_requests(monkeypatch):
    local_ollama_env(monkeypatch, private_direct="true")
    monkeypatch.setattr("jarvis.providers.messages", schema_messages)
    monkeypatch.setattr("jarvis.answers.answer_messages", schema_messages)
    extractor = NvidiaExtractor.from_env()
    responder = NvidiaResponder.from_env()

    assert isinstance(extractor, OllamaProvider)
    assert isinstance(responder, OllamaProvider)
    assert extractor.endpoint == responder.endpoint == f"{OLLAMA_BASE_URL}/chat/completions"
    assert extractor.model == responder.model == "qwen3:4b"
    assert extractor.enabled and responder.enabled
    assert extractor.unfamiliar_questions and responder.unfamiliar_sources
    assert responder.private_direct
    assert not extractor.unfamiliar_mode and not responder.unfamiliar_mode

    extraction_body, _ = extractor.prepare(None)
    answer_body, _ = responder.prepare(None)
    for body, name in ((extraction_body, "jarvis_extraction"), (answer_body, "jarvis_answer")):
        assert body["response_format"] == {
            "type": "json_schema",
            "json_schema": {"name": name, "strict": True, "schema": {"type": "object"}},
        }
        assert body["reasoning_effort"] == "none"
        assert "chat_template_kwargs" not in body
        assert "provider" not in body and "transforms" not in body


def test_ollama_transport_uses_only_the_host_gateway_and_dummy_authorization(monkeypatch):
    local_ollama_env(monkeypatch)
    monkeypatch.setattr("jarvis.answers.answer_messages", schema_messages)
    captured = []

    def transport(request):
        captured.append(request)
        return httpx.Response(
            200,
            json={
                "model": "qwen3:4b",
                "usage": {"prompt_tokens": 17, "completion_tokens": 9},
                "choices": [{"finish_reason": "stop", "message": {"content": "{}"}}],
            },
        )

    provider = NvidiaResponder.from_env()
    provider._transport = httpx.MockTransport(transport)
    body, _ = provider.prepare(None)
    completion = provider.complete(body)

    assert completion.model == "qwen3:4b"
    assert completion.input_tokens == 17 and completion.output_tokens == 9
    assert len(captured) == 1
    assert str(captured[0].url) == f"{OLLAMA_BASE_URL}/chat/completions"
    assert captured[0].headers["authorization"] == "Bearer ollama"
    assert json.loads(captured[0].content) == body
    assert "googleapis.com" not in str(captured[0].url)
    assert "openrouter.ai" not in str(captured[0].url)


def test_ollama_selection_never_constructs_a_cloud_provider(monkeypatch):
    local_ollama_env(monkeypatch, enabled="false")

    def cloud_provider(*_args, **_kwargs):
        raise AssertionError("Ollama must not select a cloud provider")

    monkeypatch.setattr(FreeChatProvider, "from_env", cloud_provider)
    extractor = NvidiaExtractor.from_env()
    responder = NvidiaResponder.from_env()

    assert isinstance(extractor, OllamaProvider)
    assert isinstance(responder, OllamaProvider)
    assert not extractor.enabled and not responder.enabled
    with pytest.raises(ApplicationError, match="provider_disabled"):
        extractor.prepare(None)


@pytest.mark.parametrize(
    "name,value",
    [
        ("JARVIS_OLLAMA_BASE_URL", "http://localhost:11434/v1"),
        ("JARVIS_OLLAMA_BASE_URL", "https://host.docker.internal:11434/v1"),
        ("JARVIS_OLLAMA_BASE_URL", "http://host.docker.internal:11434/not-v1"),
        ("JARVIS_OLLAMA_API_KEY", "a-real-secret-does-not-belong-here"),
        ("JARVIS_OLLAMA_EXTRACTOR_MODEL", "another-model"),
        ("JARVIS_OLLAMA_EMBEDDING_MODEL", "different-embedding"),
        ("JARVIS_OLLAMA_ENABLED", "yes"),
    ],
)
def test_ollama_configuration_rejects_nonlocal_or_unbounded_values(monkeypatch, name, value):
    local_ollama_env(monkeypatch)
    monkeypatch.setenv(name, value)

    with pytest.raises(ValueError):
        OllamaSettings.from_env()
    with pytest.raises(ApplicationError, match="invalid_input"):
        OllamaProvider.from_env(role="responder")


def test_ollama_unreachable_is_provider_failed_without_a_cloud_fallback(monkeypatch):
    local_ollama_env(monkeypatch)
    monkeypatch.setattr("jarvis.answers.answer_messages", schema_messages)
    attempted = []

    def unavailable(request):
        attempted.append(request)
        raise httpx.ConnectError("local server unavailable", request=request)

    provider = NvidiaResponder.from_env()
    provider._transport = httpx.MockTransport(unavailable)
    body, _ = provider.prepare(None)
    with pytest.raises(ApplicationError, match="provider_failed"):
        provider.complete(body)

    assert [str(request.url) for request in attempted] == [f"{OLLAMA_BASE_URL}/chat/completions"]
