---
title: "Mapping the Landscape of Automated Systematic Literature Review Tools: A Comparative Taxonomy with Multi-Source Coverage Evidence"
author: "Felipe Nunes"
date: 2026-09-10
status: draft
---

# Abstract

The number of tools claiming to automate systematic literature reviews (SLRs) has grown
sharply, yet researchers lack a structured basis for choosing among them. This paper maps
the landscape across five categories — triage and synthesis tools, AI-assisted discovery
platforms, embedding-weighting methods, academic MCP servers, and LLM-driven SLR pipelines —
covering 37 tools and methods. We make two contributions. First, a comparative taxonomy with
an explicit verification date per tool, addressing the rapid churn of a field where several
entries did not exist eighteen months ago. Second, an empirical measurement of a claim that
is widely assumed but rarely tested: that multi-source aggregation is worth its cost. We
measure the exclusive contribution of each academic database in a multi-source SLR run and
find that **93.0% of retrieved papers came from exactly one source**, meaning aggregation is
not redundant. We then position one tool, Academic Hunter, within the taxonomy, identifying
the axes on which it leads, the axes on which it is behind, and the resulting research agenda.
We argue that tool comparisons in this domain should be reported **per axis** rather than as
global rankings, because no single tool in the landscape dominates across all dimensions.

# 1. Introduction

Systematic literature reviews are foundational to evidence-based research, but they are
expensive: a rigorous review can take months of screening effort. The response has been a
proliferation of automation. In 2026 a researcher faces a bewildering menu: active-learning
screeners (ASReview), commercial synthesis platforms (Covidence, Rayyan), LLM-based discovery
engines (Elicit, Consensus, Undermind), citation-graph explorers (ResearchRabbit, Litmaps,
Connected Papers), and — new since 2025 — retrieval servers that expose academic search as a
tool for AI agents (a dozen MCP servers, plus paid API offerings).

This growth creates a practical problem. Tool selection guidance is scarce and dates quickly.
Comparative reviews that exist are either commercial (vendor-produced) or narrow (covering
only screening tools, or only health-sciences evidence synthesis). The field lacks a map.

This paper provides one, and uses it to answer a specific question that the map exposes:
**is multi-source aggregation actually worth its cost?** The intuition that "more databases is
better" is widely assumed but, to our knowledge, rarely measured. It matters because a
2025–2026 comparative study found that several prominent AI discovery tools return nearly
identical results — approximately 40% uniqueness — because they all query the same underlying
corpus (Semantic Scholar). If that redundancy is intrinsic to literature retrieval, then
multi-source architectures buy little. We test this directly.

Our contributions:

1. **A taxonomy of 37 tools and methods** across five categories, with verification dates (§3).
2. **An empirical measurement of source redundancy** in a multi-source run: 93.0% of papers
   were contributed by exactly one source (§5).
3. **A per-axis positioning framework**, applied to one tool, arguing that global rankings are
   the wrong instrument for this domain (§6).
4. **An explicit agenda for evaluation**: the field's most common gap is not missing features
   but missing measurement (§7).

# 2. Method

## 2.1 Identification

Tools were identified through four complementary channels:

1. **Corpus search.** Semantic search over a locally indexed corpus of 10,500 papers
   (`semantic_search`, `quick_topic_discovery`), covering SLR automation, agentic RAG, and
   embedding-weighting literature.
2. **Grey literature and web.** Product documentation, repositories, and third-party
   comparisons.
3. **Citation chaining.** Forward and backward citation traversal from known tools.
4. **MCP server catalogues.** npm, PyPI, and community registries.

## 2.2 Inclusion criteria

A tool is included if it satisfies at least one of: it performs a stage of the SLR workflow;
it exposes academic retrieval as a tool for AI agents; or it proposes an embedding-weighting
method (even without being an SLR tool).

## 2.3 Exclusion criteria

Pure databases without a software layer (Scopus, Web of Science) — these are sources, not
tools. Generic RAG frameworks (LangChain, LlamaIndex) without academic specialisation.
Projects with no code, documentation, or verifiable publication.

## 2.4 Limitations

This is an **exploratory mapping, not a formal systematic review**: no protocol was
registered, and §2.1 documents the channels used rather than a PRISMA procedure. Commercial
tools were assessed from public documentation, not executed. Most importantly, this is a
**moving target** — several entries in §3 did not exist eighteen months ago, and MCP server
listings change weekly. This is precisely why every tool in Table 1 carries a verification date.

# 3. Taxonomy

| Category                        | Definition                                 | Representative tools                                                                     |
| ------------------------------- | ------------------------------------------ | ---------------------------------------------------------------------------------------- |
| **A. Triage & synthesis**       | Screening and evidence-synthesis platforms | ASReview, Rayyan, Covidence, EPPI-Reviewer, RevMan                                       |
| **B. AI-assisted discovery**    | LLM-mediated search and reading            | Elicit, Consensus, Scite, Undermind, Ai2 Paper Finder, SciSpace, ResearchRabbit, Litmaps |
| **C. Embedding weighting**      | Methodological contributions               | SIF, SGPT, Echo, LLM2Vec, GRIT, QAEA-DR, Weight-Bleeding                                 |
| **D. Academic MCP servers**     | Retrieval exposed as agent tools           | lit-review-mcp, academic-search-mcp, paper-distill-mcp, PAPER-SQL, citecheck             |
| **E. LLM-driven SLR pipelines** | End-to-end LLM pipelines                   | JARVIS, prismAId, LatteReview, ReviewAid, SWARM-SLR, EmbedSLR, PaperQA2, Paper Circle    |

