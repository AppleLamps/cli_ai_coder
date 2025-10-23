"""Model routing policy for xAI models."""

from enum import Enum
from typing import Optional


class TaskType(Enum):
    """Task types for model routing."""
    EXPLAIN = "explain"
    REFACTOR = "refactor"
    FIX_ERROR = "fix_error"
    ADD_TESTS = "add_tests"
    FIX_TESTS = "fix_tests"


class ModelRouter:
    """Router to choose appropriate xAI model based on task complexity."""

    DEFAULT_MODEL = "grok-code-fast-1"

    # Model input token limits (approximate)
    MODEL_LIMITS = {
        "grok-code-fast-1": 128_000,
        "grok-4-fast": 128_000,
        "grok-4-fast-reasoning": 128_000,
    }

    def choose_model(
        self,
        input_lines: int,
        num_files: int,
        needs_planning: bool = False,
        override_model: Optional[str] = None,
        task_type: Optional[TaskType] = None
    ) -> str:
        """
        Choose the appropriate model based on task characteristics.

        Args:
            input_lines: Number of lines in the input code.
            num_files: Number of files involved.
            needs_planning: Whether the task requires planning and justification.
            override_model: Optional model override.
            task_type: The type of task being performed.

        Returns:
            The chosen model name.
        """
        if override_model:
            return override_model

        # Task-specific routing
        if task_type == TaskType.EXPLAIN:
            return "grok-4-fast"
        elif task_type in (TaskType.REFACTOR, TaskType.FIX_ERROR, TaskType.ADD_TESTS, TaskType.FIX_TESTS):
            if input_lines > 400 or num_files > 1:
                return "grok-4-fast"
            else:
                return "grok-code-fast-1"

        # Default routing logic
        if needs_planning:
            if num_files > 6:
                return "grok-4-fast-reasoning"
            else:
                return "grok-4-fast"
        elif input_lines <= 400 and num_files == 1:
            return "grok-code-fast-1"
        else:
            return "grok-4-fast"

    def get_max_input_tokens(self, model: str) -> int:
        """
        Get the maximum input tokens for the model.

        Args:
            model: The model name.

        Returns:
            Maximum input tokens.
        """
        return self.MODEL_LIMITS.get(model, 128_000)

    def get_temperature(self, model: str, override_temp: Optional[float] = None) -> float:
        """
        Get the recommended temperature for the model.

        Args:
            model: The model name.
            override_temp: Optional temperature override.

        Returns:
            Temperature value.
        """
        if override_temp is not None:
            return override_temp

        temps = {
            "grok-code-fast-1": 0.2,
            "grok-4-fast": 0.3,
            "grok-4-fast-reasoning": 0.15
        }
        return temps.get(model, 0.2)