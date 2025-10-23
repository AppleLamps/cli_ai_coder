"""Tests for spec→tests→code pipeline."""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock

from ai.spec_pipeline import SpecPipeline, Spec, TestSuite, Implementation, PipelineStage
from ai.client import XAIClient
from ai.router import ModelRouter


class TestSpec:
    """Test Spec dataclass."""

    def test_to_dict(self):
        """Test converting spec to dict."""
        spec = Spec(
            title="Test Feature",
            description="A test feature",
            requirements=["req1", "req2"],
            constraints={"python": "3.8+"},
            acceptance_criteria=["works", "tested"]
        )

        expected = {
            "title": "Test Feature",
            "description": "A test feature",
            "requirements": ["req1", "req2"],
            "constraints": {"python": "3.8+"},
            "acceptance_criteria": ["works", "tested"]
        }

        assert spec.to_dict() == expected

    def test_from_dict(self):
        """Test creating spec from dict."""
        data = {
            "title": "Test Feature",
            "description": "A test feature",
            "requirements": ["req1", "req2"],
            "constraints": {"python": "3.8+"},
            "acceptance_criteria": ["works", "tested"]
        }

        spec = Spec.from_dict(data)

        assert spec.title == "Test Feature"
        assert spec.description == "A test feature"
        assert spec.requirements == ["req1", "req2"]
        assert spec.constraints == {"python": "3.8+"}
        assert spec.acceptance_criteria == ["works", "tested"]


class TestTestSuite:
    """Test TestSuite dataclass."""

    def test_to_dict(self):
        """Test converting test suite to dict."""
        suite = TestSuite(
            files={"test_file.py": "test code"},
            coverage_goals=["goal1", "goal2"]
        )

        expected = {
            "files": {"test_file.py": "test code"},
            "coverage_goals": ["goal1", "goal2"]
        }

        assert suite.to_dict() == expected


class TestImplementation:
    """Test Implementation dataclass."""

    def test_to_dict(self):
        """Test converting implementation to dict."""
        impl = Implementation(
            files={"main.py": "code"},
            changes_summary="Added feature"
        )

        expected = {
            "files": {"main.py": "code"},
            "changes_summary": "Added feature"
        }

        assert impl.to_dict() == expected


