def normalize_search_query(value: str | None, *, max_length: int = 200) -> str:
    return " ".join((value or "").split())[:max_length]


def escaped_like(value: str) -> tuple[str, str]:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%", "\\"
