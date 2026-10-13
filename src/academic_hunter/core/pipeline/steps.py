"""Pipeline step abstraction — each phase of the SLR pipeline is a class.

Keeps ``manager.py`` focused on orchestration while each step owns its
logic, logging, and testability.
"""

import logging
import math
from abc import ABC, abstractmethod
from typing import Any, Dict, List

from ..fulltext.ingest import ingest_full_text
from ..infra.atomic import write_json_atomically
from ..models.citations import (
    DEFAULT_IMPACT_PERCENTILE,
    citation_signal,
    citation_summary,
    impact_cutoff,
)
from ..models.utils import doi_from_url, paper_order_key
from ..nlp.bm25 import BM25
from ..nlp.fusion import (
    DEFAULT_STRATEGY,
    IMPLEMENTED_STRATEGIES,
    fuse_scores,
    percentile_ranks,
    resolve_weights,
)
from ..nlp.reranker import rerank_config, rerank_scores, rerank_texts
from ..ports.exporter import run_dir_for
from ..ports.vector_store import ChunkStorePort

logger = logging.getLogger("academic_hunter.pipeline")


INCLUSION_KEY = "_kw_score"
"""The signal that decides inclusion, and why it is this one.

A review's included set has to be a property of the papers, not of the run they
were found in. ``Relevance_Score`` is min-max normalised **within the run**, so
adding an anchor, joining a source or simply drawing a different sample moves
every paper's score and changes which ones count as included without a single
paper changing. The first paper is also always exactly 10.0, so the number does
not compare between runs and "10.0" says nothing about the paper.

``_kw_score`` is the weighted tally of the configured domain terms: a
deterministic function of the paper and the weights, which does not move when
the corpus grows. It is what ``min_inclusion_score`` was always meant to gate.
"""


def inclusion_predicate(hunter) -> "tuple[str, float]":
    """The key and the threshold that decide inclusion, as a number.

    One function because two places apply it — this module's rank step counts
    what the threshold removes, and the pipeline removes it — and two copies of a
    predicate is how the counts and the papers stop agreeing.

    The threshold is converted here rather than compared as it arrives, so a
    configuration that writes it as text still compares. A value that is not a
    number at all raises here, at the start of the comparison, instead of
    silently admitting or dropping every paper.
    """
    return INCLUSION_KEY, float(hunter.config.min_inclusion_score())


def _as_number(value: Any) -> float:
    """A signal read as a number, with a missing or unusable one counting as 0."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _score_decimals(settings: Dict[str, Any]) -> int:
    """Decimal places ``Relevance_Score`` is written with.

    The rerank needs this exact number: its lattice is built at the written
    precision, and a finer one would be rounded away along with the order.
    """
    try:
        decimals = int(settings.get("score_precision", 1))
    except (TypeError, ValueError):
        return 1
    return decimals if decimals >= 0 else 1


class PipelineStep(ABC):
    """One phase of the SLR pipeline.

    Subclasses implement ``run()`` and can access the hunter via
    ``self.hunter``.
    """

    def __init__(self, hunter: Any) -> None:
        self.hunter = hunter

    @abstractmethod
    def run(self) -> None:
        """Execute this pipeline step."""


class RecomputeRanksStep(PipelineStep):
    """Compute the reported score by fusing a sparse and a dense signal.

    Two modes, decided by whether the configuration names a **ranking query**.

    **Without a query** (the default), the sparse signal is the domain-term
    count — a weighted tally of the configured anchor and technical terms. It
    answers "does this paper look like the domain?" and never sees a question,
    which is why every strategy measured without one turned out to be
    query-independent and why the best of them depended on the topic rather
    than on the question.

    **With ``settings.ranking_query``**, the sparse signal becomes BM25 over
    that query, computed across the collected papers. Having an actual question
    is what moved nDCG@10 from 0.28 to 0.67 on a hand-judged sample of the
    corpus — far more than any change of scoring rule achieved.

    Fusion (``settings.fusion == "weighted_norm"``, the default)::

        score = (α · minmax(sparse) + β · minmax(emb)) / (α + β) × 10

    with ``α``/``β`` from ``settings.fusion_weights``. Defaults are 0.7 / 0.3
    without a query — the ratio the pipeline's own mode labels always claimed
    and the old formula did not implement — and 1.0 / 0.0 with one, because
    adding the embedding measured monotonically worse there (90/10 0.6558,
    70/30 0.6221, 50/50 0.5638, against 0.6728 for BM25 alone).

    The superseded rule remains available as ``settings.fusion ==
    "rank_geometric"``::

        score = sqrt(rank_sparse × rank_emb) × 10

    Both signals are min-max normalised and combined as a *weighted sum*, so a
    paper strong on one signal is not dragged down by being mid-pack on the
    other — the property the rank-geometric rule lacked.

    **An optional second stage** (``settings.rerank``, off by default) reorders
    the head with a cross-encoder. It lives here rather than in a step of its own
    because of the rule below — a separate step would break the single-writer
    invariant or have to hand its scores back.

    This step is the **sole writer** of ``Relevance_Score``. Ingest records the
    ablation-dependent inclusion score under ``_hybrid_score`` instead, so that
    one key never carries two different scales. Everything downstream — the
    final threshold filter, exporters, PRISMA and the ChromaDB payload — reads
    the value written here.
    """

    def __init__(self, hunter: Any, timestamp: str = "") -> None:
        """``timestamp`` names the run directory the score distribution lands in.

        It is optional so the step can still be driven directly; without it the
        scores are computed exactly as before and only the sidecar is skipped,
        because an empty timestamp would resolve to a directory called ``run_``.
        """
        super().__init__(hunter)
        self.timestamp = timestamp

    def run(self) -> None:
        results = self.hunter.consolidated_results
        if not results:
            return

        papers_list = list(results.values())
        n = len(papers_list)

        kw_list, sem_list, cit_list = [], [], []
        for p in papers_list:
            kw = p.get("_kw_score")
            if kw is None:
                kw = self.hunter.scorer.calculate_score(
                    p.get("Title", ""), p.get("Abstract", ""), p.get("Citations", 0))
                p["_kw_score"] = kw
            kw_list.append(kw)

            sem = p.get("_sem_score")
            if sem is None and self.hunter.semantic_screener is not None:
                sem_config = self.hunter.config.screener_config()
                sem = self.hunter.semantic_screener.evaluate(p, sem_config)
                p["_sem_score"] = round(sem, 4)
            sem_list.append(sem if sem is not None else 0.0)

            citation = p.get("_citation_score")
            if citation is None:
                citation = citation_signal(p.get("Citations"))
                p["_citation_score"] = citation
            cit_list.append(citation)

        strategy = str(self.hunter.settings.get("fusion", DEFAULT_STRATEGY))
        if strategy not in IMPLEMENTED_STRATEGIES:
            logger.warning(
                "Unknown fusion strategy %r; falling back to %r.",
                strategy, DEFAULT_STRATEGY,
            )
            strategy = DEFAULT_STRATEGY

        ranking_query = str(self.hunter.settings.get("ranking_query", "") or "").strip()
        sparse_list, weights = kw_list, self.hunter.settings.get("fusion_weights")
        weights_configured = weights is not None

        corpus_texts: List[str] = []
        if ranking_query:
            corpus_texts = [
                f"{p.get('Title', '')} {p.get('Abstract', '')}" for p in papers_list
            ]
            index = BM25(corpus_texts)
            sparse_list = index.score(ranking_query)
            for i, slug in enumerate(results.keys()):
                results[slug]["_bm25_score"] = round(float(sparse_list[i]), 4)

            if weights is None:
                weights = {"keyword": 1.0, "embedding": 0.0}

            logger.info("Ranking against the configured query (BM25).")
        else:
            # `info`, not `warning`: it is true of every run without a query, and
            # a line that fires every time is a line that stops being read. The
            # actionable half is said where it can still change something --
            # `read_config` and `update_config`, before the run is spent.
            logger.info(
                "No ranking_query is configured, so every paper is ordered by "
                "_kw_score -- a function of the paper and of the configured terms, "
                "which never sees a question. Measured on a hand-judged blockchain "
                "pool: nDCG@10 0.25 by that score, against 0.67 for BM25 over a "
                "question."
            )

        effective = resolve_weights(weights, cit_list)
        discarded = [
            name
            for name, values in (("embedding", sem_list), ("citation", cit_list))
            if effective[name] == 0 and len(set(values)) > 1
        ]

        final_scores = fuse_scores(
            sparse_list, sem_list,
            strategy=strategy,
            weights=weights,
            cit_scores=cit_list,
        )

        decimals = _score_decimals(self.hunter.settings)

        final_scores = self._apply_rerank(
            final_scores, papers_list, corpus_texts, ranking_query, decimals
        )

        rank_kw = percentile_ranks(sparse_list)
        rank_sem = percentile_ranks(sem_list)

        for i, slug in enumerate(results.keys()):
            results[slug]["Relevance_Score"] = round(float(final_scores[i]), decimals)
            results[slug]["_rank_kw"] = round(rank_kw[i], 4)
            results[slug]["_rank_sem"] = round(rank_sem[i], 4)

        key, min_score = inclusion_predicate(self.hunter)
        dropped = [
            slug for slug, p in results.items()
            if _as_number(p.get(key)) < min_score
        ]
        excluded = set(dropped)
        included = [p for slug, p in results.items() if slug not in excluded]
        n_after = n - len(dropped)
        with self.hunter.lock:
            stats = self.hunter.state.stats
            stats["included_final"] = n_after
            stats["excluded_technical_score"] = len(dropped)
            stats["inclusion_predicate"] = f"{key} >= {min_score:g}"
            stats["score_distribution"] = self._distribution(papers_list, key)
            stats["impact"] = self._impact(included)
            stats["fusion"] = {
                "strategy": strategy,
                "weights": dict(effective),
                "discarded": discarded,
            }
            self._attribute_score_drops(results, dropped)

        logger.info(
            "Re-ranked %d papers (%s). %d pass the inclusion predicate (%s).",
            n, strategy, n_after, f"{key} >= {min_score:g}",
        )
        if discarded:
            reason = (
                "ranking_query is set and no fusion_weights is configured"
                if ranking_query and not weights_configured
                else "the configured weights are zero, or the counts do not vary"
            )
            logger.warning(
                "Computed and then weighted 0: %s. The ranking is the remaining "
                "signals alone, because %s.",
                ", ".join(discarded), reason,
            )
        self._write_score_distribution(results, key, min_score, n_after)

    def _impact(self, papers: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Where the line for "most cited" fell among the papers the run kept.

        A declared band rather than a fixed number of citations: the threshold is
        a property of this corpus, so the report can state it and a reader can
        argue with it. Papers with no count are counted separately — they are not
        low-impact, they are unmeasured, and folding them into the band would
        report missing data as a finding.

        The population is the included set, not everything evaluated, because the
        report prints this count beside a table of included papers. Measuring the
        wider set there would describe a paper the reader cannot find in the
        table, and the coverage line above it would disagree with the line below.
        """
        percentile = self.hunter.settings.get("impact_percentile", DEFAULT_IMPACT_PERCENTILE)
        counts = [_as_number(p.get("Citations")) for p in papers]
        cutoff = impact_cutoff(counts, percentile)
        above = [p for p in papers if cutoff > 0 and _as_number(p.get("Citations")) >= cutoff]
        return {
            "percentile": percentile,
            "cutoff": cutoff,
            "papers_above": len(above),
            "papers_measured": sum(1 for c in counts if c > 0),
            "papers_unmeasured": sum(1 for c in counts if c <= 0),
        }

    def _distribution(self, papers: List[Dict[str, Any]], key: str) -> Dict[str, Any]:
        """Where the threshold sits in this run's own distribution.

        Recorded so the cut can be argued about with numbers: the report says how
        many papers the predicate admitted, and this says how many sat next to the
        line. It is the evidence the export used to discard -- the CSV holds only
        the survivors, so any choice of threshold was a guess.
        """
        values = sorted(_as_number(p.get(key)) for p in papers)
        if not values:
            return {}

        def at(share: float) -> float:
            return round(values[min(int(share * (len(values) - 1)), len(values) - 1)], 4)

        return {
            "key": key,
            "n": len(values),
            "min": round(values[0], 4),
            "p25": at(0.25),
            "median": at(0.5),
            "p75": at(0.75),
            "max": round(values[-1], 4),
        }

    def _attribute_score_drops(self, results: Dict[str, Any], dropped: List[str]) -> None:
        """Charge each paper this threshold removed to the source it came from.

        The report contradicted itself on this: the per-source table summed to
        zero in its score column while the headline said 214. The column is
        filled during screening, but the headline is rewritten here with *this*
        step's count, and nothing re-attributed the difference -- two counters
        for one population, one of them discarded.

        Clearing the column loses nothing. Every paper the screening excluded on
        score is registered in ``consolidated_results`` before it is tested
        (``resolvers.py:142`` and ``:194`` both write first), so it is in
        ``results`` and is counted again below. One population, one counter, and
        the column sums to the headline by construction.

        The paper's ``Source`` may name several databases; it is charged to the
        first, which is the rule the screening's own adjustment already uses
        (``resolvers.py:108``) -- one paper, one row, so the column reconciles.
        """
        exclusions = self.hunter.state.stats.get("exclusions_by_source")
        if exclusions is None:
            exclusions = self.hunter.state.stats.setdefault("exclusions_by_source", {})
        for entry in exclusions.values():
            entry["score"] = 0

        for slug in dropped:
            source = str(results[slug].get("Source", "") or "").split(", ")[0]
            if source:
                self.hunter.state.track_exclusion(source, "score")
                continue
            logger.warning(
                "Excluded %s on score but it names no source, so the per-source "
                "table cannot account for it (Source=%r).",
                slug, results[slug].get("Source"),
            )

    SIGNALS = (
        "_kw_score", "_bm25_score", "_sem_score", "_hybrid_score",
        "_citation_score", "Relevance_Score", "_rank_kw", "_rank_sem",
    )

    def _write_score_distribution(
        self,
        results: Dict[str, Any],
        key: str,
        min_score: float,
        n_after: int,
    ) -> None:
        """Save every evaluated paper's signals, included or not.

        The run drops what the threshold removes before anything is written, so
        the distribution of the excluded half was lost and every choice of
        threshold was a guess about a population nobody could see. The values are
        all in hand here, one line before the eviction, so the run keeps them.

        ``title`` and ``doi`` travel with each row because they are the paper's
        identity: ``doc_id_for`` derives an id from those two fields and nothing
        else, so a row without them cannot be joined back to the paper it
        describes.

        ``fusion`` is recorded for the same reason. A run that computed the
        embedding and the citation signal and then weighed them at zero ranks on
        keywords alone, and every number it exports looks exactly like a run that
        fused three signals. Which signals were thrown away is a property of the
        run, so the run writes it down.
        """
        if not self.timestamp:
            return

        rows = []
        for slug, paper in sorted(results.items(), key=lambda item: paper_order_key(item[1])):
            value = _as_number(paper.get(key))
            row = {
                "slug": slug,
                "title": str(paper.get("Title", "") or ""),
                "doi": str(paper.get("DOI", "") or ""),
                "source": str(paper.get("Source", "") or ""),
                "year": paper.get("Year"),
                "citations": _as_number(paper.get("Citations")),
                "citations_source": str(paper.get("Citations_Source", "") or ""),
                "included": value >= min_score,
            }
            for signal in self.SIGNALS:
                if paper.get(signal) is not None:
                    row[signal] = paper[signal]
            rows.append(row)

        payload = {
            "run": self.timestamp,
            "inclusion_predicate": f"{key} >= {min_score:g}",
            "inclusion_key": key,
            "min_inclusion_score": min_score,
            "counts": {
                "evaluated": len(rows),
                "included": n_after,
                "excluded": len(rows) - n_after,
            },
            "distribution": self.hunter.state.stats.get("score_distribution", {}),
            "impact": self.hunter.state.stats.get("impact", {}),
            "citation_provenance": citation_summary(rows),
            "published_version": self.hunter.state.stats.get("published_version", {}),
            "fusion": self.hunter.state.stats.get("fusion", {}),
            "signals": [s for s in self.SIGNALS],
            "papers": rows,
        }

        path = run_dir_for(self.timestamp, self.hunter.output_dir) / (
            f"score_distribution_{self.timestamp}.json"
        )
        try:
            write_json_atomically(path, payload)
        except Exception as e:
            logger.warning(
                "Could not write the score distribution to %s (%s). The run is "
                "unaffected, but the record of what the threshold excluded for "
                "this run is missing.",
                path, e,
            )
            return
        logger.info("Score distribution for %d papers: %s", len(rows), path)

    def _apply_rerank(
        self,
        final_scores: List[float],
        papers_list: List[Any],
        corpus_texts: List[str],
        ranking_query: str,
        decimals: int,
    ) -> List[float]:
        """Rerank the head of the ranking with a cross-encoder. Never raises.

        Only the head is redistributed; see
        :func:`~academic_hunter.core.nlp.reranker.rerank_scores` for the rule.
        Every failure path leaves ``final_scores`` untouched — an optional
        enhancement that breaks a run is worse than one that is absent.
        """
        cfg = rerank_config(self.hunter.settings)
        if not cfg["enabled"]:
            return final_scores

        if not ranking_query:
            logger.warning(
                "settings.rerank.enabled is true but settings.ranking_query is "
                "empty — the cross-encoder has no query to pair documents with. "
                "Skipping the rerank."
            )
            return final_scores

        n = len(papers_list)
        top_n = min(cfg["top_n"], n)
        if top_n < 2:
            return final_scores

        head = sorted(range(n), key=lambda i: (-final_scores[i], i))[:top_n]
        texts = [corpus_texts[i] for i in head]

        try:
            scores = rerank_texts(
                ranking_query,
                texts,
                model_name=cfg["model"],
                max_length=cfg["max_length"],
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "Cross-encoder rerank failed (%s); keeping the fused ranking.", e
            )
            return final_scores

        if scores is None:
            logger.info("Cross-encoder unavailable; keeping the fused ranking.")
            return final_scores

        if any(not math.isfinite(s) for s in scores):
            logger.warning(
                "Cross-encoder returned a non-finite score; keeping the fused ranking."
            )
            return final_scores

        order = sorted(range(len(scores)), key=lambda i: (-scores[i], i))
        raw_score = {head[i]: scores[i] for i in order}
        rank = {head[i]: position for position, i in enumerate(order, 1)}

        reranked = rerank_scores(final_scores, list(rank), decimals=decimals)

        moved = sum(1 for i in rank if reranked[i] != final_scores[i])
        for index in rank:
            paper = papers_list[index]
            paper["_rerank_score"] = round(raw_score[index], 4)
            paper["_rerank_rank"] = rank[index]

        with self.hunter.lock:
            self.hunter.state.stats["reranked"] = moved

        if moved:
            logger.info(
                "Cross-encoder reordered %d of the top %d papers.", moved, top_n
            )
        else:
            logger.info(
                "Cross-encoder scored the top %d papers but moved none: their "
                "scores leave no room to reorder at %d decimal place(s).",
                top_n, decimals,
            )
        return reranked


class ResolveDoiStep(PipelineStep):
    """Store the DOI a paper's URL already carries, where the column is empty.

    Measured on the delivered run: 109 of 310 papers were arXiv-only, every one
    of them with ``DOI`` empty and an arXiv id in ``URL`` — and the pipeline had
    already computed that id's DataCite DOI, in ``_citation_key``, purely to ask
    a source for a citation count, then dropped it.

    Three properties this pass keeps, each because the obvious alternative is
    wrong:

    **It fills, it never overwrites.** A DOI a publisher registered outranks one
    derived from a URL, and no source hands over a URL-derived DOI, so a filled
    value can only ever be replaced by nothing. That is also why no merge
    strategy was added for ``DOI``: the pass runs after every copy of a work has
    been merged, so the arXiv DOI cannot be present at merge time and cannot
    lock out a publisher DOI arriving with a later copy. Filling at registration
    would do exactly that.

    **It runs before the score distribution is written.** That file carries a
    ``doi`` per paper and is derived from the run's own papers; filling later
    would leave the distribution and the exported dataset disagreeing about the
    identity of the same paper, so a row of one could not be found in the other.

    **It makes no requests.** Everything comes from the paper itself, so the
    pass costs nothing and cannot fail. What it does move is identity downstream:
    ``doc_id_for``, the full-text ``parent_id`` and the vector store's document
    id all become the DOI for these papers, which is the point — one paper, one
    identifier, in every artifact of the run.
    """

    def run(self) -> None:
        filled = 0
        for paper in self.hunter.consolidated_results.values():
            if str(paper.get("DOI") or "").strip():
                continue
            doi = doi_from_url(paper.get("URL"))
            if doi:
                paper["DOI"] = doi
                filled += 1

        with self.hunter.lock:
            self.hunter.state.stats["doi_resolved"] = filled

        if filled:
            logger.info(
                "Resolved %d DOI(s) from the papers' own URLs. Every one of them "
                "addresses the work from here on — exports, the score "
                "distribution and the vector store alike.",
                filled,
            )


