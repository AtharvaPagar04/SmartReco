from __future__ import annotations

from dataclasses import asdict, dataclass

from app.schemas.learning_path import (
    DOMAIN_BY_CODE,
    FORMAT_PREFERENCES,
    GOALS,
    LEVELS,
    PREFERENCES,
    PRIOR_SKILLS,
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
    learning_preference_codes: tuple[str, ...]
    learning_preference_labels: tuple[str, ...]
    prior_skill_codes: tuple[str, ...]
    prior_skill_labels: tuple[str, ...]
    format_codes: tuple[str, ...]
    format_labels: tuple[str, ...]
    weekly_hours: int
    target_weeks: int | None
    budget_type: str
    budget_scope: str
    budget_amount: str | None
    currency: str
    path_length: str
    requested_course_count: int
    optional_instruction: str

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
            learning_preference_codes=tuple(path_input.learning_preferences),
            learning_preference_labels=tuple(PREFERENCES[code] for code in path_input.learning_preferences),
            prior_skill_codes=tuple(path_input.prior_skills),
            prior_skill_labels=tuple(PRIOR_SKILLS[code] for code in path_input.prior_skills),
            format_codes=tuple(path_input.format_preferences),
            format_labels=tuple(FORMAT_PREFERENCES[code] for code in path_input.format_preferences),
            weekly_hours=path_input.weekly_hours,
            target_weeks=path_input.target_weeks,
            budget_type=path_input.budget_type,
            budget_scope=path_input.budget_scope,
            budget_amount=str(path_input.budget_amount) if path_input.budget_amount is not None else None,
            currency=path_input.currency,
            path_length=path_input.path_length,
            requested_course_count=path_input.requested_course_count,
            optional_instruction=path_input.optional_instruction.strip(),
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
        value["learning_preference_codes"] = list(self.learning_preference_codes)
        value["learning_preference_labels"] = list(self.learning_preference_labels)
        value["prior_skill_codes"] = list(self.prior_skill_codes)
        value["prior_skill_labels"] = list(self.prior_skill_labels)
        value["format_codes"] = list(self.format_codes)
        value["format_labels"] = list(self.format_labels)
        value["known_skills"] = list(self.prior_skill_labels)
        value["targets"] = {
            "primary_domain": self.primary_domain_label,
            "secondary_domains": list(self.secondary_domain_labels),
            "goals": list(self.goal_labels),
        }
        return value

    def retrieval_queries(self, behavior_profile: dict | None = None) -> list[tuple[str, str]]:
        primary = f"{self.primary_domain_label} production application architecture engineering interfaces"
        secondary = "; ".join(self.secondary_domain_labels)
        queries = [("primary_domain", primary)]
        if secondary:
            queries.append(("secondary_domain", f"{secondary} accessibility design systems user experience interaction design"))
        queries.append(("goals", "; ".join(self.goal_labels)))
        preference = "; ".join((*self.learning_preference_labels, *self.format_labels))
        if preference:
            queries.append(("preferences", f"Learning preferences: {preference}. Existing skills: {', '.join(self.prior_skill_labels) or 'none'}"))
        return queries
