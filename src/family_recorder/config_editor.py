from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path


class ConfigEditError(RuntimeError):
    """Raised when a targeted YAML setting cannot be updated safely."""


def update_yaml_value(path: Path, section: str, key: str, value: object) -> None:
    """Update one two-space-indented YAML value while preserving all other text."""
    original = path.read_text(encoding="utf-8")
    lines = original.splitlines(keepends=True)
    section_pattern = re.compile(rf"^{re.escape(section)}:\s*(?:#.*)?(?:\r?\n)?$")
    key_pattern = re.compile(rf"^  {re.escape(key)}:\s*.*(?:\r?\n)?$")
    section_index = next(
        (index for index, line in enumerate(lines) if section_pattern.match(line)),
        None,
    )
    if section_index is None:
        newline = "\r\n" if "\r\n" in original else "\n"
        if original.strip() == "{}":
            original = ""
        separator = "" if not original or original.endswith(("\n", "\r")) else newline
        updated = (
            f"{original}{separator}{newline if original else ''}{section}:{newline}"
            f"  {key}: {json.dumps(value, ensure_ascii=False)}{newline}"
        )
        _atomic_replace(path, updated)
        return

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
        newline = "\r\n" if "\r\n" in original else "\n"
        lines.insert(end_index, f"  {key}: {json.dumps(value, ensure_ascii=False)}{newline}")
        _atomic_replace(path, "".join(lines))
        return

    newline = "\r\n" if lines[key_index].endswith("\r\n") else "\n"
    replacement = f"  {key}: {json.dumps(value, ensure_ascii=False)}{newline}"
    block_scalar = re.match(
        rf"^  {re.escape(key)}:\s*[|>][+-]?\s*(?:#.*)?(?:\r?\n)?$", lines[key_index]
    )
    if block_scalar:
        block_end = key_index + 1
        while block_end < len(lines):
            candidate = lines[block_end]
            if candidate.strip() and not candidate.startswith(("    ", "\t")):
                break
            block_end += 1
        lines[key_index:block_end] = [replacement]
    else:
        lines[key_index] = replacement
    _atomic_replace(path, "".join(lines))


def _atomic_replace(path: Path, updated: str) -> None:
    mode = path.stat().st_mode & 0o777
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as output:
            output.write(updated)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def update_yaml_scalar(path: Path, section: str, key: str, value: str) -> None:
    update_yaml_value(path, section, key, value)
