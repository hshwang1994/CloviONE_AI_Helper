"""Job execution error classification (spec §18.7, §22)."""

from __future__ import annotations


class PermanentJobError(Exception):
    """Raised by handlers when retrying can never succeed
    (validation failure, unsupported request, forged payload, …)."""
