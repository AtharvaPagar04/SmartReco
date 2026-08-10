from pydantic import ValidationError


FRIENDLY = {
    "primary_domain": "Choose a primary domain before continuing.",
    "secondary_domains": "Choose up to two secondary domains.",
    "selected_domains": "Choose up to three domains.",
    "goals": "Choose up to two learning goals.",
    "weekly_hours": "Weekly time must be between 1 and 40 hours.",
    "requested_course_count": "Choose a path with three or four courses.",
}


def friendly_validation_errors(error: ValidationError) -> dict[str, str]:
    result: dict[str, str] = {}
    for detail in error.errors():
        raw_message = str(detail.get("msg", ""))
        field = next((str(part) for part in detail.get("loc", ()) if isinstance(part, str)), "form")
        if field == "form" and "primary domain" in raw_message.lower():
            field = "primary_domain"
        elif field == "form" and "budget" in raw_message.lower():
            field = "budget_amount"
        message = FRIENDLY.get(field, "Review this answer and try again.")
        if detail.get("type") == "missing" and field in {"primary_domain", "goals", "level"}:
            message = {
                "primary_domain": FRIENDLY["primary_domain"],
                "goals": "Choose at least one learning goal.",
                "level": "Choose your current level.",
            }[field]
        if "unique" in str(detail.get("msg", "")).lower():
            message = f"Choose each {field.replace('_', ' ')} only once."
        result.setdefault(field, message)
    return result
