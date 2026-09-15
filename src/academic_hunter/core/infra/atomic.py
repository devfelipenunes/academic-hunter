"""Escrever um arquivo que outro processo pode estar lendo."""

import json
from pathlib import Path
from typing import Any


def write_json_atomically(path, payload: Any, *, indent: int = 2) -> None:
    """Write through a sibling temp file, then rename.

    `open(path, "w")` truncates before a single byte of the replacement exists, so
    a reader landing in that window gets a parse error from a file that is fine a
    millisecond later — and a failure mid-write leaves the old content gone as
    well. The rename is the only moment the target changes, and it is atomic.
    """
    target = Path(path)
    temporary = target.with_suffix(target.suffix + ".part")
    try:
        temporary.write_text(
            json.dumps(payload, indent=indent, ensure_ascii=False), encoding="utf-8"
        )
        temporary.replace(target)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise
