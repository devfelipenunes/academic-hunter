from .engine import AcademicHunter
from .models import Paper
from .nlp import AcademicScorer
from .infra import SQLiteCache, HunterConfig, SearchState


def get_config():
    """Return a HunterConfig instance (centralized for easy future changes).

    Use this factory instead of importing ``HunterConfig`` directly.
    """
    from .infra.config import HunterConfig as _HunterConfig
    return _HunterConfig()
