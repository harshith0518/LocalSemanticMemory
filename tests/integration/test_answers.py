import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import httpx
import pytest
from answer_double import FixtureResponder
from memory_double import FixtureExtractor
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from typer.testing import CliRunner

import jarvis.cli as cli_module
from jarvis.answers import trial_questions
from jarvis.api import create_app
from jarvis.db import make_engine
from jarvis.errors import ApplicationError
from jarvis.models import ModelBudget, ModelCall, Policy, Source
from jarvis.providers import MAX_REQUESTS, FreeChatProvider, NvidiaResponder
from jarvis.services import Service


@pytest.fixture
def answering(engine):
    service = Service(engine, extractor=FixtureExtractor(), responder=FixtureResponder())
    context = service.identity.context("normal")
    service.import_observations(
        context,
        {"namespace": "answers", "expected_policy_revision": 0},
        Path("data/synthetic/sample-dictations.jsonl").read_bytes(),
    )
    return service, context


def request(**extra):
    return {"namespace": "answers", "question": trial_questions()[0], **extra}


@pytest.mark.parametrize("representation", ["history", "sources", "sources_and_memories"])
def test_answer_is_cited_and_never_learned(answering, engine, representation):
    from test_private import snapshot

    service, context = answering
    before = snapshot(engine)
    result = service.ask(context, request(representation=representation))
    assert result["status"] == "answered" and result["citations"]
    after = snapshot(engine)
    for name in before:
        if name not in {"model_calls", "model_budgets"}:
            assert before[name] == after[name]
    with Session(engine) as session:
        call = session.scalar(select(ModelCall))
        assert call.status == "succeeded" and call.job_id is None
        assert call.input_tokens == 100 and call.output_tokens == 50


@pytest.mark.parametrize("fault", ["source", "revision", "variant", "span", "end"])
def test_invalid_citations_never_release(answering, fault):
    service, context = answering

    def bad(data, result):
        passage = result["citations"][0]
        passage[
            {
                "source": "source_id",
                "revision": "source_revision",
                "variant": "variant",
                "span": "exact_text",
                "end": "end",
            }[fault]
        ] = {
            "source": str(uuid4()),
            "revision": 9,
            "variant": "formatted",
            "span": "invented",
            "end": passage["end"] + 1,
        }[fault]
        return result

    service.responder = FixtureResponder(bad)
    published = []
    with pytest.raises(ApplicationError):
        service.ask(context, request(), published.append)
    assert not published
    assert service.responder.calls <= 2


@pytest.mark.parametrize("failure", ["timeout", "malformed", "missing_key"])
def test_provider_failure_is_not_unknown_and_keeps_accounting(answering, engine, failure):
    service, context = answering
    if failure == "missing_key":
        service.responder = NvidiaResponder(approved=True)
    else:

        def broken(body):
            if failure == "timeout":
                raise TimeoutError("must never escape")
            from jarvis.providers import Completion

            return Completion("invalid", service.responder.model, 100, 10, 1)

        service.responder.complete = broken
    with pytest.raises(ApplicationError):
        service.ask(context, request())
    with Session(engine) as session:
        rows = session.scalars(select(ModelCall)).all()
        assert rows and all(row.status == "failed" for row in rows)
        assert session.scalar(select(ModelBudget.tokens)) > 0


def test_trial_question_and_sources_checked_independently(answering):
    service, context = answering
    service.responder = NvidiaResponder(approved=True)
    with pytest.raises(ApplicationError, match="trial_input_denied"):
        service.prepare_answer(context, request(question="My private question"))
    packet = service.prepare_answer(context, request(representation="history"))
    assert len(packet.evidence.sources) == 8
    with service._session(context, write=True) as session:
        session.execute(update(Source).values(raw_text="Private source sentinel"))
    with pytest.raises(ApplicationError, match="trial_input_denied"):
        service.prepare_answer(context, request(representation="history"))


def test_free_question_opt_in_keeps_synthetic_source_gate(answering):
    service, context = answering
    service.responder = FreeChatProvider(
        provider="google",
        role="responder",
        model="gemini-3.5-flash-lite",
        approved=True,
        key="synthetic-test-key",
        unfamiliar_questions=True,
    )
    packet = service.prepare_answer(
        context,
        request(question="Who is Atlas?", representation="history"),
    )
    assert len(packet.evidence.sources) == 8
    with service._session(context, write=True) as session:
        session.execute(update(Source).values(raw_text="Unapproved source sentinel"))
    with pytest.raises(ApplicationError, match="trial_input_denied"):
        service.prepare_answer(
            context,
            request(question="Who is Atlas?", representation="history"),
        )


def test_full_history_overflow_is_explicit(answering, engine):
    service, context = answering
    with engine.begin() as connection:
        connection.execute(update(Source).values(raw_text="large source " * 3000))
    with pytest.raises(ApplicationError, match="context_limit"):
        service.ask(context, request(representation="history"))
    assert service.responder.calls == 0


