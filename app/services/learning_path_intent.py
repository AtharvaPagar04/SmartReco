from __future__ import annotations

from dataclasses import asdict, dataclass

from app.schemas.learning_path import (
    DOMAIN_BY_CODE,
    GOALS,
    LEVELS,
    LearningPathInput,
)


@dataclass(frozen=True)
class LearningPathIntent:
    primary_domain_code: str
    primary_domain_label: str
    secondary_domain_codes: tuple[str, ...]
    secondary_domain_labels: tuple[str, ...]
    goal_codes: tuple[str, ...]
    goal_labels: tuple[str, ...]
    level_code: str
    level_label: str
    weekly_hours: int
    target_weeks: int | None
    budget_type: str
    budget_scope: str
    budget_amount: str | None
    currency: str
    path_length: str
    requested_course_count: int

    @classmethod
    def from_input(cls, path_input: LearningPathInput) -> "LearningPathIntent":
        primary = DOMAIN_BY_CODE[path_input.primary_domain]
        secondary = tuple(DOMAIN_BY_CODE[code] for code in path_input.secondary_domains)
        return cls(
            primary_domain_code=primary.code,
            primary_domain_label=primary.label,
            secondary_domain_codes=tuple(item.code for item in secondary),
            secondary_domain_labels=tuple(item.label for item in secondary),
            goal_codes=tuple(path_input.goals),
            goal_labels=tuple(GOALS[code] for code in path_input.goals),
            level_code=path_input.level,
            level_label=LEVELS[path_input.level],
            weekly_hours=path_input.weekly_hours,
            target_weeks=path_input.target_weeks,
            budget_type=path_input.budget_type,
            budget_scope=path_input.budget_scope,
            budget_amount=str(path_input.budget_amount) if path_input.budget_amount is not None else None,
            currency=path_input.currency,
            path_length=path_input.path_length,
            requested_course_count=path_input.requested_course_count,
        )

    @property
    def target_domains(self) -> tuple[str, ...]:
        return (self.primary_domain_code, *self.secondary_domain_codes)

    def to_prompt_dict(self) -> dict:
        value = asdict(self)
        value["secondary_domain_codes"] = list(self.secondary_domain_codes)
        value["secondary_domain_labels"] = list(self.secondary_domain_labels)
        value["goal_codes"] = list(self.goal_codes)
        value["goal_labels"] = list(self.goal_labels)
        value["targets"] = {
            "primary_domain": self.primary_domain_label,
            "secondary_domains": list(self.secondary_domain_labels),
            "goals": list(self.goal_labels),
        }
        return value

    def retrieval_queries(self, behavior_profile: dict | None = None) -> list[tuple[str, str]]:
        primary_opt = DOMAIN_BY_CODE.get(self.primary_domain_code)
        primary_kw = " ".join(primary_opt.search_keywords) if primary_opt else ""
        primary = f"{self.primary_domain_label} {primary_kw}".strip()

        queries = [("primary_domain", primary)]

        sec_terms = []
        for sec_code in self.secondary_domain_codes:
            sec_opt = DOMAIN_BY_CODE.get(sec_code)
            if sec_opt:
                kw = " ".join(sec_opt.search_keywords)
                sec_terms.append(f"{sec_opt.label} {kw}".strip())
            else:
                sec_terms.append(sec_code)
        if sec_terms:
            queries.append(("secondary_domain", "; ".join(sec_terms)))

        queries.append(("goals", "; ".join(self.goal_labels)))
        return queries
