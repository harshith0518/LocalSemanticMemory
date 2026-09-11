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


class ApplicationError(Exception):
    """Only fixed categories cross adapter boundaries, never input/driver exceptions."""

    def __init__(self, code: ErrorCode):
        self.code = ErrorCode(code)
        super().__init__(self.code.value)

    def response(self) -> dict:
        return {"status": "error", "reason": self.code.value}