class TestSpecPipeline:
    """Test SpecPipeline class."""

    @pytest.fixture
    def mock_client(self):
        """Mock AI client."""
        client = Mock(spec=XAIClient)
        return client

    @pytest.fixture
    def mock_router(self):
        """Mock model router."""
        router = Mock(spec=ModelRouter)
        router.choose_model.return_value = "grok-code-fast-1"
        router.get_temperature.return_value = 0.2
        return router

    @pytest.fixture
    def pipeline(self, mock_client, mock_router):
        """Create pipeline with mocks."""
        return SpecPipeline(mock_client, mock_router)

    def test_generate_spec_success(self, pipeline, mock_client):
        """Test successful spec generation."""
        mock_response = json.dumps({
            "title": "Test Feature",
            "description": "A test feature",
            "requirements": ["req1"],
            "constraints": {},
            "acceptance_criteria": ["works"]
        })

        mock_client.complete_chat.return_value = mock_response

        spec = pipeline.generate_spec("implement a test feature")

        assert spec.title == "Test Feature"
        assert spec.description == "A test feature"
        assert spec.requirements == ["req1"]
        mock_client.complete_chat.assert_called_once()

    def test_generate_spec_json_error(self, pipeline, mock_client):
        """Test spec generation with invalid JSON response."""
        mock_client.complete_chat.return_value = "invalid json"

        with pytest.raises(ValueError, match="Invalid spec response"):
            pipeline.generate_spec("implement a test feature")

    def test_generate_tests_success(self, pipeline, mock_client):
        """Test successful test generation."""
        spec = Spec(
            title="Test Feature",
            description="A test feature",
            requirements=["req1"],
            constraints={},
            acceptance_criteria=["works"]
        )

        mock_response = json.dumps({
            "files": {"test_feature.py": "test code"},
            "coverage_goals": ["test req1"]
        })

        mock_client.complete_chat.return_value = mock_response

        suite = pipeline.generate_tests(spec)

        assert suite.files == {"test_feature.py": "test code"}
        assert suite.coverage_goals == ["test req1"]

    def test_generate_code_success(self, pipeline, mock_client):
        """Test successful code generation."""
        spec = Spec(
            title="Test Feature",
            description="A test feature",
            requirements=["req1"],
            constraints={},
            acceptance_criteria=["works"]
        )

        test_suite = TestSuite(
            files={"test_feature.py": "test code"},
            coverage_goals=["test req1"]
        )

        mock_response = json.dumps({
            "files": {"feature.py": "implementation code"},
            "changes_summary": "Added test feature"
        })

        mock_client.complete_chat.return_value = mock_response

        impl = pipeline.generate_code(spec, test_suite)

        assert impl.files == {"feature.py": "implementation code"}
        assert impl.changes_summary == "Added test feature"

    @patch('ai.spec_pipeline.logger')
    def test_run_pipeline_success(self, mock_logger, pipeline, mock_client):
        """Test successful pipeline run."""
        # Mock all the responses
        spec_response = json.dumps({
            "title": "Test Feature",
            "description": "A test feature",
            "requirements": ["req1"],
            "constraints": {},
            "acceptance_criteria": ["works"]
        })

        test_response = json.dumps({
            "files": {"test_feature.py": "test code"},
            "coverage_goals": ["test req1"]
        })

        code_response = json.dumps({
            "files": {"feature.py": "implementation code"},
            "changes_summary": "Added test feature"
        })

        mock_client.complete_chat.side_effect = [spec_response, test_response, code_response]

        spec, tests, impl = pipeline.run_pipeline("implement a test feature")

        assert spec.title == "Test Feature"
        assert tests.files == {"test_feature.py": "test code"}
        assert impl.files == {"feature.py": "implementation code"}

        assert mock_client.complete_chat.call_count == 3

    def test_iterative_refine(self, pipeline, mock_client):
        """Test iterative refinement."""
        initial_spec = Spec(
            title="Initial",
            description="initial desc",
            requirements=[],
            constraints={},
            acceptance_criteria=[]
        )

        # Mock the run_pipeline call - it calls generate_spec, generate_tests, generate_code
        spec_response = json.dumps({
            "title": "Refined Feature",
            "description": "refined desc",
            "requirements": ["req1"],
            "constraints": {},
            "acceptance_criteria": ["works"]
        })

        test_response = json.dumps({
            "files": {"test_feature.py": "test code"},
            "coverage_goals": ["test req1"]
        })

        code_response = json.dumps({
            "files": {"feature.py": "implementation code"},
            "changes_summary": "Added refined feature"
        })

        mock_client.complete_chat.side_effect = [spec_response, test_response, code_response]

        refined_spec, refined_tests, refined_impl = pipeline.iterative_refine(
            initial_spec, "make it better"
        )

        assert refined_spec.title == "Refined Feature"
        # Check that the first call (generate_spec) includes the feedback
        first_call_messages = mock_client.complete_chat.call_args_list[0][1]["messages"]
        user_message = first_call_messages[1]["content"]  # Second message is user message
        assert "Original: initial desc" in user_message
        assert "Feedback: make it better" in user_message


class TestPipelineIntegration:
    """Integration tests for pipeline."""

    @pytest.mark.integration
    def test_pipeline_with_real_client(self):
        """Test pipeline with real client (requires API key)."""
        # This would be a real integration test
        # For now, just ensure the pipeline can be instantiated
        client = XAIClient()
        router = ModelRouter()
        pipeline = SpecPipeline(client, router)

        assert pipeline.client == client
        assert pipeline.router == router

    def test_pipeline_stages_enum(self):
        """Test pipeline stage enum values."""
        assert PipelineStage.SPEC.value == "spec"
        assert PipelineStage.TESTS.value == "tests"
        assert PipelineStage.CODE.value == "code"
        assert PipelineStage.VERIFY.value == "verify"