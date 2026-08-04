import argparse
import asyncio
from datetime import datetime, timezone
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from decimal import Decimal

from sqlalchemy import delete, select

from app.constants import COURSE_CATEGORIES, DIFFICULTIES
from app.database import async_session_maker
from app.models import ActivityEvent, Course, VectorOutbox
from app.repositories.vector_outbox import create as create_outbox
from app.services.catalog_service import VECTOR_FIELDS, apply_course_record

SEED_COURSES = [
    {"title": "Introduction to Agentic AI", "slug": "introduction-to-agentic-ai", "category": "Agentic AI", "difficulty": "BEGINNER", "tags": ["agents", "foundations", "ai workflows"], "short_description": "Learn how goal-driven AI systems plan, call tools, and verify results.", "description": "Build a practical mental model for agent loops, tool boundaries, and reliable task completion. You will leave with small patterns for evaluating agent behavior without treating every prompt as magic.", "instructor": "Maya Iyer", "duration_minutes": 75, "price": Decimal("0.00")},
    {"title": "Advanced LangGraph Workflows", "slug": "advanced-langgraph-workflows", "category": "Agentic AI", "difficulty": "ADVANCED", "tags": ["langgraph", "state machines", "tool calling", "workflow reliability"], "short_description": "Design durable stateful workflows for tool-using AI applications.", "description": "Explore graph state, checkpoints, branching, and failure recovery through a production-shaped workflow. The course focuses on control flow and observability rather than generated recommendations.", "instructor": "Jon Bell", "duration_minutes": 240, "price": Decimal("79.00")},
    {"title": "Production RAG Systems", "slug": "production-rag-systems", "category": "Artificial Intelligence", "difficulty": "ADVANCED", "tags": ["rag", "retrieval", "evaluation", "grounding"], "short_description": "Move retrieval-augmented generation from prototype to dependable service.", "description": "Cover chunking decisions, retrieval evaluation, citation quality, and operational safeguards. Exercises turn a simple search-and-answer flow into a system that can be measured and improved.", "instructor": "Leena Das", "duration_minutes": 300, "price": Decimal("99.00")},
    {"title": "Multi-Agent Orchestration", "slug": "multi-agent-orchestration", "category": "Agentic AI", "difficulty": "ADVANCED", "tags": ["multi-agent", "orchestration", "delegation", "reliability"], "short_description": "Coordinate specialized agents with explicit contracts and bounded handoffs.", "description": "Learn when multiple agents add value, how to keep their responsibilities narrow, and how to test delegation paths. The examples emphasize predictable interfaces, budgets, and failure handling.", "instructor": "Owen Carter", "duration_minutes": 210, "price": Decimal("89.00")},
    {"title": "Python for Beginners", "slug": "python-for-beginners", "category": "Python", "difficulty": "BEGINNER", "tags": ["python", "programming", "fundamentals", "practice"], "short_description": "Start programming with clear Python examples and useful small projects.", "description": "Learn variables, functions, collections, files, and testing by building a set of approachable command-line tools. Each lesson adds one durable programming habit.", "instructor": "Ravi Shah", "duration_minutes": 180, "price": Decimal("0.00")},
    {"title": "FastAPI Backend Development", "slug": "fastapi-backend-development", "category": "Web Development", "difficulty": "INTERMEDIATE", "tags": ["fastapi", "apis", "python", "async"], "short_description": "Build typed, tested APIs with FastAPI and asynchronous Python.", "description": "Create a maintainable service with request validation, dependency injection, database sessions, and practical error handling. The final project is a small catalog API ready for deployment review.", "instructor": "Asha Menon", "duration_minutes": 220, "price": Decimal("59.00")},
    {"title": "Vector Databases in Practice", "slug": "vector-databases-in-practice", "category": "Artificial Intelligence", "difficulty": "INTERMEDIATE", "tags": ["vectors", "qdrant", "similarity search", "metadata filters"], "short_description": "Understand vector indexing, payloads, and reliable similarity search.", "description": "Work through collection design, point identifiers, metadata filtering, and synchronization concerns using realistic catalog data. You will also learn why vector state needs an operational source of truth.", "instructor": "Nikhil Rao", "duration_minutes": 165, "price": Decimal("69.00")},
    {"title": "Prompt Engineering Fundamentals", "slug": "prompt-engineering-fundamentals", "category": "Artificial Intelligence", "difficulty": "BEGINNER", "tags": ["prompting", "evaluation", "structured output"], "short_description": "Write clearer prompts and evaluate outputs with repeatable methods.", "description": "Learn task framing, examples, constraints, and structured outputs without relying on trial and error alone. Practical exercises show how to turn vague requests into testable behaviors.", "instructor": "Sara Kim", "duration_minutes": 100, "price": Decimal("29.00")},
    {"title": "AI Application Observability", "slug": "ai-application-observability", "category": "DevOps", "difficulty": "INTERMEDIATE", "tags": ["observability", "metrics", "tracing", "ai operations"], "short_description": "Instrument AI application behavior so reliability issues become diagnosable.", "description": "Define useful request metrics, capture safe operational context, and connect failures to user-visible outcomes. The course treats logs and traces as product infrastructure, not an afterthought.", "instructor": "Priya Nair", "duration_minutes": 150, "price": Decimal("65.00")},
    {"title": "Building Secure AI Products", "slug": "building-secure-ai-products", "category": "Cybersecurity", "difficulty": "ADVANCED", "tags": ["security", "threats", "ai products", "privacy"], "short_description": "Design AI product boundaries that protect users, data, and operations.", "description": "Map trust boundaries, constrain tool access, validate inputs, and plan incident responses for AI-enabled products. The material connects familiar application security practices to new model-driven risks.", "instructor": "Elena Torres", "duration_minutes": 240, "price": Decimal("85.00")},
    {"title": "Design Systems That Scale", "slug": "design-systems-that-scale", "category": "UI/UX Design", "difficulty": "INTERMEDIATE", "tags": ["design systems", "components", "tokens", "collaboration"], "short_description": "Create maintainable design systems that help teams ship consistently.", "description": "Explore component boundaries, tokens, documentation, and contribution workflows. You will practice making a system easier to use without turning every visual decision into bureaucracy.", "instructor": "Tara Joseph", "duration_minutes": 140, "price": Decimal("49.00")},
    {"title": "Reliable Data Pipelines", "slug": "reliable-data-pipelines", "category": "Data Science", "difficulty": "INTERMEDIATE", "tags": ["data pipelines", "quality", "scheduling", "etl"], "short_description": "Build data pipelines that are observable, repeatable, and safe to rerun.", "description": "Learn idempotent loads, data quality checks, backfills, and operational ownership through a small analytics pipeline. Every exercise addresses what happens when a step fails halfway through.", "instructor": "Mateo Silva", "duration_minutes": 195, "price": Decimal("64.00")},
    {"title": "Accessible Interface Craft", "slug": "accessible-interface-craft", "category": "UI/UX Design", "difficulty": "BEGINNER", "tags": ["accessibility", "semantic html", "keyboard", "inclusive design"], "short_description": "Build interfaces that remain understandable and usable for more people.", "description": "Practice semantic markup, keyboard navigation, focus states, forms, and readable content. The course uses small interface audits to make accessibility a normal delivery habit.", "instructor": "Nora Williams", "duration_minutes": 120, "price": Decimal("0.00")},
    {"title": "Applied Forecasting", "slug": "applied-forecasting", "category": "Machine Learning", "difficulty": "INTERMEDIATE", "tags": ["forecasting", "time series", "features", "evaluation"], "short_description": "Make useful forecasts while respecting time, seasonality, and uncertainty.", "description": "Build a forecasting workflow from baseline models through evaluation and communicating uncertainty. Examples show why a simple, well-tested forecast can outperform a complex model in practice.", "instructor": "Ishan Kapoor", "duration_minutes": 210, "price": Decimal("74.00")},
    {"title": "Practical Feature Engineering", "slug": "practical-feature-engineering", "category": "Machine Learning", "difficulty": "INTERMEDIATE", "tags": ["features", "machine learning", "data preparation", "leakage"], "short_description": "Turn messy source data into features that support honest model evaluation.", "description": "Work through temporal features, categorical data, missing values, and leakage checks. The emphasis is on repeatable transformations that survive the move from notebook to pipeline.", "instructor": "Kavya Singh", "duration_minutes": 175, "price": Decimal("62.00")},
    {"title": "Threat Modeling for Builders", "slug": "threat-modeling-for-builders", "category": "Cybersecurity", "difficulty": "BEGINNER", "tags": ["threat modeling", "security design", "risk", "web"], "short_description": "Find and prioritize security risks before they become expensive incidents.", "description": "Use simple threat-modeling diagrams, abuse cases, and risk scoring to review a real application. You will learn a lightweight practice that fits into normal product planning.", "instructor": "Diego Morales", "duration_minutes": 90, "price": Decimal("25.00")},
    {"title": "Product Discovery Fieldwork", "slug": "product-discovery-fieldwork", "category": "Product Management", "difficulty": "BEGINNER", "tags": ["discovery", "user research", "product strategy"], "short_description": "Turn customer conversations into clearer product decisions.", "description": "Plan interviews, separate observations from assumptions, and synthesize evidence into product opportunities. The exercises focus on learning quickly without pretending every request is a roadmap commitment.", "instructor": "Meera Patel", "duration_minutes": 110, "price": Decimal("35.00")},
    {"title": "Secure Authentication Foundations", "slug": "secure-authentication-foundations", "category": "Cybersecurity", "difficulty": "INTERMEDIATE", "tags": ["authentication", "sessions", "csrf", "passwords"], "short_description": "Implement authentication flows with safer password and session practices.", "description": "Review password hashing, session cookies, CSRF defenses, authorization checks, and account lifecycle concerns. The examples are framework-neutral but concrete enough to apply immediately.", "instructor": "Fatima Ahmed", "duration_minutes": 160, "price": Decimal("55.00")},
    {"title": "Modern SQL for Analysts", "slug": "modern-sql-for-analysts", "category": "Data Science", "difficulty": "BEGINNER", "tags": ["sql", "analytics", "joins", "aggregates"], "short_description": "Answer business questions with readable, reliable SQL.", "description": "Practice joins, grouping, window functions, and careful filtering against realistic datasets. Each query is shaped around a decision an analyst may need to explain to a teammate.", "instructor": "Arjun Mehta", "duration_minutes": 130, "price": Decimal("39.00")},
    {"title": "Kubernetes Delivery Basics", "slug": "kubernetes-delivery-basics", "category": "DevOps", "difficulty": "INTERMEDIATE", "tags": ["kubernetes", "containers", "deployments", "operations"], "short_description": "Understand the Kubernetes objects that make application delivery repeatable.", "description": "Deploy a small service, configure health checks, manage secrets safely, and inspect rollout behavior. The course explains the operational concepts behind the YAML rather than asking learners to memorize it.", "instructor": "Hugo Martin", "duration_minutes": 190, "price": Decimal("68.00")},
    {"title": "Experiment Design Essentials", "slug": "experiment-design-essentials", "category": "Data Science", "difficulty": "INTERMEDIATE", "tags": ["experiments", "metrics", "causal thinking", "analysis"], "short_description": "Plan product experiments that produce interpretable evidence.", "description": "Define hypotheses, guardrail metrics, samples, and analysis plans before looking at results. You will practice spotting common decision errors in experiments that look convincing at first glance.", "instructor": "Laila Roy", "duration_minutes": 145, "price": Decimal("47.00")},
    {"title": "Cloud Architecture Patterns", "slug": "cloud-architecture-patterns", "category": "Cloud Computing", "difficulty": "ADVANCED", "tags": ["cloud", "architecture", "scalability", "reliability"], "short_description": "Choose cloud architecture patterns with explicit trade-offs.", "description": "Compare queues, caches, databases, and service boundaries through workload-shaped scenarios. The goal is not a universal diagram; it is a better way to reason about reliability, cost, and change.", "instructor": "Victor Chen", "duration_minutes": 225, "price": Decimal("82.00")},
    {"title": "TypeScript for Backend Teams", "slug": "typescript-for-backend-teams", "category": "Web Development", "difficulty": "INTERMEDIATE", "tags": ["typescript", "node", "types", "apis"], "short_description": "Use TypeScript to make backend services clearer and safer to change.", "description": "Learn type modelling, runtime validation, async workflows, and service boundaries through backend examples. The course connects language features to maintenance problems teams actually face.", "instructor": "Rachel Green", "duration_minutes": 170, "price": Decimal("52.00")},
    {"title": "Python Automation Studio", "slug": "python-automation-studio", "category": "Python", "difficulty": "INTERMEDIATE", "tags": ["python", "automation", "cli", "files"], "short_description": "Automate repetitive work with small, dependable Python tools.", "description": "Build scripts for files, APIs, reports, and scheduled jobs while learning practical error handling and logging. The project is intentionally modest: useful automation that someone else can trust.", "instructor": "Sanjay Rao", "duration_minutes": 155, "price": Decimal("44.00")},
    {"title": "Metrics That Drive Decisions", "slug": "metrics-that-drive-decisions", "category": "Business Analytics", "difficulty": "BEGINNER", "tags": ["metrics", "dashboards", "business", "decision making"], "short_description": "Choose metrics that clarify decisions instead of filling dashboards.", "description": "Connect business questions to definitions, dimensions, and review rhythms. Exercises expose vanity metrics and show how a small set of well-owned measures can guide action.", "instructor": "Grace Liu", "duration_minutes": 105, "price": Decimal("32.00")},
    {"title": "Shipping with Event-Driven APIs", "slug": "shipping-with-event-driven-apis", "category": "Web Development", "difficulty": "ADVANCED", "tags": ["events", "apis", "messaging", "idempotency"], "short_description": "Design event-driven APIs that tolerate retries and partial failure.", "description": "Build an event flow with durable delivery, stable identities, and safe consumers. You will learn when an outbox helps and where transactional boundaries should remain explicit.", "instructor": "Noah Brooks", "duration_minutes": 205, "price": Decimal("72.00")},
    {"title": "Visual Storytelling with Data", "slug": "visual-storytelling-with-data", "category": "Data Science", "difficulty": "BEGINNER", "tags": ["data visualization", "storytelling", "charts", "communication"], "short_description": "Make charts that help people understand what the data says.", "description": "Choose visual encodings, remove distracting decoration, and write a clear narrative around evidence. The course uses before-and-after critiques to build a stronger visual editing instinct.", "instructor": "Bea Okafor", "duration_minutes": 115, "price": Decimal("28.00")},
    {"title": "Evaluation-First Machine Learning", "slug": "evaluation-first-machine-learning", "category": "Machine Learning", "difficulty": "ADVANCED", "tags": ["machine learning", "evaluation", "benchmarks", "error analysis"], "short_description": "Improve machine-learning systems by measuring the right failures first.", "description": "Design representative test sets, slice errors, and compare changes with discipline. The material helps teams avoid shipping impressive averages that hide unacceptable behavior.", "instructor": "Yuki Tan", "duration_minutes": 230, "price": Decimal("91.00")},
    {"title": "DevOps Incident Readiness", "slug": "devops-incident-readiness", "category": "DevOps", "difficulty": "INTERMEDIATE", "tags": ["incidents", "runbooks", "on-call", "reliability"], "short_description": "Prepare teams to detect, contain, and learn from service incidents.", "description": "Create practical runbooks, define escalation paths, and run blameless incident reviews. Scenarios focus on reducing confusion during pressure and converting lessons into safer systems.", "instructor": "Thomas Reed", "duration_minutes": 135, "price": Decimal("46.00")},
    {"title": "Responsible AI Product Strategy", "slug": "responsible-ai-product-strategy", "category": "Product Management", "difficulty": "INTERMEDIATE", "tags": ["responsible ai", "product strategy", "risk", "governance"], "short_description": "Make responsible AI trade-offs part of ordinary product strategy.", "description": "Map affected people, define acceptable use, and plan evaluation and escalation before launch. The course gives product teams a practical language for risk without pretending governance is a single checklist.", "instructor": "Amara Williams", "duration_minutes": 150, "price": Decimal("58.00")},
]

