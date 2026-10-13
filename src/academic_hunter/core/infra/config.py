"""Configuration management for Academic Hunter.

Loads and caches JSON configuration with environment variable overrides.
Supports validation and change tracking for MCP config history.
"""

import copy
import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from ..ports.vector_store import LEGACY_COLLECTION, is_valid_collection_name
from . import paths
from .atomic import write_json_atomically

logger = logging.getLogger("academic_hunter.config")

REDACTED = "***redacted***"

DEFAULT_FULLTEXT_MAX_PAPERS = 200
DEFAULT_FULLTEXT_TIME_BUDGET = 900


def positive_int(value: Any, default: int) -> int:
    """A settings value that has to be a positive integer, or the default.

    Lives here because both settings blocks that need it — `rerank` and
    `fulltext` — have no schema, and each carried its own copy of this.
    """
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def as_bool(value: Any, default: bool = False) -> bool:
    """A settings value read as a boolean, for text that came from outside.

    ``bool("false")`` is ``True``, so a quoted value or an environment variable
    cannot be read by truthiness. Only the spellings a config file or a shell
    actually carries are accepted; anything else — including a bare integer,
    which the settings blocks reject on purpose — is the default, because
    guessing would silently switch a stage on.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in ("true", "yes", "on", "1"):
            return True
        if text in ("false", "no", "off", "0", ""):
            return False
    return default


def coerce_override(value: str, existing: Any) -> Any:
    """The environment's text in the type the setting it overrides already has.

    An override always arrives as a string, so `=1` for a setting the file holds
    as a boolean has to become `True`: `fulltext.enabled` and `rerank.enabled`
    accept only a real boolean, and `int 1` is not one — the stage stayed off
    while the operator believed they had switched it on. Reading the type from
    the value already there keeps `=1` an integer where an integer belongs.
    """
    if isinstance(existing, bool):
        return as_bool(value, existing)
    if value.lower() in ("true", "false"):
        return value.lower() == "true"
    try:
        return float(value) if "." in value else int(value)
    except (ValueError, TypeError):
        return value


def put_at_path(config: Dict[str, Any], path: Tuple[str, ...], value: Any) -> None:
    """Place ``value`` at ``path``, creating the dictionaries on the way."""
    target = config
    for part in path[:-1]:
        nested = target.get(part)
        if not isinstance(nested, dict):
            nested = {}
            target[part] = nested
        target = nested
    target[path[-1]] = value


def restore_from_disk(section: Dict[str, Any], raw: Dict[str, Any], path: Tuple[str, ...]) -> None:
    """Put back the value the file held at ``path``, or drop the key it lacked.

    The counterpart of an environment override. ``save()`` writes the live
    settings, which carry the override, so every overridden path is returned to
    what the file said — otherwise a credential read from the environment is
    written to disk, and a value set for one run outlives it.
    """
    target, source = section, raw
    for part in path[:-1]:
        if not isinstance(target, dict):
            return
        target = target.get(part)
        source = source.get(part) if isinstance(source, dict) else None
    if not isinstance(target, dict):
        return
    if isinstance(source, dict) and path[-1] in source:
        target[path[-1]] = copy.deepcopy(source[path[-1]])
    else:
        target.pop(path[-1], None)


def config_fingerprint(payload: Dict[str, Any]) -> str:
    """A stable digest of a configuration, for telling two of them apart.

    Key order does not matter, so the same configuration assembled by two
    different paths gets the same digest, and a run's archived block can be
    compared against a candidate without diffing nested dicts.

    A ``config_fingerprint`` key already in ``payload`` is ignored, so the
    digest of an archived block is the one that was stored in it rather than a
    second hash of the first.

    What it does not promise: it covers the configuration and nothing else --
    not the code that consumes it, not which connectors answered, not the
    machine. ``5`` and ``5.0`` serialize differently and therefore fingerprint
    differently, though the scorer treats them alike.
    """
    body = {key: value for key, value in payload.items() if key != "config_fingerprint"}
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def normalise_context_rules(rules: Any) -> Dict[str, List[str]]:
    """``context_rules`` with every key and keyword folded to lower case.

    The scorer lower-cases the matched term before looking it up and tests each
    keyword as a substring of lower-cased text, so a rule written ``Drex`` or
    ``{"drex": ["CBDC"]}`` never fires. A rule that never fires is worse than a
    missing one: the term passes unchallenged, which is exactly how the
    anti-collision rule this mechanism exists for stopped working -- in silence.

    Folding here means every path that sets the rules gets the same keys, including
    the two that assign the attribute straight from a tool payload.

    A rule whose value is a single string is read as one keyword rather than
    dropped: dropping it would leave the term unconstrained, which is more
    permissive than the file asked for.
    """
    if not isinstance(rules, dict):
        return {}
    folded: Dict[str, List[str]] = {}
    for key, keywords in rules.items():
        if isinstance(keywords, str):
            keywords = [keywords]
        if not isinstance(keywords, (list, tuple)):
            continue
        terms = [str(word).strip().lower() for word in keywords if str(word).strip()]
        name = str(key).strip().lower()
        if name and terms:
            folded[name] = terms
    return folded


def _source_api_key(
    settings: Dict[str, Any], env_var: str, nested_name: str, secret_setting: str
) -> str:
    """A source's API key from whichever of the three places holds it.

    The environment wins so a key can be supplied without writing it to disk.
    Both config spellings are accepted because the project has used both:
    ``api_keys.<name>`` and the flat ``SECRET_SETTINGS`` entry.
    """
    api_keys = settings.get("api_keys") or {}
    nested = api_keys.get(nested_name) if isinstance(api_keys, dict) else ""
    return os.environ.get(env_var) or nested or settings.get(secret_setting) or ""


def semantic_scholar_key(settings: Dict[str, Any]) -> str:
    """The Semantic Scholar API key, or ``""`` when none is configured.

    Single source of truth, read by the connector and — until they were moved to
    OpenAlex — by the MCP discovery tools. Those tools built their S2 URLs by
    hand and sent no key at all, so a configured credential bought them nothing,
    and the 429 they then raised told the operator to set a key already set.
    """
    return _source_api_key(
        settings, "SEMANTIC_SCHOLAR_API_KEY", "semantic_scholar", "semantic_scholar_api_key"
    )


def openalex_key(settings: Dict[str, Any]) -> str:
    """The OpenAlex API key, or ``""`` when none is configured.

    Optional: OpenAlex serves keyless callers. A key raises the daily credit
    budget tenfold, which is the difference between roughly 100 and roughly 1000
    searches a day.
    """
    return _source_api_key(settings, "OPENALEX_API_KEY", "openalex", "openalex_api_key")


def core_key(settings: Dict[str, Any]) -> str:
    """The CORE API key, or ``""`` when none is configured.

    Named here for the same reason as the other two: the connector's header and
    its availability answer have to read the same three places, or a key that
    works is a key the run does not know it has.
    """
    return _source_api_key(settings, "CORE_API_KEY", "core", "core_api_key")


class HunterConfig:
    """Handles JSON configuration loading, environment variables, pacing delays, and default fallback parameters.

    Features:
    - Lazy-loading with cache invalidation via mtime check
    - Environment variable overrides (prefixed with ACADEMIC_HUNTER_)
    - Type-validated accessors for all config sections
    """

    SECTIONS = (
        ("settings", ("settings",)),
        ("anchors", ("anchors",)),
        ("tech_strings", ("technical_strings",)),
        ("tech_weights", ("technical_weights",)),
        ("context_rules", ("settings", "context_rules")),
    )

    def __init__(self, config_path: Optional[str] = None,
                 pacing_defaults: Optional[Dict[str, float]] = None):
        """
        Args:
            config_path: Path to the JSON configuration file. ``None`` — which is
                what every caller should pass — resolves through
                ``paths.resolve_config_path()``, so the search order lives in one
                place instead of once per caller.
            pacing_defaults: Domain-to-delay mapping derived from the connector
                set by the composition root. Defaults to empty, so a config built
                without it simply has no pacing entries.
        """
        if config_path is None:
            resolved = paths.resolve_config_path()
            self.config_path = resolved.path
            self.config_origin = resolved.origin
        else:
            self.config_path = Path(config_path)
            self.config_origin = paths.ORIGIN_EXPLICIT

        self._mtime: float = 0.0
        self._raw: Dict[str, Any] = {}
        self._env_overrides: Dict[Tuple[str, ...], str] = {}

        self.settings: Dict[str, Any] = {}
        self.anchors: Dict[str, list] = {}
        self.tech_strings: Dict[str, list] = {}
        self.tech_weights: Dict[str, float] = {}
        self.context_rules: Dict[str, List[str]] = {}
        self.keyword_only_terms: List[str] = []
        self.keyword_only_category: str = ""
        self.blocked_sources: Set[str] = set()
        self.pacing_delays: Dict[str, float] = dict(pacing_defaults or {})

        self.load()

    @property
    def context_rules(self) -> Dict[str, List[str]]:
        """The contextual rules, keyed by term, with case folded away.

        Read and written through this property so that every path that sets the
        rules -- ``load``, the MCP config tools, a restore from the backup
        database -- folds them the same way, and ``settings['context_rules']``
        stays the same object as this attribute.
        """
        return self._context_rules

    @context_rules.setter
    def context_rules(self, rules: Any) -> None:
        self._context_rules = normalise_context_rules(rules)
        if isinstance(self.settings, dict):
            self.settings["context_rules"] = self._context_rules

    def _check_stale(self) -> bool:
        """Check if config file has been modified since last load."""
        if not self.config_path.exists():
            return False
        current_mtime = self.config_path.stat().st_mtime
        return current_mtime > self._mtime + 0.1

    def load(self, force: bool = False):
        """Load config from JSON file, respecting cache unless forced.

        Args:
            force: If True, bypass mtime cache and reload unconditionally.
        """
        if not force and self._raw and not self._check_stale():
            return

        if not self.config_path.exists():
            raise FileNotFoundError(
                f"Configuration file not found at '{self.config_path}' "
                f"(chosen by: {self.config_origin}). "
                "Write a config there, or set ACADEMIC_HUNTER_CONFIG to a file "
                "that exists, or start the server with --config PATH."
            )

        try:
            with open(self.config_path, encoding='utf-8') as f:
                self._raw = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Configuration file at '{self.config_path}' is not valid JSON: {e}. "
                "An interrupted save leaves it half-written."
            ) from e

        self._env_overrides = self._collect_env_overrides()

        self.settings.clear()
        self.settings.update(copy.deepcopy(self._raw.get('settings', {})))
        self._apply_env_overrides(("settings",), self.settings)

        for attribute, key in (
            ("anchors", "anchors"),
            ("tech_strings", "technical_strings"),
            ("tech_weights", "technical_weights"),
        ):
            current = getattr(self, attribute)
            current.clear()
            current.update(copy.deepcopy(self._raw.get(key, {})))
            self._apply_env_overrides((key,), current)

        self._load_context_rules()
        self.keyword_only_terms = self._raw.get('keyword_only_terms', [])
        self.keyword_only_category = self._raw.get('keyword_only_category', '')
        bare = self._env_overrides.get(('keyword_only_category',))
        if bare is not None:
            self.keyword_only_category = str(
                coerce_override(bare, self.keyword_only_category)
            )

        self._mtime = time.time()

    def _load_context_rules(self) -> None:
        """Fill ``context_rules`` from the nested copy, or the top-level one.

        Both shipped templates carry the rules under ``settings``, while ``load``
        read the top level — so a nested block was dead, and a stale top-level
        key silently won. The nested copy is now the one that counts; the
        top-level key is still read for a file that predates the move.

        ``settings['context_rules']`` and this attribute end up as the *same*
        dict, so the two spellings cannot drift apart.

        Both copies can be present with different contents, and then the choice
        above silently changes which rules apply: a config written by an older
        build carries its rules at the top level, and switching builds makes the
        nested block -- last written who knows when -- win instead. Re-saving
        collapses the two, so this warns rather than repairs.

        The block is folded to lower case on the way in, through
        :func:`normalise_context_rules`; the warning above compares the two
        blocks as the file wrote them, because that is what the operator sees.
        """
        nested = self.settings.get("context_rules")
        top_level = self._raw.get("context_rules")
        if (
            isinstance(nested, dict) and nested
            and isinstance(top_level, dict) and top_level
            and nested != top_level
        ):
            logger.warning(
                "config.json carries two different `context_rules`: %d rule(s) "
                "under `settings`, %d at the top level. The nested block is the "
                "one in effect and the top-level block is ignored; an older build "
                "wrote it there. Re-save the config (update_config) to collapse "
                "them, and check that the rules you meant are the ones that stay.",
                len(nested), len(top_level),
            )
        if not isinstance(nested, dict) or not nested:
            nested = copy.deepcopy(top_level or {})

        current = self.context_rules
        current.clear()
        current.update(normalise_context_rules(nested))
        self.settings["context_rules"] = current

    def _collect_env_overrides(self) -> Dict[Tuple[str, ...], str]:
        """Read the ``ACADEMIC_HUNTER_*`` variables into a path-to-text mapping.

        Double underscore separates the parts of the path, which is what makes
        the names acceptable to a systemd environment file:
        ``ACADEMIC_HUNTER_settings__min_relevance_score``.

        The text is *not* parsed here. Whether ``1`` means the integer or the
        boolean depends on the setting it lands on, and that is only known once
        the file's own value is in hand.
        """
        prefix = "ACADEMIC_HUNTER_"
        reserved = (paths.CONFIG_ENV, paths.DATA_ENV)
        overrides: Dict[Tuple[str, ...], str] = {}
        for key, value in sorted(os.environ.items()):
            if not key.startswith(prefix) or key in reserved:
                continue
            path = tuple(key[len(prefix):].lower().split("__"))
            if path[0] == "context_rules":
                path = ("settings", "context_rules") + path[1:]
            if len(path) == 1 and path[0] != "keyword_only_category":
                logger.warning(
                    "Ignoring %s: a bare name can only override a scalar setting, "
                    "and %r is a section.", key, path[0],
                )
                continue
            overrides[path] = value
        return overrides

    def _apply_env_overrides(self, section_path: Tuple[str, ...], section: Dict[str, Any]) -> None:
        """Apply the overrides that land inside one section, in place.

        A path matches when it starts with the section's own path, so an
        override addresses the file as it is written: ``settings__fulltext__enabled``
        and ``settings__context_rules__drex`` both belong to ``settings``.
        """
        depth = len(section_path)
        for path, text in self._env_overrides.items():
            if path[:depth] != section_path or len(path) <= depth:
                continue
            target = section
            for part in path[depth:-1]:
                nested = target.get(part)
                if not isinstance(nested, dict):
                    nested = {}
                    target[part] = nested
                target = nested
            key = path[-1]
            target[key] = coerce_override(text, target.get(key))

    def min_inclusion_score(self) -> float:
        """Threshold on ``_kw_score``: the only thing that decides **inclusion**.

        ``_kw_score`` is the weighted tally of the configured domain terms,
        computed at ingest (``AcademicScorer.calculate_score``): title matches
        scaled by ``title_multiplier``, abstract matches plain, plus
        ``log10(citations + 1)``. It is a function of the paper and of the
        configuration, and it does not move when the corpus grows — which is the
        point. Adding an anchor, joining a source, or drawing a different sample
        must not change which papers a review includes.

        ``Relevance_Score`` is the other number and is not this one. It is
        min-max normalised **within the run** to order and report, so its first
        paper is always 10.0 and one paper scores differently in two runs.
        Applying this threshold to it made inclusion a property of the run:
        widening an anchor evicted papers that had not changed.

        Falls back to ``min_relevance_score`` so a configuration that predates
        the split still resolves to a number. That number was calibrated against
        a different scale, so it is a starting point and not a recommendation:
        each run writes ``score_distribution_<timestamp>.json`` with every
        evaluated paper's signals, included or not, which is what the threshold
        should be chosen against.
        """
        return float(
            self.settings.get(
                "min_inclusion_score", self.settings.get("min_relevance_score", 5.0)
            )
        )

    def collection_name(self) -> str:
        """The vector-store collection this review's papers belong to.

        One collection per review. The name is derived once, when the review's
        configuration is written (``update_config``, from the topic), and stored
        here rather than computed at read time -- so it is visible in
        ``config.json``, survives a restart, and two runs of the same review land
        in the same place.

        Falls back to ``LEGACY_COLLECTION`` for a configuration written before
        this existed, which is where those papers actually are.
        """
        name = self.settings.get("collection_name")
        if isinstance(name, str) and is_valid_collection_name(name):
            return name

        if name:
            logger.warning(
                "settings.collection_name is %r, which ChromaDB will not accept "
                "(3-63 characters, alphanumerics plus _ - . , alphanumeric at each "
                "end). Reading %r instead; write a valid name with update_config.",
                name, LEGACY_COLLECTION,
            )
        return LEGACY_COLLECTION

    def screener_config(self) -> Dict[str, Any]:
        """Payload the semantic screener expects.

        Single source of truth for this dict shape. It used to be rebuilt inline
        in five places (validators, resolvers, pipeline steps), so a field added
        here could be silently missing everywhere else.
        """
        return {
            "anchors": self.anchors,
            "technical_strings": self.tech_strings,
            "technical_weights": self.tech_weights,
        }

    def run_snapshot(self) -> Dict[str, Any]:
        """The full configuration a run executed, deep-copied and unsullied.

        A run used to record only the *names* of its anchor and domain
        categories beside six scalars, so ``technical_weights`` and
        ``context_rules`` -- the two things that decide which papers are
        admitted and what they score -- survived nowhere. Reproducing a run's
        ``_kw_score`` meant finding the ``config.json`` that produced it, and a
        later run overwriting that file left nothing to find.

        Deep-copied because the caller hands this to an exporter that may run
        after the pipeline, while ``update_config`` mutates ``config.settings``
        in place: a reference would let a change of topic rewrite the record of
        a run that already finished.

        ``settings`` is filtered through :attr:`RUN_ARCHIVE_SETTINGS`, a
        positive list, because the archive ends up in the file people attach to
        a thesis or mail to an advisor. A positive list fails closed -- a new
        setting is archived only once someone declares it safe -- whereas a
        denial list has to guess every credential name at every depth, forever.
        ``context_rules`` travels under its own key rather than being read back
        out of ``settings``, where the property mirrors it, so the archive
        holds one copy under the name the configuration uses.
        """
        payload: Dict[str, Any] = {
            "anchors": copy.deepcopy(self.anchors),
            "technical_strings": copy.deepcopy(self.tech_strings),
            "technical_weights": copy.deepcopy(self.tech_weights),
            "context_rules": copy.deepcopy(self.context_rules),
            "keyword_only_terms": copy.deepcopy(self.keyword_only_terms),
            "keyword_only_category": self.keyword_only_category,
            "settings": {
                key: copy.deepcopy(self.settings[key])
                for key in self.RUN_ARCHIVE_SETTINGS
                if key in self.settings
            },
        }
        payload["config_fingerprint"] = config_fingerprint(payload)
        return payload

    def is_scorable(self) -> bool:
        """Whether the pipeline can query anything at all.

        The pipeline iterates anchors -- ``for anchor_cat, anchor_list in
        hunter.anchors.items()`` -- and the keyword-only branch sits inside that
        loop, so no anchors means every connector is skipped. Technical weights
        alone issue no query, which is why they are not part of this test.
        """
        return bool(self.anchors)

    SECRET_SETTINGS = ("semantic_scholar_api_key", "openalex_api_key", "core_api_key", "lens_api_key")

    RUN_ARCHIVE_SETTINGS: Tuple[str, ...] = (
        "min_inclusion_score",
        "min_relevance_score",
        "title_multiplier",
        "score_precision",
        "start_year",
        "limit_per_query",
        "ranking_query",
        "ablation",
        "fusion",
        "fusion_weights",
        "rerank",
        "citations_backfill",
    )

    def public_settings(self) -> Dict[str, Any]:
        """``settings`` with credentials masked, for anything that returns it.

        Whatever this feeds goes to the MCP client, whose context is a
        conversation log. Nothing that *uses* the config calls it — the
        connectors read the real values from ``settings``.

        A present key becomes a fixed placeholder rather than disappearing, so
        the caller can see that a credential exists without seeing it.
        """
        redacted = dict(self.settings)
        for key in self.SECRET_SETTINGS:
            if redacted.get(key):
                redacted[key] = REDACTED

        nested = redacted.get("api_keys")
        if isinstance(nested, dict):
            redacted["api_keys"] = {
                name: (REDACTED if value else "")
                for name, value in nested.items()
            }
        return redacted

    def fulltext_config(self) -> Dict[str, Any]:
        """Payload the full-text step expects.

        Single source of truth for this dict shape, like :meth:`screener_config`.
        Defaults to *off*: fetching full text means dozens of network calls and
        tens of megabytes of PDFs, which is not something a run should start
        doing because it was upgraded.
        """
        raw = self.settings.get("fulltext")
        cfg = raw if isinstance(raw, dict) else {}

        return {
            "enabled": cfg.get("enabled", False) is True,
            "email": str(cfg.get("email") or self.settings.get("user_email") or ""),
            "max_papers": positive_int(cfg.get("max_papers"), DEFAULT_FULLTEXT_MAX_PAPERS),
            "time_budget_seconds": positive_int(
                cfg.get("time_budget_seconds"), DEFAULT_FULLTEXT_TIME_BUDGET
            ),
        }

    def save(self):
        """Persist current config back to the JSON file."""
        config: Dict[str, Any] = {}
        for attribute, path in self.SECTIONS:
            put_at_path(config, path, getattr(self, attribute))
        config["keyword_only_terms"] = self.keyword_only_terms
        config["keyword_only_category"] = self.keyword_only_category
        for k, value in self._raw.items():
            if k in config or k == "context_rules":
                continue
            config[k] = copy.deepcopy(value)

        if self._env_overrides:
            config = copy.deepcopy(config)
            for path in self._env_overrides:
                restore_from_disk(config, self._raw, path)

        if paths.is_inside_package(self.config_path):
            self.config_path = paths.user_config_file()
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            self.config_origin = paths.ORIGIN_USER_CONFIG

        write_json_atomically(self.config_path, config, indent=4)

        self._mtime = time.time()