class IndexResultsStep(PipelineStep):
    """Accumulate consolidated results into ChromaDB for semantic search."""

    def run(self) -> None:
        store = getattr(self.hunter.pipeline, "vector_store", None)
        if store is None:
            logger.info("Vector store not available, skipping semantic indexing.")
            return

        papers = list(self.hunter.consolidated_results.values())
        if not papers:
            logger.info("No papers to index.")
            return

        success = store.index_papers(papers)
        collection = getattr(store, "default_collection", "?")
        if success:
            logger.info(
                "Indexed %d new papers into '%s'. ChromaDB accumulates across "
                "runs of the same review.", len(papers), collection,
            )
        else:
            logger.warning(
                "Indexing failed for %d papers; semantic search will not see them.",
                len(papers),
            )


class AutoExportObsidianStep(PipelineStep):
    """Auto-export elite report to Obsidian vault if configured.

    The write itself is delegated to ``hunter.obsidian_export``, a callable the
    composition root supplies. This step used to import ``export_to_obsidian``
    from ``interfaces.mcp.tools`` — the domain reaching into the interface layer,
    the most serious of the boundary violations.
    """

    def __init__(self, hunter: Any, timestamp: str = "") -> None:
        super().__init__(hunter)
        self.timestamp = timestamp

    def run(self) -> None:
        obsidian_path = self.hunter.config.settings.get("obsidian_vault_path", "")
        if not obsidian_path:
            return

        export = getattr(self.hunter, "obsidian_export", None)
        if export is None:
            return

        papers = list(self.hunter.consolidated_results.values())
        if not papers:
            return

        total = len(papers)
        top = sorted(papers, key=paper_order_key)[:10]

        lines = [f"# Academic Hunter Report — {self.timestamp}\n"]
        lines.append(f"**Total papers found:** {total}\n")
        lines.append(f"**Sources:** {', '.join(self.hunter.connectors.keys())}\n")
        lines.append(f"**Anchors:** {', '.join(self.hunter.anchors.keys())}\n")
        lines.append("\n---\n")
        lines.append("## Top 10 Papers by Relevance Score\n")

        for i, p in enumerate(top, 1):
            title = p.get("Title", "Untitled")
            score = p.get("Relevance_Score", 0.0)
            year = p.get("Year", "N/A")
            source = p.get("Source", "Unknown")
            doi = p.get("DOI", "")
            url = p.get("URL", "")
            lines.append(f"### {i}. {title}\n")
            lines.append(f"- **Score:** {score} | **Year:** {year} | **Source:** {source}\n")
            if doi:
                lines.append(f"- **DOI:** `{doi}`\n")
            if url:
                lines.append(f"- **URL:** {url}\n")
            lines.append("")

        content = "\n".join(lines)

        try:
            result = export(
                topic=f"Academic Hunter Report {self.timestamp}",
                content=content,
                tags=["academic-hunter", "research", "automated"],
                vault_path=obsidian_path,
            )
            logger.info("Obsidian auto-export: %s", result)
        except Exception as e:
            logger.debug("Obsidian auto-export skipped: %s", e)


class IngestFullTextStep(PipelineStep):
    """Fetch, extract and index the full text of the included papers.

    Opt-in via ``settings.fulltext.enabled``, off by default, and runs *after*
    the threshold filter so downloads are spent on the papers that qualified.
    The loop itself is :mod:`academic_hunter.core.fulltext.ingest`, which the
    ``index_fulltext`` MCP tool runs too.
    """

    def run(self) -> None:
        cfg = self.hunter.config.fulltext_config()
        if not cfg["enabled"]:
            return

        fetcher = getattr(self.hunter, "full_text_fetcher", None)
        if fetcher is None:
            logger.info("Full-text ingest is enabled but no fetcher is wired; skipping.")
            return

        store = getattr(self.hunter.pipeline, "vector_store", None)
        if not isinstance(store, ChunkStorePort):
            logger.info("Vector store cannot hold chunks; skipping full-text ingest.")
            return

        papers = list(self.hunter.consolidated_results.values())
        if not papers:
            return

        counters = ingest_full_text(papers, fetcher, store, cfg)

        with self.hunter.lock:
            self.hunter.state.stats["full_text"] = dict(counters)
