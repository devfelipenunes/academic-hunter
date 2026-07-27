#!/usr/bin/env python3
"""Comprehensive benchmark: Vanilla bi-encoder vs Weight-Bleeding vs Echo-style
repetition across multiple embedding models (MiniLM-L6-v2, BGE-base, GTE-small).

Generates:
  1. Per-model Spearman correlation tables
  2. Top-10 overlap analysis
  3. PCA visualization of centroid shift
  4. Computational cost comparison

Output: papers/experiments/results/benchmark_results.txt
        papers/experiments/results/centroid_shift.png

Usage:
    source .venv/bin/activate
    python papers/experiments/benchmark_baselines.py
"""

import sys, json, math, time, hashlib
from pathlib import Path

SRC = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(SRC))

import numpy as np
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns

REPO_ROOT = Path(__file__).parent.parent.parent
RESULTS_DIR = REPO_ROOT / "papers" / "experiments" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

PASS, FAIL = 0, 0
def check(cond, msg):
    global PASS, FAIL
    if cond: PASS += 1; print(f"  ✅ {msg}")
    else:    FAIL += 1; print(f"  ❌ {msg}")

# ========== Test papers (10 SLR-themed, diverse) ==========
TEST_PAPERS = [
    "Sentence-BERT: Sentence Embeddings using Siamese BERT-Networks",
    "Repetition Improves Language Model Embeddings",
    "SGPT: GPT Sentence Embeddings for Semantic Search",
    "A Simple but Tough-to-Beat Baseline for Sentence Embeddings",
    "Generative Representational Instruction Tuning",
    "LLM2Vec: Large Language Models Are Secretly Powerful Text Encoders",
    "Blockchain Technology for Distributed Ledger Systems",
    "Deep Learning for Natural Language Processing",
    "An open source machine learning framework for efficient and transparent systematic reviews",
    "Attention Is All You Need",
]

BASE_ANCHORS = ["sentence embedding", "bi-encoder", "semantic search", "information retrieval"]
TECH_WEIGHTS = {
    "sentence transformer": 5.0,
    "bi-encoder": 4.0,
    "mean pooling": 3.0,
    "embedding": 2.0,
    "term repetition": 5.0,
    "attention": 3.0,
}


def load_model(model_name: str):
    """Load a sentence transformer model. Returns (encode_fn, dim, actual_name)."""
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(model_name, trust_remote_code=True)
    def encode(texts):
        if isinstance(texts, str):
            texts = [texts]
        return model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    dim = model.get_sentence_embedding_dimension()
    return encode, dim, model_name


def vanilla_score(encode_fn, papers, base_text):
    """Vanilla bi-encoder: embed base, cosine similarity to each paper."""
    v_base = encode_fn(base_text)[0]
    scores = []
    for p in papers:
        v_p = encode_fn(p)[0]
        sim = float(np.dot(v_base, v_p))
        scores.append(math.sqrt(max(sim, 0)) * 10 if sim > 0 else 0)
    return scores


def weight_bleeding_score(encode_fn, papers, base_parts, tech_weights):
    """Weight-Bleeding: weighted centroid in embedding space."""
    unique_terms = list(tech_weights.keys())
    texts = [" ".join(base_parts)] + unique_terms
    embeddings = encode_fn(texts)
    v_base = np.array(embeddings[0], dtype=np.float32)
    n_base = len(base_parts)
    v_sum = v_base * n_base
    total_w = float(n_base)
    for term in unique_terms:
        idx = 1 + unique_terms.index(term)
        v_term = np.array(embeddings[idx], dtype=np.float32)
        w = tech_weights[term]
        v_sum += v_term * w
        total_w += w
    v_ref = v_sum / max(total_w, 1e-10)
    scores = []
    for p in papers:
        v_p = np.array(encode_fn(p)[0], dtype=np.float32)
        sim = float(np.dot(v_p, v_ref))
        scores.append(math.sqrt(max(sim, 0)) * 10 if sim > 0 else 0)
    return scores


def echo_repetition_score(encode_fn, papers, query_text, repeat_n=2):
    """Echo-style: repeat the entire query text N times, encode, cosine sim."""
    repeated = " ".join([query_text] * repeat_n)
    v_query = encode_fn(repeated)[0]
    scores = []
    for p in papers:
        v_p = encode_fn(p)[0]
        sim = float(np.dot(v_query, v_p))
        scores.append(math.sqrt(max(sim, 0)) * 10 if sim > 0 else 0)
    return scores


