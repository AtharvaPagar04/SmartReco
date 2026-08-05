from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.services.learning_path_policy import (
    MAX_FORMAT_PREFERENCES,
    MAX_LEARNING_GOALS,
    MAX_LEARNING_PREFERENCES,
    MAX_PATH_COURSES,
    MAX_PRIOR_SKILLS,
    MAX_QUICK_INSTRUCTIONS,
    MAX_SECONDARY_DOMAINS,
    MIN_PATH_COURSES,
)


class DomainOption:
    def __init__(self, code: str, label: str, group: str, categories: tuple[str, ...], tags: tuple[str, ...] = ()):
        self.code, self.label, self.group, self.categories, self.tags = code, label, group, categories, tags


DOMAIN_OPTIONS = (
    DomainOption("FRONTEND", "Frontend Development", "Development", ("Web Development",), ("frontend", "ui")),
    DomainOption("BACKEND", "Backend Development", "Development", ("Web Development",), ("backend", "apis", "python")),
    DomainOption("FULLSTACK", "Full-Stack Development", "Development", ("Web Development",), ("full-stack", "apis")),
    DomainOption("MOBILE", "Mobile Development", "Development", ("Web Development",), ("mobile",)),
    DomainOption("API", "API Development", "Development", ("Web Development",), ("apis", "async")),
    DomainOption("ARCHITECTURE", "Software Architecture", "Development", ("Web Development", "Cloud Computing"), ("architecture",)),
    DomainOption("PYTHON", "Python", "Artificial Intelligence and Data", ("Python",), ("python", "programming")),
    DomainOption("DATA_ANALYSIS", "Data Analysis", "Artificial Intelligence and Data", ("Data Science", "Business Analytics"), ("analytics", "analysis")),
    DomainOption("DATA_SCIENCE", "Data Science", "Artificial Intelligence and Data", ("Data Science",), ("data", "analysis")),
    DomainOption("MACHINE_LEARNING", "Machine Learning", "Artificial Intelligence and Data", ("Machine Learning",), ("machine learning", "evaluation")),
    DomainOption("GENERATIVE_AI", "Generative AI", "Artificial Intelligence and Data", ("Artificial Intelligence",), ("ai", "generation")),
    DomainOption("PROMPT_ENGINEERING", "Prompt Engineering", "Artificial Intelligence and Data", ("Artificial Intelligence",), ("prompting", "evaluation")),
    DomainOption("AGENTIC_AI", "Agentic AI", "Artificial Intelligence and Data", ("Agentic AI", "Artificial Intelligence"), ("agents", "orchestration", "tool calling")),
    DomainOption("RAG", "RAG and Vector Databases", "Artificial Intelligence and Data", ("Artificial Intelligence",), ("rag", "retrieval", "vectors")),
    DomainOption("MLOPS", "MLOps", "Artificial Intelligence and Data", ("DevOps", "Machine Learning"), ("operations", "deployment")),
    DomainOption("RESPONSIBLE_AI", "Responsible AI", "Artificial Intelligence and Data", ("Product Management",), ("responsible ai", "governance")),
    DomainOption("DEVOPS", "DevOps", "Cloud, DevOps, and Infrastructure", ("DevOps",), ("operations", "reliability")),
    DomainOption("CLOUD", "Cloud Engineering", "Cloud, DevOps, and Infrastructure", ("Cloud Computing",), ("cloud", "architecture")),
    DomainOption("KUBERNETES", "Kubernetes", "Cloud, DevOps, and Infrastructure", ("DevOps",), ("kubernetes", "containers")),
    DomainOption("DOCKER", "Docker", "Cloud, DevOps, and Infrastructure", ("DevOps",), ("containers", "docker")),
    DomainOption("IAC", "Infrastructure as Code", "Cloud, DevOps, and Infrastructure", ("Cloud Computing",), ("infrastructure",)),
    DomainOption("PLATFORM", "Platform Engineering", "Cloud, DevOps, and Infrastructure", ("Cloud Computing",), ("platform",)),
    DomainOption("SRE", "Site Reliability Engineering", "Cloud, DevOps, and Infrastructure", ("DevOps",), ("reliability", "incidents")),
    DomainOption("CYBERSECURITY", "Cybersecurity Foundations", "Cybersecurity", ("Cybersecurity",), ("security",)),
    DomainOption("APPSEC", "Application Security", "Cybersecurity", ("Cybersecurity",), ("security", "web")),
    DomainOption("CLOUD_SECURITY", "Cloud Security", "Cybersecurity", ("Cybersecurity", "Cloud Computing"), ("security", "cloud")),
    DomainOption("THREAT_MODELING", "Threat Modeling", "Cybersecurity", ("Cybersecurity",), ("threat modeling", "risk")),
    DomainOption("SECURE_AI", "Secure AI Products", "Cybersecurity", ("Cybersecurity",), ("security", "ai products")),
    DomainOption("AUTH", "Authentication and Identity", "Cybersecurity", ("Cybersecurity",), ("authentication", "sessions")),
    DomainOption("PRODUCT", "Product Management", "Product and Design", ("Product Management",), ("product", "discovery")),
    DomainOption("UX", "UI/UX Design", "Product and Design", ("UI/UX Design",), ("design", "ux")),
    DomainOption("DESIGN_SYSTEMS", "Design Systems", "Product and Design", ("UI/UX Design",), ("design systems", "components")),
    DomainOption("ACCESSIBILITY", "Accessibility", "Product and Design", ("UI/UX Design",), ("accessibility", "keyboard")),
    DomainOption("DATA_STORYTELLING", "Data Storytelling", "Product and Design", ("Data Science",), ("storytelling", "charts")),
    DomainOption("AI_PRODUCT", "AI Product Strategy", "Product and Design", ("Product Management",), ("ai", "product strategy")),
    DomainOption("SQL", "SQL", "Data Engineering", ("Data Science",), ("sql", "analytics")),
    DomainOption("DATA_PIPELINES", "Data Pipelines", "Data Engineering", ("Data Science",), ("data pipelines", "etl")),
    DomainOption("ANALYTICS_ENGINEERING", "Analytics Engineering", "Data Engineering", ("Data Science", "Business Analytics"), ("analytics", "data")),
    DomainOption("DATA_WAREHOUSING", "Data Warehousing", "Data Engineering", ("Data Science",), ("data", "warehouse")),
    DomainOption("STREAMING", "Streaming Systems", "Data Engineering", ("Data Science",), ("streaming", "events")),
    DomainOption("DATA_QUALITY", "Data Quality", "Data Engineering", ("Data Science",), ("quality", "pipelines")),
)
DOMAIN_BY_CODE = {item.code: item for item in DOMAIN_OPTIONS}
GOALS = {"FUNDAMENTALS": "Learn the fundamentals", "PROJECTS": "Build practical projects", "JOB_ROLE": "Prepare for a job role", "NEW_DOMAIN": "Move into a new domain", "CURRENT_ROLE": "Improve skills for my current role", "PRODUCTION": "Build a production application", "INTERVIEWS": "Prepare for interviews", "PORTFOLIO": "Create a portfolio", "ADVANCED": "Understand advanced concepts", "GAPS": "Fill skill gaps"}
LEVELS = {"BEGINNER": "Complete beginner", "FAMILIAR": "Some familiarity", "FOUNDATIONS": "Comfortable with fundamentals", "INTERMEDIATE": "Intermediate practitioner", "ADVANCED": "Advanced practitioner"}
PREFERENCES = {"FOUNDATIONS": "Guided foundations", "PROJECTS": "Hands-on projects", "SHORT": "Short practical lessons", "DEEP": "Deep technical explanations", "PRODUCTION": "Production-focused examples", "THEORY": "Theory and evaluation", "INTERVIEWS": "Interview preparation", "PORTFOLIO": "Portfolio-building"}
PRIOR_SKILLS = {"PYTHON": "Python", "SQL": "SQL", "GIT": "Git", "APIS": "APIs", "MACHINE_LEARNING": "Machine Learning", "CLOUD": "Cloud", "DOCKER": "Docker", "PROMPT_ENGINEERING": "Prompt Engineering"}
FORMAT_PREFERENCES = {"READING": "Reading", "PRACTICE": "Practice exercises", "PROJECTS": "Projects", "REVIEWS": "Reviews", "MIXED": "Mixed format"}
QUICK_INSTRUCTIONS = {"free": "Prefer free courses", "projects": "Prefer practical projects", "math": "Avoid advanced math", "production": "Focus on production skills", "interviews": "Include interview preparation", "short": "Keep the path short"}
BUDGET_TYPES = {"FREE": Decimal("0"), "UNDER_50": Decimal("50"), "UNDER_100": Decimal("100"), "UNDER_200": Decimal("200"), "FLEXIBLE": None, "CUSTOM": None}
PATH_LENGTHS = {"FOCUSED": (3, 4), "BALANCED": (6, 7), "EXTENDED": (8, 8), "DEEP": (8, 8), "AUTO": (3, 8)}


class LearningPathInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary_domain: str
    secondary_domains: list[str] = Field(default_factory=list, max_length=MAX_SECONDARY_DOMAINS)
    goals: list[str] = Field(min_length=1, max_length=MAX_LEARNING_GOALS)
    level: str
    learning_preferences: list[str] = Field(min_length=1, max_length=MAX_LEARNING_PREFERENCES)
    prior_skills: list[str] = Field(default_factory=list, max_length=MAX_PRIOR_SKILLS)
    format_preferences: list[str] = Field(default_factory=list, max_length=MAX_FORMAT_PREFERENCES)
    weekly_hours: int = Field(ge=1, le=40)
    target_weeks: int | None = Field(default=None, ge=1, le=52)
    budget_type: Literal["FREE", "UNDER_50", "UNDER_100", "UNDER_200", "FLEXIBLE", "CUSTOM"] = "FLEXIBLE"
    budget_scope: Literal["PATH", "COURSE"] = "PATH"
    budget_amount: Decimal | None = Field(default=None, ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    path_length: Literal["FOCUSED", "BALANCED", "EXTENDED", "DEEP", "AUTO"] = "AUTO"
    requested_course_count: int = Field(default=4, ge=MIN_PATH_COURSES, le=MAX_PATH_COURSES)
    optional_instruction: str = Field(default="", max_length=500)
    quick_instructions: list[str] = Field(default_factory=list, max_length=MAX_QUICK_INSTRUCTIONS)

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_input(cls, values):
        values = dict(values or {})
        if "goals" not in values and values.get("goal"):
            values["goals"] = [values.pop("goal")]
        else:
            values.pop("goal", None)
        if "format_preferences" not in values and values.get("format_preference"):
            values["format_preferences"] = [values.pop("format_preference")]
        else:
            values.pop("format_preference", None)
        legacy_path = values.get("path_length")
        if legacy_path in {"QUICK", "STANDARD"}:
            values["path_length"] = "FOCUSED" if legacy_path == "QUICK" else "BALANCED"
        if "requested_course_count" not in values:
            values["requested_course_count"] = 4 if values.get("path_length") == "FOCUSED" else 7 if values.get("path_length") == "BALANCED" else 8 if values.get("path_length") in {"EXTENDED", "DEEP"} else 4
        if "selected_domains" in values:
            selected = [item for item in values.pop("selected_domains") if item]
            if not values.get("primary_domain"):
                values["primary_domain"], values["secondary_domains"] = (selected[0] if selected else ""), selected[1:]
        labels = {label: code for code, label in QUICK_INSTRUCTIONS.items()}
        values["quick_instructions"] = [labels.get(item, item) for item in values.get("quick_instructions", [])]
        return values

    @field_validator("primary_domain")
    @classmethod
    def valid_domain(cls, value: str) -> str:
        if value not in DOMAIN_BY_CODE:
            raise ValueError("Choose a supported primary domain.")
        return value

    @field_validator("secondary_domains")
    @classmethod
    def valid_secondary_domains(cls, values: list[str]) -> list[str]:
        if any(value not in DOMAIN_BY_CODE for value in values):
            raise ValueError("Choose supported secondary domains.")
        if len(set(values)) != len(values):
            raise ValueError("Secondary domains must be unique.")
        return values

    @field_validator("goals")
    @classmethod
    def valid_goals(cls, values: list[str]) -> list[str]:
        if any(value not in GOALS for value in values):
            raise ValueError("Choose supported learning goals.")
        if len(set(values)) != len(values):
            raise ValueError("Learning goals must be unique.")
        return values

    @field_validator("level")
    @classmethod
    def valid_level(cls, value: str) -> str:
        if value not in LEVELS:
            raise ValueError("Choose your current level.")
        return value

    @field_validator("learning_preferences")
    @classmethod
    def valid_preferences(cls, values: list[str]) -> list[str]:
        if any(value not in PREFERENCES for value in values) or len(set(values)) != len(values):
            raise ValueError("Choose supported learning preferences.")
        return values

    @field_validator("prior_skills")
    @classmethod
    def valid_prior_skills(cls, values: list[str]) -> list[str]:
        if any(value not in PRIOR_SKILLS for value in values) or len(set(values)) != len(values):
            raise ValueError("Choose supported prior skills once each.")
        return values

    @field_validator("format_preferences")
    @classmethod
    def valid_formats(cls, values: list[str]) -> list[str]:
        if any(value not in FORMAT_PREFERENCES for value in values) or len(set(values)) != len(values):
            raise ValueError("Choose supported format preferences once each.")
        return values

    @field_validator("quick_instructions")
    @classmethod
    def valid_quick_instructions(cls, values: list[str]) -> list[str]:
        if any(value not in QUICK_INSTRUCTIONS for value in values) or len(set(values)) != len(values):
            raise ValueError("Choose supported quick instructions once each.")
        return values

    @field_validator("currency")
    @classmethod
    def uppercase_currency(cls, value: str) -> str:
        value = value.upper()
        if not value.isalpha():
            raise ValueError("Currency must be alphabetic.")
        return value

    @field_validator("budget_amount")
    @classmethod
    def valid_budget(cls, value: Decimal | None) -> Decimal | None:
        return value.quantize(Decimal("0.01")) if value is not None else value

    @model_validator(mode="after")
    def custom_budget_requires_amount(self):
        if self.primary_domain in self.secondary_domains:
            raise ValueError("The primary domain is not also a secondary interest.")
        if self.budget_type == "CUSTOM" and self.budget_amount is None:
            raise ValueError("Enter a custom budget amount.")
        return self

    def effective_budget(self) -> Decimal | None:
        return self.budget_amount if self.budget_type == "CUSTOM" else BUDGET_TYPES[self.budget_type]

    @property
    def goal(self) -> str:
        return self.goals[0]

    @property
    def format_preference(self) -> str:
        return self.format_preferences[0] if self.format_preferences else "MIXED"