**Table 1** (abridged below; full inventory with licenses, costs and verification dates is in
the companion repository file `papers/tool-mapping.md`):

| Tool               | Cat.       | License / Cost             | Verified   |
| ------------------ | ---------- | -------------------------- | ---------- |
| Academic Hunter    | A, C, D, E | MIT / zero                 | 2026-09-10 |
| ASReview           | A          | Apache / zero              | 2026-09-10 |
| Rayyan             | A          | Freemium                   | 2026-09-10 |
| Covidence          | A          | Paid                       | 2026-09-10 |
| Elicit             | B          | Freemium (~US$14/mo)       | 2026-09-10 |
| Consensus          | B          | Freemium (~US$12/mo)       | 2026-09-10 |
| Scite              | B          | Paid (~US$12–20/mo)        | 2026-09-10 |
| Undermind          | B          | Freemium (~US$19/mo)       | 2026-09-10 |
| Ai2 Paper Finder   | B          | Free (Ai2)                 | 2026-09-10 |
| EmbedSLR v2.0      | E          | Open source (SoftwareX)    | 2026-09-10 |
| LatteReview        | E          | Open source (LLM required) | 2026-09-10 |
| SWARM-SLR          | E          | Open source                | 2026-09-10 |
| PaperQA2           | E          | Apache (FutureHuman)       | 2026-09-10 |
| JARVIS Research OS | E          | MIT (Gemini API required)  | 2026-09-10 |

## 3.1 Boundary observations

Categories overlap, and the overlaps are informative. Most tools occupy exactly one category:
ASReview does triage, Litmaps does citation mapping, SIF is a method. Academic Hunter is the
only tool appearing in four categories simultaneously (A, C, D, E) **without requiring an
LLM**. This is the basis of the positioning in §6, and it is also why single-axis comparisons
misrepresent the landscape.

# 4. The redundancy question

## 4.1 Why it matters

Multi-source search is a common selling point. ASReview draws on one database; JARVIS on five;
Academic Hunter queries seven in parallel and exposes eight more on demand. The implicit claim
is that each source adds coverage.

That claim is not self-evident. A 2025–2026 comparison found that SciSpace, Consensus, and Ai2
Paper Finder return substantially overlapping results — roughly 40% uniqueness — because all
three consult Semantic Scholar. Overlap of that magnitude between independent _products_
suggests the underlying corpora, not the products, determine what is found. If the same holds
within a multi-source pipeline, aggregation is expensive theatre.

## 4.2 Measurement

We measured exclusive contribution: for each paper in a completed run, how many of the
configured sources returned it? A paper returned by exactly one source is coverage that only
that source provided.

**Setup.** A completed multi-source SLR run for a blockchain-interoperability topic:
1,538 deduplicated papers, seven configured connectors.

**Result.**

| Finding                                  | Value             |
| ---------------------------------------- | ----------------- |
| Papers retrieved by exactly one source   | **1,430 (93.0%)** |
| Papers retrieved by more than one source | 108 (7.0%)        |

| Source           | Papers found | Exclusive | Marginal loss if removed |
| ---------------- | -----------: | --------: | -----------------------: |
| OpenAlex         |          685 |       586 |                    38.1% |
| Crossref         |          582 |       494 |                    32.1% |
| ArXiv            |          292 |       274 |                    17.8% |
| Semantic Scholar |           90 |        76 |                     4.9% |

**Interpretation.** Overlap between sources in this pipeline is **7%**, an order of magnitude
below the ~60% overlap reported between single-source AI discovery products. Aggregation here
is not redundant: removing OpenAlex alone would lose 38% of the corpus, and the four
contributing sources each provide material the others do not.

**Necessary caveat.** Only **four of the seven** connectors contributed papers. DBLP, DOAJ and
CORE returned nothing for this topic — they are keyword-only connectors whose indices did not
cover the query. The run therefore exercised four sources, not seven. This is a finding in
itself: connector count is not coverage, and per-source marginal contribution should be
measured per topic rather than assumed. We return to this in §7.

**Metric caveat.** The two figures are related but not identical. The third-party 40%
uniqueness figure compares _result sets from two different products_; ours measures _exclusive
contribution within one pipeline_. Both address source redundancy; neither should be presented
as directly equivalent to the other.

# 5. Comparative matrix

