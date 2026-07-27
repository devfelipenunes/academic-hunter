#!/usr/bin/env python3
"""Score Validation Suite — Test all scoring approaches and find the best one.

Usage:
    python papers/experiments/validate_scoring.py
"""

import sys
from pathlib import Path
SRC = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(SRC))

import numpy as np
from academic_hunter.plugins.vector_stores import ChromaVectorStore
from academic_hunter.core.infra.config import HunterConfig
from academic_hunter.core.nlp import AcademicScorer
from academic_hunter.plugins.screeners.semantic import SemanticScreener

# === SETUP ===
store = ChromaVectorStore()
col = store._get_or_create_collection('papers')
cfg = HunterConfig()
scorer = AcademicScorer(cfg.anchors, cfg.tech_strings, cfg.tech_weights, cfg.context_rules, cfg.settings)
screener = SemanticScreener()
sem_config = {'anchors': cfg.anchors, 'technical_strings': cfg.tech_strings, 'technical_weights': cfg.tech_weights}

# Coleta dados
kw_list, sem_list, titles = [], [], []
for tema in ['sentence embedding transformer bi encoder systematic review',
             'blockchain government digital identity public sector',
             'ISO 20022 SWIFT cross border payment financial messaging',
             'post quantum cryptography lattice Kyber Dilithium']:
    results = col.query(query_texts=[tema], n_results=40)
    for i in range(len(results['ids'][0])):
        meta = results['metadatas'][0][i]
        title = results['documents'][0][i].split('\n\n')[0]
        abstract = results['documents'][0][i].split('\n\n')[1] if '\n\n' in results['documents'][0][i] else ''
        p = {'Title': title, 'Abstract': abstract, 'Year': int(meta.get('year', 2020) or 2020), 'Citations': int(meta.get('citations', 0) or 0)}
        kw_list.append(scorer.calculate_score(title, abstract, p['Citations']))
        sem_list.append(screener.evaluate(p, sem_config))
        titles.append(title[:60])

kw, sem = np.array(kw_list), np.array(sem_list)
print(f"Dataset: {len(kw)} papers | kw: mean={kw.mean():.1f} std={kw.std():.1f} | sem: mean={sem.mean():.3f} std={sem.std():.3f}")

# === SCORING APPROACHES ===
def rank(arr):
    n = len(arr)
    if n < 2: return np.array([0.5])
    r = np.empty(n)
    r[np.argsort(arr)] = np.arange(n) / (n - 1)
    return r

scores = {
    "A) Cosseno puro": sem.copy(),
    "B) Cosseno x10": sem * 10,
    "C) Cosseno x20": sem * 20,
    "D) x10 + kwx0.3": sem * 10 + kw * 0.3,
    "E) Rank WB": rank(sem) * 10,
    "F) Rank KW": rank(kw) * 10,
    "G) * Rank 70wb/30kw": (rank(sem) * 0.7 + rank(kw) * 0.3) * 10,
    "H) Rank 50/50": (rank(sem) * 0.5 + rank(kw) * 0.5) * 10,
    "I) MinMax cosseno": (sem - sem.min()) / (sem.max() - sem.min() + 1e-10) * 10,
    "J) MinMax hibrido": ((sem * 10 + kw * 0.3) - (sem * 10 + kw * 0.3).min()) / ((sem * 10 + kw * 0.3).max() - (sem * 10 + kw * 0.3).min() + 1e-10) * 10,
}

# === TEST 1: DISTRIBUICAO ===
print("\n" + "=" * 90)
print("  TESTE 1: DISTRIBUICAO")
print("=" * 90)
print(f"  {'Metodo':<30} {'Media':>6} {'Std':>6} {'Min':>6} {'Max':>6} {'≥5':>5} {'≥3.5':>6} {'Unicos':>6}")
print(f"  {'-'*30} {'-'*6} {'-'*6} {'-'*6} {'-'*6} {'-'*5} {'-'*6} {'-'*6}")

