# Review — Academic Hunter: Paper Preparation

## ✅ Concluído

### Paper (papers/joss-2026/)

- [x] paper.md completo (Summary, Need, Architecture, Related Work, Experiments, Conclusion, Availability)
- [x] paper.bib com 13 referências (adicionado: all-MiniLM-L6-v2, LLM2Vec, GRIT, ONNX)
- [x] Diagrama de arquitetura hexagonal
- [x] Overlap analysis incorporada (92.7% compartilhado, 3 papers únicos do embedding)
- [x] $\sqrt{\sigma}$ output scaling documentado com comparação de 6 transforms
- [x] Exemplo concreto: overlap analysis com dados reais
- [x] Ablation study re-run com $\sqrt{\sigma}$ (242 keyword, 238 embedding, 242 hybrid)
- [x] Cross-encoder validation (Spearman $\rho$: vanilla 0.345, WB 0.212)
- [x] Weight sensitivity (4 ordenações distintas)
- [x] Threshold analysis (3.5 mantido, justificado pelo anchor filter)
- [x] LLM2Vec e GRIT adicionados ao Related Work
- [x] Footnote sobre variação de API entre runs

### Experimentos (papers/experiments/)

- [x] `run_ablation.py` — script funcional, re-run com $\sqrt{\sigma}$
- [x] `verify_scoring.py` — 20/20 testes, atualizado com $\sqrt{\sigma}$
- [x] `cross_encoder_val.py` — com term repetition real (baseado em technical_weights)
- [x] `weight_sensitivity.py` — 4 ordenações distintas
- [x] `overlap_analysis.py` — executado: 3 papers únicos do embedding
- [x] Benchmark 6 transforms (linear, sqrt, cube_root, log1p, quadratic, sigmoid)

### Código

- [x] Score híbrido conectado ao pipeline
- [x] Weight-Bleeding (term repetition em bi-encoder)
- [x] $\sqrt{\sigma}$ output scaling implementado
- [x] ChromaDB fixes (fórmula L2, hash ID, cleanup)
- [x] Ablation mode (keyword/embedding/hybrid)
- [x] 21 testes de validação (unitários + integração)
- [x] MCP server com 15 tools funcionando (6.961 papers indexados)

## 📋 Pendente (você faz)

- [ ] **Criar ORCID** em orcid.org (5 min)
- [ ] **Gerar DOI Zenodo** em zenodo.org (5 min, quando for submeter)
- [ ] `git add papers/ .github/` e commitar (git add papers/ para incluir os papers no repositório)
