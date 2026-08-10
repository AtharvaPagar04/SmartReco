from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.services.learning_path_policy import (
    MAX_LEARNING_GOALS,
    MAX_PATH_COURSES,
    MAX_SECONDARY_DOMAINS,
    MIN_PATH_COURSES,
)


class DomainOption:
    def __init__(self, code: str, label: str, group: str, categories: tuple[str, ...], tags: tuple[str, ...] = (), search_keywords: tuple[str, ...] = ()):
        self.code, self.label, self.group, self.categories, self.tags, self.search_keywords = code, label, group, categories, tags, search_keywords


DOMAIN_OPTIONS = (
    DomainOption("FRONTEND", "Frontend Development", "Development", ("Web Development",), ("frontend", "ui"), ("frontend", "ui", "ux", "accessibility", "interaction design", "design systems", "web development", "react", "components")),
    DomainOption("BACKEND", "Backend Development", "Development", ("Web Development",), ("backend", "apis", "python"), ("backend", "apis", "databases", "server", "microservices", "python", "architecture")),
    DomainOption("FULLSTACK", "Full-Stack Development", "Development", ("Web Development",), ("full-stack", "apis"), ("full-stack", "frontend", "backend", "web application", "apis", "database", "architecture", "production")),
    DomainOption("MOBILE", "Mobile Development", "Development", ("Web Development",), ("mobile",), ("mobile", "ios", "android", "react native", "flutter", "apps")),
    DomainOption("API", "API Development", "Development", ("Web Development",), ("apis", "async"), ("apis", "rest", "graphql", "async", "web services", "endpoints")),
    DomainOption("ARCHITECTURE", "Software Architecture", "Development", ("Web Development", "Cloud Computing"), ("architecture",), ("architecture", "system design", "scalability", "cloud computing", "patterns", "distributed systems")),
    DomainOption("PYTHON", "Python", "Artificial Intelligence and Data", ("Python",), ("python", "programming"), ("python", "programming", "data structures", "scripting", "backend")),
    DomainOption("DATA_ANALYSIS", "Data Analysis", "Artificial Intelligence and Data", ("Data Science", "Business Analytics"), ("analytics", "analysis"), ("analytics", "analysis", "pandas", "visualization", "sql", "insights")),
    DomainOption("DATA_SCIENCE", "Data Science", "Artificial Intelligence and Data", ("Data Science",), ("data", "analysis"), ("data science", "analysis", "statistics", "python", "machine learning")),
    DomainOption("MACHINE_LEARNING", "Machine Learning", "Artificial Intelligence and Data", ("Machine Learning",), ("machine learning", "evaluation"), ("machine learning", "evaluation", "models", "scikit-learn", "deep learning", "algorithms")),
    DomainOption("GENERATIVE_AI", "Generative AI", "Artificial Intelligence and Data", ("Artificial Intelligence",), ("ai", "generation"), ("generative ai", "llms", "large language models", "prompting", "transformers", "ai generation")),
    DomainOption("PROMPT_ENGINEERING", "Prompt Engineering", "Artificial Intelligence and Data", ("Artificial Intelligence",), ("prompting", "evaluation"), ("prompting", "prompt engineering", "evaluation", "in-context learning", "llm prompts")),
    DomainOption("AGENTIC_AI", "Agentic AI", "Artificial Intelligence and Data", ("Agentic AI", "Artificial Intelligence"), ("agents", "orchestration", "tool calling"), ("agentic ai", "agents", "tool calling", "orchestration", "multi-step workflows", "langgraph", "agent systems", "production agents")),
    DomainOption("RAG", "RAG and Vector Databases", "Artificial Intelligence and Data", ("Artificial Intelligence",), ("rag", "retrieval", "vectors"), ("rag", "retrieval", "vector databases", "embeddings", "qdrant", "knowledge search")),
    DomainOption("MLOPS", "MLOps", "Artificial Intelligence and Data", ("DevOps", "Machine Learning"), ("operations", "deployment"), ("mlops", "operations", "deployment", "model monitoring", "pipelines", "machine learning")),
    DomainOption("RESPONSIBLE_AI", "Responsible AI", "Artificial Intelligence and Data", ("Product Management",), ("responsible ai", "governance"), ("responsible ai", "governance", "ethics", "bias", "safety", "ai product management")),
    DomainOption("DEVOPS", "DevOps", "Cloud, DevOps, and Infrastructure", ("DevOps",), ("operations", "reliability"), ("devops", "deployment", "ci/cd", "containers", "kubernetes", "infrastructure", "reliability", "observability", "production operations")),
    DomainOption("CLOUD", "Cloud Engineering", "Cloud, DevOps, and Infrastructure", ("Cloud Computing",), ("cloud", "architecture"), ("cloud computing", "aws", "azure", "gcp", "architecture", "infrastructure")),
    DomainOption("KUBERNETES", "Kubernetes", "Cloud, DevOps, and Infrastructure", ("DevOps",), ("kubernetes", "containers"), ("kubernetes", "containers", "orchestration", "k8s", "clusters", "deployments")),
    DomainOption("DOCKER", "Docker", "Cloud, DevOps, and Infrastructure", ("DevOps",), ("containers", "docker"), ("docker", "containers", "dockerfile", "containerization", "virtualization")),
    DomainOption("IAC", "Infrastructure as Code", "Cloud, DevOps, and Infrastructure", ("Cloud Computing",), ("infrastructure",), ("infrastructure as code", "terraform", "cloudformation", "automation", "provisioning")),
    DomainOption("PLATFORM", "Platform Engineering", "Cloud, DevOps, and Infrastructure", ("Cloud Computing",), ("platform",), ("platform engineering", "developer portal", "internal platform", "automation", "cloud")),
    DomainOption("SRE", "Site Reliability Engineering", "Cloud, DevOps, and Infrastructure", ("DevOps",), ("reliability", "incidents"), ("site reliability engineering", "reliability", "incidents", "monitoring", "slos", "observability")),
    DomainOption("CYBERSECURITY", "Cybersecurity Foundations", "Cybersecurity", ("Cybersecurity",), ("security",), ("cybersecurity", "security", "threats", "vulnerabilities", "network security")),
    DomainOption("APPSEC", "Application Security", "Cybersecurity", ("Cybersecurity",), ("security", "web"), ("application security", "security", "web security", "owasp", "vulnerability scanning")),
    DomainOption("CLOUD_SECURITY", "Cloud Security", "Cybersecurity", ("Cybersecurity", "Cloud Computing"), ("security", "cloud"), ("cloud security", "security", "iam", "cloud compliance", "network security")),
    DomainOption("THREAT_MODELING", "Threat Modeling", "Cybersecurity", ("Cybersecurity",), ("threat modeling", "risk"), ("threat modeling", "risk assessment", "stride", "mitigation", "security architecture")),
    DomainOption("SECURE_AI", "Secure AI Products", "Cybersecurity", ("Cybersecurity",), ("security", "ai products"), ("secure ai", "ai security", "red teaming", "prompt injection", "guardrails")),
    DomainOption("AUTH", "Authentication and Identity", "Cybersecurity", ("Cybersecurity",), ("authentication", "sessions"), ("authentication", "identity", "oauth", "jwt", "sessions", "single sign-on")),
    DomainOption("PRODUCT", "Product Management", "Product and Design", ("Product Management",), ("product", "discovery"), ("product management", "discovery", "roadmap", "user research", "agile", "strategy")),
    DomainOption("UX", "UI/UX Design", "Product and Design", ("UI/UX Design",), ("design", "ux"), ("ui/ux design", "design", "ux", "accessibility", "interaction design", "user experience", "wireframing")),
    DomainOption("DESIGN_SYSTEMS", "Design Systems", "Product and Design", ("UI/UX Design",), ("design systems", "components"), ("design systems", "components", "style guides", "figma", "tokens", "ui components")),
    DomainOption("ACCESSIBILITY", "Accessibility", "Product and Design", ("UI/UX Design",), ("accessibility", "keyboard"), ("accessibility", "a11y", "wcag", "keyboard navigation", "screen readers", "inclusive design")),
    DomainOption("DATA_STORYTELLING", "Data Storytelling", "Product and Design", ("Data Science",), ("storytelling", "charts"), ("data storytelling", "charts", "dashboards", "data visualization", "reporting")),
    DomainOption("AI_PRODUCT", "AI Product Strategy", "Product and Design", ("Product Management",), ("ai", "product strategy"), ("ai product strategy", "ai product management", "llm products", "monetization", "user metrics")),
    DomainOption("SQL", "SQL", "Data Engineering", ("Data Science",), ("sql", "analytics"), ("sql", "queries", "relational databases", "postgresql", "data analytics")),
    DomainOption("DATA_PIPELINES", "Data Pipelines", "Data Engineering", ("Data Science",), ("data pipelines", "etl"), ("data pipelines", "etl", "airflow", "spark", "data ingestion", "batch processing")),
    DomainOption("ANALYTICS_ENGINEERING", "Analytics Engineering", "Data Engineering", ("Data Science", "Business Analytics"), ("analytics", "data"), ("analytics engineering", "dbt", "data modeling", "data transformation", "sql")),
    DomainOption("DATA_WAREHOUSING", "Data Warehousing", "Data Engineering", ("Data Science",), ("data", "warehouse"), ("data warehousing", "snowflake", "bigquery", "redshift", "data modeling")),
    DomainOption("STREAMING", "Streaming Systems", "Data Engineering", ("Data Science",), ("streaming", "events"), ("streaming systems", "kafka", "event-driven", "real-time data", "pub/sub")),
    DomainOption("DATA_QUALITY", "Data Quality", "Data Engineering", ("Data Science",), ("quality", "pipelines"), ("data quality", "great expectations", "data testing", "pipeline validation", "observability")),
)
DOMAIN_BY_CODE = {item.code: item for item in DOMAIN_OPTIONS}
GOALS = {"FUNDAMENTALS": "Learn the fundamentals", "PROJECTS": "Build practical projects", "JOB_ROLE": "Prepare for a job role", "NEW_DOMAIN": "Move into a new domain", "CURRENT_ROLE": "Improve skills for my current role", "PRODUCTION": "Build a production application", "INTERVIEWS": "Prepare for interviews", "PORTFOLIO": "Create a portfolio", "ADVANCED": "Understand advanced concepts", "GAPS": "Fill skill gaps"}
LEVELS = {"BEGINNER": "Complete beginner", "FAMILIAR": "Some familiarity", "FOUNDATIONS": "Comfortable with fundamentals", "INTERMEDIATE": "Intermediate practitioner", "ADVANCED": "Advanced practitioner"}
BUDGET_TYPES = {"FREE": Decimal("0"), "UNDER_50": Decimal("50"), "UNDER_100": Decimal("100"), "UNDER_200": Decimal("200"), "FLEXIBLE": None, "CUSTOM": None}
PATH_LENGTHS = {"FOCUSED": (3, 4), "BALANCED": (6, 7), "EXTENDED": (8, 8), "DEEP": (8, 8), "AUTO": (3, 8)}


class LearningPathInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary_domain: str
    secondary_domains: list[str] = Field(default_factory=list, max_length=MAX_SECONDARY_DOMAINS)
    goals: list[str] = Field(min_length=1, max_length=MAX_LEARNING_GOALS)
    level: str
    weekly_hours: int = Field(ge=1, le=40)
    target_weeks: int | None = Field(default=None, ge=1, le=52)
    budget_type: Literal["FREE", "UNDER_50", "UNDER_100", "UNDER_200", "FLEXIBLE", "CUSTOM"] = "FLEXIBLE"
    budget_scope: Literal["PATH", "COURSE"] = "PATH"
    budget_amount: Decimal | None = Field(default=None, ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    path_length: Literal["FOCUSED", "BALANCED", "EXTENDED", "DEEP", "AUTO"] = "AUTO"
    requested_course_count: int = Field(default=4, ge=MIN_PATH_COURSES, le=MAX_PATH_COURSES)

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_input(cls, values):
        values = dict(values or {})
        if "goals" not in values and values.get("goal"):
            values["goals"] = [values.pop("goal")]
        else:
            values.pop("goal", None)
        for key in ("learning_preferences", "format_preferences", "format_preference", "prior_skills", "optional_instruction", "quick_instructions"):
            values.pop(key, None)
        legacy_path = values.get("path_length")
        if legacy_path in {"QUICK", "STANDARD"}:
            values["path_length"] = "FOCUSED" if legacy_path == "QUICK" else "BALANCED"
        if values.get("path_length") in {"FOCUSED", "BALANCED", "EXTENDED", "DEEP"}:
            values["requested_course_count"] = {"FOCUSED": 4, "BALANCED": 7, "EXTENDED": 8, "DEEP": 8}[values["path_length"]]
        elif "requested_course_count" not in values:
            values["requested_course_count"] = 4
        if "selected_domains" in values:
            selected = [item for item in values.pop("selected_domains") if item]
            if not values.get("primary_domain"):
                values["primary_domain"], values["secondary_domains"] = (selected[0] if selected else ""), selected[1:]
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
