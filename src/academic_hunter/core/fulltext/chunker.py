"""Split an extracted document into section-aware, retrievable fragments.

Pure: no I/O, no dependency on the extractor that produced the text.

The chunk size is not a tuning knob. ChromaDB's default embedding is MiniLM
through ONNX, capped at 256 word-pieces — roughly 190 words of academic prose.
Anything longer is silently truncated *by the embedder*, so the tail of every
chunk would be invisible to retrieval without anything reporting it. Hence 180
words, with 40 of overlap so a sentence on a boundary survives in one piece.
"""

import re
from dataclasses import dataclass
from typing import List, Sequence

from ..ports.fulltext import ExtractedDocument

#: Words per chunk. Imposed by the embedder's 256 word-piece cap — see module docstring.
TARGET_WORDS = 180

#: Words shared between consecutive chunks, so a boundary-crossing sentence survives.
OVERLAP_WORDS = 40

#: Shorter than this and a fragment carries no retrievable signal.
MIN_CHUNK_WORDS = 25

#: Section headings, matched case-insensitively against a title-cased line.
#: Order matters only for the aliases of the same target.
_SECTION_ALIASES = {
    "abstract": ("abstract", "summary"),
    "introduction": ("introduction", "background"),
    "related_work": ("related work", "literature review", "prior work"),
    "method": ("method", "methods", "methodology", "materials and methods",
               "approach", "materials"),
    "results": ("results", "findings", "experiments", "evaluation",
                "results and discussion"),
    "discussion": ("discussion",),
    "conclusion": ("conclusion", "conclusions", "concluding remarks"),
    "references": ("references", "bibliography", "works cited"),
    "appendix": ("appendix", "appendices", "supplementary material",
                 "supporting information"),
    "acknowledgements": ("acknowledgements", "acknowledgments", "funding"),
}

#: Dropped by default: 20-40% of a paper's text, matching queries about author
#: names rather than content, and it poisons the retrieval pool.
_DROPPED_BY_DEFAULT = ("references", "appendix")

#: A heading is a short line that is not a sentence.
_MAX_HEADING_CHARS = 70
_WORD = re.compile(r"\S+")


@dataclass(frozen=True)
class Section:
    """A named span of the document."""

    name: str
    start: int
    end: int


@dataclass(frozen=True)
class Chunk:
    """A retrievable fragment, with enough metadata to trace it back."""

    chunk_id: str
    parent_id: str
    text: str
    section: str
    index: int
    start: int
    end: int


def _classify(line: str) -> str:
    """The section a heading line names, or "" if it is not a heading."""
    stripped = line.strip().strip(".:#* ").lower()
    if not stripped or len(stripped) > _MAX_HEADING_CHARS:
        return ""
    # Strip a leading numbering ("2.", "2.1", "III.") before matching.
    stripped = re.sub(r"^(?:\d+(?:\.\d+)*|[ivxlc]+)[.)]?\s+", "", stripped)
    for name, aliases in _SECTION_ALIASES.items():
        for alias in aliases:
            if stripped == alias:
                return name
    return ""


def detect_sections(text: str) -> List[Section]:
    """Split ``text`` at its headings, returning spans in document order.

    Anything before the first heading becomes a ``preamble`` span, so the caller
    can drop it: that region holds authors, affiliations and copyright notices,
    none of which is the paper's content.
    """
    sections: List[Section] = []
    offset = 0
    current_name = "preamble"
    current_start = 0

    for line in text.splitlines(keepends=True):
        name = _classify(line)
        if name:
            if offset > current_start:
                sections.append(Section(current_name, current_start, offset))
            current_name = name
            # Start past the heading line: the heading is a label, not content,
            # and letting it in puts "1. Introduction" at the head of the chunk.
            current_start = offset + len(line)
        offset += len(line)

    if offset > current_start:
        sections.append(Section(current_name, current_start, offset))
    return sections


def _chunk_span(
    text: str,
    span_start: int,
    span_end: int,
    section: str,
    parent_id: str,
    base_index: int,
    *,
    target_words: int,
    overlap_words: int,
    min_chunk_words: int,
    whole_span: bool,
) -> List[Chunk]:
    """Fragment one span of ``text``, never letting a chunk cross its boundary.

    ``text`` is the whole document and the span is given as absolute offsets, so
    the slice that becomes the chunk and the offsets recorded on it come from the
    same coordinates — slicing a section-local string while recording
    document-local offsets silently produces chunks that point at other sections.
    """
    body = text[span_start:span_end]
    words = list(_WORD.finditer(body))
    if not words:
        return []

    step = max(1, target_words - overlap_words)
    chunks: List[Chunk] = []
    position = 0

    while position < len(words):
        window = words[position:position + target_words]
        # A short tail is dropped rather than merged into the previous chunk:
        # merging would push that chunk past the embedder's cap.
        if len(window) < min_chunk_words and chunks:
            break

        start = span_start + window[0].start()
        end = span_start + window[-1].end()
        index = base_index + len(chunks)
        chunks.append(Chunk(
            chunk_id=f"{parent_id}::{index}",
            parent_id=parent_id,
            text=text[start:end],
            section=section,
            index=index,
            start=start,
            end=end,
        ))

        if whole_span or len(window) < target_words:
            break
        position += step

    return chunks


def chunk_document(
    doc: ExtractedDocument,
    parent_id: str,
    *,
    target_words: int = TARGET_WORDS,
    overlap_words: int = OVERLAP_WORDS,
    min_chunk_words: int = MIN_CHUNK_WORDS,
    include_references: bool = False,
) -> List[Chunk]:
    """Fragment ``doc`` into chunks, in document order.

    The abstract becomes exactly one chunk: it is already a curated summary, and
    splitting it would scatter the densest signal in the paper. The preamble is
    dropped, and so are references and appendices unless asked for.
    """
    if not doc.text or not doc.text.strip():
        return []

    dropped = () if include_references else _DROPPED_BY_DEFAULT
    chunks: List[Chunk] = []

    for section in detect_sections(doc.text):
        if section.name in dropped or section.name == "preamble":
            continue
        chunks.extend(_chunk_span(
            doc.text,
            section.start,
            section.end,
            section.name,
            parent_id,
            base_index=len(chunks),
            target_words=target_words,
            overlap_words=overlap_words,
            min_chunk_words=min_chunk_words,
            whole_span=(section.name == "abstract"),
        ))
    return chunks
