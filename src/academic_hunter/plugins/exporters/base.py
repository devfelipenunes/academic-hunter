import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Any

logger = logging.getLogger("academic_hunter.exporters")


@dataclass
class ExportContext:
    """Encapsulates all data needed by exporters, replacing 8 loose parameters."""
    papers: List[Dict[str, Any]]
    stats: Dict[str, Any]
    settings: Dict[str, Any]
    query_history: List[Dict[str, Any]]
    anchors: Dict[str, List[str]]
    tech_strings: Dict[str, List[str]]
    timestamp: str
    output_dir: Path


class BaseExporter(ABC):
    """Abstract Base Class for exporter plugins."""
    is_prisma = False

    def _get_run_dir(self, timestamp: str, output_dir: Path) -> Path:
        """Returns the output directory for a given run, creating it if needed."""
        if "test" in str(timestamp).lower():
            return output_dir
        run_dir = output_dir / f"run_{timestamp}"
        run_dir.mkdir(exist_ok=True, parents=True)
        return run_dir

    @abstractmethod
    def export(self, context: ExportContext) -> None:
        pass
