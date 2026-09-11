"""Structural contracts, not semantic-entailment or truth certification."""

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    JsonValue,
    StrictBool,
    ValidationError,
    model_validator,
)

from jarvis.errors import ApplicationError, ErrorCode


def exact_text(value: str) -> str:
    if not value.strip():
        raise ValueError("Text must contain a non-whitespace character")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError("Text must be valid Unicode") from None
    return value  # Never strip, normalize Unicode, or change line endings.


Text = Annotated[
    str, Field(strict=True, min_length=1, max_length=65536), AfterValidator(exact_text)
]
Label = Annotated[str, Field(strict=True, min_length=1, max_length=255), AfterValidator(exact_text)]
Revision = Annotated[int, Field(strict=True, ge=0)]
PositiveRevision = Annotated[int, Field(strict=True, ge=1)]


def calendar_date(value: object) -> object:
    if isinstance(value, datetime) or not (
        isinstance(value, date)
        or isinstance(value, str)
        and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)
    ):
        raise ValueError("Calendar dates require explicit YYYY-MM-DD precision")
    return value


CalendarDate = Annotated[date, BeforeValidator(calendar_date)]


def explicit_instant(value: object) -> object:
    if not (
        isinstance(value, datetime)
        or isinstance(value, str)
        and re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})", value
        )
    ):
        raise ValueError("Instants require an explicit timestamp with timezone")
    return value


Timestamp = Annotated[AwareDatetime, BeforeValidator(explicit_instant)]


class Contract(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, revalidate_instances="always", hide_input_in_errors=True
    )


class ObservationInput(Contract):
    source_key: Label
    kind: Literal["user_message", "imported_dictation"]
    raw_text: Text
    formatted_text: Text | None = None
    captured_at: Timestamp | None = None
    capture_metadata: dict[str, JsonValue] | None = None


class SourceObservation(ObservationInput):
    id: UUID
    owner_id: UUID
    revision: PositiveRevision
    kind: Literal["user_message", "imported_dictation", "synthetic", "unknown"]
    content_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    imported_at: Timestamp


class ObservationWrite(Contract):
    observation: ObservationInput
    expected_policy_revision: Revision
    expected_source_revision: Revision = 0


class SupportingPassage(Contract):
    source_id: UUID
    source_revision: PositiveRevision
    variant: Literal["raw", "formatted"]
    start: Annotated[int, Field(strict=True, ge=0)]
    end: Annotated[int, Field(strict=True, gt=0)]
    exact_text: Text

    @model_validator(mode="after")
    def ordered_offsets(self) -> Self:
        if self.end <= self.start:
            raise ValueError("Passage must have a positive half-open range")
        return self


class EntityReference(Contract):
    label: Label
    # Absence means unresolved identity; equal names never supply this ID.
    entity_id: UUID | None = None

    @model_validator(mode="after")
    def no_unresolved_registry_ids(self) -> Self:
        if self.entity_id is not None:
            raise ValueError(
                "Resolved entity IDs require a backend registry, which is not implemented"
            )
        return self


class TextValue(Contract):
    kind: Literal["text"]
    value: Text


class QuantityValue(Contract):
    kind: Literal["quantity"]
    value: Annotated[Decimal, Field(allow_inf_nan=False)]
    unit: Label | None  # Explicit null preserves an unknown unit.


class BooleanValue(Contract):
    kind: Literal["boolean"]
    value: StrictBool


class DateValue(Contract):
    kind: Literal["date"]
    value: CalendarDate


TypedValue = Annotated[
    TextValue | QuantityValue | BooleanValue | DateValue, Field(discriminator="kind")
]


class CalendarTime(Contract):
    precision: Literal["date"]
    value: CalendarDate


class InstantTime(Contract):
    precision: Literal["instant"]
    value: Timestamp


TimePoint = Annotated[CalendarTime | InstantTime, Field(discriminator="precision")]


class ClaimTime(Contract):
    event: TimePoint | None = None
    valid_from: TimePoint | None = None
    valid_to: TimePoint | None = None

    @model_validator(mode="after")
    def ordered_interval(self) -> Self:
        if self.valid_from is not None and self.valid_to is not None:
            if self.valid_from.precision != self.valid_to.precision:
                raise ValueError("Interval endpoints must have the same precision")
            if self.valid_to.value < self.valid_from.value:
                raise ValueError("Interval endpoints are reversed")
        return self


class Scope(Contract):
    kind: Literal["unspecified", "global", "project", "task"]
    key: Label | None = None

    @model_validator(mode="after")
    def scoped_key(self) -> Self:
        if (self.kind in {"project", "task"}) != (self.key is not None):
            raise ValueError("Project/task scope requires a key; other scopes do not accept one")
        return self


class ClaimContent(Contract):
    subject: EntityReference
    predicate: Label
    value: TypedValue
    scope: Scope
    attribution: EntityReference
    evidence_status: Literal["reported", "tentative", "disputed"]
    modality: Literal["asserted", "conditional", "hypothetical", "question", "quoted"]
    negated: StrictBool
    condition: Text | None = None
    time: ClaimTime = Field(default_factory=ClaimTime)

    @model_validator(mode="after")
    def preserve_uncertainty(self) -> Self:
        if self.modality in {"conditional", "hypothetical", "question"}:
            if self.evidence_status == "reported":
                raise ValueError("Non-asserted proposals must retain uncertainty")
        if self.modality == "conditional" and self.condition is None:
            raise ValueError("Conditional proposals require their condition")
        if self.modality != "conditional" and self.condition is not None:
            raise ValueError("A condition requires conditional modality")
        return self


class ClaimWrite(Contract):
    claim_id: UUID | None = None
    expected_claim_revision: Revision = 0
    expected_policy_revision: Revision
    content: ClaimContent
    passages: Annotated[tuple[SupportingPassage, ...], Field(min_length=1, max_length=32)]

    @model_validator(mode="after")
    def revision_identity(self) -> Self:
        if (self.claim_id is None) != (self.expected_claim_revision == 0):
            raise ValueError(
                "New claims need revision zero; existing claims need their current revision"
            )
        keys = [(p.source_id, p.source_revision, p.variant, p.start, p.end) for p in self.passages]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate supporting passage")
        return self


class ClaimRevision(Contract):
    id: UUID
    claim_id: UUID
    owner_id: UUID
    revision: PositiveRevision
    policy_revision: Revision
    recorded_at: Timestamp
    lifecycle: Literal["active", "superseded", "corrected", "excluded"]
    content: ClaimContent
    passages: tuple[SupportingPassage, ...]


def parse_contract[T: Contract](model: type[T], value: object) -> T:
    try:
        if isinstance(value, (str, bytes)):
            return model.model_validate_json(value)
        # Revalidate a snapshot, including instances made with model_construct/copy.
        if isinstance(value, BaseModel):
            value = value.model_dump(mode="json", warnings=False)
        return model.model_validate(value)
    except (ValidationError, ValueError, TypeError):
        raise ApplicationError(ErrorCode.INVALID_INPUT) from None
    except Exception:
        raise ApplicationError(ErrorCode.OPERATION_FAILED) from None