from app.data.course_details import get_course_detail

SEED_FIELDS = VECTOR_FIELDS + ("is_featured", "thumbnail_url", "what_you_will_learn", "prerequisites", "target_audience", "tools_used", "estimated_effort", "curriculum", "final_project", "instructor_bio", "faqs")


def _record(definition: dict) -> dict:
    slug = definition["slug"]
    thumbnail_url = f"/static/images/courses/{slug}.png" if slug == "introduction-to-agentic-ai" else f"/static/images/courses/{slug}.svg"
    details = get_course_detail(
        definition["slug"],
        definition["title"],
        definition["category"],
        definition["instructor"],
        definition["description"],
        definition["short_description"],
        definition["tags"],
        definition["duration_minutes"]
    )
    return {
        **definition,
        **details,
        "thumbnail_url": thumbnail_url,
        "currency": "USD",
        "is_featured": definition["slug"] in {"introduction-to-agentic-ai", "production-rag-systems", "python-for-beginners"},
        "is_active": True
    }


SEED_COURSES = [_record(item) for item in SEED_COURSES]


def validate_seed_courses() -> None:
    seen = set()
    for course in SEED_COURSES:
        if course["slug"] in seen or course["category"] not in COURSE_CATEGORIES or course["difficulty"] not in DIFFICULTIES:
            raise ValueError(f"Invalid seed course: {course['slug']}")
        if not 3 <= len(course["tags"]) <= 5 or any(tag != tag.strip().lower() for tag in course["tags"]):
            raise ValueError(f"Invalid seed tags: {course['slug']}")
        seen.add(course["slug"])


