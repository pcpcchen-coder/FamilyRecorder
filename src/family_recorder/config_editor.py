from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path


class ConfigEditError(RuntimeError):
    """Raised when a targeted YAML setting cannot be updated safely."""


def update_yaml_scalar(path: Path, section: str, key: str, value: str) -> None:
    """Update one two-space-indented YAML scalar while preserving all other text."""
    original = path.read_text(encoding="utf-8")
    lines = original.splitlines(keepends=True)
    section_pattern = re.compile(rf"^{re.escape(section)}:\s*(?:#.*)?(?:\r?\n)?$")
    key_pattern = re.compile(rf"^  {re.escape(key)}:\s*.*(?:\r?\n)?$")
    section_index = next(
        (index for index, line in enumerate(lines) if section_pattern.match(line)),
        None,
    )
    if section_index is None:
        raise ConfigEditError(f"Config section {section!r} was not found in {path}")

    end_index = len(lines)
    for index in range(section_index + 1, len(lines)):
        line = lines[index]
        if line.strip() and not line.startswith((" ", "\t", "#")):
            end_index = index
            break
    key_index = next(
        (index for index in range(section_index + 1, end_index) if key_pattern.match(lines[index])),
        None,
    )
    if key_index is None:
        raise ConfigEditError(f"Config key {section}.{key} was not found in {path}")

    newline = "\r\n" if lines[key_index].endswith("\r\n") else "\n"
    lines[key_index] = f"  {key}: {json.dumps(value, ensure_ascii=False)}{newline}"
    updated = "".join(lines)
    mode = path.stat().st_mode & 0o777
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as output:
            output.write(updated)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
