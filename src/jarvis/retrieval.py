"""PostgreSQL retrieval with whole evidence, transient queries and guarded release."""

import json
from collections import defaultdict
from collections.abc import Callable
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, model_validator
from sqlalchemy import func, literal_column, or_, select
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import aliased

from jarvis.contracts import (
    ClaimRevision,
    ClaimWrite,
    Contract,
    SourceObservation,
    Timestamp,
    exact_text,
    parse_contract,
)
from jarvis.controls import blocked_sources
from jarvis.errors import ApplicationError, ErrorCode
from jarvis.imports import Identifier
from jarvis.metrics import measured
from jarvis.models import (
    CLAIM_SEARCH_SQL,
    SOURCE_SEARCH_SQL,
    ClaimEvidence,
    ClaimRecord,
    Passage,
    Policy,
    Source,
)

SEARCH_VERSION = "s08-lexical-v2"
CANDIDATES = 100


class SearchRequest(Contract):
    namespace: Identifier
    query: Annotated[str, Field(strict=True, min_length=1, max_length=512)]
    representation: Literal["sources", "sources_and_memories"] = "sources"
    history: Annotated[bool, Field(strict=True)] = False
    limit: Annotated[int, Field(strict=True, ge=1, le=20)] = 5
    max_bytes: Annotated[int, Field(strict=True, ge=1024, le=64000)] = 24000
    captured_from: Timestamp | None = None
    captured_to: Timestamp | None = None
    include_undated: Annotated[bool, Field(strict=True)] = True

    @model_validator(mode="after")
    def valid_query(self) -> Self:
        exact_text(self.query)
        if self.captured_from and self.captured_to and self.captured_from > self.captured_to:
            raise ValueError("Capture interval is reversed")
        return self


class SearchMatch(Contract):
    source_id: UUID
    rank: int
    via: tuple[Literal["source", "memory"], ...]


class ControlAnnotation(Contract):
    action: Literal["correct", "world_change"]
    source_id: UUID
    prior_source_ids: tuple[UUID, ...]


class SearchPacket(Contract):
    request: SearchRequest
    policy_revision: int | None
    status: Literal["matched", "no_matches", "evidence_budget_exceeded"]
    sources: tuple[SourceObservation, ...] = ()
    memories: tuple[ClaimRevision, ...] = ()
    controls: tuple[ControlAnnotation, ...] = ()
    matches: tuple[SearchMatch, ...] = ()
    evidence_bytes: int = 0
    has_more: bool = False
    budget_limited: bool = False
    search_version: str = SEARCH_VERSION


