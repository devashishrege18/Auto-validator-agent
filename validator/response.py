# -------------------------------------------------------
# validator/response.py
# -------------------------------------------------------
# Standardised API Response Envelope.
#
# Every endpoint should return a consistent JSON shape
# that other agents (Dispatcher, Spectre-Sentinel) can
# parse predictably.
#
# Standard format:
#   {
#     "success": true,
#     "agent": "auto-auditor-validator",
#     "version": "2.0.0",
#     "timestamp": "2026-05-16T...",
#     "data": { ... actual payload ... },
#     "meta": { "request_id": "...", "processing_ms": 42 }
#   }
#
# On error:
#   {
#     "success": false,
#     "agent": "auto-auditor-validator",
#     "error": { "code": "INVALID_EVIDENCE", "message": "..." }
#   }
# -------------------------------------------------------

import uuid
import time
from datetime import datetime, timezone
from typing import Any, Optional


AGENT_ID = "auto-auditor-validator"
AGENT_VERSION = "2.0.0"


def success_response(
    data: Any,
    processing_start: Optional[float] = None,
) -> dict:
    """
    Wrap any payload in the standard success envelope.

    Parameters
    ----------
    data : Any
        The actual response payload (dict, list, etc.)
    processing_start : float, optional
        time.time() captured at the start of request handling.
        If provided, processing_ms is calculated automatically.
    """
    meta = {
        "request_id": str(uuid.uuid4())[:8],
    }
    if processing_start is not None:
        meta["processing_ms"] = round(
            (time.time() - processing_start) * 1000, 1
        )

    return {
        "success": True,
        "agent": AGENT_ID,
        "version": AGENT_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": data,
        "meta": meta,
    }


def error_response(
    code: str,
    message: str,
    details: Optional[dict] = None,
) -> dict:
    """
    Build a standard error envelope.

    Parameters
    ----------
    code : str
        Machine-readable error code (e.g., "INVALID_EVIDENCE").
    message : str
        Human-readable error description.
    details : dict, optional
        Additional debug info (field names, expected types, etc.)
    """
    error = {
        "code": code,
        "message": message,
    }
    if details:
        error["details"] = details

    return {
        "success": False,
        "agent": AGENT_ID,
        "version": AGENT_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "error": error,
    }