@pytest.mark.parametrize("change", ["policy", "source"])
def test_change_during_generation_rejects_reply_with_real_connections(answering, settings, change):
    service, context = answering
    entered, changed = Barrier(2, timeout=10), Barrier(2, timeout=10)
    original = service.responder.complete

    def complete(body):
        result = original(body)
        entered.wait()
        changed.wait()
        return result

    service.responder.complete = complete
    independent = make_engine(settings)

    def control():
        entered.wait()
        with independent.begin() as connection:
            connection.execute(select(Policy).with_for_update())
            connection.execute(
                update(Policy).values(revision=1)
                if change == "policy"
                else update(Source).values(raw_text="changed")
            )
        changed.wait()

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(control)
            with pytest.raises(ApplicationError, match="stale_revision"):
                service.ask(context, request())
            future.result()
    finally:
        independent.dispose()


def test_extraction_and_answers_share_the_last_persisted_allowance(answering, engine):
    service, context = answering
    with Session(engine) as session, session.begin():
        session.add(
            ModelBudget(key=service.extractor.budget_key, requests=MAX_REQUESTS - 1, tokens=0)
        )
    service.ask(context, request())
    with pytest.raises(ApplicationError, match="budget_exhausted"):
        service.ask(context, request())
    assert service.responder.calls == 1


def test_api_cli_parity_and_private_unread_body(answering, monkeypatch):
    service, context = answering
    app = create_app(service)

    async def unread():
        raise AssertionError("Private body read")
        yield b""

    async def check():
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app), base_url="http://jarvis.test"
            ) as client,
        ):
            private = await client.post(
                "/ask", headers={"X-Jarvis-Mode": "private"}, content=unread()
            )
            assert private.status_code == 403
            normal = await client.post("/ask", headers={"X-Jarvis-Mode": "normal"}, json=request())
            assert normal.status_code == 200 and normal.headers["Cache-Control"] == "no-store"
            return normal.json()

    result = asyncio.run(check())
    monkeypatch.setattr(cli_module, "run", lambda fn: print(json.dumps(fn(service), default=str)))
    output = CliRunner().invoke(
        cli_module.app, ["ask", "--mode", "normal"], input=json.dumps(request())
    )
    assert output.exit_code == 0, output.output
    cli = json.loads(output.output)
    assert cli["citations"] == result["citations"] and cli["text"] == result["text"]


def test_responder_transport_uses_configured_model_and_drops_reasoning(answering):
    service, context = answering
    packet = service.prepare_answer(context, request())

    def transport(request):
        assert request.extensions["timeout"]["read"] == 180
        assert request.extensions["timeout"]["connect"] == 10
        body = json.loads(request.content)
        assert body["model"] == "moonshotai/kimi-k3" and body["reasoning_effort"] == "low"
        assert body["stream"] is False and "answers" not in body["messages"][1]["content"]
        return httpx.Response(
            200,
            json={
                "model": body["model"],
                "usage": {"prompt_tokens": 200, "completion_tokens": 100},
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": '{"status":"unknown","text":"Not recorded","citations":[]}',
                            "reasoning_content": "not persisted",
                        },
                    }
                ],
            },
        )

    responder = NvidiaResponder(
        approved=True, key="synthetic", transport=httpx.MockTransport(transport)
    )
    body, reservation = responder.prepare(packet)
    completion = responder.complete(body)
    assert "not persisted" not in completion.content and reservation > 8192


def test_feedback_requires_diagnosis_and_persists_only_one_rerun(answering, engine):
    from test_private import snapshot

    from jarvis.models import FeedbackReceipt

    service, context = answering
    result = service.ask(context, request())
    payload = {"call_id": result["call_ids"][-1], "request": request(), "diagnosis": "unclear"}
    before = snapshot(engine)
    assert service.feedback(context, payload)["status"] == "needs_detail"
    assert snapshot(engine) == before
    retry = service.feedback(context, {**payload, "diagnosis": "retrieval"})
    assert retry["answer"]["representation"] == "history" and retry["status"] == "retried"
    with pytest.raises(ApplicationError, match="retry_limit"):
        service.feedback(context, {**payload, "diagnosis": "generation"})
    with pytest.raises(ApplicationError, match="retry_limit"):
        service.feedback(
            context,
            {
                "call_id": retry["answer"]["call_ids"][-1],
                "request": retry["request"],
                "diagnosis": "generation",
            },
        )
    with Session(engine) as session:
        assert session.scalar(select(FeedbackReceipt.status)) == "succeeded"
    assert service.responder.calls == 2


def test_feedback_cannot_change_its_question_or_target_someone_elses_operation(answering):
    service, context = answering
    result = service.ask(context, request())
    for payload in [
        {"call_id": str(uuid4()), "request": request(), "diagnosis": "generation"},
        {
            "call_id": result["call_ids"][-1],
            "request": request(question="Another question"),
            "diagnosis": "generation",
        },
    ]:
        with pytest.raises(ApplicationError, match="reference_unavailable"):
            service.feedback(context, payload)
    assert service.responder.calls == 1


def test_failed_feedback_is_not_retried_after_recreating_service(answering, engine):
    service, context = answering
    result = service.ask(context, request())
    payload = {"call_id": result["call_ids"][-1], "request": request(), "diagnosis": "generation"}
    service.responder.complete = lambda body: (_ for _ in ()).throw(TimeoutError())
    with pytest.raises(ApplicationError, match="provider_failed"):
        service.feedback(context, payload)
    replacement = Service(engine, responder=FixtureResponder())
    with pytest.raises(ApplicationError, match="retry_limit"):
        replacement.feedback(context, payload)
    assert replacement.responder.calls == 0
