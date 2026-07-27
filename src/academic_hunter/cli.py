"""CLI entry points for Academic Hunter.

- ``academic-hunter run`` — execute the configured search pipeline
- ``academic-hunter interactive`` — guided SLR wizard (no config editing needed)
- ``academic-hunter benchmark`` — ablation benchmark across 3 scoring modes
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from academic_hunter import AcademicHunter
from academic_hunter.core import get_config

_STOPWORDS = {
    "the", "a", "an", "of", "in", "for", "and", "or", "to", "with",
    "on", "at", "by", "from", "as", "is", "was", "are", "were", "be",
    "been", "being", "have", "has", "had", "do", "does", "did", "but",
    "not", "what", "which", "who", "whom", "this", "that", "these",
    "those", "it", "its", "study", "research", "paper", "approach",
    "method", "result", "analysis", "based", "using", "new", "novel",
    "model", "data", "system", "method", "also", "however", "thus",
}

MODES = [
    ("keyword", "Keyword-only (regex, no embedding)"),
    ("embedding", "Embedding-only (Weight-Bleeding, no regex)"),
    ("hybrid", "Hybrid (70% keyword + 30% embedding)"),
]


# ── Interactive wizard ────────────────────────────────────────────────────────


def cmd_interactive():
    """Guided SLR wizard — discovers jargon, configures search, runs pipeline."""
    import requests

    def p(text=""): print(text)

    p()
    p("=" * 60)
    p("  🧪 Academic Hunter — Modo Interativo")
    p("  Basta dizer o tópico da sua revisão.")
    p("=" * 60)

    # ── 1. Topic ─────────────────────────────────────────────────────────────
    p()
    topic = input("  📌 Qual o tópico da sua revisão? ").strip()
    if not topic:
        print("  ❌ Tópico inválido.")
        return

    p(f"\n  🔍 Descobrindo jargões sobre '{topic}'...")

    # ── 2. Discover jargon ──────────────────────────────────────────────────
    discovered = set()
    try:
        url = f"https://api.semanticscholar.org/graph/v1/paper/search?query={topic}&limit=15&fields=title,year"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            papers = resp.json().get("data", [])
            for paper in papers:
                title = paper.get("title", "")
                # Extrai bigramas significativos do título
                words = title.lower().split()
                for i in range(len(words) - 1):
                    bigram = f"{words[i]} {words[i+1]}"
                    if len(bigram) > 6 and all(w.isalpha() for w in words[i:i+2]):
                        discovered.add(bigram)
                # Também adiciona termos individuais relevantes
                for w in words:
                    if len(w) > 4 and w.isalpha() and w not in _STOPWORDS:
                        discovered.add(w)
    except Exception as e:
        print(f"  ⚠️  Não foi possível descobrir jargões: {e}")

    # Palavras do próprio tópico
    topic_words = [w for w in topic.lower().split() if len(w) > 3]
    discovered.update(topic_words)

    # Ordena por relevância (frequência)
    from collections import Counter
    term_freq = Counter()
    try:
        url = f"https://api.semanticscholar.org/graph/v1/paper/search?query={topic}&limit=20&fields=título"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            papers = resp.json().get("data", [])
            for paper in papers:
                title = (paper.get("title") or "").lower()
                for term in discovered:
                    if term.lower() in title:
                        term_freq[term] += 1
    except Exception:
        pass

    # Se não conseguiu frequência, usa ordem alfabética
    if not term_freq:
        for t in discovered:
            term_freq[t] = 1

    sorted_terms = sorted(term_freq, key=term_freq.get, reverse=True)
    top_terms = sorted_terms[:15]

    # ── 3. Suggest configuration ────────────────────────────────────────────
    p(f"\n  📋 Termos encontrados automaticamente:")
    p()

    anchors = {}
    weights = {}
    categories = {}

    # Agrupa em âncoras (principais conceitos)
    core_terms = top_terms[:5]
    secondary = top_terms[5:12]

    # Cria categoria "Core_Concepts" com os principais
    anchors["Core_Concepts"] = core_terms
    for t in core_terms:
        weights[t] = 5.0
        categories[t] = "Core"

    # Categoria "Context" com os secundários
    if secondary:
        anchors["Context"] = secondary
        for t in secondary:
            weights[t] = 2.0
            categories[t] = "Context"

    # Sugestão de technical_strings
    tech_strings = {"Core": [], "Context": []}
    for t, cat in categories.items():
        tech_strings[cat].append(t)

    # ── 4. Review ───────────────────────────────────────────────────────────
    p("  Configuração sugerida:")
    p()
    for group, terms in anchors.items():
        p(f"    📁 {group}:")
        for t in terms:
            w = weights.get(t, 2.0)
            p(f"      · {t} (peso: {w})")
    p()

    confirm = input("  Aceitar configuração e iniciar busca? [S/n] ").strip().lower()
    if confirm == "n":
        p("\n  ⏹️  Cancelado pelo usuário.")
        return

    # ── 5. Save config ─────────────────────────────────────────────────────
    config = HunterConfig()
    config.anchors = anchors
    config.tech_strings = tech_strings
    config.tech_weights = weights
    config.context_rules = {}
    config.keyword_only_terms = list(set(top_terms) - set(core_terms) - set(secondary))
    config.keyword_only_category = "Consolidated"
    config.settings["start_year"] = 2020
    config.settings["limit_per_query"] = 100
    config.save()

    # ── 6. Run search ──────────────────────────────────────────────────────
    p(f"\n  🔍 Buscando em 16 fontes acadêmicas...")
    hunter = AcademicHunter()
    try:
        report_path = hunter.run(limit_per_source=100)
        n_papers = sum(hunter.stats.get("identified", {}).values())
        p(f"\n  ✅ {n_papers} papers encontrados")
        p(f"  📄 Relatório: {report_path}")
    except Exception as e:
        p(f"\n  ⚠️  Erro na busca: {e}")
        p("  Continuando com dados existentes...")
        n_papers = 0

    # ── 7. Auto-index para ChromaDB ────────────────────────────────────────
    try:
        from academic_hunter.plugins.vector_stores import ChromaVectorStore
        store = ChromaVectorStore(db_dir=str(Path(".").resolve() / ".academic_hunter" / "chroma_db"))
        papers = list(hunter.consolidated_results.values())
        if papers:
            store.index_papers(papers)
            p(f"  📦 {len(papers)} papers indexados no ChromaDB")
    except Exception:
        pass

    # ── 8. Interactive analysis menu ────────────────────────────────────────
    _interactive_menu(hunter, topic, n_papers)

    p("\n" + "=" * 60)
    p("  ✅ SLR concluída! Dados salvos em results/")
    p("=" * 60)


def _interactive_menu(hunter, topic, n_papers):
    """Pós-busca: menu interativo de análises."""
    from ._utils import get_project_root

    while True:
        p = print
        p()
        p("=" * 50)
        p(f"  📊 ANÁLISES — {topic}")
        p("=" * 50)
        p("  1. Ver ranking completo dos papers")
        p("  2. Agrupar por tema (clusters)")
        p("  3. Detectar papers inovadores (outliers)")
        p("  4. Ver evolução temporal")
        p("  5. Mapa da pesquisa (2D)")
        p("  6. Gerar resumo de um paper (DOI)")
        p("  7. Exportar resultados")
        p("  8. Encerrar")
        p()

        choice = input("  Escolha uma opção (1-8): ").strip()

        if choice == "1":
            _show_ranking(hunter)
        elif choice == "2":
            _run_clustering()
        elif choice == "3":
            _run_novelty()
        elif choice == "4":
            _run_evolution()
        elif choice == "5":
            _run_landscape()
        elif choice == "6":
            _run_summarize()
        elif choice == "7":
            _export_results(hunter)
        elif choice == "8":
            break
        else:
            p("  Opção inválida.")

        if choice != "8":
            input("  Pressione Enter para continuar...")


def _show_ranking(hunter):
    """Mostra top-20 papers com scores."""
    p = print
    p("\n  🏆 TOP 20 PAPERS\n")
    papers = sorted(
        hunter.consolidated_results.values(),
        key=lambda x: float(x.get("Relevance_Score", 0) or 0),
        reverse=True,
    )
    if not papers:
        papers = sorted(
            hunter.consolidated_results.values(),
            key=lambda x: float(x.get("Relevance_Score", 0) or 0),
            reverse=True,
        )
    for i, paper in enumerate(papers[:20], 1):
        title = (paper.get("Title") or "")[:70]
        score = paper.get("Relevance_Score", "?")
        year = paper.get("Year", "?")
        doi = (paper.get("DOI") or "")[:30]
        p(f"  {i:>2}. [{score}] {title}")
        p(f"      {year} · {doi}")


def _run_clustering():
    """Executa clustering via MCP tool internamente."""
    p = print
    p("\n  🧩 Para executar o clustering completo, use no MCP:")
    p("  cluster_papers(top_k=500)")


def _run_novelty():
    p = print
    p("\n  🆕 Para detectar outliers, use no MCP:")
    p("  find_novel_papers(top_k=200)")


def _run_evolution():
    p = print
    p("\n  📈 Para ver evolução temporal, use no MCP:")
    p("  topic_evolution(top_k=500)")


def _run_landscape():
    p = print
    p("\n  🌍 Para gerar o mapa 2D, use no MCP:")
    p("  visualize_landscape(top_k=500)")


def _run_summarize():
    p = print
    doi = input("  DOI do paper: ").strip()
    if doi:
        p(f"\n  📝 Para resumir, use no MCP:")
        p(f"  summarize_paper(doi=\"{doi}\")")


def _export_results(hunter):
    """Exporta resultados em formato escolhido."""
    p = print
    p("\n  Formatos disponíveis: csv, json, bibtex, ris")
    fmt = input("  Formato: ").strip().lower()
    if fmt in ("csv", "json", "bibtex", "ris"):
        from .interfaces.mcp.tools._utils import get_project_root
        project_root = get_project_root()
        ts = time.strftime("%Y%m%d_%H%M%S")
        out_path = f"results/export_{ts}.{fmt}"
        try:
            if fmt == "csv":
                import pandas as pd
                df = pd.DataFrame(list(hunter.consolidated_results.values()))
                df.to_csv(out_path, index=False)
            elif fmt == "json":
                with open(out_path, "w") as f:
                    json.dump(list(hunter.consolidated_results.values()), f, indent=2, default=str)
            p(f"  ✅ Exportado para {out_path}")
        except Exception as e:
            p(f"  ⚠️  Erro ao exportar: {e}")
    else:
        p(f"  ❌ Formato '{fmt}' não suportado.")


# ── Original run / benchmark ──────────────────────────────────────────────────


def run_scraper():
    """Entry point for the main script."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    parser = argparse.ArgumentParser(description="Academic Hunter")
    parser.add_argument("--limit", type=int, default=None, help="Limit per source (overrides config)")
    parser.add_argument("--benchmark", action="store_true", help="Run ablation benchmark (3 modes)")
    args = parser.parse_args()

    if args.benchmark:
        return run_benchmark(args.limit)

    hunter = AcademicHunter()
    if args.limit is not None:
        hunter.run(limit_per_source=args.limit)
    else:
        limit = hunter.config.settings.get("limit_per_query", 100)
        hunter.run(limit_per_source=limit)


def run_benchmark(limit_per_source=None):
    """Run all 3 scoring modes and generate comparison report."""
    print("=" * 60)
    print("  Academic Hunter — Benchmark Mode")
    print("  Comparing keyword vs embedding vs hybrid scoring")
    print("=" * 60)

    results = []
    for mode, label in MODES:
        print(f"\n  MODE: {label}")
        config = HunterConfig()
        config.settings.setdefault("ablation", {})["mode"] = mode
        config.save()

        hunter = AcademicHunter()
        t0 = time.time()
        limit = limit_per_source or config.settings.get("limit_per_query", 100)
        report_path = hunter.run(limit_per_source=limit)
        elapsed = time.time() - t0

        n_identified = sum(hunter.stats["identified"].values())
        n_final = hunter.stats["included_final"]
        scores = sorted(
            (p.get("Relevance_Score", 0) for p in hunter.consolidated_results.values()),
            reverse=True,
        )[:5]

        results.append({
            "mode": mode,
            "identified": n_identified,
            "excluded_year": hunter.stats.get("excluded_year", 0),
            "excluded_anchors": hunter.stats.get("excluded_anchors", 0),
            "excluded_score": hunter.stats.get("excluded_technical_score", 0),
            "final_included": n_final,
            "top_5_scores": scores,
            "elapsed_s": round(elapsed, 1),
        })
        print(f"  ✓ {n_final} papers included in {elapsed:.0f}s")

    # Summary
    print(f"\n{'='*60}")
    print(f"  BENCHMARK RESULTS")
    print(f"{'='*60}")
    print(f"{'Mode':<20} {'Identified':>10} {'Final':>8} {'Excl Score':>10} {'Top-1':>8} {'Time':>8}")
    print(f"{'-'*20} {'-'*10} {'-'*8} {'-'*10} {'-'*8} {'-'*8}")
    for r in results:
        print(f"{r['mode']:<20} {r['identified']:>10} {r['final_included']:>8} {r['excluded_score']:>10} {r['top_5_scores'][0]:>8} {r['elapsed_s']:>7.0f}s")

    # Save
    out_path = Path("results") / "benchmark_results.json"
    out_path.write_text(json.dumps(results, indent=2))
    print(f"\n✅ Benchmark saved to {out_path}")

    # Restore hybrid
    config = HunterConfig()
    config.settings.setdefault("ablation", {})["mode"] = "hybrid"
    config.save()
    print(f"✅ Config restored to hybrid mode")


# ── CLI dispatcher ────────────────────────────────────────────────────────────


def main():
    """CLI dispatcher: ``academic-hunter run``, ``interactive``, or ``benchmark``."""
    parser = argparse.ArgumentParser(description="Academic Hunter")
    parser.add_argument("command", nargs="?", default="run",
                        choices=["run", "interactive", "benchmark"],
                        help="Command to execute (default: run)")
    parser.add_argument("--limit", type=int, default=None, help="Limit per source")
    args = parser.parse_args()

    if args.command == "interactive":
        cmd_interactive()
    elif args.command == "benchmark":
        run_benchmark(args.limit)
    else:
        # run — mantém compatibilidade com args --limit e --benchmark
        run_scraper()


if __name__ == "__main__":
    main()
