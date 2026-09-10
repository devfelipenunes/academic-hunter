"""Semantic paper screener using all-MiniLM-L6-v2 ONNX embeddings.

Weight-Bleeding: input-level term repetition biases bi-encoder sentence
embeddings toward high-weight technical terms via mean pooling.

Theoretical formula:
    v_bleeding = (N/(N+W)) * v + (W/(N+W)) * e_t

Implementation: instead of physically repeating terms in the reference
text (which creates artificial inputs), we compute the weighted centroid
directly in embedding space — mathematically equivalent but faster and
without the artificial-text problem.
"""

import hashlib
import json
import logging
import sys
import threading
from collections import OrderedDict
from typing import Any, Dict, List, Optional

import numpy as np

from .base import BaseScreener

logger = logging.getLogger("academic_hunter.semantic_screener")

_DEFAULT_EMBED_DIM = 384

#: Papers whose embeddings are kept. Bounded because a long run would otherwise
#: hold every abstract it ever scored in memory.
_PAPER_CACHE_MAX = 4096


class SemanticScreener(BaseScreener):
    """Scores papers via cosine similarity between paper embedding and a
    weighted centroid of config terms computed via embedding-space interpolation.

    Uses Weight-Bleeding: technical_weights scale each term's contribution
    in the reference centroid. The centroid is computed as:

        v_ref = (v_base * N_base + sum(W_i * v_term_i)) / (N_base + sum(W_i))

    where N_base is the number of base terms (anchors + technical_strings),
    W_i is each term's weight, and v_term_i is the embedding of term i.

    This approximates the effect of mean pooling over repeated tokens, but is
    not equivalent to it: ``v_base`` is a single embedding of the concatenated
    base vocabulary while ``N_base`` counts individual terms, and token
    truncation in the encoder breaks the correspondence further. Empirically
    the two formulations yield divergent rankings (Spearman rho = -0.2242 on
    the probe set in ``papers/experiments/cross_encoder_val.py``).
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self.model_name = model_name
        self._embedding_function: Optional[Any] = None
        self._cached_base: Dict[str, Dict[str, np.ndarray]] = {}
        #: Paper text -> embedding. Bounded LRU; guarded by its own lock so a
        #: threaded run cannot corrupt it.
        self._paper_cache: "OrderedDict[str, np.ndarray]" = OrderedDict()
        self._cache_lock = threading.Lock()

    def _embed_paper(self, text: str) -> np.ndarray:
        """Embed the paper text, reusing a previous result when it repeats.

        The pipeline scores the same paper more than once — at validation, again
        after a duplicate merge, and again by the rank step's backfill for any
        paper whose component score was invalidated — and each call used to
        re-encode the identical string. Measured cost on CPU is about 1.5 s per
        document with an abstract, so the repeats are not a rounding error.

        The embedding runs outside the lock: two threads racing on the same
        unseen text would compute the same vector twice, which is harmless,
        whereas holding the lock across a one-second encode would serialise the
        whole run.
        """
        with self._cache_lock:
            cached = self._paper_cache.get(text)
            if cached is not None:
                self._paper_cache.move_to_end(text)
                return cached

        vector = np.array(self.embedding_function([text])[0], dtype=np.float32)

        with self._cache_lock:
            self._paper_cache[text] = vector
            self._paper_cache.move_to_end(text)
            while len(self._paper_cache) > _PAPER_CACHE_MAX:
                self._paper_cache.popitem(last=False)
        return vector

    def evaluate(self, paper_data: Dict[str, Any], config: Dict[str, Any]) -> float:
        """Semantic relevance score (0-1) between paper and config terms.

        Embeds paper title + abstract, then computes a weighted reference
        centroid via embedding-space interpolation:

            v_ref = (v_base * N + sum(W_i * v_i)) / (N + sum(W_i))

        This approximates mean pooling over repeated tokens without creating
        artificially repetitive input strings; see the class docstring for why
        the two are not equivalent in practice.

        Caches base + term embeddings across calls since they depend only on
        the config (same for all papers in a run), and paper embeddings keyed by
        text — see :meth:`_embed_paper` for why the latter matters.
        """
        paper_text = self._extract_paper_text(paper_data)
        if not paper_text:
            return 0.0

        base_parts, tech_weights = self._parse_config(config)
        if not base_parts and not tech_weights:
            return 0.0

        v_ref = self._get_ref_centroid(base_parts, tech_weights)
        v_paper = self._embed_paper(paper_text)

        similarity = self._cosine(v_paper, v_ref)
        logger.debug(
            "Semantic score for '%s': %.4f",
            (paper_data.get("title") or paper_data.get("Title") or "")[:60],
            similarity,
        )
        return similarity


    @staticmethod
    def _extract_paper_text(paper_data: Dict[str, Any]) -> str:
        """Concatenate title and abstract, accepting both snake_case and Title_Case keys."""
        title = str(paper_data.get("title") or paper_data.get("Title") or "")
        abstract = str(paper_data.get("abstract") or paper_data.get("Abstract") or "")
        return f"{title} {abstract}".strip()

    @staticmethod
    def _parse_config(config: Dict[str, Any]):
        """Extract base_parts list and tech_weights dict from a config dict."""
        base_parts: List[str] = []
        for terms in config.get("anchors", {}).values():
            if isinstance(terms, list):
                base_parts.extend(terms)
        for terms in config.get("technical_strings", {}).values():
            if isinstance(terms, list):
                base_parts.extend(terms)
        tech_weights: Dict[str, float] = config.get("technical_weights", {})
        return base_parts, tech_weights

    def _get_ref_centroid(
        self,
        base_parts: List[str],
        tech_weights: Dict[str, float],
    ) -> np.ndarray:
        """Return the cached weighted-centroid reference vector for this config.

        Computes and caches on first call; subsequent calls with the same
        (base_parts, tech_weights) are O(1) dict lookups.
        """
        config_hash = self._config_hash(base_parts, tech_weights)
        if config_hash not in self._cached_base:
            self._cached_base[config_hash] = self._compute_ref_centroid(
                base_parts, tech_weights
            )
        return self._cached_base[config_hash]

    def _compute_ref_centroid(
        self,
        base_parts: List[str],
        tech_weights: Dict[str, float],
    ) -> np.ndarray:
        """Embed base text + individual terms, then build the weighted centroid.

        Formula:
            v_sum   = v_base * N_base  +  Σ (W_i * v_term_i)
            total_w = N_base           +  Σ W_i
            v_ref   = v_sum / total_w
        """
        unique_terms = list(tech_weights.keys())

        # 1. Embed base text (anchors) + each technical term
        texts: List[str] = []
        if base_parts:
            texts.append(" ".join(base_parts))
        texts.extend(unique_terms)

        embeddings = self.embedding_function(texts)

        # 2. Base contribution (zero if no anchors)
        if base_parts:
            v_base = np.array(embeddings[0], dtype=np.float32)
            term_embeds = embeddings[1:]
            n_base = len(base_parts)
        else:
            v_base = np.zeros(_DEFAULT_EMBED_DIM, dtype=np.float32)
            term_embeds = embeddings
            n_base = 0

        v_sum = v_base * n_base
        total_w = float(n_base)

        # 3. Add each technical term weighted by its importance
        for term, raw in zip(unique_terms, term_embeds):
            v_term = np.array(raw, dtype=np.float32)
            w = tech_weights[term]
            v_sum += v_term * w
            total_w += w

        return v_sum / max(total_w, 1e-10)

    @staticmethod
    def _config_hash(base_parts: List[str], tech_weights: Dict[str, float]) -> str:
        """Stable MD5 of the config signature used as cache key."""
        sig = json.dumps({"bp": base_parts, "tw": tech_weights}, sort_keys=True)
        return hashlib.md5(sig.encode()).hexdigest()

    def _cosine(self, a: np.ndarray, b: np.ndarray) -> float:
        """Cosine similarity between two vectors, clamped to ``[0, 1]``.

        A raw cosine goes negative for weakly correlated vectors, and this score
        feeds ``sqrt(...)`` downstream, where a negative raises ``ValueError``.
        """
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a < 1e-10 or norm_b < 1e-10:
            return 0.0
        return max(0.0, float(np.dot(a, b) / (norm_a * norm_b)))


    @property
    def embedding_function(self):
        """Lazy-load ChromaDB's ONNX embedding function."""
        if self._embedding_function is None:
            try:
                from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
                self._embedding_function = DefaultEmbeddingFunction()
                logger.info("ONNX embedding function initialized (%s).", self.model_name)
            except Exception as e:
                logger.warning(
                    "Failed to load embedding function — falling back to zero vectors: %s", e
                )
                self._embedding_function = _ZeroEmbedding(_DEFAULT_EMBED_DIM)
        return self._embedding_function

    @property
    def degraded(self) -> bool:
        """True once the embedding fell back to zero vectors.

        Every semantic score is 0.0 in that state, and the run still finishes —
        so in embedding or hybrid mode it produces a full report whose numbers
        look real. Callers that report results should say so.
        """
        return isinstance(self._embedding_function, _ZeroEmbedding)


class _ZeroEmbedding:
    """Fallback embedding that returns zero vectors.

    Used when ChromaDB/ONNX is unavailable. All semantic scores will be 0.0,
    effectively disabling Weight-Bleeding scoring. Keyword-only and hybrid
    modes still work, but embedding-only mode will produce zero scores.
    """

    def __init__(self, dim: int = _DEFAULT_EMBED_DIM) -> None:
        self._dim = dim
        logger.warning(
            "Semantic screener running in ZERO-VECTOR mode — all semantic scores "
            "will be 0.0. Install chromadb with ONNX support for full functionality:\n"
            "  pip install chromadb>=1.5.0"
        )
        print(
            "[WARNING] Academic Hunter: Semantic screener in zero-vector mode. "
            "All semantic scores will be 0.0. Install chromadb with ONNX support.",
            file=sys.stderr,
        )

    def __call__(self, texts):
        return [np.zeros(self._dim, dtype=np.float32) for _ in texts]
