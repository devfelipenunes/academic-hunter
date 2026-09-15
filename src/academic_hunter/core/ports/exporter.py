"""Export port: the contract the pipeline uses to write a run's output."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List


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


def run_dir_for(timestamp: str, output_dir: Path) -> Path:
    """The directory a run writes into, created if needed.

    One rule, in one place, because two parties need it: the exporters decide
    where to write, and the pipeline tells its caller where the report is. Two
    copies of this drifted apart once already, and the path returned to the agent
    pointed at a file that was never there.
    """
    if "test" in str(timestamp).lower():
        return Path(output_dir)
    run_dir = Path(output_dir) / f"run_{timestamp}"
    run_dir.mkdir(exist_ok=True, parents=True)
    return run_dir


class BaseExporter(ABC):
    """Abstract Base Class for exporter plugins.

    Implementations live in ``plugins/exporters``; the pipeline receives the
    list of exporters by injection rather than importing the registry.
    """

    is_prisma = False

    def _get_run_dir(self, timestamp: str, output_dir: Path) -> Path:
        """Returns the output directory for a given run, creating it if needed."""
        return run_dir_for(timestamp, output_dir)

    @abstractmethod
    def export(self, context: ExportContext) -> None:
        pass
