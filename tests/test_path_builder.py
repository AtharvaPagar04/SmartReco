from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from app.models import Course
from app.schemas.learning_path import LearningPathInput
from app.services.learning_path_service import _select_courses
from app.services.recommendation_retrieval_service import RecommendationCandidate


def course(title, category, difficulty, tags, price=0, learn=None):
    return Course(id=str(uuid4()), title=title, slug=title.lower().replace(" ", "-"), short_description=title, description=title, category=category, tags=tags, price=Decimal(str(price)), currency="USD", difficulty=difficulty, instructor="Instructor", duration_minutes=120, is_active=True, what_you_will_learn=learn or tags, prerequisites=[], curriculum=[])


def test_path_input_accepts_simplified_payload_and_validates_custom_budget():
    with pytest.raises(ValueError):
        LearningPathInput(primary_domain="NOPE", goal="PROJECTS", level="BEGINNER", weekly_hours=5)
    with pytest.raises(ValueError):
        LearningPathInput(primary_domain="PYTHON", goal="PROJECTS", level="BEGINNER", weekly_hours=5, budget_type="CUSTOM")


def test_old_builder_fields_are_ignored_at_legacy_input_boundary():
    value = LearningPathInput.model_validate({
        "primary_domain": "AGENTIC_AI", "goals": ["PRODUCTION"], "level": "BEGINNER", "weekly_hours": 5,
        "learning_preferences": ["FOUNDATIONS"], "format_preferences": ["PROJECTS"], "prior_skills": ["PYTHON"],
        "optional_instruction": "keep it practical", "quick_instructions": ["projects"],
    })
    assert "learning_preferences" not in value.model_dump()
    assert "optional_instruction" not in value.model_dump()


def test_legacy_path_values_remain_readable():
    value = LearningPathInput.model_validate({"primary_domain": "PYTHON", "secondary_domains": ["RAG"], "goal": "PROJECTS", "level": "BEGINNER", "learning_preferences": ["FOUNDATIONS"], "format_preference": "PROJECTS", "path_length": "STANDARD", "weekly_hours": 5})
    assert value.goals == ["PROJECTS"]
    assert value.path_length == "BALANCED"
def test_deterministic_fallback_rejects_ungrounded_domain_drift_and_respects_budget():
    path_input = LearningPathInput(primary_domain="AGENTIC_AI", goal="PRODUCTION", level="BEGINNER", weekly_hours=5, budget_type="CUSTOM", budget_amount=Decimal("20"), path_length="FOCUSED")
    candidates = [
        RecommendationCandidate(course("Multi-Agent Orchestration", "Agentic AI", "ADVANCED", ["orchestration"], 30)),
        RecommendationCandidate(course("Introduction to Agentic AI", "Agentic AI", "BEGINNER", ["agents"], 0)),
        RecommendationCandidate(course("Prompt Engineering Fundamentals", "Artificial Intelligence", "BEGINNER", ["prompting"], 10)),
        RecommendationCandidate(course("Unrelated Design", "UI/UX Design", "BEGINNER", ["design"], 0)),
    ]
    selected = _select_courses(candidates, path_input, {})
    assert [item.title for item in selected] == ["Introduction to Agentic AI"]
    assert sum(item.price for item in selected) <= Decimal("20")


def test_path_builder_ui_has_accessible_wizard_and_grounded_roadmap():
    root = Path(__file__).parents[1]
    builder = (root / "app/templates/path_builder/index.html").read_text()
    roadmap = (root / "app/templates/learning_paths/detail.html").read_text()
    assert "Build your personalized path" in builder
    assert "data-domain-search" in builder
    assert 'data-max-learning-preferences' not in builder
    assert builder.count('data-step="') == 5
    assert "learning_preferences" not in builder
    assert "optional_instruction" not in builder
    assert builder.count('name="selected_domains"') == 1
    assert "data-choice-group" in builder
    assert "<fieldset" in builder and "aria-live" in builder
    assert "<ol class=\"learning-roadmap\"" in roadmap
    assert "how_it_prepares_next" in roadmap


def test_removed_learning_path_pipeline_features_are_not_active():
    root = Path(__file__).parents[1]
    planner = (root / "app/services/learning_path_planner.py").read_text()
    mesh = (root / "app/services/mesh_chat_service.py").read_text()
    validator = (root / "app/services/learning_path_validator.py").read_text()
    assert "preference_fit" not in planner
    assert "learner_instruction" not in mesh
    assert "KNOWN_SKILL_REDUNDANCY" not in validator
