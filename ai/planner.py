"""AI planner for multi-file code changes."""

import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from ai.client import XAIClient
from ai.prompts import build_plan_prompt, PLAN_SCHEMA
from ai.router import ModelRouter, TaskType
from core.config import get_config


@dataclass
class PlanStep:
    """A single step in the plan."""
    file: str
    intent: str  # "modify", "create", "delete", "rename"
    explanation: str = ""
    constraints: Optional[Dict[str, Any]] = None
    depends_on: Optional[List[int]] = None


@dataclass
class Plan:
    """A complete plan for multi-file changes."""
    title: str
    rationale: str
    steps: List[PlanStep]
    created_at: float
    plan_id: str

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "title": self.title,
            "rationale": self.rationale,
            "steps": [
                {
                    "file": step.file,
                    "intent": step.intent,
                    "explanation": step.explanation,
                    "constraints": step.constraints,
                    "depends_on": step.depends_on
                }
                for step in self.steps
            ],
            "created_at": self.created_at,
            "plan_id": self.plan_id
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'Plan':
        """Create from dictionary."""
        steps = [
            PlanStep(
                file=step_data["file"],
                intent=step_data["intent"],
                explanation=step_data.get("explanation", ""),
                constraints=step_data.get("constraints"),
                depends_on=step_data.get("depends_on")
            )
            for step_data in data["steps"]
        ]
        return cls(
            title=data["title"],
            rationale=data["rationale"],
            steps=steps,
            created_at=data.get("created_at", time.time()),
            plan_id=data.get("plan_id", f"plan_{int(time.time())}")
        )