for name, s in scores.items():
    print(f"  {name:<30} {s.mean():>6.2f} {s.std():>6.2f} {s.min():>6.2f} {s.max():>6.2f} {sum(s>=5):>5} {sum(s>=3.5):>6} {len(set(np.round(s,1))):>6}")

# === TEST 2: TOP-10 ===
print("\n" + "=" * 90)
print("  TESTE 2: TOP-10 (quantos papers realmente relevantes estao no topo?)")
print("=" * 90)
relevantes = {i for i in range(len(kw)) if kw[i] > 5 and sem[i] > 0.45}
golden = {i for i in range(len(kw)) if kw[i] > 8 and sem[i] > 0.50}
print(f"  Relevantes (kw>5 e sem>0.45): {len(relevantes)} | Golden (kw>8 e sem>0.50): {len(golden)}")

for name, s in scores.items():
    top10 = set(np.argsort(s)[-10:])
    n_rel = len(top10 & relevantes)
    n_gold = len(top10 & golden)
    print(f"  {name:<30} relevantes={n_rel:>2}/10  golden={n_gold:>2}/10")

# === TEST 3: ROBUSTEZ ===
print("\n" + "=" * 90)
print("  TESTE 3: ROBUSTEZ (outlier distorce?)")
print("=" * 90)
kw2 = np.concatenate([kw, [100.0]])
sem2 = np.concatenate([sem, [0.3]])

for name, s in scores.items():
    r2 = rank(kw2) if "Rank" in name and "KW" in name else (
         rank(sem2) if name == "E) Rank WB" else (
         (rank(sem2) * 0.7 + rank(kw2) * 0.3) * 10 if name == "G) * Rank 70wb/30kw" else (
         (rank(sem2) * 0.5 + rank(kw2) * 0.5) * 10 if name == "H) Rank 50/50" else None
    )))
    if r2 is not None:
        delta = abs(s.mean() - r2[:len(s)].mean())
        print(f"  {name:<30} distorcao={delta:.4f} {'OK' if delta < 0.5 else 'IMPACTO!'}")
    elif "Cosseno" in name or "x10" in name or "x20" in name or "x10 + kw" in name:
        s2 = sem2 * (10 if "x10" in name else 20 if "x20" in name else 1) + (kw2 * 0.3 if "kw" in name else 0)
        delta = abs(s.mean() - s2[:len(s)].mean())
        print(f"  {name:<30} distorcao={delta:.4f} {'OK' if delta < 1.0 else 'IMPACTO!'}")
    elif "MinMax" in name:
        print(f"  {name:<30} (pula - minmax sempre se adapta)")

# === TEST 4: PAPEL DO THRESHOLD ===
print("\n" + "=" * 90)
print("  TESTE 4: THRESHOLD (quantos passam com 3.5, 5.0, 7.0?)")
print("=" * 90)
for name, s in scores.items():
    for th in [3.5, 5.0, 7.0]:
        print(f"  {name:<30} threshold={th:.1f} -> {sum(s>=th)}/{len(s)}")

# === CONCLUSAO ===
print("\n" + "=" * 90)
print("  CONCLUSAO")
print("=" * 90)
composite = {}
for name, s in scores.items():
    relevantes_top10 = len(set(np.argsort(s)[-10:]) & {i for i in range(len(kw)) if kw[i] > 5 and sem[i] > 0.45})
    composite[name] = s.std() * 10 + len(set(np.round(s, 1))) + relevantes_top10 * 3
    print(f"  {name:<30} composto={composite[name]:.0f} (std*10={s.std()*10:.0f} + unicos={len(set(np.round(s, 1)))} + top10_rel={relevantes_top10}*3)")

best = max(composite, key=composite.get)
print(f"\n  ★ MELHOR: {best}")
print(f"  ★ Score composto: {composite[best]}")
print(f"  ★ Std={scores[best].std():.2f} | Unicos={len(set(np.round(scores[best], 1)))} | 3.5={sum(scores[best]>=3.5)}/{len(scores[best])}")