validate_seed_courses()


def _changed(course: Course, record: dict) -> bool:
    return any(getattr(course, field) != record[field] for field in SEED_FIELDS)


def _apply(course: Course, record: dict) -> bool:
    return apply_course_record(course, record)


async def main(*, reset: bool = False, sync_existing: bool = False, dry_run: bool = False) -> dict:
    validate_seed_courses()
    sync_existing = sync_existing or dry_run
    report = {"inserted": 0, "changed": 0, "unchanged": 0, "outbox": 0}
    async with async_session_maker() as db:
        if reset:
            await db.execute(delete(ActivityEvent))
            await db.execute(delete(VectorOutbox))
            await db.execute(delete(Course))
        existing = {row.slug: row for row in (await db.scalars(select(Course))).all()}
        for record in SEED_COURSES:
            course = existing.get(record["slug"])
            if course:
                if not sync_existing:
                    report["unchanged"] += 1
                    continue
                if not _changed(course, record):
                    report["unchanged"] += 1
                    continue
                vector_changed = _apply(course, record)
                report["changed"] += 1
                if vector_changed:
                    db.add(create_outbox(course, "UPSERT" if course.is_active else "DELETE", datetime.now(timezone.utc).replace(tzinfo=None)))
                    report["outbox"] += 1
                continue
            course_data = {**record, "tags": list(record["tags"]), "version": 1, "vector_status": "PENDING"}
            course = Course(**course_data)
            db.add(course)
            await db.flush()
            db.add(create_outbox(course, "UPSERT", datetime.now(timezone.utc).replace(tzinfo=None)))
            report["inserted"] += 1
            report["outbox"] += 1
        if dry_run:
            await db.rollback()
        else:
            await db.commit()
    print("Seed report:", ", ".join(f"{key}={value}" for key, value in report.items()))
    return report


def cli() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sync-existing", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--confirm-reset", action="store_true")
    args = parser.parse_args()
    if args.reset and not args.confirm_reset:
        parser.error("--reset is development-only and requires --confirm-reset")
    asyncio.run(main(reset=args.reset, sync_existing=args.sync_existing, dry_run=args.dry_run))


if __name__ == "__main__":
    cli()
