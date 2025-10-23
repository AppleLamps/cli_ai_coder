"""Tests for AI planner."""

import json
import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from ai.planner import AIPlanner, Plan, PlanStep, PLAN_SCHEMA


@pytest.fixture
def temp_dir():
    """Create a temporary directory."""
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


@pytest.fixture
def planner(temp_dir):
    """Create a planner instance."""
    with patch('ai.planner.Path') as mock_path:
        mock_path.cwd.return_value = temp_dir
        planner = AIPlanner()
        planner.plans_dir = temp_dir / ".cli_ai_coder" / "plans"
        planner.plans_dir.mkdir(parents=True, exist_ok=True)
        return planner


class TestPlan:
    """Test Plan dataclass."""

    def test_to_dict(self):
        """Test converting plan to dict."""
        step = PlanStep("test.py", "modify", "Test change")
        plan = Plan("Test Plan", "Test rationale", [step], 1234567890, "plan_123")

        data = plan.to_dict()
        assert data["title"] == "Test Plan"
        assert data["rationale"] == "Test rationale"
        assert len(data["steps"]) == 1
        assert data["steps"][0]["file"] == "test.py"

    def test_from_dict(self):
        """Test creating plan from dict."""
        data = {
            "title": "Test Plan",
            "rationale": "Test rationale",
            "steps": [{"file": "test.py", "intent": "modify", "explanation": "Test change"}],
            "created_at": 1234567890,
            "plan_id": "plan_123"
        }

        plan = Plan.from_dict(data)
        assert plan.title == "Test Plan"
        assert plan.rationale == "Test rationale"
        assert len(plan.steps) == 1
        assert plan.steps[0].file == "test.py"


class TestAIPlanner:
    """Test AI planner."""

    def test_init(self, planner, temp_dir):
        """Test initialization."""
        assert planner.plans_dir.exists()
        assert (temp_dir / ".cli_ai_coder" / "plans").exists()

    @patch('ai.planner.XAIClient')
    def test_generate_plan_success(self, mock_client_class, planner):
        """Test successful plan generation."""
        mock_client = MagicMock()
        mock_client.complete_chat.return_value = json.dumps({
            "title": "Test Plan",
            "rationale": "Test rationale",
            "steps": [{"file": "test.py", "intent": "modify", "explanation": "Test change"}]
        })
        mock_client_class.return_value = mock_client

        planner.client = mock_client
        plan = planner.generate_plan("Test goal")

        assert plan is not None
        assert plan.title == "Test Plan"
        assert len(plan.steps) == 1

    @patch('ai.planner.XAIClient')
    def test_generate_plan_invalid_json(self, mock_client_class, planner):
        """Test plan generation with invalid JSON."""
        mock_client = MagicMock()
        mock_client.complete_chat.side_effect = [
            "invalid json",  # First call fails
            json.dumps({    # Repair succeeds
                "title": "Repaired Plan",
                "rationale": "Repaired rationale",
                "steps": [{"file": "test.py", "intent": "modify", "explanation": "Test change"}]
            })
        ]
        mock_client_class.return_value = mock_client

        planner.client = mock_client
        plan = planner.generate_plan("Test goal")

        assert plan is not None
        assert plan.title == "Repaired Plan"

    def test_validate_and_repair_plan_valid(self, planner):
        """Test validation of valid plan."""
        plan_data = {
            "title": "Test Plan",
            "rationale": "Test rationale",
            "steps": [{"file": "test.py", "intent": "modify", "explanation": "Test change"}]
        }

        result = planner._validate_and_repair_plan(plan_data, "Test goal")
        assert result is not None
        assert result["title"] == "Test Plan"
        assert "created_at" in result
        assert "plan_id" in result

    def test_validate_and_repair_plan_invalid(self, planner):
        """Test validation of invalid plan."""
        plan_data = {
            "title": "Test Plan",
            # Missing rationale and steps
        }

        result = planner._validate_and_repair_plan(plan_data, "Test goal")
        # Should attempt repair and return a repaired plan
        assert result is not None
        assert "rationale" in result
        assert "steps" in result
        assert isinstance(result["steps"], list)

    def test_save_and_load_plan(self, planner):
        """Test saving and loading plans."""
        step = PlanStep("test.py", "modify", "Test change")
        plan = Plan("Test Plan", "Test rationale", [step], 1234567890, "plan_123")

        planner._save_plan(plan)

        loaded = planner.load_plan("plan_123")
        assert loaded is not None
        assert loaded.title == "Test Plan"
        assert loaded.plan_id == "plan_123"

    def test_list_plans(self, planner):
        """Test listing plans."""
        # Create a plan file
        plan_data = {
            "title": "Test Plan",
            "rationale": "Test rationale",
            "steps": [{"file": "test.py", "intent": "modify"}],
            "created_at": 1234567890,
            "plan_id": "plan_123"
        }

        plan_file = planner.plans_dir / "plan_123.json"
        with open(plan_file, 'w') as f:
            json.dump(plan_data, f)

        plans = planner.list_plans()
        assert len(plans) == 1
        assert plans[0]["title"] == "Test Plan"
        assert plans[0]["id"] == "plan_123"

    def test_get_plan_stats(self, planner):
        """Test getting plan statistics."""
        steps = [
            PlanStep("test1.py", "modify", "Change 1"),
            PlanStep("test2.py", "create", "Create file"),
            PlanStep("test3.py", "modify", "Change 2"),
            PlanStep("test4.py", "delete", "Delete file")
        ]
        plan = Plan("Test Plan", "Test rationale", steps, 1234567890, "plan_123")

        stats = planner.get_plan_stats(plan)
        assert stats["total_steps"] == 4
        assert stats["files_affected"] == 4
        assert stats["modify_steps"] == 2
        assert stats["create_steps"] == 1
        assert stats["delete_steps"] == 1


def test_plan_schema():
    """Test that PLAN_SCHEMA is valid."""
    assert "type" in PLAN_SCHEMA
    assert PLAN_SCHEMA["type"] == "object"
    assert "required" in PLAN_SCHEMA
    assert "properties" in PLAN_SCHEMA