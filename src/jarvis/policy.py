from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from jarvis.config import LOCAL_OWNER
from jarvis.errors import ApplicationError, ErrorCode


class Mode(StrEnum):
    NORMAL = "normal"
    PRIVATE = "private"


@dataclass(frozen=True)
class RequestContext:
    """Issued by backend identity resolution, never deserialized from request bodies."""

    owner_id: UUID
    mode: Mode

    def require_saved_access(self) -> None:
        if self.mode is not Mode.NORMAL:
            raise ApplicationError(ErrorCode.PRIVATE_OPERATION)


@dataclass(frozen=True)
class LocalIdentity:
    owner_id: UUID = LOCAL_OWNER

    def context(self, mode: str) -> RequestContext:
        try:
            selected = Mode(mode)
        except (TypeError, ValueError):
            raise ApplicationError(ErrorCode.INVALID_MODE) from None
        return RequestContext(self.owner_id, selected)
