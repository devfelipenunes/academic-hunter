"""Locating the sentence a position sits in.

Shared by the number and the citation verifier: both report *where* a claim was
found, and each carried its own byte-identical copy of this.
"""

import re

SENTENCE = re.compile(r"[^.!?]*[.!?]")


def sentence_around(text: str, position: int) -> str:
    """The sentence containing ``position``, collapsed to one line."""
    start = 0
    for sentence in SENTENCE.finditer(text[:position]):
        start = sentence.end()
    end_match = SENTENCE.search(text, position)
    end = end_match.end() if end_match else len(text)
    return " ".join(text[start:end].split())