class AIPlanner:
    """Generates and manages AI plans for multi-file changes."""

    def __init__(self):
        self.client = XAIClient()
        self.router = ModelRouter()
        self.config = get_config()
        self.plans_dir = Path.cwd() / ".cli_ai_coder" / "plans"
        self.plans_dir.mkdir(parents=True, exist_ok=True)

    def generate_plan(self, goal: str, repo_hints: Optional[Dict[str, Any]] = None) -> Optional[Plan]:
        """
        Generate a plan for the given goal.

        Args:
            goal: High-level description of what to accomplish.
            repo_hints: Optional hints about the repository structure.

        Returns:
            Generated plan or None if failed.
        """
        # Build prompt
        messages = build_plan_prompt(goal, repo_hints or {})

        # Choose model (prefer reasoning for complex plans)
        lines = 100  # Estimate for planning
        model = self.router.choose_model(lines, 1, task_type=TaskType.REFACTOR)
        temperature = 0.1  # Low temperature for structured output

        # Call AI
        response = self.client.complete_chat(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=2000
        )

        if not response:
            return None

        # Parse and validate JSON
        try:
            plan_data = json.loads(response)
            validated_data = self._validate_and_repair_plan(plan_data, goal)
            if validated_data:
                plan = Plan.from_dict(validated_data)
                self._save_plan(plan)
                return plan
        except json.JSONDecodeError:
            # Try to repair invalid JSON
            repaired = self._repair_json_response(response, goal)
            if repaired:
                plan = Plan.from_dict(repaired)
                self._save_plan(plan)
                return plan

        return None

    def _validate_and_repair_plan(self, plan_data: Dict, goal: str) -> Optional[Dict]:
        """
        Validate plan against schema and attempt repairs.

        Args:
            plan_data: Raw plan data from AI.
            goal: Original goal for context.

        Returns:
            Validated plan data or None.
        """
        # Basic validation
        if not isinstance(plan_data, dict):
            return None

        # Add missing required fields with defaults
        if "title" not in plan_data:
            plan_data["title"] = f"Plan for {goal}"
        if "rationale" not in plan_data:
            plan_data["rationale"] = f"Generated plan to accomplish: {goal}"
        if "steps" not in plan_data:
            plan_data["steps"] = [{"file": "example.py", "intent": "modify", "explanation": "Example step"}]

        # Validate steps
        if not isinstance(plan_data["steps"], list) or len(plan_data["steps"]) == 0:
            plan_data["steps"] = [{"file": "example.py", "intent": "modify", "explanation": "Example step"}]

        for step in plan_data["steps"]:
            if not isinstance(step, dict):
                step = {"file": "example.py", "intent": "modify", "explanation": "Fixed step"}
            if "file" not in step:
                step["file"] = "example.py"
            if "intent" not in step:
                step["intent"] = "modify"
            if step["intent"] not in ["modify", "create", "delete", "rename"]:
                step["intent"] = "modify"

        # Add metadata
        plan_data["created_at"] = time.time()
        plan_data["plan_id"] = f"plan_{int(time.time())}"

        return plan_data

    def _repair_plan_structure(self, plan_data: Dict, goal: str) -> Optional[Dict]:
        """
        Attempt to repair malformed plan structure.

        Args:
            plan_data: Malformed plan data.
            goal: Original goal.

        Returns:
            Repaired plan data or None.
        """
        # Build repair prompt
        repair_prompt = f"""
The following plan JSON is malformed. Please repair it to match this schema:

{json.dumps(PLAN_SCHEMA, indent=2)}

Original goal: {goal}
Malformed plan: {json.dumps(plan_data, indent=2)}

Return only valid JSON matching the schema.
"""

        messages = [
            {"role": "system", "content": "You are a JSON repair assistant. Return only valid JSON."},
            {"role": "user", "content": repair_prompt}
        ]

        response = self.client.complete_chat(
            model="grok-code-fast-1",  # Use fast model for repair
            messages=messages,
            temperature=0.1,
            max_tokens=1000
        )

        if response:
            try:
                return json.loads(response)
            except json.JSONDecodeError:
                pass

        return None

    def _repair_json_response(self, response: str, goal: str) -> Optional[Dict]:
        """
        Attempt to repair malformed JSON response.

        Args:
            response: Raw AI response.
            goal: Original goal.

        Returns:
            Repaired plan data or None.
        """
        repair_prompt = f"""
The following response is not valid JSON. Please extract and repair it to match this schema:

{json.dumps(PLAN_SCHEMA, indent=2)}

Original goal: {goal}
Invalid response: {response}

Return only valid JSON matching the schema.
"""

        messages = [
            {"role": "system", "content": "You are a JSON repair assistant. Return only valid JSON."},
            {"role": "user", "content": repair_prompt}
        ]

        repair_response = self.client.complete_chat(
            model="grok-code-fast-1",
            messages=messages,
            temperature=0.1,
            max_tokens=1000
        )

        if repair_response:
            try:
                return json.loads(repair_response)
            except json.JSONDecodeError:
                pass

        return None

    def _save_plan(self, plan: Plan) -> None:
        """Save plan to disk."""
        plan_file = self.plans_dir / f"{plan.plan_id}.json"
        try:
            with open(plan_file, 'w', encoding='utf-8') as f:
                json.dump(plan.to_dict(), f, indent=2)
        except (OSError, IOError):
            pass  # Continue without saving

    def load_plan(self, plan_id: str) -> Optional[Plan]:
        """Load plan from disk."""
        plan_file = self.plans_dir / f"{plan_id}.json"
        if not plan_file.exists():
            return None

        try:
            with open(plan_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return Plan.from_dict(data)
        except (json.JSONDecodeError, OSError, IOError, KeyError):
            return None

    def list_plans(self) -> List[Dict[str, Any]]:
        """List all saved plans."""
        plans = []
        if not self.plans_dir.exists():
            return plans

        for plan_file in self.plans_dir.glob("*.json"):
            try:
                with open(plan_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                plans.append({
                    "id": data.get("plan_id"),
                    "title": data.get("title", "Untitled"),
                    "created_at": data.get("created_at", 0),
                    "steps_count": len(data.get("steps", []))
                })
            except (json.JSONDecodeError, OSError, IOError):
                continue

        return sorted(plans, key=lambda p: p["created_at"], reverse=True)

    def get_plan_stats(self, plan: Plan) -> Dict[str, int]:
        """Get statistics for a plan."""
        files_affected = len(set(step.file for step in plan.steps))
        steps_by_intent = {}
        for step in plan.steps:
            steps_by_intent[step.intent] = steps_by_intent.get(step.intent, 0) + 1

        return {
            "total_steps": len(plan.steps),
            "files_affected": files_affected,
            "modify_steps": steps_by_intent.get("modify", 0),
            "create_steps": steps_by_intent.get("create", 0),
            "delete_steps": steps_by_intent.get("delete", 0),
            "rename_steps": steps_by_intent.get("rename", 0)
        }