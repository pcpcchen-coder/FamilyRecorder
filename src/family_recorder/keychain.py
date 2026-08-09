from __future__ import annotations

import getpass
import subprocess


class KeychainError(RuntimeError):
    """Raised when a required macOS Keychain item is unavailable."""


def read_generic_password(service: str, account: str | None = None) -> str:
    account = account or getpass.getuser()
    command = [
        "/usr/bin/security",
        "find-generic-password",
        "-w",
        "-s",
        service,
        "-a",
        account,
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise KeychainError(
            f"No readable Keychain password for service {service!r}, account {account!r}. "
            "Add it with the command shown in README.md."
        )
    secret = result.stdout.strip()
    if not secret:
        raise KeychainError(f"Keychain item {service!r}/{account!r} is empty")
    return secret
