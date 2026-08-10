from __future__ import annotations

import json
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Sequence

logger = logging.getLogger("app.learning_path")


# Regex patterns for redacting secrets from log values
SECRET_PATTERNS = (
    re.compile(r"(?:sk|mesh_sec|secret)[-_][a-zA-Z0-9_-]{10,}", re.I),
    re.compile(r"Bearer\s+[a-zA-Z0-9._~+/-]+=*", re.I),
    re.compile(r"(?i)(mesh[-_]?api[-_]?key|langsmith[-_]?api[-_]?key|google[-_]?client[-_]?secret|secret[-_]?key|authorization|password|token)[:=]\s*([^\s,;]+)"),
)


def sanitize_log_value(val: Any) -> Any:
    """Sanitize secrets from logged strings or primitive values."""
    if val is None:
        return None
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, (int, float)):
        return val
    if isinstance(val, (list, tuple, set)):
        return [sanitize_log_value(item) for item in val]
    if isinstance(val, dict):
        sanitized = {}
        for k, v in val.items():
            k_str = str(k)
            k_lower = k_str.lower()
            if any(secret_kw in k_lower for secret_kw in ("api_key", "secret", "token", "auth", "password", "credential", "private_key", "secret_key", "access_key")) or k_lower == "key":
                sanitized[k_str] = "[REDACTED]"
            else:
                sanitized[k_str] = sanitize_log_value(v)
        return sanitized

    sval = str(val)
    # Check regexes
    for pattern in SECRET_PATTERNS:
        if pattern.search(sval):
            # If it's a key=value pattern with capturing groups
            if pattern.groups >= 1:
                sval = pattern.sub(r"\1=[REDACTED]", sval)
            else:
                sval = pattern.sub("[REDACTED_API_KEY]", sval)
    return sval


def _sanitize_log_message(msg: Any) -> str:
    """Sanitize secrets specifically from raw string messages."""
    return str(sanitize_log_value(msg))


def format_kv_string(fields: dict[str, Any]) -> str:
    """Format dictionary into key=value pairs for structured logging."""
    pairs = []
    for k, v in fields.items():
        if v is None:
            continue
        sanitized = sanitize_log_value(v)
        if isinstance(sanitized, bool):
            s_val = "true" if sanitized else "false"
        elif isinstance(sanitized, (list, tuple)):
            s_val = json.dumps(sanitized, separators=(",", ":"))
        elif isinstance(sanitized, dict):
            s_val = json.dumps(sanitized, separators=(",", ":"))
        else:
            s_val = str(sanitized)
            if " " in s_val and not (s_val.startswith("[") or s_val.startswith("{")):
                s_val = f'"{s_val}"'
        pairs.append(f"{k}={s_val}")
    return " ".join(pairs)


def log_learning_path_step(
    log_obj: logging.Logger | None,
    event: str,
    trace_id: str,
    step: str | None = None,
    log_level: int = logging.INFO,
    duration_ms: float | int | None = None,
    **safe_fields: Any,
) -> None:
    """Standardized structured logging helper for learning path generation."""
    active_logger = log_obj or logger
    fields: dict[str, Any] = {"trace_id": trace_id}
    if step:
        fields["step"] = step
    if duration_ms is not None:
        fields["duration_ms"] = round(float(duration_ms), 2) if isinstance(duration_ms, float) else int(duration_ms)
    fields.update(safe_fields)

    msg = f"{event} {format_kv_string(fields)}"
    active_logger.log(log_level, msg)


@dataclass
class LearningPathTraceContext:
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    start_time: float = field(default_factory=time.perf_counter)

    first_failure_stage: str | None = None
    first_failure_reason: str | None = None
    final_failure_stage: str | None = None
    final_failure_reason: str | None = None

    mesh_attempt_count: int = 0
    mesh_attempt_durations_ms: list[int] = field(default_factory=list)

    retrieval_duration_ms: int = 0
    planner_duration_ms: int = 0
    persistence_duration_ms: int = 0
    total_duration_ms: int = 0

    selected_primary_count: int = 0
    selected_secondary_count: int = 0
    selected_cross_domain_count: int = 0
    selected_supporting_count: int = 0

    def record_failure(self, stage: str, reason: str) -> None:
        """Preserve the first failure stage/reason separately from later failures."""
        if self.first_failure_stage is None:
            self.first_failure_stage = stage
            self.first_failure_reason = reason
        self.final_failure_stage = stage
        self.final_failure_reason = reason

    def elapsed_ms(self) -> int:
        return int((time.perf_counter() - self.start_time) * 1000)
