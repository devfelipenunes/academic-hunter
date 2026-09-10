"""MCP tools for managing the search configuration (config.json).

All tools accept a ``ctx: Context`` parameter (auto-injected by FastMCP)
for logging and progress reporting.
"""

import json
from mcp.server.fastmcp import Context
from academic_hunter.core import get_config
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


async def update_config(config_update: SearchConfigUpdate, ctx: Context) -> str:
    """Updates the Hunter search configuration.

    Use this tool WHENEVER the user asks to research a new topic.
    Automatically backs up the previous state before applying changes.

    Args:
        config_update: The new configuration to apply.
        ctx: FastMCP Context (auto-injected).
    """
    await ctx.info("Updating configuration...")
    try:
        config = get_config()

        # 1. Backup current state
        db = MCPDatabaseManager()
        current_state = {
            "settings": config.settings,
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
        if config_update.anchors:
            config.anchors = config_update.anchors
        if config_update.technical_strings:
            config.tech_strings = config_update.technical_strings
        if config_update.technical_weights:
            config.tech_weights = config_update.technical_weights
        if config_update.context_rules is not None:
            config.context_rules = config_update.context_rules
        if config_update.keyword_only_terms is not None:
            config.keyword_only_terms = config_update.keyword_only_terms
        if config_update.keyword_only_category is not None:
            config.keyword_only_category = config_update.keyword_only_category

        config.save()

        # 3. Save final state
        new_state = {
            "settings": config.settings,
            "anchors": config.anchors,
            "technical_strings": config.tech_strings,
            "technical_weights": config.tech_weights,
            "context_rules": config.context_rules,
            "keyword_only_terms": config.keyword_only_terms,
            "keyword_only_category": config.keyword_only_category,
        }
        db.save_config(topic=topic_name, config_data=new_state)

        await ctx.info("Configuration updated successfully")
        return "Configuration updated and saved to history successfully!"
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
            config.settings = config_data["settings"]
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