| Criterion                     | AH          | ASReview    | JARVIS      | EmbedSLR        | Elicit    | Rayyan      | Covidence |
| ----------------------------- | ----------- | ----------- | ----------- | --------------- | --------- | ----------- | --------- |
| Open source                   | ✅ MIT      | ✅ Apache   | ✅ MIT      | ✅              | ❌        | ❌          | ❌        |
| Cost                          | Zero        | Zero        | Zero¹       | Zero            | ~US$14/mo | Freemium    | Paid      |
| Sources in pipeline           | **7**       | 1           | 5           | 0²              | 1         | 1–3         | 1–3       |
| Complete SLR pipeline         | ✅          | Triage only | ✅          | Triage only     | ❌        | Triage only | Partial   |
| No LLM dependency             | ✅          | ✅          | ❌          | ✅              | ❌        | N/A         | N/A       |
| Configurable semantic scoring | ✅          | ❌          | ❌          | Model consensus | ❌        | ❌          | ❌        |
| MCP server                    | ✅ 37 tools | ❌          | ✅ 15 tools | ❌              | ❌        | ❌          | ❌        |
| Offline / CPU-only            | ✅          | ✅          | ❌          | ✅              | ❌        | ❌          | ❌        |
| Full-text processing          | ❌          | ❌          | ✅          | ❌              | ❌        | ❌          | ❌        |
| Collaborative screening       | ❌          | ✅          | ❌          | ✅ (simulated)  | ❌        | ✅          | ✅        |
| Published retrieval metrics   | ❌          | ✅          | ✅          | ✅              | N/A       | N/A         | N/A       |

¹ MIT licensed, but the core pipeline requires the Gemini API.
² EmbedSLR screens a corpus the user supplies; it does not search.

# 6. Positioning: per axis, not overall

The temptation in a paper like this is to declare a winner. The evidence does not support
one. Across the 37 tools mapped, no single entry leads on all dimensions — and the dimension
on which a tool leads is usually the one its architecture was designed around.

For Academic Hunter specifically, the honest reading is:

**Where it leads.** Multi-source coverage in the pipeline (7 parallel sources, measured at 93%
exclusive contribution), absence of LLM/API dependency (fully offline, CPU-only, zero
recurring cost), configurable semantic scoring without retraining (Weight-Bleeding),
and agent-integration surface (37 MCP tools versus JARVIS's 15).

**Where it is behind.** No full-text processing — the entire pipeline operates on title and
abstract, whereas PaperQA2, Scite and JARVIS go further. No LLM layer, so no LLM-assisted
screening or structured extraction (LatteReview, SWARM-SLR, Elicit). No published retrieval
quality metrics — no nDCG, recall@k, or labelled benchmark (EmbedSLR and PaperQA2 both report
these). Weak screening: the keyword screener is a stub. No collaborative multi-reviewer mode,
which Rayyan, Covidence and ASReview have.

**The consequent claim.** Academic Hunter is not "better than" the field; it occupies a
distinct cell: an **offline, zero-cost, multi-source, agent-native SLR pipeline with a
configurable scoring method**. Tools that beat it on triage do so by requiring LLM API calls;
tools that beat it on full-text coverage do so by requiring paid access. Stated per axis, the
position is defensible and checkable. Stated globally, it would not survive review.

# 7. The field's real gap: evaluation

Across the mapping, a pattern emerges that is more consequential than any feature gap:
**most tools in this landscape do not publish retrieval-quality evaluation.**

ASReview, EmbedSLR and PaperQA2 are exceptions — they report metrics, which is why they can be
compared. Many others, including several in categories D and E, report capability lists
without evidence of retrieval quality. Capability claims are cheap; measured recall is not.

This has a direct implication for the present work and for Academic Hunter: the missing piece
is not a feature but a **labelled evaluation set**. Without query-paper pairs with relevance
judgements, it is impossible to say whether a new embedding, a cross-encoder stage, or a
different weighting scheme improves the system — only whether it changes it. We therefore
propose, as the highest-priority item for the tool examined here and a general recommendation
for the field, the construction of a shared, small, labelled benchmark (50–100 judged pairs
suffices to start) so that changes can be compared rather than merely described.

Two secondary gaps follow from the measurement in §4.2. First, **connector count is not
coverage**: three of seven connectors contributed nothing, and the field should report
per-source marginal contribution per topic rather than listing database counts. Second,
**tool comparisons should carry verification dates**; in a landscape where several entries are
under two years old and MCP listings change weekly, an undated comparison is unreliable within
months.

# 8. Conclusion

This paper mapped 37 tools and methods across five categories of SLR automation, supplied an
explicit verification date for each, and tested the assumption that multi-source aggregation
is worth its cost. It is: 93.0% of papers in a multi-source run came from exactly one source,
an order of magnitude less redundancy than reported between single-source AI discovery
products — though only four of seven configured sources contributed at all, which is itself a
finding worth carrying forward.

For the tool examined in detail, the defensible claim is per-axis rather than global: it leads
on offline multi-source coverage and agent integration, and trails on full-text handling,
LLM-assisted screening, and published retrieval metrics. The most valuable next step is not a
feature but an evaluation: a small labelled benchmark that would let the field compare tools
instead of listing their capabilities.

# Availability

The full inventory, the measurement scripts, and the taxonomy source are available in the
project repository at `github.com/devfelipenunes/academic-hunter` (`papers/tool-mapping.md`,
`papers/experiments/source_uniqueness.py`).
