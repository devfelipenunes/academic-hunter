"""MCP tools for managing the search configuration (config.json).

All tools accept a ``ctx: Context`` parameter (auto-injected by FastMCP)
for logging and progress reporting.
"""

import json

from academic_hunter.core import HunterConfig, get_config
from academic_hunter.core.infra import paths
from academic_hunter.core.nlp.scorer import compile_term_patterns
from academic_hunter.core.ports.vector_store import (
    LEGACY_COLLECTION,
    is_valid_collection_name,
    review_collection_name,
)
from academic_hunter.plugins.connectors import CONNECTORS
from mcp.server.fastmcp import Context

from ..cache import discovery_titles
from ..exceptions import ConfigError
from ..memory.config_backup import MCPDatabaseManager
from ..schemas.config_schema import SearchConfigUpdate
from ._utils import _get_vector_store, _is_generic


async def read_config(ctx: Context) -> str:
    """Returns the current full search configuration from config.json.

    Use this tool to check which anchors or technical_strings are currently
    configured, and what this configuration will fail to do.

    ``ranking`` says what orders the papers -- BM25 against ``ranking_query``,
    or the keyword score when there is none. It is a description rather than a
    note because it is true of every configuration, and ``notes`` has to be able
    to come back empty or the reader learns to skip it.

    ``notes`` carries what ``_config_notes`` finds: a context rule whose key is
    not an anchor never fires, a weight no query asks for never brings a paper
    in, an anchor that is also weighted is admitted by the gate and clears the
    cut with nothing else true of the paper, and a cut the lightest anchor
    already clears excludes nothing. Each of them runs to completion and
    searches worse instead of raising, so the only moment to see one is before
    the run is spent. ``update_config`` says these same sentences as it writes
    them; reading the configuration back has to say them too, or the warning is
    only ever visible to whoever happens to rewrite the file. The key is always
    present -- an empty list means nothing was found, not that nothing was
    looked for.
    """
    await ctx.info("Reading configuration...")
    try:
        config = get_config()
        data = {
            "config_source": {
                "path": str(config.config_path),
                "origin": str(config.config_origin),
                "is_default": config.config_origin == paths.ORIGIN_PACKAGED,
            },
            "settings": config.public_settings(),
            "anchors": config.anchors,
            "technical_strings": config.tech_strings,
            "technical_weights": config.tech_weights,
            "context_rules": config.context_rules,
            "keyword_only_terms": config.keyword_only_terms,
            "keyword_only_category": config.keyword_only_category,
            "ranking": _ranking_summary(config),
            "notes": _config_notes(config),
        }
        await ctx.info("Configuration read successfully")
        return json.dumps(data, indent=2, ensure_ascii=False)
    except ConfigError:
        raise
    except Exception as e:
        await ctx.error(f"Failed to read configuration: {e}")
        raise ConfigError(str(e))


def _ranking_summary(config) -> str:
    """What orders the papers, whichever of the two modes is in force.

    A description, not a defect, which is why it is not in ``_config_notes``: it
    is true of every configuration, and a report that always has something in it
    teaches the reader to skip it. It is still something to be said, because the
    two modes answer different questions and only one of them looks at what the
    reader is looking for.

    The no-query half quotes a measurement, because the difference is not
    obvious from the code: with no query the ordering is ``_kw_score``, a
    function of the paper and of the configured terms that never sees a question.
    On a hand-judged blockchain pool (5 queries, 250 graded judgments) ordering
    by it scored nDCG@10 0.25, against 0.67 for BM25 over a question — which
    reproduces, on other judgments and another corpus, the 0.28-to-0.67 the
    ``RecomputeRanksStep`` docstring records for introducing ``ranking_query``.
    """
    query = str(config.settings.get("ranking_query", "") or "").strip()
    cut = _as_number(config.min_inclusion_score(), 5.0)
    if query:
        return (
            "Rank every paper by BM25 of its title and abstract against "
            f"`ranking_query` -- \"{query}\" -- and not by the keyword score. The "
            f"inclusion cut is another number, `_kw_score >= {cut:g}`, so the order "
            "of the CSV and the set of papers in it answer two different questions."
        )
    return (
        "Rank every paper by the keyword score -- `_kw_score`, a function of the "
        "paper and of the configured terms, which never sees what is being looked "
        "for and therefore orders the corpus the same way whatever that is. "
        "Measured on a hand-judged blockchain pool (5 queries, 250 graded "
        "judgments): nDCG@10 0.25 by that score, against 0.67 for BM25 over a "
        "question. Set `settings.ranking_query` to rank against a question instead."
    )


