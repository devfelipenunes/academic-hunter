"""Os quatro leitores de "o último resultado" precisam concordar.

`_latest_run_dir` escolhe pelo carimbo no **nome** do arquivo; `_load_latest_papers`
procura só o CSV; `read_latest_report` usa `ctime` e prefere `RELATORIO_ELITE_*`;
o resource usa `mtime` e aceita **qualquer** `.md`. Quatro critérios para a mesma
pergunta.
"""

import os

import pytest

RUN = "run_20260101_120000"
BASE = 1_700_000_000


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "academic_hunter.interfaces.mcp.tools._utils.get_project_root", lambda: tmp_path
    )
    monkeypatch.setattr(
        "academic_hunter.interfaces.mcp.tools.search.get_project_root", lambda: tmp_path
    )
    return tmp_path


def _run_dir(project):
    """A run directory as the pipeline writes it.

    The manager calls `export_results` and then `generate_prisma_report`, so the
    PRISMA flow is the **last** thing written into the directory.
    """
    run = project / "results" / RUN
    run.mkdir(parents=True)

    elite = run / f"RELATORIO_ELITE_{RUN.removeprefix('run_')}.md"
    elite.write_text("# Elite report\n\nThe findings.", encoding="utf-8")
    prisma = run / f"FLUXO_PRISMA_{RUN.removeprefix('run_')}.md"
    prisma.write_text("# PRISMA flow\n\n```mermaid\ngraph TD\n```", encoding="utf-8")

    os.utime(elite, (BASE, BASE))
    os.utime(prisma, (BASE + 10, BASE + 10))

    (run / f"academic_dataset_{RUN.removeprefix('run_')}.csv").write_text(
        "Title,DOI\nA paper,10.1/x\n", encoding="utf-8"
    )
    return run


async def test_the_resource_returns_the_report_not_the_prisma_flow(project, mock_ctx):
    """Both are `.md` in the same directory, and the PRISMA one is newer.

    A client reading `academic-hunter://reports/latest` to summarise a run was
    handed a Mermaid diagram of the screening counters.
    """
    from academic_hunter.interfaces.mcp.resources import get_latest_report_resource

    _run_dir(project)

    content = await get_latest_report_resource()

    assert "Elite report" in content, f"got the PRISMA flow instead:\n{content[:200]}"


async def test_the_tool_and_the_resource_agree(project, mock_ctx):
    from academic_hunter.interfaces.mcp.resources import get_latest_report_resource
    from academic_hunter.interfaces.mcp.tools.search import read_latest_report

    _run_dir(project)

    from_tool = await read_latest_report(mock_ctx)
    from_resource = await get_latest_report_resource()

    assert "Elite report" in from_tool
    assert "Elite report" in from_resource, (
        "the two readers disagree about which file is the latest report"
    )
