"""Locating the sentence a position sits in.

Shared by the number and the citation verifier: both report *where* a claim was
found, and each carried its own byte-identical copy of this.
"""

import re

_DOT_INSIDE = r"(?:[^.!?]|[.!?](?!\s|$))*"
SENTENCE = re.compile(_DOT_INSIDE + r"[.!?]+(?=\s|$)|" + _DOT_INSIDE + r"$")


def sentence_around(text: str, position: int) -> str:
    """The sentence containing ``position``, collapsed to one line.

    A ``.`` only ends a sentence when whitespace or the end of the text follows
    it. Splitting on every terminator cut a sentence in half at each decimal
    point, so a claim of ``92.7%`` was reported with the context ``7% in the
    ablation.`` — the reader lost the half that said what the figure measured,
    which is the only reason the context is reported at all.

    The two branches also partition the text: everything up to a boundary
    terminator, or the trailing run that carries none. That is what keeps
    ``finditer`` from resuming mid-sentence and returning a fragment.
    """
    if not text:
        return ""
    position = max(0, min(position, len(text) - 1))
    for match in SENTENCE.finditer(text):
        if match.start() <= position < match.end():
            return " ".join(match.group().split())
    return " ".join(text.split())
