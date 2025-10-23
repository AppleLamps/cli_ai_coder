"""Prompt templates for AI interactions."""

import json
from typing import Dict, List, Optional, Any

PLAN_SCHEMA = {
    "type": "object",
    "required": ["title", "rationale", "steps"],
    "properties": {
        "title": {"type": "string", "minLength": 3},
        "rationale": {"type": "string"},
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["file", "intent"],
                "properties": {
                    "file": {"type": "string"},
                    "intent": {"type": "string", "enum": ["modify", "create", "delete", "rename"]},
                    "explanation": {"type": "string"},
                    "constraints": {"type": "object"},
                    "depends_on": {"type": "array", "items": {"type": "integer"}}
                }
            }
        }
    }
}


TOOL_USE_SYSTEM_PREFACE = (
    "You may call tools to gather repo context (search, read files, run tests). "
    "Use at most 3 calls. Prefer minimal diffs."
)


def build_explain_prompt(filename: str, code: str, question: Optional[str] = None) -> List[Dict[str, str]]:
    """
    Build messages for explaining code.

    Args:
        filename: The filename of the code.
        code: The code content.
        question: Optional specific question about the code.

    Returns:
        List of message dictionaries.
    """
    system_msg = {
        "role": "system",
        "content": TOOL_USE_SYSTEM_PREFACE + " You are a precise senior code assistant. Explain the code concisely with examples when helpful."
    }

    user_content = f"File: {filename}\n\nCode:\n{code}"
    if question:
        user_content += f"\n\nQuestion: {question}"

    user_msg = {
        "role": "user",
        "content": user_content
    }

    return [system_msg, user_msg]


def build_refactor_prompt(filename: str, before: str, constraints: Optional[Dict] = None) -> List[Dict[str, str]]:
    """
    Build messages for refactoring code.

    Args:
        filename: The filename of the code.
        before: The code to refactor.
        constraints: Optional constraints dict (e.g., {"readability": True, "performance": False}).

    Returns:
        List of message dictionaries.
    """
    system_msg = {
        "role": "system",
        "content": TOOL_USE_SYSTEM_PREFACE + " Return only a valid unified diff for the proposed refactor. Keep style consistent; small minimal changes."
    }

    user_content = f"File: {filename}\n\nCode to refactor:\n{before}"

    if constraints:
        constraint_strs = []
        for key, value in constraints.items():
            constraint_strs.append(f"{key}: {value}")
        user_content += f"\n\nConstraints: {', '.join(constraint_strs)}"

    user_msg = {
        "role": "user",
        "content": user_content
    }

    return [system_msg, user_msg]


def build_fix_error_prompt(filename: str, code: str, traceback: str) -> List[Dict[str, str]]:
    """
    Build messages for fixing errors.

    Args:
        filename: The filename of the code.
        code: The code content.
        traceback: The error traceback.

    Returns:
        List of message dictionaries.
    """
    system_msg = {
        "role": "system",
        "content": TOOL_USE_SYSTEM_PREFACE + " Prefer minimal diffs to fix the error. Return a unified diff when code changes are proposed; if no change, explain why."
    }

    user_content = f"File: {filename}\n\nCode:\n{code}\n\nError:\n{traceback}"

    user_msg = {
        "role": "user",
        "content": user_content
    }

    return [system_msg, user_msg]


def build_fix_tests_prompt(context: Dict) -> List[Dict[str, str]]:
    """
    Build messages for fixing failing tests.

    Args:
        context: Context dict with test output, code, etc.

    Returns:
        List of message dictionaries.
    """
    system_msg = {
        "role": "system",
        "content": TOOL_USE_SYSTEM_PREFACE + " Tests are failing. Propose minimal diff to make them pass. Call run_tests() to verify fixes. Return unified diff when code changes are needed."
    }

    user_content = "Fix the failing tests:\n\n"

    if "test_output" in context:
        user_content += f"Test Output:\n{context['test_output']}\n\n"

    if "code" in context:
        user_content += f"Code:\n{context['code']}\n\n"

    user_msg = {
        "role": "user",
        "content": user_content
    }

    return [system_msg, user_msg]


def build_add_tests_prompt(targets: List[str], context: Dict) -> List[Dict[str, str]]:
    """
    Build messages for adding tests.

    Args:
        targets: List of target functions/classes to test.
        context: Context dict with code, existing tests, etc.

    Returns:
        List of message dictionaries.
    """
    system_msg = {
        "role": "system",
        "content": TOOL_USE_SYSTEM_PREFACE + " Generate table-driven tests. If edits needed, output unified diff; otherwise propose new test files with filenames."
    }

    user_content = f"Targets to test: {', '.join(targets)}\n\n"

    if "code" in context:
        user_content += f"Code:\n{context['code']}\n\n"

    if "existing_tests" in context:
        user_content += f"Existing tests:\n{context['existing_tests']}\n\n"

    user_msg = {
        "role": "user",
        "content": user_content
    }

    return [system_msg, user_msg]


