"""Normal-only accounting and bounded, transient service timings; no telemetry sink."""

from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from time import perf_counter

from sqlalchemy import Text, case, cast, func, select

from jarvis.models import ClaimRecord, Job, ModelCall, Passage, Policy, Source

_current = ContextVar("jarvis_timings", default=None)


@contextmanager
def capture_timings(*, enabled=True):
    """Explicit callers retain only fixed stage names/counts/durations, never inputs."""
    stages = {} if enabled else None
    token = _current.set(stages)
    try:
        yield stages
    finally:
        _current.reset(token)


@contextmanager
def stage(name):
    stages = _current.get()
    if stages is None:
        yield
        return
    started = perf_counter()
    try:
        yield
    finally:
        value = stages.setdefault(name, {"calls": 0, "elapsed_ms": 0.0})
        value["calls"] += 1
        value["elapsed_ms"] += (perf_counter() - started) * 1000


def measured(name):
    """Service entry points authorize before collecting even transient measurements."""

    def decorate(method):
        @wraps(method)
        def run(self, context, *args, **kwargs):
            self._authorize(context)
            with stage(name):
                return method(self, context, *args, **kwargs)

        return run

    return decorate


class MetricsOperations:
    @measured("usage_snapshot")
    def usage_snapshot(self, context, render=None):
        """Owner totals across collections, including retained history; read-only."""
        with self._session(context) as session:
            policy = session.scalar(
                select(Policy).where(Policy.owner_id == context.owner_id).with_for_update()
            )

            def total(model, expression):
                return session.execute(
                    select(func.count(), func.coalesce(func.sum(expression), 0))
                    .select_from(model)
                    .where(model.owner_id == context.owner_id)
                ).one()

            source_count, source_bytes = total(
                Source,
                func.octet_length(Source.raw_text)
                + func.octet_length(func.coalesce(Source.formatted_text, "")),
            )
            claim_count, claim_bytes = total(
                ClaimRecord, func.octet_length(cast(ClaimRecord.content, Text))
            )
            passage_count, passage_bytes = total(Passage, func.octet_length(Passage.exact_text))
            jobs = dict(
                session.execute(
                    select(Job.status, func.count())
                    .where(Job.owner_id == context.owner_id)
                    .group_by(Job.status)
                ).all()
            )
            lifecycle = dict(
                session.execute(
                    select(ClaimRecord.lifecycle, func.count())
                    .where(ClaimRecord.owner_id == context.owner_id)
                    .group_by(ClaimRecord.lifecycle)
                ).all()
            )
            known = ModelCall.input_tokens.is_not(None) & ModelCall.output_tokens.is_not(None)
            role = case(
                (ModelCall.prompt_version == "turn-assessment-v1", "assessment"),
                (ModelCall.job_id.is_(None), "answer"),
                else_="extraction",
            )
            calls = (
                session.execute(
                    select(
                        ModelCall.configured_model.label("model"),
                        ModelCall.budget_key.label("allowance"),
                        role.label("role"),
                        func.count().label("attempts"),
                        func.count().filter(ModelCall.status == "succeeded").label("succeeded"),
                        func.count().filter(ModelCall.status == "failed").label("failed"),
                        func.count().filter(ModelCall.status == "reserved").label("in_flight"),
                        func.count().filter(known).label("known_usage_calls"),
                        func.count().filter(~known).label("unknown_usage_calls"),
                        func.coalesce(func.sum(ModelCall.input_tokens).filter(known), 0).label(
                            "known_input_tokens"
                        ),
                        func.coalesce(func.sum(ModelCall.output_tokens).filter(known), 0).label(
                            "known_output_tokens"
                        ),
                        func.coalesce(func.sum(ModelCall.reserved_tokens).filter(~known), 0).label(
                            "unsettled_reserved_tokens"
                        ),
                        func.count(ModelCall.elapsed_ms).label("timed_calls"),
                        func.percentile_cont(0.5)
                        .within_group(ModelCall.elapsed_ms)
                        .label("latency_p50_ms"),
                        func.percentile_cont(0.95)
                        .within_group(ModelCall.elapsed_ms)
                        .label("latency_p95_ms"),
                    )
                    .where(ModelCall.owner_id == context.owner_id)
                    .group_by(ModelCall.configured_model, ModelCall.budget_key, role)
                    .order_by(ModelCall.configured_model, ModelCall.budget_key, role)
                )
                .mappings()
                .all()
            )
            result = {
                "scope": "current_owner_all_collections_including_retained_history",
                "policy_revision": policy.revision if policy else 0,
                "storage": {
                    "source_revisions": source_count,
                    "source_text_utf8_bytes": source_bytes,
                    "claim_revisions": claim_count,
                    "claim_json_utf8_bytes": claim_bytes,
                    "supporting_passages": passage_count,
                    "passage_text_utf8_bytes": passage_bytes,
                    "claim_lifecycle": lifecycle,
                },
                "jobs": jobs,
                "models": [dict(row) for row in calls],
                "cost": {
                    "billed_usd": None,
                    "estimated_usd": None,
                    "reason": "provider_billing_and_rates_not_connected",
                },
                "semantic_quality": {"measured": False, "reason": "requires_labeled_evaluation"},
            }
            # Serialize while holding the same owner policy guard as lifecycle operations.
            return render(result) if render else result
