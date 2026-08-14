from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_g01() -> Path:
    """Return the path to the minimal HEC-RAS fixture file."""
    return FIXTURES / "sample.g01"