def _flatten_terms(mapping) -> list:
    """Every term of a ``{category: [term]}`` mapping, flattened, without repeats."""
    terms, seen = [], set()
    for group in (mapping or {}).values():
        values = [group] if isinstance(group, str) else (group or [])
        for term in values:
            name = str(term).strip()
            if name and name.lower() not in seen:
                seen.add(name.lower())
                terms.append(name)
    return terms


def _named(terms, limit: int = 8) -> str:
    """Name up to ``limit`` terms, and count the rest rather than list them.

    A call can hand over forty weights, and a line that lists forty of them is
    read by nobody -- which is the failure mode this whole reply exists to avoid.
    """
    shown = list(terms)
    rest = len(shown) - limit
    if rest > 0:
        return f"{', '.join(shown[:limit])}, and {rest} more"
    return ", ".join(shown)


def _as_number(value, default=None):
    """The value as a number, or ``default`` when it will not be one.

    Everything this report reads comes from a file an agent wrote, so nothing
    here may raise: a diagnostic that breaks the call it is diagnosing is worse
    than no diagnostic, and ``update_config`` turns any exception into a failure
    of the whole write.
    """
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


_RUN_SHAPING_SETTINGS = ("ranking_query", "start_year")


def _config_notes(config, sent=None) -> list:
    """Lines naming what this configuration will fail to do, or ``[]``.

    Every defect here runs to completion. A context rule whose key is not an
    anchor never fires; a weight no query asks for never brings a paper in; an
    anchor that also carries a weight is admitted by the gate and clears the cut
    with nothing else true of the paper. None of them raises, and the only
    symptom is a corpus assembled out of the wrong papers minutes later -- which
    is why they are said out loud here, the same reasoning as the ``NOT QUERIED``
    line. This reports; it does not refuse. The one write refused on this path is
    an unusable ``collection_name``, refused because ChromaDB would fail
    downstream on it. Nothing below fails downstream: it just searches worse.

    ``sent`` is the set of ``settings`` keys the caller passed. ``settings`` is
    merged rather than replaced, so a key left out keeps the value the previous
    topic wrote, and ``_RUN_SHAPING_SETTINGS`` names the two that shape a run
    without being a term: what ranks the papers, and which papers are young
    enough. Measured on a real run, a Stellar review came out ordered end to end
    by the low-level-AI topic's ``ranking_query`` -- a question about quantisation
    -- and no line of this reply had ever named it. The cut is deliberately not in
    that tuple: every other note here already quotes it, so a key that is not in
    it is not thereby unmentioned. Pass ``None`` when the caller does not know
    what it sent; nothing is claimed then.
    """
    cut = _as_number(config.min_inclusion_score(), 5.0)
    multiplier = _as_number(config.settings.get("title_multiplier", 1.5), 1.5)

    anchors = _flatten_terms(config.anchors)
    anchor_keys = {term.lower() for term in anchors}
    strings = _flatten_terms(config.tech_strings)
    string_keys = {term.lower() for term in strings}
    weights = dict(config.tech_weights or {})
    rules = config.context_rules or {}
    rule_keys = {str(key).strip().lower() for key in rules}

    def clears_cut(term):
        weight = _as_number(weights.get(term))
        return weight is not None and weight * multiplier >= cut

    notes = []

    if sent is not None:
        inherited = [key for key in _RUN_SHAPING_SETTINGS if key not in sent and config.settings.get(key)]
        if inherited:
            named = ", ".join(f"`{key}`" for key in inherited)
            notes.append(
                f"  Not sent by this call, so kept: {named} -- `settings` is merged, "
                "not replaced, so a key `update_config` is not given keeps whatever the "
                "previous configuration put there, whatever topic that was. Each of "
                "these shapes the run and none of them is about the terms above, so "
                "read the value before spending a run on it."
            )

    unnumbered = [term for term in weights if _as_number(weights[term]) is None]
    if unnumbered:
        notes.append(
            f"  Score nothing: {_named(unnumbered)} -- a weight that is not a "
            "number cannot be multiplied by a title hit, so every paper raises on "
            "it and the worker logs 'dropped one paper' for each: the run finishes "
            "with an empty corpus. Write numbers."
        )

    if not weights:
        note = (
            "  Score nothing: `technical_weights` is empty, so no configured term "
            "contributes to a paper's score and the whole of it is "
            "`log10(citations + 1)`."
        )
        if cut > 0:
            note += (
                f" Reaching the cut of {cut:g} that way takes about "
                f"{10 ** cut - 1:,.0f} citations, so expect a near-empty run "
                "however many papers the queries return."
            )
        notes.append(note + " Weigh the terms the field uses.")

    if cut > 0:
        by_lower = {
            str(term).strip().lower(): _as_number(weight)
            for term, weight in weights.items()
        }
        anchor_weights = [by_lower.get(term.lower()) for term in anchors]
        floor = (
            min(anchor_weights)
            if anchor_weights and all(w is not None for w in anchor_weights)
            else None
        )
        if anchor_weights and not unnumbered and floor is not None and floor >= cut:
            notes.append(
                f"  Excludes nothing: the cut is {cut:g} and the lightest anchor "
                f"weighs {floor:g}, so every paper the gate admits already scores "
                "at or above the cut before anything else is true of it. It "
                "contains one of those terms -- that is what the gate checks -- an "
                "abstract hit counts the term at full weight and a title hit "
                "counts more, and citations only add. So `min_inclusion_score` "
                "removes nothing however many papers the queries return, and the "
                "gate is doing all of the filtering by itself. Measured on a real "
                "run: every anchor at 5.0 against a cut of 5.0 evaluated 252 "
                "papers, included 252, excluded 0. For the cut to remove anything "
                "it has to sit above the lightest anchor's weight; a gate that "
                "filters with a cut deliberately set below it needs no change. "
                "Note that a context rule does not help here -- every paper that "
                "passes one still has the term counted."
            )

        bare_anchors = [
            term for term in weights
            if term.lower() in anchor_keys and term.lower() not in rule_keys and clears_cut(term)
        ]
        if bare_anchors:
            named = _named(f"{term} ({_as_number(weights[term]):g})" for term in bare_anchors)
            notes.append(
                f"  Admits anything: {named} -- each is an anchor and carries a "
                f"weight that clears the cut of {cut:g} on a title hit alone, since a "
                f"title hit multiplies the weight by {multiplier:g}. The gate takes "
                "such a paper and nothing else has to be true of it, and a context "
                "rule is the only thing that can hold the term back -- none is set. "
                "Measured on a real run, an anchor `llm` at 5.0 with no rule admitted "
                "513 of 1151 papers this way."
            )

        unguardable = sorted(
            (
                term for term in weights
                if term.lower() not in anchor_keys and clears_cut(term)
            ),
            key=str.lower,
        )
        if unguardable:
            named = _named(f"{term} ({_as_number(weights[term]):g})" for term in unguardable)
            notes.append(
                f"  Score without a guard: {named} -- each clears the cut of {cut:g} "
                "on its own, and none of them is an anchor, so no context rule can "
                "ever reach it: the lookup is by the anchor term that matched. Only "
                "making the term an anchor, and giving it a rule, can constrain it."
            )

    generic = [
        term
        for term in dict.fromkeys(anchors + strings + list(weights))
        if _is_generic(term)
    ]
    if generic:
        note = (
            f"  Generic terms in use: {_named(generic)} -- these name any field's "
            "work. In an OR list the precision is the worst term's, so a specific "
            "term sitting beside `framework` is mostly paid for in papers that say "
            "`framework`. Measured on a real run, `framework` matched 316 of 1151 "
            "papers and `accuracy` 424 -- more than the topic's own core term. Keep "
            "one only where its weight says how little it means."
        )
        generic_anchors = [term for term in generic if term.lower() in anchor_keys]
        if generic_anchors:
            note += (
                f" {_named(generic_anchors)} "
                f"{'appear' if len(generic_anchors) > 1 else 'appears'} among the "
                "anchors as well, where the weight cannot hold it back: the anchor "
                "side of every query is built from these, and the gate admits any "
                "paper that uses the word, whatever the paper is about."
            )
        notes.append(note)

    unqueried = [
        term for term in weights
        if term.lower() not in string_keys and term.lower() not in anchor_keys
    ]
    if unqueried:
        notes.append(
            f"  Weighted but never queried: {_named(unqueried)} -- the score counts "
            "them, but no query asks for them, so they never bring a paper in. Add "
            "them to `technical_strings` or drop the weight."
        )

    unscored = [term for term in strings if term.lower() not in {key.lower() for key in weights}]
    if unscored:
        notes.append(
            f"  Queried but never scored: {_named(unscored)} -- these are in "
            "`technical_strings`, so they are asked for and printed in Tech_Terms, "
            "but only `technical_weights` builds the score. A term here with no "
            "weight widens the query and counts for nothing."
        )

    dead = [key for key in rules if str(key).strip().lower() not in anchor_keys]
    if dead:
        notes.append(
            f"  Never fire: context rules for {_named(dead)} -- a rule is looked up "
            "by the anchor term that matched, so a key that is not an anchor is read "
            "by nothing. It is not a filter that is too weak, it is no filter at "
            "all, and the term it was written to constrain passes unchallenged."
        )

    return notes


