from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from app.models import Course
from app.schemas.learning_path import LearningPathInput
from app.services.form_error_service import friendly_validation_errors
from app.services.learning_path_service import _select_courses
from app.services.recommendation_retrieval_service import RecommendationCandidate
from pydantic import ValidationError


def course(title, category, difficulty, tags, price=0, learn=None):
    return Course(id=str(uuid4()), title=title, slug=title.lower().replace(" ", "-"), short_description=title, description=title, category=category, tags=tags, price=Decimal(str(price)), currency="USD", difficulty=difficulty, instructor="Instructor", duration_minutes=120, is_active=True, what_you_will_learn=learn or tags, prerequisites=[], curriculum=[])


def test_path_input_rejects_unknown_codes_and_custom_budget_without_amount():
    try:
        LearningPathInput(primary_domain="NOPE", goal="PROJECTS", level="BEGINNER", learning_preferences=["PROJECTS"], weekly_hours=5)
        assert False
    except ValueError:
        pass
    with pytest.raises(ValueError):
        LearningPathInput(primary_domain="PYTHON", goal="PROJECTS", level="BEGINNER", learning_preferences=["PROJECTS"], weekly_hours=5, budget_type="CUSTOM")


def test_three_preferences_are_valid_and_four_get_a_friendly_field_error():
    value = LearningPathInput(primary_domain="AGENTIC_AI", goal="PRODUCTION", level="BEGINNER", learning_preferences=["FOUNDATIONS", "DEEP", "PRODUCTION"], weekly_hours=5)
    assert value.learning_preferences == ["FOUNDATIONS", "DEEP", "PRODUCTION"]
    with pytest.raises(ValidationError) as error:
        LearningPathInput(primary_domain="AGENTIC_AI", goal="PRODUCTION", level="BEGINNER", learning_preferences=["FOUNDATIONS", "DEEP", "PRODUCTION", "PROJECTS"], weekly_hours=5)
    friendly = friendly_validation_errors(error.value)
    assert friendly["learning_preferences"] == "Choose up to three learning preferences."
    assert "errors.pydantic.dev" not in str(friendly)


def test_legacy_path_values_remain_readable():
    value = LearningPathInput.model_validate({"primary_domain": "PYTHON", "secondary_domains": ["RAG"], "goal": "PROJECTS", "level": "BEGINNER", "learning_preferences": ["FOUNDATIONS"], "format_preference": "PROJECTS", "path_length": "STANDARD", "weekly_hours": 5})
    assert value.goals == ["PROJECTS"]
    assert value.format_preferences == ["PROJECTS"]
    assert value.path_length == "EXTENDED"
def test_deterministic_path_orders_progression_and_respects_total_budget():
    path_input = LearningPathInput(primary_domain="AGENTIC_AI", goal="PRODUCTION", level="BEGINNER", learning_preferences=["PROJECTS", "PRODUCTION"], weekly_hours=5, budget_type="CUSTOM", budget_amount=Decimal("20"), path_length="STANDARD")
    candidates = [
        RecommendationCandidate(course("Multi-Agent Orchestration", "Agentic AI", "ADVANCED", ["orchestration"], 30)),
        RecommendationCandidate(course("Introduction to Agentic AI", "Agentic AI", "BEGINNER", ["agents"], 0)),
        RecommendationCandidate(course("Prompt Engineering Fundamentals", "Artificial Intelligence", "BEGINNER", ["prompting"], 10)),
        RecommendationCandidate(course("Unrelated Design", "UI/UX Design", "BEGINNER", ["design"], 0)),
    ]
    selected = _select_courses(candidates, path_input, {})
    assert [item.title for item in selected] == ["Introduction to Agentic AI", "Prompt Engineering Fundamentals"]
    assert sum(item.price for item in selected) <= Decimal("20")


def test_path_builder_ui_has_accessible_wizard_and_grounded_roadmap():
    root = Path(__file__).parents[1]
    builder = (root / "app/templates/path_builder/index.html").read_text()
    roadmap = (root / "app/templates/learning_paths/detail.html").read_text()
    assert "Build your personalized path" in builder
    assert "data-domain-search" in builder
    assert 'data-max-learning-preferences="{{ selection_limits.learning_preferences }}"' in builder
    assert builder.count('name="selected_domains"') == 1
    assert "data-choice-group" in builder
    assert "<fieldset" in builder and "aria-live" in builder
    assert "<ol class=\"learning-roadmap\"" in roadmap
    assert "how_it_prepares_next" in roadmap
