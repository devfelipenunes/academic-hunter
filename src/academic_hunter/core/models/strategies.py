from typing import Any

def strategy_max(old: Any, new: Any, **kwargs) -> int:
    return max(int(old or 0), int(new or 0))

def strategy_first_non_empty(old: Any, new: Any, **kwargs) -> Any:
    return old if old else new

def strategy_longest_string(old: Any, new: Any, **kwargs) -> str:
    old_str = str(old or "")
    new_str = str(new or "")
    return new_str if len(new_str) > len(old_str) else old_str

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
    priority = {"Yes": 3, "Likely": 2, "No (Preprint)": 1, "N/A": 0}
    new_status = str(new or "N/A")
    existing_status = str(old or "N/A")
    if priority.get(new_status, 0) > priority.get(existing_status, 0):
        return new_status
    return existing_status
