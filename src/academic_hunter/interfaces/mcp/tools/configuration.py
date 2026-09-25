"""MCP tools for managing the search configuration (config.json).

All tools accept a ``ctx: Context`` parameter (auto-injected by FastMCP)
for logging and progress reporting.
"""

import json
from mcp.server.fastmcp import Context
from academic_hunter.core import HunterConfig, get_config
from academic_hunter.core.infra import paths
from academic_hunter.plugins.connectors import CONNECTORS
from ..schemas.config_schema import SearchConfigUpdate
from ..memory.config_backup import MCPDatabaseManager
from ..exceptions import ConfigError


async def read_config(ctx: Context) -> str:
    """Returns the current full search configuration from config.json.

    Use this tool to check which anchors or technical_strings are currently configured.
    """
    await ctx.info("Reading configuration...")
    try:
        config = get_config()
        data = {
            # Which file this came from. The path is resolved by a search order
            # that depends on the environment the client spawned the server in,
            # so without this "why is my config ignored" has no answer a caller
            # can reach — and the packaged default looks like a config someone
            # chose, only an empty one.
            "config_source": {
                "path": str(config.config_path),
                "origin": str(config.config_origin),
                "is_default": config.config_origin == paths.ORIGIN_PACKAGED,
            },
            # Redacted: this goes to the MCP client, and a credential that
            # reaches the agent's context has leaked.
            "settings": config.public_settings(),
            "anchors": config.anchors,
            "technical_strings": config.tech_strings,
            "technical_weights": config.tech_weights,
            "context_rules": config.context_rules,
            "keyword_only_terms": config.keyword_only_terms,
            "keyword_only_category": config.keyword_only_category,
        }
        await ctx.info("Configuration read successfully")
        return json.dumps(data, indent=2, ensure_ascii=False)
    except ConfigError:
        raise
    except Exception as e:
        await ctx.error(f"Failed to read configuration: {e}")
        raise ConfigError(str(e))


def _search_plan(config) -> str:
    """What this configuration will actually ask, before a run is spent on it.

    ``technical_strings`` is what the four grid sources are queried with, and it
    is easy to leave empty -- the config then saves, searches two of six
    sources, and reports success. Saying so here is cheaper than finding it in
    the report.
    """
    grid = [name for name, cls in CONNECTORS.items() if not cls.is_keyword_only]
    keyword_only = [name for name, cls in CONNECTORS.items() if cls.is_keyword_only]

    lines = ["", "What this configuration will do:"]
    anchor_count = len(config.anchors)

    if not anchor_count:
        lines.append(
            "  Query nothing. The pipeline asks once per anchor and there are "
            "none, so run_search will refuse. Set anchors with update_config."
        )
        return "\n".join(lines)

    if config.tech_strings:
        grid_calls = anchor_count * len(config.tech_strings)
        lines.append(
            f"  Query {', '.join(grid)} once per anchor x technical-string "
            f"category ({grid_calls} queries), and {', '.join(keyword_only)} once "
            f"per anchor ({anchor_count} queries)."
        )
        return "\n".join(lines)

    lines.append(
        f"  Query only {', '.join(keyword_only)} ({anchor_count} queries). They "
        "take anchors alone. The grid sources "
        f"({', '.join(grid)}) need a technical string, so they will NOT be "
        "queried and the zeros they report are not findings."
    )
    lines.append(
        "  Add technical_strings -- a category per concept, with the terms the "
        "field uses -- and call update_config again."
    )
    return "\n".join(lines)


async def update_config(config_update: SearchConfigUpdate, ctx: Context) -> str:
    """Updates the Hunter search configuration.

    Use this tool WHENEVER the user asks to research a new topic.
    Automatically backs up the previous state before applying changes.

    The reply states what the new configuration will query, and names the
    sources that will be skipped, so an incomplete configuration is visible
    before run_search rather than as zeros in the report.

    Args:
        config_update: The new configuration to apply.
        ctx: FastMCP Context (auto-injected).
    """
    await ctx.info("Updating configuration...")
    try:
        config = get_config()

        # 1. Backup current state. `public_settings` masks the credentials: the
        # history lives in plain text in SQLite, and a config backup is not a
        # credential store.
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

        # 2. Apply updates
        if config_update.settings:
            config.settings.update(config_update.settings)
        # `is not None`, not truthiness: an empty mapping is a request to clear,
        # and an omitted one is a request to leave alone. The schema defaults to
        # `None`, so it is the only thing that separates them — with truthiness,
        # anchors could be set and never removed, and the call still said
        # "successfully".
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

        config.save()

        # 3. Save final state (masked, same as the "before" snapshot)
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
        return "Configuration updated and saved to history successfully!" + _search_plan(config)
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
            # A backup never carries credentials, so restore everything else and
            # keep the live ones. Assigning the stored dict wholesale would put
            # the redaction placeholder where the API key belongs.
            restored = {
                key: value
                for key, value in config_data["settings"].items()
                if key not in HunterConfig.SECRET_SETTINGS and key != "api_keys"
            }
            # Replaced, not merged. Merging left anything added since the backup
            # in place, so "restore this configuration" returned a hybrid of the
            # two that the researcher never configured and could not get out of.
            # The credentials are the single thing that has to survive.
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
