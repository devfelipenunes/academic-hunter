import json
import shutil
import tempfile
from pathlib import Path

import pytest

from academic_hunter import AcademicHunter
from academic_hunter.core.nlp.model_cache import clear_model_cache


@pytest.fixture(autouse=True)
def _reset_model_cache():
    """Drop cached ML models around every test.

    ``core.nlp.model_cache`` holds models in module-level dicts. Without this, a
    model loaded — or mocked — by one test would satisfy the next one, which
    would then pass while never exercising the code it claims to. Autouse at the
    root so the MCP suite and the core suite share one reset rather than each
    growing its own.
    """
    clear_model_cache()
    yield
    clear_model_cache()


@pytest.fixture
def test_config():
    """Returns a minimal test configuration dictionary."""
    return {
        "settings": {
            "title_multiplier": 1.5,
            "score_precision": 1,
            "min_relevance_score": 5.0,
            "start_year": 2021,
            "user_email": "test@example.com"
        },
        "anchors": {},
        "technical_strings": {},
        "technical_weights": {}
    }


@pytest.fixture
def tmp_dir():
    """Provides a temporary directory that is cleaned up after the test."""
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d)


@pytest.fixture
def hunter(test_config, tmp_dir):
    """
    Provides a fully initialized AcademicHunter instance using a temporary
    config file and output directory. Cache is disabled for test isolation.
    """
    config_path = Path(tmp_dir) / "config.json"
    config_path.write_text(json.dumps(test_config))
    return AcademicHunter(config_path=str(config_path), output_dir=tmp_dir, use_cache=False)