def _normalised_topic(text) -> str:
    """A topic string comparable across the two calls that write it by hand.

    The topic is typed once into the discovery and again into this call, and the
    two are not reliably the same characters: a stray space or a capital is
    enough to make a lookup miss, and a miss here reads as "nothing to check".
    """
    return " ".join(str(text or "").split()).lower()


def _discovery_note(config, topic) -> list:
    """The discovery's own titles, held against the anchors written for them.

    ``quick_topic_discovery`` sweeps a hundred titles and hands back ten, and the
    anchors that follow are meant to be written from what those titles use.
    Nothing checked that. On a real run the topic "Stellar" returned stellar
    populations, MESA isochrones and stellar winds -- in the literature that word
    is an adjective for stars -- and a configuration for the Stellar blockchain
    was written over it from memory. Forty-seven papers survived the gate,
    forty-three of them on a term any field uses.

    So what the discovery retrieved is kept, and this holds the anchors against
    it. An anchor found in no retrieved title is one the sources were never asked
    for; when most of a group is absent, the word that named the topic named
    another field. Counts are printed and no verdict is given, because the two
    readings are different problems -- anchors that are not this literature's
    vocabulary, or a topic word that is not this field's -- and the counts are
    what tell them apart.

    The trigger is a strict majority of a group's terms absent from every title:
    a group of one fires when its only term is missing, a group of two needs
    both, a group of five needs three. A single absent term is ordinary, since a
    rare synonym beside a common one says nothing is wrong, while a majority is
    a group that cannot gate much. The asymmetry is deliberate: a false alarm
    costs a reread of the titles, a miss costs a whole run assembling another
    field's corpus.

    Only titles are held here, and the gate really runs over title and abstract
    and then over ``context_rules``, so nothing below claims a paper would be
    rejected -- only that these words are not among what the topic retrieved.
    Pass no topic, or a session that discovered nothing, and nothing is said.
    """
    wanted = _normalised_topic(topic)
    if not wanted:
        return []

    live = discovery_titles.keys()
    if not live:
        return []

    matched = [key for key in live if _normalised_topic(key) == wanted]
    if matched:
        discovered_as = matched[0]
    elif len(live) == 1:
        discovered_as = live[0]
    else:
        ran_for = _named(['"' + key + '"' for key in sorted(live)])
        return [
            "  Nothing to check this configuration against: this session ran the "
            f"discovery for {ran_for}, and this "
            f"configuration is for \"{topic}\". Run quick_topic_discovery for this "
            "topic and the anchors will be held against the titles it returns."
        ]

    record = discovery_titles.get(discovered_as)
    if not isinstance(record, dict):
        return []
    titles = [str(title).lower() for title in (record.get("titles") or []) if title]
    if not titles:
        return []

    lines = []
    for name, group in (config.anchors or {}).items():
        terms = _flatten_terms({name: group})
        if not terms:
            continue
        patterns = compile_term_patterns(terms)
        hits = {
            term: sum(1 for title in titles if patterns[term].search(title))
            for term in terms
        }
        missing = [term for term in terms if not hits[term]]
        if 2 * len(missing) <= len(terms):
            continue

        present = sorted(
            ((term, hits[term]) for term in terms if hits[term]),
            key=lambda pair: -pair[1],
        )
        used = [
            entry.get("term")
            for entry in (record.get("candidates") or {}).get("candidate_terms") or []
            if entry.get("term") and entry["term"].lower() not in {term.lower() for term in terms}
        ][:6]

        total, gone = len(terms), len(missing)
        if total == 1:
            sentence = (
                f"  What the discovery for \"{discovered_as}\" returned: {len(titles)} "
                f"titles, not one of which carries `{name}`'s only anchor, "
                f"{_named(missing)}. "
            )
        elif gone == total:
            sentence = (
                f"  What the discovery for \"{discovered_as}\" returned: {len(titles)} "
                f"titles, not one of which carries any of the {total} anchors in "
                f"`{name}`: {_named(missing)}. "
            )
        else:
            sentence = (
                f"  What the discovery for \"{discovered_as}\" returned: {len(titles)} "
                f"titles, and {gone} of the {total} anchors in `{name}` are in none of "
                f"them: {_named(missing)}. "
            )
        if _normalised_topic(discovered_as) != wanted:
            sentence += (
                f"The discovery was run for \"{discovered_as}\" and this configuration "
                f"is for \"{topic}\"; these are the titles retrieved under the first. "
            )
        if len(present) == 1:
            sentence += f"The one it does carry is {present[0][0]}, in {present[0][1]}. "
        elif present:
            sentence += (
                f"The ones it does carry: "
                f"{_named([f'{term} ({count})' for term, count in present], 3)}. "
            )
        else:
            sentence += "None of them does. "
        if used:
            sentence += f"Those titles use {_named([f'`{term}`' for term in used])} instead. "
        sentence += (
            "Two readings and the counts tell them apart: either these anchors are not "
            "the vocabulary of what the sources hold under this word, or the word names "
            "another field, and either way the gate admits that field's papers. Re-read "
            "the titles and anchor on the phrases they use, or run the discovery under a "
            "name only this field uses."
        )
        lines.append(sentence)
    return lines


def _search_plan(config, sent=None, topic=None) -> str:
    """What this configuration will actually ask, before a run is spent on it.

    ``technical_strings`` is what the four grid sources are queried with, and it
    is easy to leave empty -- the config then saves, searches two of six
    sources, and reports success. Saying so here is cheaper than finding it in
    the report.

    A source that cannot run with these settings is named rather than counted,
    for the same reason: this reply is a promise about what the run will ask,
    and a source left out of it has to be left out here too.

    ``_config_notes`` carries the other half, and a heavier one: what the
    configuration will do to the papers that come back. The configuration is
    written by an agent between two calls, so a defect it invents passes in
    silence unless it is named here.

    ``topic`` is what the discovery was run for, and it buys a second opinion
    that is not about the configuration at all: whether the anchors are written
    from the literature the topic retrieves or from memory of the field. That
    answer belongs under its own heading, because a sound configuration over a
    topic word that names another field is not a defect of the configuration.
    """
    unavailable = {
        name: cls.unavailable_reason(config.settings)
        for name, cls in CONNECTORS.items()
    }
    unavailable = {name: reason for name, reason in unavailable.items() if reason}
    grid = [
        name for name, cls in CONNECTORS.items()
        if not cls.is_keyword_only and name not in unavailable
    ]
    keyword_only = [
        name for name, cls in CONNECTORS.items()
        if cls.is_keyword_only and name not in unavailable
    ]

    lines = ["", "What this configuration will do:"]
    anchor_count = len(config.anchors)

    if not anchor_count:
        lines.append(
            "  Query nothing. The pipeline asks once per anchor and there are "
            "none, so run_search will refuse. Set anchors with update_config."
        )
        return "\n".join(lines)

    group_note = ""
    if anchor_count == 1:
        group_note = (
            " One group, so the gate is a flat OR: a paper is admitted by any single "
            "term of it, and one generic term here widens every query at once."
        )

    query_word = "query" if anchor_count == 1 else "queries"

    if config.tech_strings:
        grid_calls = anchor_count * len(config.tech_strings)
        lines.append(
            f"  Query {', '.join(grid)} once per anchor x technical-string "
            f"category ({grid_calls} queries), and {', '.join(keyword_only)} once "
            f"per anchor ({anchor_count} {query_word})." + group_note
        )
    else:
        lines.append(
            f"  Query only {', '.join(keyword_only)} ({anchor_count} {query_word}). "
            "They take anchors alone. The grid sources "
            f"({', '.join(grid)}) need a technical string, so they will NOT be "
            "queried and the zeros they report are not findings." + group_note
        )
        lines.append(
            "  Add technical_strings -- a category per concept, with the terms the "
            "field uses -- and call update_config again."
        )

    if unavailable:
        named = "; ".join(f"{name}: {reason}" for name, reason in unavailable.items())
        lines.append(f"  Not queried, so not a finding: {named}")

    start_year = _as_number(config.settings.get("start_year"))
    if start_year:
        lines.append(
            f"  Keep only papers published from {start_year:g} on. An older paper is "
            "dropped before the anchor gate reaches it, so it is counted in the run "
            "report as `excluded_year` and never as a term that missed."
        )

    lines.append("  " + _ranking_summary(config))

    discovery = _discovery_note(config, topic)
    if discovery:
        lines.append("")
        lines.append("What quick_topic_discovery returned, against these anchors:")
        lines.extend(discovery)

    notes = _config_notes(config, sent)
    if notes:
        lines.append("")
        lines.append("What this configuration will fail to do:")
        lines.extend(notes)
    return "\n".join(lines)


def _papers_in(collection_name: str) -> int:
    """How many papers a collection holds, or 0 if it cannot be read."""
    if not collection_name:
        return 0
    store = _get_vector_store()
    if store is None:
        return 0
    return int(store.collection_stats(collection_name).get("count", 0) or 0)


def _set_collection(config, config_update: SearchConfigUpdate) -> str:
    """Point the configuration at this review's collection, and say what changed.

    One collection per review: a single shared one means clustering, trends and
    duplicate detection describe every review ever run in this installation while
    reading as though they described the current one. The name is written into
    ``config.json`` rather than derived at read time, so it is visible, survives a
    restart, and two runs of the same review land in the same place.

    An explicitly configured ``collection_name`` is the operator's word and is
    kept; a bad one is refused rather than quietly replaced, because being told
    which collection holds the papers is the whole point.

    Otherwise the name comes from the ``topic``, and **only** from the topic when
    one is given. A later call that tweaks a setting and names no topic keeps the
    name it already had: deriving from the anchors there would rename the
    collection of an established review, and the next run would index into a new
    one while the old corpus sat where nothing reads it. The anchors are the
    fallback for exactly one case -- a configuration that has never been given a
    name and is still sitting on the shared legacy collection.
    """
    before = config.collection_name()

    explicit = (config_update.settings or {}).get("collection_name")
    if isinstance(explicit, str) and explicit.strip():
        name = explicit.strip()
        if not is_valid_collection_name(name):
            raise ConfigError(
                f"collection_name {name!r} is not a name ChromaDB accepts: 3-63 "
                "characters, alphanumerics plus _ - . and an alphanumeric at each "
                "end. Nothing was changed."
            )
        chosen = name
    else:
        chosen = review_collection_name(config_update.topic or "")
        if not chosen and before == LEGACY_COLLECTION:
            anchors = (
                config_update.anchors if config_update.anchors is not None
                else config.anchors
            )
            chosen = review_collection_name("", anchors)

    if not chosen:
        return (
            f"\n  Collection: `{before}` (unchanged). This call named no topic, "
            "and nothing here moves an existing corpus: pass a `topic` to start "
            "a review in a collection of its own."
        )
    if chosen == before:
        return f"\n  Collection: `{chosen}` ({_papers_in(chosen)} papers indexed)."

    config.settings["collection_name"] = chosen
    elsewhere = _papers_in(before)
    note = f"\n  Collection: `{before}` -> `{chosen}`."
    if elsewhere:
        note += (
            f" {elsewhere} papers stay in `{before}` and are not moved: the next "
            "run indexes into the new collection, and every corpus analysis "
            "describes that one. Delete the old collection with "
            "vector_store_stats when you are done with it."
        )
    return note


async def update_config(config_update: SearchConfigUpdate, ctx: Context) -> str:
    """Updates the Hunter search configuration.

    Use this tool WHENEVER the user asks to research a new topic.
    Automatically backs up the previous state before applying changes.

    The reply states what the new configuration will query, and names the
    sources that will be skipped, so an incomplete configuration is visible
    before run_search rather than as zeros in the report.

    When ``quick_topic_discovery`` has run for this topic in this session, the
    reply also holds the anchors against the titles it retrieved. An anchor that
    appears in none of them is one the sources were never asked for, and a group
    mostly made of them means the topic word names another field — which is
    visible here, before a run is spent, and nowhere else afterwards.

    Args:
        config_update: The new configuration to apply.
        ctx: FastMCP Context (auto-injected).
    """
    await ctx.info("Updating configuration...")
    try:
        config = get_config()

        db = MCPDatabaseManager()
        current_state = {
            "settings": config.public_settings(),
            "anchors": config.anchors,
            "technical_strings": config.tech_strings,
            "technical_weights": config.tech_weights,
            "context_rules": config.context_rules,
            "keyword_only_terms": config.keyword_only_terms,
            "keyword_only_category": config.keyword_only_category,
        }
        topic_name = config_update.topic if config_update.topic else "Auto Backup"
        db.save_config(topic=f"Before {topic_name}", config_data=current_state)

        if config_update.settings:
            config.settings.update(config_update.settings)
        if config_update.anchors is not None:
            config.anchors = config_update.anchors
        if config_update.technical_strings is not None:
            config.tech_strings = config_update.technical_strings
        if config_update.technical_weights is not None:
            config.tech_weights = config_update.technical_weights
        if config_update.context_rules is not None:
            config.context_rules = config_update.context_rules
        if config_update.keyword_only_terms is not None:
            config.keyword_only_terms = config_update.keyword_only_terms
        if config_update.keyword_only_category is not None:
            config.keyword_only_category = config_update.keyword_only_category

        collection_note = _set_collection(config, config_update)

        config.save()

        new_state = {
            "settings": config.public_settings(),
            "anchors": config.anchors,
            "technical_strings": config.tech_strings,
            "technical_weights": config.tech_weights,
            "context_rules": config.context_rules,
            "keyword_only_terms": config.keyword_only_terms,
            "keyword_only_category": config.keyword_only_category,
        }
        db.save_config(topic=topic_name, config_data=new_state)

        await ctx.info("Configuration updated successfully")
        return (
            "Configuration updated and saved to history successfully!"
            + _search_plan(
                config,
                set((config_update.settings or {}).keys()),
                topic=config_update.topic,
            )
            + collection_note
        )
    except ConfigError:
        raise
    except Exception as e:
        await ctx.error(f"Failed to update configuration: {e}")
        raise ConfigError(str(e))


async def list_config_history(ctx: Context, limit: int = 5) -> str:
    """Lists the history of the last saved configurations in the MCP SQLite database.

    Returns the ID, Timestamp, and Topic. Useful for finding the ID of a past config.
    """
    await ctx.info("Listing configuration history...")
    try:
        db = MCPDatabaseManager()
        history = db.list_configs(limit=limit)
        if not history:
            await ctx.info("No configuration history found")
            return "No configuration history found."
        await ctx.info(f"Found {len(history)} configuration backups")
        return json.dumps(history, indent=2, ensure_ascii=False)
    except ConfigError:
        raise
    except Exception as e:
        await ctx.error(f"Failed to list config history: {e}")
        raise ConfigError(str(e))


async def restore_config_by_id(config_id: int, ctx: Context) -> str:
    """Restores the full project config.json using a database backup (by its ID).

    Args:
        config_id: The ID of the backup to restore (from list_config_history).
        ctx: FastMCP Context (auto-injected).
    """
    await ctx.info(f"Restoring configuration ID {config_id}...")
    try:
        db = MCPDatabaseManager()
        config_data = db.get_config(config_id)
        if not config_data:
            await ctx.error(f"Config ID {config_id} not found")
            raise ConfigError(f"Config ID {config_id} not found.")

        config = get_config()
        if "settings" in config_data:
            restored = {
                key: value
                for key, value in config_data["settings"].items()
                if key not in HunterConfig.SECRET_SETTINGS and key != "api_keys"
            }
            live_secrets = {
                key: value
                for key, value in config.settings.items()
                if key in HunterConfig.SECRET_SETTINGS or key == "api_keys"
            }
            config.settings = {**restored, **live_secrets}
        if "anchors" in config_data:
            config.anchors = config_data["anchors"]
        if "technical_strings" in config_data:
            config.tech_strings = config_data["technical_strings"]
        if "technical_weights" in config_data:
            config.tech_weights = config_data["technical_weights"]
        if "context_rules" in config_data:
            config.context_rules = config_data["context_rules"]
        if "keyword_only_terms" in config_data:
            config.keyword_only_terms = config_data["keyword_only_terms"]
        if "keyword_only_category" in config_data:
            config.keyword_only_category = config_data["keyword_only_category"]

        config.save()
        await ctx.info(f"Configuration ID {config_id} restored successfully")
        return f"Configuration ID {config_id} restored successfully to config.json!"
    except ConfigError:
        raise
    except Exception as e:
        await ctx.error(f"Failed to restore config: {e}")
        raise ConfigError(str(e))
