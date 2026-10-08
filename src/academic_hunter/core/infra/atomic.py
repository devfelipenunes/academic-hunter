"""Escrever um arquivo que outro processo pode estar lendo."""

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def write_json_atomically(path, payload: Any, *, indent: int = 2) -> None:
    """Write through a sibling temp file, then rename.

    `open(path, "w")` truncates before a single byte of the replacement exists, so
    a reader landing in that window gets a parse error from a file that is fine a
    millisecond later — and a failure mid-write leaves the old content gone as
    well. The rename is the only moment the target changes, and it is atomic.

    The payload is serialised before anything is created, and the temp file comes
    from `mkstemp` rather than a fixed `<name>.part`. Two writers aiming at one
    path shared that single fixed name, so whichever renamed first published
    whatever the other had written so far — a truncated config, from exactly the
    concurrent `save()` this function exists to survive.

    The mode of an existing target is carried across before the rename. Without
    it the replacement inherited the temp file's mode, so a `config.json`
    tightened to 0600 — what a file holding API keys deserves — came back 0644
    after the next `save()`. A target that does not exist yet keeps the 0600 that
    `mkstemp` opens with.
    """
    text = json.dumps(payload, indent=indent, ensure_ascii=False)

    target = Path(path)
    descriptor, name = tempfile.mkstemp(
        dir=target.parent, prefix=f"{target.name}.", suffix=".part"
    )
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        if target.exists():
            os.chmod(temporary, target.stat().st_mode)
        temporary.replace(target)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise
