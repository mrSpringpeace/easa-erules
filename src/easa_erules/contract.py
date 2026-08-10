"""Machine-readable output contract shared by every agent-facing command.

Two guarantees matter more than anything else here:

1. **Versioned shape.** Every JSON document carries ``schema_version`` so a
   downstream consumer can tell a shape change from an empty result.
2. **No ambiguous emptiness.** An empty result is always accompanied by a
   status that says *why* it is empty. ``no_match`` ("searched, found nothing")
   and ``not_cached`` ("never looked, the regulation is not here") must never
   be indistinguishable to an agent.

Versioning policy for ``schema_version``:

* breaking change to an existing field → major bump
* new optional field → minor bump
* wording or documentation only → no bump
"""

from __future__ import annotations

from enum import Enum
from typing import Any

SCHEMA_VERSION = "1.0"


class Status(str, Enum):
    """Outcome of a command, independent of how much data came back."""

    OK = "ok"
    NO_MATCH = "no_match"
    NOT_CACHED = "not_cached"
    INDEX_MISSING = "index_missing"
    FETCH_FAILED = "fetch_failed"
    SOURCE_DRIFT = "source_drift"
    PARSE_ERROR = "parse_error"
    ERROR = "error"


#: Process exit code per status. ``ok`` and ``no_match`` are both successful
#: runs — the difference is in the payload, not in the shell result.
EXIT_CODES: dict[Status, int] = {
    Status.OK: 0,
    Status.NO_MATCH: 0,
    Status.NOT_CACHED: 3,
    Status.INDEX_MISSING: 4,
    Status.FETCH_FAILED: 5,
    Status.SOURCE_DRIFT: 6,
    Status.PARSE_ERROR: 7,
    Status.ERROR: 1,
}

STATUS_HINTS: dict[Status, str] = {
    Status.NO_MATCH: "The document was searched and nothing matched. "
    "This is not evidence that the rule does not exist — confirm the "
    "regulation and amendment are the ones you meant.",
    Status.NOT_CACHED: "Regulation not in the local cache. Run 'easa-erules "
    "fetch <id>' or pass --fetch.",
    Status.INDEX_MISSING: "Search index missing or invalidated. Re-run with --rebuild.",
    Status.FETCH_FAILED: "Download failed. Check network access to easa.europa.eu.",
    Status.SOURCE_DRIFT: "The EASA landing page no longer matches the expected "
    "structure. The catalog entry needs updating.",
    Status.PARSE_ERROR: "The source could not be parsed into a Regulation AST.",
}


def exit_code(status: Status) -> int:
    """Process exit code for a status."""
    return EXIT_CODES.get(status, 1)


class ToolError(Exception):
    """An error with a status an agent can branch on."""

    def __init__(self, status: Status, message: str, **details: Any):
        super().__init__(message)
        self.status = status
        self.message = message
        self.details = details

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "status": self.status.value,
            "error": {"message": self.message},
        }
        if self.details:
            payload["error"].update(self.details)
        hint = STATUS_HINTS.get(self.status)
        if hint:
            payload["error"]["hint"] = hint
        return payload


def envelope(
    status: Status,
    *,
    source: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    **payload: Any,
) -> dict[str, Any]:
    """Wrap a command result in the standard machine-readable envelope."""
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": status.value,
    }
    if source is not None:
        result["source"] = source
    result["warnings"] = list(warnings or [])
    hint = STATUS_HINTS.get(status)
    if hint and status is not Status.OK:
        result["hint"] = hint
    result.update(payload)
    return result
