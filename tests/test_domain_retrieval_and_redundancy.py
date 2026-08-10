import pytest
from app.schemas.learning_path import LearningPathInput
from app.services.learning_path_intent import LearningPathIntent


def test_fullstack_devops_retrieval_queries():
    payload = {
        "primary_domain": "FULLSTACK",
        "secondary_domains": ["DEVOPS"],
        "goals": ["FUNDAMENTALS"],
        "level": "INTERMEDIATE",
        "weekly_hours": 10,
        "path_length": "EXTENDED",
    }
    inp = LearningPathInput.model_validate(payload)
    intent = LearningPathIntent.from_input(inp)
    queries = dict(intent.retrieval_queries())

    assert "primary_domain" in queries
    assert "secondary_domain" in queries
    assert "goals" in queries
    assert "preferences" not in queries

    sec_q = queries["secondary_domain"]
    assert "DevOps" in sec_q
    assert "ci/cd" in sec_q.lower() or "containers" in sec_q.lower() or "devops" in sec_q.lower()

    forbidden = ["accessibility", "design systems", "user experience", "interaction design"]
    for term in forbidden:
        assert term not in sec_q.lower(), f"Found hardcoded UX term '{term}' in DevOps query"


def test_generative_ai_agentic_ai_retrieval_queries():
    payload = {
        "primary_domain": "GENERATIVE_AI",
        "secondary_domains": ["AGENTIC_AI"],
        "goals": ["FUNDAMENTALS"],
        "level": "INTERMEDIATE",
        "weekly_hours": 10,
        "path_length": "BALANCED",
    }
    inp = LearningPathInput.model_validate(payload)
    intent = LearningPathIntent.from_input(inp)
    queries = dict(intent.retrieval_queries())

    sec_q = queries["secondary_domain"]
    assert "Agentic AI" in sec_q
    assert "agent" in sec_q.lower() or "orchestration" in sec_q.lower()


def test_frontend_ui_ux_retrieval_queries():
    payload = {
        "primary_domain": "FRONTEND",
        "secondary_domains": ["UX"],
        "goals": ["FUNDAMENTALS"],
        "level": "INTERMEDIATE",
        "weekly_hours": 10,
        "path_length": "BALANCED",
    }
    inp = LearningPathInput.model_validate(payload)
    intent = LearningPathIntent.from_input(inp)
    queries = dict(intent.retrieval_queries())

    sec_q = queries["secondary_domain"]
    assert "UI/UX Design" in sec_q
    assert "ux" in sec_q.lower() or "design" in sec_q.lower()