def evidence_size(sources, memories):
    """Exact serialized UTF-8 evidence bytes, not a claimed model-token measurement."""
    return len(
        json.dumps(
            {
                "sources": [s.model_dump(mode="json") for s in sources],
                "memories": [m.model_dump(mode="json") for m in memories],
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    )


def fuse_rankings(*rankings):
    """RRF over identity-deduplicated lists; scores are not confidence probabilities."""
    scores = defaultdict(float)
    for ranking in rankings:
        for rank, identity in enumerate(dict.fromkeys(ranking), 1):
            scores[identity] += 1 / (60 + rank)
    return scores


class RetrievalOperations:
    def _search_sources(self, context, query):
        newer = aliased(Source)
        statement = select(Source.id).where(
            Source.owner_id == context.owner_id,
            Source.source_key.startswith(f"import:{query.namespace}:", autoescape=True),
            Source.kind.in_(["user_message", "imported_dictation"]),
            ~Source.id.in_(blocked_sources(context)),
            ~select(newer.id)
            .where(
                newer.owner_id == context.owner_id,
                newer.source_key == Source.source_key,
                newer.revision > Source.revision,
            )
            .exists(),
        )
        times = []
        if query.captured_from:
            times.append(Source.captured_at >= query.captured_from)
        if query.captured_to:
            times.append(Source.captured_at <= query.captured_to)
        if times:
            condition = times[0]
            for item in times[1:]:
                condition &= item
            statement = statement.where(
                or_(condition, Source.captured_at.is_(None)) if query.include_undated else condition
            )
        return statement

    def _search_claims(self, context, query, eligible):
        newer = aliased(ClaimRecord)
        supports = select(ClaimEvidence.claim_revision_id).where(
            ClaimEvidence.owner_id == context.owner_id,
        )
        unavailable = (
            select(ClaimEvidence.claim_revision_id)
            .join(Passage, Passage.id == ClaimEvidence.passage_id)
            .where(ClaimEvidence.owner_id == context.owner_id, ~Passage.source_id.in_(eligible))
        )
        statement = select(ClaimRecord).where(
            ClaimRecord.owner_id == context.owner_id,
            ClaimRecord.id.in_(supports),
            ~ClaimRecord.id.in_(unavailable),
            ClaimRecord.lifecycle.in_(["active", "superseded"] if query.history else ["active"]),
        )
        if not query.history:
            statement = statement.where(
                ~select(newer.id)
                .where(
                    newer.owner_id == context.owner_id,
                    newer.claim_id == ClaimRecord.claim_id,
                    newer.revision > ClaimRecord.revision,
                )
                .exists()
            )
        return statement

    @staticmethod
    def _search_query(session, query):
        # Plain language uses OR recall, never treats a user's negation as a search command.
        # English stemming handles inflections; the simple fallback keeps stopword-only names.
        terms = session.scalar(
            select(
                func.tsvector_to_array(
                    func.to_tsvector(literal_column("'english'::regconfig"), query)
                )
            )
        )
        if not terms:
            terms = session.scalar(
                select(
                    func.tsvector_to_array(
                        func.to_tsvector(literal_column("'simple'::regconfig"), query)
                    )
                )
            )
        escaped = ["'" + term.replace("\\", "\\\\").replace("'", "''") + "'" for term in terms]
        return func.to_tsquery(literal_column("'simple'::regconfig"), " | ".join(escaped))

    def _select_search(self, session, context, query):
        policy = session.scalar(
            select(Policy).where(Policy.owner_id == context.owner_id).with_for_update()
        )
        # No durable query, trace, model call, job, browser state or search cache.
        eligible = self._search_sources(context, query)
        tsquery = self._search_query(session, query.query)
        vector = literal_column(f"({SOURCE_SEARCH_SQL})", type_=TSVECTOR())

        def variant_score(column):
            value = func.coalesce(column, "")
            parsed = func.to_tsvector(literal_column("'english'::regconfig"), value).op("||")(
                func.to_tsvector(literal_column("'simple'::regconfig"), value)
            )
            return func.ts_rank_cd(parsed, tsquery, 32)

        # Maximum variant rank avoids counting a raw/formatted pair as two observations.
        rank = func.greatest(variant_score(Source.raw_text), variant_score(Source.formatted_text))
        lexical = session.scalars(
            select(Source.id)
            .where(Source.id.in_(eligible), vector.op("@@")(tsquery))
            .order_by(rank.desc(), Source.source_key, Source.id)
            .limit(CANDIDATES)
        ).all()
        memories = []
        if query.representation == "sources_and_memories":
            claim_vector = literal_column(f"({CLAIM_SEARCH_SQL})", type_=TSVECTOR())
            rows = session.scalars(
                self._search_claims(context, query, eligible)
                .where(claim_vector.op("@@")(tsquery))
                .order_by(
                    func.ts_rank_cd(claim_vector, tsquery, 32).desc(),
                    ClaimRecord.claim_id,
                    ClaimRecord.revision,
                )
                .limit(CANDIDATES)
            ).all()
            for row in rows:
                claim = self._claim_contract(session, context, row)
                self._support(
                    session,
                    context,
                    ClaimWrite(
                        expected_policy_revision=policy.revision,
                        content=claim.content,
                        passages=claim.passages,
                    ),
                )
                memories.append(claim)

        memory_ranking = list(dict.fromkeys(p.source_id for m in memories for p in m.passages))
        scores = fuse_rankings(lexical, memory_ranking)
        if not scores:
            return SearchPacket(
                request=query,
                policy_revision=policy.revision if policy else None,
                status="no_matches",
            )
        source_rows = session.scalars(
            select(Source).where(Source.id.in_(scores), Source.owner_id == context.owner_id)
        ).all()
        sources = {s.id: self._source_contract(s) for s in source_rows}
        ordered = sorted(scores, key=lambda i: (-scores[i], sources[i].source_key, str(i)))
        if lexical:
            # Preserve the strongest original source: matching both branches must not
            # erase unextracted context (e.g. a note distinguishing two same-name people).
            ordered.remove(lexical[0])
            ordered.insert(0, lexical[0])
        selected_sources, selected_memories, matches = {}, {}, []
        budget_limited = False
        for source_id in ordered:
            if len(matches) == query.limit:
                break
            additions = [m for m in memories if any(p.source_id == source_id for p in m.passages)]
            next_memories = {**selected_memories, **{m.id: m for m in additions}}
            support_ids = {source_id} | {p.source_id for m in additions for p in m.passages}
            next_sources = {**selected_sources, **{i: sources[i] for i in sorted(support_ids)}}
            if evidence_size(next_sources.values(), next_memories.values()) > query.max_bytes:
                budget_limited = True
                break  # A truncated record could drop its negation, condition or paired conflict.
            selected_sources, selected_memories = next_sources, next_memories
            matches.append(
                SearchMatch(
                    source_id=source_id,
                    rank=len(matches) + 1,
                    via=tuple(
                        name
                        for name, ranking in (("source", lexical), ("memory", memory_ranking))
                        if source_id in ranking
                    ),
                )
            )
        return self._attach_controls(
            session,
            context,
            SearchPacket(
                request=query,
                policy_revision=policy.revision if policy else None,
                status="matched" if matches else "evidence_budget_exceeded",
                sources=tuple(selected_sources.values()),
                memories=tuple(selected_memories.values()),
                matches=tuple(matches),
                evidence_bytes=evidence_size(selected_sources.values(), selected_memories.values()),
                budget_limited=budget_limited,
                has_more=len(matches) < len(ordered)
                or len(lexical) == CANDIDATES
                or len(memories) == CANDIDATES,
            ),
        )

    @measured("retrieval")
    def prepare_search(self, context, payload):
        self._authorize(context)
        query = parse_contract(SearchRequest, payload)
        with self._session(context) as session:
            return self._select_search(session, context, query)

    @measured("release_search")
    def release_search(self, context, packet, render: Callable | None = None):
        self._authorize(context)
        packet = parse_contract(SearchPacket, packet)
        with self._session(context) as session:
            current = self._select_search(session, context, packet.request)
            if current != packet:
                raise ApplicationError(ErrorCode.STALE_REVISION)
            result = packet.model_dump(mode="json", exclude={"request"})
            # This guarded callback is the logical release boundary. Later changes cannot
            # recall a released result; future responders must call this after generation.
            return render(result) if render else result

    @measured("search")
    def search(self, context, payload, render: Callable | None = None):
        self._authorize(context)
        query = parse_contract(SearchRequest, payload)
        with self._session(context) as session:
            # Immediate search has no model/network gap: select and release under one guard.
            # Staged consumers use prepare_search/release_search across their external work.
            packet = self._select_search(session, context, query)
            result = packet.model_dump(mode="json", exclude={"request"})
            return render(result) if render else result
