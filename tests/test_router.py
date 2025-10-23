"""Tests for router module."""

from ai.router import ModelRouter


def test_choose_model_single_file_small():
    """Test choosing model for small single file."""
    router = ModelRouter()
    model = router.choose_model(input_lines=200, num_files=1, needs_planning=False)
    assert model == "grok-code-fast-1"


def test_choose_model_multiple_files():
    """Test choosing model for multiple files."""
    router = ModelRouter()
    model = router.choose_model(input_lines=500, num_files=3, needs_planning=False)
    assert model == "grok-4-fast"


def test_choose_model_needs_planning():
    """Test choosing model when planning is needed."""
    router = ModelRouter()
    model = router.choose_model(input_lines=100, num_files=1, needs_planning=True)
    assert model == "grok-4-fast"


def test_choose_model_complex():
    """Test choosing model for complex task."""
    router = ModelRouter()
    model = router.choose_model(input_lines=1000, num_files=10, needs_planning=True)
    assert model == "grok-4-fast-reasoning"


def test_choose_model_override():
    """Test model override."""
    router = ModelRouter()
    model = router.choose_model(input_lines=100, num_files=1, override_model="custom-model")
    assert model == "custom-model"


def test_get_temperature():
    """Test getting temperature."""
    router = ModelRouter()
    temp = router.get_temperature("grok-code-fast-1")
    assert temp == 0.2
    temp = router.get_temperature("grok-4-fast")
    assert temp == 0.3
    temp = router.get_temperature("grok-4-fast-reasoning")
    assert temp == 0.15


def test_get_temperature_override():
    """Test temperature override."""
    router = ModelRouter()
    temp = router.get_temperature("grok-code-fast-1", override_temp=0.5)
    assert temp == 0.5