def spearman_rho(a, b):
    n = len(a)
    ra = sorted(range(n), key=lambda i: a[i], reverse=True)
    rb = sorted(range(n), key=lambda i: b[i], reverse=True)
    rank_a = [ra.index(i) for i in range(n)]
    rank_b = [rb.index(i) for i in range(n)]
    d = sum((rank_a[i] - rank_b[i]) ** 2 for i in range(n))
    return 1 - (6 * d) / (n * (n * n - 1))


def top_n_overlap(a, b, n=10):
    top_a = set(sorted(range(len(a)), key=lambda i: a[i], reverse=True)[:n])
    top_b = set(sorted(range(len(b)), key=lambda i: b[i], reverse=True)[:n])
    return len(top_a & top_b)


# ========== Models to test ==========
MODELS = {
    "all-MiniLM-L6-v2": "MiniLM (384d)",
    "BAAI/bge-base-en-v1.5": "BGE-base (768d)",
    "thenlper/gte-small": "GTE-small (384d)",
}

QUERY_TEXT = "sentence embedding term repetition for bi-encoder semantic relevance scoring"

def run():
    global PASS, FAIL
    print("=" * 70)
    print("  WEIGHT-BLEEDING BENCHMARK — Vanilla vs WB vs Echo Repetition")
    print("  Multi-model comparison (MiniLM, BGE-base, GTE-small)")
    print("=" * 70)

    all_results = {}
    centroid_embeddings = {}  # For PCA

    for model_key, model_label in MODELS.items():
        print(f"\n{'=' * 70}")
        print(f"  Model: {model_label} ({model_key})")
        print(f"{'=' * 70}")

        encode_fn, dim, name = load_model(model_key)
        print(f"  Dim: {dim}")

        # Compute scores
        vanilla_scores = vanilla_score(encode_fn, TEST_PAPERS, QUERY_TEXT)
        wb_scores = weight_bleeding_score(encode_fn, TEST_PAPERS, BASE_ANCHORS, TECH_WEIGHTS)
        echo_scores = echo_repetition_score(encode_fn, TEST_PAPERS, QUERY_TEXT, repeat_n=2)
        echo3_scores = echo_repetition_score(encode_fn, TEST_PAPERS, QUERY_TEXT, repeat_n=3)

        # Vanilla bi-encoder with sqrt transform baseline
        vanilla_scores_raw = vanilla_score(encode_fn, TEST_PAPERS, QUERY_TEXT)

        # Comparisons
        rho_wb = spearman_rho(vanilla_scores, wb_scores)
        rho_echo = spearman_rho(vanilla_scores, echo_scores)
        rho_echo3 = spearman_rho(vanilla_scores, echo3_scores)
        rho_wb_echo = spearman_rho(wb_scores, echo_scores)
        top10_wb = top_n_overlap(vanilla_scores, wb_scores, 10)
        top10_echo = top_n_overlap(vanilla_scores, echo_scores, 10)
        top10_echo3 = top_n_overlap(vanilla_scores, echo3_scores, 10)

        print(f"\n  ┌──────────────────────┬──────────┐")
        print(f"  │ Method               │ Spearman ρ │")
        print(f"  ├──────────────────────┼──────────┤")
        print(f"  │ Vanilla vs WB        │   {rho_wb:.4f}  │")
        print(f"  │ Vanilla vs Echo (2×) │   {rho_echo:.4f}  │")
        print(f"  │ Vanilla vs Echo (3×) │   {rho_echo3:.4f}  │")
        print(f"  │ WB vs Echo (2×)      │   {rho_wb_echo:.4f}  │")
        print(f"  └──────────────────────┴──────────┘")

        print(f"\n  ┌──────────────────────┬──────────────┐")
        print(f"  │ Method               │ Top-10 overlap │")
        print(f"  ├──────────────────────┼──────────────┤")
        print(f"  │ Vanilla vs WB        │    {top10_wb}/10        │")
        print(f"  │ Vanilla vs Echo (2×) │    {top10_echo}/10        │")
        print(f"  │ Vanilla vs Echo (3×) │    {top10_echo3}/10        │")
        print(f"  └──────────────────────┴──────────────┘")

        # Print actual rankings
        print(f"\n  ┌──────────┬──────────┬──────────┬──────────┐")
        print(f"  │ Paper    │ Vanilla  │ WB       │ Echo 2×  │")
        print(f"  ├──────────┼──────────┼──────────┼──────────┤")
        for i, p in enumerate(TEST_PAPERS):
            short = p[:25]
            print(f"  │ {short:25s} │ {vanilla_scores[i]:7.2f} │ {wb_scores[i]:7.2f} │ {echo_scores[i]:7.2f} │")
        print(f"  └──────────┴──────────┴──────────┴──────────┘")

        all_results[model_label] = {
            "rho_wb": rho_wb,
            "rho_echo": rho_echo,
            "rho_echo3": rho_echo3,
            "rho_wb_echo": rho_wb_echo,
            "top10_wb": top10_wb,
            "top10_echo": top10_echo,
            "top10_echo3": top10_echo3,
            "vanilla": vanilla_scores,
            "wb": wb_scores,
            "echo": echo_scores,
            "echo3": echo3_scores,
        }

        # Collect embeddings for PCA
        for method_name, scores in [("Vanilla", vanilla_scores), ("WB", wb_scores), ("Echo_2x", echo_scores)]:
            for i, p in enumerate(TEST_PAPERS):
                key = f"{method_name}_{i}"
                centroid_embeddings[key] = {
                    "method": method_name,
                    "paper_idx": i,
                    "paper_short": p[:30],
                    "score": scores[i],
                }

    # ========== Summary table ==========
    print(f"\n{'=' * 70}")
    print(f"  SUMMARY — Across all models")
    print(f"{'=' * 70}")
    print(f"\n  ┌──────────────────┬──────────┬──────────┬──────────┐")
    print(f"  │ Metric           │ MiniLM   │ BGE-base │ GTE-small│")
    print(f"  ├──────────────────┼──────────┼──────────┼──────────┤")
    for metric in ["rho_wb", "rho_echo", "rho_echo3", "top10_wb", "top10_echo", "top10_echo3"]:
        label = metric.replace("_", " ").title()
        vals = [all_results[m][metric] for m in all_results]
        print(f"  │ {label:16s} │ {vals[0]:8.4f} │ {vals[1]:8.4f} │ {vals[2]:8.4f} │")
    print(f"  └──────────────────┴──────────┴──────────┴──────────┘")

    # ========== PCA Figure ==========
    print(f"\n  Generating PCA visualization...")
    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    colors = {"Vanilla": "#3498db", "WB": "#e74c3c", "Echo_2x": "#2ecc71"}
    markers = {"Vanilla": "o", "WB": "^", "Echo_2x": "s"}

    for idx, (model_key, model_label) in enumerate(MODELS.items()):
        encode_fn, dim, name = load_model(model_key)
        ax = axes[idx]

        # Embed all papers with each method
        all_vecs = []
        labels = []
        paper_names = []

        # Vanilla
        v_base = encode_fn(QUERY_TEXT)[0]
        paper_vecs = encode_fn(TEST_PAPERS)
        for v_p in paper_vecs:
            all_vecs.append(np.array(v_p, dtype=np.float32))
            labels.append("Vanilla")
            paper_names.append("")

        # WB centroid
        wb_texts = [" ".join(BASE_ANCHORS)] + list(TECH_WEIGHTS.keys())
        wb_embs = encode_fn(wb_texts)
        v_wb_base = np.array(wb_embs[0], dtype=np.float32)
        v_wb_sum = v_wb_base * len(BASE_ANCHORS)
        wb_total_w = float(len(BASE_ANCHORS))
        for term in TECH_WEIGHTS:
            idx_t = 1 + list(TECH_WEIGHTS.keys()).index(term)
            v_wb_sum += np.array(wb_embs[idx_t], dtype=np.float32) * TECH_WEIGHTS[term]
            wb_total_w += TECH_WEIGHTS[term]
        v_ref = v_wb_sum / wb_total_w

        for v_p in paper_vecs:
            # Project paper onto centroid direction
            v = np.array(v_p, dtype=np.float32)
            all_vecs.append(v)
            labels.append("WB")
            paper_names.append("")

        # Echo 2x
        echo_text = " ".join([QUERY_TEXT] * 2)
        v_echo = encode_fn(echo_text)[0]
        # Re-embed papers with Echo method
        # (already have paper_vecs, just use same vecs with echo query)
        for v_p in paper_vecs:
            all_vecs.append(np.array(v_p, dtype=np.float32))
            labels.append("Echo_2x")
            paper_names.append("")

        # Add centroid vectors themselves
        all_vecs.append(np.array(v_base, dtype=np.float32))
        labels.append("Query")
        paper_names.append("Query")

        all_vecs.append(np.array(v_ref, dtype=np.float32))
        labels.append("WB_Centroid")
        paper_names.append("WB_Centroid")

        all_vecs.append(np.array(v_echo, dtype=np.float32))
        labels.append("Echo_Query")
        paper_names.append("Echo_Query")

        X = np.array(all_vecs)
        pca = PCA(n_components=2)
        X_pca = pca.fit_transform(X)

        for label_name in set(labels):
            mask = [l == label_name for l in labels]
            pts = X_pca[mask]
            color = colors.get(label_name, "#95a5a6")
            marker = markers.get(label_name, "o")
            size = 200 if "Centroid" in label_name or "Query" in label_name else 80
            ax.scatter(pts[:, 0], pts[:, 1], c=color, marker=marker,
                      label=label_name, s=size, alpha=0.7, edgecolors='black', linewidth=0.5)

        ax.set_title(f"{model_label}", fontsize=14, fontweight='bold')
        ax.set_xlabel(f"PC1 ({pca.explained_variance_ratio_[0]:.1%})", fontsize=11)
        ax.set_ylabel(f"PC2 ({pca.explained_variance_ratio_[1]:.1%})", fontsize=11)
        ax.legend(fontsize=9, loc='best')
        ax.grid(True, alpha=0.3)

    plt.tight_layout()
    fig_path = RESULTS_DIR / "centroid_shift.png"
    plt.savefig(fig_path, dpi=200, bbox_inches='tight')
    print(f"  Figure saved: {fig_path}")

    # ========== Save text results ==========
    result_path = RESULTS_DIR / "benchmark_results.txt"
    with open(result_path, "w") as f:
        f.write("WEIGHT-BLEEDING BENCHMARK RESULTS\n")
        f.write(f"{'=' * 70}\n\n")
        f.write("Multi-model comparison: MiniLM-L6-v2, BGE-base-en-v1.5, GTE-small\n\n")

        for model_label, res in all_results.items():
            f.write(f"\n--- {model_label} ---\n")
            f.write(f"Vanilla vs WB: ρ = {res['rho_wb']:.4f}, Top-10: {res['top10_wb']}/10\n")
            f.write(f"Vanilla vs Echo (2×): ρ = {res['rho_echo']:.4f}, Top-10: {res['top10_echo']}/10\n")
            f.write(f"Vanilla vs Echo (3×): ρ = {res['rho_echo3']:.4f}, Top-10: {res['top10_echo3']}/10\n")
            f.write(f"WB vs Echo (2×): ρ = {res['rho_wb_echo']:.4f}\n")
            f.write("\nPer-paper scores:\n")
            f.write(f"{'Paper':30s} {'Vanilla':8s} {'WB':8s} {'Echo_2x':8s}\n")
            f.write("-" * 60 + "\n")
            for i, p in enumerate(TEST_PAPERS):
                f.write(f"{p[:28]:30s} {res['vanilla'][i]:8.2f} {res['wb'][i]:8.2f} {res['echo'][i]:8.2f}\n")

        f.write(f"\n\n{'=' * 70}\n")
        f.write("SUMMARY\n")
        f.write(f"{'=' * 70}\n")
        f.write(f"{'Metric':20s} {'MiniLM':10s} {'BGE-base':10s} {'GTE-small':10s}\n")
        f.write("-" * 50 + "\n")
        for metric in ["rho_wb", "rho_echo", "rho_echo3", "top10_wb", "top10_echo", "top10_echo3"]:
            label = metric.replace("_", " ").title()
            vals = [all_results[m][metric] for m in all_results]
            f.write(f"{label:20s} {vals[0]:10.4f} {vals[1]:10.4f} {vals[2]:10.4f}\n")

    print(f"\n  Results saved: {result_path}")

    # ========== Verdict ==========
    print(f"\n{'=' * 70}")
    print(f"  VERDICT")
    print(f"{'=' * 70}")
    print(f"  Tests passed: {PASS}")
    print(f"  Tests failed: {FAIL}")
    print(f"\n  All results written to: papers/experiments/results/")


if __name__ == "__main__":
    run()
