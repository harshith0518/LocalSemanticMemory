import httpx
import pytest

from jarvis.errors import ApplicationError
from jarvis.providers import MODEL, NvidiaExtractor


def response(**changes):
    return {
        "model": MODEL,
        "usage": {"prompt_tokens": 15, "completion_tokens": 10},
        "choices": [{"finish_reason": "stop", "message": {"content": '{"decision":"no_memory"}'}}],
        **changes,
    }


def test_transport_bounds_and_no_model_fallback():
    calls = []

    def send(request):
        calls.append(request)
        return httpx.Response(200, json=response())

    provider = NvidiaExtractor(
        approved=True, key="synthetic-key", transport=httpx.MockTransport(send)
    )
    completion = provider.complete({"model": MODEL, "stream": False})
    assert completion.input_tokens == 15 and completion.output_tokens == 10
    assert completion.model == MODEL
    assert len(calls) == 1 and str(calls[0].url).startswith("https://integrate.api.nvidia.com/")


@pytest.mark.parametrize(
    "failure", ["redirect", "auth", "timeout", "json", "usage", "model", "truncated", "oversized"]
)
def test_provider_failures_are_bounded_and_sanitized(failure, caplog):
    calls = []

    def send(request):
        calls.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout("SYNTHETIC_PRIVATE_SECRET")
        if failure == "redirect":
            return httpx.Response(307, headers={"location": "https://example.com"})
        if failure == "auth":
            return httpx.Response(401, text="SYNTHETIC_PRIVATE_SECRET")
        if failure == "json":
            return httpx.Response(200, text="SYNTHETIC_PRIVATE_SECRET")
        if failure == "oversized":
            return httpx.Response(200, content=b"x" * 262145)
        data = response()
        if failure == "usage":
            data["usage"]["prompt_tokens"] = -1
        if failure == "model":
            data["model"] = "different-model"
        if failure == "truncated":
            data["choices"][0]["finish_reason"] = "length"
        return httpx.Response(200, json=data)

    provider = NvidiaExtractor(
        approved=True, key="SYNTHETIC_PRIVATE_SECRET", transport=httpx.MockTransport(send)
    )
    with pytest.raises(ApplicationError) as caught:
        provider.complete({"model": MODEL})
    assert "SYNTHETIC_PRIVATE_SECRET" not in str(caught.value)
    assert len(calls) == 1
    assert not caplog.records


def test_disabled_provider_makes_no_transport_call():
    def send(request):
        raise AssertionError("Unexpected network request")

    provider = NvidiaExtractor(transport=httpx.MockTransport(send))
    with pytest.raises(ApplicationError, match="provider_disabled"):
        provider.complete({})
