"""Bounded dictation interchange; no file access, inference or text normalization."""

import json
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, JsonValue

from jarvis.contracts import (
    Contract,
    Label,
    ObservationInput,
    PositiveRevision,
    Revision,
    SourceObservation,
    Text,
    Timestamp,
    parse_contract,
)
from jarvis.errors import ApplicationError, ErrorCode

MAX_IMPORT_BYTES = 1024 * 1024
MAX_IMPORT_RECORDS = 1000
IMPORT_PREFIX = "import:"
Identifier = Annotated[
    str, Field(strict=True, min_length=1, max_length=96, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
]


class ImportOptions(Contract):
    namespace: Identifier
    expected_policy_revision: Revision


class DictationRecord(Contract):
    record_id: Identifier
    raw_transcript: Text
    formatted_text: Text | None = None
    metadata: dict[str, JsonValue] | None = None


class SourceQuery(Contract):
    namespace: Identifier
    after: Identifier | None = None
    limit: Annotated[int, Field(strict=True, ge=1, le=100)] = 50


class SourceSummary(Contract):
    id: UUID
    source_key: Label
    revision: PositiveRevision
    captured_at: Timestamp | None
    imported_at: Timestamp


class SourcePage(Contract):
    namespace: Identifier
    policy_revision: Revision
    observations: tuple[SourceSummary, ...]
    next_after: Identifier | None


class JobState(Contract):
    id: UUID
    status: Literal["pending", "running", "succeeded", "failed", "cancelled"]
    attempts: Revision
    expected_policy_revision: Revision
    expected_source_revision: PositiveRevision


class SourceInspection(Contract):
    observation: SourceObservation
    latest_revision: PositiveRevision
    job: JobState | None


class SourceLookup(Contract):
    source_id: UUID


class ImportItem(Contract):
    record_id: Identifier
    source_id: UUID
    revision: PositiveRevision
    job: JobState
    outcome: Literal["created", "unchanged"]


class ImportReceipt(Contract):
    status: Literal["imported"] = "imported"
    namespace: Identifier
    policy_revision: Revision
    created: Revision
    unchanged: Revision
    observations: tuple[ImportItem, ...]


def source_key(namespace: str, record_id: str) -> str:
    # Components exclude ':', so this is reversible and collision-free (<= 200 characters).
    return f"{IMPORT_PREFIX}{namespace}:{record_id}"


def canonical_json(value: object) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(",", ":")
    )


def unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def same_json(left: object, right: object) -> bool:
    """JSONB may spell a number differently; booleans are never equivalent to numbers."""
    if type(left) in {int, float} and type(right) in {int, float}:
        return Decimal(str(left)) == Decimal(str(right))
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(same_json(left[key], right[key]) for key in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(
            same_json(a, b) for a, b in zip(left, right, strict=True)
        )
    return left == right


def reject_constant(value: str) -> None:
    raise ValueError("Non-finite JSON number")


def validate_json_text(value: object) -> None:
    if isinstance(value, str):
        value.encode("utf-8")
        if "\0" in value:
            raise ValueError("NUL is not supported by PostgreSQL text")
    elif isinstance(value, dict):
        for key, item in value.items():
            validate_json_text(key)
            validate_json_text(item)
    elif isinstance(value, list):
        for item in value:
            validate_json_text(item)


def parse_dictations(namespace: str, payload: str | bytes) -> list[ObservationInput]:
    """Parse the whole batch before any transaction. Errors never contain source content."""
    try:
        if isinstance(payload, str):
            payload = payload.encode("utf-8")
        if not isinstance(payload, bytes) or len(payload) > MAX_IMPORT_BYTES:
            raise ValueError("Invalid import size/type")
        # UTF-8 BOM is a file encoding marker, not source text; permit Windows JSONL exports.
        lines = payload.decode("utf-8-sig").split("\n")
        result = []
        seen = set()
        for line in lines:
            if not line.strip():
                continue
            if len(result) >= MAX_IMPORT_RECORDS:
                raise ValueError("Too many observations")
            record = json.loads(
                line, object_pairs_hook=unique_object, parse_constant=reject_constant
            )
            # JSONB rejects NUL/unpaired surrogates; reject before reaching PostgreSQL/logs.
            canonical_json(record)
            validate_json_text(record)
            record = parse_contract(DictationRecord, record)
            if record.record_id in seen:
                raise ValueError("Repeated observation identity in batch")
            seen.add(record.record_id)
            metadata = record.metadata
            result.append(
                parse_contract(
                    ObservationInput,
                    {
                        "source_key": source_key(namespace, record.record_id),
                        "kind": "imported_dictation",
                        "raw_text": record.raw_transcript,
                        "formatted_text": record.formatted_text,
                        "captured_at": metadata.get("captured_at")
                        if metadata is not None
                        else None,
                        "capture_metadata": metadata,
                    },
                )
            )
        if not result:
            raise ValueError("Empty import")
        return result
    except (ValueError, TypeError, KeyError, RecursionError):
        raise ApplicationError(ErrorCode.INVALID_INPUT) from None
