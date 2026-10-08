"""The published version of a preprint, matched on evidence rather than on hope.

A title search returns the nearest record Crossref has, which on a preprint's
own title is frequently the preprint. Promoting that changes nothing and claims
something. The rules here are therefore the whole of the decision: what counts
as the same work, and what the code is allowed to conclude from it.

What it concludes is ``Likely``, never ``Yes``. A matching title and a shared
surname are strong evidence that a published version exists; they are not
evidence that anyone reviewed it. ``Peer_Reviewed`` is a claim about a process,
and a bibliographic search cannot witness a process.

The author check fires only when both sides carry authors. A preprint whose only
copy came from a source that publishes none — CORE and DOAJ do not — would
otherwise be rejected for a reason that has nothing to do with whether a
published version exists. ``checked_authors`` in the summary counts how many
matches had the second proof available, so a title-only acceptance is visible
rather than indistinguishable from a confirmed one.
"""

from typing import Any, Dict, Tuple

from .authors import split_authors

PREPRINT_LIKELY = "Likely"
PREPRINT = "No (Preprint)"

CROSSREF_PREPRINT_TYPE = "posted-content"


def normalize_title(value: Any) -> str:
    """The title reduced to what two records have to agree on.

    Case, punctuation and spacing differ between a preprint and its published
    version on every record that has both; the words do not. Only alphanumerics
    survive, so ``"SmartLLM: Smart Contract Auditing"`` and ``"SmartLLM — smart
    contract auditing"`` are one title.
    """
    kept = [character.lower() if character.isalnum() else " " for character in str(value or "")]
    return " ".join("".join(kept).split())


def surname(value: Any) -> str:
    """The family name out of either spelling this repository stores.

    Crossref publishes ``family`` and ``given`` separately, so its names arrive
    as ``"Lovelace, Ada"``; the sources that publish only a display name arrive
    as ``"Ada Lovelace"``. Both are reduced here, and neither is converted into
    the other anywhere else, because splitting a display name guesses at where
    the family name starts — wrong for ``van der Berg`` and wrong for a mononym.
    """
    text = " ".join(str(value or "").split())
    if not text:
        return ""
    if "," in text:
        return text.split(",", 1)[0].strip().lower()
    return text.split(" ")[-1].lower()


def surnames(value: Any) -> set:
    return {name for name in (surname(author) for author in split_authors(value)) if name}


def author_overlap(preprint_authors: Any, candidate_authors: Any) -> bool:
    """Whether the two name sets share a family name.

    One shared surname is the bar, not all of them: author lists are reordered
    and extended between a preprint and its published version, and requiring
    more would reject the matches that are real.
    """
    return bool(surnames(preprint_authors) & surnames(candidate_authors))


def match(preprint: Dict[str, Any], candidate: Dict[str, Any]) -> Tuple[bool, str]:
    """Whether a candidate record is the published version, and why not if not.

    The refusals are named rather than collapsed into ``False`` so the sidecar
    can say which bar failed. ``checked_authors`` is returned as the reason of an
    acceptance that had only the title to go on.
    """
    if not str(candidate.get("DOI") or "").strip():
        return False, "no_doi"
    if not normalize_title(candidate.get("Title")):
        return False, "no_title"
    if normalize_title(candidate.get("Title")) != normalize_title(preprint.get("Title")):
        return False, "title"
    if str(candidate.get("Type") or "").strip().lower() == CROSSREF_PREPRINT_TYPE:
        return False, "is_a_preprint"
    if str(candidate.get("DOI") or "").strip().lower() == str(preprint.get("DOI") or "").strip().lower():
        return False, "same_doi"
    if not surnames(preprint.get("Authors")) or not surnames(candidate.get("Authors")):
        return True, "title_only"
    if not author_overlap(preprint.get("Authors"), candidate.get("Authors")):
        return False, "authors"
    return True, "title_and_authors"


def best_match(preprint: Dict[str, Any], candidates: Any) -> Tuple[Dict[str, Any], str]:
    """The first candidate that clears every bar, and how it cleared them.

    First rather than best-scoring: Crossref orders by its own relevance, and a
    second ranking computed here would be a second opinion with no evidence
    behind it. A candidate that fails is not remembered — the record reported is
    the one that was accepted, or none.
    """
    if not isinstance(candidates, list):
        return {}, ""
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        accepted, reason = match(preprint, candidate)
        if accepted:
            return candidate, reason
    return {}, ""


def is_preprint(paper: Dict[str, Any], arxiv_id: str) -> bool:
    """Whether this is a paper whose published version is worth searching for.

    Two conditions, and both are asked. The status alone would search for a
    preprint that has no identifier to be the preprint *of*, and the identifier
    alone would re-search a paper whose own source already says it is published —
    a second query whose answer could only overwrite a better one.
    """
    return str(paper.get("Peer_Reviewed") or "") == PREPRINT and bool(arxiv_id)
