from typing import Any

from .authors import split_authors
from .utils import arxiv_id_from_url

PEER_REVIEW_PRIORITY = {"Yes": 3, "Likely": 2, "No (Preprint)": 1, "N/A": 0}

UNKNOWN_YEAR = "N/A"


def strategy_max(old: Any, new: Any, **kwargs) -> int:
    return max(int(old or 0), int(new or 0))

def strategy_first_non_empty(old: Any, new: Any, **kwargs) -> Any:
    return old if old else new

def strategy_url(old: Any, new: Any, **kwargs) -> str:
    """The URL that addresses the work, chosen the same way in every run.

    ``strategy_first_non_empty`` kept whichever copy the mining threads happened
    to register first, and the two copies of one preprint do not carry equivalent
    URLs: the arXiv copy carries ``arxiv.org/abs/...`` and the CORE copy carries a
    landing page. The citation backfill derives its identifier from the merged
    ``URL`` (``_citation_key``), so a paper with no DOI was asked about — or
    written off — depending on which thread won. Measured over seven runs of one
    corpus: the same paper reported 9 citations or 0, and the provenance counters
    moved with it.

    A URL that yields an arXiv id therefore wins over one that does not. That is
    the same preference ``_citation_key`` already applies between the DOI and the
    arXiv id, one level down: an address beats a landing page.

    With neither side resolving, the lexicographically smaller wins. Arbitrary,
    but the same side in every run, which is the whole point — ``paper_order_key``
    makes the same bargain for row order. The merge hands this function the two
    source names as well, so a future rule could prefer the more authoritative
    source instead, the way ``strategy_venue`` does.
    """
    old_str = str(old or "")
    new_str = str(new or "")
    if not old_str:
        return new_str
    if not new_str:
        return old_str
    old_id = arxiv_id_from_url(old_str)
    new_id = arxiv_id_from_url(new_str)
    if bool(old_id) != bool(new_id):
        return old_str if old_id else new_str
    return min(old_str, new_str)

def strategy_longest_string(old: Any, new: Any, **kwargs) -> str:
    old_str = str(old or "")
    new_str = str(new or "")
    return new_str if len(new_str) > len(old_str) else old_str

def strategy_authors(old: Any, new: Any, **kwargs) -> str:
    """The more complete author list, chosen the same way in every run.

    A source that returns a truncated list — three of nine authors — is not
    disagreeing with the source that returns all nine, it is answering less, so
    the longer list wins. That is the whole rule when the two differ in length.

    When they do not, both sources named the same number of authors and one of
    them is the one to print; keeping whichever arrived first would make the
    exported reference depend on which mining thread won, which is the defect
    ``strategy_url`` removed one field over. The lexicographically smaller
    sequence wins instead — arbitrary, but the same side in every run, the same
    bargain ``paper_order_key`` and the second tier of ``strategy_url`` make.

    Author order is preserved because a citation reproduces it, which is why
    this cannot be ``strategy_set_join``.
    """
    old_list = split_authors(old)
    new_list = split_authors(new)
    if not old_list:
        return "; ".join(new_list)
    if not new_list:
        return "; ".join(old_list)
    if len(new_list) > len(old_list):
        chosen = new_list
    elif len(new_list) < len(old_list):
        chosen = old_list
    else:
        chosen = min(old_list, new_list)
    return "; ".join(chosen)

def strategy_year(
    old: Any, new: Any, old_peer: str = None, new_peer: str = None, **kwargs
) -> Any:
    """The year of the copy whose peer-review claim is the stronger one.

    ``Year`` had no strategy, so the merge kept whichever copy the mining
    threads registered first and a copy that carried no year was never filled in
    — the defect ``strategy_url`` removed one field over. The two copies of a
    work do not disagree about its year so much as describe two versions of it:
    the arXiv posting is earlier than the paper it became, and the year a review
    cites is the year of the version that was published. Which copy that is, is
    exactly what ``Peer_Reviewed`` states, so the ranking that decides that
    field decides this one instead of a second ranking invented here.

    An unstated year never wins over a stated one. When the two copies claim the
    same status they are describing the same kind of record, and the earlier
    year wins — arbitrary, but the same side in every run, the same bargain
    ``strategy_url`` and ``strategy_authors`` make.

    The limit is ``strategy_peer_reviewed``'s: a copy whose status is unknown
    cannot outrank one that states a status, so only what the sources claim can
    be preferred, and this cannot rescue a year held by a source that says
    nothing about review.
    """
    old_text = str(old or "").strip()
    new_text = str(new or "").strip()
    if new_text in ("", UNKNOWN_YEAR):
        return old
    if old_text in ("", UNKNOWN_YEAR):
        return new
    new_rank = PEER_REVIEW_PRIORITY.get(str(new_peer or "N/A"), 0)
    old_rank = PEER_REVIEW_PRIORITY.get(str(old_peer or "N/A"), 0)
    if new_rank != old_rank:
        return new if new_rank > old_rank else old
    return old if old_text <= new_text else new

def strategy_set_join(old: Any, new: Any, **kwargs) -> str:
    old_set = set(str(old or "").split(", "))
    new_set = set(str(new or "").split(", "))
    merged = old_set | new_set
    return ", ".join(sorted(filter(None, merged)))

def strategy_anchor_category(old: Any, new: Any, anchor_cat: str = None, **kwargs) -> str:
    items = set(str(old or "").split(", "))
    if anchor_cat:
        items.add(anchor_cat)
    return ", ".join(sorted(filter(None, items)))

def strategy_tech_category(old: Any, new: Any, tech_cat: str = None, **kwargs) -> str:
    items = set(str(old or "").split(", "))
    if tech_cat:
        items.add(tech_cat)
    return ", ".join(sorted(filter(None, items)))

def strategy_venue(old: Any, new: Any, old_source: str = None, new_source: str = None, **kwargs) -> str:
    old_str = str(old or "Unknown Venue")
    new_str = str(new or "")
    if (old_str in [None, "", "Unknown Venue", "ArXiv"] or 
        (old_source == "ArXiv" and new_source != "ArXiv")) and new_str:
        return new_str
    return old_str

def strategy_peer_reviewed(old: Any, new: Any, **kwargs) -> str:
    new_status = str(new or "N/A")
    existing_status = str(old or "N/A")
    if PEER_REVIEW_PRIORITY.get(new_status, 0) > PEER_REVIEW_PRIORITY.get(existing_status, 0):
        return new_status
    return existing_status