def build_plan_prompt(goal: str, repo_hints: Dict[str, Any]) -> List[Dict[str, str]]:
    """
    Build messages for generating a multi-file change plan.

    Args:
        goal: High-level goal description.
        repo_hints: Repository structure hints.

    Returns:
        List of message dictionaries.
    """
    schema_str = json.dumps(PLAN_SCHEMA, indent=2)

    system_msg = {
        "role": "system",
        "content": f"""You are an expert software architect. Generate a structured plan for implementing the user's goal.

Return ONLY valid JSON matching this schema:
{schema_str}

Guidelines:
- Prefer small, focused steps over large changes
- Each step should be implementable independently
- Use depends_on to specify step dependencies (array of step indices)
- Keep explanations concise but clear
- Focus on files that actually need changes"""
    }

    user_content = f"Goal: {goal}\n\n"

    if repo_hints:
        user_content += f"Repository hints:\n{json.dumps(repo_hints, indent=2)}\n\n"

    user_content += "Generate a plan with specific, actionable steps."

    user_msg = {
        "role": "user",
        "content": user_content
    }

    return [system_msg, user_msg]


def build_file_change_prompt(step: Dict, original_text: str, neighbors: Dict, constraints: Optional[Dict] = None) -> List[Dict[str, str]]:
    """
    Build messages for generating file changes for a plan step.

    Args:
        step: Plan step dict.
        original_text: Current file content.
        neighbors: Related files/context.
        constraints: Optional constraints.

    Returns:
        List of message dictionaries.
    """
    system_msg = {
        "role": "system",
        "content": """Generate precise code changes. Return ONLY a unified diff or { "noop": true } if no changes needed.

Diff format requirements:
- Use proper unified diff format with --- and +++ headers
- Include sufficient context lines
- Make minimal, targeted changes
- Preserve existing code style and formatting"""
    }

    user_content = f"Step: {step.get('explanation', 'Implement change')}\n"
    user_content += f"File: {step['file']}\n"
    user_content += f"Intent: {step['intent']}\n\n"

    user_content += f"Current content:\n{original_text}\n\n"

    if neighbors:
        user_content += f"Related context:\n{json.dumps(neighbors, indent=2)}\n\n"

    if constraints:
        user_content += f"Constraints:\n{json.dumps(constraints, indent=2)}\n\n"

    user_msg = {
        "role": "user",
        "content": user_content
    }

    return [system_msg, user_msg]


def build_spec_generation_prompt(user_description: str, context: Optional[Dict[str, Any]] = None) -> List[Dict[str, str]]:
    """
    Build messages for generating a specification from user description.

    Args:
        user_description: Natural language description of what to implement.
        context: Optional context about existing codebase.

    Returns:
        List of message dictionaries.
    """
    schema_str = json.dumps({
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
    }, indent=2)

    system_msg = {
        "role": "system",
        "content": f"""You are an expert product manager and software architect. Generate a detailed specification for implementing the user's request.

Return ONLY valid JSON matching this schema:
{schema_str}

Guidelines:
- Break down the description into specific, testable requirements
- Include technical constraints and assumptions
- Define clear acceptance criteria for completion
- Focus on functional requirements, not implementation details
- Keep requirements atomic and verifiable"""
    }

    user_content = f"User Request: {user_description}\n\n"

    if context:
        user_content += f"Context:\n{json.dumps(context, indent=2)}\n\n"

    user_content += "Generate a comprehensive specification."

    user_msg = {
        "role": "user",
        "content": user_content
    }

    return [system_msg, user_msg]


def build_test_generation_prompt(spec: Dict[str, Any], existing_code: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    """
    Build messages for generating test suite from specification.

    Args:
        spec: The specification dictionary.
        existing_code: Optional existing code patterns.

    Returns:
        List of message dictionaries.
    """
    system_msg = {
        "role": "system",
        "content": """You are an expert QA engineer. Generate comprehensive test suites that thoroughly validate the specification.

Return a JSON object with:
{
  "files": {"filename": "test_code"},
  "coverage_goals": ["goal1", "goal2"]
}

Guidelines:
- Generate unit tests, integration tests, and edge case tests
- Use table-driven tests where appropriate
- Include both positive and negative test cases
- Test error conditions and boundary values
- Follow existing test patterns in the codebase
- Aim for high test coverage of all requirements"""
    }

    user_content = f"Specification:\n{json.dumps(spec, indent=2)}\n\n"

    if existing_code:
        user_content += f"Existing Code Patterns:\n{json.dumps(existing_code, indent=2)}\n\n"

    user_content += "Generate a complete test suite."

    user_msg = {
        "role": "user",
        "content": user_content
    }

    return [system_msg, user_msg]


def build_code_generation_prompt(spec: Dict[str, Any], test_suite: Dict[str, Any], existing_code: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    """
    Build messages for generating implementation code.

    Args:
        spec: The specification dictionary.
        test_suite: The test suite dictionary.
        existing_code: Optional existing code to integrate with.

    Returns:
        List of message dictionaries.
    """
    system_msg = {
        "role": "system",
        "content": """You are an expert software engineer. Generate clean, maintainable code that fully implements the specification and passes all tests.

Return a JSON object with:
{
  "files": {"filename": "code"},
  "changes_summary": "summary of changes"
}

Guidelines:
- Write production-ready, well-documented code
- Follow existing code patterns and style
- Ensure all tests would pass with this implementation
- Handle edge cases and error conditions
- Use appropriate design patterns
- Include necessary imports and dependencies"""
    }

    user_content = f"Specification:\n{json.dumps(spec, indent=2)}\n\n"
    user_content += f"Test Suite:\n{json.dumps(test_suite, indent=2)}\n\n"

    if existing_code:
        user_content += f"Existing Codebase:\n{json.dumps(existing_code, indent=2)}\n\n"

    user_content += "Generate the complete implementation."

    user_msg = {
        "role": "user",
        "content": user_content
    }

    return [system_msg, user_msg]