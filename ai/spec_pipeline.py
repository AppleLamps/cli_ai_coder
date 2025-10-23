"""Spec→Tests→Code pipeline for iterative development."""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum

from ai.client import XAIClient
from ai.prompts import build_spec_generation_prompt, build_test_generation_prompt, build_code_generation_prompt
from ai.router import ModelRouter, TaskType
from core.config import get_config

logger = logging.getLogger(__name__)


class PipelineStage(Enum):
    """Pipeline execution stages."""
    SPEC = "spec"
    TESTS = "tests"
    CODE = "code"
    VERIFY = "verify"


@dataclass
class Spec:
    """Specification for implementation."""
    title: str
    description: str
    requirements: List[str]
    constraints: Dict[str, Any]
    acceptance_criteria: List[str]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "title": self.title,
            "description": self.description,
            "requirements": self.requirements,
            "constraints": self.constraints,
            "acceptance_criteria": self.acceptance_criteria
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Spec':
        """Create from dictionary."""
        return cls(
            title=data["title"],
            description=data["description"],
            requirements=data.get("requirements", []),
            constraints=data.get("constraints", {}),
            acceptance_criteria=data.get("acceptance_criteria", [])
        )


@dataclass
class TestSuite:
    """Generated test suite."""
    files: Dict[str, str]  # filename -> test code
    coverage_goals: List[str]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "files": self.files,
            "coverage_goals": self.coverage_goals
        }


@dataclass
class Implementation:
    """Code implementation."""
    files: Dict[str, str]  # filename -> code
    changes_summary: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "files": self.files,
            "changes_summary": self.changes_summary
        }


SPEC_SCHEMA = {
    "type": "object",
    "required": ["title", "description"],
    "properties": {
        "title": {"type": "string", "minLength": 3},
        "description": {"type": "string"},
        "requirements": {
            "type": "array",
            "items": {"type": "string"}
        },
        "constraints": {"type": "object"},
        "acceptance_criteria": {
            "type": "array",
            "items": {"type": "string"}
        }
    }
}


class SpecPipeline:
    """Pipeline for spec→tests→code development."""

    def __init__(self, client: XAIClient, router: ModelRouter):
        self.client = client
        self.router = router
        self.config = get_config()

    def generate_spec(self, user_description: str, context: Optional[Dict[str, Any]] = None) -> Spec:
        """
        Generate a detailed specification from user description.

        Args:
            user_description: Natural language description of what to implement.
            context: Optional context about existing codebase.

        Returns:
            Generated specification.
        """
        messages = build_spec_generation_prompt(user_description, context)

        model = self.router.choose_model(
            input_lines=len(user_description.split('\n')),
            num_files=0,
            needs_planning=True
        )

        response = self.client.complete_chat(
            model=model,
            messages=messages,
            temperature=self.router.get_temperature(model),
            task_type="spec_generation"
        )

        try:
            spec_data = json.loads(response.strip())
            return Spec.from_dict(spec_data)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse spec JSON: {e}")
            raise ValueError(f"Invalid spec response: {response}")

    def generate_tests(self, spec: Spec, existing_code: Optional[Dict[str, str]] = None) -> TestSuite:
        """
        Generate comprehensive test suite from specification.

        Args:
            spec: The specification to test.
            existing_code: Optional existing code to understand patterns.

        Returns:
            Generated test suite.
        """
        messages = build_test_generation_prompt(spec.to_dict(), existing_code)

        model = self.router.choose_model(
            input_lines=len(spec.description.split('\n')),
            num_files=len(existing_code) if existing_code else 0,
            task_type=TaskType.ADD_TESTS
        )

        response = self.client.complete_chat(
            model=model,
            messages=messages,
            temperature=self.router.get_temperature(model),
            task_type="test_generation"
        )

        try:
            test_data = json.loads(response.strip())
            return TestSuite(
                files=test_data.get("files", {}),
                coverage_goals=test_data.get("coverage_goals", [])
            )
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse test JSON: {e}")
            raise ValueError(f"Invalid test response: {response}")

    def generate_code(self, spec: Spec, test_suite: TestSuite, existing_code: Optional[Dict[str, str]] = None) -> Implementation:
        """
        Generate implementation code that passes the tests.

        Args:
            spec: The specification to implement.
            test_suite: The test suite to satisfy.
            existing_code: Optional existing code to integrate with.

        Returns:
            Code implementation.
        """
        messages = build_code_generation_prompt(spec.to_dict(), test_suite.to_dict(), existing_code)

        model = self.router.choose_model(
            input_lines=len(spec.description.split('\n')),
            num_files=len(existing_code) if existing_code else 1,
            needs_planning=True
        )

        response = self.client.complete_chat(
            model=model,
            messages=messages,
            temperature=self.router.get_temperature(model),
            task_type="code_generation"
        )

        try:
            impl_data = json.loads(response.strip())
            return Implementation(
                files=impl_data.get("files", {}),
                changes_summary=impl_data.get("changes_summary", "")
            )
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse implementation JSON: {e}")
            raise ValueError(f"Invalid implementation response: {response}")

    def run_pipeline(
        self,
        user_description: str,
        context: Optional[Dict[str, Any]] = None,
        verify_tests: bool = True
    ) -> Tuple[Spec, TestSuite, Implementation]:
        """
        Run the complete spec→tests→code pipeline.

        Args:
            user_description: What to implement.
            context: Optional codebase context.
            verify_tests: Whether to run tests after implementation.

        Returns:
            Tuple of (spec, tests, implementation).
        """
        logger.info(f"Starting pipeline for: {user_description}")

        # Stage 1: Generate spec
        logger.info("Generating specification...")
        spec = self.generate_spec(user_description, context)

        # Stage 2: Generate tests
        logger.info("Generating test suite...")
        test_suite = self.generate_tests(spec, context)

        # Stage 3: Generate code
        logger.info("Generating implementation...")
        implementation = self.generate_code(spec, test_suite, context)

        # Stage 4: Verify (optional)
        if verify_tests and self.config.pipeline_verify_tests:
            logger.info("Verifying implementation with tests...")
            # TODO: Implement test verification
            pass

        logger.info("Pipeline completed successfully")
        return spec, test_suite, implementation

    def iterative_refine(
        self,
        initial_spec: Spec,
        feedback: str,
        current_tests: Optional[TestSuite] = None,
        current_impl: Optional[Implementation] = None
    ) -> Tuple[Spec, TestSuite, Implementation]:
        """
        Iteratively refine the spec, tests, and implementation based on feedback.

        Args:
            initial_spec: Current specification.
            feedback: User feedback for refinement.
            current_tests: Current test suite.
            current_impl: Current implementation.

        Returns:
            Refined spec, tests, and implementation.
        """
        # This would implement iterative refinement logic
        # For now, regenerate based on feedback
        refined_description = f"Original: {initial_spec.description}\n\nFeedback: {feedback}"

        # Regenerate with feedback incorporated
        return self.run_pipeline(refined_description)