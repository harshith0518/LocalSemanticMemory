"""PostgreSQL retrieval with whole evidence, transient queries and guarded release."""

import json
from collections import Counter, defaultdict
from collections.abc import Callable
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, model_validator
from sqlalchemy import func, literal_column, or_, select
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import aliased

from jarvis.answer_policy import is_inventory_question
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
    Job,
    Passage,
    Policy,
    ProcessingReceipt,
    Source,
)

SEARCH_VERSION = "s15-memory-first-v1"
CANDIDATES = 100
MAX_RANKED_SOURCES = 10000

# Automatic answers have a much narrower purpose than an explicit Search or History
# view.  They need enough complete evidence to answer one question, not a dump of a
# small workspace.  These are candidate/read caps; `max_bytes` remains the final
# immutable-record budget.
AUTO_MATCH_LIMIT = 12
AUTO_MEMORY_CANDIDATES = 24
AUTO_SOURCE_CANDIDATES = 48
AUTO_MEMORY_FALLBACK_SCAN = 96


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
    memory_eligible_only: Annotated[bool, Field(strict=True)] = False

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
    strategy: str = "lexical"
    eligible_sources: int | None = None
    eligible_memories: int | None = None


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
    def _select_auto(self, session, context, query):
        """Select bounded, memory-first evidence for an automatic answer.

        A normal question should not turn a small source collection into a prompt.
        Current learned claims are the primary recall index; complete originals are
        attached only for each selected claim's provenance, qualifiers and conflicts.
        An explicit inventory remains the deliberate exception.
        """
        policy = session.scalar(
            select(Policy).where(Policy.owner_id == context.owner_id).with_for_update()
        )
        eligible = self._search_sources(context, query)
        source_count = int(
            session.scalar(select(func.count()).select_from(eligible.subquery())) or 0
        )
        current_query = query.model_copy(update={"history": False})
        claims = self._search_claims(context, current_query, eligible)
        memory_count = int(session.scalar(select(func.count()).select_from(claims.subquery())) or 0)
        if is_inventory_question(query.query):
            return self._select_auto_inventory(
                session,
                context,
                query,
                policy,
                eligible,
                claims,
                source_count,
                memory_count,
            )

        # First retrieve normalized memories.  A fact's supporting originals travel
        # as one group, so a condition, revision or conflicting source is never
        # separated from the memory it validates.
        tsquery = self._search_query(session, query.query)
        memory_rows = session.scalars(
            claims.where(
                literal_column(f"({CLAIM_SEARCH_SQL})", type_=TSVECTOR()).op("@@")(tsquery)
            )
            .order_by(
                func.ts_rank_cd(
                    literal_column(f"({CLAIM_SEARCH_SQL})", type_=TSVECTOR()), tsquery, 32
                ).desc(),
                ClaimRecord.claim_id,
                ClaimRecord.revision,
            )
            .limit(AUTO_MEMORY_CANDIDATES)
        ).all()
        memory_candidates = [
            self._auto_claim_contract(session, context, policy, row) for row in memory_rows
        ]
        source_candidates = self._auto_lexical_source_ids(session, eligible, query, tsquery)

        selected_sources = {}
        selected_memories = {}
        matches = []
        budget_limited = False
        match_limit = min(query.limit, AUTO_MATCH_LIMIT)

        for memory in memory_candidates:
            if len(matches) >= match_limit:
                break
            if not self._auto_add_memory(
                session,
                context,
                eligible,
                query,
                selected_sources,
                selected_memories,
                matches,
                memory,
            ):
                budget_limited = True
                break

        # A lexical original can still contain a useful, unextracted detail.  It is
        # deliberately secondary to memory matches and is never used to bulk-fill a
        # small collection.
        if not budget_limited:
            for source_id in source_candidates:
                if len(matches) >= match_limit:
                    break
                if source_id in selected_sources:
                    continue
                if not self._auto_add_source(
                    session,
                    context,
                    eligible,
                    query,
                    selected_sources,
                    selected_memories,
                    matches,
                    source_id,
                ):
                    budget_limited = True
                    break

        used_diversity_fallback = False
        if not selected_sources and not selected_memories and not budget_limited and memory_count:
            # A paraphrase may have no shared lexeme with a normalized memory. This
            # is a bounded, diversity-first recall fallback, not a vector-similarity
            # result: it supplies compact learned claims and their provenance, never
            # every original note. If it cannot cover all memories, the caller gets
            # an explicit partial flag and may request one rewrite.
            fallback_rows = self._auto_diverse_fallback_rows(session, claims)
            used_diversity_fallback = bool(fallback_rows)
            for row in fallback_rows:
                if len(matches) >= match_limit:
                    break
                memory = self._auto_claim_contract(session, context, policy, row)
                if not self._auto_add_memory(
                    session,
                    context,
                    eligible,
                    query,
                    selected_sources,
                    selected_memories,
                    matches,
                    memory,
                ):
                    budget_limited = True
                    break

        has_more = len(selected_sources) < source_count or len(selected_memories) < memory_count
        if budget_limited:
            status = "evidence_budget_exceeded"
        elif selected_sources or selected_memories:
            status = "matched"
        else:
            status = "no_matches"
        # `ranked_sources_and_memories` is also the existing signal for one bounded
        # query-rewrite attempt.  Use it only when no direct hit was found or the
        # diversity fallback could not cover the semantic memory set; do not spend
        # an extra model call merely because unrelated sources exist.
        if used_diversity_fallback:
            strategy = (
                "memory_diversity_fallback"
                if len(selected_memories) == memory_count
                else "ranked_sources_and_memories"
            )
        elif memory_candidates or source_candidates:
            strategy = "memory_first_ranked"
        else:
            strategy = "ranked_sources_and_memories"
        return self._attach_controls(
            session,
            context,
            SearchPacket(
                request=query,
                policy_revision=policy.revision if policy else None,
                status=status,
                sources=tuple(selected_sources.values()),
                memories=tuple(selected_memories.values()),
                matches=tuple(matches),
                evidence_bytes=evidence_size(selected_sources.values(), selected_memories.values()),
                has_more=has_more,
                budget_limited=budget_limited,
                strategy=strategy,
                eligible_sources=source_count,
                eligible_memories=memory_count,
            ),
        )

    def _select_auto_inventory(
        self, session, context, query, policy, eligible, claims, source_count, memory_count
    ):
        """An inventory is the explicit, bounded exception to normal auto retrieval."""
        rows = session.scalars(
            select(Source)
            .where(Source.id.in_(eligible))
            .order_by(Source.source_key, Source.id)
            .limit(50)
        ).all()
        sources = []
        for row in rows:
            source = self._source_contract(row)
            if evidence_size((*sources, source), ()) > query.max_bytes:
                break
            sources.append(source)
        selected_ids = {source.id for source in sources}
        memories = []
        for row in session.scalars(
            claims.order_by(ClaimRecord.claim_id, ClaimRecord.revision).limit(80)
        ):
            claim = self._auto_claim_contract(session, context, policy, row)
            if any(passage.source_id not in selected_ids for passage in claim.passages):
                continue
            if evidence_size(sources, (*memories, claim)) > query.max_bytes:
                break
            memories.append(claim)
        complete = len(sources) == source_count and len(memories) == memory_count
        return self._attach_controls(
            session,
            context,
            SearchPacket(
                request=query,
                policy_revision=policy.revision if policy else None,
                status="matched" if sources else "no_matches",
                sources=tuple(sources),
                memories=tuple(memories),
                evidence_bytes=evidence_size(sources, memories),
                has_more=not complete,
                strategy="complete_collection" if complete else "collection_overview",
                eligible_sources=source_count,
                eligible_memories=memory_count,
            ),
        )

    def _auto_claim_contract(self, session, context, policy, row):
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
        return claim

    @staticmethod
    def _auto_diverse_fallback_rows(session, claims):
        """Round-robin structured facets instead of taking the latest N claims."""
        rows = session.scalars(
            claims.order_by(
                ClaimRecord.recorded_at.desc(), ClaimRecord.claim_id, ClaimRecord.revision
            ).limit(AUTO_MEMORY_FALLBACK_SCAN)
        ).all()
        buckets = defaultdict(list)
        for row in rows:
            content = row.content
            scope = content.get("scope", {}) if isinstance(content, dict) else {}
            subject = content.get("subject", {}) if isinstance(content, dict) else {}
            buckets[
                (
                    str(scope.get("kind", "")),
                    str(scope.get("key", "")),
                    str(subject.get("label", "")),
                    str(content.get("predicate", "")) if isinstance(content, dict) else "",
                )
            ].append(row)
        result = []
        while buckets and len(result) < AUTO_MATCH_LIMIT:
            for key in sorted(tuple(buckets)):
                result.append(buckets[key].pop(0))
                if not buckets[key]:
                    del buckets[key]
                if len(result) == AUTO_MATCH_LIMIT:
                    break
        return result

    def _auto_lexical_source_ids(self, session, eligible, query, tsquery):
        vector = literal_column(f"({SOURCE_SEARCH_SQL})", type_=TSVECTOR())

        def variant_score(column):
            value = func.coalesce(column, "")
            parsed = func.to_tsvector(literal_column("'english'::regconfig"), value).op("||")(
                func.to_tsvector(literal_column("'simple'::regconfig"), value)
            )
            return func.ts_rank_cd(parsed, tsquery, 32)

        rank = func.greatest(variant_score(Source.raw_text), variant_score(Source.formatted_text))
        rows = session.execute(
            select(
                Source.id,
                Source.source_key,
                func.tsvector_to_array(vector).label("lexemes"),
                rank.label("score"),
            )
            .where(Source.id.in_(eligible), vector.op("@@")(tsquery))
            .limit(MAX_RANKED_SOURCES + 1)
        ).all()
        if len(rows) > MAX_RANKED_SOURCES:
            raise ApplicationError(ErrorCode.CONTEXT_LIMIT)
        terms = set(self._search_terms(session, query.query))
        matching = {row.id: terms.intersection(row.lexemes) for row in rows}
        frequency = Counter(term for terms in matching.values() for term in terms)
        specificity = {
            source_id: sum(1 / frequency[term] for term in terms)
            for source_id, terms in matching.items()
        }
        return [
            row.id
            for row in sorted(
                rows,
                key=lambda row: (-specificity[row.id], -row.score, row.source_key, str(row.id)),
            )[:AUTO_SOURCE_CANDIDATES]
        ]

    def _auto_add_memory(
        self,
        session,
        context,
        eligible,
        query,
        selected_sources,
        selected_memories,
        matches,
        memory,
    ):
        support_ids = {passage.source_id for passage in memory.passages}
        rows = session.scalars(
            select(Source)
            .where(
                Source.owner_id == context.owner_id,
                Source.id.in_(support_ids),
                Source.id.in_(eligible),
            )
            .order_by(Source.source_key, Source.id)
        ).all()
        if {row.id for row in rows} != support_ids:
            raise ApplicationError(ErrorCode.REFERENCE_UNAVAILABLE)
        next_sources = {**selected_sources, **{row.id: self._source_contract(row) for row in rows}}
        next_memories = {**selected_memories, memory.id: memory}
        if evidence_size(next_sources.values(), next_memories.values()) > query.max_bytes:
            return False
        selected_sources.update(next_sources)
        selected_memories.update(next_memories)
        matches.append(
            SearchMatch(
                source_id=memory.passages[0].source_id,
                rank=len(matches) + 1,
                via=("memory",),
            )
        )
        return True

    def _auto_add_source(
        self,
        session,
        context,
        eligible,
        query,
        selected_sources,
        selected_memories,
        matches,
        source_id,
    ):
        row = session.scalar(
            select(Source).where(
                Source.owner_id == context.owner_id,
                Source.id == source_id,
                Source.id.in_(eligible),
            )
        )
        if row is None:
            raise ApplicationError(ErrorCode.REFERENCE_UNAVAILABLE)
        source = self._source_contract(row)
        next_sources = {**selected_sources, source.id: source}
        if evidence_size(next_sources.values(), selected_memories.values()) > query.max_bytes:
            return False
        selected_sources.update(next_sources)
        matches.append(SearchMatch(source_id=source.id, rank=len(matches) + 1, via=("source",)))
        return True

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
        if query.memory_eligible_only:
            no_memory = (
                select(Job.id)
                .join(ProcessingReceipt, ProcessingReceipt.job_id == Job.id)
                .where(
                    Job.source_id == Source.id,
                    Job.owner_id == context.owner_id,
                    ProcessingReceipt.result["decision"].astext == "no_memory",
                )
                .exists()
            )
            supports_claim = (
                select(Passage.id)
                .join(ClaimEvidence, ClaimEvidence.passage_id == Passage.id)
                .where(Passage.source_id == Source.id, Passage.owner_id == context.owner_id)
                .exists()
            )
            # Keep pending/failed extraction and any antecedent used by a claim.
            # A completed question-only chat receipt is history, not answer evidence.
            statement = statement.where(
                or_(Source.kind != "user_message", ~no_memory, supports_claim)
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
    def _search_terms(session, query):
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
        return terms

    @staticmethod
    def _search_query(session, query):
        terms = RetrievalOperations._search_terms(session, query)
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
        lexical_rows = session.execute(
            select(
                Source.id,
                Source.source_key,
                func.tsvector_to_array(vector).label("lexemes"),
                rank.label("score"),
            )
            .where(Source.id.in_(eligible), vector.op("@@")(tsquery))
            .limit(MAX_RANKED_SOURCES + 1)
        ).all()
        if len(lexical_rows) > MAX_RANKED_SOURCES:
            raise ApplicationError(ErrorCode.CONTEXT_LIMIT)
        # Collection-local document frequency prioritizes specific query terms over
        # common words such as "planned". No names, fixture IDs or evaluation labels
        # are hard-coded, and paired variants count as one observation for ranking.
        terms = set(self._search_terms(session, query.query))
        matching = {row.id: terms.intersection(row.lexemes) for row in lexical_rows}
        frequency = Counter(term for matches in matching.values() for term in matches)
        specificity = {
            source_id: sum(1 / frequency[term] for term in matches)
            for source_id, matches in matching.items()
        }
        lexical = [
            row.id
            for row in sorted(
                lexical_rows,
                key=lambda row: (-specificity[row.id], -row.score, row.source_key, str(row.id)),
            )[:CANDIDATES]
        ]
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
        ordered = sorted(
            scores,
            key=lambda i: (-specificity.get(i, 0), -scores[i], sources[i].source_key, str(i)),
        )
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
