from enum import StrEnum


class ErrorCode(StrEnum):
    INVALID_INPUT = "invalid_input"
    INVALID_MODE = "invalid_mode"
    PRIVATE_OPERATION = "private_operation_denied"
    REFERENCE_UNAVAILABLE = "reference_unavailable"
    INVALID_PASSAGE = "invalid_passage"
    INELIGIBLE_SOURCE = "ineligible_source"
    STALE_REVISION = "stale_revision"
    IMPORT_CONFLICT = "import_conflict"
    DATABASE_UNAVAILABLE = "database_unavailable"
    OPERATION_FAILED = "operation_failed"
    PROVIDER_DISABLED = "provider_disabled"
    PROVIDER_FAILED = "provider_failed"
    RATE_LIMITED = "rate_limited"
    PROVIDER_RESPONSE = "provider_response_invalid"
    TRIAL_INPUT_DENIED = "trial_input_denied"
    BUDGET_EXHAUSTED = "budget_exhausted"
    CONTEXT_LIMIT = "context_limit"
    INVALID_TRANSITION = "invalid_transition"
    RETRY_LIMIT = "retry_limit_reached"
    EXCLUDED_SOURCE = "excluded_source"


class ApplicationError(Exception):
    """Only fixed categories cross adapter boundaries, never input/driver exceptions."""

    def __init__(self, code: ErrorCode):
        self.code = ErrorCode(code)
        super().__init__(self.code.value)

    def response(self) -> dict:
        return {"status": "error", "reason": self.code.value}
