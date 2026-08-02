from fastapi import Request

ALLOWED = {"success", "error", "warning", "info"}


def flash(request: Request, message: str, category: str = "info") -> None:
    request.session.setdefault("flashes", []).append({"message": message[:500], "category": category if category in ALLOWED else "info"})


def pop_flashes(request: Request) -> list[dict[str, str]]:
    return request.session.pop("flashes", [])
