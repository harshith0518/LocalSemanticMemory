"""New scale/unfamiliar contracts use the real isolated PostgreSQL database, not live models."""

import asyncio
import json
from pathlib import Path

import httpx
import pytest
from answer_double import FixtureResponder
from memory_double import FixtureExtractor, content, operation

from jarvis.api import create_app
from jarvis.errors import ApplicationError
from jarvis.extraction import PROMPT_VERSION
from jarvis.providers import KIMI_MODEL, MODEL, REVIEWER_ACK, NvidiaExtractor, NvidiaResponder
from jarvis.services import Service
from jarvis.worker import process_one


@pytest.mark.parametrize("model", [MODEL, KIMI_MODEL])
def test_explicit_responder_settings_and_key_selection(monkeypatch, model):
    monkeypatch.setenv("JARVIS_RESPONSE_MODEL", model)
    monkeypatch.setenv("JARVIS_S07_SYNTHETIC_TRIAL_APPROVED", "true")
    monkeypatch.setenv("NEMOTRON_30B_API_KEY", "synthetic-lightning")
    monkeypatch.setenv("KIMI_K3_API_KEY", "synthetic-kimi")
    monkeypatch.setattr("jarvis.answers.answer_messages", lambda *a, **kw: [])
    provider = NvidiaResponder.from_env()
    body, reserved = provider.prepare(None)
    assert body["model"] == model and provider.model == model
    assert body["stream"] is False and body["temperature"] == 0
    assert reserved > body["max_tokens"]
    assert provider._key == ("synthetic-lightning" if model == MODEL else "synthetic-kimi")
    if model == MODEL:
        assert body["chat_template_kwargs"] == {"enable_thinking": False}
        assert "reasoning_effort" not in body and provider.timeout_seconds == 90
    else:
        assert body["reasoning_effort"] == "low" and provider.timeout_seconds == 180


def test_unknown_model_does_not_silently_fallback(monkeypatch):
    monkeypatch.setenv("JARVIS_RESPONSE_MODEL", "not-approved")
    with pytest.raises(ApplicationError, match="invalid_input"):
        NvidiaResponder.from_env()


@pytest.mark.parametrize(
    "flag,ack,enabled",
    [("true", "", False), ("false", REVIEWER_ACK, False), ("true", REVIEWER_ACK, True)],
)
def test_unfamiliar_requires_both_operator_consents(monkeypatch, flag, ack, enabled):
    monkeypatch.delenv("JARVIS_S07_SYNTHETIC_TRIAL_APPROVED", raising=False)
    monkeypatch.setenv("JARVIS_UNFAMILIAR_INFERENCE_APPROVED", flag)
    monkeypatch.setenv("JARVIS_UNFAMILIAR_DATA_POLICY_ACK", ack)
    monkeypatch.setenv("NVIDIA_API_KEY", "synthetic-unfamiliar")
    for provider in (NvidiaExtractor.from_env(), NvidiaResponder.from_env()):
        assert provider.enabled is enabled and provider.unfamiliar_mode is enabled
        if enabled:
            assert provider._key == "synthetic-unfamiliar"


def test_unfamiliar_accepts_unfamiliar_normal_input_but_private_still_denied(engine):
    service = Service(
        engine,
        extractor=NvidiaExtractor(approved=True, unfamiliar=True),
        responder=NvidiaResponder(approved=True, unfamiliar=True, model=MODEL),
    )
    context = service.identity.context("normal")
    source = {
        "record_id": "unfamiliar",
        "raw_transcript": "Synthetic unseen note: amber box holds six screws.",
        "formatted_text": "The amber box holds six screws.",
        "metadata": None,
    }
    options = {"namespace": "unfamiliar", "expected_policy_revision": 0}
    service.import_observations(context, options, json.dumps(source))
    assert service.request_processing(context, options)["requested"] == 1
    packet = service.prepare_answer(
        context, {"namespace": "unfamiliar", "question": "How many screws are in the amber box?"}
    )
    assert len(packet.evidence.sources) == 1
    private = service.identity.context("private")
    for action in [
        lambda: service.request_processing(private, options),
        lambda: service.prepare_answer(private, {"namespace": "unfamiliar", "question": "six"}),
        lambda: service.inference_status(private),
    ]:
        with pytest.raises(ApplicationError, match="private_operation_denied"):
            action()


def test_corpus_pairs_hashes_and_evaluator_label_separation():
    import sys

    sys.path.insert(0, str(Path("eval").resolve()))
    from corpus import validate

    payload, records, manifest, cases = validate()
    assert len(records) == 540 and len(payload) < 1024 * 1024
    assert len(manifest["categories"]) >= 24
    assert len([c for c in cases if c["split"] == "showcase"]) == 30
    assert all("expected_status" not in r for r in records)
    assert any(any(ord(ch) > 127 for ch in r["raw_transcript"]) for r in records)


def test_scale_selection_keeps_relevant_claims_and_complete_variants(engine):
    service = Service(engine, extractor=FixtureExtractor())
    ctx = service.identity.context("normal")
    rows = [
        {
            "record_id": f"r{i:03d}",
            "raw_transcript": f"Project P{i:03d} keeps a blue cabinet.",
            "formatted_text": f"Project P{i:03d} keeps a blue cabinet.",
        }
        for i in range(72)
    ]
    options = {"namespace": "scale", "expected_policy_revision": 0}
    receipt = service.import_observations(ctx, options, "\n".join(map(json.dumps, rows)))
    for i, item in enumerate(receipt.observations):
        source = service.inspect_source(ctx, item.source_id).observation
        claim = content("cabinet", "blue", subject=f"P{i:03d}", scope=f"P{i:03d}")
        op = operation(source.model_dump(mode="json"), claim)
        service.commit_claim(
            ctx, {"expected_policy_revision": 0, "content": claim, "passages": op["passages"]}
        )
    service.request_processing(ctx, options)
    packet = service.lease_next(ctx, namespace="scale")
    assert packet is not None and packet.context_claim_count == 72 and packet.context_bounded
    assert len(packet.memories) <= 16
    assert packet.memories[0].content.scope.key == "P000"
    assert packet.source.raw_text == rows[0]["raw_transcript"]
    assert packet.source.formatted_text == rows[0]["formatted_text"]
    assert len(service.list_memories(ctx, {"namespace": "scale", "limit": 100})["memories"]) == 72
    body, _ = service.extractor.prepare(packet)
    assert "s11" in PROMPT_VERSION and len(json.dumps(body).encode()) < 60000


def test_configuration_endpoint_is_not_a_live_probe_and_never_returns_keys(engine):
    service = Service(engine, extractor=FixtureExtractor(), responder=FixtureResponder())

    async def run():
        app = create_app(service)
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client,
        ):
            response = await client.get("/inference", headers={"X-Jarvis-Mode": "normal"})
            assert response.status_code == 200 and response.json()["provider_contacted"] is False
            assert "_key" not in response.text and "synthetic-unfamiliar" not in response.text
            for path in ("/inference", "/trial/corpus", "/trial/showcase"):
                assert (
                    await client.get(path, headers={"X-Jarvis-Mode": "private"})
                ).status_code == 403

    asyncio.run(run())
    assert service.extractor.calls == service.responder.calls == 0


def test_unseen_corpus_can_complete_contract_path_without_fixture_matching(engine):
    def generic(data):
        source = data["CURRENT_SOURCE"]
        return {
            "decision": "extracted",
            "operations": [
                operation(source, content("location", "blue tin", scope="synthetic-unseen"))
            ],
        }

    service = Service(engine, extractor=FixtureExtractor(generic), responder=FixtureResponder())
    ctx = service.identity.context("normal")
    options = {"namespace": "review-path", "expected_policy_revision": 0}
    row = {
        "record_id": "tiny",
        "raw_transcript": "Synthetic unseen: spare key in blue tin.",
        "formatted_text": "Spare key in blue tin.",
    }
    service.import_observations(ctx, options, json.dumps(row))
    service.request_processing(ctx, options)
    assert process_one(service, ctx, namespace="review-path")["decision"] == "extracted"
    answer = service.ask(ctx, {"namespace": "review-path", "question": "Where is the spare key?"})
    assert answer["citations"] and "blue tin" in answer["text"]
    assert len(service.list_memories(ctx, {"namespace": "review-path"})["memories"]) == 1


def test_test_doubles_keep_their_identity():
    assert FixtureResponder().model == "deterministic-answer-double"
    assert FixtureExtractor().model == "deterministic-test-double"


@pytest.mark.parametrize("provider", ["google", "openrouter"])
def test_free_provider_consent_and_no_unfamiliar_inheritance(monkeypatch, provider):
    monkeypatch.setenv("JARVIS_INFERENCE_PROVIDER", provider)
    monkeypatch.setenv("JARVIS_S07_SYNTHETIC_TRIAL_APPROVED", "true")
    assert not NvidiaExtractor.from_env().enabled
    monkeypatch.setenv("JARVIS_FREE_SYNTHETIC_TRIAL_APPROVED", "true")
    monkeypatch.setenv("JARVIS_FREE_DATA_POLICY_ACK", "I_ACCEPT_FREE_SYNTHETIC_DATA_TERMS")
    assert NvidiaExtractor.from_env().enabled and not NvidiaExtractor.from_env().unfamiliar_mode
    monkeypatch.setenv("JARVIS_UNFAMILIAR_INFERENCE_APPROVED", "true")
    monkeypatch.setenv("JARVIS_UNFAMILIAR_DATA_POLICY_ACK", REVIEWER_ACK)
    assert not NvidiaExtractor.from_env().enabled


@pytest.mark.parametrize(
    "provider,model", [("google", "gemini-3.8-flash"), ("openrouter", "google/gemma-4-31b-it:free")]
)
def test_free_transport_exact_route_accounting_and_rate_limit(monkeypatch, provider, model):
    from jarvis.providers import FreeChatProvider

    monkeypatch.setattr("jarvis.answers.answer_messages", lambda *a, **kw: [])
    captured = []

    def transport(request):
        captured.append(request)
        return httpx.Response(
            200,
            json={
                "model": model.removesuffix(":free"),
                "usage": {"prompt_tokens": 12, "completion_tokens": 7},
                "choices": [{"finish_reason": "stop", "message": {"content": "{}"}}],
            },
        )

    proposer = FreeChatProvider(
        provider=provider,
        role="responder",
        approved=True,
        key="test-key",
        transport=httpx.MockTransport(transport),
    )
    body, reservation = proposer.prepare(None)
    answer = proposer.complete(body)
    assert answer.input_tokens == 12 and answer.output_tokens == 7
    assert reservation > body["max_tokens"] and "chat_template_kwargs" not in body
    assert str(captured[0].url) == proposer.endpoint
    if provider == "openrouter":
        assert body["provider"]["max_price"] == {"prompt": 0, "completion": 0, "request": 0}
        assert body["provider"]["allow_fallbacks"] is False
        assert body["provider"]["data_collection"] == "deny"
    proposer._transport = httpx.MockTransport(lambda r: httpx.Response(429))
    with pytest.raises(ApplicationError, match="rate_limited"):
        proposer.complete(body)
    assert proposer.last_http_status == 429
    with pytest.raises(ApplicationError, match="invalid_input"):
        FreeChatProvider(provider=provider, role="extractor", model="paid-or-unknown")
