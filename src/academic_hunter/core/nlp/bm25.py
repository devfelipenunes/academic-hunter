"""BM25 — the lexical signal the pipeline was missing.

The existing "keyword" score is a weighted count of configured anchor and
technical terms. It is computed once per document and **never sees the query**:
it answers "how much does this paper look like the domain?", not "how much does
it look like what was asked?". That is why the evaluation found every strategy
to be query-independent, and why the best strategy turned out to depend on the
topic rather than on the question.

BM25 is conditional on the query by construction, which makes it the first
signal in this pipeline that can distinguish between two information needs
inside the same domain. It is also cheap: pure counting, no model, no network.

Implementations follow the standard formulation (Robertson & Zaragoza, 2009):

    score(q, d) = Σ_t IDF(t) · (f(t,d) · (k1 + 1)) / (f(t,d) + k1 · (1 - b + b · |d|/avgdl))

with the probabilistic IDF ``ln(1 + (N - n(t) + 0.5) / (n(t) + 0.5))``, which
stays positive for terms that appear in every document — the plain
``ln((N - n + 0.5)/(n + 0.5))`` form goes negative there and would let a common
term penalise a match.
"""

import math
import re
from collections import Counter
from typing import Dict, List, Sequence

#: Match the tokenizer used elsewhere in the project: lowercase alphanumeric runs.
_TOKEN = re.compile(r"[a-z0-9]+")

DEFAULT_K1 = 1.5
DEFAULT_B = 0.75


def tokenize(text: str) -> List[str]:
    """Lowercase alphanumeric tokens.

    No stemming and no stopword list. Stemming would make the scores harder to
    explain to a reviewer reading the PRISMA trail, and BM25's IDF already
    discounts terms that appear everywhere.
    """
    return _TOKEN.findall(str(text).lower())


class BM25:
    """A BM25 index over a fixed candidate set.

    Built over the pool that will be ranked, because IDF and the average
    document length are properties of the candidate set. Scoring a paper against
    statistics from a different corpus would produce numbers that cannot be
    compared with its neighbours'.
    """

    def __init__(
        self,
        documents: Sequence[str],
        k1: float = DEFAULT_K1,
        b: float = DEFAULT_B,
    ) -> None:
        self.k1 = k1
        self.b = b
        self.n_documents = len(documents)

        self._term_frequencies: List[Counter] = []
        self._lengths: List[int] = []

        for text in documents:
            tokens = tokenize(text)
            self._term_frequencies.append(Counter(tokens))
            self._lengths.append(len(tokens))

        total = sum(self._lengths)
        self.avg_length = total / self.n_documents if self.n_documents else 0.0

        document_frequency: Counter = Counter()
        for frequencies in self._term_frequencies:
            document_frequency.update(frequencies.keys())
        self._document_frequency: Dict[str, int] = dict(document_frequency)

    def idf(self, term: str) -> float:
        """Inverse document frequency, always strictly positive."""
        n = self._document_frequency.get(term, 0)
        if n == 0:
            # A term no document contains cannot discriminate; contributing 0
            # (rather than the IDF it would have) keeps unseen query terms from
            # shifting the scale.
            return 0.0
        return math.log(1.0 + (self.n_documents - n + 0.5) / (n + 0.5))

    def score(self, query: str) -> List[float]:
        """Score every document against ``query``, in the order they were given.

        Duplicate query terms are counted once. BM25 is a bag-of-words model, so
        a repeated term carries no extra information, and counting it twice
        would let a user inflate a term by typing it again — which is the job of
        the configurable weights, done openly.
        """
        scores = [0.0] * self.n_documents
        if not self.n_documents or self.avg_length == 0:
            return scores

        for term in set(tokenize(query)):
            idf = self.idf(term)
            if idf == 0.0:
                continue

            for i, frequencies in enumerate(self._term_frequencies):
                frequency = frequencies.get(term)
                if not frequency:
                    continue
                denominator = frequency + self.k1 * (
                    1.0 - self.b + self.b * self._lengths[i] / self.avg_length
                )
                scores[i] += idf * (frequency * (self.k1 + 1.0)) / denominator

        return scores


def bm25_scores(
    query: str,
    documents: Sequence[str],
    k1: float = DEFAULT_K1,
    b: float = DEFAULT_B,
) -> List[float]:
    """Convenience wrapper for scoring one query against a corpus.

    Builds the index each call, so it is for one-shot use. Ranking several
    queries over the same corpus should construct :class:`BM25` once and call
    :meth:`BM25.score` — the index is the expensive part.
    """
    return BM25(documents, k1=k1, b=b).score(query)
